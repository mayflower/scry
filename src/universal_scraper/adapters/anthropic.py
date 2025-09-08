"""Anthropic Claude client wrapper (V2+/V4).

Minimal helper to request strict JSON responses for planning and diagnosis.
Falls back gracefully if the API key is missing or the request fails.
"""

from __future__ import annotations

import json
import os
from typing import Any


def _get_api_key() -> str | None:
    # Prefer standard env name; fall back for backward compatibility
    return os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")


def has_api_key() -> bool:
    return bool(_get_api_key())


def _client():
    from anthropic import Anthropic

    key = _get_api_key()
    if not key:
        raise RuntimeError(
            "Anthropic API key not found in ANTHROPIC_API_KEY or CLAUDE_API_KEY"
        )
    return Anthropic(api_key=key)


def _extract_json(text: str) -> dict[str, Any]:
    # Best-effort JSON extraction
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            pass
    # Try code fence blocks
    if "```" in text:
        parts = text.split("```")
        for i in range(1, len(parts), 2):
            candidate = parts[i]
            if candidate.strip().startswith("json"):
                candidate = candidate[candidate.find("\n") + 1 :]
            try:
                return json.loads(candidate)
            except Exception:
                continue
    raise ValueError("Failed to parse JSON from Claude response")


def complete_json(
    system_prompt: str,
    user_prompt: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> tuple[dict[str, Any], str]:
    """Call Claude and return (json_dict, raw_text)."""
    client = _client()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    # Concatenate text blocks
    parts = []
    for block in msg.content:  # type: ignore[attr-defined]
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    raw = "".join(parts)
    data = _extract_json(raw)
    return data, raw
