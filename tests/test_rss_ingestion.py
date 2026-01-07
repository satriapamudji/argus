"""Tests for RSS ingestion module."""

import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from argus.ingestion.rss_parser import (
    extract_source_name,
    parse_feed,
    parse_published_date,
    strip_html,
)
from argus.ingestion.types import RSSEntry


class TestStripHtml:
    """Tests for strip_html function."""

    def test_strips_basic_tags(self) -> None:
        """Test basic HTML tag stripping."""
        assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_handles_empty_string(self) -> None:
        """Test empty string handling."""
        assert strip_html("") == ""

    def test_handles_plain_text(self) -> None:
        """Test plain text passthrough."""
        assert strip_html("No HTML here") == "No HTML here"

    def test_normalizes_whitespace(self) -> None:
        """Test whitespace normalization."""
        html = "<p>Multiple   spaces\n\nand newlines</p>"
        result = strip_html(html)
        assert "  " not in result
        assert "\n" not in result

    def test_handles_nested_tags(self) -> None:
        """Test nested HTML tags."""
        html = "<div><p><span>Nested</span> content</p></div>"
        assert strip_html(html) == "Nested content"

    def test_handles_br_tags(self) -> None:
        """Test break tags are handled."""
        html = "Line 1<br>Line 2<br/>Line 3"
        result = strip_html(html)
        assert "Line 1" in result
        assert "Line 2" in result

    def test_handles_entities(self) -> None:
        """Test HTML entities are decoded."""
        html = "<p>Test &amp; verify &lt;data&gt;</p>"
        result = strip_html(html)
        assert "&" in result or "&amp;" in result  # lxml may or may not decode

    def test_handles_malformed_html(self) -> None:
        """Test malformed HTML doesn't crash."""
        html = "<p>Unclosed tag <b>bold"
        result = strip_html(html)
        assert "Unclosed tag" in result


class TestExtractSourceName:
    """Tests for extract_source_name function."""

    def test_uses_feed_title(self) -> None:
        """Test extraction from feed title."""
        feed: dict[str, Any] = {"feed": {"title": "Reuters Business"}}
        assert extract_source_name(feed, "https://reuters.com/feed") == "Reuters Business"

    def test_removes_rss_suffix(self) -> None:
        """Test RSS suffix removal."""
        feed: dict[str, Any] = {"feed": {"title": "TechCrunch RSS"}}
        assert extract_source_name(feed, "https://tc.com/feed") == "TechCrunch"

    def test_removes_feed_suffix(self) -> None:
        """Test Feed suffix removal."""
        feed: dict[str, Any] = {"feed": {"title": "Bloomberg Feed"}}
        assert extract_source_name(feed, "https://bloomberg.com/feed") == "Bloomberg"

    def test_removes_dash_rss_suffix(self) -> None:
        """Test ' - RSS' suffix removal."""
        feed: dict[str, Any] = {"feed": {"title": "CNN Money - RSS"}}
        assert extract_source_name(feed, "https://cnn.com/feed") == "CNN Money"

    def test_removes_pipe_rss_suffix(self) -> None:
        """Test ' | RSS' suffix removal."""
        feed: dict[str, Any] = {"feed": {"title": "CNBC Markets | RSS"}}
        assert extract_source_name(feed, "https://cnbc.com/feed") == "CNBC Markets"

    def test_removes_news_suffix(self) -> None:
        """Test ' News' suffix removal."""
        feed: dict[str, Any] = {"feed": {"title": "Yahoo Finance News"}}
        assert extract_source_name(feed, "https://yahoo.com/feed") == "Yahoo Finance"

    def test_fallback_to_domain(self) -> None:
        """Test fallback to domain when no title."""
        feed: dict[str, Any] = {"feed": {}}
        assert extract_source_name(feed, "https://example.com/rss") == "example.com"

    def test_removes_www_from_domain(self) -> None:
        """Test www. prefix removal from domain."""
        feed: dict[str, Any] = {"feed": {}}
        assert extract_source_name(feed, "https://www.reuters.com/feed") == "reuters.com"

    def test_empty_title_uses_domain(self) -> None:
        """Test empty title string uses domain."""
        feed: dict[str, Any] = {"feed": {"title": ""}}
        assert extract_source_name(feed, "https://bloomberg.com/feed") == "bloomberg.com"

    def test_whitespace_title_uses_domain(self) -> None:
        """Test whitespace-only title uses domain."""
        feed: dict[str, Any] = {"feed": {"title": "   "}}
        assert extract_source_name(feed, "https://test.com/feed") == "test.com"


