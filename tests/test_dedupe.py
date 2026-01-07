"""Tests for near-duplicate detection and topic diversity.

Tests cover:
- SimHash computation and Hamming distance
- Topic labeling with heuristic rules
- Diversity helpers for facts bundle selection
"""

import pytest

from argus.dedupe.simhash import (
    compute_simhash,
    hamming_distance,
    is_near_duplicate,
    tokenize,
)
from argus.dedupe.topics import (
    TopicLabel,
    label_topic,
    get_topic_priority,
)
from argus.dedupe.diversity import (
    DiversityChecker,
    NewsItemForDiversity,
    compute_diversity_score,
    enforce_topic_diversity,
    rank_by_topic_priority,
    select_diverse_items_with_fallback,
)


# =============================================================================
# SimHash Tests
# =============================================================================


class TestTokenize:
    """Tests for tokenize function."""

    def test_basic_tokenization(self):
        """Test basic trigram tokenization."""
        tokens = tokenize("hello world")
        assert "hel" in tokens
        assert "ell" in tokens
        assert "wor" in tokens

    def test_short_text(self):
        """Test text shorter than ngram size."""
        tokens = tokenize("hi")
        assert tokens == ["hi"]

    def test_empty_text(self):
        """Test empty text."""
        tokens = tokenize("")
        assert tokens == []

    def test_whitespace_normalization(self):
        """Test whitespace is normalized."""
        tokens = tokenize("hello   world")
        # Multiple spaces become single space
        assert "o w" in tokens

    def test_punctuation_removal(self):
        """Test punctuation is removed."""
        tokens = tokenize("hello, world!")
        # Punctuation should be stripped
        assert "llo" in tokens  # No comma
        assert "rld" in tokens  # No exclamation

    def test_case_insensitive(self):
        """Test lowercase normalization."""
        tokens1 = tokenize("HELLO")
        tokens2 = tokenize("hello")
        assert tokens1 == tokens2

    def test_custom_ngram_size(self):
        """Test custom ngram size."""
        tokens = tokenize("hello", ngram_size=2)
        assert "he" in tokens
        assert "el" in tokens


class TestComputeSimhash:
    """Tests for compute_simhash function."""

    def test_basic_simhash(self):
        """Test basic SimHash computation."""
        h = compute_simhash("hello world")
        assert isinstance(h, int)
        assert h >= 0

    def test_empty_text(self):
        """Test empty text returns 0."""
        assert compute_simhash("") == 0

    def test_similar_texts_have_similar_hashes(self):
        """Test similar texts produce similar hashes."""
        h1 = compute_simhash("The Federal Reserve raised interest rates today")
        h2 = compute_simhash("The Federal Reserve increased interest rates today")

        # Should be more similar than completely different texts
        # (character-level SimHash may have higher distance than word-level)
        distance = hamming_distance(h1, h2)
        assert distance <= 20  # Allow reasonable variation for trigram-based SimHash

    def test_different_texts_have_different_hashes(self):
        """Test different texts produce different hashes."""
        h1 = compute_simhash("The Federal Reserve raised interest rates")
        h2 = compute_simhash("Bitcoin crashed 50% overnight in massive selloff")

        # Should be different (high Hamming distance)
        distance = hamming_distance(h1, h2)
        assert distance > 15

    def test_deterministic(self):
        """Test same text always produces same hash."""
        text = "Test text for determinism"
        h1 = compute_simhash(text)
        h2 = compute_simhash(text)
        assert h1 == h2


class TestHammingDistance:
    """Tests for hamming_distance function."""

    def test_identical_hashes(self):
        """Test identical hashes have distance 0."""
        assert hamming_distance(0, 0) == 0
        assert hamming_distance(123456, 123456) == 0

    def test_one_bit_difference(self):
        """Test one bit difference."""
        assert hamming_distance(0b0000, 0b0001) == 1
        assert hamming_distance(0b1000, 0b0000) == 1

    def test_all_bits_different(self):
        """Test all 64 bits different."""
        # All 1s XOR all 0s = 64 bits different
        assert hamming_distance(0xFFFFFFFFFFFFFFFF, 0) == 64

    def test_known_distance(self):
        """Test known Hamming distance."""
        # 0b1010 XOR 0b0101 = 0b1111 = 4 bits
        assert hamming_distance(0b1010, 0b0101) == 4


