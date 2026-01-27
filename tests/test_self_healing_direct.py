"""Direct integration tests for self-healing system.

These tests bypass native exploration and directly test the self-healing
mechanism with generated Playwright scripts against mayflower.de.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from scry.core.codegen.generator import generate_script
from scry.core.ir.model import (
    Click,
    Navigate,
    ScrapePlan,
    Validate,
)
from scry.core.self_heal.diagnose import propose_patch
from scry.core.self_heal.patch import merge_codegen_options


class TestDirectSelfHealing:
    """Test self-healing directly with generated scripts."""

    @pytest.mark.integration
    def test_basic_navigation_mayflower(self):
        """Test basic navigation to mayflower.de."""
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://mayflower.de/"),
                Validate(
                    selector="body",
                    validation_type="presence",
                    description="Check page loaded",
                    is_critical=True,
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            job_id = "test_basic_nav"

            # Generate and run script
            script_path = generate_script(plan, job_id, artifacts_root, headless=True, options={})

            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should complete successfully
            assert result.returncode == 0, f"Navigation failed: {result.stderr}"

    @pytest.mark.integration
    def test_validation_failure_recovery(self):
        """Test recovery from a validation that might fail."""
        # This selector intentionally might not exist
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://mayflower.de/"),
                Validate(
                    selector=".non-existent-element-12345",
                    validation_type="presence",
                    description="Check for element that likely doesn't exist",
                    is_critical=True,
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            job_id = "test_validation_fail"

            # First attempt - should fail
            script_path = generate_script(plan, job_id, artifacts_root, headless=True, options={})

            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should fail with exit code 1
            assert result.returncode == 1, "Expected validation to fail"
            assert (
                "CRITICAL validation failed" in result.stdout
                or "CRITICAL validation failed" in result.stderr
            )

            # Now test the recovery would work with a better selector
            plan_fixed = ScrapePlan(
                steps=[
                    Navigate(url="https://mayflower.de/"),
                    Validate(
                        selector="body",  # This should exist
                        validation_type="presence",
                        description="Check page loaded",
                        is_critical=True,
                    ),
                ],
            )

            script_path = generate_script(
                plan_fixed, job_id + "_fixed", artifacts_root, headless=True, options={}
            )

            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should succeed now
            assert result.returncode == 0

    @pytest.mark.integration
    def test_cookie_banner_handling(self):
        """Test cookie banner handling on mayflower.de."""
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://mayflower.de/"),
                # Try to interact with page content
                Click(selector="a"),  # Click first link
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            job_id = "test_cookie"

            # First try without cookie handling
            options = {"handle_cookie_banner": False}
            script_path = generate_script(
                plan, job_id, artifacts_root, headless=True, options=options
            )

            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            first_attempt_code = result.returncode

            # Now try with cookie handling
            options = {"handle_cookie_banner": True}
            script_path = generate_script(
                plan,
                job_id + "_with_cookie",
                artifacts_root,
                headless=True,
                options=options,
            )

            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # At least one should succeed
            assert first_attempt_code == 0 or result.returncode == 0, (
                "Both attempts failed - cookie handling may be needed"
            )

    @pytest.mark.integration
    def test_progressive_patches(self):
        """Test that progressive patches work."""
        plan = ScrapePlan(
            steps=[
                Navigate(url="https://mayflower.de/"),
                Validate(
                    selector="main",
                    validation_type="presence",
                    description="Check main content",
                    is_critical=True,
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            job_id = "test_progressive"

            max_attempts = 3
            options = {}

            for attempt in range(1, max_attempts + 1):
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

                # Apply patch for next attempt
                patch = propose_patch(attempt, result.stderr, None)
                options = merge_codegen_options(options, patch)

                # Verify patches are getting more aggressive
                if attempt == 1:
                    assert "wait_load_state" in patch
                elif attempt >= 2:
                    assert "handle_cookie_banner" in patch

    @pytest.mark.integration
    def test_extract_data_from_mayflower(self):
        """Test actual data extraction from mayflower.de."""
        # Create a simple extraction script
        script_content = """
from playwright.sync_api import sync_playwright
import json
import sys

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Navigate to site
            page.goto("https://mayflower.de/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Extract some basic data
            data = {}

            # Try to get page title
            try:
                data["title"] = page.title()
            except Exception:
                data["title"] = None

            # Try to get main heading
            try:
                h1 = page.query_selector("h1")
                if h1:
                    data["heading"] = h1.text_content()
            except Exception:
                data["heading"] = None

            # Try to find company name
            try:
                # Look for "Mayflower" in the page
                if "mayflower" in page.content().lower():
                    data["company_found"] = True
                else:
                    data["company_found"] = False
            except Exception:
                data["company_found"] = False

            print(json.dumps(data, indent=2))

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "extract.py"
            script_path.write_text(script_content)

            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should complete successfully
            assert result.returncode == 0, f"Extraction failed: {result.stderr}"

            # Should have extracted some data
            import json

            data = json.loads(result.stdout)
            assert data.get("company_found") is True, "Should find Mayflower in page"
            assert data.get("title") is not None, "Should extract page title"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-k", "test_basic"])
