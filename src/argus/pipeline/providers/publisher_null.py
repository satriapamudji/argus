from __future__ import annotations

from datetime import datetime, timezone

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.db.repository import update_message
from argus.publisher.types import PublishResult


class NullPublisherProvider:
    """Successful no-op publisher.

    This provider intentionally does not call Telegram. It marks the message as
    publish_status="skipped" which is treated as a terminal success state.
    """

    def publish(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        message_id: int,
        dry_run: bool,
        silent: bool,
    ) -> PublishResult:
        _ = config
        _ = silent

        if not dry_run:
            update_message(
                conn=conn,
                message_id=message_id,
                publish_status="skipped",
            )

        return PublishResult(
            success=True,
            telegram_message_id=None,
            published_at=datetime.now(timezone.utc) if dry_run else None,
            error=None,
            dry_run=dry_run,
            payload={"event": "publish", "provider": "null", "message_id": message_id},
            retries=0,
            was_truncated=False,
            original_length=0,
        )