class TestIsNearDuplicate:
    """Tests for is_near_duplicate function."""

    def test_identical_is_duplicate(self):
        """Test identical hashes are duplicates."""
        assert is_near_duplicate(12345, 12345, threshold=4)

    def test_within_threshold(self):
        """Test hashes within threshold are duplicates."""
        h1 = 0b11111111
        h2 = 0b11111110  # 1 bit different
        assert is_near_duplicate(h1, h2, threshold=4)

    def test_at_threshold(self):
        """Test hashes exactly at threshold are duplicates."""
        h1 = 0b11111111
        h2 = 0b11110000  # 4 bits different
        assert is_near_duplicate(h1, h2, threshold=4)

    def test_above_threshold(self):
        """Test hashes above threshold are not duplicates."""
        h1 = 0b11111111
        h2 = 0b11100000  # 5 bits different
        assert not is_near_duplicate(h1, h2, threshold=4)


# =============================================================================
# Topic Label Tests
# =============================================================================


class TestLabelTopic:
    """Tests for label_topic function."""

    def test_macro_keywords(self):
        """Test macro topic keywords."""
        assert label_topic("Fed raises interest rates by 25 basis points") == TopicLabel.MACRO
        assert label_topic("FOMC meeting minutes released") == TopicLabel.MACRO
        assert label_topic("Inflation hits 40-year high at 8.5%") == TopicLabel.MACRO
        assert label_topic("CPI report shows cooling inflation") == TopicLabel.MACRO
        assert label_topic("Jobs report shows strong hiring") == TopicLabel.MACRO
        assert label_topic("GDP growth slows to 1.5%") == TopicLabel.MACRO

    def test_earnings_keywords(self):
        """Test earnings topic keywords."""
        assert label_topic("Apple beats earnings estimates") == TopicLabel.EARNINGS
        assert label_topic("Microsoft reports Q3 2024 revenue growth") == TopicLabel.EARNINGS
        assert label_topic("Company issues lower guidance for next quarter") == TopicLabel.EARNINGS

    def test_geopolitics_keywords(self):
        """Test geopolitics topic keywords."""
        assert label_topic("Russia-Ukraine war escalates") == TopicLabel.GEOPOLITICS
        assert label_topic("New sanctions imposed on Russia") == TopicLabel.GEOPOLITICS
        assert label_topic("China-Taiwan tensions rise") == TopicLabel.GEOPOLITICS
        assert label_topic("NATO announces new defense measures") == TopicLabel.GEOPOLITICS

    def test_policy_keywords(self):
        """Test policy topic keywords."""
        assert label_topic("SEC announces new crypto regulations") == TopicLabel.POLICY
        assert label_topic("Congress passes new tax bill") == TopicLabel.POLICY
        assert label_topic("Antitrust investigation into Big Tech") == TopicLabel.POLICY

    def test_credit_keywords(self):
        """Test credit topic keywords."""
        assert label_topic("Credit spreads widen amid uncertainty") == TopicLabel.CREDIT
        assert label_topic("Company files for bankruptcy protection") == TopicLabel.CREDIT
        assert label_topic("Moodys downgrade of corporate bonds") == TopicLabel.CREDIT

    def test_commodities_keywords(self):
        """Test commodities topic keywords."""
        assert label_topic("Oil prices surge on OPEC cuts") == TopicLabel.COMMODITIES
        assert label_topic("Gold hits record high amid uncertainty") == TopicLabel.COMMODITIES
        assert label_topic("WTI crude falls below $70") == TopicLabel.COMMODITIES

    def test_crypto_keywords(self):
        """Test crypto topic keywords."""
        assert label_topic("Bitcoin crashes 20% overnight") == TopicLabel.CRYPTO
        assert label_topic("Ethereum merge complete") == TopicLabel.CRYPTO
        assert label_topic("Stablecoin depegs from dollar") == TopicLabel.CRYPTO

    def test_tech_keywords(self):
        """Test tech topic keywords."""
        assert label_topic("Apple announces new iPhone") == TopicLabel.TECH
        assert label_topic("Nvidia AI chips in high demand") == TopicLabel.TECH
        assert label_topic("Tech sector leads market rally") == TopicLabel.TECH

    def test_equities_keywords(self):
        """Test equities topic keywords."""
        assert label_topic("S&P 500 hits all-time high") == TopicLabel.EQUITIES
        assert label_topic("Nasdaq enters bear market") == TopicLabel.EQUITIES
        assert label_topic("Stocks rally on economic data") == TopicLabel.EQUITIES

    def test_snippet_matching(self):
        """Test matching in snippet, not title."""
        assert (
            label_topic("Breaking news", snippet="The Federal Reserve is expected to raise rates")
            == TopicLabel.MACRO
        )

    def test_unknown_returns_other(self):
        """Test unmatched text returns OTHER."""
        assert label_topic("Random news about nothing specific") == TopicLabel.OTHER

    def test_first_match_wins(self):
        """Test first matching topic wins when multiple could match."""
        # "Fed" should match MACRO before any other topic
        result = label_topic("Fed announces policy change affecting stocks")
        assert result == TopicLabel.MACRO


