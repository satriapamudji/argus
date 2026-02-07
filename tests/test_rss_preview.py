"""Tests for argus rss preview CLI command."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from argus.cli import cli


def get_pythonpath() -> str:
    """Get PYTHONPATH with src directory included."""
    return str(Path(__file__).parent.parent / "src")


class TestRSSPreviewHelp:
    """Test --help for rss preview command."""

    def test_rss_group_help(self):
        """Test that argus rss --help works."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "rss", "--help"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "preview" in result.stdout

    def test_preview_help(self):
        """Test that argus rss preview --help works."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "rss", "preview", "--help"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "--url" in result.stdout
        assert "--allowlist" in result.stdout
        assert "--stream" in result.stdout
        assert "--limit" in result.stdout
        assert "--json" in result.stdout


class TestRSSPreviewNoInputs:
    """Test error handling when no inputs provided."""

    def test_no_inputs_exits_2(self):
        """Test that no inputs exits with code 2."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "rss", "preview"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 2
        assert "No feed URLs provided" in (result.stdout + result.stderr)


class TestRSSPreviewURLSuccess:
    """Test --url success path with mocked feedparser."""

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_single_url_success(self, mock_parse: MagicMock):
        """Test parsing a single URL with mocked feedparser."""
        # Mock feedparser response
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {
                    "title": "Article 1",
                    "link": "https://example.com/1",
                    "summary": "Summary of article 1",
                    "author": "John Doe",
                    "published_parsed": time.struct_time((2024, 1, 15, 12, 30, 0, 0, 0, 0)),
                },
                {
                    "title": "Article 2",
                    "link": "https://example.com/2",
                    "summary": "Summary of article 2",
                    "published_parsed": time.struct_time((2024, 1, 14, 10, 0, 0, 0, 0, 0)),
                },
            ],
        }

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["rss", "preview", "--url", "https://example.com/feed.xml", "--limit", "2"],
        )

        assert result.exit_code == 0
        assert "FEED https://example.com/feed.xml" in result.output
        assert "OK entries=2 showing=2" in result.output
        assert "Article 1" in result.output
        assert "Article 2" in result.output
        assert "Summary: feeds_total=1 feeds_ok=1 feeds_failed=0" in result.output


class TestRSSPreviewJSONOutput:
    """Test --json output schema validation."""

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_json_output_schema(self, mock_parse: MagicMock):
        """Test JSON output matches expected schema."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {
                    "title": "Article 1",
                    "link": "https://example.com/1",
                    "summary": "Summary text",
                    "published_parsed": time.struct_time((2024, 1, 15, 12, 30, 0, 0, 0, 0)),
                }
            ],
        }

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "rss",
                "preview",
                "--url",
                "https://example.com/feed.xml",
                "--json",
                "--limit",
                "1",
            ],
        )

        assert result.exit_code == 0

        # Parse JSON output
        output = json.loads(result.output)

        # Validate top-level schema
        assert "feeds_total" in output
        assert "feeds_ok" in output
        assert "feeds_failed" in output
        assert "limit" in output
        assert "feeds" in output

        # Validate counts
        assert output["feeds_total"] == 1
        assert output["feeds_ok"] == 1
        assert output["feeds_failed"] == 0
        assert output["limit"] == 1

        # Validate feeds array
        assert len(output["feeds"]) == 1
        feed = output["feeds"][0]

        # Validate per-feed schema
        assert "feed_url" in feed
        assert "ok" in feed
        assert "error" in feed
        assert "entries_total" in feed
        assert "entries" in feed

        assert feed["feed_url"] == "https://example.com/feed.xml"
        assert feed["ok"] is True
        assert feed["error"] is None
        assert feed["entries_total"] == 1
        assert len(feed["entries"]) == 1

        # Validate per-entry schema
        entry = feed["entries"][0]
        assert "source_name" in entry
        assert "published_at" in entry
        assert "title" in entry
        assert "source_url" in entry
        assert "snippet" in entry

        assert entry["title"] == "Article 1"
        assert entry["source_url"] == "https://example.com/1"
        assert entry["snippet"] == "Summary text"
        assert entry["published_at"] == "2024-01-15T12:30:00+00:00"


class TestRSSPreviewAllowlist:
    """Test --allowlist input with comments and blank lines."""

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_allowlist_with_comments_and_blanks(self, mock_parse: MagicMock, tmp_path: Path):
        """Test allowlist parsing ignores comments and blank lines."""
        # Create allowlist file with comments and blanks
        allowlist_file = tmp_path / "feeds.txt"
        allowlist_file.write_text(
            """
# This is a comment
https://example.com/feed1.xml

# Another comment
https://example.com/feed2.xml

