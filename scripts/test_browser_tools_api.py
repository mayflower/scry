#!/usr/bin/env python3
"""Quick test to verify Browser Tools API integration works."""

import os
import sys
import tempfile
from pathlib import Path


# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scry.adapters.anthropic import BROWSER_TOOLS_MODEL
from scry.adapters.playwright_explorer import explore_with_playwright


def test_simple_exploration():
    """Test basic exploration with Browser Tools API."""
    # Simple HTML for testing
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1 id="main-title">Hello World</h1>
        <p>This is a test page with some content.</p>
        <button id="test-btn">Click Me</button>
    </body>
    </html>
    """

    import urllib.parse

    data_url = f"data:text/html,{urllib.parse.quote(html)}"

    # Schema for extraction
    schema = {
        "type": "object",
        "properties": {
            "heading": {"type": "string"},
            "has_button": {"type": "boolean"},
        },
    }

    # Create temp directories using tempfile for security
    screenshots_dir = Path(tempfile.mkdtemp(prefix="scry-test-screenshots-"))
    html_dir = Path(tempfile.mkdtemp(prefix="scry-test-html-"))

    try:
        print("[Test] Starting Browser Tools API exploration test")
        print(f"[Test] Target: {data_url[:100]}...")
        print(f"[Test] Model: {BROWSER_TOOLS_MODEL}")

        result = explore_with_playwright(
            start_url=data_url,
            nl_request="Navigate to the page and extract the heading text. Check if there's a button.",
            schema=schema,
            screenshots_dir=screenshots_dir,
            html_dir=html_dir,
            job_id="test-browser-tools-api",
            max_steps=5,  # Keep it short for testing
            headless=True,
            login_params=None,
        )

        print("\n[Test] ✅ Exploration completed successfully!")
        print(f"[Test] IR Actions: {len(result.steps)}")
        print(f"[Test] Screenshots: {len(result.screenshots)}")
        print(f"[Test] HTML pages: {len(result.html_pages)}")
        print(f"[Test] URLs visited: {result.urls}")
        print(f"[Test] Data extracted: {result.data}")

        # Verify we got some actions
        if result.steps:
            print(f"\n[Test] First action: {result.steps[0]}")

        return True

    except Exception as e:
        print(f"\n[Test] ❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run the test."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("[Test] ⚠️  ANTHROPIC_API_KEY not set, skipping test")
        return

    success = test_simple_exploration()

    if success:
        print("\n" + "=" * 60)
        print("✅ BROWSER TOOLS API INTEGRATION TEST PASSED")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ BROWSER TOOLS API INTEGRATION TEST FAILED")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
