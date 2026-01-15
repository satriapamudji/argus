"""DeFiLlama adapter for DeFi Total Value Locked (TVL) data.

Fetches protocol-level and chain-level TVL data from DeFiLlama API.
No API key required.

API endpoints:
- https://api.llama.fi/protocols - All protocols with TVL
- https://api.llama.fi/chains - TVL by chain
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
PROTOCOLS_URL = "https://api.llama.fi/protocols"
CHAINS_URL = "https://api.llama.fi/chains"


@dataclass(frozen=True)
class DeFiTVLSnapshot:
    """DeFi TVL snapshot.

    Attributes:
        timestamp: When the snapshot was taken.
        total_tvl_usd: Total DeFi TVL in USD.
        top_protocols: List of (name, tvl_usd) tuples for top protocols.
        chain_breakdown: Dict mapping chain names to their TVL in USD.
    """

    timestamp: datetime
    total_tvl_usd: float
    top_protocols: list[tuple[str, float]]
    chain_breakdown: dict[str, float]


class DeFiLlamaError(Exception):
    """Base exception for DeFiLlama adapter errors."""


class DeFiLlamaClient:
    """DeFiLlama API client for DeFi TVL data.

    No API key required for public endpoints.
    """

    def __init__(
        self,
        protocols_url: str = PROTOCOLS_URL,
        chains_url: str = CHAINS_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the DeFiLlama client.

        Args:
            protocols_url: URL for protocols endpoint.
            chains_url: URL for chains endpoint.
            timeout_seconds: HTTP request timeout.
        """
        self.protocols_url = protocols_url
        self.chains_url = chains_url
        self.timeout = timeout_seconds

    async def get_tvl_snapshot(
        self,
        top_protocols_count: int = 10,
        min_chain_tvl: float = 100_000_000,  # $100M minimum for chain breakdown
    ) -> DeFiTVLSnapshot:
        """Fetch a DeFi TVL snapshot.

        Args:
            top_protocols_count: Number of top protocols to include.
            min_chain_tvl: Minimum TVL (USD) for a chain to be included in breakdown.

        Returns:
            DeFiTVLSnapshot with total TVL, top protocols, and chain breakdown.

        Raises:
            DeFiLlamaError: If the API request fails or returns invalid data.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Fetch protocols and chains in parallel
                protocols_task = client.get(self.protocols_url)
                chains_task = client.get(self.chains_url)

                protocols_response, chains_response = await asyncio.gather(
                    protocols_task,
                    chains_task,
                )

                protocols_response.raise_for_status()
                chains_response.raise_for_status()

                protocols_data = protocols_response.json()
                chains_data = chains_response.json()

            timestamp = datetime.now(timezone.utc)

            # Parse protocols
            if not isinstance(protocols_data, list):
                raise DeFiLlamaError(f"Expected list for protocols, got {type(protocols_data)}")

            # Sort by TVL and get top protocols
            valid_protocols = [
                (p.get("name", "Unknown"), float(p.get("tvl", 0) or 0))
                for p in protocols_data
                if isinstance(p, dict) and p.get("tvl")
            ]
            valid_protocols.sort(key=lambda x: x[1], reverse=True)
            top_protocols = valid_protocols[:top_protocols_count]

            # Calculate total TVL
            total_tvl_usd = sum(tvl for _, tvl in valid_protocols)

            # Parse chains
            if not isinstance(chains_data, list):
                raise DeFiLlamaError(f"Expected list for chains, got {type(chains_data)}")

            chain_breakdown: dict[str, float] = {
                c.get("name", "Unknown"): float(c.get("tvl", 0) or 0)
                for c in chains_data
                if isinstance(c, dict)
                and c.get("name")
                and float(c.get("tvl", 0) or 0) >= min_chain_tvl
            }

            logger.info(
                f"DeFiLlama TVL: ${total_tvl_usd / 1e9:.2f}B, "
                f"top protocol: {top_protocols[0][0] if top_protocols else 'N/A'}"
            )

            return DeFiTVLSnapshot(
                timestamp=timestamp,
                total_tvl_usd=total_tvl_usd,
                top_protocols=top_protocols,
                chain_breakdown=chain_breakdown,
            )

        except httpx.HTTPStatusError as e:
            raise DeFiLlamaError(f"HTTP error {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise DeFiLlamaError(f"Network error: {e}") from e
        except (ValueError, TypeError, KeyError) as e:
            raise DeFiLlamaError(f"Failed to parse TVL data: {e}") from e


def get_tvl_snapshot_sync(
    top_protocols_count: int = 10,
    min_chain_tvl: float = 100_000_000,
) -> DeFiTVLSnapshot:
    """Synchronous wrapper for get_tvl_snapshot.

    Args:
        top_protocols_count: Number of top protocols to include.
        min_chain_tvl: Minimum TVL (USD) for chain breakdown.

    Returns:
        DeFiTVLSnapshot with DeFi TVL data.
    """
    return asyncio.run(
        DeFiLlamaClient().get_tvl_snapshot(
            top_protocols_count=top_protocols_count,
            min_chain_tvl=min_chain_tvl,
        )
    )
