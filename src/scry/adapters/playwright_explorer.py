"""Native Playwright-based agentic exploration.

Supports two modes:
1. Browser Tools API (BROWSER_TOOLS_ENABLED=true) - uses Anthropic's native browser automation
2. Async Playwright + complete_json (default) - uses regular Claude API for decisions

Cookie banner handling uses LLM-based detection (no string matching).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright

from ..core.cookie.detector import BannerHints, CookieBannerResult, detect_cookie_banner
from ..core.ir.model import (
    Click,
    Fill,
    Hover,
    KeyPress,
    Navigate,
    Select,
)
from ..core.nav.explore import ExplorationResult
from .anthropic import (
    call_with_browser_tool,
    complete_json,
    has_api_key,
    has_browser_tools,
)

if TYPE_CHECKING:
    from playwright.async_api import Browser

# Confidence threshold for cookie banner dismissal
COOKIE_CONFIDENCE_THRESHOLD = 0.7


async def _gather_banner_hints(page: Page) -> BannerHints:
    """Gather heuristic hints for cookie banner detection."""
    hints = BannerHints()

    try:
        api_check = await page.evaluate("""() => {
            return {
                has_tcf_api: typeof window.__tcfapi === 'function',
                has_cmp_api: typeof window.__cmp === 'function'
            };
        }""")
        hints.has_tcf_api = api_check.get("has_tcf_api", False)
        hints.has_cmp_api = api_check.get("has_cmp_api", False)

        if hints.has_tcf_api:
            print("[Explorer] IAB TCF API detected")
        if hints.has_cmp_api:
            print("[Explorer] CMP API detected")

    except Exception as e:
        print(f"[Explorer] Failed to check consent APIs: {e}")

    try:
        fixed_elements = await page.evaluate("""() => {
            const results = [];
            const elements = document.querySelectorAll('*');
            for (const el of elements) {
                const style = window.getComputedStyle(el);
                const position = style.position;
                const zIndex = parseInt(style.zIndex, 10) || 0;

                if ((position === 'fixed' || position === 'sticky') && zIndex > 100) {
                    const role = el.getAttribute('role') || el.tagName.toLowerCase();
                    const ref = el.getAttribute('data-ref') || '';

                    results.push({
                        ref: ref,
                        role: role,
                        z_index: String(zIndex),
                        position: position
                    });
                }
            }
            return results.sort((a, b) => parseInt(b.z_index) - parseInt(a.z_index)).slice(0, 10);
        }""")
        hints.fixed_elements = fixed_elements or []

        if hints.fixed_elements:
            print(f"[Explorer] Found {len(hints.fixed_elements)} fixed/sticky elements")

    except Exception as e:
        print(f"[Explorer] Failed to analyze fixed elements: {e}")

    return hints


async def _generate_dom_tree(page: Page) -> tuple[str, dict[str, str]]:
    """Generate DOM tree with element references for LLM analysis.

    Returns:
        Tuple of (dom_tree_string, ref_to_selector_map)
    """
    try:
        result = await page.evaluate("""() => {
            const refMap = {};
            let refCounter = 0;

            function getSelector(el) {
                if (el.id) return '#' + el.id;
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
                    if (classes) return el.tagName.toLowerCase() + '.' + classes;
                }
                return el.tagName.toLowerCase();
            }

            function getTree(el, depth = 0) {
                if (depth > 5) return '';

                const tag = el.tagName?.toLowerCase() || '';
                if (!tag || ['script', 'style', 'noscript', 'svg', 'path'].includes(tag)) return '';

                const ref = 'ref_' + (refCounter++);
                const selector = getSelector(el);
                refMap[ref] = selector;
                el.setAttribute('data-ref', ref);

                const role = el.getAttribute('role') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                const text = el.textContent?.trim().slice(0, 50) || '';
                const id = el.id || '';
                const className = (el.className && typeof el.className === 'string') ?
                    el.className.split(' ').slice(0, 2).join(' ') : '';

                let line = '  '.repeat(depth) + '- ' + tag;
                if (role) line += ' role="' + role + '"';
                if (id) line += ' id="' + id + '"';
                if (className) line += ' class="' + className + '"';
                if (ariaLabel) line += ' aria-label="' + ariaLabel + '"';
                if (text && text.length < 40 && !el.children.length) line += ' "' + text + '"';
                line += ' [ref=' + ref + ']';

                let result = line + '\\n';

                const children = Array.from(el.children || []).slice(0, 20);
                for (const child of children) {
                    result += getTree(child, depth + 1);
                }

                return result;
            }

            const tree = getTree(document.body);
            return { tree, refMap };
        }""")
        return result.get("tree", ""), result.get("refMap", {})
    except Exception as e:
        print(f"[Explorer] Failed to generate DOM tree: {e}")
        return "", {}


async def _handle_cookie_banner(page: Page) -> CookieBannerResult | None:
    """Detect and dismiss cookie banner using LLM analysis."""
    try:
        print("[Explorer] Checking for cookie banner...")

        # Generate DOM tree
        dom_tree, ref_map = await _generate_dom_tree(page)

        if not dom_tree:
            print("[Explorer] No DOM tree available")
            return None

        # Gather hints
        hints = await _gather_banner_hints(page)

        # Create a simple ref manager interface
        class RefData:
            """Simple container for element reference data."""

            def __init__(self, selector: str):
                self.selector = selector

        class SimpleRefManager:
            def __init__(self, ref_map: dict[str, str]):
                self._map = ref_map

            def get_ref(self, ref_id: str) -> RefData | None:
                selector = self._map.get(ref_id)
                if selector:
                    return RefData(selector)
                return None

        ref_manager = SimpleRefManager(ref_map)

        # Detect cookie banner
        result = detect_cookie_banner(dom_tree, ref_manager, hints)

        if not result.has_banner:
            print("[Explorer] No cookie banner detected")
            return result

        if result.confidence < COOKIE_CONFIDENCE_THRESHOLD:
            print(
                f"[Explorer] Banner detected but confidence too low: {result.confidence}"
            )
            return result

        print(
            f"[Explorer] Cookie banner detected: type={result.banner_type}, confidence={result.confidence}"
        )

        # Try to dismiss
        if result.dismiss_ref:
            selector = ref_map.get(result.dismiss_ref)
            if selector:
                try:
                    print(
                        f"[Explorer] Dismissing banner via {result.dismiss_ref} -> {selector}"
                    )
                    await page.locator(f'[data-ref="{result.dismiss_ref}"]').click(
                        timeout=3000
                    )
                    print("[Explorer] Cookie banner dismissed")
                    await page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"[Explorer] Failed to dismiss banner: {e}")

        return result

    except Exception as e:
        print(f"[Explorer] Cookie handling error: {e}")
        return None


async def _get_page_state(page: Page) -> dict[str, Any]:
    """Extract relevant page state for LLM decision-making."""
    try:
        title = await page.title()
        url = page.url

        elements = await page.evaluate("""() => {
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
                if (idx < 50 && el.offsetParent !== null) {
                    elements.push({
                        type: 'clickable',
                        selector: getSelector(el),
                        text: el.textContent?.trim().substring(0, 100) || el.value || '',
                        tag: el.tagName.toLowerCase()
                    });
                }
            });

            // Get input fields
            document.querySelectorAll('input:not([type="button"]):not([type="submit"]):not([type="file"]), textarea').forEach((el, idx) => {
                if (idx < 20 && el.offsetParent !== null) {
                    elements.push({
                        type: 'input',
                        selector: getSelector(el),
                        placeholder: el.placeholder || '',
                        inputType: el.type || 'text',
                        name: el.name || '',
                        id: el.id || '',
                        autocomplete: el.autocomplete || ''
                    });
                }
            });

            // Get select elements
            document.querySelectorAll('select').forEach((el, idx) => {
                if (idx < 10 && el.offsetParent !== null) {
                    const options = Array.from(el.options).slice(0, 5).map(opt => ({
                        value: opt.value,
                        text: opt.text
                    }));
                    elements.push({
                        type: 'select',
                        selector: getSelector(el),
                        options: options
                    });
                }
            });

            return elements;
        }""")

        text = await page.evaluate(
            "() => document.body.innerText?.substring(0, 2000) || ''"
        )

        return {
            "title": title,
            "url": url,
            "elements": elements,
            "text": text,
        }
    except Exception as e:
        print(f"[Explorer] Failed to get page state: {e}")
        return {"title": "", "url": page.url, "elements": [], "text": ""}


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
    elements_str = json.dumps(page_state.get("elements", [])[:30], indent=2)

    sys_prompt = """You are a web exploration agent. Based on the current page state, decide the next action.

