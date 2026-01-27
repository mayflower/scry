"""Natural language → IR planning (V2).

For V2, we keep planning minimal and deterministic:
- If target_urls is provided, plan a single Navigate to the first URL.
- Otherwise, no steps (future versions may add search).

Hook points for Anthropic Claude are left as placeholders.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...adapters.anthropic import complete_json, has_api_key
from ..ir.model import (
    Click,
    Fill,
    Hover,
    KeyPress,
    Navigate,
    ScrapePlan,
    Select,
    Upload,
    Validate,
    WaitFor,
)

if TYPE_CHECKING:
    from ...api.dto import ScrapeRequest

# Type alias for step union
StepType = Navigate | Click | Fill | Select | Hover | KeyPress | Upload | WaitFor | Validate


def _build_default(req: ScrapeRequest) -> ScrapePlan:
    """Build default plan when no LLM is available."""
    if req.target_urls:
        return ScrapePlan(
            steps=[Navigate(url=req.target_urls[0])],
            notes="default: navigate to first target_url",
        )
    return ScrapePlan(steps=[], notes="default: no target url; empty plan")


def _sanitize_url(url: str) -> str:
    """Sanitize URL to accept only http(s) and data URLs."""
    if not isinstance(url, str):
        return ""
    if url.startswith("http") or url.startswith("data:text/html"):
        return url
    return ""


# --- Step Parsers ---


def _parse_navigate(s: dict[str, Any]) -> Navigate | None:
    """Parse a navigate step."""
    url = _sanitize_url(s.get("url", ""))
    return Navigate(url=url) if url else None


def _parse_click(s: dict[str, Any]) -> Click | None:
    """Parse a click step."""
    sel = s.get("selector", "")
    if isinstance(sel, str) and sel:
        return Click(selector=sel)
    return None


def _parse_fill(s: dict[str, Any]) -> Fill | None:
    """Parse a fill step."""
    sel = s.get("selector", "")
    text = s.get("text", "")
    if isinstance(sel, str) and sel:
        return Fill(selector=sel, text=str(text))
    return None


def _parse_wait_for(s: dict[str, Any]) -> WaitFor | None:
    """Parse a wait_for step, skipping metadata elements."""
    sel = s.get("selector", "")
    state = s.get("state", "visible")

    if not isinstance(sel, str) or not sel:
        return None

    # Skip WaitFor on metadata elements that are never visible
    metadata_tags = ["title", "meta", "script", "style", "head"]
    if any(tag in sel.lower() for tag in metadata_tags):
        return None

    return WaitFor(selector=sel, state=str(state))


def _parse_select(s: dict[str, Any]) -> Select | None:
    """Parse a select step."""
    sel = s.get("selector", "")
    value = s.get("value", "")
    if isinstance(sel, str) and sel and isinstance(value, str):
        return Select(selector=sel, value=value)
    return None


def _parse_hover(s: dict[str, Any]) -> Hover | None:
    """Parse a hover step."""
    sel = s.get("selector", "")
    if isinstance(sel, str) and sel:
        return Hover(selector=sel)
    return None


def _parse_keypress(s: dict[str, Any]) -> KeyPress | None:
    """Parse a keypress step."""
    key = s.get("key", "")
    selector = s.get("selector")
    if isinstance(key, str) and key:
        return KeyPress(key=key, selector=selector)
    return None


def _parse_upload(s: dict[str, Any]) -> Upload | None:
    """Parse an upload step."""
    sel = s.get("selector", "")
    file_path = s.get("file_path", "")
    if isinstance(sel, str) and sel and isinstance(file_path, str):
        return Upload(selector=sel, file_path=file_path)
    return None


# Step type to parser mapping
_STEP_PARSERS: dict[str, Any] = {
    "navigate": _parse_navigate,
    "click": _parse_click,
    "fill": _parse_fill,
    "wait_for": _parse_wait_for,
    "waitfor": _parse_wait_for,
    "wait": _parse_wait_for,
    "select": _parse_select,
    "hover": _parse_hover,
    "keypress": _parse_keypress,
    "key_press": _parse_keypress,
    "press": _parse_keypress,
    "upload": _parse_upload,
}


def _parse_step(s: dict[str, Any]) -> StepType | None:
    """Parse a single step from LLM response."""
    if not isinstance(s, dict):
        return None

    typ = s.get("type")
    if not isinstance(typ, str):
        return None

    parser = _STEP_PARSERS.get(typ)
    if parser:
        return parser(s)
    return None


def _ensure_navigation(steps: list[StepType], target_urls: list[str]) -> None:
    """Ensure the plan navigates to the first target URL if provided."""
    if not target_urls:
        return

    first = target_urls[0]
    if first and not any(isinstance(x, Navigate) for x in steps):
        steps.insert(0, Navigate(url=first))


def _call_llm_planner(req: ScrapeRequest) -> dict[str, Any] | None:
    """Call LLM to generate a scraping plan."""
    target_urls: list[str] = req.target_urls or []

    sys_prompt = (
        "You are a planner that converts a natural language scraping request into a JSON IR.\n"
        "Only output strict JSON. Supported step types: navigate(url), click(selector), fill(selector,text), "
        "select(selector,value), hover(selector), keypress(key,selector?), upload(selector,file_path), wait_for(selector,state).\n"
        "Prefer generic, resilient selectors. If target_urls is provided, you MUST choose the first URL.\n"
        "IMPORTANT: Never use wait_for on metadata elements like <title>, <meta>, or hidden elements.\n"
    )
    user_prompt = (
        f"nl_request: {req.nl_request}\n\n"
        f"target_urls: {target_urls}\n\n"
        f"schema: {req.output_schema}\n\n"
        "Return JSON with shape: {\n"
        '  "steps": [\n'
        '    {"type": "navigate", "url": string} |\n'
        '    {"type": "click", "selector": string} |\n'
        '    {"type": "fill", "selector": string, "text": string} |\n'
        '    {"type": "select", "selector": string, "value": string} |\n'
        '    {"type": "hover", "selector": string} |\n'
        '    {"type": "keypress", "key": string, "selector": string?} |\n'
        '    {"type": "upload", "selector": string, "file_path": string} |\n'
        '    {"type": "wait_for", "selector": string, "state": string}\n'
        "  ],\n"
        '  "notes": string\n'
        "}\n"
    )

    try:
        data, _ = complete_json(sys_prompt, user_prompt, max_tokens=400)
        return data
    except Exception:
        return None


def build_plan(req: ScrapeRequest) -> ScrapePlan:
    """Build a scraping plan from a request, using LLM if available."""
    if not has_api_key():
        return _build_default(req)

    data = _call_llm_planner(req)
    if not data:
        return _build_default(req)

    steps: list[StepType] = []
    for s in data.get("steps", []) or []:
        step = _parse_step(s)
        if step:
            steps.append(step)

    _ensure_navigation(steps, req.target_urls or [])

    if not steps:
        return _build_default(req)

    return ScrapePlan(steps=steps, notes=str(data.get("notes") or "claude plan"))
