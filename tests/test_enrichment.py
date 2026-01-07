"""Tests for content enrichment module."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from argus.enrichment.extractor import (
    extract_article_text,
    truncate_to_excerpt,
    _normalize_whitespace,
)
from argus.enrichment.fetcher import AsyncContentFetcher
from argus.enrichment.types import (
    EnrichmentCandidate,
    EnrichmentResult,
    FetchResult,
)


class TestFetchResult:
    """Tests for FetchResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful fetch result."""
        result = FetchResult(
            url="https://example.com/article",
            success=True,
            html="<html>content</html>",
            status_code=200,
            elapsed_ms=150.5,
        )
        assert result.success is True
        assert result.html == "<html>content</html>"
        assert result.status_code == 200
        assert result.error is None

    def test_failed_result(self) -> None:
        """Test failed fetch result."""
        result = FetchResult(
            url="https://example.com/article",
            success=False,
            status_code=404,
            error="HTTP 404",
            elapsed_ms=50.0,
        )
        assert result.success is False
        assert result.html is None
        assert result.error == "HTTP 404"


class TestEnrichmentResult:
    """Tests for EnrichmentResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful enrichment result."""
        result = EnrichmentResult(
            news_item_id=123,
            success=True,
            content_type="excerpt",
            content_length=500,
        )
        assert result.success is True
        assert result.content_type == "excerpt"
        assert result.content_length == 500
        assert result.error is None

    def test_failed_result(self) -> None:
        """Test failed enrichment result."""
        result = EnrichmentResult(
            news_item_id=123,
            success=False,
            error="Timeout",
        )
        assert result.success is False
        assert result.error == "Timeout"


class TestEnrichmentCandidate:
    """Tests for EnrichmentCandidate dataclass."""

    def test_from_row(self) -> None:
        """Test creating from database row."""
        now = datetime.now(timezone.utc)
        row = (42, "https://example.com/article", "Test Title", now, 85)

        candidate = EnrichmentCandidate.from_row(row)

        assert candidate.id == 42
        assert candidate.source_url == "https://example.com/article"
        assert candidate.title == "Test Title"
        assert candidate.ingested_at == now
        assert candidate.impact_score == 85


class TestNormalizeWhitespace:
    """Tests for whitespace normalization."""

    def test_collapses_multiple_spaces(self) -> None:
        """Test multiple spaces become single space."""
        assert _normalize_whitespace("hello   world") == "hello world"

    def test_collapses_multiple_newlines(self) -> None:
        """Test multiple newlines become double newline."""
        result = _normalize_whitespace("para1\n\n\n\npara2")
        assert result == "para1\n\npara2"

    def test_replaces_tabs(self) -> None:
        """Test tabs are replaced with spaces."""
        assert _normalize_whitespace("hello\tworld") == "hello world"

    def test_strips_line_whitespace(self) -> None:
        """Test lines are stripped."""
        result = _normalize_whitespace("  hello  \n  world  ")
        assert "  hello  " not in result


class TestExtractArticleText:
    """Tests for extract_article_text function."""

    def test_extracts_from_article_tag(self) -> None:
        """Test extraction from article tag."""
        html = """
        <html>
        <body>
            <nav>Navigation</nav>
            <article>
                <h1>Title</h1>
                <p>Article content here.</p>
            </article>
            <footer>Footer</footer>
        </body>
        </html>
        """
        result = extract_article_text(html)
        assert result is not None
        assert "Article content" in result
        # Nav/footer should be stripped
        assert "Navigation" not in result or len(result) < 100

    def test_extracts_from_main_tag(self) -> None:
        """Test extraction from main tag."""
        html = """
        <html>
        <body>
            <header>Header</header>
            <main>
                <p>Main content here.</p>
            </main>
        </body>
        </html>
        """
        result = extract_article_text(html)
        assert result is not None
        assert "Main content" in result

    def test_strips_scripts(self) -> None:
        """Test script tags are removed."""
        html = """
        <html>
        <body>
            <p>Content</p>
            <script>alert('evil');</script>
        </body>
        </html>
        """
        result = extract_article_text(html)
        assert result is not None
        assert "alert" not in result
        assert "evil" not in result

    def test_strips_styles(self) -> None:
        """Test style tags are removed."""
        html = """
        <html>
        <body>
            <style>.class { color: red; }</style>
            <p>Content</p>
        </body>
        </html>
        """
        result = extract_article_text(html)
        assert result is not None
        assert "color" not in result
        assert "Content" in result

    def test_handles_empty_html(self) -> None:
        """Test empty HTML returns None."""
        assert extract_article_text("") is None
        assert extract_article_text("   ") is None

    def test_handles_plain_text(self) -> None:
        """Test plain text is returned as-is."""
        result = extract_article_text("Just plain text")
        assert result is not None
        assert "plain text" in result

    def test_handles_malformed_html(self) -> None:
        """Test malformed HTML doesn't crash."""
        html = "<p>Unclosed tag <div>nested<p>content"
        result = extract_article_text(html)
        assert result is not None
        assert "content" in result

    def test_normalizes_whitespace(self) -> None:
        """Test whitespace is normalized."""
        html = "<p>Multiple   spaces\n\n\nand   newlines</p>"
        result = extract_article_text(html)
        assert result is not None
        assert "  " not in result  # No double spaces