Available actions:
- navigate: {"action": "navigate", "url": "https://..."}
- click: {"action": "click", "selector": "button.submit"}
- fill: {"action": "fill", "selector": "input#search", "text": "search term"}
- select: {"action": "select", "selector": "select#country", "value": "USA"}
- hover: {"action": "hover", "selector": ".menu-item"}
- keypress: {"action": "keypress", "key": "Enter", "selector": "input#search"}
- extract: {"action": "extract"} - when you've found the data
- done: {"action": "done"} - when task is complete or stuck

IMPORTANT:
1. Cookie banners are handled automatically - don't worry about them.
2. For login forms, if credentials are available, fill and submit them.
3. Be efficient and goal-directed.
4. Return ONLY a JSON object with the action."""

    credentials_notice = ""
    if login_params and login_params.get("username") and login_params.get("password"):
        credentials_notice = "\n\nCredentials available for login if needed."

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
        data, raw = complete_json(sys_prompt, user_prompt, max_tokens=300)
        print(f"[Explorer] LLM action: {data}")
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"[Explorer] LLM decision failed: {e}")
        return None


async def _explore_with_complete_json(
    start_url: str,
    nl_request: str,
    schema: dict[str, Any],
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    max_steps: int,
    headless: bool,
    login_params: dict[str, Any] | None,
) -> ExplorationResult:
    """Async exploration using complete_json API for LLM decisions."""

    start_time = time.perf_counter()
    print(f"[Explorer] Starting async exploration for job {job_id}")
    print(f"[Explorer] Target: {start_url}")

    actions: list[Any] = []
    urls: list[str] = []
    html_pages: list[str] = []
    screenshots: list[Path] = []
    data: dict[str, Any] = {}

    parsed_url = urlparse(start_url)
    target_domain = parsed_url.netloc.removeprefix("www.")

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = await context.new_page()
            page.set_default_timeout(30000)

            print(
                f"[Explorer] Browser ready in {time.perf_counter() - start_time:.2f}s"
            )

            # Navigate to start URL
            print(f"[Explorer] Navigating to {start_url}")
            await page.goto(start_url, wait_until="domcontentloaded")
            actions.append(Navigate(url=start_url))
            urls.append(start_url)

            # Wait for dynamic content
            await page.wait_for_timeout(2000)

            # Handle cookie banner with LLM detection
            cookie_result = await _handle_cookie_banner(page)
            if cookie_result and cookie_result.dismiss_selector:
                data["_cookie_dismiss_selector"] = cookie_result.dismiss_selector

            # Capture initial state
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            html_dir.mkdir(parents=True, exist_ok=True)

            screenshot_path = screenshots_dir / f"exploration-step-0-{job_id}.png"
            screenshot_bytes = await page.screenshot(full_page=True)
            screenshot_path.write_bytes(screenshot_bytes)
            screenshots.append(screenshot_path)

            # Exploration loop
            for step in range(1, max_steps + 1):
                print(f"[Explorer] Step {step}/{max_steps}")

                page_state = await _get_page_state(page)

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
                        if selector:
                            await page.click(selector, timeout=5000)
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

                    elif action_type == "hover":
                        selector = action.get("selector", "")
                        if selector:
                            await page.hover(selector, timeout=5000)
                            actions.append(Hover(selector=selector))
                            await page.wait_for_timeout(500)

                    elif action_type == "keypress":
                        key = action.get("key", "")
                        selector = action.get("selector")
                        if key:
                            if selector:
                                await page.locator(selector).press(key)
                            else:
                                await page.keyboard.press(key)
                            actions.append(KeyPress(key=key, selector=selector))

                    elif action_type == "extract":
                        print(f"[Explorer] Extracting data at step {step}")
                        break

                    # Capture state after action
                    await page.wait_for_timeout(1000)

                    screenshot_path = (
                        screenshots_dir / f"exploration-step-{step}-{job_id}.png"
                    )
                    screenshot_bytes = await page.screenshot(full_page=True)
                    screenshot_path.write_bytes(screenshot_bytes)
                    screenshots.append(screenshot_path)

                    current_url = page.url
                    if current_url not in urls:
                        urls.append(current_url)

                    html_content = await page.content()
                    html_pages.append(html_content)

                except Exception as e:
                    print(f"[Explorer] Action failed: {e}")
                    continue

            # Capture final HTML
            if not html_pages:
                html_pages.append(await page.content())

            print(f"[Explorer] Exploration complete: {len(actions)} actions")

        finally:
            await browser.close()

    return ExplorationResult(
        steps=actions,
        screenshots=screenshots,
        html_pages=html_pages,
        urls=urls,
        data=data,
    )


# ============================================================================
# Browser Tools exploration (when BROWSER_TOOLS_ENABLED=true)
# Uses custom tool schema with standard messages API (browser-use-demo approach)
# ============================================================================

BROWSER_TOOLS_SYSTEM_PROMPT = """You are a web automation agent using browser tools to explore websites and extract data.

