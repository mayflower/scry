"""Browser-Use adapter (V2+).

Optional integration: if the `browser_use` package is available, provide a thin
session wrapper with a subset of methods used by our navigator.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def is_browser_use_available() -> bool:
    try:
        return True
    except Exception:
        return False


# Require Browser-Use's native Anthropic adapter
# Do not import ChatAnthropic at module import time; many environments/tests
# don't need Browser-Use and this would raise ImportError. We'll import lazily
# inside the function that actually needs it.


class BrowserUseSession:
    def __init__(
        self, headless: bool = True, timeout_ms: int = 30000, login_params: dict | None = None
    ):
        # V2 uses Browser-Use to drive Playwright for executing IR steps
        # Not as an autonomous agent, but as a controlled driver
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=headless)

        # Handle login params if provided
        context_options = {}
        if login_params and isinstance(login_params, dict):
            http_basic = login_params.get("http_basic")
            if http_basic and isinstance(http_basic, dict):
                context_options["http_credentials"] = {
                    "username": http_basic.get("username", ""),
                    "password": http_basic.get("password", ""),
                }

        self._context = self._browser.new_context(**context_options)
        self._page = self._context.new_page()
        self._page.set_default_timeout(timeout_ms)

    def goto(self, url: str) -> None:
        self._page.goto(url)

    def click(self, selector: str) -> None:
        self._page.click(selector)

    def fill(self, selector: str, text: str) -> None:
        self._page.fill(selector, text)

    def wait_for(self, selector: str, state: str = "visible") -> None:
        self._page.wait_for_selector(selector, state=state)

    def screenshot(self, out_path: Path) -> None:
        self._page.screenshot(path=str(out_path))

    def content(self) -> str:
        return self._page.content()

    def close(self) -> None:
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            # Silently ignore close errors as browser may already be closed
            _ = e


def explore_with_browser_use(
    start_url: str,
    nl_request: str,
    schema: dict,
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    max_steps: int = 20,
    headless: bool = True,
):
    """Run agentic exploration using Browser-Use and return an ExplorationResult.

    This requires the `browser_use` package and its agent/navigation APIs. If the
    package is missing, raises a RuntimeError; no fallback is performed.
    """
    if not is_browser_use_available():
        raise RuntimeError(
            "browser_use package not installed; install it to enable agentic exploration."
        )

    # We import lazily to avoid hard dependency when not used.
    import browser_use  # type: ignore

    try:
        from browser_use import ChatAnthropic  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "browser_use Anthropic adapter not available; ensure compatible browser-use version is installed."
        ) from e

    # Make max_steps configurable via environment
    max_steps = int(os.getenv("BROWSER_USE_MAX_STEPS", str(max_steps)))
    # Construct detailed task with navigation hints and schema requirements
    import json
    from urllib.parse import urlparse

    from ..core.ir.model import Click, Fill, Navigate, WaitFor  # type: ignore
    from ..core.nav.explore import ExplorationResult  # type: ignore

    schema_str = json.dumps(schema, indent=2)

    # Extract the target domain to enforce staying on it
    parsed_url = urlparse(start_url)
    target_domain = parsed_url.netloc
    # Remove www. prefix if present to allow both www and non-www versions
    target_domain = target_domain.removeprefix("www.")

    task = f"""You are on {start_url}. Complete this task:

{nl_request}

Required data to extract:
{schema_str}

