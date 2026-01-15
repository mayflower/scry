"""Self-healing diagnose loop (V4).

Lightweight heuristic diagnosis to propose minimal, generic patches when
execution fails. Supports both heuristic and LLM-powered diagnosis.

Cookie banner handling uses `cookie_dismiss_selector` - a CSS selector
detected by LLM during exploration. No string matching fallbacks are used.
"""

from __future__ import annotations

from typing import Any

from ...adapters.anthropic import complete_json, has_api_key


def _heuristic_patch(attempt: int, stderr: str | None) -> dict[str, Any]:
    """Generate heuristic patch options based on attempt number and error.

    Args:
        attempt: Current retry attempt number (1-based)
        stderr: Error output from failed execution

    Returns:
        Dict of patch options to apply
    """
    opts: dict[str, Any] = {}
    text = (stderr or "").lower()

    # First attempts: try load-state waits and a short extra wait
    if attempt == 1:
        opts["wait_load_state"] = True
        opts["extra_wait_ms"] = 1000
        return opts

    # If we suspect timeouts, increase wait
    if "timeout" in text:
        opts["wait_load_state"] = True
        opts["extra_wait_ms"] = 2000

    return opts


def propose_patch(
    attempt: int,
    stderr: str | None,
    html: str | None,
    cookie_dismiss_selector: str | None = None,
) -> dict[str, Any]:
    """Propose patch options to fix failed execution.

    Args:
        attempt: Current retry attempt number (1-based)
        stderr: Error output from failed execution
        html: HTML snippet from the page at time of failure
        cookie_dismiss_selector: Pre-detected cookie banner dismiss selector

    Returns:
        Dict of patch options to apply during code regeneration
    """
    # If we have a pre-detected cookie selector, always include it
    base_patch: dict[str, Any] = {}
    if cookie_dismiss_selector:
        base_patch["cookie_dismiss_selector"] = cookie_dismiss_selector

    if not has_api_key():
        return {**_heuristic_patch(attempt, stderr), **base_patch}

    try:
        sys_prompt = (
            "You propose minimal, safe remediation options for Playwright scripts as JSON.\n"
            "Only output JSON with keys: wait_load_state (bool), extra_wait_ms (int).\n"
            "Never output code or prose.\n"
        )
        user_prompt = (
            f"Attempt: {attempt}\n"
            f"Stderr: {stderr or ''}\n"
            f"HTML_snippet: {(html or '')[:2000]}\n"
            "Return JSON object with any subset of the allowed keys."
        )
        data, _ = complete_json(sys_prompt, user_prompt, max_tokens=200)
        # Filter to allowed keys only
        allowed = {"wait_load_state", "extra_wait_ms"}
        patch = {k: v for k, v in (data or {}).items() if k in allowed}
        return {**patch, **base_patch}
    except Exception:
        return {**_heuristic_patch(attempt, stderr), **base_patch}
