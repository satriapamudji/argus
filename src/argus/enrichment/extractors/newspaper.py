"""Universal content extractor using newspaper4k.

Uses newspaper4k for robust ML-based article extraction, with fallback
patterns for metadata (author, publication date) when newspaper4k misses them.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from lxml import html
from newspaper import Article

from argus.enrichment.extractors.base import BaseExtractor, ExtractedArticle

logger = logging.getLogger(__name__)


class NewspaperExtractor(BaseExtractor):
    """Universal content extractor using newspaper4k + common metadata patterns.

    This extractor:
    1. Uses newspaper4k for robust ML-based content extraction
    2. Falls back to common HTML patterns for author/date when newspaper4k misses them

    The common patterns cover most news sites without requiring site-specific code:
    - Author: class contains 'author-name', 'author-no-link', itemprop='author'
    - Date: <time datetime="...">, class contains 'timestamp', various text formats
    """

    def can_handle(self, url: str) -> bool:
        """Check if this extractor can handle the given URL.

        Args:
            url: The article URL.

        Returns:
            Always True - this is the primary universal extractor.
        """
        return True

    def extract(self, html_content: str, url: str) -> Optional[ExtractedArticle]:
        """Extract article content from HTML using newspaper4k.

        Args:
            html_content: Raw HTML content of the page.
            url: The article URL.

        Returns:
            ExtractedArticle with content, author, and publication date,
            or None if extraction failed.
        """
        if not html_content or not html_content.strip():
            logger.warning(f"Empty HTML content for {url}")
            return None

        try:
            # Step 1: Use newspaper4k for content extraction
            article = Article(url)
            article.download(input_html=html_content)
            article.parse()

            content = article.text
            if not content or len(content.strip()) < 50:
                logger.warning(f"newspaper4k extracted insufficient content from {url}")
                return None

            # Get initial metadata from newspaper4k
            author = article.authors[0] if article.authors else None
            published_at = article.publish_date

            # Step 2: Fallback to common patterns for missing metadata
            doc = html.fromstring(html_content)

            if not author:
                author = self._extract_author_fallback(doc)

            if not published_at:
                published_at = self._extract_date_fallback(doc)

            return ExtractedArticle(
                content=content,
                author=author,
                published_at=published_at,
            )

        except Exception as e:
            logger.exception(f"Error extracting article from {url}: {e}")
            return None

    def _extract_author_fallback(self, doc: html.HtmlElement) -> Optional[str]:
        """Extract author using common HTML patterns.

        Patterns tried (in order):
        1. class contains 'author-name' or 'authorName'
        2. class contains 'author-no-link' (Nasdaq pattern)
        3. itemprop='author'
        4. rel='author'

        Args:
            doc: Parsed lxml document.

        Returns:
            Author name or None if not found.
        """
        author_patterns = [
            '//*[contains(@class, "author-name")]//text()',
            '//*[contains(@class, "authorName")]//text()',
            '//*[contains(@class, "Author-authorName")]//text()',
            '//*[contains(@class, "author-no-link")]//text()',
            '//*[@itemprop="author"]//text()',
            '//*[@rel="author"]//text()',
        ]

        # Words that indicate false positives
        skip_words = [
            "written by",
            "author",
            "by ",
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
            "2026",
            "2025",
            "2024",
        ]

        for pattern in author_patterns:
            try:
                elements = doc.xpath(pattern)
                for el in elements:
                    text = el.strip() if isinstance(el, str) else str(el).strip()
                    if text and 2 < len(text) < 80:
                        # Skip false positives
                        if not any(skip in text.lower() for skip in skip_words):
                            return text
            except Exception:
                pass

        return None

    def _extract_date_fallback(self, doc: html.HtmlElement) -> Optional[datetime]:
        """Extract publication date using common HTML patterns.

        Patterns tried (in order):
        1. <time datetime="ISO8601"> attribute
        2. <meta property="article:published_time">
        3. itemprop='datePublished' attribute
        4. class contains 'timestamp' (text parsing)

        Args:
            doc: Parsed lxml document.

        Returns:
            Publication datetime or None if not found.
        """
        # Pattern 1: ISO format in datetime attributes
        iso_patterns = [
            "//time[@datetime]/@datetime",
            '//meta[@property="article:published_time"]/@content',
            '//*[@itemprop="datePublished"]/@datetime',
            '//*[@itemprop="datePublished"]/@content',
        ]

        for pattern in iso_patterns:
            try:
                elements = doc.xpath(pattern)
                for el in elements:
                    if el:
                        date_str = el.replace("+0000", "+00:00")
                        return datetime.fromisoformat(date_str)
            except Exception:
                pass

        # Pattern 2: Text format in timestamp class (e.g., 'January 06, 2026 - 01:50 pm EST')
        try:
            timestamp_els = doc.xpath('//*[contains(@class, "timestamp")]//text()')
            for text in timestamp_els:
                text = text.strip()
                if text and len(text) > 10:
                    parsed = self._parse_text_date(text)
                    if parsed:
                        return parsed
        except Exception:
            pass

        return None

    def _parse_text_date(self, text: str) -> Optional[datetime]:
        """Parse common text date formats.

        Handles formats like:
        - 'January 06, 2026 - 01:50 pm EST'
        - 'Jan 6, 2026 1:50 PM'

        Args:
            text: Raw date text.

        Returns:
            Parsed datetime or None.
        """
        # Clean up the text
        clean = re.sub(r"[^a-zA-Z0-9:, ]", " ", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        clean = re.sub(r"\s*(EST|EDT|PST|PDT|UTC|GMT)\s*$", "", clean, flags=re.I)

        # Try various formats
        formats = [
            "%B %d, %Y %I:%M %p",  # January 06, 2026 01:50 pm
            "%B %d, %Y %H:%M",  # January 06, 2026 13:50
            "%b %d, %Y %I:%M %p",  # Jan 06, 2026 01:50 pm
            "%b %d, %Y %H:%M",  # Jan 06, 2026 13:50
            "%B %d, %Y",  # January 06, 2026
            "%b %d, %Y",  # Jan 06, 2026
            "%Y-%m-%d %H:%M:%S",  # 2026-01-06 13:50:00
            "%Y-%m-%d",  # 2026-01-06
        ]

        for fmt in formats:
            try:
                return datetime.strptime(clean, fmt)
            except ValueError:
                pass

        return None
