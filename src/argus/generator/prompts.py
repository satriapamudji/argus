"""LLM prompts for message generation.

Contains system prompts for each generation mode and user prompt builders.
The LLM generates narrative content using [n] references to news items.
"""

from argus.facts_bundle.types import FactsBundle
from argus.generator.types import GenerationMode, NewsContext

# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPT_BASE = """You are a professional financial market analyst writing a daily market update for investors.

Your task is to write a concise, professional market narrative based ONLY on the provided facts.

CRITICAL RULES:
1. ONLY use information from the provided facts bundle - never invent data
2. Reference news items using their [n] numbers (e.g., "[1]", "[2]")
3. Use neutral, professional tone - no hype or sensationalism
4. Focus on what matters to investors
5. Be concise - every word should add value

OUTPUT FORMAT (JSON):
You must respond with valid JSON containing exactly these fields:
{
  "narrative": "2-6 paragraphs of market analysis. Reference news with [n] notation.",
  "takeaways": ["bullet 1", "bullet 2", "bullet 3"],
  "watch_next": ["watch item 1", "watch item 2", "watch item 3"]
}

STYLE GUIDELINES:
- Narrative: 2-6 short paragraphs explaining what happened, key drivers, cross-asset signals
- Takeaways: 3-5 actionable bullets for investors (start with action verbs)
- Watch Next: 2-3 bullets on what to monitor going forward

Do NOT include:
- Index levels or percentage changes (we add those separately)
- Section headers or formatting (we handle that)
- Any data not in the facts bundle
- Speculative predictions without basis in the facts"""

SYSTEM_PROMPT_US_CLOSE = (
    SYSTEM_PROMPT_BASE
    + """

MODE: Daily US Close Update
Focus on today's US equity session:
- What drove the session (risk-on/off, sector rotation, breadth)
- Key news drivers (reference with [n])
- Cross-asset confirmation (rates, USD, oil, gold if available)
- Near-term positioning implications"""
)

SYSTEM_PROMPT_WEEKEND_WRAP = (
    SYSTEM_PROMPT_BASE
    + """

MODE: Weekend Wrap (Weekly Recap)
Focus on the full trading week:
- Week-over-week market narrative
- Key themes that dominated the week
- Notable sector/factor rotations
- Setup for the week ahead
- Reference key news items that shaped the week [n]"""
)

SYSTEM_PROMPT_MONDAY_PREVIEW = (
    SYSTEM_PROMPT_BASE
    + """

