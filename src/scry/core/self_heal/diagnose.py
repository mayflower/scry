"""Self-healing diagnose loop (V4).

Lightweight heuristic diagnosis to propose minimal, generic patches when
execution fails. Hooks for Anthropic Claude can be added later.
"""

from __future__ import annotations

from typing import Any

from ...adapters.anthropic import complete_json, has_api_key


def _heuristic_patch(attempt: int, stderr: str | None) -> dict[str, Any]:
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

    # Try dismissing cookie banners generically
    if attempt >= 2:
        opts["handle_cookie_banner"] = True

    return opts


def propose_patch(attempt: int, stderr: str | None, html: str | None) -> dict[str, Any]:
    if not has_api_key():
        return _heuristic_patch(attempt, stderr)
    try:
        sys_prompt = (
            "You propose minimal, safe remediation options for Playwright scripts as JSON.\n"
            "Only output JSON with keys: wait_load_state (bool), extra_wait_ms (int), handle_cookie_banner (bool).\n"
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
        allowed = {"wait_load_state", "extra_wait_ms", "handle_cookie_banner"}
        return {k: v for k, v in (data or {}).items() if k in allowed}
    except Exception:
        return _heuristic_patch(attempt, stderr)
