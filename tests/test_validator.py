import pytest
from datetime import datetime, date
from decimal import Decimal
from argus.facts_bundle.types import (
    FactsBundle,
    MarketSnapshotBundle,
    IndexData,
    NewsItemBundle,
    CalendarEventBundle,
)
from argus.generator.types import GeneratorResult, GenerationMode
from argus.validator.validator import MessageValidator


@pytest.fixture
def sample_bundle():
    sp500 = IndexData("S&P 500", "SPX", Decimal("5000.00"), Decimal("1.00"), Decimal("50.00"))
    dow = IndexData("Dow Jones", "DJI", Decimal("38000.00"), Decimal("0.50"), Decimal("190.00"))
    nasdaq = IndexData("Nasdaq", "IXIC", Decimal("15000.00"), Decimal("1.50"), Decimal("225.00"))

    snapshot = MarketSnapshotBundle(
        trading_date=date(2026, 1, 6), sp500=sp500, dow=dow, nasdaq=nasdaq
    )

    news = (
        NewsItemBundle(
            1,
            "Test News 1",
            "Source",
            "http://example.com/1",
            datetime.now(),
            "Snippet",
            None,
            "Topic",
            80,
        ),
        NewsItemBundle(
            2,
            "Test News 2",
            "Source",
            "http://example.com/2",
            datetime.now(),
            "Snippet",
            None,
            "Topic",
            70,
        ),
    )

    calendar = (CalendarEventBundle("Event 1", datetime.now(), "economic", "10:00 UTC: Event 1"),)

    return FactsBundle(
        version="1.0",
        stream_name="test",
        run_mode="us_close",
        generated_at=datetime.now(),
        trading_date=date(2026, 1, 6),
        market_snapshot=snapshot,
        news_items=news,
        calendar_events=calendar,
    )


def _make_result(raw_message: str) -> GeneratorResult:
    """Helper to create a GeneratorResult for testing."""
    return GeneratorResult(
        message=raw_message,
        message_raw=raw_message,
        word_count=50,
        sources_count=2,
        has_spotlight=False,
        model="gpt-4",
        generation_mode=GenerationMode.US_CLOSE,
        generated_at=datetime.now(),
    )


def test_validator_valid_message(sample_bundle):
    """Test that a correctly formatted message passes validation."""
    validator = MessageValidator()

    raw_message = """*Market Update*
*6 Jan 2026*

S&P 500 – 5000.00 (1D +1.00%, +50.00 pts)
Dow Jones – 38000.00 (1D +0.50%, +190.00 pts)
Nasdaq – 15000.00 (1D +1.50%, +225.00 pts)

Narrative about [1] and [2].

----
*Investor Key Takeaways*
• Bullet 1
• Bullet 2
• Bullet 3

*Key Dates (UTC)*
• 10:00 UTC: Event 1

*What to Watch Next*
• Watch 1

*Sources*
[1] [Test News 1 — Source](http://example.com/1)
[2] [Test News 2 — Source](http://example.com/2)
"""

    result = _make_result(raw_message)
    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is True
    assert not validation.errors


def test_validator_missing_section(sample_bundle):
    """Test that missing required sections are detected."""
    validator = MessageValidator()
    raw_message = "Too short message"
    result = _make_result(raw_message)

    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is False
    assert any("Missing required section" in e for e in validation.errors)


def test_validator_invalid_takeaway_bullets(sample_bundle):
    """Test that too few takeaway bullets are detected."""
    validator = MessageValidator()
    raw_message = """*Market Update*
*6 Jan 2026*

*Investor Key Takeaways*
• Only one bullet

*Key Dates (UTC)*
• Event

*What to Watch Next*
• One
• Two
• Three
• Four

*Sources*
[1] ...
"""
    result = _make_result(raw_message)

    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is False
    assert any("Invalid takeaway bullet count" in e for e in validation.errors)
    assert any("Invalid watch next bullet count" in e for e in validation.errors)


def test_validator_invalid_reference(sample_bundle):
    """Test that out-of-range citation references are detected."""
    validator = MessageValidator()
    raw_message = """*Market Update*
*6 Jan 2026*

*Investor Key Takeaways*
• One
• Two
• Three

*Key Dates (UTC)*
• Event

*What to Watch Next*
• Watch

*Sources*
[99] Non-existent
"""
    result = _make_result(raw_message)

    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is False
    assert any("Invalid reference number" in e for e in validation.errors)


