"""Native Playwright-based agentic exploration.

Replaces browser-use dependency with a lightweight Anthropic + Playwright implementation
that provides similar exploration capabilities without external dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright

from ..core.ir.model import Click, Fill, Navigate, Validate
from ..core.nav.explore import ExplorationResult
from .anthropic import complete_json, has_api_key


def _get_page_state(page: Page) -> dict[str, Any]:
    """Extract relevant page state for LLM decision-making."""
    try:
        # Get basic page info
        title = page.title()
        url = page.url

        # Get interactive elements (simplified DOM)
        elements = page.evaluate("""() => {
            const getSelector = (el) => {
                if (el.id) return '#' + el.id;
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
                    if (classes) return el.tagName.toLowerCase() + '.' + classes;
                }
                return el.tagName.toLowerCase();
            };

            const elements = [];
            // Get clickable elements
            document.querySelectorAll('a, button, [role="button"], [onclick]').forEach((el, idx) => {
                if (idx < 50 && el.offsetParent !== null) {  // Visible elements only, limit to 50
                    elements.push({
                        type: 'clickable',
                        selector: getSelector(el),
                        text: el.textContent?.trim().substring(0, 100) || '',
                        tag: el.tagName.toLowerCase()
                    });
                }
            });

            // Get input fields
            document.querySelectorAll('input, textarea, select').forEach((el, idx) => {
                if (idx < 20 && el.offsetParent !== null) {  // Limit to 20
                    elements.push({
                        type: 'input',
                        selector: getSelector(el),
                        placeholder: el.placeholder || '',
                        inputType: el.type || 'text'
                    });
                }
            });

            return elements;
        }""")

        # Get visible text content (first 3000 chars)
        text_content = page.evaluate("() => document.body.innerText")
        if isinstance(text_content, str):
            text_content = text_content[:3000]

        return {"title": title, "url": url, "elements": elements, "text": text_content}
    except Exception as e:
        return {
            "title": "",
            "url": page.url,
            "elements": [],
            "text": "",
            "error": str(e),
        }


def _decide_next_action(
    page_state: dict[str, Any],
    nl_request: str,
    schema: dict[str, Any],
    visited_urls: list[str],
    step_num: int,
    max_steps: int,
) -> dict[str, Any] | None:
    """Use LLM to decide next action based on page state."""
    if not has_api_key():
        return None

    schema_str = json.dumps(schema, indent=2)
    elements_str = json.dumps(
        page_state.get("elements", [])[:30], indent=2
    )  # Limit for token efficiency

    sys_prompt = """You are a web exploration agent. Based on the current page state, decide the next action.

Available actions:
- navigate: {"action": "navigate", "url": "https://..."}
- click: {"action": "click", "selector": "button.submit"}
- fill: {"action": "fill", "selector": "input#search", "text": "search term"}
- extract: {"action": "extract"} - when you've found the data
- done: {"action": "done"} - when task is complete or stuck

Return ONLY a JSON object with the action. Be efficient and goal-directed."""

    user_prompt = f"""Step {step_num}/{max_steps}

Task: {nl_request}

Target schema: {schema_str}

Current page:
- URL: {page_state.get("url", "")}
- Title: {page_state.get("title", "")}

Interactive elements:
{elements_str}

Page text (excerpt):
{page_state.get("text", "")[:1000]}

Already visited: {len(visited_urls)} URLs

Decide next action (JSON only):"""

    try:
        data, _ = complete_json(sys_prompt, user_prompt, max_tokens=300)
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"[Explorer] LLM decision failed: {e}")
        return None


def _extract_data_from_page(
    page: Page,
    nl_request: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured data from current page using LLM."""
    if not has_api_key():
        return {}

    # Get page content
    try:
        text = page.evaluate("() => document.body.innerText")

        # Use LLM to extract structured data
        from ..core.extractor.llm_extract import extract_from_text

        data = extract_from_text(
            nl_request, None, schema, text if isinstance(text, str) else str(text)
        )
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[Explorer] Extraction failed: {e}")
        return {}


