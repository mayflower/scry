from __future__ import annotations

import pytest
from universal_scraper.api.dto import ScrapeRequest
from universal_scraper.core.executor.runner import run_v4_job


@pytest.mark.smoke
def test_example_com_baseline():
    req = ScrapeRequest(
        nl_request="Open and extract basic info",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "links": {"type": "array", "items": {"type": "string"}},
            },
        },
        target_urls=["https://example.com"],
    )
    res = run_v4_job(req)
    assert isinstance(res.data, dict)
    assert "title" in res.data

