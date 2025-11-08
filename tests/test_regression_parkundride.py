from __future__ import annotations

import os

import pytest
from universal_scraper.api.dto import ScrapeRequest
from universal_scraper.core.executor.runner import run_job


e2e = pytest.mark.e2e


@e2e
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="Requires ANTHROPIC_API_KEY for exploration and compression",
)
def test_parkundride_tiefgarage_moosach_free_places():
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

    res = run_job(req)

    assert isinstance(res.data, dict)
    assert "free_places" in res.data, f"data keys={list(res.data.keys())}"
    assert isinstance(res.data["free_places"], int)
    assert res.data["free_places"] >= 0

    # Ensure the validation step ran; if mismatch it should still be recorded
    assert any(flag in res.execution_log for flag in ("validation_ok", "validation_mismatch")), (
        res.execution_log
    )

    # Basic sanity on execution phases
    assert any(
        s in res.execution_log
        for s in ("exploring", "path_compressed", "codegen", "executing_script", "script_done")
    ), res.execution_log
