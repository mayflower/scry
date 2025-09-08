"""Tests for V2 - Planning + Exploration + Provisional Extraction.

V2 Requirements:
- Introduce ScrapePlan IR (generic, schema-aligned)
- Claude used to convert NL request into IR
- Browser-Use/Playwright follows IR steps
- Provisional extraction using generic DOM rules only
- Output data matches the provided schema
- Multiple screenshots captured at key steps
- HTML snapshots saved for self-healing
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from universal_scraper.api.dto import ScrapeRequest
from universal_scraper.config.settings import settings
from universal_scraper.core.executor.runner import run_minimal_job, run_v2_job
from universal_scraper.core.ir.model import Click, Navigate, ScrapePlan
from universal_scraper.core.planner.plan_builder import build_plan


@pytest.mark.v2
def test_v2_minimal_data_url_extract():
    """Test basic V2 extraction with data URL."""
    # Minimal HTML via data: URL to avoid external network
    html = (
        "<html><head>"
        "<title>V2 Test Page</title>"
        "<meta name='description' content='Hello from V2.'>"
        "</head><body>"
        "<a href='/a'>One</a>"
        "<a href='https://example.org/b'>Two</a>"
        "</body></html>"
    )
    url = "data:text/html," + html

    req = ScrapeRequest(
        nl_request="Open and extract basic info",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "links": {"type": "array", "items": {"type": "string"}},
            },
        },
        target_urls=[url],
    )

    res = run_v2_job(req)
    assert isinstance(res.data, dict), res
    assert res.data.get("title") == "V2 Test Page"
    # description comes from meta
    assert "description" in res.data
    # links should resolve as strings; since base_url is a data: URL, they may remain as is
    assert "links" in res.data and isinstance(res.data["links"], list)


@pytest.mark.v2
def test_v2_scrape_plan_ir_generation():
    """Test that V2 generates ScrapePlan IR from NL request."""
    req = ScrapeRequest(
        nl_request="Navigate to the page, click the 'More Info' button, then extract the title",
        schema={"type": "object", "properties": {"title": {"type": "string"}}},
        target_urls=["https://example.com"],
    )

    # Test with API key (if available)
    plan = build_plan(req)
    assert isinstance(plan, ScrapePlan)
    assert len(plan.steps) > 0

    # First step should be Navigate to the target URL
    assert isinstance(plan.steps[0], Navigate)
    assert plan.steps[0].url == "https://example.com"

    # Test fallback when no API key
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
        fallback_plan = build_plan(req)
        assert isinstance(fallback_plan, ScrapePlan)
        # Fallback should still navigate to first URL
        if req.target_urls:
            assert len(fallback_plan.steps) > 0
            assert isinstance(fallback_plan.steps[0], Navigate)


@pytest.mark.v2
def test_v2_multiple_screenshots():
    """Test V2 captures multiple screenshots at key steps."""
    # Multi-step HTML with navigation
    html = """
    <html><body>
        <h1>Page 1</h1>
        <a href="data:text/html,<html><body><h1>Page 2</h1></body></html>">Next</a>
    </body></html>
    """
    url = "data:text/html," + html

    req = ScrapeRequest(
        nl_request="Navigate and extract content from multiple pages",
        schema={"type": "object", "properties": {"content": {"type": "string"}}},
        target_urls=[url],
    )

    res = run_v2_job(req)

    # Check screenshots directory
    screenshots_dir = Path(settings.artifacts_root) / "screenshots" / res.job_id
    if screenshots_dir.exists():
        screenshots = list(screenshots_dir.glob("*.png"))
        # V2 should potentially capture multiple screenshots
        assert len(screenshots) >= 1
        # Check naming convention
        for screenshot in screenshots:
            assert screenshot.name.startswith("step-")


@pytest.mark.v2
def test_v2_html_artifacts():
    """Test V2 saves HTML snapshots for self-healing."""
    html = "<html><head><title>HTML Test</title></head><body><p>Content</p></body></html>"
    url = "data:text/html," + html

    req = ScrapeRequest(
        nl_request="Extract the page content",
        schema={"type": "object", "properties": {"content": {"type": "string"}}},
        target_urls=[url],
    )

    res = run_v2_job(req)

    # Check HTML artifacts
    html_dir = Path(settings.artifacts_root) / "html"
    html_file = html_dir / f"{res.job_id}-page-1.html"

    # V2 should save HTML snapshots
    assert html_file.exists(), f"HTML artifact not found at {html_file}"

    # Verify HTML content is not empty
    html_content = html_file.read_text(encoding="utf-8")
    assert len(html_content) > 0
    assert "HTML Test" in html_content or "Content" in html_content


@pytest.mark.v2
def test_v2_execution_log_sequence():
    """Test V2 execution log contains planning and extraction steps."""
    req = ScrapeRequest(
        nl_request="Extract data",
        schema={"type": "object", "properties": {"data": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>Test</body></html>"],
    )

    res = run_v2_job(req)

    # V2-specific log entries
    assert "received" in res.execution_log
    assert "planning" in res.execution_log  # V2-specific
    assert "navigating" in res.execution_log
    assert "extracting" in res.execution_log  # V2-specific
    assert "done" in res.execution_log

    # Should have screenshots_captured or no_screenshots
    assert any(log in res.execution_log for log in ["screenshots_captured", "no_screenshots"])

    # V2 should NOT have V3+ steps
    assert "optimizing" not in res.execution_log
    assert "codegen" not in res.execution_log
    assert "executing_script" not in res.execution_log


@pytest.mark.v2
def test_v2_schema_partial_extraction():
    """Test V2 handles missing/optional fields correctly."""
    html = """
    <html><body>
        <h1>Title Present</h1>
        <!-- description missing -->
        <div class="optional">Optional Content</div>
    </body></html>
    """
    url = "data:text/html," + html

    req = ScrapeRequest(
        nl_request="Extract all available data",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},  # Should be extracted
                "description": {"type": "string"},  # Missing in HTML
                "optional": {"type": "string"},  # May or may not be found
                "nested": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "required": ["title"],  # Only title is required
        },
        target_urls=[url],
    )

    res = run_v2_job(req)

    # Should extract what's available
    assert isinstance(res.data, dict)
    assert "title" in res.data  # Required field should be attempted

    # Missing fields should be handled gracefully
    # (either omitted or null, depending on implementation)
    assert res.status == "completed"


@pytest.mark.v2
def test_v2_no_code_generation():
    """Test V2 does NOT generate Playwright code (that's V3+)."""
    req = ScrapeRequest(
        nl_request="Extract content",
        schema={"type": "object", "properties": {"content": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>No Code Gen Test</body></html>"],
    )

    res = run_v2_job(req)

    # Check NO code generation artifacts
    code_dir = Path(settings.artifacts_root) / "generated_code"
    code_file = code_dir / f"{res.job_id}.py"

    assert not code_file.exists(), f"V2 should not generate code at {code_file}"

    # Execution log should not mention codegen
    assert "codegen" not in res.execution_log
    assert "generated_code" not in str(res)


@pytest.mark.v2
def test_v2_extraction_accuracy():
    """Test V2 extracts data matching schema accurately."""
    html = """
    <html>
    <head><title>Accurate Extraction Test</title></head>
    <body>
        <h1>Main Heading</h1>
        <p class="description">This is a description.</p>
        <ul>
            <li><a href="/page1">Link 1</a></li>
            <li><a href="/page2">Link 2</a></li>
            <li><a href="/page3">Link 3</a></li>
        </ul>
        <div class="stats">
            <span class="count">42</span>
            <span class="total">100</span>
        </div>
    </body>
    </html>
    """
    url = "data:text/html," + html

    req = ScrapeRequest(
        nl_request="Extract title, description, links, and statistics",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "heading": {"type": "string"},
                "description": {"type": "string"},
                "links": {"type": "array", "items": {"type": "string"}},
                "stats": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "total": {"type": "integer"},
                    },
                },
            },
        },
        target_urls=[url],
    )

    res = run_v2_job(req)

    assert isinstance(res.data, dict)
    # Should extract various elements
    if res.data.get("title"):
        assert "Accurate Extraction Test" in res.data["title"]
    if res.data.get("links"):
        assert isinstance(res.data["links"], list)
        assert len(res.data["links"]) > 0


