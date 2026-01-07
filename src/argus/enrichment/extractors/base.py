"""Base classes for source-specific content extractors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ExtractedArticle:
    """Result of extracting content from an article page.

    Attributes:
        content: Full article text (cleaned, paragraphs joined with newlines).
        author: Extracted author name (if available from page).
        published_at: Extracted publication datetime (if available from page).
    """

    content: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None


class BaseExtractor(ABC):
    """Base class for source-specific content extractors.

    Each extractor handles a specific domain (e.g., cnbc.com, nasdaq.com)
    and knows how to extract article content, author, and publication date
    from that site's HTML structure.

    Usage:
        extractor = get_extractor(url)  # From registry
        result = extractor.extract(html, url)
        if result:
            print(result.content)
    """

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this extractor can handle the given URL.

        Args:
            url: The article URL to check.

        Returns:
            True if this extractor handles this URL's domain.
        """

    @abstractmethod
    def extract(self, html_content: str, url: str) -> Optional[ExtractedArticle]:
        """Extract article content from HTML.

        Args:
            html_content: Raw HTML content of the page.
            url: The article URL (for logging/debugging).

        Returns:
            ExtractedArticle with content and optional metadata,
            or None if extraction failed.
        """
