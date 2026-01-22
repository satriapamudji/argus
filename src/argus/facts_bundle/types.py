"""Type definitions for facts bundle.

The facts bundle is the sole source of truth for the generator LLM.
All dataclasses are frozen to ensure immutability and determinism.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argus.orchestrator.weekly_stats import WeeklyReturn, WeeklyStats


# =============================================================================
# Market Data Types
# =============================================================================


@dataclass(frozen=True)
class IndexData:
    """Market index data for the facts bundle."""

    name: str
    symbol: str
    level: Decimal
    change_1d_pct: Decimal
    change_1d_pts: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "level": str(self.level),
            "change_1d_pct": str(self.change_1d_pct),
            "change_1d_pts": str(self.change_1d_pts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IndexData":
        return cls(
            name=data["name"],
            symbol=data["symbol"],
            level=Decimal(data["level"]),
            change_1d_pct=Decimal(data["change_1d_pct"]),
            change_1d_pts=Decimal(data["change_1d_pts"]),
        )


@dataclass(frozen=True)
class CrossAssetsData:
    """Cross-asset metrics for the facts bundle.

    All fields are optional - missing data does not break the bundle.
    """

    vix_level: Optional[Decimal] = None
    vix_change_pct: Optional[Decimal] = None
    us10y_yield: Optional[Decimal] = None
    us10y_change_bps: Optional[Decimal] = None
    dxy_level: Optional[Decimal] = None
    dxy_change_pct: Optional[Decimal] = None
    wti_level: Optional[Decimal] = None
    wti_change_pct: Optional[Decimal] = None
    gold_level: Optional[Decimal] = None
    gold_change_pct: Optional[Decimal] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.vix_level is not None:
            result["vix_level"] = str(self.vix_level)
        if self.vix_change_pct is not None:
            result["vix_change_pct"] = str(self.vix_change_pct)
        if self.us10y_yield is not None:
            result["us10y_yield"] = str(self.us10y_yield)
        if self.us10y_change_bps is not None:
            result["us10y_change_bps"] = str(self.us10y_change_bps)
        if self.dxy_level is not None:
            result["dxy_level"] = str(self.dxy_level)
        if self.dxy_change_pct is not None:
            result["dxy_change_pct"] = str(self.dxy_change_pct)
        if self.wti_level is not None:
            result["wti_level"] = str(self.wti_level)
        if self.wti_change_pct is not None:
            result["wti_change_pct"] = str(self.wti_change_pct)
        if self.gold_level is not None:
            result["gold_level"] = str(self.gold_level)
        if self.gold_change_pct is not None:
            result["gold_change_pct"] = str(self.gold_change_pct)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrossAssetsData":
        return cls(
            vix_level=Decimal(data["vix_level"]) if data.get("vix_level") else None,
            vix_change_pct=Decimal(data["vix_change_pct"]) if data.get("vix_change_pct") else None,
            us10y_yield=Decimal(data["us10y_yield"]) if data.get("us10y_yield") else None,
            us10y_change_bps=Decimal(data["us10y_change_bps"])
            if data.get("us10y_change_bps")
            else None,
            dxy_level=Decimal(data["dxy_level"]) if data.get("dxy_level") else None,
            dxy_change_pct=Decimal(data["dxy_change_pct"]) if data.get("dxy_change_pct") else None,
            wti_level=Decimal(data["wti_level"]) if data.get("wti_level") else None,
            wti_change_pct=Decimal(data["wti_change_pct"]) if data.get("wti_change_pct") else None,
            gold_level=Decimal(data["gold_level"]) if data.get("gold_level") else None,
            gold_change_pct=Decimal(data["gold_change_pct"])
            if data.get("gold_change_pct")
            else None,
        )


@dataclass(frozen=True)
class MarketSnapshotBundle:
    """Complete market snapshot for the facts bundle."""

    trading_date: date
    sp500: IndexData
    dow: IndexData
    nasdaq: IndexData
    cross_assets: Optional[CrossAssetsData] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "trading_date": self.trading_date.isoformat(),
            "sp500": self.sp500.to_dict(),
            "dow": self.dow.to_dict(),
            "nasdaq": self.nasdaq.to_dict(),
        }
        if self.cross_assets is not None:
            result["cross_assets"] = self.cross_assets.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketSnapshotBundle":
        cross_assets = None
        if data.get("cross_assets"):
            cross_assets = CrossAssetsData.from_dict(data["cross_assets"])
        return cls(
            trading_date=date.fromisoformat(data["trading_date"]),
            sp500=IndexData.from_dict(data["sp500"]),
            dow=IndexData.from_dict(data["dow"]),
            nasdaq=IndexData.from_dict(data["nasdaq"]),
            cross_assets=cross_assets,
        )


# =============================================================================
# News Item Types
# =============================================================================


@dataclass(frozen=True)
class NewsItemBundle:
    """A single news item for the facts bundle."""

    id: int
    title: str
    source_name: str
    source_url: str
    published_at: Optional[datetime]
    snippet: Optional[str]
    content_excerpt: Optional[str]
    topic: Optional[str]
    impact_score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "snippet": self.snippet,
            "content_excerpt": self.content_excerpt,
            "topic": self.topic,
            "impact_score": self.impact_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsItemBundle":
        published_at = None
        if data.get("published_at"):
            published_at = datetime.fromisoformat(data["published_at"])
        return cls(
            id=data["id"],
            title=data["title"],
            source_name=data["source_name"],
            source_url=data["source_url"],
            published_at=published_at,
            snippet=data.get("snippet"),
            content_excerpt=data.get("content_excerpt"),
            topic=data.get("topic"),
            impact_score=data["impact_score"],
        )


# =============================================================================
# Calendar Event Types
# =============================================================================


@dataclass(frozen=True)
class CalendarEventBundle:
    """A single calendar event for the facts bundle."""

    name: str
    timestamp_utc: datetime
    event_type: str  # 'economic', 'earnings', 'fed', 'other'
    formatted_display: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "event_type": self.event_type,
            "formatted_display": self.formatted_display,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalendarEventBundle":
        return cls(
            name=data["name"],
            timestamp_utc=datetime.fromisoformat(data["timestamp_utc"]),
            event_type=data["event_type"],
            formatted_display=data["formatted_display"],
        )


# =============================================================================
# Spotlight Types
# =============================================================================


@dataclass(frozen=True)
class SpotlightBundle:
    """Spotlight content for the facts bundle."""

    title: str
    body: str
    disclaimer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "disclaimer": self.disclaimer,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpotlightBundle":
        return cls(
            title=data["title"],
            body=data["body"],
            disclaimer=data["disclaimer"],
        )


# =============================================================================
# Weekly Stats Types
# =============================================================================


@dataclass(frozen=True)
class WeeklyReturnBundle:
    """Serialized weekly return for an index."""

    label: str
    start_date: date
    end_date: date
    return_pct: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "return_pct": str(self.return_pct),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeeklyReturnBundle":
        return cls(
            label=data["label"],
            start_date=date.fromisoformat(data["start_date"]),
            end_date=date.fromisoformat(data["end_date"]),
            return_pct=Decimal(data["return_pct"]),
        )

    @classmethod
    def from_weekly_return(cls, weekly_return: "WeeklyReturn") -> "WeeklyReturnBundle":
        return cls(
            label=weekly_return.label,
            start_date=weekly_return.start_date,
            end_date=weekly_return.end_date,
            return_pct=Decimal(str(weekly_return.return_pct)),
        )


@dataclass(frozen=True)
class WeeklyStatsBundle:
    """Serialized weekly stats for inclusion in the facts bundle."""

    week_start: date
    week_end: date
    sp500_return: Optional[WeeklyReturnBundle]
    dow_return: Optional[WeeklyReturnBundle]
    nasdaq_return: Optional[WeeklyReturnBundle]

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "sp500_return": self.sp500_return.to_dict() if self.sp500_return else None,
            "dow_return": self.dow_return.to_dict() if self.dow_return else None,
            "nasdaq_return": self.nasdaq_return.to_dict() if self.nasdaq_return else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeeklyStatsBundle":
        return cls(
            week_start=date.fromisoformat(data["week_start"]),
            week_end=date.fromisoformat(data["week_end"]),
            sp500_return=WeeklyReturnBundle.from_dict(data["sp500_return"])
            if data.get("sp500_return")
            else None,
            dow_return=WeeklyReturnBundle.from_dict(data["dow_return"])
            if data.get("dow_return")
            else None,
            nasdaq_return=WeeklyReturnBundle.from_dict(data["nasdaq_return"])
            if data.get("nasdaq_return")
            else None,
        )

    @classmethod
    def from_weekly_stats(cls, weekly_stats: "WeeklyStats") -> "WeeklyStatsBundle":
        return cls(
            week_start=weekly_stats.week_start,
            week_end=weekly_stats.week_end,
            sp500_return=WeeklyReturnBundle.from_weekly_return(weekly_stats.sp500_return)
            if weekly_stats.sp500_return
            else None,
            dow_return=WeeklyReturnBundle.from_weekly_return(weekly_stats.dow_return)
            if weekly_stats.dow_return
            else None,
            nasdaq_return=WeeklyReturnBundle.from_weekly_return(weekly_stats.nasdaq_return)
            if weekly_stats.nasdaq_return
            else None,
        )


# =============================================================================
# Main Facts Bundle
# =============================================================================


@dataclass(frozen=True)
class FactsBundle:
    """The complete facts bundle - sole source of truth for the LLM.

    This is the immutable contract between the bundle builder and the generator.
    """

    version: str
    stream_name: str
    run_mode: str  # 'us_close', 'weekend_wrap', 'monday_preview'
    generated_at: datetime
    trading_date: date
    market_snapshot: MarketSnapshotBundle
    news_items: tuple[NewsItemBundle, ...]
    calendar_events: tuple[CalendarEventBundle, ...]
    spotlight: Optional[SpotlightBundle] = None
    weekly_stats: Optional[WeeklyStatsBundle] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "version": self.version,
            "stream_name": self.stream_name,
            "run_mode": self.run_mode,
            "generated_at": self.generated_at.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "market_snapshot": self.market_snapshot.to_dict(),
            "news_items": [item.to_dict() for item in self.news_items],
            "calendar_events": [event.to_dict() for event in self.calendar_events],
        }
        if self.spotlight is not None:
            result["spotlight"] = self.spotlight.to_dict()
        if self.weekly_stats is not None:
            result["weekly_stats"] = self.weekly_stats.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactsBundle":
        spotlight = None
        if data.get("spotlight"):
            spotlight = SpotlightBundle.from_dict(data["spotlight"])
        weekly_stats = None
        if data.get("weekly_stats"):
            weekly_stats = WeeklyStatsBundle.from_dict(data["weekly_stats"])
        return cls(
            version=data["version"],
            stream_name=data["stream_name"],
            run_mode=data["run_mode"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
            trading_date=date.fromisoformat(data["trading_date"]),
            market_snapshot=MarketSnapshotBundle.from_dict(data["market_snapshot"]),
            news_items=tuple(NewsItemBundle.from_dict(item) for item in data["news_items"]),
            calendar_events=tuple(
                CalendarEventBundle.from_dict(event) for event in data["calendar_events"]
            ),
            spotlight=spotlight,
            weekly_stats=weekly_stats,
        )


# =============================================================================
# Crypto Types
# =============================================================================


@dataclass(frozen=True)
class CryptoIndexData:
    """Crypto asset data for the crypto facts bundle.

    Similar to IndexData but with additional crypto-specific fields.
    """

    symbol: str
    name: str
    price_usd: Decimal
    change_1d_pct: Decimal
    market_cap_usd: Optional[Decimal] = None
    volume_24h_usd: Optional[Decimal] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "symbol": self.symbol,
            "name": self.name,
            "price_usd": str(self.price_usd),
            "change_1d_pct": str(self.change_1d_pct),
        }
        if self.market_cap_usd is not None:
            result["market_cap_usd"] = str(self.market_cap_usd)
        if self.volume_24h_usd is not None:
            result["volume_24h_usd"] = str(self.volume_24h_usd)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CryptoIndexData":
        return cls(
            symbol=data["symbol"],
            name=data["name"],
            price_usd=Decimal(data["price_usd"]),
            change_1d_pct=Decimal(data["change_1d_pct"]),
            market_cap_usd=Decimal(data["market_cap_usd"]) if data.get("market_cap_usd") else None,
            volume_24h_usd=Decimal(data["volume_24h_usd"]) if data.get("volume_24h_usd") else None,
        )


@dataclass(frozen=True)
class CryptoMarketData:
    """Crypto-specific market metrics.

    Optional fields - missing data does not break the bundle.
    """

    btc_dominance: Optional[Decimal] = None
    total_market_cap: Optional[Decimal] = None
    fear_greed_index: Optional[int] = None
    funding_rates: Optional[dict[str, Decimal]] = None
    open_interest: Optional[dict[str, Decimal]] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.btc_dominance is not None:
            result["btc_dominance"] = str(self.btc_dominance)
        if self.total_market_cap is not None:
            result["total_market_cap"] = str(self.total_market_cap)
        if self.fear_greed_index is not None:
            result["fear_greed_index"] = self.fear_greed_index
        if self.funding_rates is not None:
            # Use format(v, 'f') to avoid scientific notation (e.g., '-6.6E-7' -> '-0.00000066')
            result["funding_rates"] = {k: format(v, 'f') for k, v in self.funding_rates.items()}
        if self.open_interest is not None:
            result["open_interest"] = {k: format(v, 'f') for k, v in self.open_interest.items()}
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CryptoMarketData":
        funding_rates = None
        if data.get("funding_rates"):
            funding_rates = {k: Decimal(v) for k, v in data["funding_rates"].items()}

        open_interest = None
        if data.get("open_interest"):
            open_interest = {k: Decimal(v) for k, v in data["open_interest"].items()}

        return cls(
            btc_dominance=Decimal(data["btc_dominance"]) if data.get("btc_dominance") else None,
            total_market_cap=Decimal(data["total_market_cap"]) if data.get("total_market_cap") else None,
            fear_greed_index=data.get("fear_greed_index"),
            funding_rates=funding_rates,
            open_interest=open_interest,
        )


@dataclass(frozen=True)
class DeFiTVLSnapshot:
    """DeFi TVL snapshot data.

    This is a simplified version of the full DeFiLlama data.
    """

    total_tvl_usd: Decimal
    top_protocols: tuple[tuple[str, Decimal], ...]
    chain_breakdown: dict[str, Decimal]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tvl_usd": str(self.total_tvl_usd),
            "top_protocols": [[name, str(tvl)] for name, tvl in self.top_protocols],
            "chain_breakdown": {k: str(v) for k, v in self.chain_breakdown.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeFiTVLSnapshot":
        top_protocols = tuple(
            (name, Decimal(tvl_str)) for name, tvl_str in data.get("top_protocols", [])
        )
        chain_breakdown = {k: Decimal(v) for k, v in data.get("chain_breakdown", {}).items()}
        return cls(
            total_tvl_usd=Decimal(data["total_tvl_usd"]),
            top_protocols=top_protocols,
            chain_breakdown=chain_breakdown,
        )


@dataclass(frozen=True)
class CryptoMarketSnapshotBundle:
    """Complete crypto market snapshot for the facts bundle."""

    trading_date: date
    btc: CryptoIndexData
    eth: CryptoIndexData
    major_alts: tuple[CryptoIndexData, ...]
    crypto_metrics: Optional[CryptoMarketData] = None
    defi_tvl: Optional[DeFiTVLSnapshot] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "trading_date": self.trading_date.isoformat(),
            "btc": self.btc.to_dict(),
            "eth": self.eth.to_dict(),
            "major_alts": [alt.to_dict() for alt in self.major_alts],
        }
        if self.crypto_metrics is not None:
            result["crypto_metrics"] = self.crypto_metrics.to_dict()
        if self.defi_tvl is not None:
            result["defi_tvl"] = self.defi_tvl.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CryptoMarketSnapshotBundle":
        crypto_metrics = None
        if data.get("crypto_metrics"):
            crypto_metrics = CryptoMarketData.from_dict(data["crypto_metrics"])

        defi_tvl = None
        if data.get("defi_tvl"):
            defi_tvl = DeFiTVLSnapshot.from_dict(data["defi_tvl"])

        return cls(
            trading_date=date.fromisoformat(data["trading_date"]),
            btc=CryptoIndexData.from_dict(data["btc"]),
            eth=CryptoIndexData.from_dict(data["eth"]),
            major_alts=tuple(CryptoIndexData.from_dict(alt) for alt in data["major_alts"]),
            crypto_metrics=crypto_metrics,
            defi_tvl=defi_tvl,
        )


@dataclass(frozen=True)
class CryptoFactsBundle:
    """The complete crypto facts bundle - sole source of truth for the LLM.

    This is the immutable contract between the bundle builder and the generator.
    """

    version: str
    stream_name: str  # "crypto"
    run_mode: str  # "crypto_daily"
    generated_at: datetime
    trading_date: date
    market_snapshot: CryptoMarketSnapshotBundle
    news_items: tuple[NewsItemBundle, ...]
    calendar_events: tuple[CalendarEventBundle, ...]
    spotlight: Optional[SpotlightBundle] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "version": self.version,
            "stream_name": self.stream_name,
            "run_mode": self.run_mode,
            "generated_at": self.generated_at.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "market_snapshot": self.market_snapshot.to_dict(),
            "news_items": [item.to_dict() for item in self.news_items],
            "calendar_events": [event.to_dict() for event in self.calendar_events],
        }
        if self.spotlight is not None:
            result["spotlight"] = self.spotlight.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CryptoFactsBundle":
        spotlight = None
        if data.get("spotlight"):
            spotlight = SpotlightBundle.from_dict(data["spotlight"])
        return cls(
            version=data["version"],
            stream_name=data["stream_name"],
            run_mode=data["run_mode"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
            trading_date=date.fromisoformat(data["trading_date"]),
            market_snapshot=CryptoMarketSnapshotBundle.from_dict(data["market_snapshot"]),
            news_items=tuple(NewsItemBundle.from_dict(item) for item in data["news_items"]),
            calendar_events=tuple(
                CalendarEventBundle.from_dict(event) for event in data["calendar_events"]
            ),
            spotlight=spotlight,
        )


# =============================================================================
# Internal Selection Types
# =============================================================================


@dataclass
class BundleCandidate:
    """Internal type for news item selection with diversity tracking.

    Not frozen because we track selection state during processing.
    """

    news_item_id: int
    title: str
    source_name: str
    source_url: str
    published_at: Optional[datetime]
    ingested_at: datetime
    snippet: Optional[str]
    content_excerpt: Optional[str]
    topic: Optional[str]
    impact_score: int
    has_content: bool = False

    @property
    def effective_score(self) -> int:
        """Score used for ranking, with bonus for enriched content."""
        bonus = 5 if self.has_content else 0
        return self.impact_score + bonus

    def to_news_item_bundle(self) -> NewsItemBundle:
        """Convert to immutable NewsItemBundle for final output."""
        return NewsItemBundle(
            id=self.news_item_id,
            title=self.title,
            source_name=self.source_name,
            source_url=self.source_url,
            published_at=self.published_at,
            snippet=self.snippet,
            content_excerpt=self.content_excerpt,
            topic=self.topic,
            impact_score=self.impact_score,
        )


@dataclass
class BundleStats:
    """Statistics from a bundle building run."""

    total_candidates: int = 0
    selected_items: int = 0
    skipped_by_topic: int = 0
    skipped_by_source: int = 0
    enriched_items: int = 0
    calendar_events: int = 0
    has_spotlight: bool = False
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "selected_items": self.selected_items,
            "skipped_by_topic": self.skipped_by_topic,
            "skipped_by_source": self.skipped_by_source,
            "enriched_items": self.enriched_items,
            "calendar_events": self.calendar_events,
            "has_spotlight": self.has_spotlight,
            "duration_seconds": self.duration_seconds,
        }
