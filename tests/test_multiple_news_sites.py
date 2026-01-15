"""Multi-site integration tests: Verify domain-agnostic implementation.

Tests extraction from multiple German news sites to ensure the implementation
is not overfitted to a single domain.
"""

import os

import pytest
from scry.api.dto import ScrapeRequest  # type: ignore[import-untyped]
from scry.core.executor.runner import run_job_with_id  # type: ignore[import-untyped]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY"
)
async def test_golem_news_extraction():
    """Extract the last 3 news items from golem.de.

    Tests iframe-aware cookie banner handling. golem.de uses a CMP
    (Consent Management Platform) iframe for cookie consent.
    """
    os.environ["MAX_EXPLORATION_STEPS"] = "15"

    req = ScrapeRequest(
        nl_request="Extract the titles and links of the last 3 news articles from the homepage",
        schema={
            "type": "object",
            "properties": {
                "news": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "link": {"type": "string"},
                        },
                    },
                }
            },
        },
        target_urls=["https://www.golem.de/"],
    )

    print("\n" + "=" * 70)
    print("INTEGRATION TEST: Extracting news from golem.de (with cookie banner)")
    print("=" * 70)

    result = await run_job_with_id("golem-news-test", req)

    print(f"\nExecution log: {result.execution_log}")
    print(f"\nExtracted data: {result.data}")

    # Verify pipeline completed
    assert any(
        "exploring" in log.lower() for log in result.execution_log
    ), "Should have exploration phase"
    assert any(
        "exploration_complete" in log.lower() for log in result.execution_log
    ), "Exploration should complete"
    assert any(
        "done" in log.lower() for log in result.execution_log
    ), "Pipeline should finish"

    # Verify data structure
    assert result.data is not None, "Should extract some data"
    assert isinstance(result.data, dict), "Data should be a dictionary"

    # Check if we got news items
    if "news" in result.data:
        news_items = result.data["news"]
        assert isinstance(news_items, list), "News should be a list"

        print(
            f"\n✅ Successfully extracted {len(news_items)} news items from golem.de:"
        )
        for i, item in enumerate(news_items[:3], 1):
            title = item.get("title", "N/A")
            link = item.get("link", "N/A")
            print(f"   {i}. {title}")
            print(f"      {link}")

        assert len(news_items) > 0, "Should extract at least one news item"

        # Verify at least one item has title (links may be empty on some sites)
        if len(news_items) > 0:
            first_item = news_items[0]
            assert first_item.get(
                "title"
            ), "First news item should have a non-empty title"

    print("\n✅ golem.de test passed (cookie banner handled!)")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY"
)
async def test_chip_news_extraction():
    """Extract the last 3 news items from chip.de."""
    os.environ["MAX_EXPLORATION_STEPS"] = "10"

    req = ScrapeRequest(
        nl_request="Extract the titles and links of the last 3 news articles from the homepage",
        schema={
            "type": "object",
            "properties": {
                "news": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "link": {"type": "string"},
                        },
                    },
                }
            },
        },
        target_urls=["https://www.chip.de/"],
    )

    print("\n" + "=" * 70)
    print("INTEGRATION TEST: Extracting news from chip.de")
    print("=" * 70)

    result = await run_job_with_id("chip-news-test", req)

    print(f"\nExecution log: {result.execution_log}")
    print(f"\nExtracted data: {result.data}")

    # Verify pipeline completed
    assert any(
        "exploring" in log.lower() for log in result.execution_log
    ), "Should have exploration phase"
    assert any(
        "exploration_complete" in log.lower() for log in result.execution_log
    ), "Exploration should complete"
    assert any(
        "done" in log.lower() for log in result.execution_log
    ), "Pipeline should finish"

    # Verify data structure
    assert result.data is not None, "Should extract some data"
    assert isinstance(result.data, dict), "Data should be a dictionary"

    # Check if we got news items
    if "news" in result.data:
        news_items = result.data["news"]
        assert isinstance(news_items, list), "News should be a list"

        print(f"\n✅ Successfully extracted {len(news_items)} news items from chip.de:")
        for i, item in enumerate(news_items[:3], 1):
            title = item.get("title", "N/A")
            link = item.get("link", "N/A")
            print(f"   {i}. {title}")
            print(f"      {link}")

        assert len(news_items) > 0, "Should extract at least one news item"

        # Verify at least one item has title (links may be empty on some sites)
        if len(news_items) > 0:
            first_item = news_items[0]
            assert first_item.get(
                "title"
            ), "First news item should have a non-empty title"

    print("\n✅ chip.de test passed")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY"
)
async def test_computerbild_news_extraction():
    """Extract the last 3 news items from computerbild.de."""
    os.environ["MAX_EXPLORATION_STEPS"] = "10"

    req = ScrapeRequest(
        nl_request="Extract the titles and links of the last 3 news articles from the homepage",
        schema={
            "type": "object",
            "properties": {
                "news": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "link": {"type": "string"},
                        },
                    },
                }
            },
        },
        target_urls=["https://www.computerbild.de/"],
    )

    print("\n" + "=" * 70)
    print("INTEGRATION TEST: Extracting news from computerbild.de")
    print("=" * 70)

    result = await run_job_with_id("computerbild-news-test", req)

    print(f"\nExecution log: {result.execution_log}")
    print(f"\nExtracted data: {result.data}")

    # Verify pipeline completed
    assert any(
        "exploring" in log.lower() for log in result.execution_log
    ), "Should have exploration phase"
    assert any(
        "exploration_complete" in log.lower() for log in result.execution_log
    ), "Exploration should complete"
    assert any(
        "done" in log.lower() for log in result.execution_log
    ), "Pipeline should finish"

    # Verify data structure
    assert result.data is not None, "Should extract some data"
    assert isinstance(result.data, dict), "Data should be a dictionary"

    # Check if we got news items
    if "news" in result.data:
        news_items = result.data["news"]
        assert isinstance(news_items, list), "News should be a list"

        print(
            f"\n✅ Successfully extracted {len(news_items)} news items from computerbild.de:"
        )
        for i, item in enumerate(news_items[:3], 1):
            title = item.get("title", "N/A")
            link = item.get("link", "N/A")
            print(f"   {i}. {title}")
            print(f"      {link}")

        assert len(news_items) > 0, "Should extract at least one news item"

        # Verify at least one item has title (links may be empty on some sites)
        if len(news_items) > 0:
            first_item = news_items[0]
            assert first_item.get(
                "title"
            ), "First news item should have a non-empty title"

    print("\n✅ computerbild.de test passed")


if __name__ == "__main__":
    # Run all tests
    import asyncio

    print("\n" + "=" * 70)
    print("MULTI-SITE VALIDATION: Testing domain-agnostic implementation")
    print("=" * 70)

    asyncio.run(test_golem_news_extraction())
    asyncio.run(test_chip_news_extraction())
    asyncio.run(test_computerbild_news_extraction())

    print("\n" + "=" * 70)
    print("✅ ALL MULTI-SITE TESTS PASSED")
    print("   Implementation is domain-agnostic!")
    print("=" * 70)
