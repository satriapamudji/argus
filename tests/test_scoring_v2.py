"""Tests for the heuristic_v2 scoring module.

Tests cover:
- Domain-based tier scoring
- Author/provider penalties
- Nasdaq template penalties
- Macro catalyst boosting
- Clickbait/listicle penalties
- Preview vs outcome distinction
- Template deduplication
"""

from datetime import datetime, timezone

import pytest

from argus.config import ScoringConfig
from argus.scoring.heuristics_v2 import (
    _get_author_penalty,
    _get_domain_tier_score,
    score_candidates_v2,
)
from argus.scoring.types import ScoringCandidate


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def default_config() -> ScoringConfig:
    """Default scoring config for tests."""
    return ScoringConfig()


def make_candidate(
    news_item_id: int = 1,
    title: str = "Test news title",
    snippet: str | None = "Test snippet content",
    source_name: str = "Test Source",
    published_at: datetime | None = None,
    ingested_at: datetime | None = None,
    simhash: int | None = None,
    feed_url: str | None = None,
    author: str | None = None,
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
        feed_url=feed_url,
        author=author,
    )


# =============================================================================
# Domain Tier Scoring Tests
# =============================================================================


class TestDomainTierScoring:
    """Tests for domain-based tier scoring."""

    def test_tier_1_domain(self):
        """Test tier 1 domains get 20 pts."""
        assert _get_domain_tier_score("reuters.com") == 20
        assert _get_domain_tier_score("bloomberg.com") == 20
        assert _get_domain_tier_score("wsj.com") == 20
        assert _get_domain_tier_score("ft.com") == 20

    def test_tier_2_domain(self):
        """Test tier 2 domains get 15 pts."""
        assert _get_domain_tier_score("cnbc.com") == 15
        assert _get_domain_tier_score("marketwatch.com") == 15
        assert _get_domain_tier_score("barrons.com") == 15

    def test_tier_3_domain(self):
        """Test tier 3 domains get 10 pts."""
        assert _get_domain_tier_score("yahoo.com") == 10
        assert _get_domain_tier_score("nasdaq.com") == 10
        assert _get_domain_tier_score("investing.com") == 10

    def test_unlisted_domain(self):
        """Test unlisted domains get 5 pts."""
        assert _get_domain_tier_score("randomnews.com") == 5
        assert _get_domain_tier_score("unknown.org") == 5

    def test_none_domain(self):
        """Test None domain returns default 5 pts."""
        assert _get_domain_tier_score(None) == 5

    def test_case_insensitive(self):
        """Test domain matching is case insensitive."""
        assert _get_domain_tier_score("REUTERS.COM") == 20
        assert _get_domain_tier_score("Reuters.Com") == 20


# =============================================================================
# Author Penalty Tests
# =============================================================================


class TestAuthorPenalty:
    """Tests for author/provider penalties."""

    def test_motley_fool_penalty(self):
        """Test Motley Fool author gets penalty."""
        penalty, key = _get_author_penalty("The Motley Fool")
        assert penalty == 25
        assert key == "the motley fool"

    def test_marketbeat_penalty(self):
        """Test MarketBeat author gets penalty."""
        penalty, key = _get_author_penalty("MarketBeat Staff")
        assert penalty == 20
        assert key == "marketbeat"

    def test_rttnews_penalty(self):
        """Test RTTNews author gets penalty."""
        penalty, key = _get_author_penalty("RTTNews")
        assert penalty == 12
        assert key == "rttnews"

    def test_zacks_penalty(self):
        """Test Zacks author gets penalty."""
        penalty, key = _get_author_penalty("Zacks Investment Research")
        assert penalty == 15
        assert key == "zacks"

    def test_no_penalty_for_unknown(self):
        """Test unknown authors get no penalty."""
        penalty, key = _get_author_penalty("John Smith")
        assert penalty == 0
        assert key is None

    def test_no_penalty_for_none(self):
        """Test None author gets no penalty."""
        penalty, key = _get_author_penalty(None)
        assert penalty == 0
        assert key is None

    def test_case_insensitive(self):
        """Test author matching is case insensitive."""
        penalty, _ = _get_author_penalty("THE MOTLEY FOOL")
        assert penalty == 25


# =============================================================================
# V2 Scoring Integration Tests
# =============================================================================