Instructions:
- Click on navigation links, menus, and buttons to explore the website
- Look for the requested information by navigating through the site
- Navigate through any cookie consent or modal dialogs that appear
- If you see a table or list of items, focus on the FIRST or NEXT relevant entry
- Extract data that matches the schema exactly
- Wait for dynamic content to load before extracting
- If no data is found after exploring, return empty/null values"""

    # Instantiate native Anthropic LLM (required)
    llm = ChatAnthropic(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))  # type: ignore

    # Attach to a pre-launched Chrome via CDP for reliability in Docker
    from browser_use.browser.session import BrowserSession  # type: ignore

    cdp_url = os.getenv("CDP_URL", "http://127.0.0.1:9222")
    session = BrowserSession(
        cdp_url=cdp_url,
        headless=headless,
        chromium_sandbox=False,
    )

    print(f"[Browser-Use] Starting exploration for job {job_id}")
    print(f"[Browser-Use] Task: {task[:200]}...")

    # Configure allowed domains to prevent navigation to other sites
    allowed_domains = [
        f"*.{target_domain}",  # Allow all subdomains of target
        f"https://{target_domain}",  # Allow main domain
        f"http://{target_domain}",  # Allow HTTP version
    ]

    print(f"[Browser-Use] Restricting navigation to domains: {allowed_domains}")

    # Enable vision mode conditionally
    use_vision = os.getenv("BROWSER_USE_VISION", "false").lower() == "true"

    # Configurable wait time for dynamic content
    step_timeout = int(os.getenv("BROWSER_USE_STEP_TIMEOUT", "300"))

    agent = browser_use.Agent(  # type: ignore[attr-defined]
        task=task,
        llm=llm,
        browser=session,  # prefer our session config when available
        # Vision mode is now configurable
        use_vision=use_vision,
        generate_gif=False,
        flash_mode=True,  # Use flash mode for faster execution
        max_failures=8,  # Increase failure tolerance
        llm_timeout=240,
        step_timeout=step_timeout,
        # Avoid embedding LLM object into settings to keep JSON serialization safe
        page_extraction_llm=None,
        directly_open_url=True,  # Start with the target URL
        allowed_domains=allowed_domains,  # Restrict to target domain only
    )

    print(f"[Browser-Use] Running agent with max_steps={max_steps}")
    agent.run_sync(max_steps=max_steps)
    print("[Browser-Use] Agent completed exploration")

    # Parse action history and URLs
    actions: list[Any] = []
    urls: list[str] = []
    html_pages: list[str] = []
    screenshots: list[Path] = []
    data: dict[str, Any] | None = None

    import json

    try:
        if hasattr(agent, "history") and hasattr(agent.history, "urls"):
            u = agent.history.urls() or []
            if isinstance(u, str):
                try:
                    u = json.loads(u)
                except Exception as e:
                    print(f"[Browser-Use] Failed to parse URLs: {e}")
                    u = []
            if isinstance(u, list):
                urls = u
                print(f"[Browser-Use] Visited URLs: {urls}")
    except Exception as e:
        print(f"[Browser-Use] Error getting URLs: {e}")
        urls = []

    # Prefer complete_history for non-truncated action list
    try:
        if hasattr(agent, "history") and hasattr(agent.history, "action_history"):
            ah = agent.history.action_history() or []
            print(f"[Browser-Use] Parsing {len(ah)} actions from history")
            for idx, item in enumerate(ah):
                # action may be dict-like; normalize
                action = getattr(item, "action", None)
                if action is None and isinstance(item, dict):
                    action = item.get("action") or {}
                name = (
                    getattr(action, "name", None)
                    or (action.get("name") if isinstance(action, dict) else None)
                    or (action.get("action") if isinstance(action, dict) else None)
                    or ""
                ).lower()
                args = (
                    getattr(action, "args", None)
                    or (action.get("args") if isinstance(action, dict) else {})
                    or {}
                )
                if name == "navigate" and args.get("url"):
                    actions.append(Navigate(url=str(args["url"])))
                    print(f"[Browser-Use] Action {idx}: Navigate to {args['url']}")
                elif name == "click" and args.get("selector"):
                    actions.append(Click(selector=str(args["selector"])))
                    print(f"[Browser-Use] Action {idx}: Click {args['selector']}")
                elif name == "fill" and args.get("selector"):
                    actions.append(
                        Fill(
                            selector=str(args["selector"]),
                            text=str(args.get("text", "")),
                        )
                    )
                    print(
                        f"[Browser-Use] Action {idx}: Fill {args['selector']} with '{args.get('text', '')}'"
                    )
                elif name in ("wait_for", "wait", "waitfor") and args.get("selector"):
                    actions.append(
                        WaitFor(
                            selector=str(args["selector"]),
                            state=str(args.get("state", "visible")),
                        )
                    )
                    print(f"[Browser-Use] Action {idx}: Wait for {args['selector']}")
    except Exception as e:
        print(f"[Browser-Use] Error parsing action history: {e}")

    # Attempt to read Browser-Use structured output or final result to map to our schema now
    try:
        if (
            hasattr(agent, "history")
            and getattr(agent.history, "structured_output", None) is not None
        ):
            so = agent.history.structured_output
            try:
                payload: dict[str, Any] = getattr(so, "model_dump", dict)()
                if isinstance(payload, dict):
                    data = payload
                    print(f"[Browser-Use] Got structured output: {data}")
            except Exception as e:
                print(f"[Browser-Use] Failed to extract structured output: {e}")
        if data is None and hasattr(agent, "history") and hasattr(agent.history, "final_result"):
            final_text = agent.history.final_result()
            if isinstance(final_text, str) and final_text.strip():
                print(f"[Browser-Use] Extracting from final result text ({len(final_text)} chars)")
                from ..core.extractor.llm_extract import extract_from_text  # type: ignore

                data = extract_from_text(
                    nl_request, schema=schema, parameters=None, text=final_text
                )
                print(f"[Browser-Use] Extracted data: {data}")
    except Exception as e:
        print(f"[Browser-Use] Error extracting data: {e}")

    # Capture current page state for debugging
    try:
        if hasattr(session, "page") and session.page:
            current_html = session.page.content()
            html_pages.append(current_html)
            print(f"[Browser-Use] Captured final page HTML ({len(current_html)} chars)")

            # Save screenshot for debugging
            screenshot_path = screenshots_dir / f"exploration-final-{job_id}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            session.page.screenshot(path=str(screenshot_path), full_page=True)
            screenshots.append(screenshot_path)
            print(f"[Browser-Use] Saved final screenshot to {screenshot_path}")
    except Exception as e:
        print(f"[Browser-Use] Failed to capture final page state: {e}")

    print(
        f"[Browser-Use] Exploration complete. Actions: {len(actions)}, Data extracted: {data is not None}"
    )

    return ExplorationResult(
        steps=actions,
        html_pages=html_pages,
        screenshots=screenshots,
        urls=urls,
        data=data,
    )
