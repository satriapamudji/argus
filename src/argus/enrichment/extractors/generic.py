"""Generic content extractor using lxml heuristics.

This is the fallback extractor for sites without a specific implementation.
It uses the existing lxml-based extraction logic from the parent module.
"""

import logging
from typing import Optional


from argus.enrichment.extractor import extract_article_text
from argus.enrichment.extractors.base import BaseExtractor, ExtractedArticle

logger = logging.getLogger(__name__)


class GenericExtractor(BaseExtractor):
    """Generic content extractor using lxml heuristics.

    This is the fallback extractor that handles any domain not covered
    by a specific extractor. It uses semantic HTML tags and common
    class/id patterns to find article content.

    Note:
        This extractor does NOT extract author or publication date.
        Those fields will be None, and the RSS-provided values will be kept.
    """

    def can_handle(self, url: str) -> bool:
        """Always returns True - this is the fallback extractor.

        Args:
            url: The article URL (unused).

        Returns:
            Always True.
        """
        return True

    def extract(self, html_content: str, url: str) -> Optional[ExtractedArticle]:
        """Extract article content using lxml heuristics.

        Uses the existing extract_article_text() function which:
        1. Tries semantic tags first (<article>, <main>)
        2. Falls back to common class patterns
        3. Cleans up whitespace and strips HTML

        Args:
            html_content: Raw HTML content of the page.
            url: The article URL (for logging).

        Returns:
            ExtractedArticle with content only (no author/date),
            or None if extraction failed.
        """
        if not html_content or not html_content.strip():
            logger.warning(f"Empty HTML content for {url}")
            return None

        try:
            text = extract_article_text(html_content)

            if not text:
                logger.warning(f"No content extracted from {url}")
                return None

            return ExtractedArticle(
                content=text,
                author=None,  # Generic extractor doesn't extract author
                published_at=None,  # Generic extractor doesn't extract date
            )

        except Exception as e:
            logger.exception(f"Error extracting content from {url}: {e}")
            return None
