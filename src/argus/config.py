"""Configuration loading for Argus.

Loads configuration from .env (secrets) and config.yaml (settings).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


class UnknownStreamError(ValueError):
    """Raised when a requested stream name does not exist in config."""


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
    daily_crypto_utc: str = "00:00"


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
class GeneratorConfig:
    """Generator LLM configuration.

    Controls the message generation using OpenRouter API.

    Attributes:
        enabled: Whether generation is enabled.
        model: OpenRouter model identifier (e.g., "openai/gpt-4.1").
        temperature: LLM temperature (0-1). Lower = more deterministic.
        max_retries: Number of retries on LLM failure.
        timeout_seconds: HTTP timeout for LLM API calls.
    """

    enabled: bool = True
    model: str = "openai/gpt-4.1"
    temperature: float = 0.4
    max_retries: int = 1
    timeout_seconds: int = 60

    @property
    def openrouter_api_key(self) -> str:
        """Get OpenRouter API key from environment."""
        return os.getenv("OPENROUTER_API_KEY", "")


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
class HolidayBehaviorConfig:
    """Holiday and half-day behavior configuration.

    Controls how the orchestrator handles market holidays and early close days.

    Attributes:
        holiday_behavior: What to do on full market holidays.
            - "skip": Skip the run entirely (default).
            - "publish_closed_note": Publish a "markets closed" note.
        half_day_behavior: What to do on early close / half days.
            - "label_half_day": Include a label in the message (default).
            - "skip": Skip the run entirely.
    """

    holiday_behavior: str = "skip"
    half_day_behavior: str = "label_half_day"

    def __post_init__(self) -> None:
        """Validate behavior values."""
        valid_holiday = {"skip", "publish_closed_note"}
        valid_half_day = {"label_half_day", "skip"}

        if self.holiday_behavior not in valid_holiday:
            raise ValueError(
                f"Invalid holiday_behavior: {self.holiday_behavior}. "
                f"Must be one of: {valid_holiday}"
            )
        if self.half_day_behavior not in valid_half_day:
            raise ValueError(
                f"Invalid half_day_behavior: {self.half_day_behavior}. "
                f"Must be one of: {valid_half_day}"
            )


@dataclass
class DaemonConfig:
    """Daemon scheduler configuration.

    Controls the long-running daemon mode with internal scheduling.

    Attributes:
        enabled: Whether daemon mode is available.
        health_port: Port for health endpoint (0 to disable).
        health_bind: Address to bind health endpoint to.
        retention_hour: Hour (UTC) to run retention cleanup.
        health_ping_minutes: Interval minutes for journald heartbeat log (<=0 to disable).
        jobs_enabled: Dict of job_id -> enabled status.
        missed_policy: Dict of job_id -> policy ('run_immediately' or 'skip').
    """

    enabled: bool = True
    health_port: int = 8080
    health_bind: str = "127.0.0.1"
    retention_hour: int = 3
    health_ping_minutes: int = 10
    jobs_enabled: dict[str, bool] = field(
        default_factory=lambda: {
            "ingest": True,
            "us_close": True,
            "weekend_wrap": True,
            "monday_preview": True,
            "crypto_daily": True,
            "retention": True,
        }
    )
    missed_policy: dict[str, str] = field(
        default_factory=lambda: {
            "ingest": "run_immediately",
            "retention": "run_immediately",
            "us_close": "skip",
            "weekend_wrap": "skip",
            "monday_preview": "skip",
        }
    )

    def is_job_enabled(self, job_id: str) -> bool:
        """Check if a job is enabled.

        Args:
            job_id: Job identifier.

        Returns:
            True if job is enabled, False otherwise.
        """
        return self.jobs_enabled.get(job_id, True)

    def get_missed_policy(self, job_id: str) -> str:
        """Get the missed job policy.

        Args:
            job_id: Job identifier.

        Returns:
            Policy string ('run_immediately' or 'skip').
        """
        return self.missed_policy.get(job_id, "skip")


@dataclass
class StreamProvidersConfig:
    """Provider selection per pipeline stage.

    These are selector keys used by the pipeline registry. Provider-specific
    configuration stays in the existing config blocks (rss/scoring/enrichment/telegram).
    """

    ingestion: str = "rss"
    scoring: str = "heuristic_v2"
    enrichment: str = "fetch_extract"
    publisher: str = "telegram"


@dataclass
class NewsApiConfig:
    """NewsAPI configuration.

    Handles TheNewsAPI.com integration with multi-key rotation.

    Config File (apis/newsapi_{stream}.txt):
        key=value format, one per line
        Example:
            locale=us
            language=en
            categories=business,technology
            rotation_strategy=round_robin
            timeout_seconds=10

    Environment Variables:
        NEWS_API_KEYS: Comma-separated API keys (key1,key2,key3)
        NEWS_API_DEFAULT_LANGUAGE: Default if not in config file
        NEWS_API_ROTATION_STRATEGY: Default if not in config file
        NEWS_API_TIMEOUT_SECONDS: Default if not in config file

    Usage Headers:
        X-UsageLimit-Limit: Monthly limit for the key
        X-UsageLimit-Remaining: Remaining requests for the month

    Error Codes:
        402: Usage limit reached
        429: Rate limit exceeded
    """

    keys_env: str = "NEWS_API_KEYS"
    config_file: Optional[str] = None
    _parsed_config: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Parse config file if provided."""
        self._parsed_config = self._parse_config_file()

    def _parse_config_file(self) -> dict:
        """Parse the config file.

        Returns:
            Dict of parsed config values.
        """
        if not self.config_file:
            return {}

        filepath = Path(self.config_file)
        if not filepath.is_absolute():
            repo_root = Path(__file__).parent.parent.parent
            filepath = repo_root / self.config_file

        if not filepath.exists():
            return {}

        config: dict = {}
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
        return config

    @property
    def api_keys(self) -> list[str]:
        """Get API keys from environment, comma-separated."""
        keys_raw = os.getenv(self.keys_env, "")
        if not keys_raw:
            return []
        return [k.strip() for k in keys_raw.split(",") if k.strip()]

    def is_configured(self) -> bool:
        """Check if at least one API key is configured."""
        return len(self.api_keys) > 0

    @property
    def locale(self) -> str:
        """Get locale from config file or default."""
        return self._parsed_config.get("locale", "us")

    @property
    def language(self) -> str:
        """Get language from config file or environment default."""
        if "language" in self._parsed_config:
            return self._parsed_config["language"]
        return os.getenv("NEWS_API_DEFAULT_LANGUAGE", "en")

    @property
    def categories(self) -> list[str]:
        """Get categories from config file."""
        cats = self._parsed_config.get("categories", "")
        if not cats:
            return []
        return [c.strip() for c in cats.split(",") if c.strip()]

    @property
    def rotation_strategy(self) -> str:
        """Get rotation strategy from config file or environment default."""
        if "rotation_strategy" in self._parsed_config:
            return self._parsed_config["rotation_strategy"]
        return os.getenv("NEWS_API_ROTATION_STRATEGY", "round_robin")

    @property
    def timeout_seconds(self) -> int:
        """Get timeout from config file or environment default."""
        if "timeout_seconds" in self._parsed_config:
            try:
                return int(self._parsed_config["timeout_seconds"])
            except ValueError:
                pass
        return int(os.getenv("NEWS_API_TIMEOUT_SECONDS", "10"))

    @property
    def domains(self) -> list[str]:
        """Get domains to filter articles by.

        Example: ['reuters.com', 'bloomberg.com', 'wsj.com']
        """
        doms = self._parsed_config.get("domains", "")
        if not doms:
            return []
        return [d.strip() for d in doms.split(",") if d.strip()]

    @property
    def lookback_hours(self) -> int:
        """Get lookback window in hours for published_after filter.

        Default: 1 hour.
        """
        if "lookback_hours" in self._parsed_config:
            try:
                return int(self._parsed_config["lookback_hours"])
            except ValueError:
                pass
        return 1

    @property
    def max_pages_safety_limit(self) -> int:
        """Get safety limit for maximum pages to fetch.

        This is a safety limit to prevent infinite loops, not the primary
        stop condition. Pagination stops on duplicate detection (sliding
        window) or end of results.

        Default: 50 pages.
        """
        if "max_pages_safety_limit" in self._parsed_config:
            try:
                return int(self._parsed_config["max_pages_safety_limit"])
            except ValueError:
                pass
        return 50

    @property
    def articles_per_request(self) -> int:
        """Get number of articles to request per API call.

        Default: 3 (matches free tier limit).
        """
        if "articles_per_request" in self._parsed_config:
            try:
                return int(self._parsed_config["articles_per_request"])
            except ValueError:
                pass
        return 3

    @property
    def max_new_per_run(self) -> int:
        """Get maximum new articles to ingest per run.

        Prevents over-fetching on initial/bootstrap runs.
        Default: 50 articles.
        """
        if "max_new_per_run" in self._parsed_config:
            try:
                return int(self._parsed_config["max_new_per_run"])
            except ValueError:
                pass
        return 50

    @property
    def min_remaining_budget(self) -> int:
        """Minimum remaining API requests to preserve.

        Ingestion stops when usage_remaining drops to or below this threshold.
        This prevents burning through the entire monthly quota in one run.

        Set to 0 to disable budget enforcement (not recommended).
        Default: 10 requests.
        """
        if "min_remaining_budget" in self._parsed_config:
            try:
                return int(self._parsed_config["min_remaining_budget"])
            except ValueError:
                pass
        return 10


