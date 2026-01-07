"""Risk score calculator for monday_preview conditional publishing.

Implements the risk_score formula from spec.md:
  risk_score = min(100, calendar_score + market_score + headline_score)

Each component has specific scoring rules:
  - calendar_score (0-60): Based on upcoming economic events
  - market_score (0-30): Based on VIX, S&P 500, and US10Y
  - headline_score (0-30): Based on high-impact recent news
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
import logging

from psycopg2.extensions import connection as Connection

from argus.adapters.economic_calendar.repository import get_upcoming_events
from argus.adapters.market_data import HistoricalMetrics, MarketDataProvider
from argus.orchestrator.types import RiskScoreBreakdown

logger = logging.getLogger(__name__)

# Calendar score point values by event type
CALENDAR_SCORE_RULES: dict[str, tuple[list[str], int]] = {
    # (keywords in title, points)
    "central_bank": (
        ["fomc", "fed decision", "rate decision", "federal reserve", "policy decision"],
        25,
    ),
    "inflation": (["cpi", "pce", "inflation", "consumer price"], 20),
    "jobs": (["nonfarm", "payrolls", "unemployment", "jobs report", "employment"], 15),
    "gdp_ism": (["gdp", "ism", "pmi", "manufacturing", "services"], 10),
    "treasury": (["treasury auction", "bond auction", "note auction", "bill auction"], 8),
}

# Political/geopolitical keywords (15 pts)
POLITICAL_KEYWORDS = [
    "election",
    "impeachment",
    "shutdown",
    "debt ceiling",
    "geopolitical",
    "sanctions",
    "war",
    "conflict",
]

# High-impact topics for headline_score
HIGH_IMPACT_TOPICS = {"geopolitics", "systemic", "policy", "credit"}


@dataclass
class CalendarScoreDetails:
    """Detailed breakdown of calendar score."""

    events_checked: int = 0
    central_bank_pts: int = 0
    inflation_pts: int = 0
    jobs_pts: int = 0
    gdp_ism_pts: int = 0
    treasury_pts: int = 0
    political_pts: int = 0
    earnings_pts: int = 0  # Cap at 24 (3 mega-cap earnings × 8)
    matched_events: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total calendar score, capped at 60."""
        raw = (
            self.central_bank_pts
            + self.inflation_pts
            + self.jobs_pts
            + self.gdp_ism_pts
            + self.treasury_pts
            + self.political_pts
            + self.earnings_pts
        )
        return min(60, raw)


@dataclass
class MarketScoreDetails:
    """Detailed breakdown of market score."""

    vix_pts: int = 0
    sp500_pts: int = 0
    us10y_pts: int = 0
    vix_level: Optional[Decimal] = None
    sp500_5d_return: Optional[Decimal] = None
    us10y_5d_move_bps: Optional[Decimal] = None

    @property
    def total(self) -> int:
        """Total market score, capped at 30."""
        return min(30, self.vix_pts + self.sp500_pts + self.us10y_pts)


