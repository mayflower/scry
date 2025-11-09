"""Navigation executor for the ScrapePlan (V2).

Executes simple Navigate steps using Playwright, capturing screenshots along the way
and returning collected HTML snapshots.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote

from playwright.sync_api import TimeoutError as PWTimeoutError, sync_playwright

from ..ir.model import (
    Click,
    Fill,
    Hover,
    KeyPress,
    Navigate,
    ScrapePlan,
    Select,
    Upload,
    WaitFor,
)


def execute_plan(
    plan: ScrapePlan,
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    headless: bool = True,
    timeout_ms: int = 30000,
    login_params: dict[str, Any] | None = None,
) -> tuple[list[str], list[Path]]:
    html_snapshots: list[str] = []
    screenshots: list[Path] = []

    if not plan.steps:
        return html_snapshots, screenshots

    # Always use Playwright directly for deterministic execution of IR steps
    # Browser-use agent is used for exploration in run_v2_job, not here
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            lp = login_params or {}
            http_basic = None
            if isinstance(lp, dict):
                http_basic = lp.get("http_basic")
            if http_basic and isinstance(http_basic, dict):
                context = browser.new_context(
                    http_credentials={
                        "username": http_basic.get("username", ""),
                        "password": http_basic.get("password", ""),
                    }
                )
            else:
                context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            step_index = 0
            for step in plan.steps:
                step_index += 1
                if isinstance(step, Navigate):
                    # Support data: URLs to enable hermetic tests without network
                    if isinstance(step.url, str) and step.url.startswith("data:text/html"):
                        try:
                            html_part = step.url.split(",", 1)[1]
                            page.set_content(unquote(html_part))
                        except Exception:
                            page.goto(step.url)
                    else:
                        page.goto(step.url)
                elif isinstance(step, Click):
                    page.click(step.selector)
                elif isinstance(step, Fill):
                    page.fill(step.selector, step.text)
                elif isinstance(step, WaitFor):
                    state = step.state
                    try:
                        if state in ("visible", "hidden", "attached", "detached"):
                            from typing import Literal, cast

                            typed_state = cast(
                                "Literal['visible', 'hidden', 'attached', 'detached']",
                                state,
                            )
                            page.wait_for_selector(step.selector, state=typed_state)
                        else:
                            page.wait_for_selector(step.selector)
                    except PWTimeoutError:
                        # Non-fatal in V2: continue to capture artifacts
                        pass
                elif isinstance(step, Select):
                    page.select_option(step.selector, step.value)
                elif isinstance(step, Hover):
                    page.hover(step.selector)
                    page.wait_for_timeout(500)
                elif isinstance(step, KeyPress):
                    if step.selector:
                        page.locator(step.selector).press(step.key)
                    else:
                        page.keyboard.press(step.key)
                elif isinstance(step, Upload):
                    page.set_input_files(step.selector, step.file_path)

                # After each step, always capture screenshot and HTML
                out_path = screenshots_dir / f"step-{step_index}.png"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(out_path), full_page=True)
                screenshots.append(out_path)
                # Capture HTML snapshot and persist
                html = page.content()
                html_snapshots.append(html)
                html_dir.mkdir(parents=True, exist_ok=True)
                html_out = html_dir / f"{job_id}-page-{step_index}.html"
                html_out.write_text(html, encoding="utf-8")

                # Small scroll and another screenshot for coverage
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                    out_path2 = (
                        screenshots_dir / f"{'' if step_index else ''}step-{step_index}-scroll.png"
                    )
                    page.screenshot(path=str(out_path2), full_page=True)
                    screenshots.append(out_path2)
                except Exception:
                    pass

        finally:
            browser.close()

    return html_snapshots, screenshots
