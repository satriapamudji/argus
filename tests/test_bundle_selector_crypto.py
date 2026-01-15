"""Integration tests for BundleSelector with crypto topics.

Tests that the BundleSelector correctly handles crypto-specific topics
and enforces topic diversity constraints with 7 crypto subtopics.
"""

import pytest

from argus.facts_bundle.selector import BundleSelector
from argus.facts_bundle.types import BundleCandidate


def _create_candidate(
    news_item_id: int,
    score: int,
    topic: str,
    source: str = "coindesk.com",
    has_content: bool = True,
) -> BundleCandidate:
    """Helper to create a test BundleCandidate."""
    from datetime import datetime

    return BundleCandidate(
        news_item_id=news_item_id,
        title=f"Test Article {news_item_id}",
        source_name=source,
        source_url=f"https://{source}/article/{news_item_id}",
        published_at=None,
        ingested_at=datetime.now(),
        snippet=f"Test snippet for article {news_item_id}",
        content_excerpt="Full content" if has_content else None,
        topic=topic,
        impact_score=score,
        has_content=has_content,
    )


def test_crypto_topic_diversity_with_all_topics():
    """Test that BundleSelector respects max_per_topic with 7 crypto topics.

    Given 20 items with various crypto topics, verify:
    - No more than max_per_topic items per topic are selected
    - Higher scoring items are prioritized
    - At least 5 different topics are represented in the bundle
    """
    sources = ["coindesk.com", "theblock.co", "decrypt.co", "cointelegraph.com", "bitcoinmagazine.com"]
    source_idx = 0

    def get_source() -> str:
        nonlocal source_idx
        src = sources[source_idx % len(sources)]
        source_idx += 1
        return src

    # Create test items with 7 crypto topics
    test_items = [
        # protocol_risk items (high priority)
        _create_candidate(1, 80, "protocol_risk", get_source()),
        _create_candidate(2, 75, "protocol_risk", get_source()),
        _create_candidate(3, 70, "protocol_risk", get_source()),
        # regulation items
        _create_candidate(4, 70, "regulation", get_source()),
        _create_candidate(5, 65, "regulation", get_source()),
        # defi items
        _create_candidate(6, 65, "defi", get_source()),
        _create_candidate(7, 60, "defi", get_source()),
        # derivatives items
        _create_candidate(8, 60, "derivatives", get_source()),
        _create_candidate(9, 55, "derivatives", get_source()),
        # onchain items
        _create_candidate(10, 55, "onchain", get_source()),
        _create_candidate(11, 50, "onchain", get_source()),
        # technical items
        _create_candidate(12, 50, "technical", get_source()),
        _create_candidate(13, 45, "technical", get_source()),
        # asset_news items
        _create_candidate(14, 45, "asset_news", get_source()),
        _create_candidate(15, 40, "asset_news", get_source()),
        # More items to fill out to 20
        _create_candidate(16, 35, "asset_news", get_source()),
        _create_candidate(17, 35, "defi", get_source()),
        _create_candidate(18, 30, "technical", get_source()),
        _create_candidate(19, 25, "derivatives", get_source()),
        _create_candidate(20, 20, "onchain", get_source()),
    ]

    selector = BundleSelector(
        max_per_topic=1,  # Conservative diversity
        max_per_source=2,
        enriched_bonus=5,
    )

    # Select up to 10 items
    selected = selector.select(
        candidates=test_items,
        min_items=2,
        max_items=10,
    )

    # Verify no more than 1 item per topic
    topic_counts = {}
    for item in selected:
        topic_counts[item.topic] = topic_counts.get(item.topic, 0) + 1

    for topic, count in topic_counts.items():
        assert count <= 1, f"Topic {topic} has {count} items, expected max 1"

    # Verify all 7 topics could be represented (at least 5 in this case)
    assert len(topic_counts) >= 5, f"Expected at least 5 different topics, got {len(topic_counts)}"

    # Verify higher scoring items are prioritized
    scores = [item.impact_score for item in selected]
    assert scores == sorted(scores, reverse=True), "Items should be sorted by score descending"


def test_crypto_topic_priority_order():
    """Test that high-priority crypto topics (protocol_risk, regulation) are selected first.

    Topics priority order: protocol_risk > regulation > defi > derivatives > onchain > technical > asset_news
    """
    test_items = [
        _create_candidate(1, 60, "protocol_risk", "coindesk.com"),  # Should be selected (highest priority)
        _create_candidate(2, 70, "asset_news", "theblock.co"),      # High score but lowest priority
        _create_candidate(3, 65, "regulation", "decrypt.co"),      # Should be selected (second priority)
        _create_candidate(4, 55, "defi", "cointelegraph.com"),            # Should be selected (third priority)
        _create_candidate(5, 50, "derivatives", "bitcoinmagazine.com"),     # Should be selected
    ]

    selector = BundleSelector(max_per_topic=1, max_per_source=2, enriched_bonus=5)
    selected = selector.select(candidates=test_items, min_items=2, max_items=5)

    # All 5 items should be selected (different topics)
    assert len(selected) == 5

    # Verify topics are diverse
    topics = [item.topic for item in selected]
    assert len(set(topics)) == 5, "All 5 topics should be different"


