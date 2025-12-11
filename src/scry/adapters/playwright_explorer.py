"""Native async Playwright-based agentic exploration.

Replaces browser-use dependency with a lightweight Anthropic + Playwright implementation
that provides similar exploration capabilities without external dependencies.

Uses async Playwright API which:
- Has no thread affinity issues (unlike sync API)
- Works naturally with FastAPI/MCP async contexts
- Enables browser pooling without thread complications
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from PIL import Image
from playwright.async_api import Page, async_playwright

from ..core.extractor.llm_extract import extract_from_text
from ..core.ir.model import (
    Click,
    Fill,
    Hover,
    KeyPress,
    Navigate,
    Select,
    Upload,
    Validate,
)
from ..core.nav.explore import ExplorationResult
from .anthropic import complete_json, has_api_key
from .browser_pool import get_browser_pool

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from playwright.async_api import Browser, Playwright

# Type alias for progress callback - can be sync or async callable
ProgressCallback = Any


def _compress_screenshot(png_bytes: bytes, max_width: int = 256) -> str:
    """Compress a PNG screenshot to reduce size for streaming.

    Args:
        png_bytes: Raw PNG image bytes
        max_width: Maximum width to resize to (default 256px for efficient streaming)

    Returns:
        Base64-encoded compressed PNG string
    """
    try:
        img = Image.open(io.BytesIO(png_bytes))

        # Calculate new dimensions maintaining aspect ratio
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

        # Save to bytes
        output = io.BytesIO()
        img.save(output, format="PNG", optimize=True)
        output.seek(0)

        return base64.b64encode(output.read()).decode("utf-8")
    except Exception:
        # Fallback: return original as base64
        return base64.b64encode(png_bytes).decode("utf-8")


async def _get_page_state(page: Page) -> dict[str, Any]:
    """Extract relevant page state for LLM decision-making.

    Scans both the main page and all iframes to find interactive elements,
    which is crucial for handling cookie consent dialogs that often live in iframes.
    """
    try:
        # Get basic page info
        title = await page.title()
        url = page.url

        # Extract elements from a frame
        async def extract_frame_elements(frame, _frame_idx=0):
            """Extract interactive elements from a frame."""
            try:
                return await frame.evaluate("""() => {
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
                    document.querySelectorAll('a, button, [role="button"], [onclick], input[type="button"], input[type="submit"]').forEach((el, idx) => {
                        if (idx < 50 && el.offsetParent !== null) {  // Visible elements only, limit to 50
                            elements.push({
                                type: 'clickable',
                                selector: getSelector(el),
                                text: el.textContent?.trim().substring(0, 100) || el.value || '',
                                tag: el.tagName.toLowerCase()
                            });
                        }
                    });

                    // Get input fields with metadata for LLM to recognize login fields
                    document.querySelectorAll('input:not([type="button"]):not([type="submit"]):not([type="file"]), textarea').forEach((el, idx) => {
                        if (idx < 20 && el.offsetParent !== null) {  // Limit to 20
                            elements.push({
                                type: 'input',
                                selector: getSelector(el),
                                placeholder: el.placeholder || '',
                                inputType: el.type || 'text',
                                name: el.name || '',
                                id: el.id || '',
                                autocomplete: el.autocomplete || '',
                                ariaLabel: el.getAttribute('aria-label') || ''
                            });
                        }
                    });

                    // Get select elements with their options
                    document.querySelectorAll('select').forEach((el, idx) => {
                        if (idx < 10 && el.offsetParent !== null) {
                            const options = Array.from(el.options).slice(0, 5).map(opt => ({
                                value: opt.value,
                                text: opt.text
                            }));
                            elements.push({
                                type: 'select',
                                selector: getSelector(el),
                                name: el.name || '',
                                id: el.id || '',
                                options: options
                            });
                        }
                    });

                    // Get file upload inputs
                    document.querySelectorAll('input[type="file"]').forEach((el, idx) => {
                        if (idx < 5 && el.offsetParent !== null) {
                            elements.push({
                                type: 'file_upload',
                                selector: getSelector(el),
                                accept: el.accept || '',
                                multiple: el.multiple,
                                name: el.name || '',
                                id: el.id || ''
                            });
                        }
                    });

                    return elements;
                }""")
            except Exception:
                return []

        # Collect elements from main frame and all iframes
        all_elements = []

        # Main frame (frame_idx=0)
        main_elements = await extract_frame_elements(page.main_frame, 0)
        for elem in main_elements:
            elem["frame"] = 0
        all_elements.extend(main_elements)

        # Scan all iframes for consent dialogs
        frames = page.frames
        for idx, frame in enumerate(
            frames[1:], start=1
        ):  # Skip main frame (already done)
            try:
                frame_url = frame.url
                # Only scan frames that might contain consent dialogs
                if frame_url and frame_url != "about:blank":
                    iframe_elements = await extract_frame_elements(frame, idx)
                    for elem in iframe_elements:
                        elem["frame"] = idx
                        elem["frame_url"] = frame_url[:80]  # Truncate for display
                    all_elements.extend(iframe_elements)
                    print(
                        f"[Explorer] Scanned iframe {idx}: {frame_url[:80]} - found {len(iframe_elements)} elements"
                    )
            except Exception as e:
                print(f"[Explorer] Failed to scan iframe {idx}: {e}")
                continue

        # Get visible text content (first 3000 chars) from main frame
        text_content = await page.evaluate("() => document.body.innerText")
        if isinstance(text_content, str):
            text_content = text_content[:3000]

        return {
            "title": title,
            "url": url,
            "elements": all_elements,
            "text": text_content,
            "frames_scanned": len(frames),
        }
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
    login_params: dict[str, Any] | None = None,
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
- click: {"action": "click", "selector": "button.submit", "frame": 0}
- fill: {"action": "fill", "selector": "input#search", "text": "search term"}
- select: {"action": "select", "selector": "select#country", "value": "USA"}
- hover: {"action": "hover", "selector": ".menu-item"}
- keypress: {"action": "keypress", "key": "Enter", "selector": "input#search"}
- upload: {"action": "upload", "selector": "input[type='file']", "file_path": "/tmp/file.pdf"}
- extract: {"action": "extract"} - when you've found the data
- done: {"action": "done"} - when task is complete or stuck

IMPORTANT PRIORITY RULES:
1. **Cookie/Consent Banners**: If you see buttons with text like "Accept", "Zustimmen", "Agree", "OK",
   "Alle akzeptieren", "Einverstanden" in ANY frame, click them IMMEDIATELY before doing anything else.
   Cookie banners block content and must be dismissed first.
2. **Login Forms**: If you detect a login/signin form (look for password input fields, username/email fields,
   login/signin buttons) and credentials are available, fill and submit the form BEFORE proceeding with the main task.
   Typical login indicators:
   - Input with inputType="password"
   - Input with name/id/autocomplete containing "user", "email", "login", "username"
   - Buttons with text "Login", "Sign in", "Submit", "Enter"
3. Elements may be in iframes (frame > 0). Include the "frame" number when clicking iframe elements.
4. After handling cookie banners and login, proceed with the actual task.

Return ONLY a JSON object with the action. Be efficient and goal-directed."""

    # Add credentials availability notice to user prompt
    credentials_notice = ""
    if login_params and login_params.get("username") and login_params.get("password"):
        credentials_notice = f"\n\nCREDENTIALS AVAILABLE: username='{login_params.get('username')}', password='***'\nIf you detect a login form, use these credentials to authenticate before proceeding with the main task."

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

