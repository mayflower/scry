"""Path compression & selector stabilization (V3/V5).

- Default `optimize_plan` keeps the plan (identity) for now.
- `compress_min_path_with_anthropic` uses Claude and an exploration trace to
  produce a shorter, direct ScrapePlan that reaches the goal quickly.
"""

from __future__ import annotations

from typing import Any

from ...adapters.anthropic import complete_json, has_api_key
from ..ir.model import Click, Fill, Navigate, PlanStep, ScrapePlan, WaitFor
from ..nav.explore import ExplorationResult


def optimize_plan(plan: ScrapePlan) -> ScrapePlan:
    """Optimize the plan by removing redundant steps and improving selectors.

    Optimizations applied:
    1. Remove consecutive duplicate steps
    2. Merge consecutive WaitFor steps for the same selector
    3. Remove unnecessary waits after navigations
    4. Improve selector resilience
    """
    if not plan.steps:
        return plan

    optimized_steps: list[Any] = []
    prev_step = None

    for step in plan.steps:
        # Skip duplicate consecutive steps
        if prev_step and _steps_are_equal(prev_step, step):
            continue

        # Skip WaitFor immediately after Navigate (navigation already waits)
        if isinstance(step, WaitFor) and prev_step and isinstance(prev_step, Navigate):
            continue

        # Merge consecutive WaitFor for same selector
        if (
            isinstance(step, WaitFor)
            and optimized_steps
            and isinstance(optimized_steps[-1], WaitFor)
            and optimized_steps[-1].selector == step.selector
        ):
            # Keep the most restrictive wait state
            if step.state == "attached" and optimized_steps[-1].state == "visible":
                optimized_steps[-1].state = "visible"
            continue

        # Improve selector if it's a Click or Fill
        if isinstance(step, (Click, Fill)) and step.selector:
            step.selector = _improve_selector(step.selector)

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

    return False


def _improve_selector(selector: str) -> str:
    """Improve selector for better resilience.

    Prioritizes:
    1. data-testid attributes
    2. id attributes
    3. aria-label attributes
    4. Unique class combinations
    """
    # If already using a stable attribute, keep it
    if any(attr in selector for attr in ["data-testid=", "#", "aria-label="]):
        return selector

    # For now, return as-is (full implementation would analyze DOM)
    # In production, this would analyze the HTML to find better selectors
    return selector


def compress_min_path_with_anthropic(
    explore: ExplorationResult, nl_request: str, schema: dict[str, Any]
) -> ScrapePlan:
    if not has_api_key():
        return ScrapePlan(steps=explore.steps, notes="no_key: using explored steps")

    # Build a compact representation of the exploration
    steps_repr: list[dict[str, Any]] = []
    for s in explore.steps:
        if isinstance(s, Navigate):
            steps_repr.append({"type": "navigate", "url": s.url})
        elif isinstance(s, Click):
            steps_repr.append({"type": "click", "selector": s.selector})
        elif isinstance(s, Fill):
            steps_repr.append({"type": "fill", "selector": s.selector, "text": s.text})
        elif isinstance(s, WaitFor):
            steps_repr.append({"type": "wait_for", "selector": s.selector, "state": s.state})

    sys = (
        "Given an exploration trace (naive actions) and the goal, generate the shortest deterministic plan.\n"
        "Use only steps: navigate(url), click(selector), fill(selector,text), wait_for(selector,state).\n"
        "Prefer direct navigation to discovered URLs when safe. Prefer resilient selectors.\n"
        "Output ONLY JSON with keys: steps[], notes.\n"
    )
    import json

    user = (
        f"goal: {nl_request}\n"
        f"schema: {json.dumps(schema)}\n"
        f"visited_urls: {json.dumps(explore.urls)}\n"
        f"trace: {json.dumps(steps_repr)}\n"
        'Return JSON: {"steps": [...], "notes": string}'
    )
    try:
        data, _ = complete_json(sys, user, max_tokens=600)
        out_steps: list[PlanStep] = []
        for s in data.get("steps", []) or []:
            if not isinstance(s, dict):
                continue
            t = s.get("type")
            if t == "navigate" and s.get("url"):
                out_steps.append(Navigate(url=str(s["url"])))
            elif t == "click" and s.get("selector"):
                out_steps.append(Click(selector=str(s["selector"])))
            elif t == "fill" and s.get("selector"):
                out_steps.append(Fill(selector=str(s["selector"]), text=str(s.get("text", ""))))
            elif t in ("wait_for", "wait", "waitfor") and s.get("selector"):
                out_steps.append(
                    WaitFor(
                        selector=str(s["selector"]),
                        state=str(s.get("state", "visible")),
                    )
                )
        if out_steps:
            return ScrapePlan(steps=out_steps, notes=str(data.get("notes") or "compressed"))
    except Exception:
        pass

    return ScrapePlan(steps=explore.steps, notes="fallback: explored steps")