class TestV2ScoringIntegration:
    """Integration tests for v2 scoring."""

    def test_macro_content_boosted(self, default_config: ScoringConfig):
        """Test macro content (Fed/CPI/jobs) gets boosted."""
        candidates = [
            make_candidate(
                news_item_id=1,
                title="Fed raises interest rates by 25 basis points, signals more hikes ahead",
            ),
            make_candidate(
                news_item_id=2,
                title="Local bakery opens new location downtown",
            ),
        ]

        results = score_candidates_v2(candidates, default_config)

        # Macro content should rank higher
        assert results[0].news_item_id == 1
        assert results[0].impact_score > results[1].impact_score

    def test_clickbait_penalized(self, default_config: ScoringConfig):
        """Test clickbait content gets penalized."""
        candidates = [
            make_candidate(
                news_item_id=1,
                title="5 Best Stocks To Buy Now Before They Triple",
            ),
            make_candidate(
                news_item_id=2,
                title="Markets close higher on positive earnings reports",
            ),
        ]

        results = score_candidates_v2(candidates, default_config)

        # Clickbait should rank lower despite catchy title
        clickbait_result = next(r for r in results if r.news_item_id == 1)
        normal_result = next(r for r in results if r.news_item_id == 2)

        assert any("v2_penalty:clickbait" in flag for flag in clickbait_result.flags)
        assert clickbait_result.impact_score < normal_result.impact_score

    def test_pundit_content_penalized(self, default_config: ScoringConfig):
        """Test pundit content (Cramer/Motley Fool) gets penalized."""
        candidate = make_candidate(
            news_item_id=1,
            title="Jim Cramer says buy this stock now",
        )

        results = score_candidates_v2([candidate], default_config)

        assert any("v2_penalty:clickbait:pundit" in flag for flag in results[0].flags)

    def test_author_penalty_applied(self, default_config: ScoringConfig):
        """Test author penalties are applied."""
        candidate = make_candidate(
            news_item_id=1,
            title="Why This Stock Could Double",
            author="The Motley Fool",
        )

        results = score_candidates_v2([candidate], default_config)

        assert any("v2_penalty:author:" in flag for flag in results[0].flags)

    def test_outcome_boosted_over_preview(self, default_config: ScoringConfig):
        """Test outcome news boosted over preview/preview news."""
        candidates = [
            make_candidate(
                news_item_id=1,
                title="Fed expected to raise rates next week",  # Preview
            ),
            make_candidate(
                news_item_id=2,
                title="Fed raised rates by 25 basis points today",  # Outcome
            ),
        ]

        results = score_candidates_v2(candidates, default_config)

        outcome = next(r for r in results if r.news_item_id == 2)
        preview = next(r for r in results if r.news_item_id == 1)

        # Outcome should have boost flag, preview should have penalty
        assert any("v2_boost:outcome" in flag for flag in outcome.flags)
        assert any("v2_penalty:preview" in flag for flag in preview.flags)

    def test_listicle_year_false_positive_avoided(self, default_config: ScoringConfig):
        """Test that years like 2026 don't trigger listicle penalty."""
        candidate = make_candidate(
            news_item_id=1,
            title="Fed policy outlook for 2026 remains uncertain",
        )

        results = score_candidates_v2([candidate], default_config)

        # Should NOT have listicle penalty
        assert not any("listicle" in flag for flag in results[0].flags)

    def test_template_market_today_capped(self, default_config: ScoringConfig):
        """Test Stock Market Today templates are capped."""
        candidate = make_candidate(
            news_item_id=1,
            title="Stock Market Today: Dow rises 200 points",
        )

        results = score_candidates_v2([candidate], default_config)

        assert any("v2_template:market_today" in flag for flag in results[0].flags)
        # Score should be capped at 52
        assert results[0].impact_score <= 52

    def test_duplicate_market_today_crushed(self, default_config: ScoringConfig):
        """Test duplicate Stock Market Today templates get crushed."""
        candidates = [
            make_candidate(
                news_item_id=1,
                title="Stock Market Today: Dow rises 200 points",
            ),
            make_candidate(
                news_item_id=2,
                title="Stock Market Today: S&P 500 closes higher",
            ),
            make_candidate(
                news_item_id=3,
                title="Stock Market Today: Nasdaq leads gains",
            ),
        ]

        results = score_candidates_v2(candidates, default_config)

        # First should keep score, others should have dup penalty
        market_today_results = [r for r in results if "v2_template:market_today" in r.flags]
        dup_results = [
            r for r in market_today_results if "v2_penalty:template_market_today_dup" in r.flags
        ]

        assert len(dup_results) == 2  # 2 of 3 should be crushed

    def test_nasdaq_template_penalized(self, default_config: ScoringConfig):
        """Test Nasdaq template patterns get penalized."""
        candidates = [
            make_candidate(
                news_item_id=1,
                title="ETF Inflow Alert: SPY sees big inflows today",
            ),
            make_candidate(
                news_item_id=2,
                title="AAPL breaks above 200-day moving average",
            ),
            make_candidate(
                news_item_id=3,
                title="Noteworthy TSLA Option Activity detected",
            ),
        ]

        results = score_candidates_v2(candidates, default_config)

        for result in results:
            assert any("v2_penalty:nasdaq_template" in flag for flag in result.flags)

    def test_speculation_blocks_outcome_boost(self, default_config: ScoringConfig):
        """Test that speculation markers block outcome boost."""
        candidate = make_candidate(
            news_item_id=1,
            title="Rate-cut hopes rise as Fed expected to pause hikes",
        )

        results = score_candidates_v2([candidate], default_config)

        # Should NOT have outcome boost due to speculation markers
        assert not any("v2_boost:outcome" in flag for flag in results[0].flags)

    def test_trade_deficit_boosted(self, default_config: ScoringConfig):
        """Test trade deficit/balance terms get macro boost."""
        candidate = make_candidate(
            news_item_id=1,
            title="US trade deficit widens to $80 billion in March",
        )

        results = score_candidates_v2([candidate], default_config)

        # Should have higher score due to macro keyword boost
        assert results[0].impact_score > 30  # Has macro boost

    def test_scorer_version_set(self, default_config: ScoringConfig):
        """Test scorer_version is set to heuristic_v2."""
        candidate = make_candidate(news_item_id=1, title="Test headline")

        results = score_candidates_v2([candidate], default_config)

        assert results[0].scorer_version == "heuristic_v2"

    def test_results_sorted_by_score(self, default_config: ScoringConfig):
        """Test results are sorted by impact_score descending."""
        candidates = [
            make_candidate(news_item_id=1, title="Low value local news"),
            make_candidate(
                news_item_id=2,
                title="BREAKING: Fed announces emergency rate cut",
            ),
            make_candidate(news_item_id=3, title="Weather forecast for today"),
        ]

        results = score_candidates_v2(candidates, default_config)

        # Should be sorted descending
        scores = [r.impact_score for r in results]
        assert scores == sorted(scores, reverse=True)

        # Fed news should be first
        assert results[0].news_item_id == 2
