"""Tests for V1 - Minimal Vertical Slice functionality.

V1 Requirements:
- Accept full request (NL query, schema, target URLs)
- In-process orchestration (no external queue)
- Open first target_url with Playwright
- Take a single screenshot
- Return empty but schema-conformant data
- Return transient execution_log
- Save screenshot to artifacts/screenshots/{job_id}/step-1.png
- No code generation
"""

from __future__ import annotations

from pathlib import Path

import pytest
from universal_scraper.api.dto import ScrapeRequest
from universal_scraper.config.settings import settings
from universal_scraper.core.executor.runner import run_minimal_job


@pytest.mark.v1
def test_v1_minimal_with_url():
    """Test V1 with a target URL - should take screenshot and return empty data."""
    # Simple HTML via data: URL to avoid external network
    html = (
        "<html><head><title>V1 Test</title></head>"
        "<body><h1>Test Page</h1><p>Content here</p></body></html>"
    )
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

    res = run_minimal_job(req)

    # Check response structure
    assert res.job_id is not None
    assert isinstance(res.data, dict)
    assert res.data == {}  # V1 returns empty data

    # Check execution log sequence
    assert res.execution_log == [
        "received",
        "navigating",
        "screenshot_captured",
        "done",
    ]

    # Check screenshot was created
    screenshots_dir = Path(settings.artifacts_root) / "screenshots" / res.job_id
    screenshot_file = screenshots_dir / "step-1.png"
    assert screenshot_file.exists(), f"Screenshot not found at {screenshot_file}"


@pytest.mark.v1
def test_v1_minimal_without_url():
    """Test V1 without target URLs - should not take screenshot."""
    req = ScrapeRequest(
        nl_request="Extract some data",
        schema={
            "type": "object",
            "properties": {
                "data": {"type": "string"},
            },
        },
        target_urls=[],  # No URLs provided
    )

    res = run_minimal_job(req)

    # Check response
    assert res.job_id is not None
    assert res.data == {}

    # Check execution log - no navigation
    assert res.execution_log == ["received", "no_target_url", "done"]

    # Check no screenshot was created
    screenshots_dir = Path(settings.artifacts_root) / "screenshots" / res.job_id
    screenshot_file = screenshots_dir / "step-1.png"
    assert not screenshot_file.exists()


@pytest.mark.v1
def test_v1_schema_conformance():
    """Test V1 returns empty but schema-conformant data for complex schemas."""
    req = ScrapeRequest(
        nl_request="Extract complex nested data",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                        },
                    },
                },
                "metadata": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
        target_urls=["data:text/html,<html><body>Test</body></html>"],
    )

    res = run_minimal_job(req)

    # V1 returns empty dict regardless of schema complexity
    assert res.data == {}
    assert isinstance(res.data, dict)


@pytest.mark.v1
def test_v1_artifact_paths():
    """Test V1 creates correct artifacts and no extra artifacts."""
    req = ScrapeRequest(
        nl_request="Test artifact creation",
        schema={"type": "object", "properties": {"test": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>Artifacts Test</body></html>"],
    )

    res = run_minimal_job(req)
    job_id = res.job_id
    artifacts_root = Path(settings.artifacts_root)

    # Check screenshot exists at correct path
    screenshot_path = artifacts_root / "screenshots" / job_id / "step-1.png"
    assert screenshot_path.exists(), f"Screenshot not at {screenshot_path}"

    # Check no code generation artifacts
    code_path = artifacts_root / "generated_code" / f"{job_id}.py"
    assert not code_path.exists(), f"V1 should not generate code at {code_path}"

    # Check no HTML artifacts
    html_path = artifacts_root / "html" / f"{job_id}-page-1.html"
    assert not html_path.exists(), f"V1 should not save HTML at {html_path}"


@pytest.mark.v1
def test_v1_execution_log_sequence():
    """Test V1 execution log contains only minimal steps, no planning/optimization."""
    req = ScrapeRequest(
        nl_request="Test execution log",
        schema={"type": "object", "properties": {"test": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>Log Test</body></html>"],
    )

    res = run_minimal_job(req)

    # Check log has correct V1 steps
    assert "received" in res.execution_log
    assert "done" in res.execution_log

    # Check log does NOT have V2+ steps
    assert "planning" not in res.execution_log
    assert "optimizing" not in res.execution_log
    assert "codegen" not in res.execution_log
    assert "exploring" not in res.execution_log
    assert "path_compressed" not in res.execution_log
    assert "executing_script" not in res.execution_log

    # Log should be minimal
    assert (
        len(res.execution_log) <= 4
    )  # received, navigating, screenshot_captured, done


@pytest.mark.v1
def test_v1_multiple_urls_uses_first():
    """Test V1 uses only the first URL when multiple are provided."""
    urls = [
        "data:text/html,<html><title>First</title></html>",
        "data:text/html,<html><title>Second</title></html>",
        "data:text/html,<html><title>Third</title></html>",
    ]

    req = ScrapeRequest(
        nl_request="Test multiple URLs",
        schema={"type": "object", "properties": {"title": {"type": "string"}}},
        target_urls=urls,
    )

    res = run_minimal_job(req)

    # Should navigate to first URL only
    assert res.execution_log == [
        "received",
        "navigating",
        "screenshot_captured",
        "done",
    ]

    # Only one screenshot should exist
    screenshots_dir = Path(settings.artifacts_root) / "screenshots" / res.job_id
    screenshot_files = list(screenshots_dir.glob("*.png"))
    assert len(screenshot_files) == 1
    assert screenshot_files[0].name == "step-1.png"
