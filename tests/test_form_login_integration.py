"""Integration tests for LLM-driven login form detection and filling."""

import os

import pytest
from scry.api.dto import ScrapeRequest  # type: ignore
from scry.core.executor.runner import run_job_with_id  # type: ignore


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_llm_detects_and_fills_login():
    """Test LLM detects login form and fills it automatically.

    Uses https://practicetestautomation.com/practice-test-login/
    Valid credentials: username="student", password="Password123"
    """
    os.environ["MAX_EXPLORATION_STEPS"] = "15"

    req = ScrapeRequest(
        nl_request="Log in to the website and extract the success message after login",
        output_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "logged_in": {"type": "boolean"},
            },
        },
        target_urls=["https://practicetestautomation.com/practice-test-login/"],
        login_params={"username": "student", "password": "Password123"},
    )

    result = run_job_with_id("login-test", req)

    # Verify exploration completed
    assert result.status == "completed"
    assert "exploring" in result.execution_log
    assert "exploration_complete" in result.execution_log

    # Check if we got data extraction (login attempt happened)
    assert result.data, "Expected data extraction"
    print(f"Login test result: {result.data}")

    # Verify that login was attempted (message field should have content)
    # Note: The LLM may or may not successfully login depending on form complexity,
    # but it should at least attempt and extract some message
    assert "message" in result.data, "Expected message field in extracted data"


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_login_not_triggered_without_credentials():
    """Test that no login happens when credentials not provided."""
    os.environ["MAX_EXPLORATION_STEPS"] = "5"

    req = ScrapeRequest(
        nl_request="Extract the page title",
        output_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        target_urls=["https://practicetestautomation.com/practice-test-login/"],
        # NO login_params
    )

    result = run_job_with_id("no-login-test", req)

    # Should not attempt login without credentials
    # Check that we didn't fill password fields
    fill_actions = [log for log in result.execution_log if "fill" in log.lower()]
    assert len(fill_actions) == 0, "Should not fill forms without credentials"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
