"""Database module for Argus."""

from argus.db.connection import get_connection, get_connection_context, get_database_url
from argus.db.models import (
    MessageRow,
    NewsContentRow,
    NewsFingerprintRow,
    NewsItemRow,
    NewsScoreRow,
    RunRow,
)
from argus.db.partitions import (
    create_partition_for_date,
    create_partitions_for_range,
    drop_old_partitions,
    ensure_partition_exists,
    get_existing_partitions,
    run_retention_cleanup,
)
from argus.db.repository import (
    check_duplicate_by_text,
    check_duplicate_by_url,
    create_message,
    create_run,
    get_or_create_fingerprint,
    hash_text,
    hash_url,
    insert_news_item,
    normalize_url,
    update_message,
    update_run,
)

__all__ = [
    # Connection
    "get_connection",
    "get_connection_context",
    "get_database_url",
    # Models
    "MessageRow",
    "NewsContentRow",
    "NewsFingerprintRow",
    "NewsItemRow",
    "NewsScoreRow",
    "RunRow",
    # Partitions
    "create_partition_for_date",
    "create_partitions_for_range",
    "drop_old_partitions",
    "ensure_partition_exists",
    "get_existing_partitions",
    "run_retention_cleanup",
    # Repository
    "check_duplicate_by_text",
    "check_duplicate_by_url",
    "create_message",
    "create_run",
    "get_or_create_fingerprint",
    "hash_text",
    "hash_url",
    "insert_news_item",
    "normalize_url",
    "update_message",
    "update_run",
]
