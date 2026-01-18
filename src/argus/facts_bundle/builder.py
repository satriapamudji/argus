"""Facts bundle builder - orchestrates bundle creation.

The builder is responsible for:
1. Fetching scored news items from the database
2. Fetching market data snapshot
3. Applying selection with diversity constraints
4. Assembling the complete facts bundle
5. Validating the bundle against schema
"""

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.adapters.market_data import (
    CrossAssetMetrics,
    IndexSnapshot,
    MarketDataProvider,
    MarketSnapshot,
)
from argus.config import ArgusConfig, EconomicCalendarConfig, SpotlightConfig
from argus.db.connection import get_connection
from argus.db.daily_market_snapshots import (
    get_daily_market_snapshots_in_range,
    get_last_daily_market_snapshot_before_date,
    upsert_daily_market_snapshot,
)
from argus.orchestrator.weekly_stats import compute_weekly_stats
from argus.facts_bundle.schema import BUNDLE_SCHEMA_VERSION, validate_bundle
from argus.facts_bundle.selector import BundleSelector
from argus.facts_bundle.types import (
    BundleCandidate,
    BundleStats,
    CalendarEventBundle,
    CrossAssetsData,
    FactsBundle,
    IndexData,
    MarketSnapshotBundle,
    SpotlightBundle,
    WeeklyStatsBundle,
)


def _previous_week_friday(reference_date: date) -> date:
    """Get the most recent Friday on or before reference_date."""
    days_since_friday = (reference_date.weekday() - 4) % 7
    return reference_date - timedelta(days=days_since_friday)


def _monday_of_week(reference_date: date) -> date:
    """Get Monday for the week containing reference_date."""
    return reference_date - timedelta(days=reference_date.weekday())


logger = logging.getLogger(__name__)


@dataclass
class BundleBuilderConfig:
    """Configuration for the bundle builder."""

    stream_name: str = "us_markets"
    run_mode: str = "us_close"
    persist_daily_snapshots: bool = False
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
        cls, config: ArgusConfig, run_mode: str = "us_close"
    ) -> "BundleBuilderConfig":
        """Create builder config from ArgusConfig.

        Args:
            config: Main Argus configuration.
            run_mode: Run mode for the bundle.

        Returns:
            BundleBuilderConfig instance.
        """
        spotlight = None
        if config.stream.spotlight.enabled:
            spotlight = config.stream.spotlight

        economic_calendar = None
        if config.stream.economic_calendar.enabled:
            economic_calendar = config.stream.economic_calendar

        # Use mode-specific window_hours for news lookup
        # weekend_wrap and monday_preview need longer windows (120h)
        # to cover the full trading week
        if run_mode in ("weekend_wrap", "monday_preview"):
            window_hours = 120
        else:
            window_hours = config.stream.scoring.window_hours

        return cls(
            stream_name=config.stream.name,
            run_mode=run_mode,
            window_hours=window_hours,
            spotlight=spotlight,
            economic_calendar=economic_calendar,
            persist_daily_snapshots=False,
            include_cross_assets=config.stream.include_cross_assets,
        )


