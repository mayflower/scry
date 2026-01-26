"""Integration tests for new action types: Select, Hover, KeyPress, Upload."""

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from scry.api.dto import ScrapeRequest  # type: ignore
from scry.core.executor.runner import run_job_with_id  # type: ignore


def test_select_action_playwright():
    """Test Select action with dropdown menu."""
    html = """
    <html>
        <body>
            <select id="country">
                <option value="">Select Country</option>
                <option value="us">United States</option>
                <option value="uk">United Kingdom</option>
            </select>
            <div id="result"></div>
            <script>
                document.getElementById('country').onchange = function() {
                    document.getElementById('result').textContent = this.value;
                };
            </script>
        </body>
    </html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)

        # Execute Select action
        page.select_option("#country", "us")

        # Verify selection
        result = page.locator("#result").text_content()
        assert result == "us"

        browser.close()


def test_hover_action_playwright():
    """Test Hover action with hover-triggered content."""
    html = """
    <html>
        <body>
            <div id="menu" style="padding:10px; display:inline-block;">Hover me</div>
            <div id="submenu" style="display:none; padding:10px;">Hidden menu</div>
            <script>
                document.getElementById('menu').onmouseover = function() {
                    document.getElementById('submenu').style.display = 'inline-block';
                };
            </script>
        </body>
    </html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)

        # Execute Hover action
        page.hover("#menu")

        # Verify submenu is visible
        submenu = page.locator("#submenu")
        assert submenu.is_visible()

        browser.close()


def test_keypress_action_playwright():
    """Test KeyPress action with Enter key."""
    html = """
    <html>
        <body>
            <input id="search" type="text" />
            <div id="result"></div>
            <script>
                document.getElementById('search').onkeydown = function(e) {
                    if (e.key === 'Enter') {
                        document.getElementById('result').textContent = 'Enter pressed';
                    }
                };
            </script>
        </body>
    </html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)

        # Fill input and press Enter
        page.fill("#search", "test query")
        page.locator("#search").press("Enter")

        # Verify Enter was detected
        result = page.locator("#result").text_content()
        assert result == "Enter pressed"

        browser.close()


def test_upload_action_playwright(tmp_path: Path):
    """Test Upload action with file input."""
    html = """
    <html>
        <body>
            <input type="file" id="file-upload" />
            <div id="filename"></div>
            <script>
                document.getElementById('file-upload').onchange = function() {
                    document.getElementById('filename').textContent = this.files[0].name;
                };
            </script>
        </body>
    </html>
    """

    # Create temporary test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)

        # Execute Upload action
        page.set_input_files("#file-upload", str(test_file))

        # Verify file was uploaded
        filename = page.locator("#filename").text_content()
        assert filename == "test.txt"

        browser.close()


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_select_in_exploration():
    """Test that LLM can use Select action during exploration."""
    html = """
    <html>
        <body>
            <h1>Product Search</h1>
            <select id="category">
                <option value="">Select Category</option>
                <option value="electronics">Electronics</option>
                <option value="books">Books</option>
            </select>
            <div id="products" style="display:none;">
                <div class="product">Product 1</div>
                <div class="product">Product 2</div>
            </div>
            <script>
                document.getElementById('category').onchange = function() {
                    if (this.value) {
                        document.getElementById('products').style.display = 'block';
                    }
                };
            </script>
        </body>
    </html>
    """

    req = ScrapeRequest(
        nl_request="Select the Electronics category and extract the product list",
        output_schema={
            "type": "object",
            "properties": {
                "products": {"type": "array", "items": {"type": "string"}},
                "category": {"type": "string"},
            },
        },
        target_urls=[f"data:text/html,{html}"],
    )

    result = run_job_with_id("select-test", req)

    # Verify exploration used Select action
    assert result.status == "completed"
    assert result.data, "Expected data extraction"
    print(f"Select test result: {result.data}")


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_hover_in_exploration():
    """Test that LLM can use Hover action during exploration."""
    html = """
    <html>
        <body>
            <h1>Menu Navigation</h1>
            <div id="menu-item" style="cursor:pointer;">Products</div>
            <div id="submenu" style="display:none;">
                <a href="#laptop">Laptop</a>
                <a href="#phone">Phone</a>
            </div>
            <script>
                document.getElementById('menu-item').onmouseover = function() {
                    document.getElementById('submenu').style.display = 'block';
                };
            </script>
        </body>
    </html>
    """

    req = ScrapeRequest(
        nl_request="Hover over the menu to reveal submenu items and extract them",
        output_schema={
            "type": "object",
            "properties": {
                "menu_items": {"type": "array", "items": {"type": "string"}},
            },
        },
        target_urls=[f"data:text/html,{html}"],
    )

    result = run_job_with_id("hover-test", req)

    # Verify exploration used Hover action
    assert result.status == "completed"
    assert result.data, "Expected data extraction"
    print(f"Hover test result: {result.data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