Your capabilities:
- navigate: Go to URLs
- read_page: Get DOM structure with element references (ref_X)
- screenshot: Capture current viewport
- left_click: Click elements by ref or coordinate
- type: Type text into focused element
- form_input: Set form field values by ref
- scroll: Scroll in direction (up/down/left/right)
- key: Press keyboard keys (enter, tab, etc.)
- wait: Wait for specified duration
- execute_js: Run JavaScript in page context

IMPORTANT WORKFLOW:
1. After navigating, ALWAYS call read_page first to get element references
2. Use element references (ref_X) for reliable interaction
3. If a cookie consent banner/overlay blocks interaction, dismiss it
4. Be efficient - minimize unnecessary actions
5. When you've completed the task or are stuck, explain your reasoning

Element references are stable identifiers from read_page output."""


async def _execute_browser_action(
    page: Page,
    action_input: dict[str, Any],
    ref_map: dict[str, str],
) -> dict[str, Any]:
    """Execute a browser tool action and return the result.

    Args:
        page: Playwright page object
        action_input: The tool input containing action and parameters
        ref_map: Map of ref_X identifiers to CSS selectors

    Returns:
        Tool result dict with output and optionally base64_image
    """
    import base64

    action = action_input.get("action", "")
    text = action_input.get("text")
    ref = action_input.get("ref")
    coordinate = action_input.get("coordinate")
    scroll_direction = action_input.get("scroll_direction")
    scroll_amount = action_input.get("scroll_amount", 3)
    duration = action_input.get("duration", 1.0)
    value = action_input.get("value")

    try:
        if action == "navigate":
            if not text:
                return {"output": "Error: URL required for navigate"}
            url = (
                text if text.startswith(("http://", "https://")) else f"https://{text}"
            )
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            screenshot_bytes = await page.screenshot()
            return {
                "output": f"Navigated to {url}",
                "base64_image": base64.b64encode(screenshot_bytes).decode(),
            }

        elif action == "screenshot":
            screenshot_bytes = await page.screenshot()
            return {
                "output": "Screenshot captured",
                "base64_image": base64.b64encode(screenshot_bytes).decode(),
            }

        elif action == "read_page":
            # Generate DOM tree with refs
            dom_tree, new_ref_map = await _generate_dom_tree(page)
            ref_map.clear()
            ref_map.update(new_ref_map)
            return {"output": dom_tree if dom_tree else "Failed to read page"}

        elif action == "get_page_text":
            text_content = await page.evaluate("() => document.body.innerText || ''")
            title = await page.title()
            return {"output": f"Title: {title}\n\n{text_content[:5000]}"}

        elif action == "left_click":
            if ref and ref in ref_map:
                await page.locator(f'[data-ref="{ref}"]').click(timeout=5000)
                return {"output": f"Clicked element {ref}"}
            elif coordinate and len(coordinate) == 2:
                await page.mouse.click(coordinate[0], coordinate[1])
                return {"output": f"Clicked at ({coordinate[0]}, {coordinate[1]})"}
            else:
                return {"output": "Error: ref or coordinate required for click"}

        elif action == "double_click":
            if ref and ref in ref_map:
                await page.locator(f'[data-ref="{ref}"]').dblclick(timeout=5000)
                return {"output": f"Double-clicked element {ref}"}
            elif coordinate and len(coordinate) == 2:
                await page.mouse.dblclick(coordinate[0], coordinate[1])
                return {
                    "output": f"Double-clicked at ({coordinate[0]}, {coordinate[1]})"
                }
            else:
                return {"output": "Error: ref or coordinate required for double_click"}

        elif action == "hover":
            if ref and ref in ref_map:
                await page.locator(f'[data-ref="{ref}"]').hover(timeout=5000)
                await page.wait_for_timeout(500)
                screenshot_bytes = await page.screenshot()
                return {
                    "output": f"Hovered over element {ref}",
                    "base64_image": base64.b64encode(screenshot_bytes).decode(),
                }
            elif coordinate and len(coordinate) == 2:
                await page.mouse.move(coordinate[0], coordinate[1])
                await page.wait_for_timeout(500)
                screenshot_bytes = await page.screenshot()
                return {
                    "output": f"Hovered at ({coordinate[0]}, {coordinate[1]})",
                    "base64_image": base64.b64encode(screenshot_bytes).decode(),
                }
            else:
                return {"output": "Error: ref or coordinate required for hover"}

        elif action == "type":
            if not text:
                return {"output": "Error: text required for type action"}
            await page.keyboard.type(text)
            return {"output": f"Typed: {text}"}

        elif action == "key":
            if not text:
                return {"output": "Error: key required for key action"}
            await page.keyboard.press(text)
            return {"output": f"Pressed key: {text}"}

        elif action == "scroll":
            if not scroll_direction:
                scroll_direction = "down"
            delta_y = (
                scroll_amount * 100
                if scroll_direction == "down"
                else -scroll_amount * 100
                if scroll_direction == "up"
                else 0
            )
            delta_x = (
                scroll_amount * 100
                if scroll_direction == "right"
                else -scroll_amount * 100
                if scroll_direction == "left"
                else 0
            )
            await page.evaluate(f"window.scrollBy({delta_x}, {delta_y})")
            await page.wait_for_timeout(500)
            screenshot_bytes = await page.screenshot()
            return {
                "output": f"Scrolled {scroll_direction} by {scroll_amount}",
                "base64_image": base64.b64encode(screenshot_bytes).decode(),
            }

        elif action == "scroll_to":
            if not ref:
                return {"output": "Error: ref required for scroll_to"}
            await page.locator(f'[data-ref="{ref}"]').scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            screenshot_bytes = await page.screenshot()
            return {
                "output": f"Scrolled to element {ref}",
                "base64_image": base64.b64encode(screenshot_bytes).decode(),
            }

        elif action == "wait":
            await page.wait_for_timeout(int(duration * 1000))
            return {"output": f"Waited {duration} seconds"}

        elif action == "form_input":
            if not ref or value is None:
                return {"output": "Error: ref and value required for form_input"}
            await page.locator(f'[data-ref="{ref}"]').fill(str(value))
            return {"output": f"Filled {ref} with: {value}"}

        elif action == "execute_js":
            if not text:
                return {"output": "Error: JavaScript code required"}
            result = await page.evaluate(text)
            return {"output": str(result) if result is not None else "undefined"}

        else:
            return {"output": f"Unknown action: {action}"}

    except Exception as e:
        return {"output": f"Error executing {action}: {e}"}


async def _explore_with_browser_tools(
    start_url: str,
    nl_request: str,
    schema: dict[str, Any],
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    max_steps: int,
    headless: bool,
    login_params: dict[str, Any] | None,
) -> ExplorationResult:
    """Exploration using browser tools with standard messages API.

    Uses the claude-quickstarts/browser-use-demo approach:
    - Custom tool schema passed to client.messages.create()
    - Manual tool execution with async Playwright
    - No special beta API required
    """

    print(f"[Explorer] Starting browser tools exploration for job {job_id}")

    ir_actions: list[Any] = []
    urls: list[str] = []
    html_pages: list[str] = []
    screenshots: list[Path] = []
    data: dict[str, Any] = {}
    ref_map: dict[str, str] = {}  # Track element references

    screenshots_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = await context.new_page()
            page.set_default_timeout(30000)

            # Create task description
            task_description = f"""Task: {nl_request}

