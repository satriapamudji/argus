"""Tests for the facts_bundle module.

Tests cover:
- Type definitions (IndexData, NewsItemBundle, FactsBundle, etc.)
- JSON Schema validation
- BundleSelector with topic + source diversity
- Serialization/deserialization (to_dict/from_dict)
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from argus.facts_bundle.schema import (
    BUNDLE_SCHEMA_VERSION,
    BundleValidationError,
    validate_bundle,
)
from argus.facts_bundle.selector import (
    BundleSelector,
    select_bundle_items,
)
from argus.facts_bundle.types import (
    BundleCandidate,
    BundleStats,
    CalendarEventBundle,
    CrossAssetsData,
    FactsBundle,
    IndexData,
    MarketSnapshotBundle,
    NewsItemBundle,
    SpotlightBundle,
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
def sample_news_item() -> NewsItemBundle:
    """Sample news item for tests."""
    return NewsItemBundle(
        id=1,
        title="Fed signals potential rate cut in March",
        source_name="Reuters",
        source_url="https://reuters.com/article/fed-rate-cut",
        published_at=datetime(2025, 1, 7, 12, 0, 0, tzinfo=timezone.utc),
        snippet="Federal Reserve officials indicated openness to rate cuts...",
        content_excerpt="The Federal Reserve signaled it may begin cutting rates...",
        topic="macro",
        impact_score=85,
    )


@pytest.fixture
def sample_facts_bundle(
    sample_market_snapshot: MarketSnapshotBundle,
    sample_news_item: NewsItemBundle,
) -> FactsBundle:
    """Sample facts bundle for tests."""
    second_item = NewsItemBundle(
        id=2,
        title="S&P hits record high",
        source_name="Bloomberg",
        source_url="https://bloomberg.com/article/sp500",
        published_at=datetime(2025, 1, 7, 14, 0, 0, tzinfo=timezone.utc),
        snippet="The S&P 500 index reached an all-time high...",
        content_excerpt="Markets rallied as investors...",
        topic="equities",
        impact_score=80,
    )
    return FactsBundle(
        version=BUNDLE_SCHEMA_VERSION,
        stream_name="us_markets",
        run_mode="us_close",
        generated_at=datetime(2025, 1, 7, 22, 0, 0, tzinfo=timezone.utc),
        trading_date=date(2025, 1, 7),
        market_snapshot=sample_market_snapshot,
        news_items=(sample_news_item, second_item),
        calendar_events=tuple(),
        spotlight=None,
    )


def make_candidate(
    news_item_id: int = 1,
    title: str = "Test news",
    source_name: str = "TestSource",
    topic: str | None = "macro",
    impact_score: int = 50,
    has_content: bool = False,
) -> BundleCandidate:
    """Helper to create test candidates."""
    now = datetime.now(timezone.utc)
    return BundleCandidate(
        news_item_id=news_item_id,
        title=title,
        source_name=source_name,
        source_url=f"https://example.com/{news_item_id}",
        published_at=now,
        ingested_at=now,
        snippet="Test snippet",
        content_excerpt=None if not has_content else "Test content",
        topic=topic,
        impact_score=impact_score,
        has_content=has_content,
    )


# =============================================================================
# IndexData Tests
# =============================================================================


class TestIndexData:
    """Tests for IndexData dataclass."""

    def test_creation(self, sample_index_data: IndexData):
        """Test IndexData creation."""
        assert sample_index_data.name == "S&P 500"
        assert sample_index_data.symbol == "^GSPC"
        assert sample_index_data.level == Decimal("5000.50")
        assert sample_index_data.change_1d_pct == Decimal("0.75")
        assert sample_index_data.change_1d_pts == Decimal("37.25")

    def test_frozen(self, sample_index_data: IndexData):
        """Test IndexData is immutable."""
        with pytest.raises(AttributeError):
            sample_index_data.level = Decimal("6000.00")

    def test_to_dict(self, sample_index_data: IndexData):
        """Test IndexData serialization."""
        data = sample_index_data.to_dict()
        assert data["name"] == "S&P 500"
        assert data["symbol"] == "^GSPC"
        assert data["level"] == "5000.50"
        assert data["change_1d_pct"] == "0.75"
        assert data["change_1d_pts"] == "37.25"

    def test_from_dict(self, sample_index_data: IndexData):
        """Test IndexData deserialization."""
        data = sample_index_data.to_dict()
        restored = IndexData.from_dict(data)
        assert restored == sample_index_data


# =============================================================================
# CrossAssetsData Tests
# =============================================================================


class TestCrossAssetsData:
    """Tests for CrossAssetsData dataclass."""

    def test_empty(self):
        """Test empty CrossAssetsData."""
        cross = CrossAssetsData()
        assert cross.vix_level is None
        assert cross.to_dict() == {}

    def test_partial(self):
        """Test CrossAssetsData with partial data."""
        cross = CrossAssetsData(
            vix_level=Decimal("15.50"),
            vix_change_pct=Decimal("-2.30"),
        )
        data = cross.to_dict()
        assert data["vix_level"] == "15.50"
        assert data["vix_change_pct"] == "-2.30"
        assert "us10y_yield" not in data

    def test_roundtrip(self):
        """Test CrossAssetsData serialization roundtrip."""
        cross = CrossAssetsData(
            vix_level=Decimal("15.50"),
            us10y_yield=Decimal("4.25"),
            gold_level=Decimal("2050.00"),
        )
        data = cross.to_dict()
        restored = CrossAssetsData.from_dict(data)
        assert restored.vix_level == cross.vix_level
        assert restored.us10y_yield == cross.us10y_yield
        assert restored.gold_level == cross.gold_level


# =============================================================================
# MarketSnapshotBundle Tests
# =============================================================================


class TestMarketSnapshotBundle:
    """Tests for MarketSnapshotBundle dataclass."""

    def test_creation(self, sample_market_snapshot: MarketSnapshotBundle):
        """Test MarketSnapshotBundle creation."""
        assert sample_market_snapshot.trading_date == date(2025, 1, 7)
        assert sample_market_snapshot.sp500.name == "S&P 500"
        assert sample_market_snapshot.dow.name == "Dow Jones"
        assert sample_market_snapshot.nasdaq.name == "Nasdaq"

    def test_to_dict(self, sample_market_snapshot: MarketSnapshotBundle):
        """Test MarketSnapshotBundle serialization."""
        data = sample_market_snapshot.to_dict()
        assert data["trading_date"] == "2025-01-07"
        assert "sp500" in data
        assert "dow" in data
        assert "nasdaq" in data

    def test_roundtrip(self, sample_market_snapshot: MarketSnapshotBundle):
        """Test MarketSnapshotBundle roundtrip."""
        data = sample_market_snapshot.to_dict()
        restored = MarketSnapshotBundle.from_dict(data)
        assert restored.trading_date == sample_market_snapshot.trading_date
        assert restored.sp500 == sample_market_snapshot.sp500

    def test_with_cross_assets(self, sample_market_snapshot: MarketSnapshotBundle):
        """Test MarketSnapshotBundle with cross-asset data."""
        cross = CrossAssetsData(vix_level=Decimal("15.50"))
        snapshot = MarketSnapshotBundle(
            trading_date=sample_market_snapshot.trading_date,
            sp500=sample_market_snapshot.sp500,
            dow=sample_market_snapshot.dow,
            nasdaq=sample_market_snapshot.nasdaq,
            cross_assets=cross,
        )
        data = snapshot.to_dict()
        assert "cross_assets" in data
        assert data["cross_assets"]["vix_level"] == "15.50"


# =============================================================================
# NewsItemBundle Tests
# =============================================================================


class TestNewsItemBundle:
    """Tests for NewsItemBundle dataclass."""

    def test_creation(self, sample_news_item: NewsItemBundle):
        """Test NewsItemBundle creation."""
        assert sample_news_item.id == 1
        assert sample_news_item.title == "Fed signals potential rate cut in March"
        assert sample_news_item.source_name == "Reuters"
        assert sample_news_item.impact_score == 85

    def test_to_dict(self, sample_news_item: NewsItemBundle):
        """Test NewsItemBundle serialization."""
        data = sample_news_item.to_dict()
        assert data["id"] == 1
        assert data["title"] == "Fed signals potential rate cut in March"
        assert data["source_name"] == "Reuters"
        assert data["impact_score"] == 85
        assert data["topic"] == "macro"

    def test_roundtrip(self, sample_news_item: NewsItemBundle):
        """Test NewsItemBundle roundtrip."""
        data = sample_news_item.to_dict()
        restored = NewsItemBundle.from_dict(data)
        assert restored.id == sample_news_item.id
        assert restored.title == sample_news_item.title

    def test_optional_fields_null(self):
        """Test NewsItemBundle with null optional fields."""
        item = NewsItemBundle(
            id=1,
            title="Test",
            source_name="Test",
            source_url="https://example.com",
            published_at=None,
            snippet=None,
            content_excerpt=None,
            topic=None,
            impact_score=50,
        )
        data = item.to_dict()
        assert data["published_at"] is None
        assert data["snippet"] is None


# =============================================================================
# FactsBundle Tests
# =============================================================================


class TestFactsBundle:
    """Tests for FactsBundle dataclass."""

    def test_creation(self, sample_facts_bundle: FactsBundle):
        """Test FactsBundle creation."""
        assert sample_facts_bundle.version == BUNDLE_SCHEMA_VERSION
        assert sample_facts_bundle.stream_name == "us_markets"
        assert sample_facts_bundle.run_mode == "us_close"
        assert len(sample_facts_bundle.news_items) == 2

    def test_frozen(self, sample_facts_bundle: FactsBundle):
        """Test FactsBundle is immutable."""
        with pytest.raises(AttributeError):
            sample_facts_bundle.version = "2.0.0"

    def test_to_dict(self, sample_facts_bundle: FactsBundle):
        """Test FactsBundle serialization."""
        data = sample_facts_bundle.to_dict()
        assert data["version"] == BUNDLE_SCHEMA_VERSION
        assert data["stream_name"] == "us_markets"
        assert data["run_mode"] == "us_close"
        assert len(data["news_items"]) == 2

    def test_roundtrip(self, sample_facts_bundle: FactsBundle):
        """Test FactsBundle roundtrip."""
        data = sample_facts_bundle.to_dict()
        restored = FactsBundle.from_dict(data)
        assert restored.version == sample_facts_bundle.version
        assert restored.stream_name == sample_facts_bundle.stream_name
        assert len(restored.news_items) == len(sample_facts_bundle.news_items)

    def test_with_spotlight(self, sample_facts_bundle: FactsBundle):
        """Test FactsBundle with spotlight."""
        spotlight = SpotlightBundle(
            title="Market Alert",
            body="Volatility expected ahead of jobs report",
            disclaimer="Not investment advice",
        )
        bundle = FactsBundle(
            version=sample_facts_bundle.version,
            stream_name=sample_facts_bundle.stream_name,
            run_mode=sample_facts_bundle.run_mode,
            generated_at=sample_facts_bundle.generated_at,
            trading_date=sample_facts_bundle.trading_date,
            market_snapshot=sample_facts_bundle.market_snapshot,
            news_items=sample_facts_bundle.news_items,
            calendar_events=sample_facts_bundle.calendar_events,
            spotlight=spotlight,
        )
        data = bundle.to_dict()
        assert "spotlight" in data
        assert data["spotlight"]["title"] == "Market Alert"


# =============================================================================
# BundleCandidate Tests
# =============================================================================


class TestBundleCandidate:
    """Tests for BundleCandidate dataclass."""

    def test_effective_score_no_content(self):
        """Test effective_score without enriched content."""
        candidate = make_candidate(impact_score=50, has_content=False)
        assert candidate.effective_score == 50

    def test_effective_score_with_content(self):
        """Test effective_score with enriched content (+5 bonus)."""
        candidate = make_candidate(impact_score=50, has_content=True)
        assert candidate.effective_score == 55

    def test_to_news_item_bundle(self):
        """Test conversion to NewsItemBundle."""
        candidate = make_candidate(
            news_item_id=42,
            title="Test title",
            source_name="TestSource",
            topic="macro",
            impact_score=75,
        )
        item = candidate.to_news_item_bundle()
        assert isinstance(item, NewsItemBundle)
        assert item.id == 42
        assert item.title == "Test title"
        assert item.impact_score == 75


# =============================================================================
# BundleSelector Tests
# =============================================================================


class TestBundleSelector:
    """Tests for BundleSelector."""

    def test_select_respects_max_items(self):
        """Test selector respects max_items limit."""
        # Create candidates with different topics AND sources to avoid constraints
        candidates = [
            make_candidate(
                news_item_id=i,
                impact_score=90 - i,
                topic=f"topic_{i}",
                source_name=f"Source_{i}",
            )
            for i in range(10)
        ]
        selector = BundleSelector(max_per_topic=5, max_per_source=5)
        selected = selector.select(candidates, min_items=2, max_items=4)
        assert len(selected) == 4

    def test_select_sorts_by_effective_score(self):
        """Test selector sorts by effective_score descending."""
        candidates = [
            make_candidate(news_item_id=1, impact_score=50, topic="tech"),
            make_candidate(news_item_id=2, impact_score=80, topic="earnings"),
            make_candidate(news_item_id=3, impact_score=70, topic="macro"),
        ]
        selector = BundleSelector(max_per_topic=1, max_per_source=5)
        selected = selector.select(candidates, min_items=2, max_items=3)
        # Should be sorted by score: 80, 70, 50
        assert len(selected) == 3
        assert selected[0].news_item_id == 2
        assert selected[1].news_item_id == 3
        assert selected[2].news_item_id == 1

    def test_select_respects_max_per_topic(self):
        """Test selector respects max_per_topic constraint."""
        candidates = [
            make_candidate(news_item_id=1, impact_score=90, topic="macro"),
            make_candidate(news_item_id=2, impact_score=85, topic="macro"),
            make_candidate(news_item_id=3, impact_score=80, topic="earnings"),
            make_candidate(news_item_id=4, impact_score=75, topic="tech"),
        ]
        selector = BundleSelector(max_per_topic=1)
        selected = selector.select(candidates, min_items=2, max_items=4)

        # Should select id=1 (macro), id=3 (earnings), id=4 (tech)
        # id=2 skipped because macro already selected
        selected_ids = {c.news_item_id for c in selected}
        assert 1 in selected_ids
        assert 2 not in selected_ids
        assert 3 in selected_ids

    def test_select_respects_max_per_source(self):
        """Test selector respects max_per_source constraint."""
        candidates = [
            make_candidate(news_item_id=1, impact_score=90, source_name="Reuters", topic="a"),
            make_candidate(news_item_id=2, impact_score=85, source_name="Reuters", topic="b"),
            make_candidate(news_item_id=3, impact_score=80, source_name="Reuters", topic="c"),
            make_candidate(news_item_id=4, impact_score=75, source_name="Bloomberg", topic="d"),
        ]
        selector = BundleSelector(max_per_source=2, max_per_topic=5)
        selected = selector.select(candidates, min_items=2, max_items=4)

        # Should select id=1, id=2 (Reuters), id=4 (Bloomberg)
        # id=3 skipped because Reuters already has 2
        selected_ids = {c.news_item_id for c in selected}
        assert 1 in selected_ids
        assert 2 in selected_ids
        assert 3 not in selected_ids
        assert 4 in selected_ids

    def test_select_prefers_enriched_content(self):
        """Test selector prefers items with enriched content."""
        candidates = [
            make_candidate(news_item_id=1, impact_score=50, has_content=True, topic="a"),
            make_candidate(news_item_id=2, impact_score=52, has_content=False, topic="b"),
        ]
        selector = BundleSelector()
        selected = selector.select(candidates, min_items=2, max_items=2)

        # id=1 has effective_score=55, id=2 has effective_score=52
        # So id=1 should come first
        assert selected[0].news_item_id == 1

    def test_select_deterministic_with_same_score(self):
        """Test selector is deterministic (sorts by id when scores equal)."""
        candidates = [
            make_candidate(news_item_id=5, impact_score=80, topic="a"),
            make_candidate(news_item_id=3, impact_score=80, topic="b"),
            make_candidate(news_item_id=7, impact_score=80, topic="c"),
        ]
        selector = BundleSelector(max_per_topic=1, max_per_source=5)
        selected = selector.select(candidates, min_items=2, max_items=3)

        # Same score, should sort by id ascending: 3, 5, 7
        assert len(selected) == 3
        assert selected[0].news_item_id == 3
        assert selected[1].news_item_id == 5
        assert selected[2].news_item_id == 7

    def test_select_relaxes_constraints_if_needed(self):
        """Test selector relaxes constraints to meet min_items."""
        # All items have same topic
        candidates = [
            make_candidate(news_item_id=i, impact_score=90 - i, topic="macro") for i in range(5)
        ]
        selector = BundleSelector(max_per_topic=1)
        selected = selector.select(candidates, min_items=3, max_items=4)

        # Should relax topic constraint to get 3 items
        assert len(selected) >= 3

    def test_get_stats(self):
        """Test selector statistics tracking."""
        candidates = [
            make_candidate(news_item_id=1, impact_score=90, topic="macro"),
            make_candidate(news_item_id=2, impact_score=85, topic="macro"),
            make_candidate(news_item_id=3, impact_score=80, topic="macro"),
        ]
        selector = BundleSelector(max_per_topic=1, max_per_source=5)
        selected = selector.select(candidates, min_items=1, max_items=3)

        stats = selector.get_stats()
        assert stats["selected"] == 1  # Only one macro allowed
        assert stats["skipped_by_topic"] == 2


class TestSelectBundleItems:
    """Tests for select_bundle_items convenience function."""

    def test_returns_news_item_bundles(self):
        """Test function returns NewsItemBundle list."""
        candidates = [
            make_candidate(news_item_id=1, topic="a"),
            make_candidate(news_item_id=2, topic="b"),
        ]
        items, stats = select_bundle_items(candidates)
        assert all(isinstance(item, NewsItemBundle) for item in items)
        assert len(items) == 2

    def test_returns_stats(self):
        """Test function returns stats dict."""
        candidates = [make_candidate(news_item_id=i, topic=str(i)) for i in range(5)]
        items, stats = select_bundle_items(candidates)
        assert "selected" in stats
        assert "skipped_by_topic" in stats
        assert "skipped_by_source" in stats
        assert "enriched_items" in stats


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestSchemaValidation:
    """Tests for JSON Schema validation."""

    def test_valid_bundle(self, sample_facts_bundle: FactsBundle):
        """Test valid bundle passes validation."""
        data = sample_facts_bundle.to_dict()
        errors = validate_bundle(data, raise_on_error=False)
        assert errors == []

    def test_invalid_version_format(self, sample_facts_bundle: FactsBundle):
        """Test invalid version format fails validation."""
        data = sample_facts_bundle.to_dict()
        data["version"] = "invalid"
        errors = validate_bundle(data, raise_on_error=False)
        assert len(errors) > 0

    def test_invalid_run_mode(self, sample_facts_bundle: FactsBundle):
        """Test invalid run_mode fails validation."""
        data = sample_facts_bundle.to_dict()
        data["run_mode"] = "invalid_mode"
        errors = validate_bundle(data, raise_on_error=False)
        assert len(errors) > 0

    def test_missing_required_field(self, sample_facts_bundle: FactsBundle):
        """Test missing required field fails validation."""
        data = sample_facts_bundle.to_dict()
        del data["market_snapshot"]
        errors = validate_bundle(data, raise_on_error=False)
        assert len(errors) > 0

    def test_too_few_news_items(self, sample_market_snapshot: MarketSnapshotBundle):
        """Test bundle with < 2 news items fails validation."""
        item = NewsItemBundle(
            id=1,
            title="Test",
            source_name="Test",
            source_url="https://example.com",
            published_at=None,
            snippet=None,
            content_excerpt=None,
            topic=None,
            impact_score=50,
        )
        bundle = FactsBundle(
            version=BUNDLE_SCHEMA_VERSION,
            stream_name="test",
            run_mode="us_close",
            generated_at=datetime.now(timezone.utc),
            trading_date=date.today(),
            market_snapshot=sample_market_snapshot,
            news_items=(item,),  # Only 1 item
            calendar_events=tuple(),
        )
        data = bundle.to_dict()
        errors = validate_bundle(data, raise_on_error=False)
        assert len(errors) > 0
        # Check for the minimum items error (phrasing may vary)
        assert any("1" in e and ("item" in e.lower() or "short" in e.lower()) for e in errors)

    def test_raises_on_error(self, sample_facts_bundle: FactsBundle):
        """Test validate_bundle raises BundleValidationError."""
        data = sample_facts_bundle.to_dict()
        data["version"] = "invalid"
        with pytest.raises(BundleValidationError) as exc_info:
            validate_bundle(data, raise_on_error=True)
        assert len(exc_info.value.errors) > 0


# =============================================================================
# BundleStats Tests
# =============================================================================


class TestBundleStats:
    """Tests for BundleStats dataclass."""

    def test_defaults(self):
        """Test BundleStats defaults."""
        stats = BundleStats()
        assert stats.total_candidates == 0
        assert stats.selected_items == 0
        assert stats.duration_seconds == 0.0

    def test_to_dict(self):
        """Test BundleStats serialization."""
        stats = BundleStats(
            total_candidates=50,
            selected_items=5,
            skipped_by_topic=10,
            enriched_items=3,
            duration_seconds=1.5,
        )
        data = stats.to_dict()
        assert data["total_candidates"] == 50
        assert data["selected_items"] == 5
        assert data["duration_seconds"] == 1.5


# =============================================================================
# Calendar and Spotlight Tests
# =============================================================================


class TestCalendarEventBundle:
    """Tests for CalendarEventBundle."""

    def test_creation(self):
        """Test CalendarEventBundle creation."""
        event = CalendarEventBundle(
            name="FOMC Meeting",
            timestamp_utc=datetime(2025, 1, 29, 19, 0, 0, tzinfo=timezone.utc),
            event_type="fed",
            formatted_display="Wed 29 Jan 2:00 PM ET - FOMC Meeting",
        )
        assert event.name == "FOMC Meeting"
        assert event.event_type == "fed"

    def test_roundtrip(self):
        """Test CalendarEventBundle roundtrip."""
        event = CalendarEventBundle(
            name="Jobs Report",
            timestamp_utc=datetime(2025, 2, 7, 13, 30, 0, tzinfo=timezone.utc),
            event_type="economic",
            formatted_display="Fri 7 Feb 8:30 AM ET - Jobs Report",
        )
        data = event.to_dict()
        restored = CalendarEventBundle.from_dict(data)
        assert restored.name == event.name
        assert restored.timestamp_utc == event.timestamp_utc


class TestSpotlightBundle:
    """Tests for SpotlightBundle."""

    def test_creation(self):
        """Test SpotlightBundle creation."""
        spotlight = SpotlightBundle(
            title="Market Alert",
            body="Volatility expected this week",
            disclaimer="Not investment advice",
        )
        assert spotlight.title == "Market Alert"

    def test_roundtrip(self):
        """Test SpotlightBundle roundtrip."""
        spotlight = SpotlightBundle(
            title="Test",
            body="Body text",
            disclaimer="Disclaimer",
        )
        data = spotlight.to_dict()
        restored = SpotlightBundle.from_dict(data)
        assert restored == spotlight
