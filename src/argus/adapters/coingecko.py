"""CoinGecko adapter for cryptocurrency market data.

Fetches market cap rankings, prices, and global market data.
Free API (no key required) with rate limits.

API endpoints:
- /api/v3/coins/markets - Top coins by market cap
- /api/v3/global - Global market data
"""

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
BASE_URL = "https://api.coingecko.com/api/v3"


@dataclass(frozen=True)
class CryptoAsset:
    """A single cryptocurrency asset.

    Attributes:
        symbol: Trading symbol (e.g., "BTC", "ETH").
        name: Full asset name (e.g., "Bitcoin", "Ethereum").
        price_usd: Current price in USD.
        price_change_24h_pct: 24-hour percentage change.
        market_cap_usd: Market capitalization in USD.
        volume_24h_usd: 24-hour trading volume in USD.
        market_cap_rank: Market cap rank (1=highest).
    """

    symbol: str
    name: str
    price_usd: float
    price_change_24h_pct: float
    market_cap_usd: float
    volume_24h_usd: float
    market_cap_rank: int


@dataclass(frozen=True)
class GlobalMarketData:
    """Global cryptocurrency market data.

    Attributes:
        total_market_cap_usd: Total crypto market cap in USD.
        btc_dominance_pct: Bitcoin's market cap dominance percentage.
        eth_dominance_pct: Ethereum's market cap dominance percentage.
        total_volume_24h_usd: Total 24-hour trading volume in USD.
    """

    total_market_cap_usd: float
    btc_dominance_pct: float
    eth_dominance_pct: float | None
    total_volume_24h_usd: float | None


class CoinGeckoError(Exception):
    """Base exception for CoinGecko adapter errors."""


class CoinGeckoClient:
    """CoinGecko API client for crypto market data.

    Uses the free API (no key required) with rate limit handling.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the CoinGecko client.

        Args:
            base_url: API base URL.
            timeout_seconds: HTTP request timeout.
        """
        self.base_url = base_url
        self.timeout = timeout_seconds

    async def get_top_n_by_market_cap(
        self,
        n: int,
        always_include: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> list[CryptoAsset]:
        """Fetch top N cryptocurrencies by market cap.

        Args:
            n: Number of coins to return.
            always_include: Symbols to always include regardless of rank (e.g., ["BTC", "ETH"]).
            exclude: Symbols to exclude (e.g., ["USDT", "USDC", "DAI"] for stablecoins).

        Returns:
            List of CryptoAsset sorted by market cap rank.

        Raises:
            CoinGeckoError: If the API request fails or returns invalid data.
        """
        always_include = [s.upper() for s in (always_include or [])]
        exclude_set = {s.upper() for s in (exclude or [])}

        # Fetch more than needed to account for exclusions and find always-include
        fetch_count = max(n + len(exclude_set) + 20, 100)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": fetch_count,
                    "page": 1,
                    "sparkline": "false",
                    "price_change_percentage": "24h",
                }
                response = await client.get(
                    f"{self.base_url}/coins/markets",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            if not isinstance(data, list):
                raise CoinGeckoError(f"Expected list, got {type(data).__name__}")

            # Process results
            assets_by_symbol: dict[str, CryptoAsset] = {}
            always_include_assets: dict[str, CryptoAsset] = {}

            for item in data:
                symbol = item.get("symbol", "").upper()
                if not symbol:
                    continue

                # Skip excluded symbols (stablecoins)
                if symbol in exclude_set:
                    continue

                try:
                    asset = CryptoAsset(
                        symbol=symbol,
                        name=item.get("name", ""),
                        price_usd=float(item.get("current_price", 0)),
                        price_change_24h_pct=float(
                            item.get("price_change_percentage_24h", 0) or 0
                        ),
                        market_cap_usd=float(item.get("market_cap", 0) or 0),
                        volume_24h_usd=float(item.get("total_volume", 0) or 0),
                        market_cap_rank=int(item.get("market_cap_rank") or 999),
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse coin data for {symbol}: {e}")
                    continue

                # Track always-include separately
                if symbol in always_include:
                    always_include_assets[symbol] = asset
                else:
                    assets_by_symbol[symbol] = asset

            # Build final list: always-include first, then fill to N
            result: list[CryptoAsset] = []
            result.extend(always_include_assets.values())

            # Add remaining by market cap rank
            remaining = sorted(
                [a for a in assets_by_symbol.values() if a.symbol not in always_include],
                key=lambda a: a.market_cap_rank,
            )

            for asset in remaining:
                if len(result) >= n:
                    break
                result.append(asset)

            # Sort final result by rank
            result.sort(key=lambda a: a.market_cap_rank)

            logger.info(
                f"CoinGecko fetched {len(result)} assets: "
                f"{', '.join(a.symbol for a in result[:5])}..."
            )

            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise CoinGeckoError("Rate limited - too many requests to CoinGecko") from e
            raise CoinGeckoError(f"HTTP error {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise CoinGeckoError(f"Network error: {e}") from e

    async def get_global_market_data(self) -> GlobalMarketData:
        """Fetch global cryptocurrency market data.

        Returns:
            GlobalMarketData with total market cap and BTC dominance.

        Raises:
            CoinGeckoError: If the API request fails or returns invalid data.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/global")
                response.raise_for_status()
                data = response.json()

            if not isinstance(data, dict) or "data" not in data:
                raise CoinGeckoError("Invalid response format")

            gd = data["data"]
            mcap_dict = gd.get("market_cap_percentage") or {}
            volume_dict = gd.get("total_volume") or {}

            # Helper to safely extract float value
            def _get_float(
                source: dict, key: str, default: float | None = None
            ) -> float | None:
                val = source.get(key)
                if val is None:
                    return default
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return default

            total_mcap_raw = gd.get("total_market_cap", {}).get("usd")
            total_market_cap_usd = float(total_mcap_raw or 0)

            btc_dom_raw = mcap_dict.get("btc")
            btc_dominance_pct = float(btc_dom_raw or 0)

            eth_dominance_pct = _get_float(mcap_dict, "eth")
            total_volume_24h_usd = _get_float(volume_dict, "usd")

            return GlobalMarketData(
                total_market_cap_usd=total_market_cap_usd,
                btc_dominance_pct=btc_dominance_pct,
                eth_dominance_pct=eth_dominance_pct,
                total_volume_24h_usd=total_volume_24h_usd,
            )

        except (ValueError, TypeError, KeyError) as e:
            raise CoinGeckoError(f"Failed to parse global data: {e}") from e
        except httpx.HTTPStatusError as e:
            raise CoinGeckoError(f"HTTP error {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise CoinGeckoError(f"Network error: {e}") from e


def get_top_n_by_market_cap_sync(
    n: int,
    always_include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[CryptoAsset]:
    """Synchronous wrapper for get_top_n_by_market_cap."""
    return asyncio.run(
        CoinGeckoClient().get_top_n_by_market_cap(
            n=n,
            always_include=always_include,
            exclude=exclude,
        )
    )


def get_global_market_data_sync() -> GlobalMarketData:
    """Synchronous wrapper for get_global_market_data."""
    return asyncio.run(CoinGeckoClient().get_global_market_data())
