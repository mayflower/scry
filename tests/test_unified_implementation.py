"""Tests for the unified implementation.

The unified implementation combines:
- Agentic exploration using native exploration
- Path optimization and IR generation
- Deterministic Playwright code generation
- Self-healing with retry logic
- Data extraction and validation
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scry.api.dto import ScrapeRequest
from scry.config.settings import settings
from scry.core.executor.runner import run_job, run_job_with_id


class TestUnifiedImplementation:
    """Test suite for the unified scraping implementation."""

    @pytest.mark.integration
    def test_basic_extraction(self):
        """Test basic data extraction with simple HTML."""
        html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Main Heading</h1>
            <p class="description">This is a test description.</p>
            <div class="price">$99.99</div>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract the title, heading, description and price",
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "heading": {"type": "string"},
                    "description": {"type": "string"},
                    "price": {"type": "string"},
                },
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Verify response structure
        assert res.job_id is not None
        assert res.status == "completed"
        assert isinstance(res.data, dict)

        # Verify data extraction
        assert res.data.get("title") == "Test Page"
        assert res.data.get("heading") == "Main Heading"
        assert "test description" in res.data.get("description", "").lower()
        assert "$99.99" in res.data.get("price", "")

    @pytest.mark.integration
    def test_exploration_phase(self):
        """Test that exploration with native exploration agent works."""
        html = """
        <html>
        <body>
            <div id="content">
                <h1>Products</h1>
                <div class="product">
                    <h2>Product A</h2>
                    <span class="price">$50</span>
                </div>
                <div class="product">
                    <h2>Product B</h2>
                    <span class="price">$75</span>
                </div>
            </div>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract all product names and prices",
            schema={
                "type": "object",
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "price": {"type": "string"},
                            },
                        },
                    },
                },
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Check execution log for exploration
        assert "exploring" in res.execution_log
        assert "exploration_complete" in res.execution_log

        # Check that data was extracted
        assert isinstance(res.data, dict)
        if "products" in res.data:
            assert isinstance(res.data["products"], list)

    @pytest.mark.integration
    def test_code_generation(self):
        """Test that Playwright code is generated from exploration."""
        html = "<html><body><h1>Code Gen Test</h1></body></html>"
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract the heading",
            schema={
                "type": "object",
                "properties": {"heading": {"type": "string"}},
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Check execution log for code generation
        assert "codegen" in res.execution_log
        assert "executing_script" in res.execution_log

        # Check that generated code artifact exists
        code_path = (
            Path(settings.artifacts_root) / "generated_code" / f"{res.job_id}.py"
        )
        assert code_path.exists(), f"Generated code not found at {code_path}"

        # Verify the generated code is valid Python
        code_content = code_path.read_text()
        assert "from playwright.sync_api import sync_playwright" in code_content
        assert "def main():" in code_content

    @pytest.mark.integration
    def test_artifacts_creation(self):
        """Test that all expected artifacts are created."""
        html = """
        <html>
        <head><title>Artifacts Test</title></head>
        <body>
            <h1>Test Content</h1>
            <p>This page tests artifact creation.</p>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract the title and content",
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
            target_urls=[url],
        )

        res = run_job(req)
        job_id = res.job_id
        artifacts_root = Path(settings.artifacts_root)

        # Check screenshots
        screenshots_dir = artifacts_root / "screenshots" / job_id
        assert screenshots_dir.exists()
        screenshots = list(screenshots_dir.glob("*.png"))
        assert len(screenshots) > 0, "No screenshots captured"

        # Check generated code
        code_path = artifacts_root / "generated_code" / f"{job_id}.py"
        assert code_path.exists(), "Generated code not found"

        # Check HTML snapshots
        html_dir = artifacts_root / "html"
        html_files = list(html_dir.glob(f"{job_id}-*.html"))
        assert len(html_files) > 0, "No HTML snapshots saved"

    @pytest.mark.integration
    def test_execution_log_completeness(self):
        """Test that execution log contains all expected steps."""
        html = "<html><body><h1>Log Test</h1></body></html>"
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract the heading",
            schema={
                "type": "object",
                "properties": {"heading": {"type": "string"}},
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Check for all expected log entries
        expected_entries = [
            "received",
            "exploring",
            "exploration_complete",
            "codegen",
            "executing_script",
            "extracting",
            "done",
        ]

        for entry in expected_entries:
            assert entry in res.execution_log, f"Missing log entry: {entry}"

        # Should have either optimizing or path_compressed
        assert (
            "optimizing" in res.execution_log or "path_compressed" in res.execution_log
        )

    @pytest.mark.integration
    def test_schema_validation(self):
        """Test that extracted data conforms to the provided schema."""
        html = """
        <html>
        <body>
            <div class="item">
                <h2>Item Name</h2>
                <span class="count">5</span>
                <span class="price">29.99</span>
            </div>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract item details with correct types",
            schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer"},
                    "price": {"type": "number"},
                },
                "required": ["name"],
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Check data was extracted
        assert isinstance(res.data, dict)

        # Verify types match schema
        if "name" in res.data:
            assert isinstance(res.data["name"], str)
        if "count" in res.data:
            assert isinstance(res.data["count"], (int, type(None)))
        if "price" in res.data:
            assert isinstance(res.data["price"], (int, float, type(None)))

    @pytest.mark.integration
    def test_no_target_url_handling(self):
        """Test handling when no target URL is provided."""
        req = ScrapeRequest(
            nl_request="Extract data",
            schema={
                "type": "object",
                "properties": {"data": {"type": "string"}},
            },
            target_urls=[],  # No URLs
        )

        res = run_job(req)

        # Should handle gracefully
        assert res.status == "completed"
        assert res.data == {}
        assert "no_target_url" in res.execution_log
        assert "done" in res.execution_log

    @pytest.mark.integration
    def test_complex_schema_extraction(self):
        """Test extraction with complex nested schema."""
        html = """
        <html>
        <body>
            <div class="company">
                <h1>TechCorp</h1>
                <div class="info">
                    <p class="description">Leading tech company</p>
                    <div class="stats">
                        <span class="employees">5000</span>
                        <span class="revenue">$1B</span>
                    </div>
                </div>
                <ul class="departments">
                    <li>Engineering</li>
                    <li>Sales</li>
                    <li>Marketing</li>
                </ul>
            </div>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract company information including departments and stats",
            schema={
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "description": {"type": "string"},
                    "stats": {
                        "type": "object",
                        "properties": {
                            "employees": {"type": "integer"},
                            "revenue": {"type": "string"},
                        },
                    },
                    "departments": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Check extraction worked
        assert res.status == "completed"
        assert isinstance(res.data, dict)

        # Verify nested structure
        if "departments" in res.data:
            assert isinstance(res.data["departments"], list)
        if "stats" in res.data:
            assert isinstance(res.data["stats"], dict)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_self_healing_retry(self):
        """Test self-healing retry logic on failure."""
        # This test would need a way to simulate failure and retry
        # For now, just test that the retry mechanism is in place
        html = "<html><body><h1>Retry Test</h1></body></html>"
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract heading",
            schema={
                "type": "object",
                "properties": {"heading": {"type": "string"}},
            },
            target_urls=[url],
        )

        # The self-healing loop should handle any issues
        res = run_job(req)

        # Should complete successfully even with potential issues
        assert res.status == "completed"

        # Check for repair attempts in log if any occurred
        repair_logs = [log for log in res.execution_log if "repair_attempt" in log]
        # If repairs happened, they should be logged
        if repair_logs:
            assert len(repair_logs) <= 20  # Max 20 repair attempts

    @pytest.mark.integration
    def test_job_with_id(self):
        """Test running job with specific ID."""
        import uuid

        job_id = str(uuid.uuid4())
        html = "<html><body><h1>ID Test</h1></body></html>"
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract heading",
            schema={
                "type": "object",
                "properties": {"heading": {"type": "string"}},
            },
            target_urls=[url],
        )

        res = run_job_with_id(job_id, req)

        # Should use the provided ID
        assert res.job_id == job_id
        assert res.status == "completed"

        # Check artifacts use correct ID
        artifacts_root = Path(settings.artifacts_root)
        screenshots_dir = artifacts_root / "screenshots" / job_id
        assert screenshots_dir.exists()


class TestDataExtraction:
    """Test suite specifically for data extraction capabilities."""

    @pytest.mark.integration
    def test_extract_multiple_items(self):
        """Test extracting multiple items from a list."""
        html = """
        <html>
        <body>
            <div class="products">
                <div class="product">
                    <h3>Product 1</h3>
                    <span class="price">$10</span>
                </div>
                <div class="product">
                    <h3>Product 2</h3>
                    <span class="price">$20</span>
                </div>
                <div class="product">
                    <h3>Product 3</h3>
                    <span class="price">$30</span>
                </div>
            </div>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract all products with their names and prices",
            schema={
                "type": "object",
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "price": {"type": "string"},
                            },
                        },
                    },
                },
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Should extract array of products
        assert res.status == "completed"
        if "products" in res.data:
            products = res.data["products"]
            assert isinstance(products, list)
            # Should extract at least some products
            if len(products) > 0:
                # Check structure of first product
                assert "name" in products[0] or "price" in products[0]

    @pytest.mark.integration
    def test_extract_with_missing_fields(self):
        """Test extraction when some fields are missing."""
        html = """
        <html>
        <body>
            <h1>Page Title</h1>
            <!-- description is missing -->
            <div class="content">Some content here</div>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract title, description, and content",
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},  # This won't be found
                    "content": {"type": "string"},
                },
                "required": ["title"],  # Only title is required
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Should complete successfully
        assert res.status == "completed"

        # Should extract available fields
        assert "title" in res.data  # Required field
        # Optional fields may or may not be present
        assert isinstance(res.data, dict)


class TestErrorHandling:
    """Test suite for error handling and edge cases."""

    @pytest.mark.integration
    def test_invalid_url_format(self):
        """Test handling of invalid URL formats."""
        req = ScrapeRequest(
            nl_request="Extract data",
            schema={
                "type": "object",
                "properties": {"data": {"type": "string"}},
            },
            target_urls=["not-a-valid-url"],
        )

        # Should handle gracefully - native exploration will try to navigate
        # but the exploration will adapt
        res = run_job(req)
        assert res.job_id is not None
        # May fail or return empty data depending on native exploration handling

    @pytest.mark.integration
    def test_empty_html_page(self):
        """Test extraction from empty HTML."""
        url = "data:text/html,<html><body></body></html>"

        req = ScrapeRequest(
            nl_request="Extract any data",
            schema={
                "type": "object",
                "properties": {"data": {"type": "string"}},
            },
            target_urls=[url],
        )

        res = run_job(req)

        # Should complete but with empty or minimal data
        assert res.status == "completed"
        assert isinstance(res.data, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