https://example.com/feed3.xml
""".lstrip(),
            encoding="utf-8",
        )

        # Mock feedparser to return different data for each URL
        def mock_parse_side_effect(url: str, **kwargs: Any) -> dict[str, Any]:
            if "feed1" in url:
                return {
                    "status": 200,
                    "feed": {"title": "Feed 1"},
                    "entries": [
                        {
                            "title": "Article from Feed 1",
                            "link": "https://example.com/1",
                            "summary": "Summary 1",
                            "published_parsed": time.struct_time((2024, 1, 15, 12, 0, 0, 0, 0, 0)),
                        }
                    ],
                }
            elif "feed2" in url:
                return {
                    "status": 200,
                    "feed": {"title": "Feed 2"},
                    "entries": [
                        {
                            "title": "Article from Feed 2",
                            "link": "https://example.com/2",
                            "summary": "Summary 2",
                            "published_parsed": time.struct_time((2024, 1, 14, 12, 0, 0, 0, 0, 0)),
                        }
                    ],
                }
            else:  # feed3
                return {
                    "status": 200,
                    "feed": {"title": "Feed 3"},
                    "entries": [
                        {
                            "title": "Article from Feed 3",
                            "link": "https://example.com/3",
                            "summary": "Summary 3",
                            "published_parsed": time.struct_time((2024, 1, 13, 12, 0, 0, 0, 0, 0)),
                        }
                    ],
                }

        mock_parse.side_effect = mock_parse_side_effect

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["rss", "preview", "--allowlist", str(allowlist_file), "--limit", "1"],
        )

        assert result.exit_code == 0
        # Should have 3 feeds (comments and blanks ignored)
        assert "FEED https://example.com/feed1.xml" in result.output
        assert "FEED https://example.com/feed2.xml" in result.output
        assert "FEED https://example.com/feed3.xml" in result.output
        assert "Summary: feeds_total=3 feeds_ok=3 feeds_failed=0" in result.output


class TestRSSPreviewStream:
    """Test --stream input with tmp config."""

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_stream_config_resolution(self, mock_parse: MagicMock, tmp_path: Path):
        """Test --stream loads feeds from config.yaml."""
        # Create tmp allowlist file
        allowlist_file = tmp_path / "feeds.txt"
        allowlist_file.write_text(
            "https://example.com/feed1.xml\nhttps://example.com/feed2.xml\n",
            encoding="utf-8",
        )

        # Create tmp config.yaml
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            f"""
streams:
  test_stream:
    enabled: true
    rss:
      allowlist_files:
        - {allowlist_file}
""".lstrip(),
            encoding="utf-8",
        )

        # Mock feedparser
        def mock_parse_side_effect(url: str, **kwargs: Any) -> dict[str, Any]:
            return {
                "status": 200,
                "feed": {"title": "Test Feed"},
                "entries": [
                    {
                        "title": "Article",
                        "link": url.replace("feed", "article"),
                        "summary": "Summary",
                        "published_parsed": time.struct_time((2024, 1, 15, 12, 0, 0, 0, 0, 0)),
                    }
                ],
            }

        mock_parse.side_effect = mock_parse_side_effect

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--config",
                str(config_file),
                "rss",
                "preview",
                "--stream",
                "test_stream",
                "--limit",
                "1",
            ],
        )

        assert result.exit_code == 0
        assert "FEED https://example.com/feed1.xml" in result.output
        assert "FEED https://example.com/feed2.xml" in result.output
        assert "Summary: feeds_total=2 feeds_ok=2 feeds_failed=0" in result.output


class TestRSSPreviewUnknownStream:
    """Test error handling for unknown stream."""

    def test_unknown_stream_exits_2(self, tmp_path: Path):
        """Test that unknown stream exits with code 2."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
streams:
  test_stream:
    enabled: true
