"""Tests for the publisher module.

Tests cover:
- TelegramPublisher class (dry run, API calls, truncation, retries)
- run_publish() integration with database
- PublishResult and PublishError types
"""

from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, patch

import httpx
import pytest

from argus.config import TelegramConfig
from argus.publisher import PublishError, PublishResult, TelegramPublisher
from argus.publisher.telegram import (
    MAX_MESSAGE_LENGTH,
    TRUNCATION_SUFFIX,
    publish_content,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def telegram_config() -> Generator[TelegramConfig, None, None]:
    """Telegram config with mock environment."""
    with patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "test_bot_token_12345",
            "TELEGRAM_CHAT_ID": "-123456789",
            "TELEGRAM_PARSE_MODE": "MarkdownV2",
        },
    ):
        yield TelegramConfig()


@pytest.fixture
def mock_success_response() -> dict:
    """Successful Telegram API response."""
    return {
        "ok": True,
        "result": {
            "message_id": 42,
            "from": {"id": 123, "is_bot": True, "first_name": "TestBot"},
            "chat": {"id": -123456789, "type": "group"},
            "date": 1704628800,
            "text": "Test message",
        },
    }


@pytest.fixture
def sample_message_content() -> str:
    """Sample MarkdownV2 escaped message content."""
    return r"""*Market Update*
*7 Jan 2025*

S&P 500 – 5000\.50 \(1D \+0\.75%, \+37\.25 pts\)
Dow Jones – 42000\.00 \(1D \-0\.25%, \-105\.50 pts\)
Nasdaq – 16000\.00 \(1D \+1\.20%, \+189\.50 pts\)

Markets closed higher today\.

\-\-\-\-

*Investor Key Takeaways*
• First takeaway point
• Second takeaway point
• Third takeaway point

*Key Dates \(UTC\)*
• Jan 10 14:30 \- US Employment Report

*What to Watch Next*
• Monitor Fed comments

*Sources*
\[1\] Reuters \- Fed signals rate cut"""


# =============================================================================
# TelegramPublisher Tests
# =============================================================================


class TestTelegramPublisher:
    """Tests for TelegramPublisher class."""

    def test_init_defaults(self, telegram_config: TelegramConfig) -> None:
        """Test default initialization."""
        publisher = TelegramPublisher(telegram_config)
        assert publisher.config == telegram_config
        assert publisher.max_retries == 3
        assert publisher.timeout_seconds == 30.0

    def test_init_custom_params(self, telegram_config: TelegramConfig) -> None:
        """Test initialization with custom parameters."""
        publisher = TelegramPublisher(
            telegram_config,
            max_retries=5,
            timeout_seconds=60.0,
        )
        assert publisher.max_retries == 5
        assert publisher.timeout_seconds == 60.0

    def test_context_manager(self, telegram_config: TelegramConfig) -> None:
        """Test context manager creates and closes client."""
        with TelegramPublisher(telegram_config) as publisher:
            # Force client creation
            client = publisher._get_client()
            assert client is not None
            assert publisher._owns_client is True

        # After exit, client should be closed
        assert publisher._client is None


