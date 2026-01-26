"""Navigation executor for the ScrapePlan (V2).

Executes simple Navigate steps using Playwright, capturing screenshots along the way
and returning collected HTML snapshots.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeoutError

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

if TYPE_CHECKING:
    from pathlib import Path


# --- Step Executors ---


def _execute_navigate(page: Page, step: Navigate) -> None:
    """Execute a Navigate step, supporting data: URLs for testing."""
    if isinstance(step.url, str) and step.url.startswith("data:text/html"):
        try:
            html_part = step.url.split(",", 1)[1]
            page.set_content(unquote(html_part))
        except Exception:
            page.goto(step.url)
    else:
        page.goto(step.url)


def _execute_click(page: Page, step: Click) -> None:
    """Execute a Click step."""
    page.click(step.selector)


def _execute_fill(page: Page, step: Fill) -> None:
    """Execute a Fill step."""
    page.fill(step.selector, step.text)


def _execute_wait_for(page: Page, step: WaitFor) -> None:
    """Execute a WaitFor step with state handling."""
    state = step.state
    try:
        if state in ("visible", "hidden", "attached", "detached"):
            page.wait_for_selector(step.selector, state=state)  # type: ignore[arg-type]
        else:
            page.wait_for_selector(step.selector)
    except PWTimeoutError:
        # Non-fatal in V2: continue to capture artifacts
        pass


def _execute_select(page: Page, step: Select) -> None:
    """Execute a Select step."""
    page.select_option(step.selector, step.value)


def _execute_hover(page: Page, step: Hover) -> None:
    """Execute a Hover step with a small delay."""
    page.hover(step.selector)
    page.wait_for_timeout(500)


def _execute_keypress(page: Page, step: KeyPress) -> None:
    """Execute a KeyPress step."""
    if step.selector:
        page.locator(step.selector).press(step.key)
    else:
        page.keyboard.press(step.key)


def _execute_upload(page: Page, step: Upload) -> None:
    """Execute an Upload step."""
    page.set_input_files(step.selector, step.file_path)


def _execute_step(page: Page, step: Any) -> None:
    """Dispatch step execution to the appropriate handler."""
    if isinstance(step, Navigate):
        _execute_navigate(page, step)
    elif isinstance(step, Click):
        _execute_click(page, step)
    elif isinstance(step, Fill):
        _execute_fill(page, step)
    elif isinstance(step, WaitFor):
        _execute_wait_for(page, step)
    elif isinstance(step, Select):
        _execute_select(page, step)
    elif isinstance(step, Hover):
        _execute_hover(page, step)
    elif isinstance(step, KeyPress):
        _execute_keypress(page, step)
    elif isinstance(step, Upload):
        _execute_upload(page, step)


# --- Context Setup ---


def _get_http_credentials(login_params: dict[str, Any] | None) -> dict[str, str] | None:
    """Extract HTTP basic auth credentials from login params."""
    if not login_params or not isinstance(login_params, dict):
        return None
    http_basic = login_params.get("http_basic")
    if not http_basic or not isinstance(http_basic, dict):
        return None
    return {
        "username": http_basic.get("username", ""),
        "password": http_basic.get("password", ""),
    }


def _create_browser_context(browser: Any, login_params: dict[str, Any] | None) -> Any:
    """Create browser context with optional HTTP credentials."""
    credentials = _get_http_credentials(login_params)
    if credentials:
        return browser.new_context(http_credentials=credentials)
    return browser.new_context()


# --- Artifact Capture ---


def _capture_artifacts(
    page: Page,
    step_index: int,
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    html_snapshots: list[str],
    screenshots: list[Path],
) -> None:
    """Capture screenshot and HTML after a step."""
    # Screenshot
    out_path = screenshots_dir / f"step-{step_index}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_path), full_page=True)
    screenshots.append(out_path)

    # HTML snapshot
    html = page.content()
    html_snapshots.append(html)
    html_dir.mkdir(parents=True, exist_ok=True)
    html_out = html_dir / f"{job_id}-page-{step_index}.html"
    html_out.write_text(html, encoding="utf-8")

    # Scroll screenshot for coverage
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
        out_path2 = screenshots_dir / f"step-{step_index}-scroll.png"
        page.screenshot(path=str(out_path2), full_page=True)
        screenshots.append(out_path2)
    except Exception:  # noqa: S110 - screenshot failure shouldn't stop navigation
        pass


# --- Main Entry Point ---


def execute_plan(
    plan: ScrapePlan,
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    headless: bool = True,
    timeout_ms: int = 30000,
    login_params: dict[str, Any] | None = None,
) -> tuple[list[str], list[Path]]:
    """Execute a scraping plan and return HTML snapshots and screenshot paths."""
    html_snapshots: list[str] = []
    screenshots: list[Path] = []

    if not plan.steps:
        return html_snapshots, screenshots

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            context = _create_browser_context(browser, login_params)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            for step_index, step in enumerate(plan.steps, start=1):
                _execute_step(page, step)
                _capture_artifacts(
                    page, step_index, screenshots_dir, html_dir, job_id, html_snapshots, screenshots
                )
        finally:
            browser.close()

    return html_snapshots, screenshots
