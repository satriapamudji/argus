"""Fear & Greed Index adapter for crypto market sentiment.

Fetches the Fear & Greed Index from Alternative.me API.
No API key required.

API: https://api.alternative.me/fng/?limit=2
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10
FNG_API_URL = "https://api.alternative.me/fng/?limit=2"


@dataclass(frozen=True)
class FearGreedIndex:
    """Fear & Greed Index data.

    Attributes:
        value: Index value (0-100). 0 = Extreme Fear, 100 = Extreme Greed.
        classification: Text classification (e.g., "Fear", "Greed").
        timestamp: When the index was recorded.
        previous_value: Previous day's value for comparison.
    """

    value: int
    classification: str
    timestamp: datetime
    previous_value: int | None = None


class FearGreedError(Exception):
    """Base exception for Fear & Greed adapter errors."""


async def get_fear_greed_index(
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> FearGreedIndex:
    """Fetch the current Fear & Greed Index from Alternative.me.

    Args:
        timeout_seconds: HTTP request timeout.

    Returns:
        FearGreedIndex with current and previous values.

    Raises:
        FearGreedError: If the API request fails or returns invalid data.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(FNG_API_URL)
            response.raise_for_status()
            data = response.json()

        if not data.get("data") or len(data["data"]) == 0:
            raise FearGreedError("No Fear & Greed data in response")

        current_data = data["data"][0]
        value = int(current_data["value"])
        classification = current_data["value_classification"]
        timestamp = datetime.fromtimestamp(int(current_data["timestamp"]), tz=timezone.utc)

        # Get previous value if available
        previous_value = None
        if len(data["data"]) > 1:
            previous_value = int(data["data"][1]["value"])

        logger.info(
            f"Fear & Greed Index: {value} ({classification}), "
            f"previous: {previous_value if previous_value else 'N/A'}"
        )

        return FearGreedIndex(
            value=value,
            classification=classification,
            timestamp=timestamp,
            previous_value=previous_value,
        )

    except httpx.HTTPStatusError as e:
        raise FearGreedError(f"HTTP error fetching Fear & Greed: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise FearGreedError(f"Network error fetching Fear & Greed: {e}") from e
    except (KeyError, ValueError, TypeError) as e:
        raise FearGreedError(f"Invalid Fear & Greed API response: {e}") from e


def get_fear_greed_index_sync(
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> FearGreedIndex:
    """Synchronous wrapper for get_fear_greed_index.

    Args:
        timeout_seconds: HTTP request timeout.

    Returns:
        FearGreedIndex with current and previous values.
    """
    return asyncio.run(get_fear_greed_index(timeout_seconds=timeout_seconds))
