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
from datetime import date, datetime, timezone
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.adapters.market_data import (
    CrossAssetMetrics,
    IndexSnapshot,
    MarketDataProvider,
)
from argus.config import ArgusConfig, EconomicCalendarConfig, SpotlightConfig
from argus.db.connection import get_connection
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
)

logger = logging.getLogger(__name__)


@dataclass
class BundleBuilderConfig:
    """Configuration for the bundle builder."""

    stream_name: str = "us_close_basic"
    run_mode: str = "us_close"
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

        return cls(
            stream_name=config.stream.name,
            run_mode=run_mode,
            window_hours=config.stream.scoring.window_hours,
            spotlight=spotlight,
            economic_calendar=economic_calendar,
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

    def _fetch_market_snapshot(self, trading_date: date) -> MarketSnapshotBundle:
        """Fetch market data and convert to bundle format.

        Args:
            trading_date: The trading date for the snapshot.

        Returns:
            MarketSnapshotBundle with index data.
        """
        snapshot = self._market_provider.fetch_snapshot(trading_date)

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

            # 2. Fetch market snapshot
            market_snapshot = self._fetch_market_snapshot(trading_date)
            logger.info(f"Fetched market snapshot for {trading_date}")

            # 3. Get calendar events
            calendar_events = self._get_calendar_events(conn)
            stats.calendar_events = len(calendar_events)

            # 4. Build spotlight if configured
            spotlight = self._build_spotlight()
            stats.has_spotlight = spotlight is not None

            # 5. Assemble the bundle
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
