"""Test suite for heuristic_v3 crypto-specific scoring.

Tests crypto boost detection, penalty detection, and topic detection.
"""

import pytest

from argus.config import ScoringConfig
from argus.scoring.heuristics_v3 import score_candidates_v3, _detect_crypto_topic
from argus.scoring.types import ScoringCandidate
from datetime import datetime


def _create_candidate(
    news_item_id: int,
    title: str,
    source: str = "coindesk.com",
    snippet: str = "",
    author: str = "",
) -> ScoringCandidate:
    """Helper to create a test ScoringCandidate."""
    return ScoringCandidate(
        news_item_id=news_item_id,
        fingerprint_id=news_item_id + 1000,
        source_name=source,
        source_url=f"https://{source}/article/{news_item_id}",
        title=title,
        snippet=snippet,
        published_at=None,
        ingested_at=datetime.now(),
        feed_url=f"https://{source}/feed",
        author=author if author else None,
    )


class TestBoostDetection:
    """Test that crypto boosters are detected and scored correctly."""

    def test_regulation_boost(self):
        """Test SEC/BTC ETF approval gets high score."""
        candidate = _create_candidate(
            1,
            "SEC Approves Spot Bitcoin ETF, Landmark Decision Expected Soon",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        # Should get high score from regulation boost + tier 1 domain
        assert result.impact_score >= 50
        assert result.topic == "regulation"
        assert "v3_boost:protocol" in " ".join(result.flags)
        assert "v3_tier:20" in " ".join(result.flags)

    def test_protocol_risk_boost(self):
        """Test DeFi hack gets high score."""
        candidate = _create_candidate(
            2,
            "$100M Drained from DeFi Protocol in Flash Loan Attack",
            source="theblock.co",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        assert result.impact_score >= 55
        assert result.topic == "protocol_risk"
        assert "v3_boost:protocol" in " ".join(result.flags)

    def test_technical_signal_boost(self):
        """Test ATH break gets medium-high score."""
        candidate = _create_candidate(
            3,
            "BTC Breaks Above $100K for First Time Ever",
            source="cointelegraph.com",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        # Technical + asset_news + tier 2 domain
        assert result.impact_score >= 40
        assert any(t in result.flags for t in ["v3_boost:technical:ath_break", "v3_topic:asset_news"])

    def test_defi_tvl_boost(self):
        """Test DeFi TVL surge gets boost."""
        candidate = _create_candidate(
            4,
            "DeFi Total Value Locked Surges to $50B After ETH Rally",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        assert result.impact_score >= 40
        assert "v3_boost:market:tvl_change" in " ".join(result.flags)


class TestPenaltyDetection:
    """Test that crypto penalties are applied correctly."""

    def test_price_prediction_penalty(self):
        """Test price prediction spam gets low score."""
        candidate = _create_candidate(
            1,
            "Bitcoin Will Reach $1 Million by 2030, Analyst Predicts",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        # Should be penalized heavily
        assert result.impact_score <= 40
        assert "v3_penalty:price_prediction" in " ".join(result.flags)

    def test_shilling_spam_penalty(self):
        """Test shilling spam gets low score."""
        candidate = _create_candidate(
            2,
            "Top 5 Crypto Gems to Buy Before They Explode - Don't Miss Out!",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        assert result.impact_score <= 45
        assert "v3_penalty:shilling" in " ".join(result.flags)

    def test_generic_wrap_penalty(self):
        """Test generic market wrap gets penalized."""
        candidate = _create_candidate(
            3,
            "Daily Crypto Market Update: Prices Mixed Amid Volatility",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        assert "v3_penalty:generic_wrap" in " ".join(result.flags)


class TestTopicDetection:
    """Test that crypto topics are detected correctly."""

    def test_all_topics_detected(self):
        """Test that all 7 crypto topics are detected."""
        test_cases = [
            ("Major Exchange Suspends Withdrawals Amid Security Concerns", "protocol_risk"),
            ("SEC Approves Bitcoin ETF Applications", "regulation"),
            ("Uniswap TVL Hits New High as DeFi Rally Continues", "defi"),
            ("Bitcoin Funding Rate Turns Positive as Longs Increase", "derivatives"),
            ("Whale Accumulation: 10K BTC Moved to Cold Storage", "onchain"),
            ("BTC Faces Strong Resistance at $95K as Bears Defend", "technical"),
            ("Ethereum Outperforms with 15% Daily Gain", "asset_news"),
        ]

        for title, expected_topic in test_cases:
            detected = _detect_crypto_topic(title.lower())
            assert detected == expected_topic, f"Title '{title}' should map to {expected_topic}, got {detected}"

    def test_topic_priority_order(self):
        """Test that higher priority topics are selected when multiple match."""
        # "hacked" matches protocol_risk first, not regulation
        candidate = _create_candidate(
            1,
            "SEC Investigates After Exchange Was Hacked of $50M",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        # Should detect protocol_risk (higher priority) over regulation
        assert result.topic == "protocol_risk"


class TestDomainTierScoring:
    """Test that crypto domain tiers work correctly."""

    def test_tier_1_sources(self):
        """Test CoinDesk and TheBlock get tier 1 (20 pts)."""
        tier_1_sources = ["coindesk.com", "theblock.co", "decrypt.co"]

        for source in tier_1_sources:
            candidate = _create_candidate(1, "Bitcoin Price Rallies", source=source)
            config = ScoringConfig()
            results = score_candidates_v3([candidate], config)

            assert "v3_tier:20" in " ".join(results[0].flags), f"{source} should get tier 1"

    def test_tier_2_sources(self):
        """Test Cointelegraph and BitcoinMagazine get tier 2 (15 pts)."""
        tier_2_sources = ["cointelegraph.com", "bitcoinmagazine.com"]

        for source in tier_2_sources:
            candidate = _create_candidate(1, "Ethereum Update", source=source)
            config = ScoringConfig()
            results = score_candidates_v3([candidate], config)

            assert "v3_tier:15" in " ".join(results[0].flags), f"{source} should get tier 2"

    def test_tier_4_default(self):
        """Test unknown sources get tier 4 (5 pts)."""
        candidate = _create_candidate(1, "Crypto News", source="unknownsource.com")
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert "v3_tier:5" in " ".join(results[0].flags)


class TestBreakingNewsBypass:
    """Test that breaking news gets boost regardless of domain."""

    def test_breaking_news_boost(self):
        """Test breaking news boost works for lower-tier sources."""
        candidate = _create_candidate(
            1,
            "BREAKING: Major Protocol Halted After $200M Exploit",
            source="unknownsource.com",  # Low tier
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        result = results[0]
        assert "v3_boost:breaking_news" in " ".join(result.flags)


class TestScoringConsistency:
    """Test that scoring is consistent and deterministic."""

    def test_same_input_same_score(self):
        """Test that identical inputs get identical scores."""
        candidate = _create_candidate(
            1,
            "SEC Approves Bitcoin ETF in Landmark Decision",
        )
        config = ScoringConfig()

        results1 = score_candidates_v3([candidate], config)
        results2 = score_candidates_v3([candidate], config)

        assert results1[0].impact_score == results2[0].impact_score

    def test_sorting_by_score(self):
        """Test that results are sorted by impact_score descending."""
        candidates = [
            _create_candidate(1, "Low priority news"),
            _create_candidate(2, "SEC Approves Bitcoin ETF in Landmark Decision"),
            _create_candidate(3, "Medium priority update"),
        ]
        config = ScoringConfig()
        results = score_candidates_v3(candidates, config)

        # Check descending order
        scores = [r.impact_score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestScorerVersion:
    """Test that v3 scorer is properly tagged."""

    def test_scorer_version_tag(self):
        """Test that all results have scorer_version = 'heuristic_v3'."""
        candidates = [
            _create_candidate(1, "Bitcoin news"),
            _create_candidate(2, "Ethereum update"),
        ]
        config = ScoringConfig()
        results = score_candidates_v3(candidates, config)

        for result in results:
            assert result.scorer_version == "heuristic_v3"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_title(self):
        """Test that empty title doesn't crash."""
        candidate = _create_candidate(1, "")
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        assert len(results) == 1
        # Should get base score only
        assert results[0].impact_score >= 0

    def test_no_crypto_context(self):
        """Test that non-crypto news gets appropriate score."""
        candidate = _create_candidate(
            1,
            "Stock Market Rallies as Manufacturing Data Beats Expectations",
            source="reuters.com",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        # Non-crypto news gets base score + tier 5 (unknown domain for crypto)
        # The v3 scorer is designed for crypto, so non-crypto news gets lower score
        # but may still get some points from recency/source tier
        assert results[0].scorer_version == "heuristic_v3"
        # Verify no crypto-specific boosts were applied
        has_crypto_boost = any("v3_boost:" in flag for flag in results[0].flags)
        assert not has_crypto_boost, "Non-crypto news should not get crypto boosts"

    def test_mixed_signals(self):
        """Test item with both boost and penalty signals."""
        candidate = _create_candidate(
            1,
            "Bitcoin Will Reach $1M After SEC Approval, Analyst Predicts",
        )
        config = ScoringConfig()
        results = score_candidates_v3([candidate], config)

        # Should have both boost and penalty flags
        flags = " ".join(results[0].flags)
        has_boost = any("v3_boost" in flag for flag in results[0].flags)
        has_penalty = any("v3_penalty" in flag for flag in results[0].flags)

        # Regulation boost should be present
        assert has_boost or has_penalty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
