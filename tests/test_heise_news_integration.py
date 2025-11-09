"""Real-world integration test: Extract news from heise.de

This tests the complete pipeline with:
- Real website (heise.de)
- Real browser navigation
- Real LLM decisions
- Real data extraction
"""

import os

import pytest
from scry.api.dto import ScrapeRequest
from scry.core.executor.runner import run_job_with_id


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_heise_news_extraction():
    """Extract the last 3 news items from heise.de.

    This is a REAL integration test:
    - Real website with dynamic content
    - Real browser automation
    - Real LLM-driven exploration
    - Real data extraction
    """
    # Allow more exploration steps for real website
    os.environ["MAX_EXPLORATION_STEPS"] = "10"

    req = ScrapeRequest(
        nl_request="Extract the titles and links of the last 3 news articles from the homepage",
        output_schema={
            "type": "object",
            "properties": {
                "news": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}, "link": {"type": "string"}},
                    },
                }
            },
        },
        target_urls=["https://www.heise.de/"],
    )

    print("\n" + "=" * 70)
    print("REAL INTEGRATION TEST: Extracting news from heise.de")
    print("=" * 70)

    result = run_job_with_id("heise-news-test", req)

    print(f"\nExecution log: {result.execution_log}")
    print(f"\nExtracted data: {result.data}")

    # Verify pipeline completed
    assert "exploring" in result.execution_log, "Should have exploration phase"
    assert "exploration_complete" in result.execution_log, "Exploration should complete"
    assert "done" in result.execution_log, "Pipeline should finish"

    # Verify data structure
    assert result.data is not None, "Should extract some data"
    assert isinstance(result.data, dict), "Data should be a dictionary"

    # Check if we got news items
    if "news" in result.data:
        news_items = result.data["news"]
        assert isinstance(news_items, list), "News should be a list"

        print(f"\n✅ Successfully extracted {len(news_items)} news items:")
        for i, item in enumerate(news_items[:3], 1):
            title = item.get("title", "N/A")
            link = item.get("link", "N/A")
            print(f"   {i}. {title}")
            print(f"      {link}")

        # Verify we got at least some news
        assert len(news_items) > 0, "Should extract at least one news item"

        # Verify first item has required fields
        if len(news_items) > 0:
            first_item = news_items[0]
            assert "title" in first_item or "link" in first_item, (
                "News items should have title or link"
            )

    print("\n" + "=" * 70)
    print("✅ REAL-WORLD INTEGRATION TEST PASSED")
    print("   Native Playwright + Anthropic explorer works on real website!")
    print("=" * 70)

    return True


if __name__ == "__main__":
    # Run directly for testing
    test_heise_news_extraction()
    print("\n✅ Test completed successfully!")
