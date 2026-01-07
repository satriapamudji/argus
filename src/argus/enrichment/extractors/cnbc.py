"""CNBC content extractor.

Handles article extraction from cnbc.com pages, including:
- Publication date from time[data-testid="published-timestamp"]
- Author from a.Author-authorName
- Content from div.ArticleBody-articleBody (excluding RelatedContent)
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from lxml import html

from argus.enrichment.extractors.base import BaseExtractor, ExtractedArticle

logger = logging.getLogger(__name__)


class CNBCExtractor(BaseExtractor):
    """Content extractor for CNBC articles.

    CNBC articles have a specific structure:
    - Date is in <time data-testid="published-timestamp" datetime="ISO8601">
    - Author is in <a class="Author-authorName">
    - Article body is in <div class="ArticleBody-articleBody">
    - RelatedContent-relatedContent is INSIDE the body and must be removed

    The key issue this extractor solves is that RelatedContent appears
    mid-article, and naive extraction stops there, losing ~45% of content.
    """

    def can_handle(self, url: str) -> bool:
        """Check if this is a CNBC URL.

        Args:
            url: The article URL.

        Returns:
            True if domain is cnbc.com.
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return "cnbc.com" in domain
        except Exception:
            return False

    def extract(self, html_content: str, url: str) -> Optional[ExtractedArticle]:
        """Extract article content from CNBC HTML.

        Args:
            html_content: Raw HTML content.
            url: The article URL.

        Returns:
            ExtractedArticle with content, author, and publication date,
            or None if extraction failed.
        """
        if not html_content or not html_content.strip():
            logger.warning(f"Empty HTML content for {url}")
            return None

        try:
            doc = html.fromstring(html_content)

            # Extract publication date
            published_at = self._extract_date(doc)

            # Extract author
            author = self._extract_author(doc)

            # Extract article content
            content = self._extract_content(doc)

            if not content:
                logger.warning(f"No content extracted from CNBC article: {url}")
                return None

            return ExtractedArticle(
                content=content,
                author=author,
                published_at=published_at,
            )

        except Exception as e:
            logger.exception(f"Error extracting CNBC article {url}: {e}")
            return None

    def _extract_date(self, doc: html.HtmlElement) -> Optional[datetime]:
        """Extract publication date from CNBC article.

        Uses the datetime attribute which is in ISO 8601 format.
        Example: datetime="2026-01-06T23:54:30+0000"
        """
        try:
            # Try the specific CNBC timestamp element
            time_elements = doc.xpath('//time[@data-testid="published-timestamp"]')
            if time_elements:
                datetime_attr = time_elements[0].get("datetime")
                if datetime_attr:
                    # Parse ISO 8601 format
                    # Handle format like "2026-01-06T23:54:30+0000"
                    datetime_attr = datetime_attr.replace("+0000", "+00:00")
                    return datetime.fromisoformat(datetime_attr)

            # Fallback: try any time element with itemprop="datePublished"
            time_elements = doc.xpath('//time[@itemprop="datePublished"]')
            if time_elements:
                datetime_attr = time_elements[0].get("datetime")
                if datetime_attr:
                    datetime_attr = datetime_attr.replace("+0000", "+00:00")
                    return datetime.fromisoformat(datetime_attr)

        except Exception as e:
            logger.debug(f"Could not extract CNBC date: {e}")

        return None

    def _extract_author(self, doc: html.HtmlElement) -> Optional[str]:
        """Extract author name from CNBC article.

        Author is in <a class="Author-authorName">Author Name</a>
        """
        try:
            author_elements = doc.xpath('//a[contains(@class, "Author-authorName")]')
            if author_elements:
                author = author_elements[0].text_content().strip()
                if author:
                    return author

            # Fallback: try div with Author-author class
            author_elements = doc.xpath('//div[contains(@class, "Author-author")]//a')
            if author_elements:
                author = author_elements[0].text_content().strip()
                if author:
                    return author

        except Exception as e:
            logger.debug(f"Could not extract CNBC author: {e}")

        return None

    def _extract_content(self, doc: html.HtmlElement) -> Optional[str]:
        """Extract article content from CNBC article.

        1. Find div.ArticleBody-articleBody
        2. Remove div.RelatedContent-relatedContent (embedded mid-article)
        3. Extract text from remaining div.group > p elements
        """
        try:
            # Find article body
            body_elements = doc.xpath('//div[contains(@class, "ArticleBody-articleBody")]')
            if not body_elements:
                logger.debug("No ArticleBody-articleBody found")
                return None

            body = body_elements[0]

            # Remove RelatedContent sections (they're embedded mid-article)
            for related in body.xpath('.//div[contains(@class, "RelatedContent-relatedContent")]'):
                related.getparent().remove(related)

            # Remove ad containers
            for ad in body.xpath('.//div[contains(@class, "InlineVideo")]'):
                ad.getparent().remove(ad)

            # Extract paragraphs from group divs
            paragraphs = []
            for p in body.xpath('.//div[contains(@class, "group")]//p'):
                text = p.text_content().strip()
                if text:
                    paragraphs.append(text)

            # If no group divs, try direct paragraphs
            if not paragraphs:
                for p in body.xpath(".//p"):
                    text = p.text_content().strip()
                    if text:
                        paragraphs.append(text)

            if not paragraphs:
                # Last resort: get all text
                text = body.text_content().strip()
                return self._normalize_whitespace(text) if text else None

            return "\n\n".join(paragraphs)

        except Exception as e:
            logger.debug(f"Could not extract CNBC content: {e}")
            return None

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in extracted text."""
        # Replace tabs with spaces
        text = text.replace("\t", " ")
        # Collapse multiple spaces
        text = re.sub(r" +", " ", text)
        # Collapse multiple newlines to double
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        # Strip each line
        lines = [line.strip() for line in text.split("\n")]
        return "\n".join(lines).strip()
