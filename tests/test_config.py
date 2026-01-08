"""Tests for configuration loading."""

import tempfile
from pathlib import Path

import yaml

from argus.config import (
    ArgusConfig,
    TelegramConfig,
    UnknownStreamError,
)


class TestTelegramConfig:
    """Tests for TelegramConfig."""

    def test_bot_token_from_env(self, monkeypatch):
        """Test bot token retrieval from environment."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token_123")
        config = TelegramConfig()
        assert config.bot_token == "test_token_123"

    def test_chat_id_from_env(self, monkeypatch):
        """Test chat ID retrieval from environment."""
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123456789")
        config = TelegramConfig()
        assert config.chat_id == "-100123456789"

    def test_parse_mode_default(self):
        """Test parse mode has correct default."""
        config = TelegramConfig()
        assert config.parse_mode == "MarkdownV2"


class TestArgusConfigLoad:
    """Tests for ArgusConfig.load()."""

    def test_load_default_config(self):
        """Test loading with no config file returns defaults."""
        config = ArgusConfig.load(config_path=Path("/nonexistent/config.yaml"))
        assert config.stream.name == "us_close_basic"
        assert config.stream.enabled is True
        assert config.log_level == "INFO"

    def test_load_custom_config(self, monkeypatch):
        """Test loading with custom YAML config."""
        config_content = {
            "stream": {
                "name": "test_stream",
                "enabled": False,
                "telegram": {
                    "bot_token_env": "CUSTOM_BOT_TOKEN",
                },
                "schedule": {
                    "daily_us_close_sgt": "07:00",
                },
            },
            "log_level": "DEBUG",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_content, f)
            config_path = Path(f.name)

        try:
            config = ArgusConfig.load(config_path=config_path)
            assert config.stream.name == "test_stream"
            assert config.stream.enabled is False
            assert config.stream.telegram.bot_token_env == "CUSTOM_BOT_TOKEN"
            assert config.stream.schedule.daily_us_close_sgt == "07:00"
            assert config.log_level == "DEBUG"
        finally:
            config_path.unlink()

    def test_nested_config_parsing(self, monkeypatch):
        """Test that nested configurations are properly parsed."""
        config_content = {
            "stream": {
                "dedupe": {
                    "url_hash": False,
                    "simhash": {
                        "enabled": False,
                        "hamming_threshold": 3,
                    },
                },
                "enrichment": {
                    "max_enrich_per_run": 50,
                    "allow_full_text_storage": True,
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_content, f)
            config_path = Path(f.name)

        try:
            config = ArgusConfig.load(config_path=config_path)
            assert config.stream.dedupe.url_hash is False
            assert config.stream.dedupe.simhash.enabled is False
            assert config.stream.dedupe.simhash.hamming_threshold == 3
            assert config.stream.enrichment.max_enrich_per_run == 50
            assert config.stream.enrichment.allow_full_text_storage is True
        finally:
            config_path.unlink()


class TestMultiStreamConfig:
    def test_load_streams_map(self):
        config_content = {
            "streams": {
                "alpha": {"enabled": True},
                "beta": {"enabled": False},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_content, f)
            config_path = Path(f.name)

        try:
            config = ArgusConfig.load(config_path=config_path)
            assert set(config.streams.keys()) == {"alpha", "beta"}
            assert config.get_stream("alpha").name == "alpha"
            assert config.get_stream("beta").enabled is False
            assert config.list_streams() == ["alpha", "beta"]
            assert config.list_streams(enabled_only=True) == ["alpha"]
        finally:
            config_path.unlink()

    def test_load_stream_backward_compat_populates_streams(self):
        config_content = {"stream": {"name": "solo", "enabled": True}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_content, f)
            config_path = Path(f.name)

        try:
            config = ArgusConfig.load(config_path=config_path)
            assert config.stream.name == "solo"
            assert config.streams["solo"].name == "solo"
        finally:
            config_path.unlink()

    def test_get_stream_unknown_raises(self):
        config_content = {"streams": {"alpha": {"enabled": True}}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_content, f)
            config_path = Path(f.name)

        try:
            config = ArgusConfig.load(config_path=config_path)
            try:
                config.get_stream("missing")
                assert False, "expected UnknownStreamError"
            except UnknownStreamError:
                pass
        finally:
            config_path.unlink()


class TestGetRssFeeds:
    """Tests for get_rss_feeds()."""

    def test_get_rss_feeds_from_file(self, monkeypatch):
        """Test loading RSS feeds from allowlist file."""
        # Create a temporary RSS file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Comment line\n")
            f.write("https://example.com/feed1.xml\n")
            f.write("\n")
            f.write("https://example.com/feed2.xml\n")
            rss_path = Path(f.name)

        config_content = {
            "stream": {
                "rss": {
                    "allowlist_files": [str(rss_path)],
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_content, f)
            config_path = Path(f.name)

        try:
            config = ArgusConfig.load(config_path=config_path)
            feeds = config.get_rss_feeds()
            assert len(feeds) == 2
            assert "https://example.com/feed1.xml" in feeds
            assert "https://example.com/feed2.xml" in feeds
        finally:
            rss_path.unlink()
            config_path.unlink()

    def test_get_rss_feeds_empty(self, monkeypatch):
        """Test when no RSS files are configured."""
        config_content = {
            "stream": {
                "rss": {
                    "allowlist_files": [],
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_content, f)
            config_path = Path(f.name)

        try:
            config = ArgusConfig.load(config_path=config_path)
            feeds = config.get_rss_feeds()
            assert feeds == []
        finally:
            config_path.unlink()
