"""Type definitions for content enrichment."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class FetchResult:
    """Result of fetching content from a URL.

    Attributes:
        url: The URL that was fetched.
        success: Whether the fetch succeeded.
        html: Raw HTML content if successful.
        status_code: HTTP status code.
        error: Error message if failed.
        elapsed_ms: Time taken to fetch in milliseconds.
    """

    url: str
    success: bool
    html: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class EnrichmentResult:
    """Result of enriching a single news item.

    Attributes:
        news_item_id: ID of the news item that was enriched.
        success: Whether enrichment succeeded.
        content_type: Type of content stored ('excerpt' or 'full_text').
        content_length: Length of extracted content in characters.
        error: Error message if failed.
    """

    news_item_id: int
    success: bool
    content_type: Optional[str] = None
    content_length: int = 0
    error: Optional[str] = None


@dataclass
class EnrichmentCandidate:
    """A news item candidate for enrichment.

    Combines news_items data with impact_score from news_scores.

    Attributes:
        id: News item ID.
        source_url: URL to fetch content from.
        title: News item title.
        ingested_at: When the item was ingested.
        impact_score: Score from news_scores table.
    """

    id: int
    source_url: str
    title: str
    ingested_at: datetime
    impact_score: int

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "EnrichmentCandidate":
        """Create from database row tuple.

        Expected row format from query:
        (id, source_url, title, ingested_at, impact_score)
        """
        return cls(
            id=row[0],
            source_url=row[1],
            title=row[2],
            ingested_at=row[3],
            impact_score=row[4],
        )
