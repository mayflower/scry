from __future__ import annotations

from typing import Any

from ...adapters.anthropic import complete_json, has_api_key


def synthesize_selectors(
    nl_request: str,
    parameters: dict[str, Any] | None,
    schema: dict[str, Any],
    html: str,
    url: str,
) -> dict[str, dict[str, Any]]:
    """Ask Anthropic to propose CSS selectors for each schema field.

    Returns a dict mapping field -> {selector: str, regex?: str, attr?: str}
    """
    params = parameters or {}
    sys = (
        "You output only JSON. Task: Propose robust CSS selectors (and optional regex)\n"
        "to extract fields from the given HTML for the user goal.\n"
        "Return an object mapping field names to {selector, regex?}. Prefer unique selectors.\n"
    )
    user = (
        f"url: {url}\n"
        f"goal: {nl_request}\n"
        f"parameters: {params}\n"
        f"schema: {schema}\n"
        "html (truncated):\n" + html[:15000]
    )
    if not has_api_key():
        return {}
    try:
        data, _ = complete_json(sys, user, max_tokens=800)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}