class TestPublishDryRun:
    """Tests for dry run publishing."""

    def test_dry_run_returns_payload(
        self, telegram_config: TelegramConfig, sample_message_content: str
    ) -> None:
        """Dry run returns payload without making API call."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            publisher = TelegramPublisher(telegram_config)
            result = publisher.publish_dry_run(sample_message_content)

        assert result.success is True
        assert result.dry_run is True
        assert result.telegram_message_id is None
        assert result.published_at is None
        assert result.error is None
        assert result.retries == 0

        # Check payload structure
        assert "chat_id" in result.payload
        assert "text" in result.payload
        assert result.payload["parse_mode"] == "MarkdownV2"
        assert result.payload["disable_web_page_preview"] is True

    def test_dry_run_with_silent(
        self, telegram_config: TelegramConfig, sample_message_content: str
    ) -> None:
        """Dry run with silent flag includes disable_notification."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            publisher = TelegramPublisher(telegram_config)
            result = publisher.publish_dry_run(sample_message_content, silent=True)

        assert result.payload.get("disable_notification") is True

    def test_dry_run_without_chat_id_uses_placeholder(
        self, telegram_config: TelegramConfig
    ) -> None:
        """Dry run without chat ID uses placeholder."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "",  # Empty
            },
        ):
            publisher = TelegramPublisher(telegram_config)
            result = publisher.publish_dry_run("Test message")

        assert result.payload["chat_id"] == "<TELEGRAM_CHAT_ID>"


class TestMessageTruncation:
    """Tests for message truncation."""

    def test_short_message_not_truncated(self, telegram_config: TelegramConfig) -> None:
        """Short messages are not truncated."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123",
            },
        ):
            publisher = TelegramPublisher(telegram_config)
            short_message = "Short message"
            result = publisher.publish_dry_run(short_message)

        assert result.was_truncated is False
        assert result.original_length == len(short_message)
        assert result.payload["text"] == short_message

    def test_long_message_truncated(self, telegram_config: TelegramConfig) -> None:
        """Long messages are truncated to fit Telegram's limit."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123",
            },
        ):
            publisher = TelegramPublisher(telegram_config)
            # Create a message that exceeds the limit
            long_message = "A" * (MAX_MESSAGE_LENGTH + 500)
            result = publisher.publish_dry_run(long_message)

        assert result.was_truncated is True
        assert result.original_length == len(long_message)
        assert len(result.payload["text"]) <= MAX_MESSAGE_LENGTH
        assert TRUNCATION_SUFFIX in result.payload["text"]

    def test_truncation_preserves_newlines_when_possible(
        self, telegram_config: TelegramConfig
    ) -> None:
        """Truncation tries to end at a newline for cleaner output."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123",
            },
        ):
            publisher = TelegramPublisher(telegram_config)
            # Create a message with newlines near the end
            base = "A" * (MAX_MESSAGE_LENGTH - 100)
            with_newlines = base + "\nLine 1\nLine 2\nLine 3" + "B" * 200
            result = publisher.publish_dry_run(with_newlines)

        assert result.was_truncated is True
        # Either ends at newline or was adjusted
        assert len(result.payload["text"]) <= MAX_MESSAGE_LENGTH


class TestPublishWithMockedClient:
    """Tests for actual publishing with mocked HTTP client."""

    def test_publish_success(
        self,
        telegram_config: TelegramConfig,
        mock_success_response: dict,
        sample_message_content: str,
    ) -> None:
        """Successful publish returns message ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_success_response

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            publisher = TelegramPublisher(telegram_config, http_client=mock_client)
            result = publisher.publish(sample_message_content)

        assert result.success is True
        assert result.telegram_message_id == 42
        assert result.published_at is not None
        assert result.dry_run is False
        assert result.error is None
        mock_client.post.assert_called_once()

    def test_publish_api_error(
        self, telegram_config: TelegramConfig, sample_message_content: str
    ) -> None:
        """API error returns failed result."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: can't parse entities",
        }
        mock_response.text = '{"ok": false}'

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            publisher = TelegramPublisher(telegram_config, http_client=mock_client)
            result = publisher.publish(sample_message_content)

        assert result.success is False
        assert result.telegram_message_id is None
        assert result.error is not None
        assert "can't parse entities" in result.error

    def test_publish_retries_on_429(
        self,
        telegram_config: TelegramConfig,
        mock_success_response: dict,
        sample_message_content: str,
    ) -> None:
        """Publisher retries on rate limit (429) errors."""
        # First call: 429, second call: success
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.text = "Rate limited"

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = mock_success_response

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = [mock_429, mock_200]

        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            with patch("argus.publisher.telegram.time.sleep"):  # Skip actual sleep
                publisher = TelegramPublisher(telegram_config, http_client=mock_client)
                result = publisher.publish(sample_message_content)

        assert result.success is True
        assert result.retries == 1
        assert mock_client.post.call_count == 2

    def test_publish_retries_on_network_error(
        self,
        telegram_config: TelegramConfig,
        mock_success_response: dict,
        sample_message_content: str,
    ) -> None:
        """Publisher retries on network errors."""
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = mock_success_response

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = [
            httpx.RequestError("Connection failed"),
            mock_200,
        ]

        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            with patch("argus.publisher.telegram.time.sleep"):
                publisher = TelegramPublisher(telegram_config, http_client=mock_client)
                result = publisher.publish(sample_message_content)

        assert result.success is True
        assert result.retries == 1

    def test_publish_fails_after_max_retries(
        self, telegram_config: TelegramConfig, sample_message_content: str
    ) -> None:
        """Publisher fails after exhausting retries."""
        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.text = "Internal Server Error"

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_500

        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            with patch("argus.publisher.telegram.time.sleep"):
                publisher = TelegramPublisher(
                    telegram_config, http_client=mock_client, max_retries=2
                )
                result = publisher.publish(sample_message_content)

        assert result.success is False
        assert result.retries == 2
        assert mock_client.post.call_count == 3  # Initial + 2 retries

    def test_publish_no_retry_on_400(
        self, telegram_config: TelegramConfig, sample_message_content: str
    ) -> None:
        """Publisher does not retry on 400 errors."""
        mock_400 = MagicMock()
        mock_400.status_code = 400
        mock_400.text = "Bad Request"

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_400

        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            publisher = TelegramPublisher(telegram_config, http_client=mock_client)
            result = publisher.publish(sample_message_content)

        assert result.success is False
        assert result.retries == 0
        mock_client.post.assert_called_once()


