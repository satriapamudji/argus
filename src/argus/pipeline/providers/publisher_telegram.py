from __future__ import annotations

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.publisher.types import PublishResult


class TelegramPublisherProvider:
    def publish(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        message_id: int,
        dry_run: bool,
        silent: bool,
    ) -> PublishResult:
        from argus.publisher.telegram import run_publish

        return run_publish(
            conn=conn,
            message_id=message_id,
            config=config.stream.telegram,
            dry_run=dry_run,
            silent=silent,
        )
