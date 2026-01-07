"""Type definitions for the run orchestrator.

Contains data structures for run results, window configuration,
risk score breakdown, and timing information.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class RunMode(Enum):
    """Available run modes for Argus."""

    US_CLOSE = "us_close"
    WEEKEND_WRAP = "weekend_wrap"
    MONDAY_PREVIEW = "monday_preview"

    @classmethod
    def from_string(cls, value: str) -> "RunMode":
        """Create RunMode from string value.

        Args:
            value: String representation of the run mode.

        Returns:
            Corresponding RunMode enum value.

        Raises:
            ValueError: If value doesn't match any run mode.
        """
        for mode in cls:
            if mode.value == value:
                return mode
        raise ValueError(f"Unknown run mode: {value}")


class RunStatus(Enum):
    """Status of a run execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g., holiday skip, conditional skip


class HolidayBehavior(Enum):
    """Behavior when a run falls on a market holiday."""

    SKIP = "skip"
    PUBLISH_CLOSED_NOTE = "publish_closed_note"


class HalfDayBehavior(Enum):
    """Behavior when a run falls on an early close / half day."""

    LABEL_HALF_DAY = "label_half_day"
    SKIP = "skip"


@dataclass(frozen=True)
class WindowConfig:
    """Configuration for the news selection window.

    Attributes:
        start: Start of the window (inclusive).
        end: End of the window (inclusive).
        window_hours: Duration of the window in hours.
        mode: The run mode this window is for.
    """

    start: datetime
    end: datetime
    window_hours: int
    mode: RunMode


@dataclass
class RiskScoreBreakdown:
    """Breakdown of the monday_preview risk score.

    The total risk_score determines whether to publish the monday_preview.
    Default threshold is 60.

    Attributes:
        calendar_score: Score from upcoming economic events (0-60).
        market_score: Score from market stress indicators (0-30).
        headline_score: Score from high-impact recent news (0-30).
        total: Combined risk score, capped at 100.
        details: Optional dict with scoring details for debugging.
    """

    calendar_score: int = 0
    market_score: int = 0
    headline_score: int = 0
    details: Optional[dict[str, Any]] = None

    @property
    def total(self) -> int:
        """Calculate total risk score, capped at 100."""
        return min(100, self.calendar_score + self.market_score + self.headline_score)


@dataclass
class RunTimings:
    """Timing breakdown for a run execution.

    All times are in milliseconds.
    """

    ingest_ms: Optional[int] = None
    scoring_ms: Optional[int] = None
    enrichment_ms: Optional[int] = None
    window_selection_ms: Optional[int] = None
    risk_score_ms: Optional[int] = None
    bundle_ms: Optional[int] = None
    generation_ms: Optional[int] = None
    validation_ms: Optional[int] = None
    publish_ms: Optional[int] = None
    total_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            k: v
            for k, v in {
                "ingest_ms": self.ingest_ms,
                "scoring_ms": self.scoring_ms,
                "enrichment_ms": self.enrichment_ms,
                "window_selection_ms": self.window_selection_ms,
                "risk_score_ms": self.risk_score_ms,
                "bundle_ms": self.bundle_ms,
                "generation_ms": self.generation_ms,
                "validation_ms": self.validation_ms,
                "publish_ms": self.publish_ms,
                "total_ms": self.total_ms,
            }.items()
            if v is not None
        }


@dataclass
class HolidayInfo:
    """Information about holiday/half-day status for a run.

    Attributes:
        is_holiday: Whether the trading day is a market holiday.
        is_half_day: Whether the trading day is an early close.
        holiday_name: Name of the holiday if applicable.
        behavior_applied: The behavior that was applied (skip, label, etc.).
        should_skip: Whether the run should be skipped entirely.
        label_text: Optional label to include in the message.
    """

    is_holiday: bool = False
    is_half_day: bool = False
    holiday_name: Optional[str] = None
    behavior_applied: Optional[str] = None
    should_skip: bool = False
    label_text: Optional[str] = None


@dataclass
class RunResult:
    """Result of a complete run execution.

    Attributes:
        run_id: Database ID of the run record.
        message_id: Database ID of the generated message (if any).
        status: Final status of the run.
        mode: The run mode that was executed.
        stream_name: Name of the stream.
        trading_date: The trading date for this run.
        timings: Timing breakdown for the run.
        risk_score: Risk score breakdown (for monday_preview).
        holiday_info: Holiday/half-day information.
        facts_bundle: The generated facts bundle (if successful).
        message_content: The generated message content (if successful).
        telegram_message_id: Telegram message ID (if published).
        error: Error message if the run failed.
        was_conditional_skip: Whether run was skipped due to conditional check.
        publish_skipped: Whether publishing was explicitly skipped.
    """

    run_id: Optional[int] = None
    message_id: Optional[int] = None
    status: RunStatus = RunStatus.PENDING
    mode: Optional[RunMode] = None
    stream_name: str = ""
    trading_date: Optional[datetime] = None
    timings: RunTimings = field(default_factory=RunTimings)
    risk_score: Optional[RiskScoreBreakdown] = None
    holiday_info: Optional[HolidayInfo] = None
    facts_bundle: Optional[dict[str, Any]] = None
    message_content: Optional[str] = None
    telegram_message_id: Optional[int] = None
    error: Optional[str] = None
    was_conditional_skip: bool = False
    publish_skipped: bool = False
