from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


def take_screenshot(
    url: str, out_path: Path, headless: bool = True, timeout_ms: int = 30000
) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(url)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out_path), full_page=True)
        finally:
            browser.close()
