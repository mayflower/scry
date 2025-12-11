from __future__ import annotations

from typing import Any

from ...adapters.anthropic import complete_json, has_api_key


def extract_from_text(
    nl_request: str,
    parameters: dict[str, Any] | None,
    schema: dict[str, Any],
    text: str,
) -> dict[str, Any]:
    params = parameters or {}
    sys = (
        "Extract structured JSON matching the provided schema from the given text.\n"
        "Only output JSON (no prose). Omit fields you cannot extract reliably.\n"
    )
    user = (
        f"goal: {nl_request}\n"
        f"parameters: {params}\n"
        f"schema: {schema}\n"
        f"text: {text[:12000]}\n"
    )
    if not has_api_key():
        return {}
    try:
        data, _ = complete_json(sys, user, max_tokens=600)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}
