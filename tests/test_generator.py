"""Tests for the generator module.

Tests cover:
- Type definitions (GenerationMode, GeneratorConfig, NewsContext, etc.)
- Prompts (system prompts, user prompt building, news context formatting)
- Renderer (MarkdownV2 escaping, section formatting, message assembly)
- Generator (LLM integration with mocked responses)
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from argus.config import ConstraintsConfig
from argus.facts_bundle.types import (
    CalendarEventBundle,
    FactsBundle,
    IndexData,
    MarketSnapshotBundle,
    NewsItemBundle,
    SpotlightBundle,
)
from argus.generator import (
    GenerationError,
    GenerationMode,
    GeneratorConfig,
    GeneratorResult,
    LLMGeneratedContent,
    MessageGenerator,
    MessageRenderer,
    NewsContext,
    build_news_contexts,
    build_user_prompt,
    count_words,
    escape_markdown_v2,
    extract_referenced_ids,
    format_index_snapshot,
    get_system_prompt,
    render_message,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_index_data() -> IndexData:
    """Sample index data for tests."""
    return IndexData(
        name="S&P 500",
        symbol="^GSPC",
        level=Decimal("5000.50"),
        change_1d_pct=Decimal("0.75"),
        change_1d_pts=Decimal("37.25"),
    )


@pytest.fixture
def sample_market_snapshot(sample_index_data: IndexData) -> MarketSnapshotBundle:
    """Sample market snapshot for tests."""
    return MarketSnapshotBundle(
        trading_date=date(2025, 1, 7),
        sp500=sample_index_data,
        dow=IndexData(
            name="Dow Jones",
            symbol="^DJI",
            level=Decimal("42000.00"),
            change_1d_pct=Decimal("-0.25"),
            change_1d_pts=Decimal("-105.50"),
        ),
        nasdaq=IndexData(
            name="Nasdaq",
            symbol="^IXIC",
            level=Decimal("16000.00"),
            change_1d_pct=Decimal("1.20"),
            change_1d_pts=Decimal("189.50"),
        ),
    )


@pytest.fixture
def sample_news_items() -> tuple[NewsItemBundle, ...]:
    """Sample news items for tests."""
    return (
        NewsItemBundle(
            id=1,
            title="Fed signals potential rate cut in March",
            source_name="Reuters",
            source_url="https://reuters.com/article/fed-rate-cut",
            published_at=datetime(2025, 1, 7, 12, 0, 0, tzinfo=timezone.utc),
            snippet="Federal Reserve officials indicated openness to rate cuts...",
            content_excerpt="The Federal Reserve signaled it may begin cutting rates...",
            topic="macro",
            impact_score=85,
        ),
        NewsItemBundle(
            id=2,
            title="Tech earnings beat expectations across the board",
            source_name="Bloomberg",
            source_url="https://bloomberg.com/news/tech-earnings",
            published_at=datetime(2025, 1, 7, 10, 0, 0, tzinfo=timezone.utc),
            snippet="Major tech companies reported strong Q4 results...",
            content_excerpt="Apple, Microsoft, and Google all beat analyst estimates...",
            topic="earnings",
            impact_score=75,
        ),
        NewsItemBundle(
            id=3,
            title="Oil prices rise on supply concerns",
            source_name="CNBC",
            source_url="https://cnbc.com/oil-prices-rise",
            published_at=datetime(2025, 1, 7, 8, 0, 0, tzinfo=timezone.utc),
            snippet="WTI crude climbed 2% amid geopolitical tensions...",
            content_excerpt=None,
            topic="commodities",
            impact_score=60,
        ),
    )


@pytest.fixture
def sample_calendar_events() -> tuple[CalendarEventBundle, ...]:
    """Sample calendar events for tests."""
    return (
        CalendarEventBundle(
            name="FOMC Minutes",
            timestamp_utc=datetime(2025, 1, 8, 19, 0, 0, tzinfo=timezone.utc),
            event_type="fed",
            formatted_display="Wed 8 Jan – FOMC Minutes (19:00 UTC)",
        ),
        CalendarEventBundle(
            name="CPI Report",
            timestamp_utc=datetime(2025, 1, 10, 13, 30, 0, tzinfo=timezone.utc),
            event_type="economic",
            formatted_display="Fri 10 Jan – CPI Report (13:30 UTC)",
        ),
    )


@pytest.fixture
def sample_facts_bundle(
    sample_market_snapshot: MarketSnapshotBundle,
    sample_news_items: tuple[NewsItemBundle, ...],
    sample_calendar_events: tuple[CalendarEventBundle, ...],
) -> FactsBundle:
    """Sample facts bundle for tests."""
    return FactsBundle(
        version="1.0",
        stream_name="us_close_basic",
        run_mode="us_close",
        generated_at=datetime(2025, 1, 7, 22, 0, 0, tzinfo=timezone.utc),
        trading_date=date(2025, 1, 7),
        market_snapshot=sample_market_snapshot,
        news_items=sample_news_items,
        calendar_events=sample_calendar_events,
        spotlight=None,
    )


@pytest.fixture
def sample_news_contexts(sample_news_items: tuple[NewsItemBundle, ...]) -> list[NewsContext]:
    """Sample news contexts for tests."""
    contexts = []
    for i, item in enumerate(sample_news_items, start=1):
        published_date = None
        if item.published_at:
            published_date = item.published_at.strftime("%d %b %Y")
        contexts.append(
            NewsContext(
                ref_number=i,
                news_item_id=item.id,
                title=item.title,
                source_name=item.source_name,
                source_url=item.source_url,
                published_date=published_date,
                snippet=item.snippet,
                content_excerpt=item.content_excerpt,
                topic=item.topic,
            )
        )
    return contexts


@pytest.fixture
def sample_llm_content() -> LLMGeneratedContent:
    """Sample LLM-generated content for tests."""
    return LLMGeneratedContent(
        narrative=(
            "Markets rallied today as the Federal Reserve signaled openness to rate cuts [1]. "
            "Tech stocks led the charge following strong earnings reports [2].\n\n"
            "The S&P 500 closed higher, buoyed by optimism around monetary policy. "
            "Cross-asset confirmation came from falling Treasury yields."
        ),
        takeaways=[
            "Monitor Fed communications for rate cut timing",
            "Tech sector showing resilience despite macro uncertainty",
            "Treasury yields trending lower supports equity valuations",
        ],
        watch_next=[
            "FOMC Minutes release on Wednesday",
            "CPI data on Friday for inflation signals",
        ],
        referenced_item_ids=[1, 2],
        raw_response='{"narrative": "...", "takeaways": [...], "watch_next": [...]}',
    )


# =============================================================================
# Tests: types.py
# =============================================================================


class TestGenerationMode:
    """Tests for GenerationMode enum."""

    def test_from_string_us_close(self) -> None:
        """Test parsing us_close mode."""
        mode = GenerationMode.from_string("us_close")
        assert mode == GenerationMode.US_CLOSE

    def test_from_string_weekend_wrap(self) -> None:
        """Test parsing weekend_wrap mode."""
        mode = GenerationMode.from_string("weekend_wrap")
        assert mode == GenerationMode.WEEKEND_WRAP

    def test_from_string_monday_preview(self) -> None:
        """Test parsing monday_preview mode."""
        mode = GenerationMode.from_string("monday_preview")
        assert mode == GenerationMode.MONDAY_PREVIEW

    def test_from_string_invalid(self) -> None:
        """Test parsing invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown generation mode"):
            GenerationMode.from_string("invalid_mode")


