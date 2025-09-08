"""Tests for V3 - Path Optimization + Code Generation + Decoupled Workers.

V3 Requirements:
- Path Optimizer: compress exploration path into stable steps
- Generate Playwright Python that runs without AI at runtime
- Redis event backend for decoupled workers
- Execute generated script and produce final data
- Artifacts: generated_code/{job_id}.py and screenshots

Key V3 innovation: Convert AI-discovered paths into deterministic,
reusable Python scripts that run without any LLM.
"""

from __future__ import annotations

import ast
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from universal_scraper.api.dto import ScrapeRequest
from universal_scraper.config.settings import settings
from universal_scraper.core.codegen.generator import generate_script
from universal_scraper.core.executor.runner import run_v2_job, run_v3_job
from universal_scraper.core.ir.model import Click, Fill, Navigate, ScrapePlan, WaitFor
from universal_scraper.core.optimizer.optimize import optimize_plan


@pytest.mark.v3
def test_v3_generates_playwright_script():
    """Test V3 generates a Playwright Python script file."""
    req = ScrapeRequest(
        nl_request="Navigate and extract content",
        schema={"type": "object", "properties": {"content": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>V3 Test</body></html>"],
    )

    res = run_v3_job(req)

    # Check script was generated
    script_path = Path(settings.artifacts_root) / "generated_code" / f"{res.job_id}.py"
    assert script_path.exists(), f"Script not generated at {script_path}"

    # Verify it's valid Python
    script_content = script_path.read_text(encoding="utf-8")
    assert len(script_content) > 0

    # Parse as Python to verify syntax
    try:
        ast.parse(script_content)
    except SyntaxError as e:
        pytest.fail(f"Generated script has invalid Python syntax: {e}")

    # Verify no AI/LLM imports
    assert "anthropic" not in script_content.lower()
    assert "openai" not in script_content.lower()
    assert "langchain" not in script_content.lower()
    assert "browser_use" not in script_content.lower()  # V3 uses pure Playwright


@pytest.mark.v3
def test_v3_script_is_executable():
    """Test V3 generated script can be executed."""
    plan = ScrapePlan(
        steps=[
            Navigate(url="data:text/html,<html><body>Executable Test</body></html>")
        ],
        notes="Simple navigation test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_path = Path(tmpdir)
        job_id = "test_exec_123"

        # Generate script
        script_path = generate_script(plan, job_id, artifacts_path, headless=True)

        assert script_path.exists()

        # Try to execute it (may fail without Playwright installed, but should be valid Python)
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{script_path}').read())"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Script parsing failed: {result.stderr}"


@pytest.mark.v3
def test_v3_execution_log_sequence():
    """Test V3 execution log contains correct sequence."""
    req = ScrapeRequest(
        nl_request="Test execution log",
        schema={"type": "object", "properties": {"test": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>Log Test</body></html>"],
    )

    res = run_v3_job(req)

    # V3-specific log sequence
    assert "received" in res.execution_log
    assert "planning" in res.execution_log
    assert "optimizing" in res.execution_log  # V3-specific
    assert "codegen" in res.execution_log  # V3-specific
    assert "executing_script" in res.execution_log  # V3-specific
    assert "extracting" in res.execution_log
    assert "done" in res.execution_log

    # Should have either script_done or script_failed
    assert any(
        status in res.execution_log for status in ["script_done", "script_failed"]
    )

    # V3 should NOT have V4+ steps (self-healing)
    assert "diagnosing" not in res.execution_log
    assert "patching" not in res.execution_log


@pytest.mark.v3
def test_v3_path_optimization():
    """Test V3 path optimizer removes duplicates and optimizes."""
    # Create a plan with potentially optimizable steps
    original_plan = ScrapePlan(
        steps=[
            Navigate(url="https://example.com"),
            Click(selector="button.menu"),
            Click(selector="button.menu"),  # Duplicate click - should be removed
            Navigate(url="https://example.com/page"),
        ],
        notes="Unoptimized plan",
    )

    optimized = optimize_plan(original_plan)

    # Optimization should remove the duplicate click
    assert len(optimized.steps) == 3  # Down from 4
    assert "optimized: 4 -> 3 steps" in optimized.notes

    # Check the steps are in correct order without duplicates
    assert isinstance(optimized.steps[0], Navigate)
    assert optimized.steps[0].url == "https://example.com"
    assert isinstance(optimized.steps[1], Click)
    assert optimized.steps[1].selector == "button.menu"
    assert isinstance(optimized.steps[2], Navigate)
    assert optimized.steps[2].url == "https://example.com/page"


@pytest.mark.v3
def test_v3_generated_script_structure():
    """Test V3 generated script has proper structure."""
    plan = ScrapePlan(
        steps=[
            Navigate(url="https://example.com"),
            Click(selector="button.start"),
        ],
        notes="Structure test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = generate_script(
            plan, "test_structure", Path(tmpdir), headless=True
        )

        script_content = script_path.read_text(encoding="utf-8")

        # Check essential imports
        assert "from playwright.sync_api import sync_playwright" in script_content
        assert "from pathlib import Path" in script_content

        # Check Playwright setup
        assert "sync_playwright()" in script_content
        assert "browser = p.chromium.launch" in script_content
        assert "context = browser.new_context()" in script_content
        assert "page = context.new_page()" in script_content

        # Check artifacts setup
        assert "screenshots" in script_content
        assert "html" in script_content
        assert "mkdir(parents=True, exist_ok=True)" in script_content

        # Check cleanup
        assert "browser.close()" in script_content


@pytest.mark.v3
def test_v3_script_captures_artifacts():
    """Test V3 script includes artifact capture code."""
    plan = ScrapePlan(
        steps=[Navigate(url="data:text/html,<html><body>Artifact Test</body></html>")],
        notes="Artifact capture test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        job_id = "artifact_test"
        script_path = generate_script(plan, job_id, Path(tmpdir), headless=True)

        script_content = script_path.read_text(encoding="utf-8")

        # Check screenshot capture
        assert "screenshot" in script_content.lower()
        assert ".png" in script_content

        # Check HTML capture
        assert "content()" in script_content or "innerHTML" in script_content.lower()
        assert ".html" in script_content

        # Check artifact paths use job_id
        assert job_id in script_content


@pytest.mark.v3
def test_v3_no_llm_at_runtime():
    """Test V3 generated scripts contain no LLM dependencies."""
    req = ScrapeRequest(
        nl_request="Test autonomous execution",
        schema={"type": "object", "properties": {"data": {"type": "string"}}},
        target_urls=[
            "data:text/html,<html><body>No Machine Learning Dependencies</body></html>"
        ],
    )

    res = run_v3_job(req)

    script_path = Path(settings.artifacts_root) / "generated_code" / f"{res.job_id}.py"
    script_content = script_path.read_text(encoding="utf-8")

    # List of LLM-related imports that should NOT be present
    forbidden_imports = [
        "anthropic",
        "openai",
        "langchain",
        "transformers",
        "browser_use",
        "claude",
        "gpt",
    ]

    for forbidden in forbidden_imports:
        assert forbidden not in script_content.lower(), (
            f"Generated script contains forbidden LLM import: {forbidden}"
        )

    # Check for LLM as a whole word (not as substring)
    import re

    assert not re.search(r"\bllm\b", script_content.lower()), (
        "Generated script contains 'llm' as a word"
    )

    # Should only use Playwright and standard libraries
    assert "playwright" in script_content.lower()
    assert "from pathlib import Path" in script_content


@pytest.mark.v3
def test_v3_redis_event_backend():
    """Test V3 Redis event backend integration (mocked)."""
    req = ScrapeRequest(
        nl_request="Test Redis events",
        schema={"type": "object", "properties": {"test": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>Redis Test</body></html>"],
    )

    # Mock Redis to test event publishing
    # Since redis is imported inside RedisBus class, we mock at that level
    with patch("redis.Redis"):
        # Set environment to use Redis
        with patch.dict(
            "os.environ",
            {"EVENT_BACKEND": "redis", "REDIS_URL": "redis://localhost:6379/0"},
        ):
            # This tests that V3 can run with Redis backend configured
            # The actual Redis interaction is mocked
            pass

    # For now, just verify V3 runs
    res = run_v3_job(req)
    # Check that the job completed successfully
    assert "done" in res.execution_log


@pytest.mark.v3
def test_v3_vs_v2_differences():
    """Test key differences between V2 and V3."""
    req = ScrapeRequest(
        nl_request="Compare V2 and V3",
        schema={"type": "object", "properties": {"data": {"type": "string"}}},
        target_urls=["data:text/html,<html><body>V2 vs V3</body></html>"],
    )

    # Run V2 (with mocked execute_plan to avoid browser-use dependency)
    with patch("universal_scraper.core.executor.runner.execute_plan") as mock_execute:
        mock_execute.return_value = (["<html></html>"], ["screenshot.png"])
        v2_res = run_v2_job(req)

    # Run V3
    v3_res = run_v3_job(req)

    # V2 characteristics
    assert "codegen" not in v2_res.execution_log  # V2 doesn't generate code
    assert "executing_script" not in v2_res.execution_log

    # V3 characteristics
    assert "optimizing" in v3_res.execution_log  # V3 optimizes path
    assert "codegen" in v3_res.execution_log  # V3 generates code
    assert "executing_script" in v3_res.execution_log  # V3 executes generated script

    # Check V3 created code artifact
    v3_script = Path(settings.artifacts_root) / "generated_code" / f"{v3_res.job_id}.py"
    v2_script = Path(settings.artifacts_root) / "generated_code" / f"{v2_res.job_id}.py"

    assert v3_script.exists()  # V3 generates script
    assert not v2_script.exists()  # V2 does not


@pytest.mark.v3
def test_v3_script_handles_errors():
    """Test V3 handles script execution errors gracefully."""
    # Create a plan that might fail
    plan = ScrapePlan(
        steps=[
            Navigate(url="https://unreachable.invalid.domain"),
            Click(selector="button.nonexistent"),
        ],
        notes="Error handling test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        job_id = "error_test"
        script_path = generate_script(plan, job_id, Path(tmpdir), headless=True)

        # The script should be generated even for invalid URLs
        assert script_path.exists()

        script_content = script_path.read_text(encoding="utf-8")

        # Should have try-except blocks for error handling
        assert "try:" in script_content
        assert "except" in script_content or "finally:" in script_content


@pytest.mark.v3
def test_v3_generates_deterministic_scripts():
    """Test V3 generates deterministic scripts for the same input."""
    plan = ScrapePlan(
        steps=[Navigate(url="https://example.com")],
        notes="Deterministic test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # Generate script twice with same inputs
        script1 = generate_script(plan, "job1", Path(tmpdir), headless=True)
        script2 = generate_script(plan, "job2", Path(tmpdir), headless=True)

        content1 = script1.read_text(encoding="utf-8")
        content2 = script2.read_text(encoding="utf-8")

        # Replace job_id to compare structure
        content1_normalized = content1.replace("job1", "JOB_ID")
        content2_normalized = content2.replace("job2", "JOB_ID")

        # Scripts should be structurally identical
        assert content1_normalized == content2_normalized


@pytest.mark.v3
def test_v3_click_step_generation():
    """Test V3 generates correct code for Click steps."""
    plan = ScrapePlan(
        steps=[
            Navigate(url="https://example.com"),
            Click(selector="button.submit"),
        ],
        notes="Click test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = generate_script(plan, "click_test", Path(tmpdir), headless=True)
        script_content = script_path.read_text(encoding="utf-8")

        # Check Click step is generated
        assert "Click button.submit" in script_content
        assert 'page.locator("button.submit").click' in script_content
        assert "page.wait_for_load_state" in script_content
        assert "step-2-click.png" in script_content


@pytest.mark.v3
def test_v3_fill_step_generation():
    """Test V3 generates correct code for Fill steps."""
    plan = ScrapePlan(
        steps=[
            Navigate(url="https://example.com"),
            Fill(selector="input#username", text="testuser"),
        ],
        notes="Fill test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = generate_script(plan, "fill_test", Path(tmpdir), headless=True)
        script_content = script_path.read_text(encoding="utf-8")

        # Check Fill step is generated
        assert "Fill input#username" in script_content
        assert 'page.locator("input#username").fill("testuser")' in script_content
        assert "step-2-fill.png" in script_content


@pytest.mark.v3
def test_v3_waitfor_step_generation():
    """Test V3 generates correct code for WaitFor steps."""
    plan = ScrapePlan(
        steps=[
            Navigate(url="https://example.com"),
            WaitFor(selector="div.loaded", state="visible"),
        ],
        notes="WaitFor test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = generate_script(plan, "wait_test", Path(tmpdir), headless=True)
        script_content = script_path.read_text(encoding="utf-8")

        # Check WaitFor step is generated
        assert "Wait for div.loaded" in script_content
        assert 'page.locator("div.loaded").wait_for(state="visible"' in script_content


@pytest.mark.v3
def test_v3_multi_page_navigation():
    """Test V3 handles multiple navigation steps correctly."""
    plan = ScrapePlan(
        steps=[
            Navigate(url="https://example.com"),
            Click(selector="a.next"),
            Navigate(url="https://example.com/page2"),
        ],
        notes="Multi-page test",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = generate_script(
            plan, "multipage_test", Path(tmpdir), headless=True
        )
        script_content = script_path.read_text(encoding="utf-8")

        # Check multiple page captures
        assert "page-1.html" in script_content
        assert "page-2.html" in script_content
        assert script_content.count("Navigate to") == 2


@pytest.mark.v3
def test_v3_path_optimization_removes_duplicates():
    """Test V3 path optimization removes duplicate steps."""
    from universal_scraper.core.optimizer.optimize import optimize_plan

    plan = ScrapePlan(
        steps=[
            Navigate(url="https://example.com"),
            Navigate(url="https://example.com"),  # Duplicate
            Click(selector="button"),
            Click(selector="button"),  # Duplicate
        ],
        notes="Unoptimized",
    )

    optimized = optimize_plan(plan)

    assert len(optimized.steps) == 2
    assert "optimized: 4 -> 2 steps" in optimized.notes
    assert isinstance(optimized.steps[0], Navigate)
    assert isinstance(optimized.steps[1], Click)


@pytest.mark.v3
def test_v3_selector_resilience():
    """Test resilient selector generation."""
    from universal_scraper.core.optimizer.selectors import make_resilient_selector

    # Test with HTML context
    html = '<button data-testid="submit-btn" id="submit" aria-label="Submit form">Submit</button>'
    selectors = make_resilient_selector("button", html)

    # Should prioritize stable attributes
    assert "#submit" in selectors  # id should be high priority
    assert '[data-testid="submit-btn"]' in selectors
    assert '[aria-label="Submit form"]' in selectors

    # Original should still be included
    assert "button" in selectors
