"""Market data and calendar adapters for Argus."""

from argus.adapters.market_data import (
    CrossAssetMetrics,
    IndexSnapshot,
    MarketDataProvider,
    MarketSnapshot,
)
from argus.adapters.calendar import (
    Catalyst,
    CatalystType,
    MarketCalendarAdapter,
    TradingDayInfo,
    create_catalyst,
)

__all__ = [
    "CrossAssetMetrics",
    "IndexSnapshot",
    "MarketDataProvider",
    "MarketSnapshot",
    "Catalyst",
    "CatalystType",
    "MarketCalendarAdapter",
    "TradingDayInfo",
    "create_catalyst",
]
