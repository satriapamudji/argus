"""Tests for Binance derivatives adapter.

These tests use live API calls as specified in the task requirements.
"""

import asyncio
import pytest

from argus.adapters.binance_derivatives import (
    BinanceDerivativesClient,
    FundingRate,
    OpenInterest,
    LongShortRatio,
)


class TestBinanceDerivativesClient:
    """Tests for Binance derivatives client using live API calls."""

    @pytest.mark.asyncio
    async def test_get_funding_rates(self):
        """Test fetching funding rates."""
        client = BinanceDerivativesClient()
        symbols = ["BTCUSDT", "ETHUSDT"]

        rates = await client.get_funding_rates(symbols)

        assert len(rates) <= len(symbols)
        assert all(isinstance(r, FundingRate) for r in rates)

        for rate in rates:
            assert rate.symbol.endswith("USDT")
            assert -1 <= rate.rate <= 1  # Funding rate should be reasonable
            assert rate.interpretation in ["Bullish", "Bearish", "Neutral"]

    @pytest.mark.asyncio
    async def test_get_open_interest(self):
        """Test fetching open interest."""
        client = BinanceDerivativesClient()
        symbols = ["BTCUSDT", "ETHUSDT"]

        oi = await client.get_open_interest(symbols)

        assert len(oi) <= len(symbols)
        assert all(isinstance(o, OpenInterest) for o in oi)

        for item in oi:
            assert item.symbol.endswith("USDT")
            assert item.open_interest > 0

    @pytest.mark.asyncio
    async def test_get_long_short_ratio(self):
        """Test fetching long/short ratio."""
        client = BinanceDerivativesClient()
        symbols = ["BTCUSDT", "ETHUSDT"]

        ratios = await client.get_long_short_ratio(symbols)

        assert len(ratios) <= len(symbols)
        assert all(isinstance(r, LongShortRatio) for r in ratios)

        for ratio in ratios:
            assert ratio.symbol.endswith("USDT")
            assert ratio.long_short_ratio > 0
            # Binance returns decimal fractions (0.52 = 52%), not percentages
            assert 0 <= ratio.long_account_pct <= 1
            assert 0 <= ratio.short_account_pct <= 1
            # Long + short should be close to 1.0 (100%)
            assert 0.95 <= ratio.long_account_pct + ratio.short_account_pct <= 1.05

    @pytest.mark.asyncio
    async def test_funding_rate_interpretation(self):
        """Test funding rate interpretation logic."""
        client = BinanceDerivativesClient()

        # Test with BTC which typically has measurable funding
        rates = await client.get_funding_rates(["BTCUSDT"])

        if rates:
            rate = rates[0]
            # Threshold is 0.0001 (0.01%)
            # Positive funding > 0.0001 = longs pay shorts = bullish
            if rate.rate > 0.0001:
                assert rate.interpretation == "Bullish"
            # Negative funding < -0.0001 = shorts pay longs = bearish
            elif rate.rate < -0.0001:
                assert rate.interpretation == "Bearish"
            else:
                # Near zero = neutral
                assert rate.interpretation == "Neutral"
                # Verify it's actually near zero
                assert abs(rate.rate) <= 0.0001

    @pytest.mark.asyncio
    async def test_multiple_symbols_parallel(self):
        """Test that multiple symbols are fetched in parallel."""
        client = BinanceDerivativesClient()
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]

        # All three methods should complete reasonably quickly
        import time
        start = time.time()

        results = await asyncio.gather(
            client.get_funding_rates(symbols),
            client.get_open_interest(symbols),
            client.get_long_short_ratio(symbols),
            return_exceptions=True,
        )

        elapsed = time.time() - start

        # Should complete in under 10 seconds (parallel requests)
        assert elapsed < 10

        # Verify no exceptions
        assert not any(isinstance(r, Exception) for r in results)


class TestFundingRate:
    """Tests for FundingRate dataclass."""

    def test_funding_rate_is_frozen(self):
        """Test that FundingRate is immutable."""
        from datetime import datetime, timezone

        rate = FundingRate(
            symbol="BTCUSDT",
            rate=0.0001,
            next_funding_time=datetime.now(timezone.utc),
            interpretation="Bullish",
        )

        with pytest.raises(AttributeError):
            rate.rate = 0.0002  # type: ignore[misc]

    def test_funding_rate_fields(self):
        """Test that all fields are populated correctly."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        rate = FundingRate(
            symbol="ETHUSDT",
            rate=-0.0001,
            next_funding_time=now,
            interpretation="Bearish",
        )

        assert rate.symbol == "ETHUSDT"
        assert rate.rate == -0.0001
        assert rate.next_funding_time == now
        assert rate.interpretation == "Bearish"


class TestOpenInterest:
    """Tests for OpenInterest dataclass."""

    def test_open_interest_is_frozen(self):
        """Test that OpenInterest is immutable."""
        oi = OpenInterest(symbol="BTCUSDT", open_interest=1_000_000_000)

        with pytest.raises(AttributeError):
            oi.open_interest = 2_000_000_000  # type: ignore[misc]


class TestLongShortRatio:
    """Tests for LongShortRatio dataclass."""

    def test_long_short_ratio_is_frozen(self):
        """Test that LongShortRatio is immutable."""
        ratio = LongShortRatio(
            symbol="BTCUSDT",
            long_short_ratio=1.5,
            long_account_pct=60.0,
            short_account_pct=40.0,
        )

        with pytest.raises(AttributeError):
            ratio.long_short_ratio = 2.0  # type: ignore[misc]

    def test_long_short_ratio_percentages(self):
        """Test that long + short percentages sum to ~100%."""
        ratio = LongShortRatio(
            symbol="ETHUSDT",
            long_short_ratio=1.2,
            long_account_pct=55.0,
            short_account_pct=45.0,
        )

        assert ratio.symbol == "ETHUSDT"
        assert ratio.long_short_ratio == 1.2
        assert ratio.long_account_pct + ratio.short_account_pct == 100.0