class TestGetTopicPriority:
    """Tests for get_topic_priority function."""

    def test_returns_dict(self):
        """Test returns dict with all topics."""
        priorities = get_topic_priority()
        assert isinstance(priorities, dict)
        for topic in TopicLabel:
            assert topic in priorities

    def test_macro_highest_priority(self):
        """Test macro has highest priority."""
        priorities = get_topic_priority()
        assert priorities[TopicLabel.MACRO] == max(priorities.values())

    def test_other_lowest_priority(self):
        """Test other has lowest priority."""
        priorities = get_topic_priority()
        assert priorities[TopicLabel.OTHER] == min(priorities.values())


# =============================================================================
# Diversity Helper Tests
# =============================================================================


def make_item(id: int, topic: TopicLabel, score: float) -> NewsItemForDiversity:
    """Helper to create test items."""
    return NewsItemForDiversity(id=id, topic=topic, score=score)


class TestDiversityChecker:
    """Tests for DiversityChecker class."""

    def test_can_add_first_item(self):
        """Test can add first item."""
        checker = DiversityChecker(max_per_topic=1)
        item = make_item(1, TopicLabel.MACRO, 90.0)
        assert checker.can_add(item)

    def test_cannot_add_duplicate_topic(self):
        """Test cannot add second item of same topic."""
        checker = DiversityChecker(max_per_topic=1)
        item1 = make_item(1, TopicLabel.MACRO, 90.0)
        item2 = make_item(2, TopicLabel.MACRO, 80.0)

        checker.add(item1)
        assert not checker.can_add(item2)

    def test_can_add_different_topics(self):
        """Test can add items with different topics."""
        checker = DiversityChecker(max_per_topic=1)
        item1 = make_item(1, TopicLabel.MACRO, 90.0)
        item2 = make_item(2, TopicLabel.EARNINGS, 80.0)

        checker.add(item1)
        assert checker.can_add(item2)

    def test_max_per_topic_respects_limit(self):
        """Test max_per_topic allows multiple items."""
        checker = DiversityChecker(max_per_topic=2)
        item1 = make_item(1, TopicLabel.MACRO, 90.0)
        item2 = make_item(2, TopicLabel.MACRO, 80.0)
        item3 = make_item(3, TopicLabel.MACRO, 70.0)

        assert checker.add(item1)
        assert checker.add(item2)
        assert not checker.add(item3)  # Third rejected

    def test_cannot_add_same_id_twice(self):
        """Test cannot add same item ID twice."""
        checker = DiversityChecker(max_per_topic=2)
        item = make_item(1, TopicLabel.MACRO, 90.0)

        assert checker.add(item)
        assert not checker.can_add(item)

    def test_reset_clears_state(self):
        """Test reset clears all state."""
        checker = DiversityChecker(max_per_topic=1)
        item = make_item(1, TopicLabel.MACRO, 90.0)

        checker.add(item)
        checker.reset()

        assert checker.can_add(item)
        assert checker.get_topic_counts() == {}
        assert checker.get_selected_ids() == set()

    def test_get_topic_counts(self):
        """Test get_topic_counts returns correct counts."""
        checker = DiversityChecker(max_per_topic=2)
        checker.add(make_item(1, TopicLabel.MACRO, 90.0))
        checker.add(make_item(2, TopicLabel.MACRO, 80.0))
        checker.add(make_item(3, TopicLabel.EARNINGS, 70.0))

        counts = checker.get_topic_counts()
        assert counts[TopicLabel.MACRO] == 2
        assert counts[TopicLabel.EARNINGS] == 1

    def test_get_selected_ids(self):
        """Test get_selected_ids returns correct IDs."""
        checker = DiversityChecker(max_per_topic=1)
        checker.add(make_item(1, TopicLabel.MACRO, 90.0))
        checker.add(make_item(2, TopicLabel.EARNINGS, 80.0))

        ids = checker.get_selected_ids()
        assert ids == {1, 2}


