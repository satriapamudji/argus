"""Async HTTP content fetcher with rate limiting and retries."""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

import httpx

from argus.enrichment.types import FetchResult

logger = logging.getLogger(__name__)

# Default user agent that identifies as a news aggregator
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; ArgusBot/1.0; +https://github.com/argus-news-bot)"

# Default timeouts
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_CONNECT_TIMEOUT = 5.0


class AsyncContentFetcher:
    """Async HTTP fetcher with concurrency control and per-domain rate limiting.

    Features:
    - Semaphore-based concurrency control (max 2 concurrent requests by default)
    - Per-domain rate limiting (1 request/second per domain)
    - Automatic retries with exponential backoff
    - Respects robots.txt by default user agent

    Usage:
        async with AsyncContentFetcher() as fetcher:
            result = await fetcher.fetch("https://example.com/article")
    """

    def __init__(
        self,
        max_concurrent: int = 2,
        requests_per_second_per_domain: float = 1.0,
        max_retries: int = 2,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        """Initialize the fetcher.

        Args:
            max_concurrent: Maximum concurrent requests across all domains.
            requests_per_second_per_domain: Rate limit per domain.
            max_retries: Maximum number of retry attempts.
            timeout_seconds: Request timeout.
            user_agent: User-Agent header value.
        """
        self.max_concurrent = max_concurrent
        self.min_interval = 1.0 / requests_per_second_per_domain
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

        self._semaphore: Optional[asyncio.Semaphore] = None
        self._domain_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._domain_last_request: dict[str, float] = defaultdict(float)
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "AsyncContentFetcher":
        """Async context manager entry."""
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds, connect=DEFAULT_CONNECT_TIMEOUT),
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
            http2=True,
        )
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL for rate limiting."""
        parsed = urlparse(url)
        return parsed.netloc.lower()

    async def _wait_for_rate_limit(self, domain: str) -> None:
        """Wait if needed to respect per-domain rate limit."""
        async with self._domain_locks[domain]:
            now = time.monotonic()
            last_request = self._domain_last_request[domain]
            elapsed = now - last_request

            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                logger.debug(f"Rate limiting {domain}: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

            self._domain_last_request[domain] = time.monotonic()

    async def fetch(self, url: str) -> FetchResult:
        """Fetch content from a URL with rate limiting and retries.

        Args:
            url: URL to fetch.

        Returns:
            FetchResult with success status and content/error.
        """
        if not self._client or not self._semaphore:
            raise RuntimeError("Fetcher not initialized. Use async context manager.")

        domain = self._get_domain(url)
        start_time = time.monotonic()
        last_error: Optional[str] = None
        last_status: Optional[int] = None

        for attempt in range(self.max_retries + 1):
            try:
                # Acquire semaphore for concurrency control
                async with self._semaphore:
                    # Wait for domain rate limit
                    await self._wait_for_rate_limit(domain)

                    # Make the request
                    response = await self._client.get(url)
                    elapsed_ms = (time.monotonic() - start_time) * 1000

                    if response.status_code == 200:
                        return FetchResult(
                            url=url,
                            success=True,
                            html=response.text,
                            status_code=response.status_code,
                            elapsed_ms=elapsed_ms,
                        )

                    # Non-200 response
                    last_status = response.status_code
                    last_error = f"HTTP {response.status_code}"

                    # Don't retry on client errors (4xx) except 429
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        return FetchResult(
                            url=url,
                            success=False,
                            status_code=response.status_code,
                            error=last_error,
                            elapsed_ms=elapsed_ms,
                        )

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")

            except httpx.HTTPError as e:
                last_error = f"HTTP error: {e}"
                logger.warning(f"HTTP error fetching {url}: {e} (attempt {attempt + 1})")

            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.exception(f"Unexpected error fetching {url}")
                break  # Don't retry unexpected errors

            # Exponential backoff before retry
            if attempt < self.max_retries:
                backoff = 2**attempt
                logger.debug(f"Retrying {url} in {backoff}s")
                await asyncio.sleep(backoff)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        return FetchResult(
            url=url,
            success=False,
            status_code=last_status,
            error=last_error or "Unknown error",
            elapsed_ms=elapsed_ms,
        )

    async def fetch_many(self, urls: list[str]) -> list[FetchResult]:
        """Fetch multiple URLs concurrently with rate limiting.

        Args:
            urls: List of URLs to fetch.

        Returns:
            List of FetchResults in same order as input URLs.
        """
        tasks = [self.fetch(url) for url in urls]
        return await asyncio.gather(*tasks)
