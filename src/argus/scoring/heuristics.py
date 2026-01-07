"""Heuristic scoring functions for Argus.

Implements the heuristic scoring pipeline:
- Recency: 0-25 pts (exponential decay over 24h)
- Source Tier: 0-20 pts (configurable tiers)
- Keyword Relevance: 0-30 pts (market-relevant keywords)
- Uniqueness: 0-15 pts (SimHash distance from recent items)
- Breaking/Urgency: 0-10 pts (contains "breaking", "urgent", etc.)
"""

import math
import re
from datetime import datetime, timezone
from typing import Optional

from argus.config import ScoringConfig
from argus.dedupe.simhash import hamming_distance
from argus.scoring.types import ScoreBreakdown, ScoringCandidate, ScoringResult


# Topic detection keyword sets
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "macro": [
        "fed",
        "federal reserve",
        "fomc",
        "inflation",
        "cpi",
        "pce",
        "gdp",
        "jobs",
        "employment",
        "unemployment",
        "nonfarm",
        "payrolls",
        "interest rate",
        "rate hike",
        "rate cut",
        "dovish",
        "hawkish",
        "treasury",
        "yield",
        "yields",
        "bond",
        "bonds",
    ],
    "earnings": [
        "earnings",
        "revenue",
        "profit",
        "quarterly",
        "guidance",
        "eps",
        "beat",
        "miss",
        "outlook",
        "forecast",
        "q1",
        "q2",
        "q3",
        "q4",
        "results",
        "report",
    ],
    "geopolitics": [
        "war",
        "conflict",
        "sanctions",
        "tariff",
        "tariffs",
        "election",
        "vote",
        "china",
        "russia",
        "ukraine",
        "taiwan",
        "iran",
        "opec",
        "trade war",
        "embargo",
    ],
    "markets": [
        "s&p",
        "s&p 500",
        "nasdaq",
        "dow",
        "djia",
        "rally",
        "selloff",
        "sell-off",
        "bull",
        "bear",
        "correction",
        "crash",
        "record high",
        "all-time high",
        "futures",
        "vix",
        "volatility",
    ],
    "crypto": [
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "crypto",
        "cryptocurrency",
        "blockchain",
        "defi",
        "nft",
        "stablecoin",
        "binance",
        "coinbase",
    ],
    "commodities": [
        "oil",
        "crude",
        "wti",
        "brent",
        "gold",
        "silver",
        "copper",
        "natural gas",
        "lng",
        "wheat",
        "corn",
        "commodity",
        "commodities",
    ],
}

# High-value keywords for relevance scoring (higher points)
HIGH_VALUE_KEYWORDS: list[str] = [
    "fed",
    "fomc",
    "inflation",
    "cpi",
    "gdp",
    "earnings",
    "interest rate",
    "rate hike",
    "rate cut",
    "tariff",
    "sanctions",
    "breaking",
    "exclusive",
    "s&p",
    "nasdaq",
    "rally",
    "crash",
    "selloff",
]

# Medium-value keywords
MEDIUM_VALUE_KEYWORDS: list[str] = [
    "treasury",
    "yield",
    "bond",
    "employment",
    "jobs",
    "revenue",
    "profit",
    "guidance",
    "forecast",
    "outlook",
    "china",
    "russia",
    "opec",
    "oil",
    "gold",
    "bitcoin",
    "volatility",
    "futures",
]

# Breaking/urgency indicators
BREAKING_KEYWORDS: list[str] = [
    "breaking",
    "just in",
    "developing",
    "urgent",
    "alert",
    "exclusive",
    "flash",
    "live",
]