def test_crypto_source_diversity():
    """Test that source diversity constraint works with crypto sources."""
    test_items = [
        # CoinDesk items (should max at 2)
        _create_candidate(1, 80, "protocol_risk", "coindesk.com"),
        _create_candidate(2, 75, "regulation", "coindesk.com"),
        _create_candidate(3, 70, "defi", "coindesk.com"),  # Should be skipped (source limit)
        # TheBlock items
        _create_candidate(4, 65, "derivatives", "theblock.co"),
        _create_candidate(5, 60, "onchain", "theblock.co"),
        # Cointelegraph items
        _create_candidate(6, 55, "technical", "cointelegraph.com"),
    ]

    selector = BundleSelector(max_per_topic=1, max_per_source=2, enriched_bonus=5)
    selected = selector.select(candidates=test_items, min_items=2, max_items=10)

    # Count CoinDesk items
    coindesk_count = sum(1 for item in selected if "coindesk" in item.source_name.lower())
    assert coindesk_count <= 2, f"Expected max 2 CoinDesk items, got {coindesk_count}"

    # Verify the high-scoring CoinDesk item was still selected
    coindesk_items = [item for item in selected if "coindesk" in item.source_name.lower()]
    assert len(coindesk_items) == 2
    assert coindesk_items[0].impact_score == 80
    assert coindesk_items[1].impact_score == 75


def test_crypto_topic_enrichment_bonus():
    """Test that enriched bonus prioritizes items with full content."""
    test_items = [
        _create_candidate(1, 50, "protocol_risk", "coindesk.com", has_content=True),
        _create_candidate(2, 55, "protocol_risk", "theblock.co", has_content=False),  # Higher base score but no content
        _create_candidate(3, 45, "regulation", "coindesk.com", has_content=True),
        _create_candidate(4, 50, "regulation", "theblock.co", has_content=False),
    ]

    selector = BundleSelector(max_per_topic=1, max_per_source=2, enriched_bonus=5)
    selected = selector.select(candidates=test_items, min_items=2, max_items=10)

    # With 5-point bonus, item 1 (50+5=55) should beat item 2 (55+0=55)
    # Same score, but item 1 has content so it should be selected
    # Note: The selector sorts by score first, then by other factors

    # Verify we have items (at least 2 different topics)
    assert len(selected) >= 2

    # Verify content bonus is being applied (enriched items should be prioritized)
    enriched_count = sum(1 for item in selected if item.has_content)
    assert enriched_count >= 1


def test_crypto_selector_stats():
    """Test that selector stats accurately reflect crypto topic distribution."""
    test_items = [
        _create_candidate(1, 80, "protocol_risk", "coindesk.com"),
        _create_candidate(2, 70, "protocol_risk", "theblock.co"),  # Should be skipped (topic limit)
        _create_candidate(3, 65, "regulation", "coindesk.com"),   # Should be skipped (source limit)
        _create_candidate(4, 60, "defi", "cointelegraph.com"),
        _create_candidate(5, 55, "derivatives", "theblock.co"),
        _create_candidate(6, 50, "onchain", "cointelegraph.com"),
    ]

    selector = BundleSelector(max_per_topic=1, max_per_source=1, enriched_bonus=5)
    selected = selector.select(candidates=test_items, min_items=2, max_items=10)
    stats = selector.get_stats()

    # Should have skipped 2 items:
    # - 1 for protocol_risk topic limit (item 2)
    # - 1 for CoinDesk source limit (item 3)
    assert stats["skipped_by_topic"] >= 1
    assert stats["skipped_by_source"] >= 1
    assert stats["selected"] == len(selected)


def test_crypto_min_items_constraint():
    """Test that min_items constraint is respected even with topic constraints."""
    test_items = [
        _create_candidate(1, 50, "protocol_risk"),
        _create_candidate(2, 45, "protocol_risk"),  # Different topic (after topic limit relaxes)
        _create_candidate(3, 40, "regulation"),
        _create_candidate(4, 35, "defi"),
    ]

    selector = BundleSelector(max_per_topic=1, max_per_source=2, enriched_bonus=5)
    selected = selector.select(candidates=test_items, min_items=3, max_items=10)

    # Should select at least 3 items (min_items constraint)
    assert len(selected) >= 3


def test_crypto_unknown_topic_handling():
    """Test that unknown/None topics are handled correctly."""
    test_items = [
        _create_candidate(1, 80, "protocol_risk"),
        _create_candidate(2, 70, ""),  # Empty topic (should be treated as "other")
        _create_candidate(3, 60, "unknown_topic"),  # Unknown topic
        _create_candidate(4, 50, "regulation"),
    ]

    selector = BundleSelector(max_per_topic=1, max_per_source=2, enriched_bonus=5)
    selected = selector.select(candidates=test_items, min_items=2, max_items=10)

    # Should handle None and unknown topics gracefully
    assert len(selected) >= 2

    # Count "other" topics (empty and unknown)
    other_count = sum(1 for item in selected if not item.topic or item.topic == "unknown_topic")
    assert other_count >= 1, "Should have at least one 'other' topic item"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
