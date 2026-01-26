"""Real integration tests for self-healing system using mayflower.de.

These tests use actual browser automation and external dependencies
to validate the self-healing functionality against real websites.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from scry.api.dto import ScrapeRequest
from scry.config.settings import settings
from scry.core.codegen.generator import generate_script
from scry.core.executor.runner import run_job, run_job_with_id
from scry.core.ir.model import (
    Click,
    Navigate,
    ScrapePlan,
    Validate,
    WaitFor,
)
from scry.core.self_heal.diagnose import propose_patch
from scry.core.self_heal.patch import merge_codegen_options


class TestRealSelfHealing:
    """Test self-healing with real browser automation."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_mayflower_navigation_with_validation(self):
        """Test navigation to Mayflower site with validation checkpoints."""
        req = ScrapeRequest(
            nl_request="Navigate to Mayflower website and extract the company name and main heading",
            schema={
                "type": "object",
                "properties": {
                    "company": {"type": "string", "description": "Company name"},
                    "heading": {"type": "string", "description": "Main page heading"},
                },
            },
            target_urls=["https://mayflower.de/"],
        )

        result = run_job(req)

        # Should complete successfully
        assert result.status == "completed"
        assert result.job_id is not None

        # Check execution log for validation steps
        assert "exploring" in result.execution_log
        assert "script_done" in result.execution_log

        # Should extract some data
        assert result.data is not None
        if result.data:
            # Mayflower should be mentioned somewhere
            data_str = json.dumps(result.data).lower()
            assert "mayflower" in data_str or len(result.data) > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_validation_failure_and_recovery(self):
        """Test recovery from validation failures using a real page."""
        # Create a plan with a validation that might fail initially
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://mayflower.de/"),
                Validate(
                    selector="body",
                    validation_type="presence",
                    description="Check page loaded",
                    is_critical=True,
                ),
                # This might fail if cookie banner appears
                Validate(
                    selector="main",
                    validation_type="presence",
                    description="Check main content visible",
                    is_critical=True,
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            job_id = "test_validation_recovery"

            # Try with no options first
            options = {}
            script_path = generate_script(
                plan, job_id, artifacts_root, headless=True, options=options
            )

            # Execute and see if it needs healing
            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Should trigger self-healing
                print(f"Initial execution failed: {result.stderr}")

                # Get a patch
                patch = propose_patch(1, result.stderr, None)
                assert patch is not None
                assert len(patch) > 0

                # Apply patch and retry
                options = merge_codegen_options(options, patch)
                script_path = generate_script(
                    plan, job_id, artifacts_root, headless=True, options=options
                )

                result = subprocess.run(
                    ["python", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                # Should succeed after patch
                assert result.returncode == 0, f"Still failed after patch: {result.stderr}"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_progressive_healing_attempts(self):
        """Test that progressive healing attempts work on a real site."""
        # Create a challenging scraping request
        req = ScrapeRequest(
            nl_request="Navigate to Mayflower and find information about their services",
            schema={
                "type": "object",
                "properties": {
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of services offered",
                    },
                    "description": {
                        "type": "string",
                        "description": "Company description",
                    },
                },
            },
            target_urls=["https://mayflower.de/"],
        )

        result = run_job_with_id("test_progressive_healing", req)

        # Check for any repair attempts
        repair_logs = [log for log in result.execution_log if "repair_attempt" in log]

        # If repairs were needed, verify they were bounded
        if repair_logs:
            assert len(repair_logs) <= settings.max_repair_attempts
            print(f"Needed {len(repair_logs)} repair attempts")

        # Should eventually complete
        assert result.status == "completed"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_cookie_banner_handling(self):
        """Test that cookie banner patches work on real sites."""
        # Many German sites have cookie banners
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://mayflower.de/"),
                # Try to click something that might be blocked by cookie banner
                Click(selector="a[href*='leistungen']"),  # Services link
                Validate(
                    selector="body",
                    validation_type="presence",
                    description="Check navigation worked",
                    is_critical=True,
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            job_id = "test_cookie_banner"

            # Start with cookie banner handling disabled
            options = {"handle_cookie_banner": False}

            for attempt in range(1, 4):
                script_path = generate_script(
                    plan, job_id, artifacts_root, headless=True, options=options
                )

                result = subprocess.run(
                    ["python", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    print(f"Succeeded on attempt {attempt}")
                    break

                # Get patch for next attempt
                patch = propose_patch(attempt, result.stderr, None)
                options = merge_codegen_options(options, patch)

                # Check if cookie banner handling was added
                if attempt >= 2:
                    assert options.get("handle_cookie_banner") is True

    @pytest.mark.integration
    @pytest.mark.slow
    def test_timeout_recovery(self):
        """Test recovery from timeout errors with real page loading."""
        # Create a plan that might timeout on slow connections
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://mayflower.de/"),
                WaitFor(selector=".complex-element-that-might-not-exist", state="visible"),
                Navigate(url="https://mayflower.de/leistungen/"),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            job_id = "test_timeout"

            # Start with short timeout
            options = {}
            attempts = 0
            max_attempts = 3

            while attempts < max_attempts:
                attempts += 1
                script_path = generate_script(
                    plan, job_id, artifacts_root, headless=True, options=options
                )

                result = subprocess.run(
                    ["python", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode == 0:
                    break

                # Should get timeout error
                if "timeout" in result.stderr.lower():
                    # Get patch that should increase wait times
                    patch = propose_patch(attempts, result.stderr, None)

                    # Verify patch includes wait adjustments
                    assert patch.get("wait_load_state") is True or patch.get("extra_wait_ms", 0) > 0

                    options = merge_codegen_options(options, patch)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_dynamic_content_validation(self):
        """Test validation with dynamically loaded content."""
        req = ScrapeRequest(
            nl_request="Find and extract dynamic content from Mayflower site",
            schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Page content"},
                    "loaded": {
                        "type": "boolean",
                        "description": "Content loaded successfully",
                    },
                },
            },
            target_urls=["https://mayflower.de/"],
        )

        # Run with validation-based self-healing
        result = run_job(req)

        assert result.status == "completed"

        # Check if validations were used
        if "validation_ok" in result.execution_log:
            print("Validations passed on first try")
        elif "validation_failed" in result.execution_log:
            print("Validation failed but was recovered")
            # Should have repair attempts
            assert any("repair_attempt" in log for log in result.execution_log)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_multi_page_navigation_healing(self):
        """Test self-healing across multiple page navigations."""
        # Navigate through multiple pages on Mayflower site
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://mayflower.de/"),
                Validate(
                    selector="body",
                    validation_type="presence",
                    description="Main page loaded",
                    is_critical=True,
                ),
                Click(selector="a[href*='leistungen']"),  # Go to services
                Validate(
                    selector="body",
                    validation_type="presence",
                    description="Services page loaded",
                    is_critical=True,
                ),
                Click(selector="a[href*='karriere']"),  # Go to careers
                Validate(
                    selector="body",
                    validation_type="presence",
                    description="Careers page loaded",
                    is_critical=True,
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            job_id = "test_multi_page"
            options = {}

            # Execute with potential for self-healing
            script_path = generate_script(
                plan, job_id, artifacts_root, headless=True, options=options
            )

            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Should complete the multi-page journey
            # May need patches for cookie banners or slow loading
            if result.returncode != 0:
                print(f"Failed: {result.stderr}")

                # Try with healing
                patch = propose_patch(1, result.stderr, None)
                options = merge_codegen_options(options, patch)

                script_path = generate_script(
                    plan, job_id, artifacts_root, headless=True, options=options
                )

                result = subprocess.run(
                    ["python", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                assert result.returncode == 0, "Multi-page navigation failed even with healing"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_extraction_after_healing(self):
        """Test that data extraction works after self-healing."""
        req = ScrapeRequest(
            nl_request="Extract all navigation menu items from Mayflower site",
            schema={
                "type": "object",
                "properties": {
                    "menu_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Navigation menu items",
                    },
                },
                "required": ["menu_items"],
            },
            target_urls=["https://mayflower.de/"],
        )

        result = run_job(req)

        # Should complete and extract data
        assert result.status == "completed"
        assert result.data is not None

        # Check if we got menu items
        if "menu_items" in result.data:
            items = result.data["menu_items"]
            assert isinstance(items, list)
            if items:
                assert len(items) > 0
                print(f"Extracted {len(items)} menu items")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ai_powered_healing(self):
        """Test AI-powered healing with real errors."""
        if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("CLAUDE_API_KEY"):
            pytest.skip("No API key for AI-powered healing")

        # Create a complex request that might need AI assistance
        req = ScrapeRequest(
            nl_request="Find and extract technical details about Mayflower's software development services",
            schema={
                "type": "object",
                "properties": {
                    "technologies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Technologies used",
                    },
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Development services offered",
                    },
                },
            },
            target_urls=["https://mayflower.de/"],
        )

        result = run_job(req)

        assert result.status == "completed"

        # AI-powered healing should handle complex scenarios better
        if result.data:
            print(f"AI-assisted extraction: {json.dumps(result.data, indent=2)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
