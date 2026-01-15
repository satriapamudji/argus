"""ChartInspect adapter for crypto OHLCV (Open, High, Low, Close, Volume) data.

This adapter provides OHLCV data with fallback to CoinGecko when:
1. CHARTINSPECT_API environment variable is not set
2. The API returns an error (403 for free tier on pro endpoints)

Note: ChartInspect free tier provides basic OHLCV. Derivatives/on-chain require Pro subscription.

API endpoint:
- /crypto/prices/{symbol}?days=N - Daily OHLCV data
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_BASE_URL = "https://api.chartinspect.org/v1"


@dataclass(frozen=True)
class CryptoOHLCV:
    """OHLCV data for a single day.

    Attributes:
        symbol: Trading symbol (e.g., "BTC").
        date: Trading date.
        open: Opening price in USD.
        high: Highest price in USD.
        low: Lowest price in USD.
        close: Closing price in USD.
        volume: Trading volume in base currency.
    """

    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartInspectError(Exception):
    """Base exception for ChartInspect adapter errors."""


class ChartInspectClient:
    """ChartInspect API client for OHLCV data.

    Falls back to CoinGecko if no API key or on API errors.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the ChartInspect client.

        Args:
            api_key: ChartInspect API key (from CHARTINSPECT_API env var).
            base_url: API base URL.
            timeout_seconds: HTTP request timeout.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout_seconds

    def is_available(self) -> bool:
        """Check if ChartInspect API is configured and available.

        Returns:
            True if API key is set, False otherwise.
        """
        return bool(self.api_key)

    async def get_daily_ohlcv(
        self,
        symbol: str,
        days: int = 2,
    ) -> list[CryptoOHLCV]:
        """Fetch daily OHLCV data for a symbol.

        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH").
            days: Number of days of data to fetch.

        Returns:
            List of CryptoOHLCV objects, most recent first.

        Raises:
            ChartInspectError: If the API request fails and no fallback is available.
        """
        if not self.is_available():
            logger.info("ChartInspect API key not set, returning empty list")
            return []

        try:
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=headers,
            ) as client:
                response = await client.get(
                    f"{self.base_url}/crypto/prices/{symbol}",
                    params={"days": days},
                )
                response.raise_for_status()
                data = response.json()

            if not isinstance(data, dict) or "prices" not in data:
                raise ChartInspectError("Invalid response format")

            results: list[CryptoOHLCV] = []
            for item in data["prices"]:
                try:
                    results.append(
                        CryptoOHLCV(
                            symbol=symbol,
                            date=datetime.fromisoformat(item["date"]).date(),
                            open=float(item["open"]),
                            high=float(item["high"]),
                            low=float(item["low"]),
                            close=float(item["close"]),
                            volume=float(item.get("volume", 0) or 0),
                        )
                    )
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to parse OHLCV item: {e}")
                    continue

            logger.info(f"ChartInspect: fetched {len(results)} OHLCV records for {symbol}")
            return results

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning(f"ChartInspect API returned 403 (Pro endpoint?): {e}")
                # Return empty list - caller should use CoinGecko fallback
                return []
            elif e.response.status_code == 401:
                logger.warning("ChartInspect API key invalid or expired")
                return []
            raise ChartInspectError(f"HTTP error {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.warning(f"ChartInspect network error: {e}")
            return []
        except (ValueError, TypeError, KeyError) as e:
            raise ChartInspectError(f"Failed to parse OHLCV data: {e}") from e


def get_daily_ohlcv_sync(
    symbol: str,
    api_key: str,
    days: int = 2,
) -> list[CryptoOHLCV]:
    """Synchronous wrapper for get_daily_ohlcv.

    Args:
        symbol: Trading symbol.
        api_key: ChartInspect API key.
        days: Number of days of data to fetch.

    Returns:
        List of CryptoOHLCV objects, or empty list if API unavailable.
    """
    return asyncio.run(
        ChartInspectClient(api_key=api_key).get_daily_ohlcv(symbol, days)
    )