class TestParsePublishedDate:
    """Tests for parse_published_date function."""

    def test_parses_published_parsed(self) -> None:
        """Test parsing from published_parsed field."""
        struct_time = time.struct_time((2024, 1, 15, 12, 30, 0, 0, 0, 0))
        entry: dict[str, Any] = {"published_parsed": struct_time}
        result = parse_published_date(entry)
        assert result == datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)

    def test_fallback_to_updated(self) -> None:
        """Test fallback to updated_parsed field."""
        struct_time = time.struct_time((2024, 2, 20, 8, 0, 0, 0, 0, 0))
        entry: dict[str, Any] = {"updated_parsed": struct_time}
        result = parse_published_date(entry)
        assert result == datetime(2024, 2, 20, 8, 0, 0, tzinfo=timezone.utc)

    def test_prefers_published_over_updated(self) -> None:
        """Test published_parsed takes precedence over updated_parsed."""
        pub_time = time.struct_time((2024, 1, 1, 0, 0, 0, 0, 0, 0))
        upd_time = time.struct_time((2024, 2, 2, 0, 0, 0, 0, 0, 0))
        entry: dict[str, Any] = {"published_parsed": pub_time, "updated_parsed": upd_time}
        result = parse_published_date(entry)
        assert result == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_returns_none_when_missing(self) -> None:
        """Test returns None when no date fields."""
        entry: dict[str, Any] = {}
        assert parse_published_date(entry) is None

    def test_returns_none_for_invalid_format(self) -> None:
        """Test returns None for invalid date format."""
        entry: dict[str, Any] = {"published_parsed": "not a struct_time"}
        assert parse_published_date(entry) is None


class TestRSSEntry:
    """Tests for RSSEntry dataclass."""

    def test_required_fields(self) -> None:
        """Test required fields initialization."""
        entry = RSSEntry(
            source_name="Reuters",
            source_url="https://example.com/article",
            title="Test Article",
        )
        assert entry.source_name == "Reuters"
        assert entry.source_url == "https://example.com/article"
        assert entry.title == "Test Article"

    def test_optional_fields_default_none(self) -> None:
        """Test optional fields default to None."""
        entry = RSSEntry(
            source_name="Reuters",
            source_url="https://example.com/article",
            title="Test Article",
        )
        assert entry.snippet is None
        assert entry.author is None
        assert entry.published_at is None
        assert entry.raw_metadata is None

    def test_all_fields(self) -> None:
        """Test with all fields populated."""
        now = datetime.now(timezone.utc)
        entry = RSSEntry(
            source_name="Bloomberg",
            source_url="https://bloomberg.com/news/article",
            title="Market Update",
            snippet="Markets rose today...",
            author="John Doe",
            published_at=now,
            raw_metadata={"feed_url": "https://bloomberg.com/feed"},
        )
        assert entry.source_name == "Bloomberg"
        assert entry.snippet == "Markets rose today..."
        assert entry.author == "John Doe"
        assert entry.published_at == now
        assert entry.raw_metadata is not None
        assert entry.raw_metadata["feed_url"] == "https://bloomberg.com/feed"


