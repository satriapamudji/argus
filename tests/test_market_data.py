"""Tests for market data adapter."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from argus.adapters.market_data import (
    CrossAssetMetrics,
    IndexSnapshot,
    MarketDataProvider,
    MarketSnapshot,
    INDEX_SYMBOLS,
    CROSS_ASSET_SYMBOLS,
)


class TestIndexSnapshot:
    """Tests for IndexSnapshot dataclass."""

    def test_create_index_snapshot(self):
        """Test creating an IndexSnapshot."""
        now = datetime.now(timezone.utc)
        snapshot = IndexSnapshot(
            name="S&P 500",
            symbol="^GSPC",
            level=Decimal("5000.50"),
            change_1d_pct=Decimal("1.25"),
            change_1d_pts=Decimal("62.00"),
            as_of=now,
        )

        assert snapshot.name == "S&P 500"
        assert snapshot.symbol == "^GSPC"
        assert snapshot.level == Decimal("5000.50")
        assert snapshot.change_1d_pct == Decimal("1.25")
        assert snapshot.change_1d_pts == Decimal("62.00")
        assert snapshot.as_of == now

    def test_snapshot_is_frozen(self):
        """Test that IndexSnapshot is immutable."""
        now = datetime.now(timezone.utc)
        snapshot = IndexSnapshot(
            name="S&P 500",
            symbol="^GSPC",
            level=Decimal("5000.50"),
            change_1d_pct=Decimal("1.25"),
            change_1d_pts=Decimal("62.00"),
            as_of=now,
        )

        with pytest.raises(AttributeError):
            snapshot.level = Decimal("5100.00")  # type: ignore[misc]


class TestCrossAssetMetrics:
    """Tests for CrossAssetMetrics dataclass."""

    def test_create_empty_metrics(self):
        """Test creating CrossAssetMetrics with no data."""
        metrics = CrossAssetMetrics()

        assert metrics.vix_level is None
        assert metrics.us10y_yield is None
        assert metrics.dxy_level is None

    def test_create_partial_metrics(self):
        """Test creating CrossAssetMetrics with partial data."""
        now = datetime.now(timezone.utc)
        metrics = CrossAssetMetrics(
            vix_level=Decimal("18.50"),
            vix_change_pct=Decimal("-2.5"),
            gold_level=Decimal("2050.00"),
            as_of=now,
        )

        assert metrics.vix_level == Decimal("18.50")
        assert metrics.gold_level == Decimal("2050.00")
        assert metrics.us10y_yield is None


class TestMarketSnapshot:
    """Tests for MarketSnapshot dataclass."""

    def test_create_market_snapshot(self):
        """Test creating a complete MarketSnapshot."""
        now = datetime.now(timezone.utc)
        today = date.today()

        sp500 = IndexSnapshot(
            name="S&P 500",
            symbol="^GSPC",
            level=Decimal("5000.00"),
            change_1d_pct=Decimal("1.00"),
            change_1d_pts=Decimal("50.00"),
            as_of=now,
        )
        dow = IndexSnapshot(
            name="Dow Jones",
            symbol="^DJI",
            level=Decimal("39000.00"),
            change_1d_pct=Decimal("0.80"),
            change_1d_pts=Decimal("300.00"),
            as_of=now,
        )
        nasdaq = IndexSnapshot(
            name="Nasdaq",
            symbol="^IXIC",
            level=Decimal("16000.00"),
            change_1d_pct=Decimal("1.50"),
            change_1d_pts=Decimal("230.00"),
            as_of=now,
        )

        snapshot = MarketSnapshot(
            trading_date=today,
            sp500=sp500,
            dow=dow,
            nasdaq=nasdaq,
        )

        assert snapshot.trading_date == today
        assert snapshot.sp500.name == "S&P 500"
        assert snapshot.dow.name == "Dow Jones"
        assert snapshot.nasdaq.name == "Nasdaq"
        assert snapshot.cross_assets is None

    def test_snapshot_with_cross_assets(self):
        """Test MarketSnapshot with cross-asset data."""
        now = datetime.now(timezone.utc)
        today = date.today()

        sp500 = IndexSnapshot(
            name="S&P 500",
            symbol="^GSPC",
            level=Decimal("5000.00"),
            change_1d_pct=Decimal("1.00"),
            change_1d_pts=Decimal("50.00"),
            as_of=now,
        )
        dow = IndexSnapshot(
            name="Dow Jones",
            symbol="^DJI",
            level=Decimal("39000.00"),
            change_1d_pct=Decimal("0.80"),
            change_1d_pts=Decimal("300.00"),
            as_of=now,
        )
        nasdaq = IndexSnapshot(
            name="Nasdaq",
            symbol="^IXIC",
            level=Decimal("16000.00"),
            change_1d_pct=Decimal("1.50"),
            change_1d_pts=Decimal("230.00"),
            as_of=now,
        )
        cross = CrossAssetMetrics(
            vix_level=Decimal("18.00"),
            gold_level=Decimal("2100.00"),
        )

        snapshot = MarketSnapshot(
            trading_date=today,
            sp500=sp500,
            dow=dow,
            nasdaq=nasdaq,
            cross_assets=cross,
        )

        assert snapshot.cross_assets is not None
        assert snapshot.cross_assets.vix_level == Decimal("18.00")


class TestSymbolMappings:
    """Tests for ticker symbol constants."""

    def test_index_symbols_defined(self):
        """Test that all required index symbols are defined."""
        assert "sp500" in INDEX_SYMBOLS
        assert "dow" in INDEX_SYMBOLS
        assert "nasdaq" in INDEX_SYMBOLS

        assert INDEX_SYMBOLS["sp500"] == ("^GSPC", "S&P 500")
        assert INDEX_SYMBOLS["dow"] == ("^DJI", "Dow Jones")
        assert INDEX_SYMBOLS["nasdaq"] == ("^IXIC", "Nasdaq")

    def test_cross_asset_symbols_defined(self):
        """Test that cross-asset symbols are defined."""
        assert "vix" in CROSS_ASSET_SYMBOLS
        assert "us10y" in CROSS_ASSET_SYMBOLS
        assert "dxy" in CROSS_ASSET_SYMBOLS
        assert "wti" in CROSS_ASSET_SYMBOLS
        assert "gold" in CROSS_ASSET_SYMBOLS
        assert "silver" in CROSS_ASSET_SYMBOLS


class TestMarketDataProvider:
    """Tests for MarketDataProvider."""

    def test_init_default(self):
        """Test default initialization."""
        provider = MarketDataProvider()
        assert provider._include_cross_assets is False

    def test_init_with_cross_assets(self):
        """Test initialization with cross-assets enabled."""
        provider = MarketDataProvider(include_cross_assets=True)
        assert provider._include_cross_assets is True

    def test_lazy_load_yfinance(self):
        """Test that yfinance is lazy-loaded."""
        provider = MarketDataProvider()
        assert provider._yf is None

        # Calling _get_yfinance should load it
        yf = provider._get_yfinance()
        assert yf is not None
        assert provider._yf is not None

    @patch("argus.adapters.market_data.MarketDataProvider._get_yfinance")
    def test_fetch_index_snapshot_fast_info(self, mock_get_yf):
        """Test fetching index using fast_info."""
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.fast_info = {
            "last_price": 5000.0,
            "previous_close": 4950.0,
        }
        mock_yf.Ticker.return_value = mock_ticker
        mock_get_yf.return_value = mock_yf

        provider = MarketDataProvider()
        now = datetime.now(timezone.utc)

        snapshot = provider._fetch_index_snapshot("^GSPC", "S&P 500", now)

        assert snapshot is not None
        assert snapshot.name == "S&P 500"
        assert snapshot.symbol == "^GSPC"
        assert snapshot.level == Decimal("5000.0")
        # (5000 - 4950) / 4950 * 100 = 1.01%
        assert float(snapshot.change_1d_pct) == pytest.approx(1.01, rel=0.01)
        assert float(snapshot.change_1d_pts) == pytest.approx(50.0, rel=0.01)

    @patch("argus.adapters.market_data.MarketDataProvider._get_yfinance")
    def test_fetch_index_snapshot_fallback_history(self, mock_get_yf):
        """Test fetching index using history fallback."""
        import pandas as pd

        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        # fast_info returns None values to force fallback
        mock_ticker.fast_info = {"last_price": None, "previous_close": None}
        # History succeeds with proper indexed DataFrame
        mock_ticker.history.return_value = pd.DataFrame({"Close": pd.Series([4950.0, 5000.0])})
        mock_yf.Ticker.return_value = mock_ticker
        mock_get_yf.return_value = mock_yf

        provider = MarketDataProvider()
        now = datetime.now(timezone.utc)

        snapshot = provider._fetch_index_snapshot("^GSPC", "S&P 500", now)

        assert snapshot is not None
        assert snapshot.level == Decimal("5000.0")

    @patch("argus.adapters.market_data.MarketDataProvider._get_yfinance")
    def test_fetch_index_snapshot_failure(self, mock_get_yf):
        """Test handling fetch failure."""
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.fast_info = MagicMock(side_effect=Exception("Network error"))
        mock_ticker.history.return_value = MagicMock(empty=True)
        mock_yf.Ticker.return_value = mock_ticker
        mock_get_yf.return_value = mock_yf

        provider = MarketDataProvider()
        now = datetime.now(timezone.utc)

        snapshot = provider._fetch_index_snapshot("^GSPC", "S&P 500", now)

        assert snapshot is None

    @patch("argus.adapters.market_data.MarketDataProvider._fetch_index_snapshot")
    def test_fetch_snapshot_success(self, mock_fetch_index):
        """Test full snapshot fetch success."""

        def make_snapshot(symbol: str, name: str, as_of: datetime):
            return IndexSnapshot(
                name=name,
                symbol=symbol,
                level=Decimal("5000.00"),
                change_1d_pct=Decimal("1.00"),
                change_1d_pts=Decimal("50.00"),
                as_of=as_of,
            )

        mock_fetch_index.side_effect = make_snapshot

        provider = MarketDataProvider()
        snapshot = provider.fetch_snapshot()

        assert snapshot is not None
        assert snapshot.sp500 is not None
        assert snapshot.dow is not None
        assert snapshot.nasdaq is not None
        assert mock_fetch_index.call_count == 3

    @patch("argus.adapters.market_data.MarketDataProvider._fetch_index_snapshot")
    def test_fetch_snapshot_missing_required(self, mock_fetch_index):
        """Test fetch failure when required index is missing."""
        mock_fetch_index.return_value = None

        provider = MarketDataProvider()

        with pytest.raises(ValueError, match="Failed to fetch required index data"):
            provider.fetch_snapshot()
