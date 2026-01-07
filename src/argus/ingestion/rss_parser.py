"""RSS parsing utilities for Argus."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, cast
from urllib.parse import urlparse

import feedparser
from lxml import html as lxml_html

from argus.ingestion.types import RSSEntry

logger = logging.getLogger(__name__)


def strip_html(html_content: str) -> str:
    """Strip HTML tags from content using lxml.

    Args:
        html_content: HTML string to strip.

    Returns:
        Plain text with HTML tags removed.
    """
    if not html_content:
        return ""

    try:
        # Parse as HTML and extract text
        doc = lxml_html.fromstring(html_content)
        if doc is None:
            return html_content
        text = doc.text_content()
        # Normalize whitespace
        return " ".join(text.split())
    except Exception:
        # Fallback: return as-is if parsing fails
        return html_content


def extract_source_name(feed: dict[str, Any], feed_url: str) -> str:
    """Extract a clean source name from feed metadata.

    Args:
        feed: Parsed feed object.
        feed_url: Original feed URL.

    Returns:
        Source name string.
    """
    # Try feed title first
    feed_info = feed.get("feed", {})
    raw_title = feed_info.get("title", "")
    title: str = str(raw_title).strip() if raw_title else ""

    if title:
        # Clean up common suffixes (check longer patterns first to avoid partial matches)
        for suffix in [" - RSS", " | RSS", " RSS", " Feed", " News"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)]
                break  # Only remove one suffix
        return title.strip()

    # Fallback to domain name
    parsed = urlparse(feed_url)
    domain = parsed.netloc
    # Remove www. prefix
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def parse_published_date(entry: dict[str, Any]) -> Optional[datetime]:
    """Parse publication date from feed entry.

    Args:
        entry: Feed entry object.

    Returns:
        datetime object or None if not available.
    """
    # Try published_parsed first (time.struct_time)
    parsed = entry.get("published_parsed")
    if parsed:
        try:
            dt = datetime(
                year=parsed[0],
                month=parsed[1],
                day=parsed[2],
                hour=parsed[3],
                minute=parsed[4],
                second=parsed[5],
                tzinfo=timezone.utc,
            )
            return dt
        except (TypeError, ValueError, IndexError):
            pass

    # Try updated_parsed as fallback
    parsed = entry.get("updated_parsed")
    if parsed:
        try:
            dt = datetime(
                year=parsed[0],
                month=parsed[1],
                day=parsed[2],
                hour=parsed[3],
                minute=parsed[4],
                second=parsed[5],
                tzinfo=timezone.utc,
            )
            return dt
        except (TypeError, ValueError, IndexError):
            pass

    return None


def parse_feed(
    feed_url: str,
    max_snippet_chars: int = 1200,
) -> tuple[list[RSSEntry], Optional[str]]:
    """Parse an RSS feed and return normalized entries.

    Args:
        feed_url: URL of the RSS feed.
        max_snippet_chars: Maximum characters for snippet.

    Returns:
        Tuple of (list of RSSEntry objects, error message or None).
    """
    try:
        # Parse the feed
        result = feedparser.parse(feed_url, request_headers={"User-Agent": "Argus/1.0"})

        # Check for HTTP errors - feedparser returns status as int when available
        status = cast(int, result.get("status", 0))
        if status >= 400:
            return [], f"HTTP error {status} for {feed_url}"

        # Check for parsing errors
        if result.get("bozo") and not result.get("entries"):
            bozo_exception = result.get("bozo_exception")
            return [], f"Feed parsing error: {bozo_exception}"

        # Cast result to dict for extract_source_name
        source_name = extract_source_name(cast(dict[str, Any], result), feed_url)
        entries: list[RSSEntry] = []

        # Get entries list - feedparser returns list of FeedParserDict
        feed_entries = result.get("entries") or []

        for entry in feed_entries:
            # Cast entry to dict for proper typing
            entry_dict = cast(dict[str, Any], entry)

            # Extract required fields
            title_raw = entry_dict.get("title", "")
            link_raw = entry_dict.get("link", "")
            title = str(title_raw).strip() if title_raw else ""
            link = str(link_raw).strip() if link_raw else ""

            if not title or not link:
                logger.debug(f"Skipping entry without title or link in {feed_url}")
                continue

            # Extract snippet from summary/description
            raw_snippet = entry_dict.get("summary") or entry_dict.get("description") or ""
            snippet = strip_html(str(raw_snippet))
            if len(snippet) > max_snippet_chars:
                snippet = snippet[:max_snippet_chars].rsplit(" ", 1)[0] + "..."

            # Extract optional fields
            author_raw = entry_dict.get("author", "")
            author = str(author_raw).strip() if author_raw else None
            published_at = parse_published_date(entry_dict)

            # Store raw metadata for debugging/future use
            tags_list = entry_dict.get("tags") or []
            raw_metadata: dict[str, Any] = {
                "feed_url": feed_url,
                "entry_id": entry_dict.get("id"),
                "tags": [cast(dict[str, Any], tag).get("term") for tag in tags_list],
            }

            entries.append(
                RSSEntry(
                    source_name=source_name,
                    source_url=link,
                    title=title,
                    snippet=snippet if snippet else None,
                    author=author,
                    published_at=published_at,
                    raw_metadata=raw_metadata,
                )
            )

        logger.info(f"Parsed {len(entries)} entries from {feed_url}")
        return entries, None

    except Exception as e:
        logger.exception(f"Error parsing feed {feed_url}")
        return [], str(e)