Target schema for data extraction:
{json.dumps(schema, indent=2)}

Starting URL: {start_url}

Instructions:
1. Navigate to the starting URL
2. Call read_page to understand the page structure
3. Explore the site to accomplish the task
4. If a cookie banner appears, dismiss it by finding and clicking the accept/dismiss button
5. Extract data matching the schema when found

When you're done or stuck, explain what you accomplished."""

            messages: list[dict[str, Any]] = [
                {"role": "user", "content": task_description}
            ]

            for iteration in range(max_steps):
                print(f"[Explorer] Iteration {iteration + 1}/{max_steps}")

                try:
                    response = call_with_browser_tool(
                        messages=messages,
                        max_tokens=4096,
                        system_prompt=BROWSER_TOOLS_SYSTEM_PROMPT,
                    )
                except Exception as e:
                    print(f"[Explorer] API error: {e}")
                    break

                # Process response
                assistant_content: list[dict[str, Any]] = []
                has_tool_use = False

                for block in response.content:
                    if hasattr(block, "type"):
                        if block.type == "text":
                            assistant_content.append(
                                {"type": "text", "text": block.text}
                            )
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

                messages.append({"role": "assistant", "content": assistant_content})

                if not has_tool_use or response.stop_reason != "tool_use":
                    print("[Explorer] Agent finished")
                    break

                # Execute tool actions
                tool_results: list[dict[str, Any]] = []

                for block in response.content:
                    if not hasattr(block, "type") or block.type != "tool_use":
                        continue

                    if block.name != "browser":
                        continue

                    action_input = block.input
                    action_name = action_input.get("action", "")
                    print(f"[Explorer] Executing: {action_name}")

                    result = await _execute_browser_action(page, action_input, ref_map)

                    # Build tool result
                    content: list[dict[str, Any]] = []
                    if result.get("output"):
                        content.append({"type": "text", "text": result["output"]})
                    if result.get("base64_image"):
                        content.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": result["base64_image"],
                                },
                            }
                        )

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                        }
                    )

                    # Track IR actions
                    if action_name == "navigate":
                        nav_url = action_input.get("text", "")
                        if nav_url:
                            if not nav_url.startswith(("http://", "https://")):
                                nav_url = f"https://{nav_url}"
                            urls.append(nav_url)
                            ir_actions.append(Navigate(url=nav_url))
                    elif action_name == "left_click":
                        ref = action_input.get("ref")
                        if ref and ref in ref_map:
                            ir_actions.append(Click(selector=f'[data-ref="{ref}"]'))
                    elif action_name == "form_input":
                        ref = action_input.get("ref")
                        value = action_input.get("value", "")
                        if ref and ref in ref_map:
                            ir_actions.append(
                                Fill(selector=f'[data-ref="{ref}"]', text=str(value))
                            )

                    # Save screenshot if taken
                    if result.get("base64_image"):
                        screenshot_path = (
                            screenshots_dir
                            / f"exploration-step-{iteration}-{job_id}.png"
                        )
                        import base64 as b64

                        screenshot_path.write_bytes(
                            b64.b64decode(result["base64_image"])
                        )
                        screenshots.append(screenshot_path)

                if tool_results:
                    messages.append({"role": "user", "content": tool_results})

            # Capture final HTML
            try:
                html_pages.append(await page.content())
            except Exception:
                pass

            print(f"[Explorer] Completed with {len(ir_actions)} IR actions")

        finally:
            await browser.close()

    return ExplorationResult(
        steps=ir_actions,
        screenshots=screenshots,
        html_pages=html_pages,
        urls=urls if urls else [start_url],
        data=data,
    )


