"""Crypto facts bundle builder - orchestrates crypto bundle creation.

The builder is responsible for:
1. Fetching scored crypto news items from the database
2. Fetching crypto market data (CoinGecko, Fear & Greed, DeFiLlama, Binance)
3. Applying selection with diversity constraints
4. Assembling the complete crypto facts bundle
5. Validating the bundle against schema
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.adapters.binance_derivatives import (
    BinanceDerivativesClient,
    FundingRate,
    LongShortRatio,
    OpenInterest,
)
from argus.adapters.chartinspect import ChartInspectClient
from argus.adapters.coingecko import CoinGeckoClient, CryptoAsset
from argus.adapters.defillama import DeFiLlamaClient, DeFiTVLSnapshot
from argus.adapters.fear_greed import FearGreedIndex, get_fear_greed_index
from argus.config import ArgusConfig, CryptoStreamConfig
from argus.db.connection import get_connection
from argus.facts_bundle.schema import BUNDLE_SCHEMA_VERSION, validate_bundle
from argus.facts_bundle.selector import BundleSelector
from argus.facts_bundle.types import (
    BundleCandidate,
    BundleStats,
    CalendarEventBundle,
    CryptoFactsBundle,
    CryptoIndexData,
    CryptoMarketData,
    CryptoMarketSnapshotBundle,
    DeFiTVLSnapshot as BundleDeFiTVLSnapshot,
)


logger = logging.getLogger(__name__)


@dataclass
class CryptoBundleBuilderConfig:
    """Configuration for the crypto bundle builder."""

    stream_name: str = "crypto"
    run_mode: str = "crypto_daily"
    window_hours: int = 24
    min_items: int = 2
    max_items: int = 6
    max_per_topic: int = 1
    max_per_source: int = 2
    enriched_bonus: int = 5
    top_n_market_cap: int = 10
    always_include_symbols: list[str] | None = None
    exclude_symbols: list[str] | None = None
    chartinspect_api_key: str = ""

    def __post_init__(self):
        if self.always_include_symbols is None:
            self.always_include_symbols = ["BTC", "ETH"]
        if self.exclude_symbols is None:
            self.exclude_symbols = ["USDT", "USDC", "DAI"]

    @classmethod
    def from_argus_config(
        cls,
        config: ArgusConfig,
        run_mode: str = "crypto_daily",
        stream_name: Optional[str] = None,
    ) -> "CryptoBundleBuilderConfig":
        """Create builder config from ArgusConfig.

        Args:
            config: Main Argus configuration.
            run_mode: Run mode for the bundle (e.g., 'crypto_daily', 'crypto_weekly').
            stream_name: Optional stream name. If None, derives from run_mode
                       (e.g., 'crypto_daily' -> 'crypto') or falls back to config.stream.name.

        Returns:
            CryptoBundleBuilderConfig instance.
        """
        crypto_config: CryptoStreamConfig = config.stream.crypto

        # Determine stream name: explicit param -> derive from run_mode -> config default
        if stream_name is None:
            if run_mode.startswith("crypto_"):
                stream_name = "crypto"
            else:
                stream_name = config.stream.name

        return cls(
            stream_name=stream_name,
            run_mode=run_mode,
            window_hours=config.stream.scoring.window_hours,
            top_n_market_cap=crypto_config.top_n_market_cap,
            always_include_symbols=crypto_config.always_include_symbols,
            exclude_symbols=crypto_config.exclude_symbols,
            chartinspect_api_key=crypto_config.chartinspect_api_key,
        )


class CryptoFactsBundleBuilder:
    """Builds crypto facts bundles from database and external data.

    Usage:
        builder = CryptoFactsBundleBuilder(config)
        bundle, stats = builder.build()
    """

    def __init__(
        self,
        config: CryptoBundleBuilderConfig,
        conn: Optional[Connection] = None,
    ) -> None:
        """Initialize the crypto bundle builder.

        Args:
            config: Builder configuration.
            conn: Optional database connection (will create if not provided).
        """
        self.config = config
        self._conn = conn
        self._owns_connection = conn is None

        # Initialize crypto clients
        self._coingecko_client = CoinGeckoClient()
        self._binance_client = BinanceDerivativesClient()
        self._defillama_client = DeFiLlamaClient()
        self._chartinspect_client = ChartInspectClient(api_key=config.chartinspect_api_key)

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
            limit=100,
            stream_name=self.config.stream_name,
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

        logger.info(f"Fetched {len(candidates)} candidates for crypto bundle")
        return candidates

    def _convert_crypto_asset(self, asset: CryptoAsset) -> CryptoIndexData:
        """Convert CoinGecko CryptoAsset to CryptoIndexData."""
        return CryptoIndexData(
            symbol=asset.symbol,
            name=asset.name,
            price_usd=Decimal(str(asset.price_usd)),
            change_1d_pct=Decimal(str(asset.price_change_24h_pct)),
            market_cap_usd=Decimal(str(asset.market_cap_usd)),
            volume_24h_usd=Decimal(str(asset.volume_24h_usd)),
        )

    def _convert_defi_tvl(self, tvl: DeFiTVLSnapshot) -> BundleDeFiTVLSnapshot:
        """Convert adapter DeFiTVLSnapshot to bundle DeFiTVLSnapshot."""
        return BundleDeFiTVLSnapshot(
            total_tvl_usd=Decimal(str(tvl.total_tvl_usd)),
            top_protocols=tuple((name, Decimal(str(tvl))) for name, tvl in tvl.top_protocols),
            chain_breakdown={
                chain: Decimal(str(tvl)) for chain, tvl in tvl.chain_breakdown.items()
            },
        )

    async def _fetch_fear_greed(self) -> FearGreedIndex | None:
        """Fetch Fear & Greed Index."""
        try:
            return await get_fear_greed_index()
        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed Index: {e}")
            return None

    async def _fetch_defi_tvl(self) -> DeFiTVLSnapshot | None:
        """Fetch DeFi TVL from DeFiLlama."""
        try:
            return await self._defillama_client.get_tvl_snapshot()
        except Exception as e:
            logger.warning(f"Failed to fetch DeFi TVL: {e}")
            return None

    async def _fetch_derivatives(
        self, symbols: list[str]
    ) -> tuple[list[FundingRate], list[OpenInterest], list[LongShortRatio]]:
        """Fetch derivatives data from Binance.

        Args:
            symbols: List of base symbols (e.g., ["BTC", "ETH"]).

        Returns:
            Tuple of (funding_rates, open_interest, long_short_ratios).
        """
        # Convert to Binance symbols (e.g., "BTC" -> "BTCUSDT")
        binance_symbols = [f"{s}USDT" for s in symbols]

        try:
            results = await asyncio.gather(
                self._binance_client.get_funding_rates(binance_symbols),
                self._binance_client.get_open_interest(binance_symbols),
                self._binance_client.get_long_short_ratio(binance_symbols),
                return_exceptions=True,
            )

            # Handle exceptions and replace with empty lists
            funding_rates = results[0] if not isinstance(results[0], BaseException) else []
            open_interest = results[1] if not isinstance(results[1], BaseException) else []
            long_short_ratios = results[2] if not isinstance(results[2], BaseException) else []

            if isinstance(results[0], BaseException):
                logger.warning(f"Funding rates fetch failed: {results[0]}")
            if isinstance(results[1], BaseException):
                logger.warning(f"Open interest fetch failed: {results[1]}")
            if isinstance(results[2], BaseException):
                logger.warning(f"Long/short ratio fetch failed: {results[2]}")

            return funding_rates, open_interest, long_short_ratios

        except Exception as e:
            logger.warning(f"Failed to fetch derivatives data: {e}")
            return [], [], []

    async def _fetch_crypto_market_snapshot(self, trading_date: date) -> CryptoMarketSnapshotBundle:
        """Fetch crypto market data snapshot.

        Args:
            trading_date: Trading date for the snapshot.

        Returns:
            CryptoMarketSnapshotBundle with all crypto market data.
        """
        # Fetch top N assets by market cap
        assets = await self._coingecko_client.get_top_n_by_market_cap(
            n=self.config.top_n_market_cap,
            always_include=self.config.always_include_symbols,
            exclude=self.config.exclude_symbols,
        )

        if not assets:
            raise ValueError("No crypto assets fetched from CoinGecko")

        # Separate BTC, ETH, and major alts
        btc_asset = next((a for a in assets if a.symbol == "BTC"), None)
        eth_asset = next((a for a in assets if a.symbol == "ETH"), None)
        major_alts = [a for a in assets if a.symbol not in ["BTC", "ETH"]]

        if btc_asset is None:
            raise ValueError("BTC not found in top assets")
        if eth_asset is None:
            raise ValueError("ETH not found in top assets")

        # Fetch global market data
        global_data = await self._coingecko_client.get_global_market_data()

        # Fetch Fear & Greed, DeFi TVL, derivatives in parallel
        gather_results = await asyncio.gather(
            self._fetch_fear_greed(),
            self._fetch_defi_tvl(),
            self._fetch_derivatives([a.symbol for a in assets]),
            return_exceptions=True,
        )

        fear_greed = gather_results[0] if not isinstance(gather_results[0], BaseException) else None
        defi_tvl = gather_results[1] if not isinstance(gather_results[1], BaseException) else None
        derivatives = (
            gather_results[2] if not isinstance(gather_results[2], BaseException) else None
        )

        # Handle exceptions - log warnings
        if isinstance(gather_results[0], BaseException):
            logger.warning(f"Fear & Greed fetch failed: {gather_results[0]}")
        if isinstance(gather_results[1], BaseException):
            logger.warning(f"DeFi TVL fetch failed: {gather_results[1]}")
        if isinstance(gather_results[2], BaseException):
            logger.warning(f"Derivatives fetch failed: {gather_results[2]}")

        # Unpack derivatives if available
        if derivatives:
            funding_rates, open_interest, _ = derivatives
        else:
            funding_rates, open_interest = [], []

        # Build derivatives dict
        funding_dict = {
            fr.symbol.replace("USDT", ""): Decimal(str(fr.rate)) for fr in funding_rates
        }

        # Build price lookup dict for OI conversion (OI from Binance is in base asset, not USD)
        price_lookup = {a.symbol: Decimal(str(a.price_usd)) for a in assets}

        # Convert open interest to USD by multiplying by asset price
        oi_dict = {}
        for oi in open_interest:
            symbol = oi.symbol.replace("USDT", "")
            oi_value = Decimal(str(oi.open_interest))
            price_usd = price_lookup.get(symbol)

            if price_usd is not None:
                # OI from Binance is in base asset units (e.g., BTC), multiply by price to get USD
                oi_usd = oi_value * price_usd
                oi_dict[symbol] = oi_usd
            else:
                # No price data available, skip this symbol
                logger.debug(f"No price data for {symbol}, skipping OI conversion")

        # Build crypto metrics
        crypto_metrics = CryptoMarketData(
            btc_dominance=Decimal(str(global_data.btc_dominance_pct))
            if global_data.btc_dominance_pct
            else None,
            total_market_cap=Decimal(str(global_data.total_market_cap_usd))
            if global_data.total_market_cap_usd
            else None,
            fear_greed_index=fear_greed.value if fear_greed else None,
            funding_rates=funding_dict if funding_dict else None,
            open_interest=oi_dict if oi_dict else None,
        )

        # Convert DeFiTVLSnapshot if available
        converted_defi_tvl = self._convert_defi_tvl(defi_tvl) if defi_tvl else None

        return CryptoMarketSnapshotBundle(
            trading_date=trading_date,
            btc=self._convert_crypto_asset(btc_asset),
            eth=self._convert_crypto_asset(eth_asset),
            major_alts=tuple(self._convert_crypto_asset(a) for a in major_alts),
            crypto_metrics=crypto_metrics,
            defi_tvl=converted_defi_tvl,
        )

    def build(self, trading_date: Optional[date] = None) -> tuple[CryptoFactsBundle, BundleStats]:
        """Build a complete crypto facts bundle.

        Args:
            trading_date: Trading date for the bundle (defaults to today).

        Returns:
            Tuple of (CryptoFactsBundle, BundleStats).

        Raises:
            ValueError: If crypto market data cannot be fetched.
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
            logger.info(f"Selected {len(news_items)} news items for crypto bundle")

            # 2. Fetch crypto market snapshot (async)
            market_snapshot = asyncio.run(self._fetch_crypto_market_snapshot(trading_date))
            logger.info(f"Fetched crypto market snapshot for {trading_date}")

            # 3. Empty calendar events for crypto (not used yet)
            calendar_events: tuple[CalendarEventBundle, ...] = tuple()

            # 4. Assemble the bundle
            now = datetime.now(timezone.utc)
            bundle = CryptoFactsBundle(
                version=BUNDLE_SCHEMA_VERSION,
                stream_name=self.config.stream_name,
                run_mode=self.config.run_mode,
                generated_at=now,
                trading_date=trading_date,
                market_snapshot=market_snapshot,
                news_items=news_items,
                calendar_events=calendar_events,
            )

            # 5. Validate against schema
            bundle_dict = bundle.to_dict()
            validate_bundle(bundle_dict, raise_on_error=True)
            logger.info("Crypto bundle validated successfully")

            stats.duration_seconds = time.time() - start_time
            return bundle, stats

        finally:
            if self._owns_connection:
                self._close_connection()


def run_crypto_bundle(
    config: Optional[CryptoBundleBuilderConfig] = None,
    argus_config: Optional[ArgusConfig] = None,
    run_mode: str = "crypto_daily",
    trading_date: Optional[date] = None,
    conn: Optional[Connection] = None,
) -> tuple[CryptoFactsBundle, BundleStats]:
    """Convenience function to build a crypto facts bundle.

    Args:
        config: Optional explicit builder config.
        argus_config: Optional main Argus config (used if config not provided).
        run_mode: Run mode for the bundle.
        trading_date: Trading date (defaults to today).
        conn: Optional database connection.

    Returns:
        Tuple of (CryptoFactsBundle, BundleStats).
    """
    if config is None:
        if argus_config is None:
            argus_config = ArgusConfig.load()
        config = CryptoBundleBuilderConfig.from_argus_config(argus_config, run_mode)

    builder = CryptoFactsBundleBuilder(config=config, conn=conn)
    return builder.build(trading_date=trading_date)
