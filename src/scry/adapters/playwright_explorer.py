"""Native Playwright-based agentic exploration using Browser Tools API.

This module implements web exploration using Anthropic's native Browser Tools API
(browser_20250910), which provides more robust automation through element references
and accessibility tree navigation compared to custom JSON-based approaches.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.ir.model import (
    Click,
    Fill,
    KeyPress,
    Navigate,
)
from ..core.nav.explore import ExplorationResult
from .anthropic import complete_with_browser_tools, has_api_key
from .browser_executor import BrowserExecutor


def _create_system_prompt() -> str:
    """Create system prompt for browser automation agent."""
    return """You are a web automation agent using browser tools to explore websites and extract data.

Your capabilities:
- navigate: Go to URLs or use browser history (back/forward)
- read_page: See the page structure with element references (ref_X)
- screenshot: Capture current viewport
- left_click: Click elements by ref or coordinate
- type: Type text into focused element
- form_input: Directly set form field values by ref
- scroll: Scroll in direction (up/down/left/right)
- key: Press keyboard keys (enter, tab, etc.)
- wait: Wait for specified duration

IMPORTANT WORKFLOW:
1. After navigating to a page, ALWAYS call read_page first to understand the structure
2. Use element references (ref_X) from read_page output for reliable interaction
3. Handle cookie banners immediately - look for "Accept", "OK", "Agree" buttons
4. Be efficient - minimize unnecessary actions
5. When you've completed the task or are stuck, explain your reasoning

Element references are stable identifiers that survive page changes better than CSS selectors."""


def _map_tool_action_to_ir(
    action_name: str, input_data: dict[str, Any], ref_manager: Any
) -> Any:
    """Map Browser Tools API action to IR action.

    Args:
        action_name: Browser tool action name
        input_data: Action input data from tool_use block
        ref_manager: Element reference manager for selector lookup

    Returns:
        IR action object (Navigate, Click, Fill, etc.) or None
    """
    if action_name == "navigate":
        url = input_data.get("text", "")
        if url and url not in ("back", "forward"):
            return Navigate(url=url)

    elif action_name == "left_click":
        ref = input_data.get("ref")
        if ref:
            ref_data = ref_manager.get_ref(ref)
            if ref_data:
                return Click(selector=ref_data.selector)

    elif action_name in ("type", "form_input"):
        ref = input_data.get("ref")
        text = input_data.get("text") or input_data.get("value")
        if ref and text:
            ref_data = ref_manager.get_ref(ref)
            if ref_data:
                return Fill(selector=ref_data.selector, text=str(text))

    elif action_name == "key":
        key_text = input_data.get("text", "")
        if key_text:
            return KeyPress(key=key_text)

    # Note: scroll, screenshot, read_page, etc. are exploration actions
    # that don't map to IR actions - they're for runtime only

    return None


def explore_with_playwright(
    start_url: str,
    nl_request: str,
    schema: dict[str, Any],
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    max_steps: int = 20,
    headless: bool = True,
    login_params: dict[str, Any] | None = None,
) -> ExplorationResult:
    """Explore website using Browser Tools API.

    This replaces the custom JSON-based exploration with native Anthropic
    Browser Tools API integration for more robust automation.

    Args:
        start_url: Starting URL for exploration
        nl_request: Natural language request describing the task
        schema: JSON schema for data to extract
        screenshots_dir: Directory for saving screenshots
        html_dir: Directory for saving HTML snapshots
        job_id: Unique job identifier
        max_steps: Maximum exploration steps (default: 20)
        headless: Whether to run browser in headless mode
        login_params: Optional login credentials (username, password)

    Returns:
        ExplorationResult with actions, screenshots, HTML pages, URLs, and extracted data
    """
    print(f"[Explorer] Starting Browser Tools API exploration for job {job_id}")
    print(f"[Explorer] Target: {start_url}")
    print(f"[Explorer] Task: {nl_request}")

    if not has_api_key():
        print("[Explorer] No API key found, falling back to basic navigation")
        # Fallback to simple navigation without LLM
        steps = [Navigate(url=start_url)]
        return ExplorationResult(
            steps=steps,  # type: ignore[arg-type]
            screenshots=[],
            html_pages=[],
            urls=[start_url],
            data={},
        )

    # Initialize browser executor
    executor = BrowserExecutor(
        viewport_width=1280, viewport_height=720, headless=headless
    )
    executor.start()

    try:
        # Track exploration results
        ir_actions: list[Any] = []
        urls: list[str] = []
        html_pages: list[str] = []
        screenshots: list[Path] = []
        data: dict[str, Any] = {}

        # Build task description
        task_description = f"""Task: {nl_request}

