"""Tests for database models."""

from datetime import datetime, timezone

from argus.db.models import (
    MessageRow,
    NewsContentRow,
    NewsFingerprintRow,
    NewsItemRow,
    NewsScoreRow,
    RunRow,
)


class TestNewsFingerprintRow:
    """Tests for NewsFingerprintRow."""

    def test_from_row(self) -> None:
        """Test creating NewsFingerprintRow from tuple."""
        now = datetime.now(timezone.utc)
        row = (
            1,
            "abc123def456",
            "text_hash_value",
            1234567890,
            "reuters",
            now,
            now,
        )
        fingerprint = NewsFingerprintRow.from_row(row)

        assert fingerprint.id == 1
        assert fingerprint.hash_url == "abc123def456"
        assert fingerprint.hash_text == "text_hash_value"
        assert fingerprint.simhash == 1234567890
        assert fingerprint.source_name == "reuters"
        assert fingerprint.first_seen_at == now
        assert fingerprint.last_seen_at == now


class TestNewsItemRow:
    """Tests for NewsItemRow."""

    def test_from_row(self) -> None:
        """Test creating NewsItemRow from tuple."""
        now = datetime.now(timezone.utc)
        row = (
            1,
            10,
            "reuters",
            "https://reuters.com/article",
            "Test Article Title",
            "This is a snippet",
            "John Doe",
            now,
            now,
            {"key": "value"},
        )
        news_item = NewsItemRow.from_row(row)

        assert news_item.id == 1
        assert news_item.fingerprint_id == 10
        assert news_item.source_name == "reuters"
        assert news_item.source_url == "https://reuters.com/article"
        assert news_item.title == "Test Article Title"
        assert news_item.snippet == "This is a snippet"
        assert news_item.author == "John Doe"
        assert news_item.published_at == now
        assert news_item.ingested_at == now
        assert news_item.raw_metadata == {"key": "value"}


class TestNewsContentRow:
    """Tests for NewsContentRow."""

    def test_from_row(self) -> None:
        """Test creating NewsContentRow from tuple."""
        now = datetime.now(timezone.utc)
        row = (
            1,
            100,
            "excerpt",
            "This is the content",
            "contenthash123",
            now,
            "success",
        )
        content = NewsContentRow.from_row(row)

        assert content.id == 1
        assert content.news_item_id == 100
        assert content.content_type == "excerpt"
        assert content.content == "This is the content"
        assert content.content_hash == "contenthash123"
        assert content.fetched_at == now
        assert content.content_status == "success"


class TestNewsScoreRow:
    """Tests for NewsScoreRow."""

    def test_from_row(self) -> None:
        """Test creating NewsScoreRow from tuple."""
        now = datetime.now(timezone.utc)
        row = (
            1,
            100,
            85,
            90,
            95,
            "macro",
            ["breaking", "important"],
            ["High impact event", "Market moving"],
            now,
            "v1",
        )
        score = NewsScoreRow.from_row(row)

        assert score.id == 1
        assert score.news_item_id == 100
        assert score.impact_score == 85
        assert score.quality_score == 90
        assert score.confidence_score == 95
        assert score.topic == "macro"
        assert score.flags == ["breaking", "important"]
        assert score.reasons == ["High impact event", "Market moving"]
        assert score.scored_at == now
        assert score.scorer_version == "v1"


class TestRunRow:
    """Tests for RunRow."""

    def test_from_row(self) -> None:
        """Test creating RunRow from tuple."""
        now = datetime.now(timezone.utc)
        row = (
            1,
            "us_close_basic",
            "us_close",
            now,
            now,
            "completed",
            {"facts": "bundle"},
            {"step1": 100},
            75,
            40,
            20,
            15,
            None,
        )
        run = RunRow.from_row(row)

        assert run.id == 1
        assert run.stream_name == "us_close_basic"
        assert run.run_mode == "us_close"
        assert run.started_at == now
        assert run.completed_at == now
        assert run.status == "completed"
        assert run.facts_bundle_json == {"facts": "bundle"}
        assert run.timings_json == {"step1": 100}
        assert run.risk_score == 75
        assert run.calendar_score == 40
        assert run.market_score == 20
        assert run.headline_score == 15
        assert run.error_message is None


class TestMessageRow:
    """Tests for MessageRow."""

    def test_from_row(self) -> None:
        """Test creating MessageRow from tuple."""
        now = datetime.now(timezone.utc)
        row = (
            1,
            10,
            "This is the message content",
            "valid",
            None,
            "published",
            123456789,
            now,
            now,
        )
        message = MessageRow.from_row(row)

        assert message.id == 1
        assert message.run_id == 10
        assert message.content == "This is the message content"
        assert message.validation_status == "valid"
        assert message.validation_errors is None
        assert message.publish_status == "published"
        assert message.telegram_message_id == 123456789
        assert message.published_at == now
        assert message.created_at == now