def explore_with_playwright(
    start_url: str,
    nl_request: str,
    schema: dict[str, Any],
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    max_steps: int = 20,
    headless: bool = True,
) -> ExplorationResult:
    """Native Playwright-based agentic exploration using Anthropic for decisions.

    This replaces browser-use with a lightweight implementation that:
    - Uses Playwright for browser automation
    - Uses Anthropic Claude for exploration decisions
    - Captures actions, screenshots, and HTML
    - Returns ExplorationResult compatible with existing pipeline
    """
    print(f"[Explorer] Starting native exploration for job {job_id}")
    print(f"[Explorer] Target: {start_url}")
    print(f"[Explorer] Task: {nl_request}")

    actions: list[Any] = []
    urls: list[str] = []
    html_pages: list[str] = []
    screenshots: list[Path] = []
    data: dict[str, Any] = {}

    # Get target domain for restriction
    parsed_url = urlparse(start_url)
    target_domain = parsed_url.netloc.removeprefix("www.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = context.new_page()
            page.set_default_timeout(30000)

            # Navigate to start URL
            print(f"[Explorer] Navigating to {start_url}")
            page.goto(start_url, wait_until="domcontentloaded")
            actions.append(Navigate(url=start_url))
            urls.append(start_url)

            # Capture initial state
            screenshot_path = screenshots_dir / f"exploration-step-0-{job_id}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            screenshots.append(screenshot_path)

            html_content = page.content()
            html_pages.append(html_content)

            # Exploration loop
            for step in range(1, max_steps + 1):
                print(f"[Explorer] Step {step}/{max_steps}")

                # Get current page state
                page_state = _get_page_state(page)

                # Decide next action
                action = _decide_next_action(
                    page_state, nl_request, schema, urls, step, max_steps
                )

                if not action or action.get("action") == "done":
                    print(f"[Explorer] Agent decided to stop at step {step}")
                    break

                action_type = action.get("action", "")
                print(f"[Explorer] Action: {action_type}")

                try:
                    if action_type == "navigate":
                        nav_url = action.get("url", "")
                        # Check domain restriction
                        nav_domain = urlparse(nav_url).netloc.removeprefix("www.")
                        if target_domain not in nav_domain:
                            print(
                                f"[Explorer] Skipping navigation to different domain: {nav_url}"
                            )
                            continue

                        page.goto(nav_url, wait_until="domcontentloaded")
                        actions.append(Navigate(url=nav_url))
                        urls.append(nav_url)

                    elif action_type == "click":
                        selector = action.get("selector", "")
                        if selector:
                            page.click(selector, timeout=5000)
                            actions.append(Click(selector=selector))
                            page.wait_for_load_state("domcontentloaded")

                    elif action_type == "fill":
                        selector = action.get("selector", "")
                        text = action.get("text", "")
                        if selector and text:
                            page.fill(selector, text)
                            actions.append(Fill(selector=selector, text=text))

                    elif action_type == "extract":
                        print(f"[Explorer] Extracting data at step {step}")
                        data = _extract_data_from_page(page, nl_request, schema)
                        print(f"[Explorer] Extracted: {data}")
                        break

                    # Capture state after action
                    page.wait_for_timeout(1000)  # Brief wait for content

                    screenshot_path = (
                        screenshots_dir / f"exploration-step-{step}-{job_id}.png"
                    )
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    screenshots.append(screenshot_path)

                    html_content = page.content()
                    html_pages.append(html_content)

                    # Check if URL changed
                    current_url = page.url
                    if current_url not in urls:
                        urls.append(current_url)

                except Exception as e:
                    print(f"[Explorer] Action failed: {e}")
                    # Continue exploration despite failures
                    continue

            # Final extraction if not done yet
            if not data:
                print("[Explorer] Performing final extraction")
                data = _extract_data_from_page(page, nl_request, schema)

            # Add final validation
            actions.append(
                Validate(
                    selector="body",
                    validation_type="presence",
                    description="Final page load validation",
                    is_critical=False,
                )
            )

        finally:
            browser.close()

    print(
        f"[Explorer] Exploration complete. Actions: {len(actions)}, URLs: {len(urls)}, Data: {bool(data)}"
    )

    return ExplorationResult(
        steps=actions,
        html_pages=html_pages,
        screenshots=screenshots,
        urls=urls,
        data=data,
    )