class TestTruncateToExcerpt:
    """Tests for truncate_to_excerpt function."""

    def test_short_text_unchanged(self) -> None:
        """Test text shorter than limit is unchanged."""
        text = "Short text"
        assert truncate_to_excerpt(text, max_chars=100) == text

    def test_exact_length_unchanged(self) -> None:
        """Test text at exact limit is unchanged."""
        text = "x" * 100
        assert truncate_to_excerpt(text, max_chars=100) == text

    def test_truncates_at_sentence_end(self) -> None:
        """Test truncation at sentence boundary when possible."""
        text = "First sentence. Second sentence. Third sentence is very long."
        result = truncate_to_excerpt(text, max_chars=50)
        # Should break after "Second sentence."
        assert result.endswith(".")
        assert len(result) <= 50

    def test_truncates_at_word_boundary(self) -> None:
        """Test truncation at word boundary when no sentence end."""
        text = "word " * 50  # No sentence endings
        result = truncate_to_excerpt(text, max_chars=100)
        assert result.endswith("...")
        assert len(result) <= 103  # 100 + "..."

    def test_handles_no_spaces(self) -> None:
        """Test handling of text with no spaces."""
        text = "x" * 200
        result = truncate_to_excerpt(text, max_chars=100)
        assert len(result) <= 103
        assert result.endswith("...")

    def test_preserves_content_quality(self) -> None:
        """Test at least 50% of limit is used for sentence break."""
        text = "A. " + "x" * 200  # Short sentence then long text
        result = truncate_to_excerpt(text, max_chars=100)
        # Should NOT break after "A." because it's less than 50%
        assert len(result) > 50


class TestAsyncContentFetcher:
    """Tests for AsyncContentFetcher."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test async context manager setup/teardown."""
        async with AsyncContentFetcher() as fetcher:
            assert fetcher._client is not None
            assert fetcher._semaphore is not None

        assert fetcher._client is None

    @pytest.mark.asyncio
    async def test_domain_extraction(self) -> None:
        """Test domain extraction from URL."""
        fetcher = AsyncContentFetcher()
        assert fetcher._get_domain("https://example.com/path") == "example.com"
        assert fetcher._get_domain("https://WWW.EXAMPLE.COM/path") == "www.example.com"
        assert fetcher._get_domain("http://sub.example.com:8080/") == "sub.example.com:8080"

    @pytest.mark.asyncio
    async def test_fetch_not_initialized_raises(self) -> None:
        """Test fetch raises when not initialized."""
        fetcher = AsyncContentFetcher()
        with pytest.raises(RuntimeError, match="not initialized"):
            await fetcher.fetch("https://example.com")

    @pytest.mark.asyncio
    async def test_fetch_success(self) -> None:
        """Test successful fetch."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = MagicMock(
                status_code=200,
                text="<html>content</html>",
            )
            mock_client.aclose = AsyncMock()

            async with AsyncContentFetcher() as fetcher:
                # Replace the client with our mock
                fetcher._client = mock_client
                result = await fetcher.fetch("https://example.com/article")

            assert result.success is True
            assert result.status_code == 200
            assert result.html == "<html>content</html>"
            assert result.error is None

    @pytest.mark.asyncio
    async def test_fetch_http_error(self) -> None:
        """Test handling of HTTP errors."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = MagicMock(status_code=404)
            mock_client.aclose = AsyncMock()

            async with AsyncContentFetcher() as fetcher:
                fetcher._client = mock_client
                result = await fetcher.fetch("https://example.com/notfound")

            assert result.success is False
            assert result.status_code == 404
            assert "404" in (result.error or "")

    @pytest.mark.asyncio
    async def test_fetch_many(self) -> None:
        """Test fetching multiple URLs."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = MagicMock(
                status_code=200,
                text="<html>content</html>",
            )
            mock_client.aclose = AsyncMock()

            async with AsyncContentFetcher() as fetcher:
                fetcher._client = mock_client
                urls = [
                    "https://example.com/1",
                    "https://example.com/2",
                ]
                results = await fetcher.fetch_many(urls)

            assert len(results) == 2
            assert all(r.success for r in results)


class TestAsyncContentFetcherRateLimiting:
    """Tests for rate limiting in AsyncContentFetcher."""

    @pytest.mark.asyncio
    async def test_respects_concurrency_limit(self) -> None:
        """Test semaphore limits concurrent requests."""
        fetcher = AsyncContentFetcher(max_concurrent=1)
        assert fetcher.max_concurrent == 1

    @pytest.mark.asyncio
    async def test_respects_per_domain_rate_limit(self) -> None:
        """Test rate limiting per domain."""
        fetcher = AsyncContentFetcher(requests_per_second_per_domain=10)
        # Should have 0.1 second interval
        assert fetcher.min_interval == 0.1


class TestEnrichmentIntegration:
    """Integration tests for enrichment (require network, skipped by default)."""

    @pytest.mark.skip(reason="Requires network access")
    @pytest.mark.asyncio
    async def test_real_fetch(self) -> None:
        """Test fetching a real URL."""
        async with AsyncContentFetcher() as fetcher:
            result = await fetcher.fetch("https://example.com")
            assert result.success is True
            assert result.html is not None
            assert "Example Domain" in result.html
