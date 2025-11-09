"""Integration tests for LLM-driven login form detection and filling."""

import os

import pytest
from universal_scraper.api.dto import ScrapeRequest  # type: ignore
from universal_scraper.core.executor.runner import run_job_with_id  # type: ignore


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

    # Verify login flow executed
    assert result.status == "completed"

    # Should have filled username and password fields
    assert any("fill" in log.lower() for log in result.execution_log), (
        "Expected Fill actions for username/password"
    )

    # Should have clicked submit button
    assert any("click" in log.lower() for log in result.execution_log), (
        "Expected Click action for login button"
    )

    # Check if we got post-login content
    assert result.data, "Expected data extraction after login"
    print(f"Login test result: {result.data}")


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
