"""NewsAPI client with multi-key rotation.

TheNewsAPI.com integration for fetching news headlines and articles.

Key Features:
- Round-robin key rotation across multiple API keys
- Automatic failover on 402 (usage limit) and 429 (rate limit) errors
- Usage tracking via X-UsageLimit-* headers

Usage:
    client = NewsApiClient(config)
    result = client.get_headlines(locale="us", categories=["business"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from argus.config import NewsApiConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://api.thenewsapi.com/v1/news"


class NewsApiError(Exception):
    """Base exception for NewsAPI errors."""

    def __init__(self, message: str, status_code: int, key_index: int):
        super().__init__(message)
        self.status_code = status_code
        self.key_index = key_index


class UsageLimitError(NewsApiError):
    """Raised when usage limit (402) is hit."""

    def __init__(self, message: str, key_index: int, limit: int, remaining: int):
        super().__init__(message, 402, key_index)
        self.limit = limit
        self.remaining = remaining


class RateLimitError(NewsApiError):
    """Raised when rate limit (429) is hit."""

    def __init__(self, message: str, key_index: int, retry_after: Optional[int] = None):
        super().__init__(message, 429, key_index)
        self.retry_after = retry_after


@dataclass
class NewsArticle:
    """Single news article from API response."""

    uuid: str
    title: str
    description: Optional[str]
    snippet: Optional[str]
    url: str
    image_url: Optional[str]
    language: str
    published_at: str
    source: str
    categories: list[str]
    relevance_score: Optional[float] = None
    keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict) -> "NewsArticle":
        """Create from API response dict."""
        return cls(
            uuid=data.get("uuid", ""),
            title=data.get("title", ""),
            description=data.get("description"),
            snippet=data.get("snippet"),
            url=data.get("url", ""),
            image_url=data.get("image_url"),
            language=data.get("language", "en"),
            published_at=data.get("published_at", ""),
            source=data.get("source", ""),
            categories=data.get("categories", []),
            relevance_score=data.get("relevance_score"),
            keywords=data.get("keywords", []),
        )


@dataclass
class NewsApiResponse:
    """API response container."""

    data: list[NewsArticle]
    meta: dict
    key_index: int

    @property
    def total_found(self) -> int:
        """Total articles matching query."""
        return self.meta.get("found", 0)

    @property
    def returned(self) -> int:
        """Articles returned in this response."""
        val = self.meta.get("returned")
        if val is None:
            return len(self.data)  # Fallback to actual count
        try:
            return int(val)
        except (ValueError, TypeError):
            return len(self.data)

    @property
    def usage_limit(self) -> Optional[int]:
        """Monthly limit for the key used."""
        val = self.meta.get("limit")
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    @property
    def usage_remaining(self) -> Optional[int]:
        """Remaining requests for the month."""
        val = self.meta.get("remaining")
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None


class NewsApiClient:
    """NewsAPI client with key rotation.

    Supports:
    - Multiple API keys with round-robin rotation
    - Automatic failover on 402/429 errors
    - Usage tracking per key
    """

    def __init__(self, config: NewsApiConfig, client: Optional[httpx.Client] = None):
        """Initialize client.

        Args:
            config: NewsApiConfig instance.
            client: Optional httpx Client for dependency injection.
        """
        self.config = config
        self.keys = config.api_keys
        self.key_index = 0  # Round-robin index

        if not self.keys:
            raise ValueError("No API keys configured. Set NEWS_API_KEYS in environment.")

        if client:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(timeout=config.timeout_seconds)
            self._owns_client = True

    def __enter__(self) -> "NewsApiClient":
        """Context manager entry."""
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        """Context manager exit."""
        if self._owns_client:
            self._client.close()

    def _get_current_key(self) -> str:
        """Get the current API key for rotation."""
        return self.keys[self.key_index % len(self.keys)]

    def _rotate_key(self) -> None:
        """Rotate to next key (round-robin)."""
        self.key_index = (self.key_index + 1) % len(self.keys)
        logger.info(f"Rotated to key index {self.key_index} ({len(self.keys)} keys total)")

    def _should_retry(self, status_code: int) -> bool:
        """Check if error is retryable."""
        return status_code in {402, 429, 500, 502, 503, 504}

    def _build_params(
        self,
        *,
        locale: Optional[str] = None,
        language: Optional[str] = None,
        categories: Optional[list[str]] = None,
        search: Optional[str] = None,
        domains: Optional[list[str]] = None,
        source_ids: Optional[list[str]] = None,
        exclude_categories: Optional[list[str]] = None,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        limit: int = 10,
        page: int = 1,
    ) -> dict:
        """Build query parameters for API."""
        params: dict = {"api_token": self._get_current_key()}

        if locale:
            params["locale"] = locale
        if language:
            params["language"] = language
        if categories:
            params["categories"] = ",".join(categories)
        if search:
            params["search"] = search
        if domains:
            params["domains"] = ",".join(domains)
        if source_ids:
            params["source_ids"] = ",".join(source_ids)
        if exclude_categories:
            params["exclude_categories"] = ",".join(exclude_categories)
        if published_after:
            params["published_after"] = published_after
        if published_before:
            params["published_before"] = published_before
        if limit != 10:
            params["limit"] = limit
        if page != 1:
            params["page"] = page

        return params

    def _request(
        self,
        endpoint: str,
        *,
        retries: int = 2,
        **params,
    ) -> NewsApiResponse:
        """Make API request with key rotation on failure.

        Args:
            endpoint: API endpoint (e.g., "headlines", "all", "top")
            retries: Maximum retry attempts with different keys.
            **params: Query parameters.

        Returns:
            NewsApiResponse with articles and metadata.

        Raises:
            UsageLimitError: When all keys hit usage limit (402).
            RateLimitError: When all keys hit rate limit (429).
            NewsApiError: On other API errors.
        """
        url = f"{BASE_URL}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self._client.get(url, params=params)

                # Parse usage headers
                meta = {
                    "found": response.headers.get("X-Meta-found"),
                    "returned": response.headers.get("X-Meta-returned"),
                    "limit": response.headers.get("X-UsageLimit-Limit"),
                    "remaining": response.headers.get("X-UsageLimit-Remaining"),
                }

                if response.status_code == 200:
                    data = response.json()
                    articles = [NewsArticle.from_api(a) for a in data.get("data", [])]
                    return NewsApiResponse(data=articles, meta=meta, key_index=self.key_index)

                # Handle retryable errors
                if self._should_retry(response.status_code):
                    error_msg = response.text or f"HTTP {response.status_code}"

                    if response.status_code == 402:
                        limit_hdr = response.headers.get("X-UsageLimit-Limit", "unknown")
                        remaining_hdr = response.headers.get("X-UsageLimit-Remaining", "unknown")
                        logger.warning(
                            f"Key {self.key_index} hit usage limit (402). "
                            f"Limit: {limit_hdr}, Remaining: {remaining_hdr}"
                        )
                        raise UsageLimitError(
                            f"Usage limit reached: {error_msg}",
                            key_index=self.key_index,
                            limit=int(limit_hdr) if limit_hdr.isdigit() else 0,
                            remaining=int(remaining_hdr) if remaining_hdr.isdigit() else 0,
                        )

                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        logger.warning(f"Key {self.key_index} hit rate limit (429)")
                        raise RateLimitError(
                            f"Rate limit exceeded: {error_msg}",
                            key_index=self.key_index,
                            retry_after=int(retry_after) if retry_after else None,
                        )

                    logger.warning(
                        f"API error {response.status_code} on key {self.key_index}, "
                        f"rotating (attempt {attempt + 1}/{retries})"
                    )
                    self._rotate_key()
                    params["api_token"] = self._get_current_key()
                    continue

                # Non-retryable error
                raise NewsApiError(
                    f"API error: {response.status_code} - {response.text}",
                    response.status_code,
                    self.key_index,
                )

            except (UsageLimitError, RateLimitError):
                # Always rotate on 402/429, even on last attempt
                if attempt < retries - 1:
                    self._rotate_key()
                    params["api_token"] = self._get_current_key()
                    continue
                raise

            except httpx.RequestError as e:
                raise NewsApiError(f"Request failed: {e}", 0, self.key_index)

        raise NewsApiError("Max retries exceeded", 0, self.key_index)

    def get_headlines(
        self,
        *,
        locale: Optional[str] = None,
        language: Optional[str] = None,
        categories: Optional[list[str]] = None,
        search: Optional[str] = None,
        domains: Optional[list[str]] = None,
        exclude_categories: Optional[list[str]] = None,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        limit: int = 10,
        page: int = 1,
    ) -> NewsApiResponse:
        """Fetch news headlines.

        Args:
            locale: Country code (e.g., "us", "gb").
            language: Language code (e.g., "en", "es").
            categories: Filter by categories.
            search: Search query string.
            domains: Filter by domains.
            exclude_categories: Categories to exclude.
            published_after: ISO datetime or date.
            published_before: ISO datetime or date.
            limit: Results per page (max 100).
            page: Page number.

        Returns:
            NewsApiResponse with articles.
        """
        params = self._build_params(
            locale=locale or self.config.locale,
            language=language or self.config.language,
            categories=categories or self.config.categories,
            search=search,
            domains=domains,
            exclude_categories=exclude_categories,
            published_after=published_after,
            published_before=published_before,
            limit=limit,
            page=page,
        )
        return self._request("headlines", **params)

    def get_all(
        self,
        *,
        locale: Optional[str] = None,
        language: Optional[str] = None,
        categories: Optional[list[str]] = None,
        search: Optional[str] = None,
        domains: Optional[list[str]] = None,
        source_ids: Optional[list[str]] = None,
        exclude_categories: Optional[list[str]] = None,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        limit: int = 10,
        page: int = 1,
    ) -> NewsApiResponse:
        """Fetch all news with filters.

        Args:
            locale: Country code.
            language: Language code.
            categories: Filter by categories.
            search: Search query.
            domains: Filter by domains.
            source_ids: Filter by source IDs.
            exclude_categories: Categories to exclude.
            published_after: ISO datetime or date.
            published_before: ISO datetime or date.
            limit: Results per page (max 100).
            page: Page number.

        Returns:
            NewsApiResponse with articles.
        """
        params = self._build_params(
            locale=locale or self.config.locale,
            language=language or self.config.language,
            categories=categories or self.config.categories,
            search=search,
            domains=domains,
            source_ids=source_ids,
            exclude_categories=exclude_categories,
            published_after=published_after,
            published_before=published_before,
            limit=limit,
            page=page,
        )
        return self._request("all", **params)

    def get_top(
        self,
        *,
        locale: Optional[str] = None,
        language: Optional[str] = None,
        categories: Optional[list[str]] = None,
        search: Optional[str] = None,
        domains: Optional[list[str]] = None,
        limit: int = 10,
        page: int = 1,
    ) -> NewsApiResponse:
        """Fetch top stories.

        Args:
            locale: Country code.
            language: Language code.
            categories: Filter by categories.
            search: Search query.
            domains: Filter by domains.
            limit: Results per page (max 100).
            page: Page number.

        Returns:
            NewsApiResponse with articles.
        """
        params = self._build_params(
            locale=locale or self.config.locale,
            language=language or self.config.language,
            categories=categories or self.config.categories,
            search=search,
            domains=domains,
            limit=limit,
            page=page,
        )
        return self._request("top", **params)

    def get_by_uuid(self, uuid: str) -> NewsApiResponse:
        """Fetch single article by UUID.

        Args:
            uuid: Article UUID.

        Returns:
            NewsApiResponse with single article.
        """
        params = self._build_params()
        return self._request(f"uuid/{uuid}", **params)

    def get_similar(self, uuid: str) -> NewsApiResponse:
        """Fetch similar articles.

        Args:
            uuid: Source article UUID.

        Returns:
            NewsApiResponse with similar articles.
        """
        params = self._build_params()
        return self._request(f"similar/{uuid}", **params)

    def get_sources(
        self,
        *,
        locale: Optional[str] = None,
        language: Optional[str] = None,
        categories: Optional[list[str]] = None,
    ) -> dict:
        """Fetch available sources.

        Args:
            locale: Filter by locale.
            language: Filter by language.
            categories: Filter by categories.

        Returns:
            API response as dict (sources format differs from articles).
        """
        params = self._build_params(
            locale=locale or self.config.locale,
            language=language or self.config.language,
            categories=categories or self.config.categories,
        )
        url = f"{BASE_URL}/sources"
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_usage_status(self) -> list[dict]:
        """Get usage status for all configured keys.

        Makes a lightweight request to check remaining quota.

        Returns:
            List of dicts with key_index and remaining usage.
        """
        status = []
        original_index = self.key_index

        for i in range(len(self.keys)):
            self.key_index = i
            try:
                # Use top endpoint with minimal params for usage check
                params = self._build_params(limit=1)
                response = self._client.get(f"{BASE_URL}/top", params=params)
                if response.status_code == 200:
                    remaining = response.headers.get("X-UsageLimit-Remaining", "unknown")
                    limit = response.headers.get("X-UsageLimit-Limit", "unknown")
                    status.append(
                        {
                            "key_index": i,
                            "key_prefix": f"{self.keys[i][:4]}...",
                            "limit": limit,
                            "remaining": remaining,
                        }
                    )
                else:
                    status.append(
                        {
                            "key_index": i,
                            "key_prefix": f"{self.keys[i][:4]}...",
                            "error": response.status_code,
                        }
                    )
            except httpx.RequestError as e:
                status.append(
                    {
                        "key_index": i,
                        "key_prefix": f"{self.keys[i][:4]}...",
                        "error": str(e),
                    }
                )

        # Restore original key index
        self.key_index = original_index
        return status
