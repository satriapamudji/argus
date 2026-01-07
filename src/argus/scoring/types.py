"""Scoring types for Argus.

Dataclasses for scoring candidates, results, and breakdowns.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScoringCandidate:
    """A news item candidate for scoring.

    Contains all the data needed to score a news item.
    """

    news_item_id: int
    fingerprint_id: int
    source_name: str
    source_url: str
    title: str
    snippet: Optional[str]
    published_at: Optional[datetime]
    ingested_at: datetime
    simhash: Optional[int] = None  # From fingerprints table

    @property
    def text_for_scoring(self) -> str:
        """Combined text for keyword/topic analysis."""
        parts = [self.title]
        if self.snippet:
            parts.append(self.snippet)
        return " ".join(parts)


@dataclass
class ScoreBreakdown:
    """Breakdown of individual scoring components.

    Shows how each heuristic contributed to the final score.
    """

    recency: int = 0  # 0-25 pts
    source_tier: int = 0  # 0-20 pts
    keyword_relevance: int = 0  # 0-30 pts
    uniqueness: int = 0  # 0-15 pts
    breaking_urgency: int = 0  # 0-10 pts

    @property
    def total(self) -> int:
        """Total heuristic score (0-100)."""
        return (
            self.recency
            + self.source_tier
            + self.keyword_relevance
            + self.uniqueness
            + self.breaking_urgency
        )

    def to_reasons(self) -> list[str]:
        """Convert breakdown to human-readable reasons list."""
        reasons = []
        if self.recency > 0:
            reasons.append(f"recency: +{self.recency}")
        if self.source_tier > 0:
            reasons.append(f"source_tier: +{self.source_tier}")
        if self.keyword_relevance > 0:
            reasons.append(f"keywords: +{self.keyword_relevance}")
        if self.uniqueness > 0:
            reasons.append(f"uniqueness: +{self.uniqueness}")
        if self.breaking_urgency > 0:
            reasons.append(f"breaking: +{self.breaking_urgency}")
        return reasons


@dataclass
class ScoringResult:
    """Result of scoring a news item.

    Maps to the news_scores table structure.
    """

    news_item_id: int
    ingested_at: datetime  # Denormalized for partition pruning
    impact_score: int  # 0-100, main ranking score
    quality_score: int  # 0-100, confidence in the score
    confidence_score: int  # 0-100, how confident we are
    topic: Optional[str]  # Detected topic: macro, earnings, etc.
    flags: list[str] = field(default_factory=list)  # Special flags
    reasons: list[str] = field(default_factory=list)  # Score breakdown
    scorer_version: str = "heuristic_v1"
    breakdown: Optional[ScoreBreakdown] = None  # Optional detailed breakdown

    @classmethod
    def from_breakdown(
        cls,
        candidate: ScoringCandidate,
        breakdown: ScoreBreakdown,
        topic: Optional[str],
        flags: list[str],
        scorer_version: str = "heuristic_v1",
    ) -> "ScoringResult":
        """Create a ScoringResult from a score breakdown.

        Args:
            candidate: The original scoring candidate.
            breakdown: The heuristic score breakdown.
            topic: Detected topic (macro, earnings, etc.).
            flags: Special flags (breaking, exclusive, etc.).
            scorer_version: Version string for the scorer.

        Returns:
            ScoringResult with computed scores.
        """
        # Impact score is the raw total from heuristics
        impact_score = breakdown.total

        # Quality score based on how many signals contributed
        signals_present = sum(
            1
            for score in [
                breakdown.recency,
                breakdown.source_tier,
                breakdown.keyword_relevance,
                breakdown.uniqueness,
                breakdown.breaking_urgency,
            ]
            if score > 0
        )
        quality_score = min(100, signals_present * 20)  # 20 pts per signal

        # Confidence based on source tier and signal count
        confidence_score = min(100, 50 + breakdown.source_tier + (signals_present * 5))

        return cls(
            news_item_id=candidate.news_item_id,
            ingested_at=candidate.ingested_at,
            impact_score=impact_score,
            quality_score=quality_score,
            confidence_score=confidence_score,
            topic=topic,
            flags=flags,
            reasons=breakdown.to_reasons(),
            scorer_version=scorer_version,
            breakdown=breakdown,
        )


@dataclass
class ScoringStats:
    """Statistics for a scoring run."""

    total_candidates: int = 0
    scored: int = 0
    skipped_already_scored: int = 0
    errors: int = 0
    llm_triaged: int = 0
    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Percentage of candidates successfully scored."""
        if self.total_candidates == 0:
            return 0.0
        return (self.scored / self.total_candidates) * 100