@dataclass
class CryptoStreamConfig:
    """Crypto-specific stream configuration.

    Controls crypto stream behavior including symbol selection and data sources.
    """

    top_n_market_cap: int = 10
    always_include_symbols: list[str] = field(default_factory=lambda: ["BTC", "ETH"])
    exclude_symbols: list[str] = field(default_factory=lambda: ["USDT", "USDC", "DAI"])
    chartinspect_api_key_env: str = "CHARTINSPECT_API"

    def __post_init__(self) -> None:
        """Validate crypto configuration."""
        if self.top_n_market_cap < 1:
            raise ValueError("top_n_market_cap must be at least 1")

    @property
    def chartinspect_api_key(self) -> str:
        """Get ChartInspect API key from environment."""
        return os.getenv(self.chartinspect_api_key_env, "")


@dataclass
class StreamDaemonConfig:
    """Per-stream daemon job overrides.

    Allows enabling/disabling specific jobs for this stream.
    When jobs_enabled[job_id] is set, it overrides the global daemon.jobs_enabled value.
    When not set (None or missing key), the global default is used.
    """

    jobs_enabled: dict[str, bool] = field(default_factory=dict)


@dataclass
class StreamConfig:
    """Stream configuration."""

    name: str = ""
    enabled: bool = True
    include_cross_assets: bool = False
    providers: StreamProvidersConfig = field(default_factory=StreamProvidersConfig)
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
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    economic_calendar: EconomicCalendarConfig = field(default_factory=EconomicCalendarConfig)
    holiday_behavior: HolidayBehaviorConfig = field(default_factory=HolidayBehaviorConfig)
    news_api: NewsApiConfig = field(default_factory=NewsApiConfig)
    crypto: CryptoStreamConfig = field(default_factory=CryptoStreamConfig)
    daemon: StreamDaemonConfig = field(default_factory=StreamDaemonConfig)


