"""Nasdaq content extractor.

Handles article extraction from nasdaq.com pages, including:
- Publication date from p.jupiter22-c-author-byline__timestamp
- Author from span.jupiter22-c-author-byline__author-no-link
- Content from section.jupiter22-c-article-body (excluding ads and disclaimer)
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from lxml import html

from argus.enrichment.extractors.base import BaseExtractor, ExtractedArticle

logger = logging.getLogger(__name__)

# Regex pattern for Nasdaq date format
# Example: "January 06, 2026 — 01:50 pm EST"
NASDAQ_DATE_PATTERN = re.compile(
    r"(\w+)\s+(\d{1,2}),\s+(\d{4})\s*[—–-]\s*(\d{1,2}):(\d{2})\s*(am|pm)\s*(\w+)",
    re.IGNORECASE,
)

# Month name to number mapping
MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# US timezone offsets (simplified - doesn't handle DST perfectly)
TIMEZONE_OFFSETS = {
    "est": -5,
    "edt": -4,
    "cst": -6,
    "cdt": -5,
    "mst": -7,
    "mdt": -6,
    "pst": -8,
    "pdt": -7,
    "et": -5,
    "ct": -6,
    "mt": -7,
    "pt": -8,  # Generic versions
}


class NasdaqExtractor(BaseExtractor):
    """Content extractor for Nasdaq articles.

    Nasdaq articles (often RTTNews syndicated) have a specific structure:
    - Date is in <p class="jupiter22-c-author-byline__timestamp">
    - Author is in <span class="jupiter22-c-author-byline__author-no-link">
    - Article body is in <section class="jupiter22-c-article-body">
    - Inline ads (.ads__inline) must be filtered out
    - Disclaimer (.body__disclaimer) should be excluded
    """

    def can_handle(self, url: str) -> bool:
        """Check if this is a Nasdaq URL.

        Args:
            url: The article URL.

        Returns:
            True if domain is nasdaq.com.
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return "nasdaq.com" in domain
        except Exception:
            return False

    def extract(self, html_content: str, url: str) -> Optional[ExtractedArticle]:
        """Extract article content from Nasdaq HTML.

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
                logger.warning(f"No content extracted from Nasdaq article: {url}")
                return None

            return ExtractedArticle(
                content=content,
                author=author,
                published_at=published_at,
            )

        except Exception as e:
            logger.exception(f"Error extracting Nasdaq article {url}: {e}")
            return None

    def _extract_date(self, doc: html.HtmlElement) -> Optional[datetime]:
        """Extract publication date from Nasdaq article.

        Format: "January 06, 2026 — 01:50 pm EST"
        """
        try:
            timestamp_elements = doc.xpath(
                '//p[contains(@class, "jupiter22-c-author-byline__timestamp")]'
            )
            if not timestamp_elements:
                return None

            timestamp_text = timestamp_elements[0].text_content().strip()
            if not timestamp_text:
                return None

            match = NASDAQ_DATE_PATTERN.match(timestamp_text)
            if not match:
                logger.debug(f"Could not parse Nasdaq date: {timestamp_text}")
                return None

            month_name, day, year, hour, minute, ampm, tz = match.groups()

            # Convert month name to number
            month = MONTH_MAP.get(month_name.lower())
            if not month:
                return None

            # Convert to 24-hour format
            hour = int(hour)
            if ampm.lower() == "pm" and hour != 12:
                hour += 12
            elif ampm.lower() == "am" and hour == 12:
                hour = 0

            # Get timezone offset
            tz_offset = TIMEZONE_OFFSETS.get(tz.lower(), -5)  # Default to EST

            # Create datetime with timezone
            from datetime import timedelta

            tzinfo = timezone(timedelta(hours=tz_offset))

            return datetime(
                year=int(year),
                month=month,
                day=int(day),
                hour=hour,
                minute=int(minute),
                tzinfo=tzinfo,
            )

        except Exception as e:
            logger.debug(f"Could not extract Nasdaq date: {e}")
            return None

    def _extract_author(self, doc: html.HtmlElement) -> Optional[str]:
        """Extract author name from Nasdaq article.

        Author is in <span class="jupiter22-c-author-byline__author-no-link">
        """
        try:
            # Try the no-link author span first
            author_elements = doc.xpath(
                '//span[contains(@class, "jupiter22-c-author-byline__author-no-link")]'
            )
            if author_elements:
                author = author_elements[0].text_content().strip()
                if author:
                    return author

            # Fallback: try linked author
            author_elements = doc.xpath(
                '//a[contains(@class, "jupiter22-c-author-byline__author")]'
            )
            if author_elements:
                author = author_elements[0].text_content().strip()
                if author:
                    return author

        except Exception as e:
            logger.debug(f"Could not extract Nasdaq author: {e}")

        return None

    def _extract_content(self, doc: html.HtmlElement) -> Optional[str]:
        """Extract article content from Nasdaq article.

        1. Find section.jupiter22-c-article-body
        2. Find .body__content within it
        3. Remove .ads__inline divs
        4. Extract text from <p> elements, excluding .body__disclaimer
        """
        try:
            # Find article body section
            body_elements = doc.xpath('//section[contains(@class, "jupiter22-c-article-body")]')
            if not body_elements:
                logger.debug("No jupiter22-c-article-body found")
                return None

            body = body_elements[0]

            # Find body__content div
            content_elements = body.xpath('.//div[contains(@class, "body__content")]')
            if content_elements:
                body = content_elements[0]

            # Remove inline ads
            for ad in body.xpath('.//div[contains(@class, "ads__inline")]'):
                ad.getparent().remove(ad)

            # Extract paragraphs, excluding disclaimer
            paragraphs = []
            for p in body.xpath(".//p"):
                # Skip disclaimer
                p_class = p.get("class", "")
                if "body__disclaimer" in p_class:
                    continue

                text = p.text_content().strip()
                if text:
                    paragraphs.append(text)

            if not paragraphs:
                # Fallback: get all text from body
                text = body.text_content().strip()
                return self._normalize_whitespace(text) if text else None

            return "\n\n".join(paragraphs)

        except Exception as e:
            logger.debug(f"Could not extract Nasdaq content: {e}")
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
