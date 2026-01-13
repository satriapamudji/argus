"""Market data provider for fetching US equity index snapshots.

Fetches real-time and historical market data for S&P 500, Dow Jones,
Nasdaq, and optional cross-asset metrics (VIX, rates, commodities).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoricalMetrics:
    """Historical market metrics for risk score calculation.

    Contains multi-day data needed to calculate market_score component
    of the risk score formula.

    Attributes:
        vix_current: Current VIX level.
        sp500_5d_return_pct: S&P 500 5-day return percentage.
        us10y_5d_move_bps: US 10Y yield 5-day absolute move in basis points.
        data_start: Start date of the historical window.
        data_end: End date of the historical window.
        fetched_at: When this data was fetched.
    """

    vix_current: Optional[Decimal] = None
    sp500_5d_return_pct: Optional[Decimal] = None
    us10y_5d_move_bps: Optional[Decimal] = None
    data_start: Optional[date] = None
    data_end: Optional[date] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class IndexSnapshot:
    """Snapshot of a single market index.

    Attributes:
        name: Display name of the index (e.g., "S&P 500").
        symbol: Ticker symbol (e.g., "^GSPC").
        level: Current/closing price level.
        change_1d_pct: 1-day percentage change vs prior close.
        change_1d_pts: 1-day point change vs prior close.
        as_of: Timestamp when the data was fetched/valid.
    """

    name: str
    symbol: str
    level: Decimal
    change_1d_pct: Decimal
    change_1d_pts: Decimal
    as_of: datetime


@dataclass(frozen=True)
class CrossAssetMetrics:
    """Optional cross-asset market metrics.

    All fields are optional - missing data does not break the facts bundle.

    Attributes:
        vix_level: VIX index level.
        vix_change_pct: VIX 1-day percentage change.
        us10y_yield: US 10-year Treasury yield (percentage points).
        us10y_change_bps: US 10Y yield change in basis points.
        dxy_level: US Dollar Index level.
        dxy_change_pct: DXY 1-day percentage change.
        wti_level: WTI crude oil price (USD per barrel).
        wti_change_pct: WTI 1-day percentage change.
        gold_level: Gold price (USD per troy ounce).
        gold_change_pct: Gold 1-day percentage change.
        silver_level: Silver price (USD per troy ounce).
        silver_change_pct: Silver 1-day percentage change.
        as_of: Timestamp when the data was fetched.
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
    silver_level: Optional[Decimal] = None
    silver_change_pct: Optional[Decimal] = None
    as_of: Optional[datetime] = None


@dataclass(frozen=True)
class MarketSnapshot:
    """Complete market snapshot for a trading day.

    Contains the three required US equity indices plus optional cross-asset data.

    Attributes:
        trading_date: The trading date this snapshot represents.
        sp500: S&P 500 index snapshot.
        dow: Dow Jones Industrial Average snapshot.
        nasdaq: Nasdaq Composite snapshot.
        cross_assets: Optional cross-asset metrics.
        fetched_at: When this snapshot was fetched.
    """

    trading_date: date
    sp500: IndexSnapshot
    dow: IndexSnapshot
    nasdaq: IndexSnapshot
    cross_assets: Optional[CrossAssetMetrics] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Ticker symbol mappings
INDEX_SYMBOLS = {
    "sp500": ("^GSPC", "S&P 500"),
    "dow": ("^DJI", "Dow Jones"),
    "nasdaq": ("^IXIC", "Nasdaq"),
}

CROSS_ASSET_SYMBOLS = {
    "vix": "^VIX",
    "us10y": "^TNX",
    "dxy": "DX-Y.NYB",
    "wti": "CL=F",
    "gold": "GC=F",
    "silver": "SI=F",
}