class TestNewsContext:
    """Tests for NewsContext dataclass."""

    def test_format_for_prompt_with_all_fields(
        self, sample_news_contexts: list[NewsContext]
    ) -> None:
        """Test format_for_prompt with all fields populated."""
        ctx = sample_news_contexts[0]
        formatted = ctx.format_for_prompt()

        assert "[1]" in formatted
        assert "Fed signals potential rate cut" in formatted
        assert "Reuters" in formatted
        assert "[macro]" in formatted
        assert "07 Jan 2025" in formatted

    def test_format_for_prompt_without_content(
        self, sample_news_contexts: list[NewsContext]
    ) -> None:
        """Test format_for_prompt when content_excerpt is None."""
        ctx = sample_news_contexts[2]  # Oil prices article has no content_excerpt
        formatted = ctx.format_for_prompt()

        # Should fall back to snippet
        assert "WTI crude climbed 2%" in formatted

    def test_format_for_sources(self, sample_news_contexts: list[NewsContext]) -> None:
        """Test format_for_sources produces valid source citation."""
        ctx = sample_news_contexts[0]
        formatted = ctx.format_for_sources()

        # Format: [n] [Title](url) - hyperlinked title
        assert "[1]" in formatted
        assert "Fed signals potential rate cut" in formatted
        assert "https://reuters.com" in formatted
        # Source name and date are not included
        assert "Reuters —" not in formatted