class TestEnforceTopicDiversity:
    """Tests for enforce_topic_diversity function."""

    def test_selects_highest_scoring(self):
        """Test selects highest scoring items."""
        items = [
            make_item(1, TopicLabel.MACRO, 90.0),
            make_item(2, TopicLabel.EARNINGS, 80.0),
            make_item(3, TopicLabel.GEOPOLITICS, 70.0),
        ]

        selected = enforce_topic_diversity(items, max_items=2, max_per_topic=1)
        assert len(selected) == 2
        assert selected[0].id == 1
        assert selected[1].id == 2

    def test_enforces_diversity(self):
        """Test enforces max_per_topic."""
        items = [
            make_item(1, TopicLabel.MACRO, 100.0),
            make_item(2, TopicLabel.MACRO, 90.0),  # Same topic, skipped
            make_item(3, TopicLabel.EARNINGS, 80.0),
        ]

        selected = enforce_topic_diversity(items, max_items=2, max_per_topic=1)
        assert len(selected) == 2
        assert selected[0].id == 1
        assert selected[1].id == 3  # Item 2 skipped due to diversity

    def test_min_score_filter(self):
        """Test min_score filter works."""
        items = [
            make_item(1, TopicLabel.MACRO, 90.0),
            make_item(2, TopicLabel.EARNINGS, 50.0),  # Below threshold
        ]

        selected = enforce_topic_diversity(items, max_items=2, min_score=60.0)
        assert len(selected) == 1
        assert selected[0].id == 1

    def test_max_items_limit(self):
        """Test max_items limit is respected."""
        # Use valid TopicLabel values in rotation
        topics = [
            TopicLabel.MACRO,
            TopicLabel.EARNINGS,
            TopicLabel.GEOPOLITICS,
            TopicLabel.POLICY,
            TopicLabel.CREDIT,
        ]
        items = [make_item(i, topics[i % len(topics)], float(100 - i)) for i in range(10)]

        selected = enforce_topic_diversity(items, max_items=3, max_per_topic=5)
        assert len(selected) <= 3


class TestSelectDiverseItemsWithFallback:
    """Tests for select_diverse_items_with_fallback function."""

    def test_uses_strict_diversity_when_possible(self):
        """Test uses strict diversity when enough unique topics."""
        items = [
            make_item(1, TopicLabel.MACRO, 90.0),
            make_item(2, TopicLabel.EARNINGS, 80.0),
            make_item(3, TopicLabel.GEOPOLITICS, 70.0),
        ]

        selected = select_diverse_items_with_fallback(
            items, max_items=3, max_per_topic=1, fallback_max_per_topic=2
        )
        assert len(selected) == 3

    def test_falls_back_when_needed(self):
        """Test falls back to relaxed constraint when needed."""
        items = [
            make_item(1, TopicLabel.MACRO, 90.0),
            make_item(2, TopicLabel.MACRO, 80.0),  # Same topic
        ]

        selected = select_diverse_items_with_fallback(
            items, max_items=2, max_per_topic=1, fallback_max_per_topic=2
        )
        # Should get both items via fallback
        assert len(selected) == 2


class TestComputeDiversityScore:
    """Tests for compute_diversity_score function."""

    def test_empty_list(self):
        """Test empty list returns 0."""
        assert compute_diversity_score([]) == 0.0

    def test_perfect_diversity(self):
        """Test all unique topics = 1.0."""
        items = [
            make_item(1, TopicLabel.MACRO, 90.0),
            make_item(2, TopicLabel.EARNINGS, 80.0),
            make_item(3, TopicLabel.GEOPOLITICS, 70.0),
        ]
        assert compute_diversity_score(items) == 1.0

    def test_no_diversity(self):
        """Test all same topic < 1.0."""
        items = [
            make_item(1, TopicLabel.MACRO, 90.0),
            make_item(2, TopicLabel.MACRO, 80.0),
            make_item(3, TopicLabel.MACRO, 70.0),
        ]
        assert compute_diversity_score(items) == pytest.approx(1 / 3)

    def test_partial_diversity(self):
        """Test partial diversity score."""
        items = [
            make_item(1, TopicLabel.MACRO, 90.0),
            make_item(2, TopicLabel.MACRO, 80.0),
            make_item(3, TopicLabel.EARNINGS, 70.0),
            make_item(4, TopicLabel.EARNINGS, 60.0),
        ]
        # 2 unique topics / 4 items = 0.5
        assert compute_diversity_score(items) == 0.5


class TestRankByTopicPriority:
    """Tests for rank_by_topic_priority function."""

    def test_ranks_by_priority(self):
        """Test items ranked by topic priority."""
        items = [
            make_item(1, TopicLabel.OTHER, 90.0),  # Lowest priority
            make_item(2, TopicLabel.MACRO, 80.0),  # Highest priority
            make_item(3, TopicLabel.CRYPTO, 70.0),  # Middle priority
        ]

        ranked = rank_by_topic_priority(items)
        assert ranked[0].topic == TopicLabel.MACRO
        assert ranked[-1].topic == TopicLabel.OTHER

    def test_preserves_items(self):
        """Test all items preserved in ranking."""
        items = [make_item(i, TopicLabel.MACRO, float(i)) for i in range(5)]
        ranked = rank_by_topic_priority(items)
        assert len(ranked) == len(items)
