"""Economic calendar adapter package.

Provides integration with ForexFactory economic calendar data
for the "Key Dates (UTC)" section in generated messages.
"""

from argus.adapters.economic_calendar.adapter import EconomicCalendarAdapter
from argus.adapters.economic_calendar.fetcher import refresh_economic_calendar
from argus.adapters.economic_calendar.types import (
    EconomicEventRow,
    RawEconomicEvent,
    RefreshResult,
)

__all__ = [
    "EconomicCalendarAdapter",
    "refresh_economic_calendar",
    "EconomicEventRow",
    "RawEconomicEvent",
    "RefreshResult",
]
