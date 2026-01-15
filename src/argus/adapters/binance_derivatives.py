"""Binance derivatives adapter for crypto futures data.

Fetches funding rates, open interest, and long/short ratios for USDT-margined futures.
Uses Binance FAPI (futures API) - no authentication required for public data.

API endpoints:
- /fapi/v1/fundingRate - Funding rates
- /fapi/v1/openInterest - Open interest
- /futures/data/globalLongShortAccountRatio - Long/short ratio
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
BASE_URL = "https://fapi.binance.com"


@dataclass(frozen=True)
class FundingRate:
    """Perpetual futures funding rate data.

    Attributes:
        symbol: Trading pair symbol (e.g., "BTCUSDT").
        rate: Funding rate (0.0001 = 0.01%).
        next_funding_time: UTC timestamp of next funding.
        interpretation: "Bullish" (longs pay shorts), "Bearish" (shorts pay longs),
                       or "Neutral" (near zero).
    """

    symbol: str
    rate: float
    next_funding_time: datetime
    interpretation: str


@dataclass(frozen=True)
class OpenInterest:
    """Open interest data.

    Attributes:
        symbol: Trading pair symbol.
        open_interest: Total open interest in USDT.
    """

    symbol: str
    open_interest: float


@dataclass(frozen=True)
class LongShortRatio:
    """Long/short ratio data.

    Attributes:
        symbol: Trading pair symbol.
        long_short_ratio: Ratio of long to short positions (>1 = more longs).
        long_account_pct: Percentage of accounts with long positions.
        short_account_pct: Percentage of accounts with short positions.
    """

    symbol: str
    long_short_ratio: float
    long_account_pct: float
    short_account_pct: float


@dataclass(frozen=True)
class BinanceDerivativesSnapshot:
    """Complete derivatives snapshot for multiple symbols.

    Attributes:
        funding_rates: List of funding rates by symbol.
        open_interest: List of open interest by symbol.
        long_short_ratios: List of long/short ratios by symbol.
    """

    funding_rates: list[FundingRate]
    open_interest: list[OpenInterest]
    long_short_ratios: list[LongShortRatio]


class BinanceDerivativesError(Exception):
    """Base exception for Binance derivatives adapter errors."""


class BinanceDerivativesClient:
    """Binance FAPI client for derivatives data.

    No API key required for public endpoints.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the Binance derivatives client.

        Args:
            base_url: API base URL.
            timeout_seconds: HTTP request timeout.
        """
        self.base_url = base_url
        self.timeout = timeout_seconds

    async def get_funding_rates(
        self,
        symbols: list[str],
        limit: int = 1,
    ) -> list[FundingRate]:
        """Fetch funding rates for the given symbols.

        Args:
            symbols: List of trading pair symbols (e.g., ["BTCUSDT", "ETHUSDT"]).
            limit: Number of historical records to fetch (default: 1 for latest).

        Returns:
            List of FundingRate objects.

        Raises:
            BinanceDerivativesError: If the API request fails.
        """
        results: list[FundingRate] = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for symbol in symbols:
                try:
                    params = {"symbol": symbol, "limit": limit}
                    response = await client.get(
                        f"{self.base_url}/fapi/v1/fundingRate",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if not isinstance(data, list) or not data:
                        continue

                    latest = data[-1]  # Get most recent
                    rate = float(latest.get("fundingRate", 0))
                    next_funding_time = datetime.fromtimestamp(
                        int(latest.get("fundingTime", 0)) / 1000,
                        tz=timezone.utc,
                    )

                    # Determine interpretation
                    if rate > 0.0001:  # > 0.01% = shorts pay longs = bullish
                        interpretation = "Bullish"
                    elif rate < -0.0001:  # < -0.01% = longs pay shorts = bearish
                        interpretation = "Bearish"
                    else:
                        interpretation = "Neutral"

                    results.append(
                        FundingRate(
                            symbol=symbol,
                            rate=rate,
                            next_funding_time=next_funding_time,
                            interpretation=interpretation,
                        )
                    )

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400:
                        # Symbol may not have USDT-margined perpetuals
                        logger.debug(f"Symbol {symbol} not available on Binance futures")
                        continue
                    raise
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse funding rate for {symbol}: {e}")
                    continue

        return results

    async def get_open_interest(
        self,
        symbols: list[str],
    ) -> list[OpenInterest]:
        """Fetch open interest for the given symbols.

        Args:
            symbols: List of trading pair symbols.

        Returns:
            List of OpenInterest objects.

        Raises:
            BinanceDerivativesError: If the API request fails.
        """
        results: list[OpenInterest] = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for symbol in symbols:
                try:
                    params = {"symbol": symbol}
                    response = await client.get(
                        f"{self.base_url}/fapi/v1/openInterest",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()

                    open_interest = float(data.get("openInterest", 0))
                    results.append(
                        OpenInterest(
                            symbol=symbol,
                            open_interest=open_interest,
                        )
                    )

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400:
                        logger.debug(f"Symbol {symbol} not available on Binance futures")
                        continue
                    raise
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse open interest for {symbol}: {e}")
                    continue

        return results

    async def get_long_short_ratio(
        self,
        symbols: list[str],
        period: str = "1d",
        limit: int = 2,
    ) -> list[LongShortRatio]:
        """Fetch long/short account ratio for the given symbols.

        Args:
            symbols: List of trading pair symbols.
            period: Time period (1d, 1h, etc.).
            limit: Number of historical records.

        Returns:
            List of LongShortRatio objects.

        Raises:
            BinanceDerivativesError: If the API request fails.
        """
        results: list[LongShortRatio] = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for symbol in symbols:
                try:
                    params = {"symbol": symbol, "period": period, "limit": limit}
                    response = await client.get(
                        f"{self.base_url}/futures/data/globalLongShortAccountRatio",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if not isinstance(data, list) or not data:
                        continue

                    latest = data[-1]  # Get most recent
                    long_short_ratio = float(latest.get("longShortRatio", 0))
                    long_account_pct = float(latest.get("longAccount", 0))
                    short_account_pct = float(latest.get("shortAccount", 0))

                    results.append(
                        LongShortRatio(
                            symbol=symbol,
                            long_short_ratio=long_short_ratio,
                            long_account_pct=long_account_pct,
                            short_account_pct=short_account_pct,
                        )
                    )

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400:
                        logger.debug(f"Symbol {symbol} not available on Binance futures")
                        continue
                    raise
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse long/short ratio for {symbol}: {e}")
                    continue

        return results

    async def get_all_derivatives_data(
        self,
        symbols: list[str],
    ) -> BinanceDerivativesSnapshot:
        """Fetch all derivatives data for the given symbols.

        Args:
            symbols: List of trading pair symbols.

        Returns:
            BinanceDerivativesSnapshot with all data.
        """
        # Fetch all data in parallel
        funding_rates_task = self.get_funding_rates(symbols)
        open_interest_task = self.get_open_interest(symbols)
        long_short_task = self.get_long_short_ratio(symbols)

        results = await asyncio.gather(
            funding_rates_task,
            open_interest_task,
            long_short_task,
            return_exceptions=True,
        )

        # Handle any exceptions - BaseException is what gather returns
        funding_rates_result: list[FundingRate] | BaseException = results[0]
        open_interest_result: list[OpenInterest] | BaseException = results[1]
        long_short_result: list[LongShortRatio] | BaseException = results[2]

        if isinstance(funding_rates_result, BaseException):
            logger.error(f"Funding rates error: {funding_rates_result}")
            funding_rates: list[FundingRate] = []
        else:
            funding_rates = funding_rates_result

        if isinstance(open_interest_result, BaseException):
            logger.error(f"Open interest error: {open_interest_result}")
            open_interest: list[OpenInterest] = []
        else:
            open_interest = open_interest_result

        if isinstance(long_short_result, BaseException):
            logger.error(f"Long/short ratio error: {long_short_result}")
            long_short_ratios: list[LongShortRatio] = []
        else:
            long_short_ratios = long_short_result

        return BinanceDerivativesSnapshot(
            funding_rates=funding_rates,
            open_interest=open_interest,
            long_short_ratios=long_short_ratios,
        )


def get_all_derivatives_data_sync(symbols: list[str]) -> BinanceDerivativesSnapshot:
    """Synchronous wrapper for get_all_derivatives_data.

    Args:
        symbols: List of trading pair symbols.

    Returns:
        BinanceDerivativesSnapshot with all data.
    """
    return asyncio.run(
        BinanceDerivativesClient().get_all_derivatives_data(symbols)
    )
