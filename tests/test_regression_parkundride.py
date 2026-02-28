"""Regression test for Park+Ride website extraction.

This is an e2e test that contacts a real website. It can fail due to:
- Website layout changes
- Network issues
- LLM exploration variance

The test verifies the pipeline works correctly, with lenient data assertions.
"""

from __future__ import annotations

import os

import pytest

from scry.api.dto import ScrapeRequest
from scry.core.executor.runner import run_job

e2e = pytest.mark.e2e


@e2e
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="Requires ANTHROPIC_API_KEY for exploration and compression",
)
async def test_parkundride_tiefgarage_moosach_free_places():
    """Test extraction from parkundride.de.

    This test verifies the full pipeline runs correctly on a real website.
    Data extraction assertions are lenient since websites can change.
    """
    # Give the explorer more steps for complex navigation
    os.environ["MAX_EXPLORATION_STEPS"] = "15"

    req = ScrapeRequest(
        nl_request="Using https://www.parkundride.de/, find the current number of free spaces at Tiefgarage Moosach.",
        parameters={"facility": "Tiefgarage Moosach"},
        schema={
            "type": "object",
            "properties": {
                "facility": {"type": "string"},
                "free_places": {"type": "integer"},
            },
        },
        target_urls=["https://www.parkundride.de/"],
    )

    res = await run_job(req)

    # --- Pipeline assertions (must pass) ---
    assert res.status == "completed", f"Job should complete, got: {res.status}"
    assert isinstance(res.data, dict), "Data should be a dict"

    # Check that core pipeline phases ran
    log_str = " ".join(res.execution_log)
    assert "exploring" in log_str, "Should have exploration phase"
    assert "exploration_complete" in log_str, "Exploration should complete"

    # Either codegen ran OR we used exploration data (both are valid outcomes)
    assert "codegen" in log_str or "using_exploration_data" in log_str, (
        f"Should have codegen or fallback to exploration data. Log: {res.execution_log}"
    )

    # Pipeline should finish
    assert "done" in log_str, f"Pipeline should finish. Log: {res.execution_log}"

    # --- Data assertions (lenient - website can change) ---
    # Check if we got meaningful data (not just internal fields)
    user_data_keys = [k for k in res.data if not k.startswith("_")]

    if "free_places" in res.data:
        # Best case: we extracted the expected data
        assert isinstance(res.data["free_places"], int), "free_places should be int"
        assert res.data["free_places"] >= 0, "free_places should be non-negative"
        print(f"✅ Extracted free_places: {res.data['free_places']}")
    elif user_data_keys:
        # Acceptable: we extracted some data (website may have changed)
        print(f"⚠️ Got different data than expected: {user_data_keys}")
        print(f"   Data: {res.data}")
    else:
        # Website may have changed significantly - log but don't fail hard
        # This allows the test to pass if the pipeline worked but website changed
        print("⚠️ No user data extracted. Website may have changed.")
        print(f"   Internal data: {res.data}")
        # Only fail if we didn't even get through the pipeline
        assert "validation_ok" in log_str or "using_exploration_data" in log_str, (
            f"Pipeline should complete successfully. Log: {res.execution_log}"
        )

    print("\n✅ Pipeline completed successfully")
    print(f"   Execution phases: {len(res.execution_log)} steps")
