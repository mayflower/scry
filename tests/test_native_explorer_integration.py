"""Fast integration test to verify native explorer actually works in the pipeline."""

import os

import pytest
from scry.api.dto import ScrapeRequest
from scry.core.executor.runner import run_job_with_id


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_native_explorer_minimal_integration():
    """Minimal test: Does the pipeline actually work with native explorer?

    This is a REAL test - no mocks, actual browser, actual LLM.
    Uses a data URL to avoid network issues.
    """
    # Set very low limits for speed
    os.environ["MAX_EXPLORATION_STEPS"] = "1"

    # Simple HTML that doesn't require navigation
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1 id="main-title">Hello World</h1>
        <p>This is a test page.</p>
    </body>
    </html>
    """

    # Use data URL to avoid network
    import urllib.parse

    data_url = f"data:text/html,{urllib.parse.quote(html)}"

    req = ScrapeRequest(
        nl_request="Extract the h1 heading text",
        output_schema={"type": "object", "properties": {"heading": {"type": "string"}}},
        target_urls=[data_url],
    )

    # This is the real test - does it complete without crashing?
    result = run_job_with_id("native-explorer-test", req)

    # Verify pipeline ran
    assert result.job_id == "native-explorer-test"
    assert "exploring" in result.execution_log
    assert "exploration_complete" in result.execution_log

    # Should have completed something (may or may not have correct data with data URLs)
    assert "done" in result.execution_log

    print("\n✅ NATIVE EXPLORER INTEGRATION VERIFIED")
    print(f"   Execution log: {result.execution_log}")
    print(f"   Data: {result.data}")

    return True


if __name__ == "__main__":
    # Run directly for quick testing
    if test_native_explorer_minimal_integration():
        print("\n✅ INTEGRATION TEST PASSED - Native explorer works!")