class FactsBundleBuilder:
    """Builds facts bundles from database and external data.

    Usage:
        builder = FactsBundleBuilder(config)
        bundle, stats = builder.build()
    """

    def __init__(
        self,
        config: BundleBuilderConfig,
        conn: Optional[Connection] = None,
        market_provider: Optional[MarketDataProvider] = None,
    ) -> None:
        """Initialize the bundle builder.

        Args:
            config: Builder configuration.
            conn: Optional database connection (will create if not provided).
            market_provider: Optional market data provider.
        """
        self.config = config
        self._conn = conn
        self._owns_connection = conn is None
        self._market_provider = market_provider or MarketDataProvider(
            include_cross_assets=config.include_cross_assets
        )

    def _get_connection(self) -> Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = get_connection()
        return self._conn

    def _close_connection(self) -> None:
        """Close connection if we own it."""
        if self._owns_connection and self._conn is not None:
            self._conn.close()
            self._conn = None

    def _fetch_candidates(self, conn: Connection) -> list[BundleCandidate]:
        """Fetch scored news items as candidates.

        Args:
            conn: Database connection.

        Returns:
            List of BundleCandidate objects.
        """
        from argus.db.repository import get_scored_items_for_bundle

        rows = get_scored_items_for_bundle(
            conn=conn,
            window_hours=self.config.window_hours,
            limit=100,  # Fetch more than needed for selection
        )

        candidates = []
        for row in rows:
            candidate = BundleCandidate(
                news_item_id=row["id"],
                title=row["title"],
                source_name=row["source_name"],
                source_url=row["source_url"],
                published_at=row.get("published_at"),
                ingested_at=row["ingested_at"],
                snippet=row.get("snippet"),
                content_excerpt=row.get("content_excerpt"),
                topic=row.get("topic"),
                impact_score=row["impact_score"],
                has_content=row.get("has_content", False),
            )
            candidates.append(candidate)

        logger.info(f"Fetched {len(candidates)} candidates for bundle selection")
        return candidates

    def _convert_index_snapshot(self, snapshot: IndexSnapshot) -> IndexData:
        """Convert adapter IndexSnapshot to bundle IndexData."""
        return IndexData(
            name=snapshot.name,
            symbol=snapshot.symbol,
            level=snapshot.level,
            change_1d_pct=snapshot.change_1d_pct,
            change_1d_pts=snapshot.change_1d_pts,
        )

    def _convert_cross_assets(
        self, metrics: Optional[CrossAssetMetrics]
    ) -> Optional[CrossAssetsData]:
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

    def _fetch_market_snapshot(self, trading_date: date) -> MarketSnapshot:
        """Fetch market data snapshot.

        Returns the raw adapter MarketSnapshot so the caller can optionally persist it,
        while still being able to convert it into a MarketSnapshotBundle for the LLM.
        """
        return self._market_provider.fetch_snapshot(trading_date)

    def _to_market_snapshot_bundle(self, snapshot: MarketSnapshot) -> MarketSnapshotBundle:
        """Convert adapter MarketSnapshot to bundle MarketSnapshotBundle."""
        return MarketSnapshotBundle(
            trading_date=snapshot.trading_date,
            sp500=self._convert_index_snapshot(snapshot.sp500),
            dow=self._convert_index_snapshot(snapshot.dow),
            nasdaq=self._convert_index_snapshot(snapshot.nasdaq),
            cross_assets=self._convert_cross_assets(snapshot.cross_assets),
        )

    def _get_calendar_events(self, conn: Connection) -> tuple[CalendarEventBundle, ...]:
        """Get calendar events for the bundle.

        Uses EconomicCalendarAdapter to fetch upcoming events from the database.
        Auto-refreshes from ForexFactory if data is stale.

        Args:
            conn: Database connection.

        Returns:
            Tuple of CalendarEventBundle for upcoming events.
        """
        if self.config.economic_calendar is None:
            logger.debug("Economic calendar not configured")
            return tuple()

        try:
            from argus.adapters.economic_calendar import EconomicCalendarAdapter

            adapter = EconomicCalendarAdapter(
                conn=conn,
                config=self.config.economic_calendar,
            )
            events = adapter.get_upcoming_events(auto_refresh=True)
            logger.info(f"Fetched {len(events)} economic calendar events")
            return tuple(events)

        except Exception as e:
            logger.warning(f"Failed to fetch economic calendar events: {e}")
            return tuple()

    def _build_spotlight(self) -> Optional[SpotlightBundle]:
        """Build spotlight if configured.

        Returns:
            SpotlightBundle if spotlight is enabled and configured.
        """
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

    def build(self, trading_date: Optional[date] = None) -> tuple[FactsBundle, BundleStats]:
        """Build a complete facts bundle.

        Args:
            trading_date: Trading date for the bundle (defaults to today).

        Returns:
            Tuple of (FactsBundle, BundleStats).

        Raises:
            ValueError: If market data cannot be fetched.
            BundleValidationError: If bundle fails validation.
        """
        start_time = time.time()
        stats = BundleStats()

        if trading_date is None:
            trading_date = date.today()

        try:
            conn = self._get_connection()

            # 1. Fetch and select news items
            candidates = self._fetch_candidates(conn)
            stats.total_candidates = len(candidates)

            selector = BundleSelector(
                max_per_topic=self.config.max_per_topic,
                max_per_source=self.config.max_per_source,
                enriched_bonus=self.config.enriched_bonus,
            )
            selected = selector.select(
                candidates=candidates,
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

            # 2. Fetch market snapshot (and keep raw snapshot for persistence)
            raw_market_snapshot = self._fetch_market_snapshot(trading_date)
            logger.info(f"Fetched market snapshot for {trading_date}")

            market_snapshot = self._to_market_snapshot_bundle(raw_market_snapshot)

            # Persist daily snapshot (explicitly opt-in).
            if self.config.persist_daily_snapshots and self.config.run_mode == "us_close":
                cross = raw_market_snapshot.cross_assets
                upsert_daily_market_snapshot(
                    conn,
                    stream_name=self.config.stream_name,
                    trading_date=raw_market_snapshot.trading_date,
                    sp500_close=float(raw_market_snapshot.sp500.level),
                    sp500_change_pct=float(raw_market_snapshot.sp500.change_1d_pct),
                    dow_close=float(raw_market_snapshot.dow.level),
                    dow_change_pct=float(raw_market_snapshot.dow.change_1d_pct),
                    nasdaq_close=float(raw_market_snapshot.nasdaq.level),
                    nasdaq_change_pct=float(raw_market_snapshot.nasdaq.change_1d_pct),
                    vix_close=float(cross.vix_level)
                    if cross and cross.vix_level is not None
                    else None,
                    vix_change_pct=float(cross.vix_change_pct)
                    if cross and cross.vix_change_pct is not None
                    else None,
                    usd_dxy_close=float(cross.dxy_level)
                    if cross and cross.dxy_level is not None
                    else None,
                    usd_dxy_change_pct=float(cross.dxy_change_pct)
                    if cross and cross.dxy_change_pct is not None
                    else None,
                    us10y_yield=float(cross.us10y_yield)
                    if cross and cross.us10y_yield is not None
                    else None,
                    us10y_change_bp=float(cross.us10y_change_bps)
                    if cross and cross.us10y_change_bps is not None
                    else None,
                    wti_crude_close=float(cross.wti_level)
                    if cross and cross.wti_level is not None
                    else None,
                    wti_crude_change_pct=float(cross.wti_change_pct)
                    if cross and cross.wti_change_pct is not None
                    else None,
                    gold_close=float(cross.gold_level)
                    if cross and cross.gold_level is not None
                    else None,
                    gold_change_pct=float(cross.gold_change_pct)
                    if cross and cross.gold_change_pct is not None
                    else None,
                )

                # Note: legacy older persistence mapping removed.

            # 3. Get calendar events
            calendar_events = self._get_calendar_events(conn)
            stats.calendar_events = len(calendar_events)

            # 4. Build spotlight if configured
            spotlight = self._build_spotlight()
            stats.has_spotlight = spotlight is not None

            # 5. Compute weekly stats for recap/preview modes (DB-backed)
            weekly_stats_bundle: Optional[WeeklyStatsBundle] = None
            if self.config.run_mode in {"weekend_wrap", "monday_preview"}:
                # Target the most recently closed week (Mon..Fri).
                # Orchestrator trading_date for weekend_wrap is Friday; for monday_preview it's Monday.
                # This logic is resilient if trading_date is not aligned.
                if self.config.run_mode == "weekend_wrap":
                    week_end = _previous_week_friday(trading_date)
                else:
                    # monday_preview runs with trading_date = upcoming Monday; prior week ends previous Friday.
                    week_end = _previous_week_friday(trading_date - timedelta(days=1))

                week_start = _monday_of_week(week_end)

                week_rows = get_daily_market_snapshots_in_range(
                    conn=conn,
                    stream_name=self.config.stream_name,
                    start_date=week_start,
                    end_date=week_end,
                )
                prior_anchor = get_last_daily_market_snapshot_before_date(
                    conn=conn,
                    stream_name=self.config.stream_name,
                    before_date=week_start,
                )

                stats_obj = compute_weekly_stats(
                    week_start=week_start,
                    week_end=week_end,
                    week_snapshots=week_rows,
                    prior_anchor_snapshot=prior_anchor,
                )
                weekly_stats_bundle = WeeklyStatsBundle.from_weekly_stats(stats_obj)

            # 6. Assemble the bundle
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

            # 6. Validate against schema
            bundle_dict = bundle.to_dict()
            validate_bundle(bundle_dict, raise_on_error=True)
            logger.info("Bundle validated successfully")

            stats.duration_seconds = time.time() - start_time
            return bundle, stats

        finally:
            if self._owns_connection:
                self._close_connection()


def run_bundle(
    config: Optional[BundleBuilderConfig] = None,
    argus_config: Optional[ArgusConfig] = None,
    run_mode: str = "us_close",
    trading_date: Optional[date] = None,
    conn: Optional[Connection] = None,
) -> tuple[FactsBundle, BundleStats]:
    """Convenience function to build a facts bundle.

    Args:
        config: Optional explicit builder config.
        argus_config: Optional main Argus config (used if config not provided).
        run_mode: Run mode for the bundle.
        trading_date: Trading date (defaults to today).
        conn: Optional database connection.

    Returns:
        Tuple of (FactsBundle, BundleStats).
    """
    if config is None:
        if argus_config is None:
            argus_config = ArgusConfig.load()
        config = BundleBuilderConfig.from_argus_config(argus_config, run_mode)

    builder = FactsBundleBuilder(config=config, conn=conn)
    return builder.build(trading_date=trading_date)
