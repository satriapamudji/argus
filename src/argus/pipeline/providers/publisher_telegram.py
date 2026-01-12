from __future__ import annotations

import logging

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.db.repository import get_message_by_id, update_message
from argus.db.telegram_repository import list_broadcast_chat_ids  # type: ignore[attr-defined]
from argus.publisher.telegram import TelegramPublisher, run_publish
from argus.publisher.types import PublishResult

logger = logging.getLogger(__name__)


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
        """Publish a message to Telegram.

        If there are enabled per-stream subscriptions (Task 19), we broadcast to all
        authorized subscribed chats (Task 20). If no subscriptions exist for the
        stream, we fall back to legacy single-destination publishing via
        TELEGRAM_CHAT_ID.
        """

        # Fetch message from database
        message = get_message_by_id(conn, message_id)
        if message is None:
            raise ValueError(f"Message not found: {message_id}")

        # If there are no subscribers, keep legacy behavior intact.
        recipients = list_broadcast_chat_ids(conn, stream_name=config.stream.name)
        if not recipients:
            return run_publish(
                conn=conn,
                message_id=message_id,
                config=config.stream.telegram,
                dry_run=dry_run,
                silent=silent,
            )

        # Broadcast: best-effort per recipient.
        successes: list[PublishResult] = []
        failures: list[tuple[int, str]] = []

        with TelegramPublisher(config.stream.telegram) as publisher:
            for chat_id in recipients:
                try:
                    if dry_run:
                        result = publisher.publish_dry_run(
                            message.content, chat_id=str(chat_id), silent=silent
                        )
                    else:
                        result = publisher.publish(
                            message.content, chat_id=str(chat_id), silent=silent
                        )

                    if result.success:
                        successes.append(result)
                    else:
                        failures.append((chat_id, result.error or "publish failed"))

                except Exception as e:  # best-effort send loop
                    failures.append((chat_id, str(e)))

        for chat_id, err in failures:
            logger.error(f"Telegram broadcast failed for chat_id={chat_id}: {err}")

        # For backward compatibility: publish_status is updated on any success.
        # telegram_message_id remains a single column, so we store the first
        # successfully published telegram_message_id.
        if not dry_run:
            if successes:
                first = successes[0]
                update_message(
                    conn,
                    message_id=message_id,
                    publish_status="published",
                    telegram_message_id=first.telegram_message_id,
                    published_at=first.published_at,
                )
            else:
                update_message(
                    conn,
                    message_id=message_id,
                    publish_status="failed",
                )

        # Return representative result (first success if any, else synthesize failure)
        if successes:
            return successes[0]

        return PublishResult(
            success=False,
            telegram_message_id=None,
            published_at=None,
            error=f"Telegram broadcast failed for all recipients (count={len(recipients)})",
            dry_run=dry_run,
            payload={},
            retries=0,
            was_truncated=False,
            original_length=len(message.content),
        )
