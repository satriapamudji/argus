"""DB-free FactsBundle builder for trace module.

Builds a FactsBundle without database access by:
- Using RSS entries directly (ingested live)
- Using scoring functions (already pure)
- Using BundleSelector (already pure)
- Using MarketDataProvider.fetch_snapshot() (already DB-free)
- Using our DB-free calendar and weekly_stats helpers
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, Union

from argus.adapters.market_data import (
    CrossAssetMetrics,
    IndexSnapshot,
    MarketDataProvider,
    MarketSnapshot,
)
from argus.config import ArgusConfig, EconomicCalendarConfig, SpotlightConfig
from argus.facts_bundle.schema import BUNDLE_SCHEMA_VERSION, validate_bundle
from argus.facts_bundle.selector import BundleSelector
from argus.facts_bundle.types import (
    BundleCandidate,
    BundleStats,
    CalendarEventBundle,
    CrossAssetsData,
    CryptoFactsBundle,
    CryptoMarketSnapshotBundle,
    FactsBundle,
    IndexData,
    MarketSnapshotBundle,
    NewsItemBundle,
    SpotlightBundle,
    WeeklyStatsBundle,
)
from argus.ingestion.types import RSSEntry
from argus.scoring.types import ScoringCandidate, ScoringResult

from argus.trace.calendar import fetch_upcoming_events
from argus.trace.weekly_stats import fetch_weekly_stats

logger = logging.getLogger(__name__)


def synthetic_id(url: str) -> int:
    """Generate a synthetic ID from URL hash (since no DB)."""
    return int(hashlib.sha256(url.encode()).hexdigest()[:15], 16)


@dataclass
class TraceBundleConfig:
    """Configuration for trace bundle builder."""

    stream_name: str = "us_markets"
    run_mode: str = "us_close"
    scoring_version: str = "v2"
    window_hours: int = 24
    min_items: int = 2
    max_items: int = 6
    max_per_topic: int = 1
    max_per_source: int = 2
    enriched_bonus: int = 5
    include_cross_assets: bool = False
    spotlight: Optional[SpotlightConfig] = None
    economic_calendar: Optional[EconomicCalendarConfig] = None

    @classmethod
    def from_argus_config(
        cls,
        config: ArgusConfig,
        run_mode: str = "us_close",
        scoring_version: Optional[str] = None,
    ) -> "TraceBundleConfig":
        """Create from ArgusConfig.

        Args:
            config: Main Argus configuration.
            run_mode: Run mode for the bundle.
            scoring_version: Scoring version override (v2 or v3).

        Returns:
            TraceBundleConfig instance.
        """
        spotlight = None
        if config.stream.spotlight.enabled:
            spotlight = config.stream.spotlight

        economic_calendar = None
        if config.stream.economic_calendar.enabled:
            economic_calendar = config.stream.economic_calendar

        # Use mode-specific window_hours
        if run_mode in ("weekend_wrap", "monday_preview"):
            window_hours = 120
        else:
            window_hours = config.stream.scoring.window_hours

        # Determine scoring version
        if scoring_version is None:
            # Default: v3 for crypto, v2 for us_markets
            if config.stream.name == "crypto":
                scoring_version = "v3"
            else:
                scoring_version = "v2"

        return cls(
            stream_name=config.stream.name,
            run_mode=run_mode,
            scoring_version=scoring_version,
            window_hours=window_hours,
            spotlight=spotlight,
            economic_calendar=economic_calendar,
            include_cross_assets=config.stream.include_cross_assets,
        )


def rss_entry_to_scoring_candidate(entry: RSSEntry, feed_url: str) -> ScoringCandidate:
    """Convert RSS entry to ScoringCandidate for scoring."""
    news_item_id = synthetic_id(entry.source_url)
    return ScoringCandidate(
        news_item_id=news_item_id,
        fingerprint_id=news_item_id,  # Same synthetic ID
        source_name=entry.source_name,
        source_url=entry.source_url,
        title=entry.title,
        snippet=entry.snippet,
        published_at=entry.published_at,
        ingested_at=datetime.now(timezone.utc),
        feed_url=feed_url,
        author=entry.author,
    )


def scoring_result_to_bundle_candidate(
    result: ScoringResult,
    candidate: ScoringCandidate,
    content_excerpt: Optional[str] = None,
) -> BundleCandidate:
    """Convert ScoringResult + ScoringCandidate to BundleCandidate."""
    return BundleCandidate(
        news_item_id=result.news_item_id,
        title=candidate.title,
        source_name=candidate.source_name,
        source_url=candidate.source_url,
        published_at=candidate.published_at,
        ingested_at=candidate.ingested_at,
        snippet=candidate.snippet,
        content_excerpt=content_excerpt,
        topic=result.topic,
        impact_score=result.impact_score,
        has_content=content_excerpt is not None,
    )


def convert_index_snapshot(snapshot: IndexSnapshot) -> IndexData:
    """Convert adapter IndexSnapshot to bundle IndexData."""
    return IndexData(
        name=snapshot.name,
        symbol=snapshot.symbol,
        level=snapshot.level,
        change_1d_pct=snapshot.change_1d_pct,
        change_1d_pts=snapshot.change_1d_pts,
    )


def convert_cross_assets(metrics: Optional[CrossAssetMetrics]) -> Optional[CrossAssetsData]:
    """Convert adapter CrossAssetMetrics to bundle CrossAssetsData."""
    if metrics is None:
        return None
    return CrossAssetsData(
        vix_level=metrics.vix_level,
        vix_change_pct=metrics.vix_change_pct,
        us10y_yield=metrics.us10y_yield,
        us10y_change_bps=metrics.us10y_change_bps,
        dxy_level=metrics.dxy_level,
        dxy_change_pct=metrics.dxy_change_pct,
        wti_level=metrics.wti_level,
        wti_change_pct=metrics.wti_change_pct,
        gold_level=metrics.gold_level,
        gold_change_pct=metrics.gold_change_pct,
    )


def to_market_snapshot_bundle(snapshot: MarketSnapshot) -> MarketSnapshotBundle:
    """Convert adapter MarketSnapshot to bundle MarketSnapshotBundle."""
    return MarketSnapshotBundle(
        trading_date=snapshot.trading_date,
        sp500=convert_index_snapshot(snapshot.sp500),
        dow=convert_index_snapshot(snapshot.dow),
        nasdaq=convert_index_snapshot(snapshot.nasdaq),
        cross_assets=convert_cross_assets(snapshot.cross_assets),
    )


class TraceBundleBuilder:
    """DB-free bundle builder for trace mode.

    Builds a FactsBundle from:
    - Pre-fetched RSS entries
    - Pre-scored results
    - Live market data
    - Live economic calendar
    """

    def __init__(
        self,
        config: TraceBundleConfig,
        market_provider: Optional[MarketDataProvider] = None,
    ) -> None:
        """Initialize the trace bundle builder.

        Args:
            config: Builder configuration.
            market_provider: Optional market data provider.
        """
        self.config = config
        self._market_provider = market_provider or MarketDataProvider(
            include_cross_assets=config.include_cross_assets
        )

    def _build_spotlight(self) -> Optional[SpotlightBundle]:
        """Build spotlight if configured."""
        if self.config.spotlight is None or not self.config.spotlight.enabled:
            return None

        if not self.config.spotlight.title or not self.config.spotlight.body:
            logger.warning("Spotlight enabled but title/body not configured")
            return None

        return SpotlightBundle(
            title=self.config.spotlight.title,
            body=self.config.spotlight.body,
            disclaimer=self.config.spotlight.disclaimer or "",
        )

    def build(
        self,
        scored_candidates: list[tuple[ScoringResult, ScoringCandidate]],
        trading_date: Optional[date] = None,
    ) -> tuple[FactsBundle, BundleStats]:
        """Build a complete facts bundle.

        Args:
            scored_candidates: List of (ScoringResult, ScoringCandidate) tuples.
            trading_date: Trading date for the bundle (defaults to today).

        Returns:
            Tuple of (FactsBundle, BundleStats).

        Raises:
            ValueError: If market data cannot be fetched.
        """
        import time

        start_time = time.time()
        stats = BundleStats()

        if trading_date is None:
            trading_date = date.today()

        # 1. Convert to BundleCandidates
        bundle_candidates = [
            scoring_result_to_bundle_candidate(result, candidate)
            for result, candidate in scored_candidates
        ]
        stats.total_candidates = len(bundle_candidates)

        # 2. Select with diversity constraints
        selector = BundleSelector(
            max_per_topic=self.config.max_per_topic,
            max_per_source=self.config.max_per_source,
            enriched_bonus=self.config.enriched_bonus,
        )
        selected = selector.select(
            candidates=bundle_candidates,
            min_items=self.config.min_items,
            max_items=self.config.max_items,
        )

        selection_stats = selector.get_stats()
        stats.selected_items = selection_stats["selected"]
        stats.skipped_by_topic = selection_stats["skipped_by_topic"]
        stats.skipped_by_source = selection_stats["skipped_by_source"]
        stats.enriched_items = sum(1 for c in selected if c.has_content)

        # Convert to immutable NewsItemBundle
        news_items = tuple(c.to_news_item_bundle() for c in selected)
        logger.info(f"Selected {len(news_items)} news items for bundle")

        # 3. Fetch market snapshot
        raw_market_snapshot = self._market_provider.fetch_snapshot(trading_date)
        logger.info(f"Fetched market snapshot for {trading_date}")
        market_snapshot = to_market_snapshot_bundle(raw_market_snapshot)

        # 4. Get calendar events (DB-free)
        calendar_events: tuple[CalendarEventBundle, ...] = tuple()
        if self.config.economic_calendar is not None:
            try:
                events = fetch_upcoming_events(self.config.economic_calendar)
                calendar_events = tuple(events)
                logger.info(f"Fetched {len(calendar_events)} economic calendar events")
            except Exception as e:
                logger.warning(f"Failed to fetch economic calendar events: {e}")
        stats.calendar_events = len(calendar_events)

        # 5. Build spotlight
        spotlight = self._build_spotlight()
        stats.has_spotlight = spotlight is not None

        # 6. Compute weekly stats (DB-free)
        weekly_stats_bundle: Optional[WeeklyStatsBundle] = None
        if self.config.run_mode in {"weekend_wrap", "monday_preview"}:
            try:
                weekly_stats_bundle = fetch_weekly_stats(
                    run_mode=self.config.run_mode,
                    trading_date=trading_date,
                )
                if weekly_stats_bundle:
                    logger.info("Computed weekly stats from yfinance")
            except Exception as e:
                logger.warning(f"Failed to compute weekly stats: {e}")

        # 7. Assemble the bundle
        now = datetime.now(timezone.utc)
        bundle = FactsBundle(
            version=BUNDLE_SCHEMA_VERSION,
            stream_name=self.config.stream_name,
            run_mode=self.config.run_mode,
            generated_at=now,
            trading_date=trading_date,
            market_snapshot=market_snapshot,
            news_items=news_items,
            calendar_events=calendar_events,
            spotlight=spotlight,
            weekly_stats=weekly_stats_bundle,
        )

        # 8. Validate against schema
        bundle_dict = bundle.to_dict()
        validate_bundle(bundle_dict, raise_on_error=True)
        logger.info("Bundle validated successfully")

        stats.duration_seconds = time.time() - start_time
        return bundle, stats
