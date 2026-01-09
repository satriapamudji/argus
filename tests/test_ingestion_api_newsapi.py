"""Tests for NewsAPI ingestion provider and common utilities."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from argus.pipeline.providers.ingestion_api_common import (
    NormalizedArticle,
    ingest_article,
    parse_iso_datetime,
)
from argus.pipeline.providers.ingestion_api_newsapi import NewsApiIngestionProvider
from argus.pipeline.providers.news_api_client import NewsApiResponse, NewsArticle


class TestParseIsoDatetime:
    """Tests for parse_iso_datetime function."""

    def test_parses_z_suffix(self) -> None:
        """Test parsing ISO datetime with Z suffix."""
        result = parse_iso_datetime("2024-01-15T10:30:00Z")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_parses_milliseconds_z(self) -> None:
        """Test parsing ISO datetime with milliseconds and Z suffix."""
        result = parse_iso_datetime("2024-01-15T10:30:00.123Z")
        assert result == datetime(2024, 1, 15, 10, 30, 0, 123000)

    def test_parses_timezone_offset(self) -> None:
        """Test parsing ISO datetime with timezone offset."""
        result = parse_iso_datetime("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        # Note: converted to naive (UTC assumed)
        assert result.tzinfo is None

    def test_parses_date_only(self) -> None:
        """Test parsing date-only string."""
        result = parse_iso_datetime("2024-01-15")
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    def test_parses_space_separator(self) -> None:
        """Test parsing datetime with space separator."""
        result = parse_iso_datetime("2024-01-15 10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_returns_none_for_invalid(self) -> None:
        """Test returns None for invalid format."""
        result = parse_iso_datetime("not a date")
        assert result is None

    def test_returns_none_for_empty(self) -> None:
        """Test returns None for empty string."""
        assert parse_iso_datetime("") is None
        assert parse_iso_datetime(None) is None


class TestNormalizedArticle:
    """Tests for NormalizedArticle dataclass."""

    def test_creates_with_required_fields(self) -> None:
        """Test creation with required fields only."""
        article = NormalizedArticle(
            url="https://example.com/article",
            title="Test Article",
            source_name="example.com",
        )
        assert article.url == "https://example.com/article"
        assert article.title == "Test Article"
        assert article.source_name == "example.com"
        assert article.snippet is None
        assert article.published_at is None
        assert article.author is None
        assert article.raw_metadata == {}

    def test_creates_with_all_fields(self) -> None:
        """Test creation with all fields."""
        published = datetime(2024, 1, 15, 10, 30, 0)
        article = NormalizedArticle(
            url="https://example.com/article",
            title="Test Article",
            source_name="example.com",
            snippet="Article summary",
            published_at=published,
            author="John Doe",
            raw_metadata={"uuid": "abc-123"},
        )
        assert article.snippet == "Article summary"
        assert article.published_at == published
        assert article.author == "John Doe"
        assert article.raw_metadata == {"uuid": "abc-123"}


class TestIngestArticle:
    """Tests for ingest_article function."""

    def test_skips_duplicate_url(self) -> None:
        """Test that duplicate URLs are skipped."""
        conn = MagicMock()
        article = NormalizedArticle(
            url="https://example.com/article",
            title="Test Article",
            source_name="example.com",
        )

        with patch(
            "argus.pipeline.providers.ingestion_api_common.check_duplicate_by_url"
        ) as mock_check:
            mock_check.return_value = True  # URL exists

            result = ingest_article(conn, article, "us_markets")

            assert result is False
            mock_check.assert_called_once_with(conn, article.url, stream_name="us_markets")

    def test_inserts_new_article(self) -> None:
        """Test that new articles are inserted."""
        conn = MagicMock()
        article = NormalizedArticle(
            url="https://example.com/article",
            title="Test Article",
            source_name="example.com",
            snippet="Summary",
        )

        mock_fingerprint = MagicMock()
        mock_fingerprint.id = 123

        with (
            patch(
                "argus.pipeline.providers.ingestion_api_common.check_duplicate_by_url"
            ) as mock_check,
            patch(
                "argus.pipeline.providers.ingestion_api_common.get_or_create_fingerprint"
            ) as mock_fp,
            patch("argus.pipeline.providers.ingestion_api_common.insert_news_item") as mock_insert,
        ):
            mock_check.return_value = False  # URL is new
            mock_fp.return_value = (mock_fingerprint, True)  # Created new fingerprint

            result = ingest_article(conn, article, "us_markets")

            assert result is True
            mock_insert.assert_called_once()

    def test_skips_existing_fingerprint(self) -> None:
        """Test that articles with existing fingerprints are skipped."""
        conn = MagicMock()
        article = NormalizedArticle(
            url="https://example.com/article",
            title="Test Article",
            source_name="example.com",
        )

        mock_fingerprint = MagicMock()
        mock_fingerprint.id = 123

        with (
            patch(
                "argus.pipeline.providers.ingestion_api_common.check_duplicate_by_url"
            ) as mock_check,
            patch(
                "argus.pipeline.providers.ingestion_api_common.get_or_create_fingerprint"
            ) as mock_fp,
        ):
            mock_check.return_value = False  # URL is new
            mock_fp.return_value = (mock_fingerprint, False)  # Fingerprint already exists

            result = ingest_article(conn, article, "us_markets")

            assert result is False


class TestNewsApiIngestionProvider:
    """Tests for NewsApiIngestionProvider."""

    def test_validate_config_fails_without_keys(self) -> None:
        """Test that validation fails without API keys."""
        provider = NewsApiIngestionProvider()

        mock_config = MagicMock()
        mock_config.api_keys = []
        mock_config.domains = ["reuters.com"]

        with pytest.raises(ValueError, match="NEWS_API_KEYS"):
            provider._validate_config(mock_config)

    def test_validate_config_fails_without_domains(self) -> None:
        """Test that validation fails without domains."""
        provider = NewsApiIngestionProvider()

        mock_config = MagicMock()
        mock_config.api_keys = ["key1"]
        mock_config.domains = []

        with pytest.raises(ValueError, match="domains"):
            provider._validate_config(mock_config)

    def test_validate_config_passes_with_valid_config(self) -> None:
        """Test that validation passes with valid config."""
        provider = NewsApiIngestionProvider()

        mock_config = MagicMock()
        mock_config.api_keys = ["key1"]
        mock_config.domains = ["reuters.com"]

        # Should not raise
        provider._validate_config(mock_config)

    def test_normalize_article_maps_fields(self) -> None:
        """Test that NewsArticle is correctly normalized."""
        provider = NewsApiIngestionProvider()

        news_article = NewsArticle(
            uuid="abc-123",
            title="Test Article",
            description="Full description text",
            snippet="Short snippet",
            url="https://reuters.com/article",
            image_url="https://reuters.com/image.jpg",
            language="en",
            published_at="2024-01-15T10:30:00Z",
            source="reuters.com",
            categories=["business", "finance"],
            keywords=["market", "stocks"],
            relevance_score=0.95,
        )

        normalized = provider._normalize_article(news_article)

        assert normalized.url == "https://reuters.com/article"
        assert normalized.title == "Test Article"
        assert normalized.source_name == "reuters.com"
        # Should prefer description over snippet
        assert normalized.snippet == "Full description text"
        assert normalized.published_at == datetime(2024, 1, 15, 10, 30, 0)
        assert normalized.author is None
        assert normalized.raw_metadata["uuid"] == "abc-123"
        assert normalized.raw_metadata["categories"] == ["business", "finance"]
        assert normalized.raw_metadata["keywords"] == ["market", "stocks"]

    def test_normalize_article_uses_snippet_when_no_description(self) -> None:
        """Test that snippet is used when description is None."""
        provider = NewsApiIngestionProvider()

        news_article = NewsArticle(
            uuid="abc-123",
            title="Test Article",
            description=None,
            snippet="Short snippet",
            url="https://reuters.com/article",
            image_url=None,
            language="en",
            published_at="2024-01-15T10:30:00Z",
            source="reuters.com",
            categories=[],
            keywords=[],
            relevance_score=None,
        )

        normalized = provider._normalize_article(news_article)

        assert normalized.snippet == "Short snippet"

    def test_run_stops_on_duplicate(self) -> None:
        """Test that pagination stops when hitting a duplicate."""
        provider = NewsApiIngestionProvider()

        # Create mock config
        mock_app_config = MagicMock()
        mock_stream = MagicMock()
        mock_stream.name = "us_markets"
        mock_stream.news_api.api_keys = ["key1"]
        mock_stream.news_api.domains = ["reuters.com"]
        mock_stream.news_api.language = "en"
        mock_stream.news_api.lookback_hours = 1
        mock_stream.news_api.max_pages_safety_limit = 50
        mock_stream.news_api.articles_per_request = 3
        mock_stream.news_api.max_new_per_run = 50
        mock_app_config.stream = mock_stream

        # Create mock response with one article
        mock_article = MagicMock()
        mock_article.url = "https://reuters.com/article"
        mock_article.title = "Test"
        mock_article.description = "Desc"
        mock_article.snippet = "Snippet"
        mock_article.source = "reuters.com"
        mock_article.published_at = "2024-01-15T10:30:00Z"
        mock_article.uuid = "abc"
        mock_article.categories = []
        mock_article.keywords = []
        mock_article.image_url = None
        mock_article.language = "en"
        mock_article.relevance_score = None

        mock_response = MagicMock()
        mock_response.data = [mock_article]
        mock_response.returned = 1
        mock_response.usage_remaining = 99
        mock_response.usage_limit = 100

        mock_conn = MagicMock()

        with (
            patch(
                "argus.pipeline.providers.ingestion_api_newsapi.NewsApiClient"
            ) as mock_client_cls,
            patch("argus.pipeline.providers.ingestion_api_newsapi.ingest_article") as mock_ingest,
        ):
            mock_client = MagicMock()
            mock_client.get_all.return_value = mock_response
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # First call returns duplicate (False)
            mock_ingest.return_value = False

            stats = provider.run(config=mock_app_config, conn=mock_conn)

            # Should have called get_all only once (stopped on duplicate)
            assert mock_client.get_all.call_count == 1
            assert stats.entries_found == 1
            assert stats.entries_duplicate == 1
            assert stats.entries_new == 0

    def test_check_budget_stops_at_threshold(self) -> None:
        """Test that budget check correctly identifies when to stop."""
        provider = NewsApiIngestionProvider()

        # Create mock response with low remaining budget
        mock_response = MagicMock()
        mock_response.usage_remaining = 5

        # Should stop when remaining equals threshold
        should_continue, reason = provider._check_budget(mock_response, min_remaining=5)
        assert should_continue is False
        assert reason is not None
        assert "Budget threshold reached" in reason
        assert "5 requests remaining" in reason

        # Should stop when remaining is below threshold
        mock_response.usage_remaining = 3
        should_continue, reason = provider._check_budget(mock_response, min_remaining=5)
        assert should_continue is False

    def test_check_budget_continues_above_threshold(self) -> None:
        """Test that budget check allows continuation above threshold."""
        provider = NewsApiIngestionProvider()

        mock_response = MagicMock()
        mock_response.usage_remaining = 50

        should_continue, reason = provider._check_budget(mock_response, min_remaining=10)
        assert should_continue is True
        assert reason is None

    def test_check_budget_continues_when_disabled(self) -> None:
        """Test that budget check allows continuation when disabled (threshold=0)."""
        provider = NewsApiIngestionProvider()

        mock_response = MagicMock()
        mock_response.usage_remaining = 0  # Exhausted, but enforcement disabled

        should_continue, reason = provider._check_budget(mock_response, min_remaining=0)
        assert should_continue is True
        assert reason is None

    def test_check_budget_continues_when_no_usage_info(self) -> None:
        """Test that budget check allows continuation when usage info is missing."""
        provider = NewsApiIngestionProvider()

        mock_response = MagicMock()
        mock_response.usage_remaining = None  # No usage info from API

        should_continue, reason = provider._check_budget(mock_response, min_remaining=10)
        assert should_continue is True
        assert reason is None

    def test_run_stops_on_budget_threshold(self) -> None:
        """Test that ingestion stops when budget threshold is reached."""
        provider = NewsApiIngestionProvider()

        # Create mock config with budget enforcement
        mock_app_config = MagicMock()
        mock_stream = MagicMock()
        mock_stream.name = "us_markets"
        mock_stream.news_api.api_keys = ["key1"]
        mock_stream.news_api.domains = ["reuters.com"]
        mock_stream.news_api.language = "en"
        mock_stream.news_api.lookback_hours = 1
        mock_stream.news_api.max_pages_safety_limit = 50
        mock_stream.news_api.articles_per_request = 3
        mock_stream.news_api.max_new_per_run = 50
        mock_stream.news_api.min_remaining_budget = 10  # Stop at 10 remaining
        mock_app_config.stream = mock_stream

        # Create mock article
        mock_article = MagicMock()
        mock_article.url = "https://reuters.com/article"
        mock_article.title = "Test"
        mock_article.description = "Desc"
        mock_article.snippet = "Snippet"
        mock_article.source = "reuters.com"
        mock_article.published_at = "2024-01-15T10:30:00Z"
        mock_article.uuid = "abc"
        mock_article.categories = []
        mock_article.keywords = []
        mock_article.image_url = None
        mock_article.language = "en"
        mock_article.relevance_score = None

        # Response with low budget - should trigger stop
        mock_response = MagicMock()
        mock_response.data = [mock_article]
        mock_response.returned = 3  # Full page, would normally continue
        mock_response.usage_remaining = 8  # Below threshold of 10
        mock_response.usage_limit = 100

        mock_conn = MagicMock()

        with (
            patch(
                "argus.pipeline.providers.ingestion_api_newsapi.NewsApiClient"
            ) as mock_client_cls,
            patch("argus.pipeline.providers.ingestion_api_newsapi.ingest_article") as mock_ingest,
        ):
            mock_client = MagicMock()
            mock_client.get_all.return_value = mock_response
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Article is new (would normally continue)
            mock_ingest.return_value = True

            stats = provider.run(config=mock_app_config, conn=mock_conn)

            # Should have called get_all only once (stopped on budget)
            assert mock_client.get_all.call_count == 1
            assert stats.entries_new == 1
