"""Path compression & selector stabilization (V3/V5).

- Default `optimize_plan` keeps the plan (identity) for now.
- `compress_min_path_with_anthropic` uses Claude and an exploration trace to
  produce a shorter, direct ScrapePlan that reaches the goal quickly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...adapters.anthropic import complete_json, has_api_key
from ..ir.model import Click, Fill, Navigate, PlanStep, ScrapePlan, Validate, WaitFor

if TYPE_CHECKING:
    from ..nav.explore import ExplorationResult


# --- Optimization Helpers ---


def _is_duplicate_step(prev_step: Any, step: Any) -> bool:
    """Check if step is a duplicate of the previous step."""
    return prev_step is not None and _steps_are_equal(prev_step, step)


def _is_redundant_wait_after_navigate(step: Any, prev_step: Any) -> bool:
    """Check if WaitFor is redundant after Navigate."""
    return isinstance(step, WaitFor) and prev_step and isinstance(prev_step, Navigate)


def _try_merge_wait_for(step: Any, optimized_steps: list[Any]) -> bool:
    """Try to merge consecutive WaitFor steps for same selector.

    Returns True if step was merged, False otherwise.
    """
    if not isinstance(step, WaitFor):
        return False
    if not optimized_steps:
        return False
    last_step = optimized_steps[-1]
    if not isinstance(last_step, WaitFor):
        return False
    if last_step.selector != step.selector:
        return False

    # When merging, prioritize 'visible' over 'attached' (more restrictive)
    # The merged step keeps the existing state, current step is discarded
    if step.state == "attached" and last_step.state == "visible":
        pass  # Keep last_step.state as "visible"
    return True


def _handle_validate_step(step: Any, optimized_steps: list[Any]) -> bool:
    """Handle a Validate step, adding it only if it validates a real action.

    Returns True if step was handled, False otherwise.
    """
    if not isinstance(step, Validate):
        return False

    # Only add validation if there's a preceding action to validate
    if optimized_steps and not isinstance(optimized_steps[-1], Validate):
        optimized_steps.append(step)
    return True


def _improve_step_selector(step: Any) -> None:
    """Improve selector for Click or Fill steps."""
    if isinstance(step, (Click, Fill)) and step.selector:
        step.selector = _improve_selector(step.selector)


def optimize_plan(plan: ScrapePlan) -> ScrapePlan:
    """Optimize the plan by removing redundant steps and improving selectors."""
    if not plan.steps:
        return plan

    optimized_steps: list[Any] = []
    prev_step = None

    for step in plan.steps:
        # Skip duplicate consecutive steps
        if _is_duplicate_step(prev_step, step):
            continue

        # Skip WaitFor immediately after Navigate
        if _is_redundant_wait_after_navigate(step, prev_step):
            continue

        # Merge consecutive WaitFor for same selector
        if _try_merge_wait_for(step, optimized_steps):
            continue

        # Handle Validate steps specially
        if _handle_validate_step(step, optimized_steps):
            continue

        # Improve selector if applicable
        _improve_step_selector(step)

        optimized_steps.append(step)
        prev_step = step

    notes = f"optimized: {len(plan.steps)} -> {len(optimized_steps)} steps"
    return ScrapePlan(steps=optimized_steps, notes=notes)


def _steps_are_equal(step1: Any, step2: Any) -> bool:
    """Check if two steps are functionally equivalent."""
    if type(step1) is not type(step2):
        return False

    if isinstance(step1, Navigate):
        return step1.url == step2.url
    if isinstance(step1, Click):
        return step1.selector == step2.selector
    if isinstance(step1, Fill):
        return step1.selector == step2.selector and step1.text == step2.text
    if isinstance(step1, WaitFor):
        return step1.selector == step2.selector and step1.state == step2.state
    # Validate steps are not compared for equality - preserve all checkpoints

    return False


# --- Selector Improvement ---


def _has_stable_attribute(selector: str) -> bool:
    """Check if selector uses stable attributes."""
    stable_attrs = ["data-testid=", "data-test=", "aria-label="]
    return any(attr in selector for attr in stable_attrs)


def _is_simple_id_selector(selector: str) -> bool:
    """Check if selector is a simple #id selector."""
    return selector.startswith("#") and " " not in selector


def _simplify_multi_class_selector(selector: str) -> str | None:
    """Simplify selector with many classes to first 4 parts."""
    if "." not in selector or selector.count(".") <= 3:
        return None
    parts = selector.split(".")
    return ".".join(parts[:4])


