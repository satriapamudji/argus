"""Economic calendar adapter package.

Provides integration with ForexFactory economic calendar data
for the "Key Dates (UTC)" section in generated messages.
"""

from argus.adapters.economic_calendar.adapter import EconomicCalendarAdapter
from argus.adapters.economic_calendar.fetcher import EconomicCalendarFetcher
from argus.adapters.economic_calendar.types import (
    EconomicEventRow,
    RawEconomicEvent,
    RefreshResult,
)

__all__ = [
    "EconomicCalendarAdapter",
    "EconomicCalendarFetcher",
    "EconomicEventRow",
    "RawEconomicEvent",
    "RefreshResult",
]
