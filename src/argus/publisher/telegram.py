"""Telegram publisher for sending messages via Bot API.

Handles:
- Message publishing with MarkdownV2 parse mode
- Automatic truncation for messages exceeding Telegram's limit
- Retry with exponential backoff on transient errors
- Dry-run mode for testing without sending
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from argus.config import TelegramConfig
from argus.publisher.types import PublishError, PublishResult

logger = logging.getLogger(__name__)

# Telegram Bot API constants
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LENGTH = 4096
TRUNCATION_SUFFIX = "\n\n\\.\\.\\. _\\[message truncated\\]_"

# Retry configuration
DEFAULT_MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
RETRY_BACKOFF_MULTIPLIER = 2.0

# HTTP status codes that should trigger a retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class TelegramPublisher:
    """Publisher for sending messages to Telegram via Bot API.

    Supports:
    - MarkdownV2 parse mode (enforced)
    - Automatic message truncation with warning
    - Retry with exponential backoff on transient errors
    - Dry-run mode for testing
    - Disable link preview (default)
    - Silent notifications (optional)

    Example:
        >>> config = TelegramConfig()
        >>> publisher = TelegramPublisher(config)
        >>> result = publisher.publish("*Hello* world\\!")
        >>> print(result.telegram_message_id)
    """

    def __init__(
        self,
        config: TelegramConfig,
        http_client: Optional[httpx.Client] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Initialize the Telegram publisher.

        Args:
            config: Telegram configuration with bot token and chat ID.
            http_client: Optional httpx client (for testing/reuse).
            max_retries: Maximum retry attempts on transient errors.
            timeout_seconds: HTTP request timeout.
        """
        self.config = config
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self._client = http_client
        self._owns_client = False

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout_seconds)
            self._owns_client = True
        return self._client

    def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "TelegramPublisher":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _get_api_url(self) -> str:
        """Build the Telegram API URL with bot token."""
        token = self.config.bot_token
        if not token:
            raise PublishError(
                f"Telegram bot token not found in environment variable: {self.config.bot_token_env}"
            )
        return TELEGRAM_API_BASE.format(token=token)

    def _truncate_message(self, content: str) -> tuple[str, bool, int]:
        """Truncate message if it exceeds Telegram's limit.

        Args:
            content: Message content (already MarkdownV2 escaped).

        Returns:
            Tuple of (truncated_content, was_truncated, original_length).
        """
        original_length = len(content)

        if original_length <= MAX_MESSAGE_LENGTH:
            return content, False, original_length

        # Calculate available space for content
        suffix_length = len(TRUNCATION_SUFFIX)
        max_content_length = MAX_MESSAGE_LENGTH - suffix_length

        # Truncate at a safe point (avoid cutting in middle of escape sequence)
        truncated = content[:max_content_length]

        # Try to end at a newline for cleaner output
        last_newline = truncated.rfind("\n")
        if last_newline > max_content_length - 200:  # Within last 200 chars
            truncated = truncated[:last_newline]

        # Ensure we don't end with a dangling escape backslash
        while truncated.endswith("\\"):
            truncated = truncated[:-1]

        truncated += TRUNCATION_SUFFIX

        logger.warning(f"Message truncated from {original_length} to {len(truncated)} characters")

        return truncated, True, original_length

    def _build_payload(
        self,
        content: str,
        chat_id: str,
        silent: bool,
    ) -> tuple[dict[str, Any], bool, int]:
        """Build the API request payload.

        Args:
            content: Message content (MarkdownV2 escaped).
            chat_id: Target chat ID.
            silent: Whether to send without notification.

        Returns:
            Tuple of (payload_dict, was_truncated, original_length).
        """
        truncated_content, was_truncated, original_length = self._truncate_message(content)

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": truncated_content,
            "parse_mode": self.config.parse_mode,
            "disable_web_page_preview": True,
        }

        if silent:
            payload["disable_notification"] = True

        return payload, was_truncated, original_length

    def _send_with_retry(self, payload: dict[str, Any]) -> tuple[int, int]:
        """Send message with retry on transient errors.

        Args:
            payload: Request payload.

        Returns:
            Tuple of (telegram_message_id, retry_count).

        Raises:
            PublishError: If all retries fail.
        """
        client = self._get_client()
        url = self._get_api_url()

        last_error: Optional[Exception] = None
        last_status_code: Optional[int] = None
        last_response: Optional[str] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(url, json=payload)
                last_status_code = response.status_code

                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        message_id = data["result"]["message_id"]
                        return message_id, attempt
                    else:
                        # API returned ok=false
                        error_desc = data.get("description", "Unknown error")
                        raise PublishError(
                            f"Telegram API error: {error_desc}",
                            retries=attempt,
                            last_status_code=last_status_code,
                            last_response=response.text,
                        )

                # Check if we should retry
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_response = response.text
                    if attempt < self.max_retries:
                        delay = RETRY_BASE_DELAY * (RETRY_BACKOFF_MULTIPLIER**attempt)
                        logger.warning(
                            f"Telegram API returned {response.status_code}, "
                            f"retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})"
                        )
                        time.sleep(delay)
                        continue

                # Non-retryable error
                raise PublishError(
                    f"Telegram API error: HTTP {response.status_code}",
                    retries=attempt,
                    last_status_code=last_status_code,
                    last_response=response.text,
                )

            except httpx.RequestError as e:
                # Network error - retry
                last_error = e
                if attempt < self.max_retries:
                    delay = RETRY_BASE_DELAY * (RETRY_BACKOFF_MULTIPLIER**attempt)
                    logger.warning(
                        f"Network error: {e}, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue

                raise PublishError(
                    f"Network error after {attempt + 1} attempts: {e}",
                    retries=attempt,
                    last_status_code=last_status_code,
                    last_response=last_response,
                ) from e

        # Should not reach here, but just in case
        raise PublishError(
            f"Failed after {self.max_retries + 1} attempts: {last_error}",
            retries=self.max_retries,
            last_status_code=last_status_code,
            last_response=last_response,
        )

    def publish(
        self,
        content: str,
        chat_id: Optional[str] = None,
        silent: bool = False,
    ) -> PublishResult:
        """Publish a message to Telegram.

        Args:
            content: Message content (must be MarkdownV2 escaped).
            chat_id: Target chat ID (defaults to config.chat_id).
            silent: Send without notification sound.

        Returns:
            PublishResult with success status and message ID.

        Raises:
            PublishError: If publishing fails after all retries.
        """
        target_chat_id = chat_id or self.config.chat_id
        if not target_chat_id:
            raise PublishError(
                f"Chat ID not found in environment variable: {self.config.chat_id_env}"
            )

        payload, was_truncated, original_length = self._build_payload(
            content, target_chat_id, silent
        )

        try:
            telegram_message_id, retries = self._send_with_retry(payload)
            published_at = datetime.now(timezone.utc)

            logger.info(
                f"Published message {telegram_message_id} to chat {target_chat_id}"
                + (f" (truncated from {original_length} chars)" if was_truncated else "")
            )

            return PublishResult(
                success=True,
                telegram_message_id=telegram_message_id,
                published_at=published_at,
                error=None,
                dry_run=False,
                payload=payload,
                retries=retries,
                was_truncated=was_truncated,
                original_length=original_length,
            )

        except PublishError as e:
            logger.error(f"Failed to publish message: {e}")
            return PublishResult(
                success=False,
                telegram_message_id=None,
                published_at=None,
                error=str(e),
                dry_run=False,
                payload=payload,
                retries=e.retries,
                was_truncated=was_truncated,
                original_length=original_length,
            )

    def publish_dry_run(
        self,
        content: str,
        chat_id: Optional[str] = None,
        silent: bool = False,
    ) -> PublishResult:
        """Simulate publishing without making an API call.

        Args:
            content: Message content (must be MarkdownV2 escaped).
            chat_id: Target chat ID (defaults to config.chat_id).
            silent: Would send without notification sound.

        Returns:
            PublishResult with dry_run=True and the payload that would be sent.
        """
        target_chat_id = chat_id or self.config.chat_id
        if not target_chat_id:
            # Use a placeholder for dry run if no chat ID configured
            target_chat_id = "<TELEGRAM_CHAT_ID>"

        payload, was_truncated, original_length = self._build_payload(
            content, target_chat_id, silent
        )

        logger.info(
            f"Dry run: would publish {len(payload['text'])} chars to {target_chat_id}"
            + (f" (truncated from {original_length} chars)" if was_truncated else "")
        )

        return PublishResult(
            success=True,
            telegram_message_id=None,
            published_at=None,
            error=None,
            dry_run=True,
            payload=payload,
            retries=0,
            was_truncated=was_truncated,
            original_length=original_length,
        )


# =============================================================================
# Orchestrator/CLI Integration Helper
# =============================================================================


def run_publish(
    conn: Any,  # psycopg2 connection
    message_id: int,
    config: TelegramConfig,
    dry_run: bool = False,
    silent: bool = False,
) -> PublishResult:
    """Publish a message from the database and update its status.

    This is the main integration point for the CLI and orchestrator.
    It fetches the message from DB, publishes via Telegram, and updates
    the message record with the result.

    Args:
        conn: Database connection.
        message_id: ID of the message to publish.
        config: Telegram configuration.
        dry_run: If True, simulate publishing without API call.
        silent: If True, send without notification sound.

    Returns:
        PublishResult with success status and details.

    Raises:
        ValueError: If message not found or not in publishable state.
    """
    from argus.db.repository import get_message_by_id, update_message

    # Fetch message from database
    message = get_message_by_id(conn, message_id)
    if message is None:
        raise ValueError(f"Message not found: {message_id}")

    # Check message is in publishable state
    if message.validation_status not in ("valid", "fallback"):
        raise ValueError(
            f"Message {message_id} is not validated (status: {message.validation_status})"
        )

    if message.publish_status == "published":
        raise ValueError(
            f"Message {message_id} is already published "
            f"(telegram_message_id: {message.telegram_message_id})"
        )

    # Publish via Telegram
    with TelegramPublisher(config) as publisher:
        if dry_run:
            result = publisher.publish_dry_run(message.content, silent=silent)
        else:
            result = publisher.publish(message.content, silent=silent)

    # Update database (skip for dry run)
    if not dry_run:
        if result.success:
            update_message(
                conn,
                message_id=message_id,
                publish_status="published",
                telegram_message_id=result.telegram_message_id,
                published_at=result.published_at,
            )
            logger.info(f"Message {message_id} published successfully")
        else:
            update_message(
                conn,
                message_id=message_id,
                publish_status="failed",
            )
            logger.error(f"Message {message_id} failed to publish: {result.error}")

    return result


def publish_content(
    content: str,
    config: TelegramConfig,
    dry_run: bool = False,
    silent: bool = False,
) -> PublishResult:
    """Publish arbitrary content to Telegram (no database interaction).

    This is a convenience function for testing and ad-hoc publishing.

    Args:
        content: Message content (must be MarkdownV2 escaped).
        config: Telegram configuration.
        dry_run: If True, simulate publishing without API call.
        silent: If True, send without notification sound.

    Returns:
        PublishResult with success status and details.
    """
    with TelegramPublisher(config) as publisher:
        if dry_run:
            return publisher.publish_dry_run(content, silent=silent)
        else:
            return publisher.publish(content, silent=silent)
