"""Type definitions for trace output.

The trace module produces a detailed JSON trace of pipeline execution
without requiring database access.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Union

from argus.facts_bundle.types import FactsBundle, CryptoFactsBundle


@dataclass
class ScoredItemTrace:
    """Trace of a single scored news item.

    Includes all scoring details for debugging and analysis.
    """

    news_item_id: int
    title: str
    source_name: str
    source_url: str
    published_at: Optional[str]  # ISO format string
    impact_score: int
    quality_score: int
    confidence_score: int
    topic: Optional[str]
    reasons: list[str]
    flags: list[str]
    breakdown: Optional[dict[str, int]]  # ScoreBreakdown fields
    selected_for_bundle: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "news_item_id": self.news_item_id,
            "title": self.title,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "published_at": self.published_at,
            "impact_score": self.impact_score,
            "quality_score": self.quality_score,
            "confidence_score": self.confidence_score,
            "topic": self.topic,
            "reasons": self.reasons,
            "flags": self.flags,
            "breakdown": self.breakdown,
            "selected_for_bundle": self.selected_for_bundle,
        }


@dataclass
class StageTrace:
    """Trace of a single pipeline stage.

    Records timing and output for each stage of execution.
    """

    name: str
    started_at: str  # ISO format
    completed_at: str  # ISO format
    duration_ms: int
    item_count: int
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "item_count": self.item_count,
            "artifacts": self.artifacts,
            "errors": self.errors,
        }


@dataclass
class TraceOutput:
    """Complete trace output from a pipeline run.

    This is the JSON-serializable output of the trace command.
    """

    run_id: str
    stream_name: str
    run_mode: str
    trading_date: str  # ISO format date
    scoring_version: str
    started_at: str  # ISO format
    completed_at: Optional[str]  # ISO format, None if still running
    stages: list[StageTrace] = field(default_factory=list)
    all_scored_items: list[ScoredItemTrace] = field(default_factory=list)
    facts_bundle: Optional[dict[str, Any]] = None
    generated_message: Optional[str] = None
    validation_errors: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stream_name": self.stream_name,
            "run_mode": self.run_mode,
            "trading_date": self.trading_date,
            "scoring_version": self.scoring_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stages": [stage.to_dict() for stage in self.stages],
            "all_scored_items": [item.to_dict() for item in self.all_scored_items],
            "facts_bundle": self.facts_bundle,
            "generated_message": self.generated_message,
            "validation_errors": self.validation_errors,
            "errors": self.errors,
        }

    def add_stage(self, stage: StageTrace) -> None:
        """Add a completed stage to the trace."""
        self.stages.append(stage)

    def set_bundle(self, bundle: Union[FactsBundle, CryptoFactsBundle]) -> None:
        """Set the facts bundle from a typed bundle object."""
        self.facts_bundle = bundle.to_dict()

    def finalize(self) -> None:
        """Mark the trace as complete with current timestamp."""
        self.completed_at = datetime.now(timezone.utc).isoformat()


def create_stage_trace(
    name: str,
    started_at: datetime,
    completed_at: datetime,
    item_count: int,
    artifacts: Optional[dict[str, Any]] = None,
    errors: Optional[list[str]] = None,
) -> StageTrace:
    """Helper to create a stage trace with computed duration."""
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    return StageTrace(
        name=name,
        started_at=started_at.isoformat(),
        completed_at=completed_at.isoformat(),
        duration_ms=duration_ms,
        item_count=item_count,
        artifacts=artifacts or {},
        errors=errors or [],
    )
