"""NewsAPI ingestion provider.

Integrates TheNewsAPI.com as an ingestion source with:
- Smart pagination (stops on duplicate or end of results)
- Domain filtering to preserve API quota
- Lookback window for recent articles only
- Budget enforcement to prevent quota exhaustion
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig, NewsApiConfig
from argus.ingestion.rss_worker import IngestionStats
from argus.pipeline.providers.ingestion_api_common import (
    NormalizedArticle,
    ingest_article,
    parse_iso_datetime,
)
from argus.pipeline.providers.news_api_client import (
    NewsApiClient,
    NewsApiError,
    NewsApiResponse,
    NewsArticle,
)

logger = logging.getLogger(__name__)


class NewsApiIngestionProvider:
    """Ingestion provider for TheNewsAPI.

    Fetches articles from TheNewsAPI using configured filters and
    smart pagination to minimize API quota usage.
    """

    def _validate_config(self, config: NewsApiConfig) -> None:
        """Validate configuration, fail fast if missing required settings.

        Args:
            config: NewsAPI configuration.

        Raises:
            ValueError: If required configuration is missing.
        """
        if not config.api_keys:
            raise ValueError(
                "NewsAPI keys not configured. "
                "Set NEWS_API_KEYS environment variable with comma-separated API keys."
            )

        if not config.domains:
            raise ValueError(
                "NewsAPI domains not configured. "
                "Add 'domains=reuters.com,bloomberg.com' to apis/newsapi_{stream}.txt"
            )

    def _check_budget(
        self, response: NewsApiResponse, min_remaining: int
    ) -> tuple[bool, Optional[str]]:
        """Check if we should continue based on API budget.

        Args:
            response: API response containing usage headers.
            min_remaining: Minimum remaining requests to preserve.

        Returns:
            Tuple of (should_continue, reason_if_stopping).
        """
        if min_remaining <= 0:
            # Budget enforcement disabled
            return True, None

        remaining = response.usage_remaining
        if remaining is None:
            # No usage info available, continue cautiously
            return True, None

        if remaining <= min_remaining:
            reason = (
                f"Budget threshold reached: {remaining} requests remaining, "
                f"threshold is {min_remaining}"
            )
            return False, reason

        return True, None

    def _normalize_article(self, article: NewsArticle) -> NormalizedArticle:
        """Convert NewsArticle to NormalizedArticle.

        Args:
            article: NewsArticle from API response.

        Returns:
            NormalizedArticle for database insertion.
        """
        # Prefer description over snippet (usually longer/better)
        snippet = article.description or article.snippet

        # Build raw_metadata with API-specific fields
        raw_metadata = {
            "uuid": article.uuid,
            "categories": article.categories,
            "keywords": article.keywords,
            "image_url": article.image_url,
            "language": article.language,
            "relevance_score": article.relevance_score,
        }

        return NormalizedArticle(
            url=article.url,
            title=article.title,
            source_name=article.source,
            snippet=snippet,
            published_at=parse_iso_datetime(article.published_at),
            author=None,  # TheNewsAPI doesn't provide author
            raw_metadata=raw_metadata,
        )

    def run(self, *, config: ArgusConfig, conn: Connection) -> IngestionStats:
        """Run ingestion from TheNewsAPI.

        Fetches articles with sliding window pagination:
        1. Calculate published_after from lookback_hours
        2. Fetch pages until:
           - ANY duplicate is found (sliding window detection)
           - Empty response (no more articles)
           - Fewer articles than requested (end of results)
           - Safety limit reached (max_pages_safety_limit)

        The sliding window approach means: if page N returns [a,b,c] and
        page N+1 returns [c,d,e], we stop because 'c' is a duplicate,
        indicating we've caught up to previously ingested content.

        Args:
            config: Argus configuration.
            conn: Database connection.

        Returns:
            IngestionStats with ingestion results.
        """
        newsapi_config = config.stream.news_api
        stream_name = config.stream.name

        # Validate configuration (fail fast)
        self._validate_config(newsapi_config)

        stats = IngestionStats()

        # Calculate published_after timestamp (UTC)
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        published_after = now_utc - timedelta(hours=newsapi_config.lookback_hours)
        published_after_str = published_after.strftime("%Y-%m-%dT%H:%M:%S")

        # Safety limit to prevent infinite loops (high default: 50 pages)
        safety_limit = newsapi_config.max_pages_safety_limit

        logger.info(
            f"Starting NewsAPI ingestion for stream '{stream_name}': "
            f"domains={newsapi_config.domains}, lookback={newsapi_config.lookback_hours}h, "
            f"limit={newsapi_config.articles_per_request}, "
            f"min_budget={newsapi_config.min_remaining_budget}"
        )

        try:
            with NewsApiClient(newsapi_config) as client:
                page = 0
                max_new = newsapi_config.max_new_per_run
                min_budget = newsapi_config.min_remaining_budget

                while True:
                    page += 1

                    # Safety limit check
                    if page > safety_limit:
                        logger.warning(f"Reached safety limit of {safety_limit} pages, stopping")
                        break

                    # Max new articles limit (prevents over-fetching on bootstrap)
                    if stats.entries_new >= max_new:
                        logger.info(f"Reached max new articles limit ({max_new}), stopping")
                        break

                    logger.debug(f"Fetching page {page}")

                    response = client.get_all(
                        language=newsapi_config.language,
                        domains=newsapi_config.domains,
                        published_after=published_after_str,
                        limit=newsapi_config.articles_per_request,
                        page=page,
                    )

                    if not response.data:
                        logger.debug(f"No articles returned on page {page}, stopping pagination")
                        break

                    new_on_page = 0
                    dup_on_page = 0
                    for article in response.data:
                        stats.entries_found += 1
                        normalized = self._normalize_article(article)

                        if ingest_article(conn, normalized, stream_name):
                            stats.entries_new += 1
                            new_on_page += 1
                        else:
                            stats.entries_duplicate += 1
                            dup_on_page += 1

                    # Log usage info if available
                    if response.usage_remaining is not None:
                        logger.info(
                            f"API usage: {response.usage_remaining} requests remaining "
                            f"(limit: {response.usage_limit})"
                        )

                    # Budget enforcement: stop if remaining requests below threshold
                    should_continue, budget_reason = self._check_budget(response, min_budget)
                    if not should_continue:
                        logger.warning(budget_reason)
                        break

                    logger.debug(f"Page {page}: {new_on_page} new, {dup_on_page} duplicates")

                    # Stop condition: ALL articles on page are duplicates
                    # This means we've caught up to previous ingestion
                    if new_on_page == 0:
                        logger.debug(
                            f"All {dup_on_page} articles on page {page} are duplicates, "
                            "caught up - stopping pagination"
                        )
                        break

                    # Received fewer articles than requested = end of results
                    if response.returned < newsapi_config.articles_per_request:
                        logger.debug(
                            f"Received {response.returned} articles "
                            f"(requested {newsapi_config.articles_per_request}), "
                            f"end of results - stopping pagination"
                        )
                        break

                    stats.feeds_processed = page  # Track pages as "feeds"

        except NewsApiError as e:
            error_msg = f"NewsAPI error: {e}"
            stats.errors.append(error_msg)
            stats.feeds_failed += 1
            logger.error(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error during NewsAPI ingestion: {e}"
            stats.errors.append(error_msg)
            stats.feeds_failed += 1
            logger.exception(error_msg)

        logger.info(
            f"NewsAPI ingestion complete: "
            f"found={stats.entries_found}, new={stats.entries_new}, "
            f"duplicates={stats.entries_duplicate}"
        )

        return stats