class MarketDataProvider:
    """Provider for fetching market data snapshots.

    Uses yfinance to fetch real-time and historical market data.
    Gracefully handles missing/unavailable data for optional fields.
    """

    def __init__(self, include_cross_assets: bool = False) -> None:
        """Initialize the market data provider.

        Args:
            include_cross_assets: Whether to fetch optional cross-asset metrics.
        """
        self._include_cross_assets = include_cross_assets
        self._yf: Optional[object] = None

    def _get_yfinance(self) -> object:
        """Lazy-load yfinance module.

        Returns:
            The yfinance module.

        Raises:
            ImportError: If yfinance is not installed.
        """
        if self._yf is None:
            try:
                import yfinance as yf

                self._yf = yf
            except ImportError as e:
                raise ImportError(
                    "yfinance is required for market data. Install with: pip install yfinance"
                ) from e
        return self._yf

    def _fetch_index_snapshot(
        self, symbol: str, name: str, as_of: datetime
    ) -> Optional[IndexSnapshot]:
        """Fetch snapshot for a single index.

        Args:
            symbol: Ticker symbol (e.g., "^GSPC").
            name: Display name (e.g., "S&P 500").
            as_of: Timestamp for the snapshot.

        Returns:
            IndexSnapshot if data is available, None otherwise.
        """
        yf = self._get_yfinance()

        try:
            ticker = yf.Ticker(symbol)  # type: ignore[attr-defined]

            # Try fast_info first for efficiency
            try:
                fast_info = ticker.fast_info
                current_price = fast_info.get("last_price") or fast_info.get("lastPrice")
                prev_close = fast_info.get("previous_close") or fast_info.get("previousClose")

                if current_price is not None and prev_close is not None:
                    change_pts = float(current_price) - float(prev_close)
                    change_pct = (change_pts / float(prev_close)) * 100.0

                    return IndexSnapshot(
                        name=name,
                        symbol=symbol,
                        level=Decimal(str(round(current_price, 2))),
                        change_1d_pct=Decimal(str(round(change_pct, 2))),
                        change_1d_pts=Decimal(str(round(change_pts, 2))),
                        as_of=as_of,
                    )
            except (AttributeError, KeyError, TypeError):
                pass  # Fall through to history method

            # Fallback: use history
            hist = ticker.history(period="2d")

            if hist.empty or len(hist) < 2:
                logger.warning(f"Insufficient history data for {symbol}")
                return None

            prev_close = float(hist["Close"].iloc[-2])
            current_close = float(hist["Close"].iloc[-1])
            change_pts = current_close - prev_close
            change_pct = (change_pts / prev_close) * 100.0

            return IndexSnapshot(
                name=name,
                symbol=symbol,
                level=Decimal(str(round(current_close, 2))),
                change_1d_pct=Decimal(str(round(change_pct, 2))),
                change_1d_pts=Decimal(str(round(change_pts, 2))),
                as_of=as_of,
            )

        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")
            return None

    def _fetch_cross_assets(self, as_of: datetime) -> Optional[CrossAssetMetrics]:
        """Fetch optional cross-asset metrics.

        Args:
            as_of: Timestamp for the data.

        Returns:
            CrossAssetMetrics with available data, None if all fetches fail.
        """
        yf = self._get_yfinance()
        metrics: dict[str, Optional[Decimal]] = {}

        for asset_key, symbol in CROSS_ASSET_SYMBOLS.items():
            try:
                ticker = yf.Ticker(symbol)  # type: ignore[attr-defined]
                hist = ticker.history(period="2d")

                if hist.empty or len(hist) < 2:
                    logger.debug(f"No data for {asset_key} ({symbol})")
                    continue

                prev_close = float(hist["Close"].iloc[-2])
                current = float(hist["Close"].iloc[-1])
                change_pct = ((current - prev_close) / prev_close) * 100.0

                # Handle different metric types
                if asset_key == "us10y":
                    # Treasury yield is already in percentage points
                    # Change is in basis points (bps)
                    change_bps = (current - prev_close) * 100.0
                    metrics["us10y_yield"] = Decimal(str(round(current, 3)))
                    metrics["us10y_change_bps"] = Decimal(str(round(change_bps, 1)))
                elif asset_key == "vix":
                    metrics["vix_level"] = Decimal(str(round(current, 2)))
                    metrics["vix_change_pct"] = Decimal(str(round(change_pct, 2)))
                elif asset_key == "dxy":
                    metrics["dxy_level"] = Decimal(str(round(current, 2)))
                    metrics["dxy_change_pct"] = Decimal(str(round(change_pct, 2)))
                elif asset_key == "wti":
                    metrics["wti_level"] = Decimal(str(round(current, 2)))
                    metrics["wti_change_pct"] = Decimal(str(round(change_pct, 2)))
                elif asset_key == "gold":
                    metrics["gold_level"] = Decimal(str(round(current, 2)))
                    metrics["gold_change_pct"] = Decimal(str(round(change_pct, 2)))
                elif asset_key == "silver":
                    metrics["silver_level"] = Decimal(str(round(current, 2)))
                    metrics["silver_change_pct"] = Decimal(str(round(change_pct, 2)))

            except Exception as e:
                logger.debug(f"Failed to fetch {asset_key} ({symbol}): {e}")
                continue

        if not metrics:
            return None

        return CrossAssetMetrics(
            vix_level=metrics.get("vix_level"),
            vix_change_pct=metrics.get("vix_change_pct"),
            us10y_yield=metrics.get("us10y_yield"),
            us10y_change_bps=metrics.get("us10y_change_bps"),
            dxy_level=metrics.get("dxy_level"),
            dxy_change_pct=metrics.get("dxy_change_pct"),
            wti_level=metrics.get("wti_level"),
            wti_change_pct=metrics.get("wti_change_pct"),
            gold_level=metrics.get("gold_level"),
            gold_change_pct=metrics.get("gold_change_pct"),
            silver_level=metrics.get("silver_level"),
            silver_change_pct=metrics.get("silver_change_pct"),
            as_of=as_of,
        )

    def _fetch_cross_assets_for_date(self, trading_date: date) -> Optional[CrossAssetMetrics]:
        """Fetch cross-asset metrics for a specific trading date.

        Uses a small historical window to derive the close and 1-day change.
        """
        yf = self._get_yfinance()
        metrics: dict[str, Optional[Decimal]] = {}

        start = trading_date - timedelta(days=7)
        end = trading_date + timedelta(days=1)

        for asset_key, symbol in CROSS_ASSET_SYMBOLS.items():
            try:
                ticker = yf.Ticker(symbol)  # type: ignore[attr-defined]
                hist = ticker.history(start=start, end=end)

                if hist.empty:
                    logger.debug(f"No data for {asset_key} ({symbol}) on {trading_date}")
                    continue

                hist = hist[~hist["Close"].isna()].sort_index()
                hist = hist[hist.index.date <= trading_date]
                if hist.empty:
                    logger.debug(f"No close for {asset_key} ({symbol}) on {trading_date}")
                    continue

                current = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
                change_pct = (
                    ((current - prev_close) / prev_close) * 100.0 if prev_close else None
                )

                if asset_key == "us10y":
                    change_bps = (current - prev_close) * 100.0 if prev_close else None
                    metrics["us10y_yield"] = Decimal(str(round(current, 3)))
                    metrics["us10y_change_bps"] = (
                        Decimal(str(round(change_bps, 1))) if change_bps is not None else None
                    )
                elif asset_key == "vix":
                    metrics["vix_level"] = Decimal(str(round(current, 2)))
                    metrics["vix_change_pct"] = (
                        Decimal(str(round(change_pct, 2))) if change_pct is not None else None
                    )
                elif asset_key == "dxy":
                    metrics["dxy_level"] = Decimal(str(round(current, 2)))
                    metrics["dxy_change_pct"] = (
                        Decimal(str(round(change_pct, 2))) if change_pct is not None else None
                    )
                elif asset_key == "wti":
                    metrics["wti_level"] = Decimal(str(round(current, 2)))
                    metrics["wti_change_pct"] = (
                        Decimal(str(round(change_pct, 2))) if change_pct is not None else None
                    )
                elif asset_key == "gold":
                    metrics["gold_level"] = Decimal(str(round(current, 2)))
                    metrics["gold_change_pct"] = (
                        Decimal(str(round(change_pct, 2))) if change_pct is not None else None
                    )
                elif asset_key == "silver":
                    metrics["silver_level"] = Decimal(str(round(current, 2)))
                    metrics["silver_change_pct"] = (
                        Decimal(str(round(change_pct, 2))) if change_pct is not None else None
                    )

            except Exception as e:
                logger.debug(f"Failed to fetch {asset_key} ({symbol}) on {trading_date}: {e}")
                continue

        if not metrics:
            return None

        return CrossAssetMetrics(
            vix_level=metrics.get("vix_level"),
            vix_change_pct=metrics.get("vix_change_pct"),
            us10y_yield=metrics.get("us10y_yield"),
            us10y_change_bps=metrics.get("us10y_change_bps"),
            dxy_level=metrics.get("dxy_level"),
            dxy_change_pct=metrics.get("dxy_change_pct"),
            wti_level=metrics.get("wti_level"),
            wti_change_pct=metrics.get("wti_change_pct"),
            gold_level=metrics.get("gold_level"),
            gold_change_pct=metrics.get("gold_change_pct"),
            silver_level=metrics.get("silver_level"),
            silver_change_pct=metrics.get("silver_change_pct"),
            as_of=datetime.now(timezone.utc),
        )

    def fetch_cross_assets_for_date(self, trading_date: date) -> Optional[CrossAssetMetrics]:
        """Public wrapper for fetching cross-asset metrics for a trading date."""
        return self._fetch_cross_assets_for_date(trading_date)

    def fetch_snapshot(self, trading_date: Optional[date] = None) -> MarketSnapshot:
        """Fetch a complete market snapshot.

        Args:
            trading_date: The trading date for the snapshot.
                          Defaults to today's date.

        Returns:
            MarketSnapshot with index data and optional cross-assets.

        Raises:
            ValueError: If required index data cannot be fetched.
        """
        if trading_date is None:
            trading_date = date.today()

        now = datetime.now(timezone.utc)

        # Fetch required indices
        sp500 = self._fetch_index_snapshot(
            INDEX_SYMBOLS["sp500"][0], INDEX_SYMBOLS["sp500"][1], now
        )
        dow = self._fetch_index_snapshot(INDEX_SYMBOLS["dow"][0], INDEX_SYMBOLS["dow"][1], now)
        nasdaq = self._fetch_index_snapshot(
            INDEX_SYMBOLS["nasdaq"][0], INDEX_SYMBOLS["nasdaq"][1], now
        )

        # Validate required data - all three indices must be present
        if sp500 is None or dow is None or nasdaq is None:
            missing = []
            if sp500 is None:
                missing.append("S&P 500")
            if dow is None:
                missing.append("Dow Jones")
            if nasdaq is None:
                missing.append("Nasdaq")
            raise ValueError(f"Failed to fetch required index data: {', '.join(missing)}")

        # Fetch optional cross-assets
        cross_assets = None
        if self._include_cross_assets:
            # Use a date-based window to improve reliability (some Yahoo tickers return
            # sparse/partial 2d history at runtime, which can lead to missing fields).
            cross_assets = self._fetch_cross_assets_for_date(trading_date)

        return MarketSnapshot(
            trading_date=trading_date,
            sp500=sp500,
            dow=dow,
            nasdaq=nasdaq,
            cross_assets=cross_assets,
            fetched_at=now,
        )

    def fetch_historical(self, days: int = 7) -> HistoricalMetrics:
        """Fetch historical market data for risk score calculation.

        Fetches multi-day data to calculate:
        - Current VIX level
        - S&P 500 5-day return
        - US 10Y yield 5-day absolute move

        Args:
            days: Number of days of history to fetch (default 7 for buffer).

        Returns:
            HistoricalMetrics with available data.

        Note:
            Missing data is tolerated - fields will be None if unavailable.
            The risk score calculator should handle None gracefully.
        """
        yf = self._get_yfinance()
        now = datetime.now(timezone.utc)

        # We need at least 5 trading days, fetch extra for buffer
        period = f"{days}d"

        vix_current: Optional[Decimal] = None
        sp500_5d_return_pct: Optional[Decimal] = None
        us10y_5d_move_bps: Optional[Decimal] = None
        data_start: Optional[date] = None
        data_end: Optional[date] = None

        # Fetch VIX current level
        try:
            vix_ticker = yf.Ticker(CROSS_ASSET_SYMBOLS["vix"])  # type: ignore[attr-defined]
            vix_hist = vix_ticker.history(period=period)

            if not vix_hist.empty:
                vix_current = Decimal(str(round(float(vix_hist["Close"].iloc[-1]), 2)))
                logger.debug(f"VIX current: {vix_current}")
        except Exception as e:
            logger.warning(f"Failed to fetch VIX history: {e}")

        # Fetch S&P 500 for 5-day return
        try:
            sp500_ticker = yf.Ticker(INDEX_SYMBOLS["sp500"][0])  # type: ignore[attr-defined]
            sp500_hist = sp500_ticker.history(period=period)

            if not sp500_hist.empty and len(sp500_hist) >= 5:
                # 5-day return: (current - 5 days ago) / 5 days ago * 100
                current_close = float(sp500_hist["Close"].iloc[-1])
                close_5d_ago = float(sp500_hist["Close"].iloc[-6])  # -6 because -1 is today
                return_pct = ((current_close - close_5d_ago) / close_5d_ago) * 100.0
                sp500_5d_return_pct = Decimal(str(round(return_pct, 2)))

                # Track data range
                data_start = sp500_hist.index[0].date()
                data_end = sp500_hist.index[-1].date()
                logger.debug(f"S&P 500 5D return: {sp500_5d_return_pct}%")
            elif not sp500_hist.empty and len(sp500_hist) >= 2:
                # Less than 5 days available, use what we have
                current_close = float(sp500_hist["Close"].iloc[-1])
                oldest_close = float(sp500_hist["Close"].iloc[0])
                return_pct = ((current_close - oldest_close) / oldest_close) * 100.0
                sp500_5d_return_pct = Decimal(str(round(return_pct, 2)))
                data_start = sp500_hist.index[0].date()
                data_end = sp500_hist.index[-1].date()
                logger.debug(f"S&P 500 {len(sp500_hist)}D return (partial): {sp500_5d_return_pct}%")
        except Exception as e:
            logger.warning(f"Failed to fetch S&P 500 history: {e}")

        # Fetch US 10Y yield for 5-day move
        try:
            us10y_ticker = yf.Ticker(CROSS_ASSET_SYMBOLS["us10y"])  # type: ignore[attr-defined]
            us10y_hist = us10y_ticker.history(period=period)

            if not us10y_hist.empty and len(us10y_hist) >= 5:
                # 5-day absolute move in basis points
                current_yield = float(us10y_hist["Close"].iloc[-1])
                yield_5d_ago = float(us10y_hist["Close"].iloc[-6])
                move_bps = abs(current_yield - yield_5d_ago) * 100.0  # Convert to bps
                us10y_5d_move_bps = Decimal(str(round(move_bps, 1)))
                logger.debug(f"US 10Y 5D move: {us10y_5d_move_bps} bps")
            elif not us10y_hist.empty and len(us10y_hist) >= 2:
                # Less than 5 days available
                current_yield = float(us10y_hist["Close"].iloc[-1])
                oldest_yield = float(us10y_hist["Close"].iloc[0])
                move_bps = abs(current_yield - oldest_yield) * 100.0
                us10y_5d_move_bps = Decimal(str(round(move_bps, 1)))
                logger.debug(f"US 10Y {len(us10y_hist)}D move (partial): {us10y_5d_move_bps} bps")
        except Exception as e:
            logger.warning(f"Failed to fetch US 10Y history: {e}")

        return HistoricalMetrics(
            vix_current=vix_current,
            sp500_5d_return_pct=sp500_5d_return_pct,
            us10y_5d_move_bps=us10y_5d_move_bps,
            data_start=data_start,
            data_end=data_end,
            fetched_at=now,
        )