class HeuristicScorer:
    """Heuristic-based news item scorer.

    Computes impact scores based on recency, source tier,
    keyword relevance, uniqueness, and breaking indicators.
    """

    def __init__(
        self,
        config: ScoringConfig,
        reference_time: Optional[datetime] = None,
    ):
        """Initialize the scorer.

        Args:
            config: Scoring configuration.
            reference_time: Reference time for recency calculation.
                          Defaults to current UTC time.
        """
        self.config = config
        self.source_tiers = config.source_tiers
        self.reference_time = reference_time or datetime.now(timezone.utc)
        self._recent_simhashes: list[int] = []

    def set_recent_simhashes(self, simhashes: list[int]) -> None:
        """Set the list of recent SimHashes for uniqueness comparison.

        Args:
            simhashes: List of SimHash values from recent items.
        """
        self._recent_simhashes = [s for s in simhashes if s is not None]

    def score_candidate(
        self,
        candidate: ScoringCandidate,
    ) -> ScoringResult:
        """Score a single candidate.

        Args:
            candidate: The news item candidate to score.

        Returns:
            ScoringResult with computed scores and breakdown.
        """
        # Compute individual components
        recency_score = self._score_recency(candidate)
        source_score = self._score_source_tier(candidate)
        keyword_score = self._score_keywords(candidate)
        uniqueness_score = self._score_uniqueness(candidate)
        breaking_score = self._score_breaking(candidate)

        # Build breakdown
        breakdown = ScoreBreakdown(
            recency=recency_score,
            source_tier=source_score,
            keyword_relevance=keyword_score,
            uniqueness=uniqueness_score,
            breaking_urgency=breaking_score,
        )

        # Detect topic
        topic = self._detect_topic(candidate)

        # Detect flags
        flags = self._detect_flags(candidate)

        # Create result from breakdown
        return ScoringResult.from_breakdown(
            candidate=candidate,
            breakdown=breakdown,
            topic=topic,
            flags=flags,
            scorer_version=self.config.scorer_version,
        )

    def _score_recency(self, candidate: ScoringCandidate) -> int:
        """Score based on recency (0-25 pts).

        Uses exponential decay over the scoring window.
        Newer items get higher scores.

        Args:
            candidate: Candidate to score.

        Returns:
            Recency score (0-25).
        """
        # Use published_at if available, otherwise ingested_at
        item_time = candidate.published_at or candidate.ingested_at

        # Ensure timezone-aware comparison
        if item_time.tzinfo is None:
            item_time = item_time.replace(tzinfo=timezone.utc)

        # Calculate age in hours
        age_delta = self.reference_time - item_time
        age_hours = age_delta.total_seconds() / 3600

        if age_hours < 0:
            # Future time (clock skew), give max score
            return 25

        # Exponential decay: score = 25 * e^(-age_hours / half_life)
        # Half-life of 6 hours means score drops to ~12.5 at 6h, ~6.25 at 12h
        half_life = 6.0
        decay_factor = math.exp(-age_hours * math.log(2) / half_life)

        return min(25, max(0, int(25 * decay_factor)))

    def _score_source_tier(self, candidate: ScoringCandidate) -> int:
        """Score based on source tier (0-20 pts).

        Uses configurable source tiers from config.

        Args:
            candidate: Candidate to score.

        Returns:
            Source tier score (0-20).
        """
        return self.source_tiers.get_tier_score(candidate.source_name)

    def _score_keywords(self, candidate: ScoringCandidate) -> int:
        """Score based on keyword relevance (0-30 pts).

        Checks for market-relevant keywords in title and snippet.

        Args:
            candidate: Candidate to score.

        Returns:
            Keyword relevance score (0-30).
        """
        text = candidate.text_for_scoring.lower()
        score = 0

        # High-value keywords: 5 pts each, max 15 pts
        high_matches = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw in text)
        score += min(15, high_matches * 5)

        # Medium-value keywords: 2 pts each, max 10 pts
        medium_matches = sum(1 for kw in MEDIUM_VALUE_KEYWORDS if kw in text)
        score += min(10, medium_matches * 2)

        # Topic diversity bonus: 1 pt per topic mentioned, max 5 pts
        topics_found = sum(
            1 for topic_kws in TOPIC_KEYWORDS.values() if any(kw in text for kw in topic_kws)
        )
        score += min(5, topics_found)

        return min(30, score)

    def _score_uniqueness(self, candidate: ScoringCandidate) -> int:
        """Score based on uniqueness vs recent items (0-15 pts).

        Uses SimHash Hamming distance to measure uniqueness.
        Items that are more different from recent items get higher scores.

        Args:
            candidate: Candidate to score.

        Returns:
            Uniqueness score (0-15).
        """
        if not self._recent_simhashes or candidate.simhash is None:
            # No comparison possible, give moderate score
            return 8

        # Find minimum Hamming distance to any recent item
        min_distance = min(
            hamming_distance(candidate.simhash, recent) for recent in self._recent_simhashes
        )

        # Distance 0-3: very similar (low uniqueness) -> 0-3 pts
        # Distance 4-7: somewhat similar -> 4-8 pts
        # Distance 8-15: quite different -> 9-12 pts
        # Distance 16+: very unique -> 13-15 pts

        if min_distance <= 3:
            return min_distance
        elif min_distance <= 7:
            return 4 + (min_distance - 4)
        elif min_distance <= 15:
            return 9 + min((min_distance - 8) // 2, 3)
        else:
            return 15

    def _score_breaking(self, candidate: ScoringCandidate) -> int:
        """Score based on breaking/urgency indicators (0-10 pts).

        Checks for breaking news keywords in title.

        Args:
            candidate: Candidate to score.

        Returns:
            Breaking/urgency score (0-10).
        """
        title_lower = candidate.title.lower()

        # Check for breaking keywords
        for keyword in BREAKING_KEYWORDS:
            if keyword in title_lower:
                return 10

        # Check for urgency patterns
        urgency_patterns = [
            r"\bbreaks?\b",
            r"\bjust\s+in\b",
            r"\bdeveloping\b",
            r"\bexclusive\b",
        ]

        for pattern in urgency_patterns:
            if re.search(pattern, title_lower):
                return 8

        return 0

    def _detect_topic(self, candidate: ScoringCandidate) -> Optional[str]:
        """Detect the primary topic of the news item.

        Args:
            candidate: Candidate to analyze.

        Returns:
            Topic string or None if no strong topic match.
        """
        text = candidate.text_for_scoring.lower()

        # Count matches for each topic
        topic_scores: dict[str, int] = {}
        for topic, keywords in TOPIC_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in text)
            if matches > 0:
                topic_scores[topic] = matches

        if not topic_scores:
            return None

        # Return topic with most matches
        return max(topic_scores, key=lambda t: topic_scores[t])

    def _detect_flags(self, candidate: ScoringCandidate) -> list[str]:
        """Detect special flags for the news item.

        Args:
            candidate: Candidate to analyze.

        Returns:
            List of flag strings.
        """
        flags = []
        title_lower = candidate.title.lower()
        text_lower = candidate.text_for_scoring.lower()

        # Breaking news
        if any(kw in title_lower for kw in ["breaking", "just in", "developing"]):
            flags.append("breaking")

        # Exclusive
        if "exclusive" in title_lower:
            flags.append("exclusive")

        # Market moving (specific high-impact keywords in title)
        market_movers = ["fed", "fomc", "rate hike", "rate cut", "cpi", "gdp"]
        if any(kw in title_lower for kw in market_movers):
            flags.append("market_moving")

        # Earnings related
        if any(kw in text_lower for kw in ["earnings", "quarterly", "eps", "guidance"]):
            flags.append("earnings")

        return flags


def score_candidates(
    candidates: list[ScoringCandidate],
    config: ScoringConfig,
    recent_simhashes: Optional[list[int]] = None,
) -> list[ScoringResult]:
    """Score a batch of candidates.

    Args:
        candidates: List of candidates to score.
        config: Scoring configuration.
        recent_simhashes: SimHashes from recent items for uniqueness.

    Returns:
        List of ScoringResults, sorted by impact_score descending.
    """
    scorer = HeuristicScorer(config)

    if recent_simhashes:
        scorer.set_recent_simhashes(recent_simhashes)

    results = [scorer.score_candidate(c) for c in candidates]

    # Sort by impact score descending
    results.sort(key=lambda r: r.impact_score, reverse=True)

    return results
