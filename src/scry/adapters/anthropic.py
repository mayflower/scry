"""Anthropic Claude client wrapper (V2+/V4).

Minimal helper to request strict JSON responses for planning and diagnosis.
Falls back gracefully if the API key is missing or the request fails.

Browser automation support follows the claude-quickstarts/browser-use-demo approach:
- Custom tool schema (BROWSER_TOOL_INPUT_SCHEMA)
- Regular messages API with tools parameter
- Manual tool execution via Playwright
"""

from __future__ import annotations

import json
import os
from typing import Any


# Browser Tool configuration (following browser-use-demo approach)
# Uses standard messages API with custom tool definition, NOT beta browser tools API
BROWSER_TOOL_MODEL = "claude-sonnet-4-20250514"
BROWSER_TOOLS_ENABLED = os.getenv("BROWSER_TOOLS_ENABLED", "false").lower() == "true"
PROMPT_CACHING_BETA_FLAG = "prompt-caching-2024-07-31"

# Custom browser tool input schema (adapted from browser-use-demo)
BROWSER_TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "properties": {
        "action": {
            "description": """The action to perform. Available actions:
* `navigate`: Navigate to a URL. Automatically includes a screenshot.
* `screenshot`: Take a screenshot of the current browser viewport.
* `left_click`: Click at the specified coordinate or element reference.
* `double_click`: Double-click at the specified coordinate or element reference.
* `hover`: Move cursor to coordinate or element reference without clicking.
* `scroll`: Scroll the page in a specified direction.
* `scroll_to`: Scroll to bring an element into view.
* `type`: Type text at the current cursor position.
* `key`: Press a key or key combination (e.g., "Enter", "ctrl+a").
* `read_page`: Get the DOM tree structure with element references.
* `get_page_text`: Get all text content from the page.
* `wait`: Wait for a specified duration in seconds.
* `form_input`: Set the value of a form input element by ref.
* `execute_js`: Execute JavaScript code in the page context.""",
            "enum": [
                "navigate",
                "screenshot",
                "left_click",
                "double_click",
                "hover",
                "scroll",
                "scroll_to",
                "type",
                "key",
                "read_page",
                "get_page_text",
                "wait",
                "form_input",
                "execute_js",
            ],
            "type": "string",
        },
        "text": {
            "description": "Required for: `navigate` (URL), `type` (text to type), `key` (key to press), `execute_js` (JavaScript code).",
            "type": "string",
        },
        "ref": {
            "description": "Element reference (ref_X) for targeting DOM elements. Required for `scroll_to` and `form_input`. Optional for click/hover as alternative to coordinates.",
            "type": "string",
        },
        "coordinate": {
            "description": "(x, y): Pixel coordinates for mouse actions when `ref` is not provided.",
            "type": "array",
            "items": {"type": "integer"},
        },
        "scroll_direction": {
            "description": "The direction to scroll. Required for `scroll` action.",
            "enum": ["up", "down", "left", "right"],
            "type": "string",
        },
        "scroll_amount": {
            "description": "Number of scroll units. Required for `scroll` action.",
            "type": "integer",
        },
        "duration": {
            "description": "Duration in seconds. Required for `wait` action.",
            "type": "number",
        },
        "value": {
            "description": "The value to set for a form input. Required for `form_input` action.",
            "type": ["string", "number", "boolean"],
        },
    },
    "required": ["action"],
    "type": "object",
}

BROWSER_TOOL_DESCRIPTION = """A browser automation tool for web interaction.

Key actions:
- navigate: Go to a URL (automatically includes a screenshot)
- screenshot: Take a visual screenshot
- read_page: Get DOM structure with element references (ref_X)
- get_page_text: Extract all text content
- left_click, double_click: Click elements
- hover: Move cursor without clicking (for tooltips, dropdowns)
- type: Enter text at cursor
- scroll: Scroll the page
- form_input: Fill form fields by ref
- execute_js: Run JavaScript in page context

After navigating, always call read_page first to get element references."""


def _get_api_key() -> str | None:
    # Prefer standard env name; fall back for backward compatibility
    return os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")


def has_api_key() -> bool:
    return bool(_get_api_key())


def has_browser_tools() -> bool:
    """Check if Browser Tools API is enabled and available."""
    return BROWSER_TOOLS_ENABLED and has_api_key()


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


def get_browser_tool_definition() -> dict[str, Any]:
    """Get the browser tool definition for the messages API.

    Returns a standard tool definition that can be passed to client.messages.create().
    Follows the claude-quickstarts/browser-use-demo approach.
    """
    return {
        "name": "browser",
        "description": BROWSER_TOOL_DESCRIPTION,
        "input_schema": BROWSER_TOOL_INPUT_SCHEMA,
    }


def call_with_browser_tool(
    messages: list[dict[str, Any]],
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system_prompt: str | None = None,
) -> Any:
    """Call Claude with browser tool capability.

    Uses standard client.messages.create() with custom tool definition.
    This follows the claude-quickstarts/browser-use-demo approach -
    NO special beta API required.

    Args:
        messages: Conversation messages in Anthropic format
        model: Claude model to use (default: BROWSER_TOOL_MODEL)
        max_tokens: Max tokens in response
        temperature: Temperature for sampling (0.0 = deterministic)
        system_prompt: Optional system prompt

    Returns:
        Anthropic API response object
    """
    client = _client()

    if model is None:
        model = BROWSER_TOOL_MODEL

    tool_def = get_browser_tool_definition()

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "tools": [tool_def],
        "messages": messages,
    }

    if system_prompt:
        kwargs["system"] = system_prompt

    return client.messages.create(**kwargs)


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