Target schema for data extraction:
{schema}

Starting URL: {start_url}

Instructions:
1. Navigate to the starting URL
2. Explore the site to accomplish the task
3. Extract data matching the schema when found
4. Be efficient - complete the task in as few steps as possible

When you're done or stuck, explain what you accomplished."""

        # Initialize conversation with user task
        messages: list[dict[str, Any]] = [{"role": "user", "content": task_description}]

        # Agent loop
        for iteration in range(max_steps):
            print(f"[Explorer] Iteration {iteration + 1}/{max_steps}")

            # Call Claude with browser tools (uses BROWSER_TOOLS_MODEL by default)
            try:
                response = complete_with_browser_tools(
                    messages=messages,
                    max_tokens=4096,
                    system_prompt=_create_system_prompt(),
                )
            except Exception as e:
                print(f"[Explorer] API error: {e}")
                break

            # Process response - build assistant message
            assistant_content: list[dict[str, Any]] = []

            # Extract text and tool_use blocks
            has_tool_use = False
            for block in response.content:
                if hasattr(block, "type"):
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                        print(f"[Explorer] Claude: {block.text[:200]}")
                    elif block.type == "tool_use":
                        has_tool_use = True
                        assistant_content.append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )
                        action_name = block.input.get("action", "unknown")
                        print(f"[Explorer] Tool use: {action_name} (id: {block.id})")

            # Add assistant message to conversation
            messages.append({"role": "assistant", "content": assistant_content})

            # Check if done (no more tool use)
            if not has_tool_use or response.stop_reason != "tool_use":
                print("[Explorer] Agent finished - no more tool use")
                break

            # Execute tool calls and collect results
            tool_results: list[dict[str, Any]] = []

            for block in response.content:
                if not hasattr(block, "type") or block.type != "tool_use":
                    continue

                if block.name != "browser":
                    print(f"[Explorer] Warning: unknown tool {block.name}")
                    continue

                # Execute browser action
                result = executor.execute(block.id, block.input)
                tool_results.append(result)

                # Map to IR action if applicable
                action_name = block.input.get("action", "")
                ir_action = _map_tool_action_to_ir(
                    action_name, block.input, executor.ref_manager
                )
                if ir_action:
                    ir_actions.append(ir_action)

                # Track navigation URLs
                if action_name == "navigate":
                    nav_url = block.input.get("text", "")
                    if nav_url and nav_url not in ("back", "forward"):
                        urls.append(nav_url)

                # Save screenshots from tool results
                if not result.get("is_error"):
                    for content in result.get("content", []):
                        if content.get("type") == "image":
                            # Screenshot is in base64 - we could decode and save it
                            # For now, just track that we have it
                            screenshot_path = (
                                screenshots_dir
                                / f"browser-api-step-{iteration}-{job_id}.png"
                            )
                            screenshots.append(screenshot_path)
                            # Note: In production, decode base64 and save actual file

            # Add tool results to conversation
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # Capture page HTML periodically
            if iteration % 3 == 0:  # Every 3 iterations
                try:
                    page_html = executor.page.content()
                    html_pages.append(page_html)
                except Exception as e:
                    print(f"[Explorer] Failed to capture HTML: {e}")

        # Final data extraction attempt
        # For now, return empty data - in production would use read_page + extraction
        print(f"[Explorer] Completed exploration with {len(ir_actions)} IR actions")

        return ExplorationResult(
            steps=ir_actions,
            screenshots=screenshots,
            html_pages=html_pages,
            urls=urls if urls else [start_url],
            data=data,
        )

    finally:
        executor.stop()
