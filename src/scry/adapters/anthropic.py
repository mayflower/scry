"""Anthropic Claude client wrapper (V2+/V4).

Minimal helper to request strict JSON responses for planning and diagnosis.
Falls back gracefully if the API key is missing or the request fails.
"""

from __future__ import annotations

import json
import os
from typing import Any


# Browser Tools API configuration
BROWSER_TOOLS_BETA_FLAG = "browser-tools-2025-09-10"
BROWSER_TOOLS_MODEL = "claude-opus-4-5-20251101"  # Current Claude Opus 4.5


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


def create_browser_tool_config(
    viewport_width: int = 1024, viewport_height: int = 768
) -> dict[str, Any]:
    """Create Browser Tools API tool configuration.

    Args:
        viewport_width: Browser viewport width in pixels
        viewport_height: Browser viewport height in pixels

    Returns:
        Tool configuration dict for browser_20250910 tool
    """
    return {
        "type": "browser_20250910",
        "name": "browser",
        "display_width_px": viewport_width,
        "display_height_px": viewport_height,
    }


def complete_with_browser_tools(
    messages: list[dict[str, Any]],
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    viewport_width: int = 1024,
    viewport_height: int = 768,
    system_prompt: str | None = None,
) -> Any:
    """Call Claude with Browser Tools API.

    Uses client.beta.messages.create() with betas parameter for Browser Tools API.

    Args:
        messages: Conversation messages in Anthropic format
        model: Claude model to use (default: BROWSER_TOOLS_MODEL)
               Supported models: claude-sonnet-4-20250514, claude-opus-4-20250514
        max_tokens: Max tokens in response
        temperature: Temperature for sampling (0.0 = deterministic)
        viewport_width: Browser viewport width
        viewport_height: Browser viewport height
        system_prompt: Optional system prompt

    Returns:
        Anthropic API response object
    """
    client = _client()

    # Use default model if not specified
    if model is None:
        model = BROWSER_TOOLS_MODEL

    tool_config = create_browser_tool_config(viewport_width, viewport_height)

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "tools": [tool_config],
        "messages": messages,
        "betas": [BROWSER_TOOLS_BETA_FLAG],
    }

    if system_prompt:
        kwargs["system"] = system_prompt

    return client.beta.messages.create(**kwargs)


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
