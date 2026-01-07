"""Type definitions for economic calendar adapter.

All dataclasses follow the codebase convention of using frozen=True
for immutability where appropriate.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class RawEconomicEvent:
    """Raw economic event parsed from ForexFactory JSON.

    Timestamps are converted to UTC during parsing.

    Attributes:
        title: Event name (e.g., "Non-Farm Employment Change").
        country: Currency/country code (e.g., "USD").
        timestamp_utc: Event time converted to UTC.
        impact: Impact level ("High", "Medium", "Low", "Holiday").
        forecast: Forecasted value (e.g., "66K", "3.2%").
        previous: Previous value (e.g., "64K", "3.1%").
    """

    title: str
    country: str
    timestamp_utc: datetime
    impact: str
    forecast: Optional[str] = None
    previous: Optional[str] = None

    def __post_init__(self) -> None:
        """Ensure timestamp is UTC."""
        from datetime import timezone

        if self.timestamp_utc.tzinfo is None:
            object.__setattr__(
                self,
                "timestamp_utc",
                self.timestamp_utc.replace(tzinfo=timezone.utc),
            )
        elif self.timestamp_utc.tzinfo != timezone.utc:
            object.__setattr__(
                self,
                "timestamp_utc",
                self.timestamp_utc.astimezone(timezone.utc),
            )


@dataclass(frozen=True)
class EconomicEventRow:
    """Database row for economic calendar events.

    Matches the economic_calendar_events table schema.

    Attributes:
        id: Primary key.
        title: Event name.
        country: Currency/country code.
        event_timestamp: Event time in UTC.
        impact: Impact level.
        forecast: Forecasted value.
        previous: Previous value.
        actual: Actual value (filled after event).
        source: Data source (e.g., "forexfactory").
        fetched_at: When this record was fetched.
    """

    id: int
    title: str
    country: str
    event_timestamp: datetime
    impact: str
    forecast: Optional[str]
    previous: Optional[str]
    actual: Optional[str]
    source: str
    fetched_at: datetime

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "EconomicEventRow":
        """Create from database row tuple.

        Args:
            row: Database row tuple in column order.

        Returns:
            EconomicEventRow instance.
        """
        return cls(
            id=row[0],
            title=row[1],
            country=row[2],
            event_timestamp=row[3],
            impact=row[4],
            forecast=row[5],
            previous=row[6],
            actual=row[7],
            source=row[8],
            fetched_at=row[9],
        )


@dataclass
class RefreshResult:
    """Result of a calendar refresh operation.

    Attributes:
        events_fetched: Total events fetched from source.
        events_inserted: New events inserted.
        events_updated: Existing events updated.
        source: Data source name.
        fetched_at: Timestamp of the fetch.
        duration_seconds: How long the operation took.
        errors: List of error messages if any.
    """

    events_fetched: int
    events_inserted: int
    events_updated: int
    source: str
    fetched_at: datetime
    duration_seconds: float
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Return True if no errors occurred."""
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "events_fetched": self.events_fetched,
            "events_inserted": self.events_inserted,
            "events_updated": self.events_updated,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
            "success": self.success,
        }
