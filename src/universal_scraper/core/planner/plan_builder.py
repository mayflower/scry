"""Natural language → IR planning (V2).

For V2, we keep planning minimal and deterministic:
- If target_urls is provided, plan a single Navigate to the first URL.
- Otherwise, no steps (future versions may add search).

Hook points for Anthropic Claude are left as placeholders.
"""

from __future__ import annotations

from ...adapters.anthropic import complete_json, has_api_key
from ...api.dto import ScrapeRequest
from ..ir.model import Click, Fill, Navigate, ScrapePlan, WaitFor


def _build_default(req: ScrapeRequest) -> ScrapePlan:
    if req.target_urls:
        return ScrapePlan(
            steps=[Navigate(url=req.target_urls[0])],
            notes="default: navigate to first target_url",
        )
    return ScrapePlan(steps=[], notes="default: no target url; empty plan")


def _sanitize_url(url: str) -> str:
    # Accept http(s) and data URLs for hermetic/local testing.
    if not isinstance(url, str):
        return ""
    if url.startswith("http") or url.startswith("data:text/html"):
        return url
    return ""


def build_plan(req: ScrapeRequest) -> ScrapePlan:
    # Use Claude to produce a plan if API key is present; fallback to default
    if not has_api_key():
        return _build_default(req)

    target_urls: list[str] = req.target_urls or []
    sys_prompt = (
        "You are a planner that converts a natural language scraping request into a JSON IR.\n"
        "Only output strict JSON. Supported step types: navigate(url), click(selector), fill(selector,text), wait_for(selector,state).\n"
        "Prefer generic, resilient selectors. If target_urls is provided, you MUST choose the first URL.\n"
        "IMPORTANT: Never use wait_for on metadata elements like <title>, <meta>, or hidden elements - these are for extraction only.\n"
        "Only use wait_for for visible page elements that might load dynamically.\n"
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
        '    {"type": "wait_for", "selector": string, "state": string}\n'
        "  ],\n"
        '  "notes": string\n'
        "}\n"
    )
    try:
        data, _ = complete_json(sys_prompt, user_prompt, max_tokens=400)
        steps = []
        for s in data.get("steps", []) or []:
            if not isinstance(s, dict):
                continue
            typ = s.get("type")
            if typ == "navigate":
                url = _sanitize_url(s.get("url", ""))
                if url:
                    steps.append(Navigate(url=url))
            elif typ == "click":
                sel = s.get("selector", "")
                if isinstance(sel, str) and sel:
                    steps.append(Click(selector=sel))
            elif typ == "fill":
                sel = s.get("selector", "")
                text = s.get("text", "")
                if isinstance(sel, str) and sel:
                    steps.append(Fill(selector=sel, text=str(text)))
            elif typ in ("wait_for", "waitfor", "wait"):
                sel = s.get("selector", "")
                state = s.get("state", "visible")
                # Skip WaitFor on metadata elements that are never visible
                if isinstance(sel, str) and sel:
                    # Don't wait for title, meta, or script tags
                    if not any(
                        tag in sel.lower()
                        for tag in ["title", "meta", "script", "style", "head"]
                    ):
                        steps.append(WaitFor(selector=sel, state=str(state)))
        # Ensure we always navigate to the first target URL if provided
        if req.target_urls:
            first = req.target_urls[0]
            if first and not any(isinstance(x, Navigate) for x in steps):
                steps.insert(0, Navigate(url=first))
        if not steps:
            return _build_default(req)
        return ScrapePlan(steps=steps, notes=str(data.get("notes") or "claude plan"))
    except Exception:
        return _build_default(req)