@dataclass
class ArgusConfig:
    """Main Argus configuration."""

    # Backward compatibility: most of the codebase still expects .stream
    # to exist (single-stream mode). In multi-stream configs, .stream is
    # set to the *selected* stream (CLI) or iterated by the daemon.
    stream: StreamConfig = field(default_factory=StreamConfig)

    # Multi-stream support (optional). Keyed by stream name.
    streams: dict[str, StreamConfig] = field(default_factory=dict)

    daemon: DaemonConfig = field(default_factory=DaemonConfig)
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

        def build_stream_config(stream_raw: dict, root_raw: dict) -> StreamConfig:
            """Build a StreamConfig from YAML.

            Supports both root-level defaults and stream-level overrides.
            Priority: stream-level > root-level > code defaults.
            """

            providers_raw = stream_raw.get("providers", {})
            # Merge root-level providers with stream-level overrides
            root_providers = root_raw.get("providers", {})
            providers_raw = {**root_providers, **providers_raw}

            def merge_config(key: str) -> dict:
                root = root_raw.get(key, {})
                stream = stream_raw.get(key, {})
                return {**root, **stream}

            telegram_raw = merge_config("telegram")
            schedule_raw = merge_config("schedule")
            monday_preview_raw = merge_config("monday_preview")
            retention_raw = merge_config("retention")
            dedupe_raw = merge_config("dedupe")
            enrichment_raw = merge_config("enrichment")
            scoring_raw = merge_config("scoring")
            rss_raw = merge_config("rss")
            constraints_raw = merge_config("constraints")
            spotlight_raw = merge_config("spotlight")
            generator_raw = merge_config("generator")
            economic_calendar_raw = merge_config("economic_calendar")
            holiday_behavior_raw = merge_config("holiday_behavior")

            providers = StreamProvidersConfig(
                ingestion=providers_raw.get("ingestion", "rss"),
                scoring=providers_raw.get("scoring", "heuristic_v2"),
                enrichment=providers_raw.get("enrichment", "fetch_extract"),
                publisher=providers_raw.get("publisher", "telegram"),
            )

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

            generator = GeneratorConfig(
                enabled=generator_raw.get("enabled", True),
                model=generator_raw.get("model", "openai/gpt-4.1"),
                temperature=generator_raw.get("temperature", 0.4),
                max_retries=generator_raw.get("max_retries", 1),
                timeout_seconds=generator_raw.get("timeout_seconds", 60),
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

            holiday_behavior = HolidayBehaviorConfig(
                holiday_behavior=holiday_behavior_raw.get("holiday_behavior", "skip"),
                half_day_behavior=holiday_behavior_raw.get("half_day_behavior", "label_half_day"),
            )

            include_cross_assets = stream_raw.get(
                "include_cross_assets", root_raw.get("include_cross_assets", False)
            )

            # Build NewsAPI config file path from stream name
            stream_name = stream_raw.get("name", "us_markets")
            newsapi_config_file = f"apis/newsapi_{stream_name}.txt"

            news_api = NewsApiConfig(config_file=newsapi_config_file)

            # Crypto-specific configuration
            crypto_raw = stream_raw.get("crypto", {})
            crypto = CryptoStreamConfig(
                top_n_market_cap=crypto_raw.get("top_n_market_cap", 10),
                always_include_symbols=crypto_raw.get("always_include_symbols", ["BTC", "ETH"]),
                exclude_symbols=crypto_raw.get("exclude_symbols", ["USDT", "USDC", "DAI"]),
                chartinspect_api_key_env=crypto_raw.get(
                    "chartinspect_api_key_env", "CHARTINSPECT_API"
                ),
            )

            # Per-stream daemon configuration (job overrides)
            stream_daemon_raw = stream_raw.get("daemon", {})
            stream_daemon = StreamDaemonConfig(
                jobs_enabled=stream_daemon_raw.get("jobs_enabled", {}),
            )

            return StreamConfig(
                name=stream_raw.get("name", "us_markets"),
                enabled=stream_raw.get("enabled", True),
                include_cross_assets=bool(include_cross_assets),
                providers=providers,
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
                generator=generator,
                economic_calendar=economic_calendar,
                holiday_behavior=holiday_behavior,
                news_api=news_api,
                crypto=crypto,
                daemon=stream_daemon,
            )

        # Build stream config(s) from YAML.
        streams_raw = raw_config.get("streams")
        streams: dict[str, StreamConfig] = {}

        if isinstance(streams_raw, dict) and streams_raw:
            for stream_name, stream_overrides in streams_raw.items():
                if not isinstance(stream_overrides, dict):
                    stream_overrides = {}
                # Ensure stream name is set deterministically.
                merged_stream = {**stream_overrides, "name": stream_name}
                stream_cfg = build_stream_config(merged_stream, raw_config)
                streams[stream_name] = stream_cfg

            # Backward-compat: pick the first stream as .stream placeholder.
            # CLI/daemon should explicitly select the active streams.
            first_name = next(iter(streams.keys()))
            stream = streams[first_name]
        else:
            stream_raw = raw_config.get("stream", {})
            stream = build_stream_config(stream_raw, raw_config)
            streams = {stream.name: stream}

        # NOTE: provider-specific runtime validations should live in the provider itself
        # (or the worker it wraps), not during config load.

        # Parse daemon config
        daemon_raw = raw_config.get("daemon", {})
        jobs_enabled_raw = daemon_raw.get("jobs_enabled", {})
        missed_policy_raw = daemon_raw.get("missed_policy", {})

        daemon = DaemonConfig(
            enabled=daemon_raw.get("enabled", True),
            health_port=daemon_raw.get("health_port", 8080),
            health_bind=daemon_raw.get("health_bind", "127.0.0.1"),
            retention_hour=daemon_raw.get("retention_hour", 3),
            health_ping_minutes=daemon_raw.get("health_ping_minutes", 10),
            jobs_enabled={
                "ingest": jobs_enabled_raw.get("ingest", True),
                "us_close": jobs_enabled_raw.get("us_close", True),
                "weekend_wrap": jobs_enabled_raw.get("weekend_wrap", True),
                "monday_preview": jobs_enabled_raw.get("monday_preview", True),
                "crypto_daily": jobs_enabled_raw.get("crypto_daily", True),
                "retention": jobs_enabled_raw.get("retention", True),
            },
            missed_policy={
                "ingest": missed_policy_raw.get("ingest", "run_immediately"),
                "retention": missed_policy_raw.get("retention", "run_immediately"),
                "us_close": missed_policy_raw.get("us_close", "skip"),
                "weekend_wrap": missed_policy_raw.get("weekend_wrap", "skip"),
                "monday_preview": missed_policy_raw.get("monday_preview", "skip"),
            },
        )

        log_level = raw_config.get("log_level", "INFO")

        return cls(stream=stream, streams=streams, daemon=daemon, log_level=log_level)

    def list_streams(self, *, enabled_only: bool = False) -> list[str]:
        """List configured stream names.

        Args:
            enabled_only: If True, return only enabled streams.

        Returns:
            Sorted list of stream names.
        """
        if enabled_only:
            names = [name for name, s in self.streams.items() if s.enabled]
        else:
            names = list(self.streams.keys())
        return sorted(names)

    def get_stream(self, stream_name: str) -> StreamConfig:
        """Get a stream config by name.

        Raises:
            UnknownStreamError: if stream_name does not exist.
        """
        stream = self.streams.get(stream_name)
        if stream is None:
            raise UnknownStreamError(
                f"Unknown stream: {stream_name}. Available: {', '.join(self.list_streams())}"
            )
        return stream

    def select_stream(self, stream_name: str) -> "ArgusConfig":
        """Return a view of this config with .stream set to the chosen stream."""
        selected = self.get_stream(stream_name)
        self.stream = selected
        return self

    def get_rss_feeds(self, stream_name: Optional[str] = None) -> list[str]:
        """Get list of RSS feed URLs from allowlist files.

        Args:
            stream_name: Optional stream name. If omitted, uses self.stream.

        Returns:
            List of RSS feed URLs.
        """
        feeds: list[str] = []
        stream = self.get_stream(stream_name) if stream_name else self.stream
        allowlist = stream.rss.allowlist_files or []

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


def is_job_enabled_for_stream(
    stream_cfg: StreamConfig,
    job_id: str,
    global_daemon: DaemonConfig,
) -> bool:
    """Check if a job is enabled for a specific stream.

    Resolution order:
    1. Per-stream override (stream_cfg.daemon.jobs_enabled[job_id]) takes precedence
    2. Falls back to global daemon config (global_daemon.jobs_enabled[job_id])

    Args:
        stream_cfg: The stream configuration to check.
        job_id: The job identifier (e.g., "us_close", "crypto_daily").
        global_daemon: The global daemon configuration.

    Returns:
        True if the job should run for this stream, False otherwise.
    """
    # Check per-stream override first
    stream_override = stream_cfg.daemon.jobs_enabled.get(job_id)
    if stream_override is not None:
        return stream_override

    # Fall back to global default
    return global_daemon.jobs_enabled.get(job_id, False)