def test_validator_hallucinated_url(sample_bundle):
    """Test that URLs not in the bundle are detected as hallucinations."""
    validator = MessageValidator()
    raw_message = """*Market Update*
*6 Jan 2026*

S&P 500 – 5000.00 (1D +1.00%, +50.00 pts)
Dow Jones – 38000.00 (1D +0.50%, +190.00 pts)
Nasdaq – 15000.00 (1D +1.50%, +225.00 pts)

Check out this fake link https://fake-news-site.com/article for more.

----
*Investor Key Takeaways*
• Bullet 1
• Bullet 2
• Bullet 3

*Key Dates (UTC)*
• Event

*What to Watch Next*
• Watch

*Sources*
[1] [Test News 1 — Source](http://example.com/1)
"""
    result = _make_result(raw_message)

    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is False
    assert any("Hallucinated URL" in e for e in validation.errors)


def test_validator_hallucinated_percentage(sample_bundle):
    """Test that percentages not in the bundle are detected as hallucinations."""
    validator = MessageValidator()
    # Bundle has 1.00%, 0.50%, 1.50% - we're using 7.5% which is not in the bundle
    raw_message = """*Market Update*
*6 Jan 2026*

S&P 500 – 5000.00 (1D +1.00%, +50.00 pts)
Dow Jones – 38000.00 (1D +0.50%, +190.00 pts)
Nasdaq – 15000.00 (1D +1.50%, +225.00 pts)

Markets rallied with tech stocks up 7.5% on strong earnings.

----
*Investor Key Takeaways*
• Bullet 1
• Bullet 2
• Bullet 3

*Key Dates (UTC)*
• Event

*What to Watch Next*
• Watch

*Sources*
[1] [Test News 1 — Source](http://example.com/1)
"""
    result = _make_result(raw_message)

    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is False
    assert any("Hallucinated percentage" in e for e in validation.errors)


def test_validator_hallucinated_large_number(sample_bundle):
    """Test that large numbers not in the bundle are detected as hallucinations."""
    validator = MessageValidator()
    # Bundle has 5000.00, 38000.00, 15000.00 - we're using 42000.00 which is not
    raw_message = """*Market Update*
*6 Jan 2026*

S&P 500 – 5000.00 (1D +1.00%, +50.00 pts)
Dow Jones – 38000.00 (1D +0.50%, +190.00 pts)
Nasdaq – 15000.00 (1D +1.50%, +225.00 pts)

The index hit 42000.00 at one point during trading.

----
*Investor Key Takeaways*
• Bullet 1
• Bullet 2
• Bullet 3

*Key Dates (UTC)*
• Event

*What to Watch Next*
• Watch

*Sources*
[1] [Test News 1 — Source](http://example.com/1)
"""
    result = _make_result(raw_message)

    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is False
    assert any("Hallucinated number" in e for e in validation.errors)


def test_validator_valid_numbers_from_bundle(sample_bundle):
    """Test that numbers from the bundle are accepted."""
    validator = MessageValidator()
    # Using only numbers that exist in the bundle
    raw_message = """*Market Update*
*6 Jan 2026*

S&P 500 – 5000.00 (1D +1.00%, +50.00 pts)
Dow Jones – 38000.00 (1D +0.50%, +190.00 pts)
Nasdaq – 15000.00 (1D +1.50%, +225.00 pts)

The S&P 500 closed at 5000.00, up 1.00% for the day.

----
*Investor Key Takeaways*
• S&P gained +50.00 pts
• Dow added +190.00 pts
• Nasdaq up +225.00 pts

*Key Dates (UTC)*
• Event

*What to Watch Next*
• Watch

*Sources*
[1] [Test News 1 — Source](http://example.com/1)
"""
    result = _make_result(raw_message)

    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is True
    assert not validation.errors


def test_validator_unbalanced_bold_markers(sample_bundle):
    """Test that unbalanced bold markers are detected."""
    validator = MessageValidator()
    raw_message = """*Market Update*
*6 Jan 2026*

S&P 500 – 5000.00 (1D +1.00%, +50.00 pts)
Dow Jones – 38000.00 (1D +0.50%, +190.00 pts)
Nasdaq – 15000.00 (1D +1.50%, +225.00 pts)

Some *unbalanced bold

----
*Investor Key Takeaways*
• Bullet 1
• Bullet 2
• Bullet 3

*Key Dates (UTC)*
• Event

*What to Watch Next*
• Watch

*Sources*
[1] [Test News 1 — Source](http://example.com/1)
"""
    result = _make_result(raw_message)

    validation = validator.validate(result, sample_bundle)
    assert validation.is_valid is False
    assert any("Unbalanced bold markers" in e for e in validation.errors)