@pytest.mark.v2
def test_v2_login_params_support():
    """Test V2 passes login_params to execute_plan."""
    req = ScrapeRequest(
        nl_request="Login and extract data",
        schema={"type": "object", "properties": {"data": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>Login Test</body></html>"],
        login_params={
            "username": "testuser",
            "password": "testpass",
            "login_url": "https://example.com/login",
        },
    )

    # Mock execute_plan to verify it receives login_params
    with patch("universal_scraper.core.executor.runner.execute_plan") as mock_execute:
        mock_execute.return_value = (["<html></html>"], ["screenshot.png"])
        _ = run_v2_job(req)

        # Verify execute_plan was called with login_params
        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert "login_params" in call_kwargs
        assert call_kwargs["login_params"] == req.login_params


@pytest.mark.v2
def test_v2_vs_v1_differences():
    """Test key differences between V1 and V2."""
    html = """
    <html>
    <head><title>V1 vs V2 Test</title></head>
    <body>
        <h1>Comparison Test</h1>
        <p>This content should be extracted by V2 but not V1.</p>
    </body>
    </html>
    """
    url = "data:text/html," + html

    req = ScrapeRequest(
        nl_request="Extract title and content",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
        },
        target_urls=[url],
    )

    # Run through V1
    v1_res = run_minimal_job(req)

    # Run through V2
    v2_res = run_v2_job(req)

    # V1 characteristics
    assert v1_res.data == {}  # V1 returns empty data
    assert "planning" not in v1_res.execution_log
    assert "extracting" not in v1_res.execution_log

    # V2 characteristics
    assert v2_res.data != {}  # V2 extracts actual data
    assert "planning" in v2_res.execution_log  # V2 has planning step
    assert "extracting" in v2_res.execution_log  # V2 has extraction step

    # Check artifacts
    v2_html_file = Path(settings.artifacts_root) / "html" / f"{v2_res.job_id}-page-1.html"
    v1_html_file = Path(settings.artifacts_root) / "html" / f"{v1_res.job_id}-page-1.html"

    assert v2_html_file.exists()  # V2 saves HTML
    assert not v1_html_file.exists()  # V1 does not save HTML


@pytest.mark.v2
def test_v2_complex_navigation():
    """Test V2 handles multi-step navigation plans."""
    # Create a plan with multiple steps
    from universal_scraper.core.ir.model import Fill, WaitFor

    req = ScrapeRequest(
        nl_request="Navigate, click button, fill form, and wait for results",
        schema={"type": "object", "properties": {"result": {"type": "string"}}},
        target_urls=["https://example.com"],
    )

    # Create a complex plan
    complex_plan = ScrapePlan(
        steps=[
            Navigate(url="https://example.com"),
            Click(selector="button.start"),
            Fill(selector="input#search", text="test query"),
            WaitFor(selector="div.results", state="visible"),
        ],
        notes="Complex multi-step navigation",
    )

    # Mock build_plan to return our complex plan
    with patch("universal_scraper.core.executor.runner.build_plan") as mock_build:
        mock_build.return_value = complex_plan

        # Mock execute_plan to verify it receives the complex plan
        with patch("universal_scraper.core.executor.runner.execute_plan") as mock_execute:
            mock_execute.return_value = (
                ["<html><div class='results'>Result</div></html>"],
                ["screenshot.png"],
            )

            _ = run_v2_job(req)

            # Verify the complex plan was passed to execute_plan
            mock_execute.assert_called_once()
            executed_plan = mock_execute.call_args.args[0]
            assert len(executed_plan.steps) == 4
            assert isinstance(executed_plan.steps[0], Navigate)
            assert isinstance(executed_plan.steps[1], Click)
            assert isinstance(executed_plan.steps[2], Fill)
            assert isinstance(executed_plan.steps[3], WaitFor)
