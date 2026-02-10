"""Integration test: extract Ust-Id Nr from mayflower.de impressum."""

from __future__ import annotations

import os

import pytest

from scry.core.executor.runner import run_job_with_id


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
async def test_extract_ust_id_from_mayflower():
    """Extract the Ust-Id Nr (VAT ID) from mayflower.de."""
    from scry.api.dto import ScrapeRequest

    req = ScrapeRequest(
        nl_request=(
            "Find the Impressum or legal notice on the website and extract the Ust-Id Nr "
            "(German VAT identification number). It is usually in the Impressum page."
        ),
        output_schema={
            "type": "object",
            "properties": {
                "ust_id_nr": {
                    "type": "string",
                    "description": "The Ust-Id Nr (VAT ID), e.g. DE123456789",
                },
            },
        },
        target_urls=["https://mayflower.de/"],
    )

    result = await run_job_with_id("mayflower-ust-id-test", req)

    assert result.job_id == "mayflower-ust-id-test"
    assert result.data is not None
    ust_id = result.data.get("ust_id_nr", "")
    assert ust_id.startswith("DE"), f"Expected German VAT ID starting with DE, got: {ust_id}"
    print(f"Extracted Ust-Id Nr: {ust_id}")
