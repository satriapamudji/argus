"""Telegram publisher module.

Provides functionality to publish messages to Telegram via Bot API.

Usage:
    from argus.publisher import TelegramPublisher, run_publish

    # Direct publishing
    publisher = TelegramPublisher(config)
    result = publisher.publish(message_content)

    # With database integration
    result = run_publish(conn, message_id, config)
"""

from argus.publisher.telegram import (
    TelegramPublisher,
    publish_content,
    run_publish,
)
from argus.publisher.types import PublishError, PublishResult

__all__ = [
    "TelegramPublisher",
    "PublishResult",
    "PublishError",
    "run_publish",
    "publish_content",
]
