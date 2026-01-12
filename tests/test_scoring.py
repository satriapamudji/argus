"""Tests for the scoring module.

Tests cover:
- Heuristic scoring functions (recency, source tier, keywords, uniqueness, breaking)
- Topic detection
- Score breakdown and result generation
- ScoringConfig and SourceTiersConfig
"""

from datetime import datetime, timedelta, timezone

import pytest

from argus.config import ScoringConfig, SourceTiersConfig
from argus.scoring.heuristics import (
    HeuristicScorer,
    score_candidates,
)
from argus.scoring.types import (
    ScoreBreakdown,
    ScoringCandidate,
    ScoringResult,
    ScoringStats,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def default_config() -> ScoringConfig:
    """Default scoring config for tests."""
    return ScoringConfig()


@pytest.fixture
def scorer(default_config: ScoringConfig) -> HeuristicScorer:
    """Default scorer for tests."""
    return HeuristicScorer(default_config)


def make_candidate(
    news_item_id: int = 1,
    title: str = "Test news title",
    snippet: str | None = "Test snippet content",
    source_name: str = "Test Source",
    published_at: datetime | None = None,
    ingested_at: datetime | None = None,
    simhash: int | None = None,
) -> ScoringCandidate:
    """Helper to create test candidates."""
    now = datetime.now(timezone.utc)
    return ScoringCandidate(
        news_item_id=news_item_id,
        fingerprint_id=news_item_id,
        source_name=source_name,
        source_url=f"https://example.com/news/{news_item_id}",
        title=title,
        snippet=snippet,
        published_at=published_at or now,
        ingested_at=ingested_at or now,
        simhash=simhash,
    )


# =============================================================================
# SourceTiersConfig Tests
# =============================================================================


class TestSourceTiersConfig:
    """Tests for SourceTiersConfig."""

    def test_default_tiers(self):
        """Test default tier lists."""
        config = SourceTiersConfig()
        assert "Reuters" in config.tier_1
        assert "Bloomberg" in config.tier_1
        assert "CNBC" in config.tier_2
        assert "Yahoo Finance" in config.tier_3

    def test_tier_1_score(self):
        """Test tier 1 sources get 20 pts."""
        config = SourceTiersConfig()
        assert config.get_tier_score("Reuters") == 20
        assert config.get_tier_score("Bloomberg") == 20
        assert config.get_tier_score("WSJ") == 20

    def test_tier_2_score(self):
        """Test tier 2 sources get 15 pts."""
        config = SourceTiersConfig()
        assert config.get_tier_score("CNBC") == 15
        assert config.get_tier_score("Financial Times") == 15

    def test_tier_3_score(self):
        """Test tier 3 sources get 10 pts."""
        config = SourceTiersConfig()
        assert config.get_tier_score("Yahoo Finance") == 10
        assert config.get_tier_score("MarketWatch") == 10

    def test_unlisted_score(self):
        """Test unlisted sources get 5 pts."""
        config = SourceTiersConfig()
        assert config.get_tier_score("Unknown Blog") == 5
        assert config.get_tier_score("Random News Site") == 5

    def test_case_insensitive_matching(self):
        """Test case insensitive source matching."""
        config = SourceTiersConfig()
        assert config.get_tier_score("reuters") == 20
        assert config.get_tier_score("REUTERS") == 20
        assert config.get_tier_score("Reuters News") == 20

    def test_partial_matching(self):
        """Test partial source name matching."""
        config = SourceTiersConfig()
        # "Reuters" in "Reuters News"
        assert config.get_tier_score("Reuters News Wire") == 20


# =============================================================================
# ScoringConfig Tests
# =============================================================================


class TestScoringConfig:
    """Tests for ScoringConfig."""

    def test_defaults(self):
        """Test default configuration values."""
        config = ScoringConfig()
        assert config.enabled is True
        assert config.window_hours == 24
        assert config.max_items_per_run == 100
        assert config.scorer_version == "heuristic_v1"
        assert config.llm_triage_enabled is False

    def test_source_tiers_default(self):
        """Test source tiers are included."""
        config = ScoringConfig()
        assert isinstance(config.source_tiers, SourceTiersConfig)


# =============================================================================
# ScoreBreakdown Tests
# =============================================================================


class TestScoreBreakdown:
    """Tests for ScoreBreakdown dataclass."""

    def test_total_calculation(self):
        """Test total score calculation."""
        breakdown = ScoreBreakdown(
            recency=20,
            source_tier=15,
            keyword_relevance=25,
            uniqueness=10,
            breaking_urgency=8,
        )
        assert breakdown.total == 78

    def test_to_reasons(self):
        """Test reasons list generation."""
        breakdown = ScoreBreakdown(
            recency=20,
            source_tier=15,
            keyword_relevance=0,  # Zero shouldn't appear
            uniqueness=10,
            breaking_urgency=0,
        )
        reasons = breakdown.to_reasons()
        assert "recency: +20" in reasons
        assert "source_tier: +15" in reasons
        assert "uniqueness: +10" in reasons
        # Zero-value components should not appear
        assert not any("keywords" in r for r in reasons)
        assert not any("breaking" in r for r in reasons)

    def test_empty_breakdown(self):
        """Test breakdown with all zeros."""
        breakdown = ScoreBreakdown()
        assert breakdown.total == 0
        assert breakdown.to_reasons() == []


# =============================================================================
# Recency Scoring Tests
# =============================================================================


class TestRecencyScoring:
    """Tests for recency scoring."""

    def test_brand_new_item_max_score(self, scorer: HeuristicScorer):
        """Test brand new item gets max recency score."""
        candidate = make_candidate(published_at=scorer.reference_time)
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.recency == 25

    def test_old_item_low_score(self, scorer: HeuristicScorer):
        """Test 24h old item gets low recency score."""
        old_time = scorer.reference_time - timedelta(hours=24)
        candidate = make_candidate(published_at=old_time)
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.recency < 5  # Very low after 24h

    def test_6h_old_item_half_score(self, scorer: HeuristicScorer):
        """Test ~6h old item gets roughly half score (half-life)."""
        old_time = scorer.reference_time - timedelta(hours=6)
        candidate = make_candidate(published_at=old_time)
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        # Should be approximately 12-13 (half of 25)
        assert 10 <= result.breakdown.recency <= 15

    def test_future_item_max_score(self, scorer: HeuristicScorer):
        """Test future dated item (clock skew) gets max score."""
        future_time = scorer.reference_time + timedelta(hours=1)
        candidate = make_candidate(published_at=future_time)
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.recency == 25


# =============================================================================
# Source Tier Scoring Tests
# =============================================================================


class TestSourceTierScoring:
    """Tests for source tier scoring."""

    def test_tier_1_source(self, scorer: HeuristicScorer):
        """Test tier 1 source gets 20 pts."""
        candidate = make_candidate(source_name="Reuters")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.source_tier == 20

    def test_tier_2_source(self, scorer: HeuristicScorer):
        """Test tier 2 source gets 15 pts."""
        candidate = make_candidate(source_name="CNBC")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.source_tier == 15

    def test_tier_3_source(self, scorer: HeuristicScorer):
        """Test tier 3 source gets 10 pts."""
        candidate = make_candidate(source_name="Yahoo Finance")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.source_tier == 10

    def test_unlisted_source(self, scorer: HeuristicScorer):
        """Test unlisted source gets 5 pts."""
        candidate = make_candidate(source_name="Random Blog")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.source_tier == 5


# =============================================================================
# Keyword Scoring Tests
# =============================================================================


class TestKeywordScoring:
    """Tests for keyword relevance scoring."""

    def test_high_value_keywords(self, scorer: HeuristicScorer):
        """Test high-value keywords score higher."""
        # Use a high-value keyword
        candidate = make_candidate(title="Fed raises interest rates by 25 basis points")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.keyword_relevance >= 5  # At least one high-value match

    def test_multiple_keywords(self, scorer: HeuristicScorer):
        """Test multiple keywords accumulate score."""
        # Title with multiple keywords
        candidate = make_candidate(title="Fed raises rates as inflation hits CPI target, GDP grows")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.keyword_relevance >= 10

    def test_no_keywords(self, scorer: HeuristicScorer):
        """Test no market keywords gives low score."""
        candidate = make_candidate(title="Local bakery opens new location")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.keyword_relevance == 0

    def test_snippet_keywords_count(self, scorer: HeuristicScorer):
        """Test keywords in snippet are counted."""
        candidate = make_candidate(
            title="Breaking news", snippet="The Federal Reserve announced a rate hike today"
        )
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.keyword_relevance >= 5


# =============================================================================
# Uniqueness Scoring Tests
# =============================================================================


class TestUniquenessScoring:
    """Tests for uniqueness scoring via SimHash."""

    def test_no_recent_simhashes(self, scorer: HeuristicScorer):
        """Test moderate uniqueness score with no comparison."""
        candidate = make_candidate(simhash=12345)
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.uniqueness == 8  # Default when no comparison

    def test_unique_from_recent(self, scorer: HeuristicScorer):
        """Test high uniqueness when very different from recent."""
        scorer.set_recent_simhashes([0xFFFFFFFFFFFFFFFF])  # Very different
        candidate = make_candidate(simhash=0)  # All zeros
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.uniqueness >= 13  # High distance = high uniqueness

    def test_similar_to_recent(self, scorer: HeuristicScorer):
        """Test low uniqueness when similar to recent."""
        scorer.set_recent_simhashes([0b11111111])
        candidate = make_candidate(simhash=0b11111110)  # 1 bit different
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.uniqueness <= 3  # Low distance = low uniqueness

    def test_no_simhash(self, scorer: HeuristicScorer):
        """Test default score when candidate has no simhash."""
        scorer.set_recent_simhashes([12345, 67890])
        candidate = make_candidate(simhash=None)
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.uniqueness == 8  # Default


# =============================================================================
# Breaking/Urgency Scoring Tests
# =============================================================================


class TestBreakingScoring:
    """Tests for breaking/urgency scoring."""

    def test_breaking_keyword(self, scorer: HeuristicScorer):
        """Test 'breaking' in title gives max score."""
        candidate = make_candidate(title="BREAKING: Fed announces emergency rate cut")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.breaking_urgency == 10

    def test_urgent_keyword(self, scorer: HeuristicScorer):
        """Test 'urgent' in title gives max score."""
        candidate = make_candidate(title="URGENT: Market circuit breakers triggered")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.breaking_urgency == 10

    def test_exclusive_keyword(self, scorer: HeuristicScorer):
        """Test 'exclusive' in title gives max score."""
        candidate = make_candidate(title="EXCLUSIVE: CEO to resign amid scandal")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.breaking_urgency == 10

    def test_no_urgency(self, scorer: HeuristicScorer):
        """Test normal headline gives 0 breaking score."""
        candidate = make_candidate(title="Markets close higher on Wednesday")
        result = scorer.score_candidate(candidate)
        assert result.breakdown is not None
        assert result.breakdown.breaking_urgency == 0


# =============================================================================
# Topic Detection Tests
# =============================================================================


class TestTopicDetection:
    """Tests for topic detection."""

    def test_macro_topic(self, scorer: HeuristicScorer):
        """Test macro topic detection."""
        candidate = make_candidate(title="Fed raises interest rates by 25 basis points")
        result = scorer.score_candidate(candidate)
        assert result.topic == "macro"

    def test_earnings_topic(self, scorer: HeuristicScorer):
        """Test earnings topic detection."""
        candidate = make_candidate(title="Apple beats Q3 earnings estimates")
        result = scorer.score_candidate(candidate)
        assert result.topic == "earnings"

    def test_geopolitics_topic(self, scorer: HeuristicScorer):
        """Test geopolitics topic detection."""
        candidate = make_candidate(title="New sanctions imposed on Russia")
        result = scorer.score_candidate(candidate)
        assert result.topic == "geopolitics"

    def test_markets_topic(self, scorer: HeuristicScorer):
        """Test markets topic detection."""
        candidate = make_candidate(title="S&P 500 hits all-time high")
        result = scorer.score_candidate(candidate)
        assert result.topic == "markets"

    def test_crypto_topic(self, scorer: HeuristicScorer):
        """Test crypto topic detection."""
        candidate = make_candidate(title="Ethereum blockchain upgrade completed successfully")
        result = scorer.score_candidate(candidate)
        assert result.topic == "crypto"

    def test_commodities_topic(self, scorer: HeuristicScorer):
        """Test commodities topic detection."""
        candidate = make_candidate(title="WTI crude oil falls below 70 dollars per barrel")
        result = scorer.score_candidate(candidate)
        assert result.topic == "commodities"

    def test_no_topic(self, scorer: HeuristicScorer):
        """Test no topic for generic content."""
        candidate = make_candidate(title="Cat stuck in tree rescued by firefighters")
        result = scorer.score_candidate(candidate)
        assert result.topic is None


# =============================================================================
# Flag Detection Tests
# =============================================================================


class TestFlagDetection:
    """Tests for flag detection."""

    def test_breaking_flag(self, scorer: HeuristicScorer):
        """Test breaking flag detection."""
        candidate = make_candidate(title="BREAKING: Major announcement")
        result = scorer.score_candidate(candidate)
        assert "breaking" in result.flags

    def test_exclusive_flag(self, scorer: HeuristicScorer):
        """Test exclusive flag detection."""
        candidate = make_candidate(title="EXCLUSIVE: Insider report")
        result = scorer.score_candidate(candidate)
        assert "exclusive" in result.flags

    def test_market_moving_flag(self, scorer: HeuristicScorer):
        """Test market_moving flag detection."""
        candidate = make_candidate(title="Fed announces rate decision")
        result = scorer.score_candidate(candidate)
        assert "market_moving" in result.flags

    def test_earnings_flag(self, scorer: HeuristicScorer):
        """Test earnings flag detection."""
        candidate = make_candidate(title="Company beats earnings expectations")
        result = scorer.score_candidate(candidate)
        assert "earnings" in result.flags


# =============================================================================
# ScoringResult Tests
# =============================================================================


class TestScoringResult:
    """Tests for ScoringResult."""

    def test_from_breakdown(self):
        """Test creating ScoringResult from breakdown."""
        candidate = make_candidate()
        breakdown = ScoreBreakdown(
            recency=20,
            source_tier=15,
            keyword_relevance=25,
            uniqueness=10,
            breaking_urgency=8,
        )

        result = ScoringResult.from_breakdown(
            candidate=candidate,
            breakdown=breakdown,
            topic="macro",
            flags=["breaking"],
        )

        assert result.news_item_id == candidate.news_item_id
        assert result.impact_score == 78  # Sum of breakdown
        assert result.topic == "macro"
        assert "breaking" in result.flags
        assert len(result.reasons) > 0

    def test_quality_score_calculation(self):
        """Test quality score based on signal count."""
        candidate = make_candidate()
        # All signals present
        breakdown = ScoreBreakdown(
            recency=20,
            source_tier=15,
            keyword_relevance=25,
            uniqueness=10,
            breaking_urgency=8,
        )

        result = ScoringResult.from_breakdown(
            candidate=candidate,
            breakdown=breakdown,
            topic="macro",
            flags=[],
        )

        # 5 signals * 20 = 100 (capped)
        assert result.quality_score == 100


# =============================================================================
# ScoringStats Tests
# =============================================================================


class TestScoringStats:
    """Tests for ScoringStats."""

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = ScoringStats(total_candidates=100, scored=90, errors=10)
        assert stats.success_rate == 90.0

    def test_success_rate_zero_candidates(self):
        """Test success rate with zero candidates."""
        stats = ScoringStats(total_candidates=0, scored=0)
        assert stats.success_rate == 0.0


# =============================================================================
# Batch Scoring Tests
# =============================================================================


class TestBatchScoring:
    """Tests for batch scoring function."""

    def test_score_candidates_sorted(self, default_config: ScoringConfig):
        """Test candidates are sorted by score descending."""
        candidates = [
            make_candidate(news_item_id=1, title="Local news"),
            make_candidate(news_item_id=2, title="BREAKING: Fed raises rates"),
            make_candidate(news_item_id=3, title="Weather update"),
        ]

        results = score_candidates(candidates, default_config)

        # Item 2 should be first (breaking + fed keywords)
        assert results[0].news_item_id == 2
        assert results[0].impact_score >= results[1].impact_score
        assert results[1].impact_score >= results[2].impact_score

    def test_score_candidates_with_simhashes(self, default_config: ScoringConfig):
        """Test scoring with recent SimHashes for uniqueness."""
        candidates = [
            make_candidate(news_item_id=1, simhash=0),
            make_candidate(news_item_id=2, simhash=0xFFFFFFFF),
        ]

        results = score_candidates(
            candidates,
            default_config,
            recent_simhashes=[0b11111111],
        )

        # Both should have uniqueness scores calculated
        assert all(r.breakdown is not None for r in results)


# =============================================================================
# Integration Tests
# =============================================================================


class TestScoringIntegration:
    """Integration tests for the scoring pipeline."""

    def test_full_scoring_pipeline(self, default_config: ScoringConfig):
        """Test complete scoring of a realistic news item."""
        candidate = make_candidate(
            news_item_id=1,
            source_name="Reuters",  # Tier 1
            title="BREAKING: Fed raises interest rates by 50 basis points",
            snippet="The Federal Reserve announced a larger than expected rate hike amid inflation concerns.",
            simhash=12345,
        )

        scorer = HeuristicScorer(default_config)
        result = scorer.score_candidate(candidate)

        # Should have high score due to:
        # - Tier 1 source (20 pts)
        # - Breaking keyword (10 pts)
        # - Fed/rates keywords (high value)
        # - Good recency
        assert result.impact_score >= 50
        assert result.topic == "macro"
        assert "breaking" in result.flags
        assert "market_moving" in result.flags
        assert result.breakdown is not None
        assert result.breakdown.source_tier == 20
        assert result.breakdown.breaking_urgency == 10

    def test_low_value_item(self, default_config: ScoringConfig):
        """Test scoring of a low-value news item."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        candidate = make_candidate(
            news_item_id=2,
            source_name="Unknown Blog",  # Unlisted
            title="My thoughts on the weather today",
            snippet="It's sunny outside.",
            published_at=old_time,
            simhash=99999,
        )

        scorer = HeuristicScorer(default_config)
        result = scorer.score_candidate(candidate)

        # Should have low score
        assert result.impact_score < 20
        assert result.topic is None
        assert result.flags == []
