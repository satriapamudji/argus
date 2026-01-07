"""Type definitions for RSS ingestion."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class RSSEntry:
    """Normalized representation of an RSS feed entry.

    Attributes:
        source_name: Name of the news source (e.g., "Reuters").
        source_url: Full URL of the article.
        title: Article title.
        snippet: Optional article snippet/summary (HTML stripped).
        author: Optional author name.
        published_at: Optional publication timestamp.
        raw_metadata: Optional dict with additional metadata for debugging.
    """

    source_name: str
    source_url: str
    title: str
    snippet: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    raw_metadata: Optional[dict[str, Any]] = None
