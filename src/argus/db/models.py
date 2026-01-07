"""Database models (row types) for Argus.

These are typed dataclasses representing database rows.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class NewsFingerprintRow:
    """Row type for news_fingerprints table.

    Long-lived fingerprints for deduplication. Retained 1-10 years.
    """

    id: int
    hash_url: str  # sha256 of normalized URL
    hash_text: Optional[str]  # sha256 of normalized title + snippet
    simhash: Optional[int]  # 64-bit SimHash signature
    source_name: str
    first_seen_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "NewsFingerprintRow":
        """Create from database row tuple."""
        return cls(
            id=row[0],
            hash_url=row[1],
            hash_text=row[2],
            simhash=row[3],
            source_name=row[4],
            first_seen_at=row[5],
            last_seen_at=row[6],
        )


@dataclass
class NewsItemRow:
    """Row type for news_items table.

    Partitioned by day on ingested_at. Retained 60 days by default.
    """

    id: int
    fingerprint_id: int
    source_name: str
    source_url: str
    title: str
    snippet: Optional[str]
    author: Optional[str]
    published_at: Optional[datetime]
    ingested_at: datetime
    raw_metadata: Optional[dict[str, Any]]  # JSONB

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "NewsItemRow":
        """Create from database row tuple."""
        return cls(
            id=row[0],
            fingerprint_id=row[1],
            source_name=row[2],
            source_url=row[3],
            title=row[4],
            snippet=row[5],
            author=row[6],
            published_at=row[7],
            ingested_at=row[8],
            raw_metadata=row[9],
        )


@dataclass
class NewsContentRow:
    """Row type for news_content table.

    Optional storage for excerpts/full text when permitted.
    """

    id: int
    news_item_id: int
    content_type: str  # 'excerpt' | 'full_text'
    content: str
    content_hash: str  # sha256 of content
    fetched_at: datetime
    content_status: str  # 'success' | 'failed' | 'pending'

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "NewsContentRow":
        """Create from database row tuple."""
        return cls(
            id=row[0],
            news_item_id=row[1],
            content_type=row[2],
            content=row[3],
            content_hash=row[4],
            fetched_at=row[5],
            content_status=row[6],
        )


@dataclass
class NewsScoreRow:
    """Row type for news_scores table.

    Scoring results from heuristics and/or LLM triage.
    """

    id: int
    news_item_id: int
    impact_score: int  # 0-100
    quality_score: int  # 0-100
    confidence_score: int  # 0-100
    topic: Optional[str]  # e.g., 'macro', 'earnings', 'geopolitics'
    flags: Optional[list[str]]  # JSONB array
    reasons: Optional[list[str]]  # JSONB array
    scored_at: datetime
    scorer_version: str

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "NewsScoreRow":
        """Create from database row tuple."""
        return cls(
            id=row[0],
            news_item_id=row[1],
            impact_score=row[2],
            quality_score=row[3],
            confidence_score=row[4],
            topic=row[5],
            flags=row[6],
            reasons=row[7],
            scored_at=row[8],
            scorer_version=row[9],
        )


@dataclass
class RunRow:
    """Row type for runs table.

    Run artifacts including facts bundle, timings, and monday_preview breakdown.
    """

    id: int
    stream_name: str
    run_mode: str  # 'us_close' | 'weekend_wrap' | 'monday_preview'
    started_at: datetime
    completed_at: Optional[datetime]
    status: str  # 'pending' | 'running' | 'completed' | 'failed'
    facts_bundle_json: Optional[dict[str, Any]]  # JSONB
    timings_json: Optional[dict[str, Any]]  # JSONB - timing breakdown
    # Monday preview risk breakdown (null for other modes)
    risk_score: Optional[int]
    calendar_score: Optional[int]
    market_score: Optional[int]
    headline_score: Optional[int]
    error_message: Optional[str]

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "RunRow":
        """Create from database row tuple."""
        return cls(
            id=row[0],
            stream_name=row[1],
            run_mode=row[2],
            started_at=row[3],
            completed_at=row[4],
            status=row[5],
            facts_bundle_json=row[6],
            timings_json=row[7],
            risk_score=row[8],
            calendar_score=row[9],
            market_score=row[10],
            headline_score=row[11],
            error_message=row[12],
        )


@dataclass
class MessageRow:
    """Row type for messages table.

    Generated messages with validation and publish status.
    """

    id: int
    run_id: int
    content: str
    validation_status: str  # 'pending' | 'valid' | 'invalid' | 'fallback'
    validation_errors: Optional[list[str]]  # JSONB array
    publish_status: str  # 'pending' | 'published' | 'failed' | 'skipped'
    telegram_message_id: Optional[int]
    published_at: Optional[datetime]
    created_at: datetime

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "MessageRow":
        """Create from database row tuple."""
        return cls(
            id=row[0],
            run_id=row[1],
            content=row[2],
            validation_status=row[3],
            validation_errors=row[4],
            publish_status=row[5],
            telegram_message_id=row[6],
            published_at=row[7],
            created_at=row[8],
        )