# ============================================================================
# Main entry point
# ============================================================================


async def explore_with_playwright(
    start_url: str,
    nl_request: str,
    schema: dict[str, Any],
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    max_steps: int = 20,
    headless: bool = True,
    login_params: dict[str, Any] | None = None,
    progress_callback: Any | None = None,
) -> ExplorationResult:
    """Explore website using LLM-guided browser automation.

    Uses Browser Tools API if BROWSER_TOOLS_ENABLED=true, otherwise falls back
    to async Playwright with complete_json API for decisions.

    Cookie banners are handled via LLM-based detection (no string matching).
    """
    print(f"[Explorer] Starting exploration for job {job_id}")
    print(f"[Explorer] Target: {start_url}")
    print(f"[Explorer] Task: {nl_request}")

    if not has_api_key():
        print("[Explorer] No API key found, returning basic navigation only")
        return ExplorationResult(
            steps=[Navigate(url=start_url)],
            screenshots=[],
            html_pages=[],
            urls=[start_url],
            data={},
        )

    if has_browser_tools():
        print("[Explorer] Using Browser Tools API")
        return await _explore_with_browser_tools(
            start_url=start_url,
            nl_request=nl_request,
            schema=schema,
            screenshots_dir=screenshots_dir,
            html_dir=html_dir,
            job_id=job_id,
            max_steps=max_steps,
            headless=headless,
            login_params=login_params,
        )
    else:
        print("[Explorer] Using async Playwright with complete_json API")
        return await _explore_with_complete_json(
            start_url=start_url,
            nl_request=nl_request,
            schema=schema,
            screenshots_dir=screenshots_dir,
            html_dir=html_dir,
            job_id=job_id,
            max_steps=max_steps,
            headless=headless,
            login_params=login_params,
        )