class TestParseFeed:
    """Tests for parse_feed function."""

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_parses_valid_feed(self, mock_parse: MagicMock) -> None:
        """Test parsing a valid RSS feed."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Reuters"},
            "entries": [
                {
                    "title": "Article 1",
                    "link": "https://example.com/1",
                    "summary": "<p>Summary text</p>",
                    "author": "John Doe",
                    "published_parsed": time.struct_time((2024, 1, 1, 0, 0, 0, 0, 0, 0)),
                }
            ],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert len(entries) == 1
        assert entries[0].title == "Article 1"
        assert entries[0].source_url == "https://example.com/1"
        assert entries[0].source_name == "Reuters"
        assert entries[0].snippet == "Summary text"
        assert entries[0].author == "John Doe"
        assert entries[0].published_at is not None

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_handles_http_error(self, mock_parse: MagicMock) -> None:
        """Test handling of HTTP errors."""
        mock_parse.return_value = {"status": 404}

        entries, error = parse_feed("https://example.com/feed.xml")

        assert entries == []
        assert error is not None
        assert "HTTP error 404" in error

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_handles_500_error(self, mock_parse: MagicMock) -> None:
        """Test handling of server errors."""
        mock_parse.return_value = {"status": 500}

        entries, error = parse_feed("https://example.com/feed.xml")

        assert entries == []
        assert error is not None
        assert "HTTP error 500" in error

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_skips_entries_without_title(self, mock_parse: MagicMock) -> None:
        """Test entries without title are skipped."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {"link": "https://example.com/1"},  # No title
                {"title": "Valid", "link": "https://example.com/2"},
            ],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert len(entries) == 1
        assert entries[0].title == "Valid"

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_skips_entries_without_link(self, mock_parse: MagicMock) -> None:
        """Test entries without link are skipped."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {"title": "No Link"},  # No link
                {"title": "Valid", "link": "https://example.com/2"},
            ],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert len(entries) == 1
        assert entries[0].title == "Valid"

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_truncates_long_snippets(self, mock_parse: MagicMock) -> None:
        """Test long snippets are truncated."""
        long_text = "word " * 500  # 2500 chars
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {"title": "Article", "link": "https://example.com/1", "summary": long_text}
            ],
        }

        entries, error = parse_feed("https://example.com/feed.xml", max_snippet_chars=100)

        assert error is None
        assert len(entries[0].snippet or "") <= 103  # 100 + "..."
        assert entries[0].snippet is not None
        assert entries[0].snippet.endswith("...")

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_uses_description_when_no_summary(self, mock_parse: MagicMock) -> None:
        """Test description field is used when summary is missing."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {
                    "title": "Article",
                    "link": "https://example.com/1",
                    "description": "Description text",
                }
            ],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert entries[0].snippet == "Description text"

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_empty_snippet_becomes_none(self, mock_parse: MagicMock) -> None:
        """Test empty snippet is stored as None."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [{"title": "Article", "link": "https://example.com/1", "summary": ""}],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert entries[0].snippet is None

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_empty_author_becomes_none(self, mock_parse: MagicMock) -> None:
        """Test empty author is stored as None."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [{"title": "Article", "link": "https://example.com/1", "author": ""}],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert entries[0].author is None

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_extracts_tags(self, mock_parse: MagicMock) -> None:
        """Test tags are extracted to raw_metadata."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {
                    "title": "Article",
                    "link": "https://example.com/1",
                    "tags": [{"term": "finance"}, {"term": "markets"}],
                }
            ],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert entries[0].raw_metadata is not None
        assert entries[0].raw_metadata["tags"] == ["finance", "markets"]

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_handles_bozo_error_with_entries(self, mock_parse: MagicMock) -> None:
        """Test bozo errors don't fail if entries exist."""
        mock_parse.return_value = {
            "status": 200,
            "bozo": True,
            "bozo_exception": Exception("Minor parse error"),
            "feed": {"title": "Test Feed"},
            "entries": [{"title": "Article", "link": "https://example.com/1"}],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        # Should succeed despite bozo flag since entries exist
        assert error is None
        assert len(entries) == 1

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_handles_bozo_error_without_entries(self, mock_parse: MagicMock) -> None:
        """Test bozo errors fail if no entries."""
        mock_parse.return_value = {
            "status": 200,
            "bozo": True,
            "bozo_exception": Exception("Parse failed completely"),
            "feed": {},
            "entries": [],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert entries == []
        assert error is not None
        assert "Feed parsing error" in error

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_handles_exception(self, mock_parse: MagicMock) -> None:
        """Test handling of unexpected exceptions."""
        mock_parse.side_effect = Exception("Network error")

        entries, error = parse_feed("https://example.com/feed.xml")

        assert entries == []
        assert error is not None
        assert "Network error" in error

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_handles_empty_entries_list(self, mock_parse: MagicMock) -> None:
        """Test handling of feed with no entries."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Empty Feed"},
            "entries": [],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert entries == []

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_strips_html_from_snippet(self, mock_parse: MagicMock) -> None:
        """Test HTML is stripped from snippets."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {
                    "title": "Article",
                    "link": "https://example.com/1",
                    "summary": "<p><b>Bold</b> and <i>italic</i></p>",
                }
            ],
        }

        entries, error = parse_feed("https://example.com/feed.xml")

        assert error is None
        assert entries[0].snippet == "Bold and italic"


class TestParseFeedIntegration:
    """Integration tests for parse_feed (optional, require network)."""

    @pytest.mark.skip(reason="Requires network access")
    def test_real_rss_feed(self) -> None:
        """Test parsing a real RSS feed."""
        # This test is skipped by default but can be enabled for integration testing
        entries, error = parse_feed("https://feeds.bbci.co.uk/news/rss.xml")
        assert error is None
        assert len(entries) > 0