def _remove_nth_child(selector: str) -> str | None:
    """Remove fragile nth-child pseudo-selectors."""
    if ":nth-child(" not in selector:
        return None
    import re

    cleaned = re.sub(r":nth-child\([^)]+\)", "", selector)
    if cleaned and cleaned != selector:
        return cleaned.strip()
    return None


def _improve_selector(selector: str) -> str:
    """Improve selector for better resilience."""
    normalized = " ".join(selector.split())

    if _has_stable_attribute(normalized):
        return normalized

    if _is_simple_id_selector(normalized):
        return normalized

    simplified = _simplify_multi_class_selector(normalized)
    if simplified:
        return simplified

    cleaned = _remove_nth_child(normalized)
    if cleaned:
        return cleaned

    return normalized


# --- Step Serialization ---


def _step_to_dict(step: Any) -> dict[str, Any] | None:
    """Convert a step to its dictionary representation."""
    if isinstance(step, Navigate):
        return {"type": "navigate", "url": step.url}
    if isinstance(step, Click):
        return {"type": "click", "selector": step.selector}
    if isinstance(step, Fill):
        return {"type": "fill", "selector": step.selector, "text": step.text}
    if isinstance(step, WaitFor):
        return {"type": "wait_for", "selector": step.selector, "state": step.state}
    if isinstance(step, Validate):
        return {
            "type": "validate",
            "selector": step.selector,
            "validation_type": step.validation_type,
            "is_critical": step.is_critical,
            "description": step.description,
        }
    return None


def _dict_to_step(s: dict[str, Any]) -> PlanStep | None:
    """Convert a dictionary to a step object."""
    t = s.get("type")
    if t == "navigate" and s.get("url"):
        return Navigate(url=str(s["url"]))
    if t == "click" and s.get("selector"):
        return Click(selector=str(s["selector"]))
    if t == "fill" and s.get("selector"):
        return Fill(selector=str(s["selector"]), text=str(s.get("text", "")))
    if t in ("wait_for", "wait", "waitfor") and s.get("selector"):
        return WaitFor(
            selector=str(s["selector"]),
            state=str(s.get("state", "visible")),
        )
    return None


# --- LLM Compression ---


def _build_steps_repr(steps: list[Any]) -> list[dict[str, Any]]:
    """Build a compact representation of exploration steps."""
    steps_repr: list[dict[str, Any]] = []
    for s in steps:
        d = _step_to_dict(s)
        if d:
            steps_repr.append(d)
    return steps_repr


def _build_compression_prompt(
    nl_request: str, schema: dict[str, Any], explore: ExplorationResult
) -> tuple[str, str]:
    """Build system and user prompts for LLM compression."""
    import json

    sys = (
        "Given an exploration trace (naive actions) and the goal, generate the shortest deterministic plan.\n"
        "Use only steps: navigate(url), click(selector), fill(selector,text), wait_for(selector,state).\n"
        "Prefer direct navigation to discovered URLs when safe. Prefer resilient selectors.\n"
        "Output ONLY JSON with keys: steps[], notes.\n"
    )

    steps_repr = _build_steps_repr(explore.steps)
    user = (
        f"goal: {nl_request}\n"
        f"schema: {json.dumps(schema)}\n"
        f"visited_urls: {json.dumps(explore.urls)}\n"
        f"trace: {json.dumps(steps_repr)}\n"
        'Return JSON: {"steps": [...], "notes": string}'
    )
    return sys, user


def _parse_compressed_steps(data: dict[str, Any]) -> list[PlanStep]:
    """Parse LLM response into step objects."""
    out_steps: list[PlanStep] = []
    for s in data.get("steps", []) or []:
        if not isinstance(s, dict):
            continue
        step = _dict_to_step(s)
        if step:
            out_steps.append(step)
    return out_steps


def compress_min_path_with_anthropic(
    explore: ExplorationResult, nl_request: str, schema: dict[str, Any]
) -> ScrapePlan:
    """Use Claude to compress exploration trace into optimal path."""
    if not has_api_key():
        return ScrapePlan(steps=explore.steps, notes="no_key: using explored steps")

    sys, user = _build_compression_prompt(nl_request, schema, explore)

    try:
        data, _ = complete_json(sys, user, max_tokens=600)
        out_steps = _parse_compressed_steps(data)
        if out_steps:
            return ScrapePlan(steps=out_steps, notes=str(data.get("notes") or "compressed"))
    except Exception:  # noqa: S110 - fallback to unoptimized steps on failure
        pass

    return ScrapePlan(steps=explore.steps, notes="fallback: explored steps")
