from __future__ import annotations

from typing import Any, Dict

from ...adapters.anthropic import has_api_key, complete_json


def extract_from_text(
    nl_request: str,
    parameters: Dict[str, Any] | None,
    schema: Dict[str, Any],
    text: str,
) -> Dict[str, Any]:
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