Already visited: {len(visited_urls)} URLs{credentials_notice}

Decide next action (JSON only):"""

    try:
        data, _ = complete_json(sys_prompt, user_prompt, max_tokens=300)
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"[Explorer] LLM decision failed: {e}")
        return None


async def _extract_data_from_page(
    page: Page,
    nl_request: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured data from current page using LLM."""
    if not has_api_key():
        return {}

    # Get page content
    try:
        text = await page.evaluate("() => document.body.innerText")

        # Use LLM to extract structured data
        data = extract_from_text(
            nl_request, None, schema, text if isinstance(text, str) else str(text)
        )
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[Explorer] Extraction failed: {e}")
        return {}


def _use_browser_pool() -> bool:
    """Check if browser pool is enabled via environment variable."""
    return os.getenv("BROWSER_USE_POOL", "true").lower() in {"true", "1", "yes"}


@asynccontextmanager
async def _direct_launch(
    headless: bool,
) -> AsyncGenerator[tuple[Browser, Playwright], None]:
    """Direct browser launch without pool (fallback mode)."""
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=headless)
    try:
        yield browser, p
    finally:
        await browser.close()
        await p.stop()


async def explore_with_playwright(  # noqa: PLR0912, PLR0915
    start_url: str,
    nl_request: str,
    schema: dict[str, Any],
    screenshots_dir: Path,
    html_dir: Path,  # noqa: ARG001
    job_id: str,
    max_steps: int = 20,
    headless: bool = True,
    login_params: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ExplorationResult:
    """Async Playwright-based agentic exploration using Anthropic for decisions.

    This replaces browser-use with a lightweight implementation that:
    - Uses async Playwright for browser automation (no thread affinity issues)
    - Uses Anthropic Claude for exploration decisions
    - Captures actions, screenshots, and HTML
    - Returns ExplorationResult compatible with existing pipeline

    Args:
        progress_callback: Optional callback for real-time progress streaming.
            Called with dict containing: step, action, screenshot_b64, url, status

    Environment:
        BROWSER_USE_POOL: Enable browser pool for faster startup (default: true)
    """

    start_time = time.perf_counter()
    print(f"[Explorer] Starting async exploration for job {job_id}")
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

    # Use browser pool if enabled, otherwise fall back to direct launch
    use_pool = _use_browser_pool()

    if use_pool:
        pool = await get_browser_pool()
        context_manager = pool.acquire()
        print("[Explorer] Using async browser pool")
    else:
        print("[Explorer] Using direct browser launch (pool disabled)")
        context_manager = _direct_launch(headless)

    async with context_manager as (browser, _playwright):
        context = None
        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = await context.new_page()
            page.set_default_timeout(30000)

            browser_ready_time = time.perf_counter()
            print(f"[Explorer] Browser ready in {browser_ready_time - start_time:.2f}s")

            # Navigate to start URL
            print(f"[Explorer] Navigating to {start_url}")
            await page.goto(start_url, wait_until="domcontentloaded")
            actions.append(Navigate(url=start_url))
            urls.append(start_url)

            # Wait for dynamic content and iframes to load
            await page.wait_for_timeout(2000)

            # Capture initial state
            screenshot_path = screenshots_dir / f"exploration-step-0-{job_id}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot_bytes = await page.screenshot(full_page=True)
            screenshot_path.write_bytes(screenshot_bytes)
            screenshots.append(screenshot_path)

            # Emit progress callback for initial state
            if progress_callback:
                try:
                    progress_callback(
                        {
                            "step": 0,
                            "max_steps": max_steps,
                            "action": "navigate",
                            "screenshot_b64": _compress_screenshot(screenshot_bytes),
                            "url": start_url,
                            "status": "exploring",
                        }
                    )
                except Exception as e:
                    print(f"[Explorer] Progress callback failed: {e}")

            html_content = await page.content()
            html_pages.append(html_content)

            # Exploration loop
            for step in range(1, max_steps + 1):
                print(f"[Explorer] Step {step}/{max_steps}")

                # Get current page state
                page_state = await _get_page_state(page)

                # Decide next action (sync LLM call - could be made async later)
                action = _decide_next_action(
                    page_state, nl_request, schema, urls, step, max_steps, login_params
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

                        await page.goto(nav_url, wait_until="domcontentloaded")
                        actions.append(Navigate(url=nav_url))
                        urls.append(nav_url)

                    elif action_type == "click":
                        selector = action.get("selector", "")
                        frame_idx = action.get("frame", 0)
                        if selector:
                            # Click in the appropriate frame
                            if frame_idx == 0:
                                # Main frame
                                await page.click(selector, timeout=5000)
                            else:
                                # Iframe - get the frame by index
                                frames = page.frames
                                if 0 <= frame_idx < len(frames):
                                    await frames[frame_idx].click(
                                        selector, timeout=5000
                                    )
                                    print(f"[Explorer] Clicked in iframe {frame_idx}")
                                else:
                                    print(
                                        f"[Explorer] Invalid frame index: {frame_idx}"
                                    )
                                    continue
                            actions.append(Click(selector=selector))
                            await page.wait_for_load_state(
                                "domcontentloaded", timeout=5000
                            )

                    elif action_type == "fill":
                        selector = action.get("selector", "")
                        text = action.get("text", "")
                        if selector and text:
                            await page.fill(selector, text)
                            actions.append(Fill(selector=selector, text=text))

                    elif action_type == "select":
                        selector = action.get("selector", "")
                        value = action.get("value", "")
                        if selector and value:
                            await page.select_option(selector, value)
                            actions.append(Select(selector=selector, value=value))
                            await page.wait_for_load_state(
                                "domcontentloaded", timeout=5000
                            )

                    elif action_type == "hover":
                        selector = action.get("selector", "")
                        if selector:
                            await page.hover(selector, timeout=5000)
                            actions.append(Hover(selector=selector))
                            await page.wait_for_timeout(500)  # Wait for hover effects

                    elif action_type == "keypress":
                        key = action.get("key", "")
                        selector = action.get("selector")
                        if key:
                            if selector:
                                await page.locator(selector).press(key)
                            else:
                                await page.keyboard.press(key)
                            actions.append(KeyPress(key=key, selector=selector))
                            await page.wait_for_timeout(500)

                    elif action_type == "upload":
                        selector = action.get("selector", "")
                        file_path = action.get("file_path", "")
                        if selector and file_path:
                            await page.set_input_files(selector, file_path)
                            actions.append(
                                Upload(selector=selector, file_path=file_path)
                            )

                    elif action_type == "extract":
                        print(f"[Explorer] Extracting data at step {step}")
                        data = await _extract_data_from_page(page, nl_request, schema)
                        print(f"[Explorer] Extracted: {data}")
                        break

                    # Capture state after action
                    await page.wait_for_timeout(1000)  # Brief wait for content

                    screenshot_path = (
                        screenshots_dir / f"exploration-step-{step}-{job_id}.png"
                    )
                    screenshot_bytes = await page.screenshot(full_page=True)
                    screenshot_path.write_bytes(screenshot_bytes)
                    screenshots.append(screenshot_path)

                    # Check if URL changed
                    current_url = page.url
                    if current_url not in urls:
                        urls.append(current_url)

                    # Emit progress callback for this step
                    if progress_callback:
                        try:
                            progress_callback(
                                {
                                    "step": step,
                                    "max_steps": max_steps,
                                    "action": action_type,
                                    "screenshot_b64": _compress_screenshot(
                                        screenshot_bytes
                                    ),
                                    "url": current_url,
                                    "status": "exploring",
                                }
                            )
                        except Exception as cb_err:
                            print(f"[Explorer] Progress callback failed: {cb_err}")

                    html_content = await page.content()
                    html_pages.append(html_content)

                except Exception as e:
                    print(f"[Explorer] Action failed: {e}")
                    # Continue exploration despite failures
                    continue

            # Final extraction if not done yet
            if not data:
                print("[Explorer] Performing final extraction")
                data = await _extract_data_from_page(page, nl_request, schema)

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
            # Close context only - browser lifecycle managed by pool or context_manager
            if context:
                await context.close()

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