MODE: Monday Preview (Risk Alert)
Focus on the week ahead:
- Why this week matters (catalysts, risk events)
- Key dates and events to watch
- Current market positioning/sentiment
- Risk scenarios to monitor
- Keep it shorter and more focused than daily updates"""
)


def get_system_prompt(mode: GenerationMode) -> str:
    """Get the system prompt for a given generation mode.

    Args:
        mode: The generation mode.

    Returns:
        System prompt string.
    """
    prompt_map = {
        GenerationMode.US_CLOSE: SYSTEM_PROMPT_US_CLOSE,
        GenerationMode.WEEKEND_WRAP: SYSTEM_PROMPT_WEEKEND_WRAP,
        GenerationMode.MONDAY_PREVIEW: SYSTEM_PROMPT_MONDAY_PREVIEW,
    }
    return prompt_map[mode]


# =============================================================================
# User Prompt Builder
# =============================================================================


def build_news_contexts(bundle: FactsBundle) -> list[NewsContext]:
    """Build NewsContext list from facts bundle.

    Assigns reference numbers [1], [2], etc. to each news item.

    Args:
        bundle: The facts bundle containing news items.

    Returns:
        List of NewsContext objects with assigned reference numbers.
    """
    contexts = []
    for i, item in enumerate(bundle.news_items, start=1):
        # Format published date
        published_date = None
        if item.published_at:
            published_date = item.published_at.strftime("%d %b %Y")

        context = NewsContext(
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
        contexts.append(context)

    return contexts


def format_market_data_for_prompt(bundle: FactsBundle) -> str:
    """Format market snapshot data for inclusion in prompt.

    Args:
        bundle: The facts bundle.

    Returns:
        Formatted market data string.
    """
    snapshot = bundle.market_snapshot

    lines = [
        "MARKET DATA:",
        f"Trading Date: {bundle.trading_date.strftime('%d %b %Y')}",
        "",
        "Index Performance (1D):",
        f"- S&P 500: {snapshot.sp500.level} ({snapshot.sp500.change_1d_pct:+}%, {snapshot.sp500.change_1d_pts:+} pts)",
        f"- Dow Jones: {snapshot.dow.level} ({snapshot.dow.change_1d_pct:+}%, {snapshot.dow.change_1d_pts:+} pts)",
        f"- Nasdaq: {snapshot.nasdaq.level} ({snapshot.nasdaq.change_1d_pct:+}%, {snapshot.nasdaq.change_1d_pts:+} pts)",
    ]

    # Add cross-asset data if available
    cross = snapshot.cross_assets
    if cross:
        lines.append("")
        lines.append("Cross-Asset:")
        if cross.vix_level is not None:
            vix_chg = f" ({cross.vix_change_pct:+}%)" if cross.vix_change_pct else ""
            lines.append(f"- VIX: {cross.vix_level}{vix_chg}")
        if cross.us10y_yield is not None:
            us10y_chg = f" ({cross.us10y_change_bps:+} bps)" if cross.us10y_change_bps else ""
            lines.append(f"- US 10Y Yield: {cross.us10y_yield}%{us10y_chg}")
        if cross.dxy_level is not None:
            dxy_chg = f" ({cross.dxy_change_pct:+}%)" if cross.dxy_change_pct else ""
            lines.append(f"- DXY: {cross.dxy_level}{dxy_chg}")
        if cross.wti_level is not None:
            wti_chg = f" ({cross.wti_change_pct:+}%)" if cross.wti_change_pct else ""
            lines.append(f"- WTI Oil: ${cross.wti_level}{wti_chg}")
        if cross.gold_level is not None:
            gold_chg = f" ({cross.gold_change_pct:+}%)" if cross.gold_change_pct else ""
            lines.append(f"- Gold: ${cross.gold_level}{gold_chg}")

    return "\n".join(lines)


def format_calendar_for_prompt(bundle: FactsBundle) -> str:
    """Format calendar events for inclusion in prompt.

    Args:
        bundle: The facts bundle.

    Returns:
        Formatted calendar events string.
    """
    if not bundle.calendar_events:
        return "UPCOMING EVENTS:\nNo major events scheduled."

    lines = ["UPCOMING EVENTS:"]
    for event in bundle.calendar_events:
        lines.append(f"- {event.formatted_display}")

    return "\n".join(lines)


def build_user_prompt(
    bundle: FactsBundle,
    news_contexts: list[NewsContext],
    mode: GenerationMode,
    max_words: int,
) -> str:
    """Build the user prompt for the LLM.

    Args:
        bundle: The facts bundle.
        news_contexts: Pre-processed news items with reference numbers.
        mode: Generation mode.
        max_words: Maximum word count for the narrative.

    Returns:
        Complete user prompt string.
    """
    # Market data section
    market_data = format_market_data_for_prompt(bundle)

    # News items section
    news_lines = ["NEWS ITEMS (use [n] to reference):"]
    for ctx in news_contexts:
        news_lines.append("")
        news_lines.append(ctx.format_for_prompt())

    news_section = "\n".join(news_lines)

    # Calendar section
    calendar_section = format_calendar_for_prompt(bundle)

    # Word limit instruction
    mode_name = {
        GenerationMode.US_CLOSE: "Daily US Close",
        GenerationMode.WEEKEND_WRAP: "Weekend Wrap",
        GenerationMode.MONDAY_PREVIEW: "Monday Preview",
    }[mode]

    # Build final prompt
    prompt = f"""Generate a {mode_name} market update.

{market_data}

{news_section}

{calendar_section}

CONSTRAINTS:
- Maximum {max_words} words for the narrative
- Reference at least 2 news items using [n] notation
- 3-5 takeaway bullets
- 2-3 watch next bullets

Respond with valid JSON only."""

    return prompt