@dataclass
class HeadlineScoreDetails:
    """Detailed breakdown of headline score."""

    high_impact_count: int = 0
    matching_items: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total headline score: 10 pts per high-impact item, capped at 30."""
        return min(30, self.high_impact_count * 10)


def calculate_calendar_score(
    conn: Connection,
    window_start: datetime,
    window_end: datetime,
) -> CalendarScoreDetails:
    """Calculate calendar score from upcoming economic events.

    Args:
        conn: Database connection.
        window_start: Start of the calendar window.
        window_end: End of the calendar window.

    Returns:
        CalendarScoreDetails with breakdown.
    """
    details = CalendarScoreDetails()

    # Extend window to capture week's events for monday_preview
    # Look from now to 5 trading days ahead
    now = datetime.now(timezone.utc)
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)

    # For monday_preview, look at the upcoming week's events
    # Extend end to cover 5 business days
    extended_end = window_end + timedelta(days=7)

    try:
        events = get_upcoming_events(
            conn,
            start_time=now,
            end_time=extended_end,
            countries=["USD"],  # Focus on US events
            impact_filter=["High"],  # Only high impact
        )
    except Exception as e:
        logger.error(f"Failed to fetch calendar events: {e}")
        return details

    details.events_checked = len(events)

    for event in events:
        title_lower = event.title.lower()
        matched = False

        # Check each scoring category
        for category, (keywords, points) in CALENDAR_SCORE_RULES.items():
            if any(kw in title_lower for kw in keywords):
                matched = True
                if category == "central_bank" and details.central_bank_pts == 0:
                    details.central_bank_pts = points
                    details.matched_events.append(f"{event.title} (+{points} central_bank)")
                elif category == "inflation" and details.inflation_pts == 0:
                    details.inflation_pts = points
                    details.matched_events.append(f"{event.title} (+{points} inflation)")
                elif category == "jobs" and details.jobs_pts == 0:
                    details.jobs_pts = points
                    details.matched_events.append(f"{event.title} (+{points} jobs)")
                elif category == "gdp_ism" and details.gdp_ism_pts < 10:
                    details.gdp_ism_pts = points
                    details.matched_events.append(f"{event.title} (+{points} gdp/ism)")
                elif category == "treasury" and details.treasury_pts < 8:
                    details.treasury_pts = points
                    details.matched_events.append(f"{event.title} (+{points} treasury)")

        # Check for political/geopolitical events
        if any(kw in title_lower for kw in POLITICAL_KEYWORDS):
            if details.political_pts == 0:
                details.political_pts = 15
                details.matched_events.append(f"{event.title} (+15 political)")
                matched = True

        if not matched:
            logger.debug(f"Calendar event not scored: {event.title}")

    logger.info(
        f"Calendar score: {details.total} from {details.events_checked} events "
        f"({len(details.matched_events)} matched)"
    )
    return details


def calculate_market_score(
    historical: Optional[HistoricalMetrics] = None,
    provider: Optional[MarketDataProvider] = None,
) -> MarketScoreDetails:
    """Calculate market score from VIX, S&P 500, and US10Y.

    Uses the formula from spec.md:
    - VIX >= 20: +10, >= 25: +20, >= 30: +30
    - S&P 500 5D return <= -3%: +10, <= -5%: +20
    - US10Y 5D abs move >= 20 bps: +8, >= 30 bps: +12

    Args:
        historical: Pre-fetched historical metrics (preferred).
        provider: MarketDataProvider to fetch data if historical not provided.

    Returns:
        MarketScoreDetails with breakdown.
    """
    details = MarketScoreDetails()

    # Fetch historical data if not provided
    if historical is None:
        if provider is None:
            provider = MarketDataProvider(include_cross_assets=True)
        try:
            historical = provider.fetch_historical(days=7)
        except Exception as e:
            logger.error(f"Failed to fetch historical market data: {e}")
            return details

    # VIX scoring
    if historical.vix_current is not None:
        details.vix_level = historical.vix_current
        vix = float(historical.vix_current)
        if vix >= 30:
            details.vix_pts = 30
        elif vix >= 25:
            details.vix_pts = 20
        elif vix >= 20:
            details.vix_pts = 10
        logger.debug(f"VIX: {vix:.2f} -> {details.vix_pts} pts")

    # S&P 500 5D return scoring
    if historical.sp500_5d_return_pct is not None:
        details.sp500_5d_return = historical.sp500_5d_return_pct
        ret = float(historical.sp500_5d_return_pct)
        if ret <= -5:
            details.sp500_pts = 20
        elif ret <= -3:
            details.sp500_pts = 10
        logger.debug(f"S&P 500 5D return: {ret:.2f}% -> {details.sp500_pts} pts")

    # US10Y 5D move scoring
    if historical.us10y_5d_move_bps is not None:
        details.us10y_5d_move_bps = historical.us10y_5d_move_bps
        move = float(historical.us10y_5d_move_bps)
        if move >= 30:
            details.us10y_pts = 12
        elif move >= 20:
            details.us10y_pts = 8
        logger.debug(f"US10Y 5D move: {move:.1f} bps -> {details.us10y_pts} pts")

    logger.info(
        f"Market score: {details.total} "
        f"(VIX={details.vix_pts}, SP500={details.sp500_pts}, US10Y={details.us10y_pts})"
    )
    return details


def calculate_headline_score(
    conn: Connection,
    window_start: datetime,
    window_end: datetime,
    impact_threshold: int = 80,
) -> HeadlineScoreDetails:
    """Calculate headline score from high-impact recent news.

    Each high-impact news item (impact>=80, topic in high-impact set)
    contributes 10 points, capped at 30.

    Args:
        conn: Database connection.
        window_start: Start of the news window.
        window_end: End of the news window.
        impact_threshold: Minimum impact_score to consider.

    Returns:
        HeadlineScoreDetails with breakdown.
    """
    details = HeadlineScoreDetails()

    # Ensure timezone-aware
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)

    # Query high-impact news items with relevant topics
    query = """
        SELECT ni.id, ni.title, ns.impact_score, ns.topic
        FROM news_items ni
        JOIN news_scores ns ON ni.id = ns.news_item_id 
            AND ni.ingested_at = ns.ingested_at
        WHERE ni.ingested_at >= %s
          AND ni.ingested_at <= %s
          AND ns.impact_score >= %s
        ORDER BY ns.impact_score DESC
        LIMIT 50
    """

    try:
        with conn.cursor() as cur:
            cur.execute(query, (window_start, window_end, impact_threshold))
            rows = cur.fetchall()

        for row in rows:
            item_id, title, impact_score, topic = row

            # Check if topic is high-impact
            if topic and topic.lower() in HIGH_IMPACT_TOPICS:
                details.high_impact_count += 1
                details.matching_items.append(f"[{impact_score}] {topic}: {title[:60]}...")

                # Cap at 3 items (30 points)
                if details.high_impact_count >= 3:
                    break

    except Exception as e:
        logger.error(f"Failed to query headline news: {e}")
        return details

    logger.info(
        f"Headline score: {details.total} from {details.high_impact_count} high-impact items"
    )
    return details


def calculate_risk_score(
    conn: Connection,
    window_start: datetime,
    window_end: datetime,
    historical_metrics: Optional[HistoricalMetrics] = None,
    market_provider: Optional[MarketDataProvider] = None,
) -> RiskScoreBreakdown:
    """Calculate complete risk score for monday_preview.

    Combines calendar_score, market_score, and headline_score.

    Args:
        conn: Database connection.
        window_start: Start of the time window.
        window_end: End of the time window.
        historical_metrics: Optional pre-fetched market data.
        market_provider: Optional MarketDataProvider instance.

    Returns:
        RiskScoreBreakdown with all components and details.
    """
    logger.info(f"Calculating risk score for window: {window_start} to {window_end}")

    # Calculate each component
    calendar_details = calculate_calendar_score(conn, window_start, window_end)
    market_details = calculate_market_score(historical_metrics, market_provider)
    headline_details = calculate_headline_score(conn, window_start, window_end)

    # Compile details dict
    details: dict[str, Any] = {
        "calendar": {
            "total": calendar_details.total,
            "events_checked": calendar_details.events_checked,
            "central_bank_pts": calendar_details.central_bank_pts,
            "inflation_pts": calendar_details.inflation_pts,
            "jobs_pts": calendar_details.jobs_pts,
            "gdp_ism_pts": calendar_details.gdp_ism_pts,
            "treasury_pts": calendar_details.treasury_pts,
            "political_pts": calendar_details.political_pts,
            "earnings_pts": calendar_details.earnings_pts,
            "matched_events": calendar_details.matched_events,
        },
        "market": {
            "total": market_details.total,
            "vix_pts": market_details.vix_pts,
            "sp500_pts": market_details.sp500_pts,
            "us10y_pts": market_details.us10y_pts,
            "vix_level": str(market_details.vix_level) if market_details.vix_level else None,
            "sp500_5d_return": (
                str(market_details.sp500_5d_return) if market_details.sp500_5d_return else None
            ),
            "us10y_5d_move_bps": (
                str(market_details.us10y_5d_move_bps) if market_details.us10y_5d_move_bps else None
            ),
        },
        "headline": {
            "total": headline_details.total,
            "high_impact_count": headline_details.high_impact_count,
            "matching_items": headline_details.matching_items,
        },
    }

    breakdown = RiskScoreBreakdown(
        calendar_score=calendar_details.total,
        market_score=market_details.total,
        headline_score=headline_details.total,
        details=details,
    )

    logger.info(
        f"Risk score: {breakdown.total} "
        f"(calendar={breakdown.calendar_score}, market={breakdown.market_score}, "
        f"headline={breakdown.headline_score})"
    )

    return breakdown
