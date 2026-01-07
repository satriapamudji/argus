"""Configuration loading for Argus.

Loads configuration from .env (secrets) and config.yaml (settings).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class TelegramConfig:
    """Telegram configuration."""

    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"
    parse_mode_env: str = "TELEGRAM_PARSE_MODE"

    @property
    def bot_token(self) -> str:
        """Get bot token from environment."""
        return os.getenv(self.bot_token_env, "")

    @property
    def chat_id(self) -> str:
        """Get chat ID from environment."""
        return os.getenv(self.chat_id_env, "")

    @property
    def parse_mode(self) -> str:
        """Get parse mode from environment."""
        return os.getenv(self.parse_mode_env, "MarkdownV2")


@dataclass
class ScheduleConfig:
    """Schedule configuration."""

    daily_us_close_sgt: str = "06:00"
    weekend_wrap_sgt: str = "10:00"
    monday_preview_ny: str = "SUN 18:10"


@dataclass
class MondayPreviewConfig:
    """Monday preview configuration."""

    conditional: bool = True
    risk_threshold: int = 60
    force_publish: bool = False
    force_skip: bool = False


@dataclass
class RetentionConfig:
    """Retention configuration."""

    news_items_days: int = 60
    fingerprints_days: int = 3650
    runs_days: int = 3650


@dataclass
class SimHashConfig:
    """SimHash deduplication configuration."""

    enabled: bool = True
    hamming_threshold: int = 4
    window_days: int = 14


@dataclass
class TitleTrigramConfig:
    """Title trigram deduplication configuration."""

    enabled: bool = True
    similarity_threshold: float = 0.85


@dataclass
class DedupeConfig:
    """Deduplication configuration."""

    url_hash: bool = True
    text_hash: bool = True
    simhash: SimHashConfig = field(default_factory=SimHashConfig)
    title_trigram: TitleTrigramConfig = field(default_factory=TitleTrigramConfig)


@dataclass
class EnrichmentConfig:
    """Enrichment configuration."""

    enabled: bool = True
    max_enrich_per_run: int = 25
    allow_full_text_storage: bool = False
    snippet_chars: int = 1200


@dataclass
class SourceTiersConfig:
    """Source tier configuration for scoring.

    tier_1: Most authoritative sources (20 pts)
    tier_2: High-quality sources (15 pts)
    tier_3: Standard sources (10 pts)
    Unlisted sources default to 5 pts.
    """

    tier_1: list[str] = field(default_factory=lambda: ["Reuters", "Bloomberg", "WSJ"])
    tier_2: list[str] = field(default_factory=lambda: ["CNBC", "Financial Times"])
    tier_3: list[str] = field(default_factory=lambda: ["Yahoo Finance", "MarketWatch"])

    def get_tier_score(self, source_name: str) -> int:
        """Get score for a source based on its tier.

        Args:
            source_name: Name of the source to look up.

        Returns:
            Score: 20 for tier_1, 15 for tier_2, 10 for tier_3, 5 for unlisted.
        """
        source_lower = source_name.lower()
        for name in self.tier_1:
            if name.lower() in source_lower or source_lower in name.lower():
                return 20
        for name in self.tier_2:
            if name.lower() in source_lower or source_lower in name.lower():
                return 15
        for name in self.tier_3:
            if name.lower() in source_lower or source_lower in name.lower():
                return 10
        return 5


@dataclass
class ScoringConfig:
    """Scoring configuration."""

    enabled: bool = True
    window_hours: int = 24
    max_items_per_run: int = 100
    scorer_version: str = "heuristic_v1"
    source_tiers: SourceTiersConfig = field(default_factory=SourceTiersConfig)
    llm_triage_enabled: bool = False
    llm_model: str = "mistralai/mistral-7b-instruct"
    llm_max_items: int = 25

    @property
    def openrouter_api_key(self) -> str:
        """Get OpenRouter API key from environment."""
        return os.getenv("OPENROUTER_API_KEY", "")


@dataclass
class RSSConfig:
    """RSS configuration."""

    allowlist_files: Optional[list[str]] = None
    poll_interval_minutes: int = 10

    def __post_init__(self) -> None:
        if self.allowlist_files is None:
            self.allowlist_files = []


@dataclass
class ConstraintsConfig:
    """Constraints configuration."""

    max_words_daily: int = 420
    max_words_weekend: int = 520
    max_words_preview: int = 320
    max_takeaway_bullets: int = 5
    max_watch_bullets: int = 3


@dataclass
class SpotlightConfig:
    """Spotlight configuration."""

    enabled: bool = False
    title: str = ""
    body: str = ""
    disclaimer: str = ""


@dataclass
class EconomicCalendarConfig:
    """Economic calendar configuration.

    Controls the ForexFactory economic calendar integration for the
    "Key Dates (UTC)" section in generated messages.

    Attributes:
        enabled: Whether to fetch and include economic calendar events.
        feed_url: URL of the ForexFactory JSON feed.
        countries: List of country codes to include (e.g., ["USD", "EUR"]).
        impact_filter: List of impact levels to include (e.g., ["High"]).
        lookahead_days: Number of days ahead to look for events.
        stale_hours: Auto-refresh if data is older than this many hours.
    """

    enabled: bool = True
    feed_url: str = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    countries: list[str] = field(default_factory=lambda: ["USD"])
    impact_filter: list[str] = field(default_factory=lambda: ["High"])
    lookahead_days: int = 7
    stale_hours: int = 12


@dataclass
class StreamConfig:
    """Stream configuration."""

    name: str = ""
    enabled: bool = True
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    monday_preview: MondayPreviewConfig = field(default_factory=MondayPreviewConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    dedupe: DedupeConfig = field(default_factory=DedupeConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    rss: RSSConfig = field(default_factory=RSSConfig)
    constraints: ConstraintsConfig = field(default_factory=ConstraintsConfig)
    spotlight: SpotlightConfig = field(default_factory=SpotlightConfig)
    economic_calendar: EconomicCalendarConfig = field(default_factory=EconomicCalendarConfig)


@dataclass
class ArgusConfig:
    """Main Argus configuration."""

    stream: StreamConfig = field(default_factory=StreamConfig)
    log_level: str = "INFO"

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "ArgusConfig":
        """Load configuration from .env and config.yaml.

        Args:
            config_path: Optional path to config.yaml. Defaults to repo root.

        Returns:
            Loaded ArgusConfig instance.
        """
        # Load .env first
        load_dotenv()

        # Determine config path
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config.yaml"

        # Load YAML config
        if config_path.exists():
            with open(config_path, "r") as f:
                raw_config = yaml.safe_load(f) or {}
        else:
            raw_config = {}

        # Build stream config from YAML
        stream_raw = raw_config.get("stream", {})
        telegram_raw = stream_raw.get("telegram", {})
        schedule_raw = stream_raw.get("schedule", {})
        monday_preview_raw = stream_raw.get("monday_preview", {})
        retention_raw = stream_raw.get("retention", {})
        dedupe_raw = stream_raw.get("dedupe", {})
        enrichment_raw = stream_raw.get("enrichment", {})
        scoring_raw = stream_raw.get("scoring", {})
        rss_raw = stream_raw.get("rss", {})
        constraints_raw = stream_raw.get("constraints", {})
        spotlight_raw = stream_raw.get("spotlight", {})
        economic_calendar_raw = stream_raw.get("economic_calendar", {})

        # Parse nested configs
        telegram = TelegramConfig(
            bot_token_env=telegram_raw.get("bot_token_env", "TELEGRAM_BOT_TOKEN"),
            chat_id_env=telegram_raw.get("chat_id_env", "TELEGRAM_CHAT_ID"),
            parse_mode_env=telegram_raw.get("parse_mode_env", "TELEGRAM_PARSE_MODE"),
        )

        schedule = ScheduleConfig(
            daily_us_close_sgt=schedule_raw.get("daily_us_close_sgt", "06:00"),
            weekend_wrap_sgt=schedule_raw.get("weekend_wrap_sgt", "10:00"),
            monday_preview_ny=schedule_raw.get("monday_preview_ny", "SUN 18:10"),
        )

        monday_preview = MondayPreviewConfig(
            conditional=monday_preview_raw.get("conditional", True),
            risk_threshold=monday_preview_raw.get("risk_threshold", 60),
            force_publish=monday_preview_raw.get("force_publish", False),
            force_skip=monday_preview_raw.get("force_skip", False),
        )

        retention = RetentionConfig(
            news_items_days=retention_raw.get("news_items_days", 60),
            fingerprints_days=retention_raw.get("fingerprints_days", 3650),
            runs_days=retention_raw.get("runs_days", 3650),
        )

        simhash_raw = dedupe_raw.get("simhash", {})
        simhash = SimHashConfig(
            enabled=simhash_raw.get("enabled", True),
            hamming_threshold=simhash_raw.get("hamming_threshold", 4),
            window_days=simhash_raw.get("window_days", 14),
        )

        trigram_raw = dedupe_raw.get("title_trigram", {})
        title_trigram = TitleTrigramConfig(
            enabled=trigram_raw.get("enabled", True),
            similarity_threshold=trigram_raw.get("similarity_threshold", 0.85),
        )

        dedupe = DedupeConfig(
            url_hash=dedupe_raw.get("url_hash", True),
            text_hash=dedupe_raw.get("text_hash", True),
            simhash=simhash,
            title_trigram=title_trigram,
        )

        enrichment = EnrichmentConfig(
            enabled=enrichment_raw.get("enabled", True),
            max_enrich_per_run=enrichment_raw.get("max_enrich_per_run", 25),
            allow_full_text_storage=enrichment_raw.get("allow_full_text_storage", False),
            snippet_chars=enrichment_raw.get("snippet_chars", 1200),
        )

        source_tiers_raw = scoring_raw.get("source_tiers", {})
        source_tiers = SourceTiersConfig(
            tier_1=source_tiers_raw.get("tier_1", ["Reuters", "Bloomberg", "WSJ"]),
            tier_2=source_tiers_raw.get("tier_2", ["CNBC", "Financial Times"]),
            tier_3=source_tiers_raw.get("tier_3", ["Yahoo Finance", "MarketWatch"]),
        )

        scoring = ScoringConfig(
            enabled=scoring_raw.get("enabled", True),
            window_hours=scoring_raw.get("window_hours", 24),
            max_items_per_run=scoring_raw.get("max_items_per_run", 100),
            scorer_version=scoring_raw.get("scorer_version", "heuristic_v1"),
            source_tiers=source_tiers,
            llm_triage_enabled=scoring_raw.get("llm_triage_enabled", False),
            llm_model=scoring_raw.get("llm_model", "mistralai/mistral-7b-instruct"),
            llm_max_items=scoring_raw.get("llm_max_items", 25),
        )

        rss = RSSConfig(
            allowlist_files=rss_raw.get("allowlist_files", []),
            poll_interval_minutes=rss_raw.get("poll_interval_minutes", 10),
        )

        constraints = ConstraintsConfig(
            max_words_daily=constraints_raw.get("max_words_daily", 420),
            max_words_weekend=constraints_raw.get("max_words_weekend", 520),
            max_words_preview=constraints_raw.get("max_words_preview", 320),
            max_takeaway_bullets=constraints_raw.get("max_takeaway_bullets", 5),
            max_watch_bullets=constraints_raw.get("max_watch_bullets", 3),
        )

        spotlight = SpotlightConfig(
            enabled=spotlight_raw.get("enabled", False),
            title=spotlight_raw.get("title", ""),
            body=spotlight_raw.get("body", ""),
            disclaimer=spotlight_raw.get("disclaimer", ""),
        )

        economic_calendar = EconomicCalendarConfig(
            enabled=economic_calendar_raw.get("enabled", True),
            feed_url=economic_calendar_raw.get(
                "feed_url", "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            ),
            countries=economic_calendar_raw.get("countries", ["USD"]),
            impact_filter=economic_calendar_raw.get("impact_filter", ["High"]),
            lookahead_days=economic_calendar_raw.get("lookahead_days", 7),
            stale_hours=economic_calendar_raw.get("stale_hours", 12),
        )

        stream = StreamConfig(
            name=stream_raw.get("name", "us_close_basic"),
            enabled=stream_raw.get("enabled", True),
            telegram=telegram,
            schedule=schedule,
            monday_preview=monday_preview,
            retention=retention,
            dedupe=dedupe,
            enrichment=enrichment,
            scoring=scoring,
            rss=rss,
            constraints=constraints,
            spotlight=spotlight,
            economic_calendar=economic_calendar,
        )

        log_level = raw_config.get("log_level", "INFO")

        return cls(stream=stream, log_level=log_level)

    def get_rss_feeds(self) -> list[str]:
        """Get list of RSS feed URLs from allowlist files.

        Returns:
            List of RSS feed URLs.
        """
        feeds = []
        allowlist = self.stream.rss.allowlist_files or []
        for filename in allowlist:
            filepath = Path(filename)
            if not filepath.is_absolute():
                # Relative to repo root
                filepath = Path(__file__).parent.parent.parent / filename

            if filepath.exists():
                with open(filepath, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            feeds.append(line)
        return feeds