""".lstrip(),
            encoding="utf-8",
        )

        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "argus",
                "--config",
                str(config_file),
                "rss",
                "preview",
                "--stream",
                "unknown_stream",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 2
        assert "Error" in (result.stdout + result.stderr)


class TestRSSPreviewPartialFailures:
    """Test partial failures (one feed OK, one ERROR)."""

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_partial_failures_exit_1(self, mock_parse: MagicMock):
        """Test that partial failures exit with code 1."""

        def mock_parse_side_effect(url: str, **kwargs: Any) -> dict[str, Any]:
            if "good" in url:
                return {
                    "status": 200,
                    "feed": {"title": "Good Feed"},
                    "entries": [
                        {
                            "title": "Article",
                            "link": "https://example.com/1",
                            "summary": "Summary",
                            "published_parsed": time.struct_time((2024, 1, 15, 12, 0, 0, 0, 0, 0)),
                        }
                    ],
                }
            else:  # bad
                return {"status": 404}

        mock_parse.side_effect = mock_parse_side_effect

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "rss",
                "preview",
                "--url",
                "https://example.com/good.xml",
                "--url",
                "https://example.com/bad.xml",
                "--limit",
                "1",
            ],
        )

        assert result.exit_code == 1
        assert "FEED https://example.com/good.xml" in result.output
        assert "OK entries=1 showing=1" in result.output
        assert "FEED https://example.com/bad.xml" in result.output
        assert "ERROR: HTTP error 404" in result.output
        assert "Summary: feeds_total=2 feeds_ok=1 feeds_failed=1" in result.output

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_partial_failures_json_includes_errors(self, mock_parse: MagicMock):
        """Test that JSON output includes errors for failed feeds."""

        def mock_parse_side_effect(url: str, **kwargs: Any) -> dict[str, Any]:
            if "good" in url:
                return {
                    "status": 200,
                    "feed": {"title": "Good Feed"},
                    "entries": [
                        {
                            "title": "Article",
                            "link": "https://example.com/1",
                            "summary": "Summary",
                            "published_parsed": time.struct_time((2024, 1, 15, 12, 0, 0, 0, 0, 0)),
                        }
                    ],
                }
            else:  # bad
                return {"status": 404}

        mock_parse.side_effect = mock_parse_side_effect

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "rss",
                "preview",
                "--url",
                "https://example.com/good.xml",
                "--url",
                "https://example.com/bad.xml",
                "--json",
                "--limit",
                "1",
            ],
        )

        assert result.exit_code == 1

        # Parse JSON output
        output = json.loads(result.output)

        # Validate counts
        assert output["feeds_total"] == 2
        assert output["feeds_ok"] == 1
        assert output["feeds_failed"] == 1

        # Find good and bad feeds
        good_feed = next(f for f in output["feeds"] if "good" in f["feed_url"])
        bad_feed = next(f for f in output["feeds"] if "bad" in f["feed_url"])

        # Validate good feed
        assert good_feed["ok"] is True
        assert good_feed["error"] is None
        assert good_feed["entries_total"] == 1
        assert len(good_feed["entries"]) == 1

        # Validate bad feed
        assert bad_feed["ok"] is False
        assert bad_feed["error"] is not None
        assert "HTTP error 404" in bad_feed["error"]
        assert bad_feed["entries_total"] == 0
        assert len(bad_feed["entries"]) == 0


class TestRSSPreviewDeduplication:
    """Test URL deduplication."""

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_deduplication_preserves_order(self, mock_parse: MagicMock):
        """Test that duplicate URLs are deduplicated while preserving order."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {
                    "title": "Article",
                    "link": "https://example.com/1",
                    "summary": "Summary",
                    "published_parsed": time.struct_time((2024, 1, 15, 12, 0, 0, 0, 0, 0)),
                }
            ],
        }

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "rss",
                "preview",
                "--url",
                "https://example.com/feed.xml",
                "--url",
                "https://example.com/feed.xml",
                "--url",
                "https://example.com/feed.xml",
                "--limit",
                "1",
            ],
        )

        assert result.exit_code == 0
        # Should only appear once in output
        assert result.output.count("FEED https://example.com/feed.xml") == 1
        assert "Summary: feeds_total=1 feeds_ok=1 feeds_failed=0" in result.output


class TestRSSPreviewLimitZero:
    """Test --limit 0 behavior."""

    @patch("argus.ingestion.rss_parser.feedparser.parse")
    def test_limit_zero_shows_status_no_entries(self, mock_parse: MagicMock):
        """Test that --limit 0 shows feed status but no entries."""
        mock_parse.return_value = {
            "status": 200,
            "feed": {"title": "Test Feed"},
            "entries": [
                {
                    "title": "Article 1",
                    "link": "https://example.com/1",
                    "summary": "Summary 1",
                    "published_parsed": time.struct_time((2024, 1, 15, 12, 0, 0, 0, 0, 0)),
                },
                {
                    "title": "Article 2",
                    "link": "https://example.com/2",
                    "summary": "Summary 2",
                    "published_parsed": time.struct_time((2024, 1, 14, 12, 0, 0, 0, 0, 0)),
                },
            ],
        }

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "rss",
                "preview",
                "--url",
                "https://example.com/feed.xml",
                "--limit",
                "0",
            ],
        )

        assert result.exit_code == 0
        assert "FEED https://example.com/feed.xml" in result.output
        assert "OK entries=2 showing=0" in result.output
        # Should not show any articles
        assert "Article 1" not in result.output
        assert "Article 2" not in result.output
        assert "Summary: feeds_total=1 feeds_ok=1 feeds_failed=0" in result.output