class TestGeneratorConfig:
    """Tests for GeneratorConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = GeneratorConfig()

        assert config.enabled is True
        assert config.model == "openai/gpt-4.1"
        assert config.temperature == 0.4
        assert config.max_retries == 1
        assert config.timeout_seconds == 60

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = GeneratorConfig(
            enabled=False,
            model="anthropic/claude-3-sonnet",
            temperature=0.7,
            max_retries=3,
            timeout_seconds=120,
        )

        assert config.enabled is False
        assert config.model == "anthropic/claude-3-sonnet"
        assert config.temperature == 0.7
        assert config.max_retries == 3
        assert config.timeout_seconds == 120


class TestGeneratorResult:
    """Tests for GeneratorResult dataclass."""

    def test_to_dict(self, sample_llm_content: LLMGeneratedContent) -> None:
        """Test serialization to dict."""
        result = GeneratorResult(
            message="*Market Update*\n...",
            message_raw="*Market Update*\n...",
            word_count=150,
            sources_count=2,
            has_spotlight=False,
            model="openai/gpt-4.1",
            generation_mode=GenerationMode.US_CLOSE,
            generated_at=datetime(2025, 1, 7, 22, 0, 0, tzinfo=timezone.utc),
            retry_count=0,
            llm_duration_seconds=2.5,
            error=None,
        )

        data = result.to_dict()

        assert data["word_count"] == 150
        assert data["sources_count"] == 2
        assert data["generation_mode"] == "us_close"
        assert data["model"] == "openai/gpt-4.1"


# =============================================================================
# Tests: prompts.py
# =============================================================================


class TestGetSystemPrompt:
    """Tests for get_system_prompt function."""

    def test_us_close_prompt(self) -> None:
        """Test system prompt for US close mode."""
        prompt = get_system_prompt(GenerationMode.US_CLOSE)

        assert "Daily US Close Update" in prompt
        assert "risk-on/off" in prompt
        assert "JSON" in prompt

    def test_weekend_wrap_prompt(self) -> None:
        """Test system prompt for weekend wrap mode."""
        prompt = get_system_prompt(GenerationMode.WEEKEND_WRAP)

        assert "Weekend Wrap" in prompt
        assert "Weekly Recap" in prompt

    def test_monday_preview_prompt(self) -> None:
        """Test system prompt for monday preview mode."""
        prompt = get_system_prompt(GenerationMode.MONDAY_PREVIEW)

        assert "Monday Preview" in prompt
        assert "Risk Alert" in prompt


class TestBuildNewsContexts:
    """Tests for build_news_contexts function."""

    def test_assigns_sequential_ref_numbers(self, sample_facts_bundle: FactsBundle) -> None:
        """Test that reference numbers are assigned sequentially."""
        contexts = build_news_contexts(sample_facts_bundle)

        assert len(contexts) == 3
        assert contexts[0].ref_number == 1
        assert contexts[1].ref_number == 2
        assert contexts[2].ref_number == 3

    def test_preserves_news_item_ids(self, sample_facts_bundle: FactsBundle) -> None:
        """Test that news item IDs are preserved."""
        contexts = build_news_contexts(sample_facts_bundle)

        assert contexts[0].news_item_id == 1
        assert contexts[1].news_item_id == 2
        assert contexts[2].news_item_id == 3

    def test_formats_published_date(self, sample_facts_bundle: FactsBundle) -> None:
        """Test that published dates are formatted correctly."""
        contexts = build_news_contexts(sample_facts_bundle)

        assert contexts[0].published_date == "07 Jan 2025"


class TestBuildUserPrompt:
    """Tests for build_user_prompt function."""

    def test_includes_market_data(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
    ) -> None:
        """Test that user prompt includes market data."""
        prompt = build_user_prompt(
            sample_facts_bundle,
            sample_news_contexts,
            GenerationMode.US_CLOSE,
            max_words=420,
        )

        assert "S&P 500" in prompt
        assert "5000.50" in prompt
        assert "MARKET DATA" in prompt

    def test_includes_news_items(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
    ) -> None:
        """Test that user prompt includes news items."""
        prompt = build_user_prompt(
            sample_facts_bundle,
            sample_news_contexts,
            GenerationMode.US_CLOSE,
            max_words=420,
        )

        assert "NEWS ITEMS" in prompt
        assert "[1]" in prompt
        assert "Fed signals" in prompt

    def test_includes_calendar_events(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
    ) -> None:
        """Test that user prompt includes calendar events."""
        prompt = build_user_prompt(
            sample_facts_bundle,
            sample_news_contexts,
            GenerationMode.US_CLOSE,
            max_words=420,
        )

        assert "UPCOMING EVENTS" in prompt
        assert "FOMC Minutes" in prompt

    def test_includes_word_limit(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
    ) -> None:
        """Test that user prompt includes word limit constraint."""
        prompt = build_user_prompt(
            sample_facts_bundle,
            sample_news_contexts,
            GenerationMode.US_CLOSE,
            max_words=420,
        )

        assert "Maximum 420 words" in prompt


# =============================================================================
# Tests: renderer.py
# =============================================================================


class TestEscapeMarkdownV2:
    """Tests for escape_markdown_v2 function."""

    def test_escapes_dots(self) -> None:
        """Test that dots are escaped."""
        result = escape_markdown_v2("S&P 500 is 5000.50")
        assert "\\." in result

    def test_escapes_parentheses(self) -> None:
        """Test that parentheses are escaped."""
        result = escape_markdown_v2("(+0.75%)")
        assert "\\(" in result
        assert "\\)" in result

    def test_escapes_hash(self) -> None:
        """Test that hash symbols are escaped."""
        result = escape_markdown_v2("#trending")
        assert "\\#" in result

    def test_escapes_plus(self) -> None:
        """Test that plus signs are escaped."""
        result = escape_markdown_v2("+1.5%")
        assert "\\+" in result


class TestFormatIndexSnapshot:
    """Tests for format_index_snapshot function."""

    def test_includes_all_indices(self, sample_market_snapshot: MarketSnapshotBundle) -> None:
        """Test that all three indices are included."""
        formatted = format_index_snapshot(sample_market_snapshot)

        assert "S&P 500" in formatted
        assert "Dow Jones" in formatted
        assert "Nasdaq" in formatted

    def test_includes_levels_and_changes(
        self, sample_market_snapshot: MarketSnapshotBundle
    ) -> None:
        """Test that levels and changes are formatted correctly."""
        formatted = format_index_snapshot(sample_market_snapshot)

        # S&P 500: 5000.50 (+0.75%, +37.25 pts)
        assert "5000.50" in formatted
        assert "+0.75%" in formatted
        assert "+37.25 pts" in formatted


class TestExtractReferencedIds:
    """Tests for extract_referenced_ids function."""

    def test_extracts_single_reference(self, sample_news_contexts: list[NewsContext]) -> None:
        """Test extracting a single reference."""
        narrative = "Markets rallied on Fed news [1]."
        ids = extract_referenced_ids(narrative, sample_news_contexts)

        assert ids == [1]

    def test_extracts_multiple_references(self, sample_news_contexts: list[NewsContext]) -> None:
        """Test extracting multiple references."""
        narrative = "Fed [1] and tech earnings [2] drove gains."
        ids = extract_referenced_ids(narrative, sample_news_contexts)

        assert ids == [1, 2]

    def test_preserves_order_of_first_reference(
        self, sample_news_contexts: list[NewsContext]
    ) -> None:
        """Test that order is based on first reference."""
        narrative = "Tech [2] led, but Fed [1] was key. More on tech [2]."
        ids = extract_referenced_ids(narrative, sample_news_contexts)

        # Order should be [2, 1] since [2] appears first
        assert ids == [2, 1]

    def test_deduplicates_references(self, sample_news_contexts: list[NewsContext]) -> None:
        """Test that duplicate references are deduplicated."""
        narrative = "Fed [1] led. More Fed [1]. Tech [2]."
        ids = extract_referenced_ids(narrative, sample_news_contexts)

        assert ids == [1, 2]

    def test_ignores_invalid_references(self, sample_news_contexts: list[NewsContext]) -> None:
        """Test that invalid reference numbers are ignored."""
        narrative = "Markets [1] and something else [99]."
        ids = extract_referenced_ids(narrative, sample_news_contexts)

        assert ids == [1]


class TestCountWords:
    """Tests for count_words function."""

    def test_counts_simple_text(self) -> None:
        """Test counting words in simple text."""
        assert count_words("hello world") == 2

    def test_counts_paragraph(self) -> None:
        """Test counting words in a paragraph."""
        text = "Markets rallied today as investors cheered the Fed."
        assert count_words(text) == 8


class TestMessageRenderer:
    """Tests for MessageRenderer class."""

    def test_render_produces_output(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that render produces non-empty output."""
        renderer = MessageRenderer(sample_facts_bundle, sample_news_contexts)
        escaped, raw = renderer.render(sample_llm_content)

        assert len(escaped) > 0
        assert len(raw) > 0

    def test_render_includes_header(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that rendered message includes header."""
        renderer = MessageRenderer(sample_facts_bundle, sample_news_contexts)
        _, raw = renderer.render(sample_llm_content)

        assert "*Market Update*" in raw
        assert "7 Jan 2025" in raw

    def test_render_includes_indices(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that rendered message includes index snapshot."""
        renderer = MessageRenderer(sample_facts_bundle, sample_news_contexts)
        _, raw = renderer.render(sample_llm_content)

        assert "S&P 500" in raw
        assert "5000.50" in raw

    def test_render_includes_narrative(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that rendered message includes narrative."""
        renderer = MessageRenderer(sample_facts_bundle, sample_news_contexts)
        _, raw = renderer.render(sample_llm_content)

        assert "Federal Reserve signaled openness" in raw

    def test_render_includes_takeaways(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that rendered message includes takeaways."""
        renderer = MessageRenderer(sample_facts_bundle, sample_news_contexts)
        _, raw = renderer.render(sample_llm_content)

        # Now uses underline format
        assert "__Investor Key Takeaways__" in raw
        assert "Monitor Fed communications" in raw

    def test_render_includes_key_dates(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that rendered message includes key dates."""
        renderer = MessageRenderer(sample_facts_bundle, sample_news_contexts)
        _, raw = renderer.render(sample_llm_content)

        # Now uses underline format
        assert "__Key Dates (UTC)__" in raw
        assert "FOMC Minutes" in raw

    def test_render_includes_watch_next(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that rendered message includes watch next."""
        renderer = MessageRenderer(sample_facts_bundle, sample_news_contexts)
        _, raw = renderer.render(sample_llm_content)

        # Now uses underline format
        assert "__What to Watch Next__" in raw

    def test_render_includes_sources(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that rendered message includes sources."""
        renderer = MessageRenderer(sample_facts_bundle, sample_news_contexts)
        _, raw = renderer.render(sample_llm_content)

        # Now uses underline format and simplified source format
        assert "__Sources__" in raw
        assert "[1]" in raw
        # Source name is no longer included in the simplified format
        assert "Fed signals potential rate cut" in raw


class TestRenderMessage:
    """Tests for render_message convenience function."""

    def test_returns_tuple(
        self,
        sample_facts_bundle: FactsBundle,
        sample_news_contexts: list[NewsContext],
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that render_message returns (escaped, raw) tuple."""
        escaped, raw = render_message(
            sample_facts_bundle,
            sample_news_contexts,
            sample_llm_content,
            escape_markdown=True,
        )

        assert isinstance(escaped, str)
        assert isinstance(raw, str)
        assert len(escaped) > 0
        assert len(raw) > 0


# =============================================================================
# Tests: generator.py
# =============================================================================


class TestMessageGenerator:
    """Tests for MessageGenerator class."""

    def test_disabled_generator_raises_error(self, sample_facts_bundle: FactsBundle) -> None:
        """Test that disabled generator raises GenerationError."""
        config = GeneratorConfig(enabled=False)
        generator = MessageGenerator(config)

        with pytest.raises(GenerationError, match="disabled"):
            generator.generate(sample_facts_bundle)

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": ""})
    def test_missing_api_key_returns_fallback(self, sample_facts_bundle: FactsBundle) -> None:
        """Test that missing API key triggers fallback message."""
        config = GeneratorConfig(enabled=True)
        generator = MessageGenerator(config)

        result, validation = generator.generate(sample_facts_bundle)
        # Should return a fallback message, not raise an error
        assert result is not None
        assert result.error is not None  # Error is recorded but not raised
        assert "Market Update" in result.message_raw

    @patch("argus.generator.generator.httpx.Client")
    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
    def test_successful_generation(
        self,
        mock_client_class: MagicMock,
        sample_facts_bundle: FactsBundle,
    ) -> None:
        """Test successful message generation with mocked LLM."""
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"narrative": "Markets rallied [1].", "takeaways": ["Watch Fed", "Monitor markets", "Check data"], "watch_next": ["CPI data"]}'
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = GeneratorConfig(enabled=True, max_retries=0)
        constraints = ConstraintsConfig()

        with MessageGenerator(config, constraints) as generator:
            result, validation = generator.generate(sample_facts_bundle)

        assert isinstance(result, GeneratorResult)
        assert result.word_count >= 0
        assert result.generation_mode == GenerationMode.US_CLOSE

    @patch("argus.generator.generator.httpx.Client")
    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
    def test_parses_json_response(
        self,
        mock_client_class: MagicMock,
        sample_facts_bundle: FactsBundle,
    ) -> None:
        """Test that JSON response is correctly parsed."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": """{
                            "narrative": "Test narrative with [1] reference.",
                            "takeaways": ["Bullet 1", "Bullet 2", "Bullet 3"],
                            "watch_next": ["Watch 1"]
                        }"""
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = GeneratorConfig(enabled=True, max_retries=0)

        with MessageGenerator(config) as generator:
            result, validation = generator.generate(sample_facts_bundle)

        assert "Test narrative" in result.message_raw
        assert result.sources_count >= 0

    @patch("argus.generator.generator.httpx.Client")
    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
    def test_handles_markdown_code_block_response(
        self,
        mock_client_class: MagicMock,
        sample_facts_bundle: FactsBundle,
    ) -> None:
        """Test that markdown code block wrapped JSON is parsed."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": """```json
{
    "narrative": "Wrapped in code block [1].",
    "takeaways": ["Bullet", "Bullet 2", "Bullet 3"],
    "watch_next": ["Watch"]
}
```"""
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = GeneratorConfig(enabled=True, max_retries=0)

        with MessageGenerator(config) as generator:
            result, validation = generator.generate(sample_facts_bundle)

        assert "Wrapped in code block" in result.message_raw

    def test_context_manager(self) -> None:
        """Test that MessageGenerator works as context manager."""
        config = GeneratorConfig(enabled=False)

        with MessageGenerator(config) as generator:
            assert generator is not None

    def test_get_max_words_for_modes(self) -> None:
        """Test max words for different modes."""
        config = GeneratorConfig()
        constraints = ConstraintsConfig(
            max_words_daily=420,
            max_words_weekend=520,
            max_words_preview=320,
        )
        generator = MessageGenerator(config, constraints)

        assert generator._get_max_words(GenerationMode.US_CLOSE) == 420
        assert generator._get_max_words(GenerationMode.WEEKEND_WRAP) == 520
        assert generator._get_max_words(GenerationMode.MONDAY_PREVIEW) == 320


class TestGenerationWithSpotlight:
    """Tests for generation with spotlight content."""

    @pytest.fixture
    def bundle_with_spotlight(self, sample_facts_bundle: FactsBundle) -> FactsBundle:
        """Create a bundle with spotlight."""
        return FactsBundle(
            version=sample_facts_bundle.version,
            stream_name=sample_facts_bundle.stream_name,
            run_mode=sample_facts_bundle.run_mode,
            generated_at=sample_facts_bundle.generated_at,
            trading_date=sample_facts_bundle.trading_date,
            market_snapshot=sample_facts_bundle.market_snapshot,
            news_items=sample_facts_bundle.news_items,
            calendar_events=sample_facts_bundle.calendar_events,
            spotlight=SpotlightBundle(
                title="Global Equity Fund",
                body="Our flagship fund is now open for subscription.",
                disclaimer="Past performance is not indicative of future results.",
            ),
        )

    def test_spotlight_included_in_render(
        self,
        bundle_with_spotlight: FactsBundle,
        sample_llm_content: LLMGeneratedContent,
    ) -> None:
        """Test that spotlight is included in rendered output."""
        news_contexts = build_news_contexts(bundle_with_spotlight)
        renderer = MessageRenderer(bundle_with_spotlight, news_contexts)
        _, raw = renderer.render(sample_llm_content)

        assert "Fund Spotlight" in raw
        assert "Global Equity Fund" in raw
        assert "Past performance" in raw
