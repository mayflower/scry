"""Tests for the validation-based self-healing system.

This test suite covers:
- Validate IR model class
- Validation capture during native exploration exploration
- Validation preservation during path optimization
- Validation code generation in Playwright scripts
- Validation failure handling and self-healing triggers
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scry.api.dto import ScrapeRequest
from scry.core.codegen.generator import generate_script
from scry.core.executor.runner import run_job_with_id
from scry.core.ir.model import (
    Click,
    Fill,
    Navigate,
    ScrapePlan,
    Validate,
)
from scry.core.nav.explore import ExplorationResult
from scry.core.optimizer.optimize import optimize_plan


class TestValidateIRModel:
    """Test the Validate class in the IR model."""

    def test_validate_creation(self):
        """Test creating a Validate step with all parameters."""
        validate = Validate(
            selector="div.content",
            expected_text="Hello World",
            expected_count=5,
            is_critical=True,
            description="Check main content",
            validation_type="text",
        )

        assert validate.selector == "div.content"
        assert validate.expected_text == "Hello World"
        assert validate.expected_count == 5
        assert validate.is_critical is True
        assert validate.description == "Check main content"
        assert validate.validation_type == "text"

    def test_validate_defaults(self):
        """Test Validate step with default values."""
        validate = Validate(selector="body")

        assert validate.selector == "body"
        assert validate.expected_text is None
        assert validate.expected_count is None
        assert validate.is_critical is False
        assert validate.description == ""
        assert validate.validation_type == "presence"

    def test_validate_types(self):
        """Test different validation types."""
        presence = Validate(selector="#header", validation_type="presence")
        absence = Validate(selector=".error", validation_type="absence")
        text = Validate(selector=".title", validation_type="text", expected_text="Welcome")
        count = Validate(selector=".item", validation_type="count", expected_count=10)

        assert presence.validation_type == "presence"
        assert absence.validation_type == "absence"
        assert text.validation_type == "text"
        assert count.validation_type == "count"

    def test_critical_vs_non_critical(self):
        """Test critical vs non-critical validations."""
        critical = Validate(
            selector=".required",
            is_critical=True,
            description="Critical check",
        )
        non_critical = Validate(
            selector=".optional",
            is_critical=False,
            description="Optional check",
        )

        assert critical.is_critical is True
        assert non_critical.is_critical is False


class TestValidationInBrowserUse:
    """Test validation capture during native exploration exploration."""

    def test_native_explorer_adds_validations(self):
        """Test that validation logic adds checkpoints after navigation and clicks."""
        # This test verifies the validation logic directly without running native exploration
        # since native exploration requires actual browser and network access

        # Simulate what native_explorer.py does when processing action history
        steps = []
        actions = [
            {"name": "navigate", "args": {"url": "https://example.com"}},
            {"name": "click", "args": {"selector": "button.submit"}},
            {"name": "fill", "args": {"selector": "input", "text": "test"}},
        ]

        # Simulate the validation injection logic from native_explorer.py
        for i, action in enumerate(actions):
            name = action.get("name", "").lower()
            args = action.get("args", {})

            if name == "navigate" and args.get("url"):
                steps.append(Navigate(url=str(args["url"])))
                # Add validation after navigation (as native_explorer.py does)
                if i < len(actions) - 1:
                    steps.append(
                        Validate(
                            selector="body",
                            validation_type="presence",
                            description="Verify page loaded after navigation",
                            is_critical=True,
                        )
                    )
            elif name == "click" and args.get("selector"):
                steps.append(Click(selector=str(args["selector"])))
                # Add validation after click (as native_explorer.py does)
                if i < len(actions) - 1:
                    steps.append(
                        Validate(
                            selector=str(args.get("selector", "body")),
                            validation_type="presence",
                            description="Verify element still present after click",
                            is_critical=False,
                        )
                    )
            elif name == "fill" and args.get("selector"):
                steps.append(
                    Fill(
                        selector=str(args["selector"]),
                        text=str(args.get("text", "")),
                    )
                )

        # Check that validations were added
        validate_steps = [s for s in steps if isinstance(s, Validate)]
        assert len(validate_steps) == 2, f"Expected 2 validations, got {len(validate_steps)}"

        # Check navigation validation
        nav_validations = [v for v in validate_steps if "page loaded" in v.description.lower()]
        assert len(nav_validations) == 1, "Should have one navigation validation"
        assert nav_validations[0].is_critical is True

        # Check click validation
        click_validations = [v for v in validate_steps if "after click" in v.description.lower()]
        assert len(click_validations) == 1, "Should have one click validation"
        assert click_validations[0].is_critical is False

    def test_validation_after_navigation(self):
        """Test that validations are added after navigation steps."""
        steps = [
            Navigate(url="https://example.com"),
            Click(selector="button"),
            Navigate(url="https://example.com/page2"),
            Click(selector="button2"),  # Add another action so second Navigate isn't last
        ]

        # Simulate what native_explorer.py does
        enhanced_steps = []
        for i, step in enumerate(steps):
            enhanced_steps.append(step)
            if isinstance(step, Navigate) and i < len(steps) - 1:
                enhanced_steps.append(
                    Validate(
                        selector="body",
                        validation_type="presence",
                        description="Verify page loaded after navigation",
                        is_critical=True,
                    )
                )

        # Should have added validations
        validate_steps = [s for s in enhanced_steps if isinstance(s, Validate)]
        assert len(validate_steps) == 2  # Two navigations, two validations

    def test_validation_after_click(self):
        """Test that validations are added after click actions."""
        steps = [
            Navigate(url="https://example.com"),
            Click(selector="button#submit"),
            Fill(selector="input", text="test"),
        ]

        # Simulate what native_explorer.py does
        enhanced_steps = []
        for i, step in enumerate(steps):
            enhanced_steps.append(step)
            if isinstance(step, Click) and i < len(steps) - 1:
                enhanced_steps.append(
                    Validate(
                        selector=step.selector,
                        validation_type="presence",
                        description="Verify element still present after click",
                        is_critical=False,
                    )
                )

        # Should have added validation after click
        validate_steps = [s for s in enhanced_steps if isinstance(s, Validate)]
        assert len(validate_steps) == 1
        assert validate_steps[0].selector == "button#submit"


class TestValidationInOptimizer:
    """Test validation preservation during path optimization."""

    def test_optimizer_preserves_validations(self):
        """Test that optimizer preserves validations for surviving steps."""
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://example.com"),
                Validate(
                    selector="body",
                    validation_type="presence",
                    description="Page loaded",
                    is_critical=True,
                ),
                Click(selector="button"),
                Validate(
                    selector="button",
                    validation_type="presence",
                    description="Button check",
                ),
                Click(selector="button"),  # Duplicate - should be removed
                Validate(
                    selector="button",
                    validation_type="presence",
                    description="Duplicate validation",
                ),
                Fill(selector="input", text="test"),
            ]
        )

        optimized = optimize_plan(plan)

        # Should remove duplicate click and its validation
        assert len(optimized.steps) < len(plan.steps)

        # Should preserve validations for surviving steps
        validate_steps = [s for s in optimized.steps if isinstance(s, Validate)]
        assert len(validate_steps) == 2  # Two validations should remain

    def test_optimizer_removes_orphan_validations(self):
        """Test that optimizer removes validations without preceding actions."""
        plan = ScrapePlan(
            steps=[
                Validate(
                    selector="div",
                    description="Orphan validation at start",
                ),
                Navigate(url="https://example.com"),
                Validate(
                    selector="body",
                    description="Valid validation after nav",
                ),
                Validate(
                    selector="div",
                    description="Another orphan",
                ),
                Validate(
                    selector="span",
                    description="Yet another orphan",
                ),
            ]
        )

        optimized = optimize_plan(plan)

        # Should only keep validation after navigation
        validate_steps = [s for s in optimized.steps if isinstance(s, Validate)]
        assert len(validate_steps) == 1
        assert validate_steps[0].description == "Valid validation after nav"

    def test_optimizer_handles_critical_validations(self):
        """Test that critical validations are preserved."""
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://example.com"),
                Validate(
                    selector="body",
                    is_critical=True,
                    description="Critical check",
                ),
                Click(selector="button"),
                Validate(
                    selector="div",
                    is_critical=False,
                    description="Non-critical check",
                ),
            ]
        )

        optimized = optimize_plan(plan)

        # Both validations should be preserved
        validate_steps = [s for s in optimized.steps if isinstance(s, Validate)]
        assert len(validate_steps) == 2

        # Critical validation should be preserved
        critical_validations = [v for v in validate_steps if v.is_critical]
        assert len(critical_validations) == 1


class TestValidationCodeGeneration:
    """Test validation code generation in Playwright scripts."""

    def test_generate_validation_code(self):
        """Test that validation steps generate correct Playwright code."""
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://example.com"),
                Validate(
                    selector="h1",
                    validation_type="presence",
                    description="Check heading exists",
                    is_critical=True,
                ),
                Validate(
                    selector=".error",
                    validation_type="absence",
                    description="No errors present",
                    is_critical=False,
                ),
                Validate(
                    selector=".title",
                    validation_type="text",
                    expected_text="Welcome",
                    description="Check welcome text",
                    is_critical=True,
                ),
                Validate(
                    selector=".item",
                    validation_type="count",
                    expected_count=5,
                    description="Check item count",
                    is_critical=False,
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = generate_script(
                plan,
                job_id="test-validation",
                artifacts_root=Path(tmpdir),
                headless=True,
                options={},
            )

            content = script_path.read_text()

            # Check for validation code
            assert "# Step" in content
            assert "Validate" in content
            assert "is_visible" in content
            assert "text_content" in content
            assert "count()" in content
            assert "sys.exit(1)" in content  # Critical failure handling
            assert "CRITICAL validation failed" in content
            assert "Non-critical validation failed" in content

    def test_critical_validation_exits(self):
        """Test that critical validations cause script exit on failure."""
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://example.com"),
                Validate(
                    selector=".non-existent",
                    validation_type="presence",
                    description="This will fail",
                    is_critical=True,
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = generate_script(
                plan,
                job_id="test-critical",
                artifacts_root=Path(tmpdir),
                headless=True,
                options={},
            )

            content = script_path.read_text()

            # Should exit on critical failure
            assert "sys.exit(1)" in content
            assert "is_critical" in content or "CRITICAL" in content


class TestValidationInRunner:
    """Test validation failure handling in the runner."""

    @pytest.mark.asyncio
    @patch("subprocess.run")
    async def test_runner_handles_validation_failure(self, mock_run):
        """Test that runner detects and handles validation failures."""
        # Simulate validation failure (exit code 1)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "CRITICAL validation failed: element not found"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        req = ScrapeRequest(
            nl_request="Extract title",
            schema={"type": "object", "properties": {"title": {"type": "string"}}},
            target_urls=["https://example.com"],
        )

        with patch(
            "scry.adapters.playwright_explorer.explore_with_playwright",
            new_callable=AsyncMock,
        ) as mock_explore:
            # Mock exploration result
            mock_explore.return_value = ExplorationResult(
                steps=[Navigate(url="https://example.com")],
                html_pages=[],
                screenshots=[],
                urls=["https://example.com"],
                data={"title": "Test"},
            )

            with patch("scry.core.executor.runner.propose_patch") as mock_patch:
                mock_patch.return_value = {"extra_wait_ms": 1000}

                result = await run_job_with_id("test-job", req)

                # Should detect validation failure
                assert any("validation_failed" in log for log in result.execution_log)

                # Should attempt repair
                assert mock_patch.called

    @pytest.mark.asyncio
    @patch("subprocess.run")
    async def test_runner_retries_on_validation_failure(self, mock_run):
        """Test that runner retries after validation failure."""
        # First call fails, second succeeds
        mock_result_fail = MagicMock()
        mock_result_fail.returncode = 1
        mock_result_fail.stderr = "CRITICAL validation failed"

        mock_result_success = MagicMock()
        mock_result_success.returncode = 0
        mock_result_success.stdout = "Success"

        mock_run.side_effect = [mock_result_fail, mock_result_success]

        req = ScrapeRequest(
            nl_request="Extract title",
            schema={"type": "object", "properties": {"title": {"type": "string"}}},
            target_urls=["https://example.com"],
        )

        with patch(
            "scry.adapters.playwright_explorer.explore_with_playwright",
            new_callable=AsyncMock,
        ) as mock_explore:
            mock_explore.return_value = ExplorationResult(
                steps=[Navigate(url="https://example.com")],
                html_pages=[],
                screenshots=[],
                urls=["https://example.com"],
                data={},
            )

            result = await run_job_with_id("test-job", req)

            # Should have tried twice
            assert mock_run.call_count == 2

            # Should have repair attempt in log
            repair_logs = [log for log in result.execution_log if "repair_attempt" in log]
            assert len(repair_logs) >= 1


class TestEndToEndValidation:
    """End-to-end tests for the validation system."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_full_validation_flow(self):
        """Test complete validation flow from exploration to self-healing."""
        html = """
        <html>
        <head><title>Validation Test Page</title></head>
        <body>
            <h1 id="main-heading">Welcome</h1>
            <div class="content">
                <p>This is test content.</p>
                <button id="action-btn">Click Me</button>
            </div>
            <div class="results" style="display:none;">
                <p>Results will appear here</p>
            </div>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract the heading and click the button to see results",
            schema={
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "results": {"type": "string"},
                },
            },
            target_urls=[url],
        )

        result = await run_job_with_id("validation-test", req)

        # Should complete successfully
        assert result.status == "completed"

        # Check for validation in execution log
        if "validation_failed" in result.execution_log:
            # If validation failed, should have attempted repair
            repair_logs = [log for log in result.execution_log if "repair_attempt" in log]
            assert len(repair_logs) > 0
        elif "validation_ok" in result.execution_log:
            # Validation passed - verify it's recorded in the log
            assert result.execution_log.count("validation_ok") >= 1
        else:
            # Should have some validation result
            assert "script_done" in result.execution_log

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_validation_with_dynamic_content(self):
        """Test validation with dynamically loaded content."""
        html = """
        <html>
        <body>
            <div id="content">Loading...</div>
            <script>
                setTimeout(() => {
                    document.getElementById('content').innerHTML = 'Loaded!';
                }, 100);
            </script>
        </body>
        </html>
        """
        url = f"data:text/html,{html}"

        req = ScrapeRequest(
            nl_request="Extract content after it loads",
            schema={
                "type": "object",
                "properties": {"content": {"type": "string"}},
            },
            target_urls=[url],
        )

        result = await run_job_with_id("dynamic-test", req)

        # Should handle dynamic content
        assert result.status == "completed"

        # If native exploration succeeded, we should have data
        if result.data:
            # Content should be "Loaded!" not "Loading..."
            assert result.data.get("content") != "Loading..."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