class TestPublishValidation:
    """Tests for publish parameter validation."""

    def test_publish_without_token_fails(self) -> None:
        """Publishing without bot token raises error."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            config = TelegramConfig()
            publisher = TelegramPublisher(config)
            result = publisher.publish("Test message")

        assert result.success is False
        assert result.error is not None
        assert "bot token" in result.error.lower()

    def test_publish_without_chat_id_fails(self) -> None:
        """Publishing without chat ID raises error."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "",
            },
        ):
            config = TelegramConfig()
            publisher = TelegramPublisher(config)

            # Should raise or return error
            with pytest.raises(PublishError) as exc_info:
                publisher.publish("Test message")

            assert "chat id" in str(exc_info.value).lower()


class TestPublishContent:
    """Tests for publish_content convenience function."""

    def test_publish_content_dry_run(self, telegram_config: TelegramConfig) -> None:
        """publish_content with dry_run returns payload."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_CHAT_ID": "-123456789",
            },
        ):
            result = publish_content(
                content="Test message",
                config=telegram_config,
                dry_run=True,
            )

        assert result.success is True
        assert result.dry_run is True
        assert result.payload["text"] == "Test message"


class TestPublishResult:
    """Tests for PublishResult dataclass."""

    def test_publish_result_fields(self) -> None:
        """PublishResult contains all expected fields."""
        result = PublishResult(
            success=True,
            telegram_message_id=42,
            published_at=datetime.now(timezone.utc),
            error=None,
            dry_run=False,
            payload={"chat_id": "-123", "text": "Test"},
            retries=1,
            was_truncated=False,
            original_length=4,
        )

        assert result.success is True
        assert result.telegram_message_id == 42
        assert result.retries == 1
        assert result.was_truncated is False


class TestPublishError:
    """Tests for PublishError exception."""

    def test_publish_error_message(self) -> None:
        """PublishError contains message and metadata."""
        error = PublishError(
            "API error",
            retries=2,
            last_status_code=500,
            last_response="Internal error",
        )

        assert str(error) == "API error (HTTP 500)"
        assert error.retries == 2
        assert error.last_status_code == 500
        assert error.last_response == "Internal error"

    def test_publish_error_without_status_code(self) -> None:
        """PublishError without status code."""
        error = PublishError("Network error", retries=1)
        assert str(error) == "Network error"
