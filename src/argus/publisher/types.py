"""Type definitions for the Telegram publisher module."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class PublishResult:
    """Result of a publish operation.

    Attributes:
        success: Whether the publish succeeded.
        telegram_message_id: Message ID returned by Telegram (None if failed or dry_run).
        published_at: Timestamp when message was published (None if failed or dry_run).
        error: Error message if publish failed.
        dry_run: Whether this was a dry run (no actual API call).
        payload: The exact payload sent (or would be sent in dry_run).
        retries: Number of retry attempts made.
        was_truncated: Whether the message was truncated to fit Telegram's limit.
        original_length: Original message length before truncation.
    """

    success: bool
    telegram_message_id: Optional[int]
    published_at: Optional[datetime]
    error: Optional[str]
    dry_run: bool
    payload: dict[str, Any]
    retries: int
    was_truncated: bool
    original_length: int


class PublishError(Exception):
    """Raised when publishing fails after all retries.

    Attributes:
        message: Error description.
        retries: Number of retries attempted before failure.
        last_status_code: HTTP status code from last attempt (if available).
        last_response: Response body from last attempt (if available).
    """

    def __init__(
        self,
        message: str,
        retries: int = 0,
        last_status_code: Optional[int] = None,
        last_response: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.retries = retries
        self.last_status_code = last_status_code
        self.last_response = last_response

    def __str__(self) -> str:
        base = super().__str__()
        if self.last_status_code:
            base += f" (HTTP {self.last_status_code})"
        return base
