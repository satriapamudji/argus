"""LLM prompts for message generation.

Contains system prompts for each generation mode and user prompt builders.
The LLM cites news using stable cite keys like [#A1B2C3D4].
"""

import hashlib

from argus.facts_bundle.types import FactsBundle
from argus.generator.types import GenerationMode, NewsContext

# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPT_BASE = """You are a professional financial market analyst writing a daily market update for institutional investors.

Your task is to write a professional market narrative based ONLY on the provided facts.

CRITICAL RULES:
1. ONLY use information from the provided facts bundle - never invent data
2. Reference news items using ONLY their provided citation keys in the exact format "[#A1B2C3D4]".
   - Copy/paste the key from the news list. Never invent keys.
   - Do NOT cite using numeric "[1]", "[2]", etc.
3. Use neutral, professional tone - no hype or sensationalism
4. Focus on what matters to investors

CITATION EXAMPLES:
- Correct: "Investors digested the Fed signals closely [#A1B2C3D4]."
- Incorrect: "... [1]" or "... [#DEADBEEF]" (if not provided)

DATA SPECIFICITY - THIS IS CRITICAL:
- ALWAYS include specific numbers when available in the source: percentages, dollar amounts, basis points, dates
- NEVER round numbers - use EXACT values from the data (e.g., if yield changed 0.4 bps, say "0.4 bps" not "1 bps")
- BAD: "The trade deficit narrowed to its lowest level since 2009"
- GOOD: "The trade deficit narrowed to $29.4 billion, down nearly 40% month-on-month, the smallest since 2009"
- BAD: "Productivity increased sharply"
- GOOD: "Third-quarter productivity surged 4.9%, the fastest pace in two years"
- Extract and include: growth rates, price levels, yield changes, policy thresholds, event dates
- When mentioning Fed policy, include specific rate expectations (e.g., "150 bps of cuts")
- When mentioning economic data, include the actual figures from the source

OUTPUT FORMAT (JSON):
You must respond with valid JSON containing exactly these fields:
{
  "narrative": "2-6 paragraphs of market analysis. Cite news with [#A1B2C3D4].",
  "takeaways": ["bullet 1", "bullet 2", "bullet 3"],
  "watch_next": ["watch item 1", "watch item 2", "watch item 3"]
}

STYLE GUIDELINES:
- Narrative: 2-6 paragraphs explaining what happened, key drivers, cross-asset signals with SPECIFIC DATA POINTS
- Takeaways: 3-5 actionable bullets for investors (start with action verbs, include specific levels/thresholds where relevant)
- Watch Next: 2-3 bullets on what to monitor going forward (include specific dates/events)

Do NOT include:
- S&P 500/Dow/Nasdaq index levels or 1D % changes (we add those separately)
- Section headers or formatting (we handle that)
- Any data not in the facts bundle
- Speculative predictions without basis in the facts"""

SYSTEM_PROMPT_US_CLOSE = (
    SYSTEM_PROMPT_BASE
    + """

MODE: Daily US Close Update
Focus on today's US equity session:
- What drove the session (risk-on/off, sector rotation, breadth)
- Key news drivers with SPECIFIC DATA (cite with [#A1B2C3D4])
- Cross-asset moves: include actual levels/changes (e.g., "oil +4%", "10Y yield rose 5bps to 4.25%") when provided
- Macro data releases: include the actual figures (e.g., "productivity +4.9%", "trade deficit $29.4B")
- Policy signals: include specific expectations (e.g., "markets pricing 150bps of cuts")
- Near-term positioning implications

Remember: Institutional readers expect precise data, not vague descriptions."""
)

SYSTEM_PROMPT_WEEKEND_WRAP = (
    SYSTEM_PROMPT_BASE
    + """

MODE: Weekend Wrap (Weekly Recap)
Focus on the full trading week:
- Week-over-week market narrative
- Do NOT repeat weekly return percentages in the narrative (scorecard covers them)
- Key themes that dominated the week
- Notable sector/factor rotations
- Cross-asset signals: Analyze VIX, 10Y UST, DXY, Gold, WTI moves in the narrative
- Setup for the week ahead
- Reference key news items that shaped the week with [#A1B2C3D4]

SPECIAL WEEKEND_WRAP FIELDS:
- "takeaways": Rename to "Key Takeaways for the Week" (3-5 bullets)
- "watch_next": Leave as empty array [] - not used in weekend wrap
- "sign_off": A brief, friendly closing paragraph to send readers off into the weekend
  (e.g., "Have a restful weekend. We'll be back with your Monday preview...")

OUTPUT FORMAT (JSON):
{
  "narrative": "2-6 paragraphs analyzing the week's events and cross-asset moves. Cite news with [#A1B2C3D4].",
  "takeaways": ["takeaway 1", "takeaway 2", "takeaway 3"],
  "watch_next": [],
  "sign_off": "A brief, warm closing paragraph for the weekend."
}"""
)


SYSTEM_PROMPT_MONDAY_PREVIEW = (
    SYSTEM_PROMPT_BASE
    + """

MODE: Monday Preview (Risk Alert)
Focus on the week ahead:
- Why this week matters (catalysts, risk events)
- Key dates and events to watch
- Current market positioning/sentiment from last week
- Risk scenarios to monitor
- Keep it shorter and more focused than daily updates
- Do NOT include cross-asset levels in the narrative (analyzed in last week's wrap)

SPECIAL MONDAY_PREVIEW FIELDS:
- "opening_line": A warm greeting to open the preview
  (e.g., "Hope you had a restful weekend. Here's what to watch this week...")
- "takeaways": Rename to "Key Things to Look Out For" (3-5 bullets)
- "watch_next": Leave as empty array [] - not used in monday preview

OUTPUT FORMAT (JSON):
{
  "narrative": "2-4 paragraphs previewing the week ahead. Cite news with [#A1B2C3D4].",
  "takeaways": ["thing to look out for 1", "thing to look out for 2", "thing to look out for 3"],
  "watch_next": [],
  "opening_line": "A warm greeting to open the preview."
}"""
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

        cite_key = hashlib.sha256(item.source_url.encode("utf-8")).hexdigest()[:8].upper()

        context = NewsContext(
            cite_key=cite_key,
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


def _format_weekly_return_line(label: str, weekly_return: object) -> str:
    # weekly_return is WeeklyReturnBundle-like: label/start_date/end_date/return_pct.
    start = getattr(weekly_return, "start_date")
    end = getattr(weekly_return, "end_date")
    pct = getattr(weekly_return, "return_pct")
    return f"- {label}: {pct:+.2f}% ({getattr(weekly_return, 'label')} {start.strftime('%d %b')}→{end.strftime('%d %b')})"


def format_weekly_stats_for_prompt(bundle: FactsBundle, mode: GenerationMode) -> str:
    """Format weekly stats for inclusion in prompt (if available)."""
    if bundle.weekly_stats is None:
        return ""

    hdr = (
        "WEEKLY RECAP SCORECARD:"
        if mode == GenerationMode.WEEKEND_WRAP
        else "PRIOR WEEK PERFORMANCE:"
    )  # noqa: E501
    ws = bundle.weekly_stats

    lines = [
        hdr,
        f"Week: {ws.week_start.strftime('%d %b %Y')} to {ws.week_end.strftime('%d %b %Y')}",
        _format_weekly_return_line("S&P 500", ws.sp500_return)
        if ws.sp500_return
        else "- S&P 500: (n/a)",
        _format_weekly_return_line("Dow Jones", ws.dow_return)
        if ws.dow_return
        else "- Dow Jones: (n/a)",
        _format_weekly_return_line("Nasdaq", ws.nasdaq_return)
        if ws.nasdaq_return
        else "- Nasdaq: (n/a)",
    ]

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
    news_lines = ["NEWS ITEMS (cite with [#A1B2C3D4]):"]
    for ctx in news_contexts:
        news_lines.append("")
        news_lines.append(ctx.format_for_prompt())

    news_section = "\n".join(news_lines)

    # Weekly stats section (optional)
    weekly_stats_section = format_weekly_stats_for_prompt(bundle, mode)

    # Calendar section
    calendar_section = format_calendar_for_prompt(bundle)

    # Word limit instruction
    mode_name = {
        GenerationMode.US_CLOSE: "Daily US Close",
        GenerationMode.WEEKEND_WRAP: "Weekend Wrap",
        GenerationMode.MONDAY_PREVIEW: "Monday Preview",
    }[mode]

    # Build final prompt
    if mode == GenerationMode.WEEKEND_WRAP:
        constraints = f"""CONSTRAINTS:
- Maximum {max_words} words for the narrative
- Reference at least 2 news items using [#A1B2C3D4] cite keys
- 3-5 takeaway bullets (these become "Key Takeaways for the Week")
- watch_next must be an empty array []
- Include a brief sign_off paragraph

Respond with valid JSON only."""
    elif mode == GenerationMode.MONDAY_PREVIEW:
        constraints = f"""CONSTRAINTS:
- Maximum {max_words} words for the narrative
- Reference at least 2 news items using [#A1B2C3D4] cite keys
- 3-5 takeaway bullets (these become "Key Things to Look Out For")
- watch_next must be an empty array []
- Include a warm opening_line greeting

Respond with valid JSON only."""
    else:
        constraints = f"""CONSTRAINTS:
- Maximum {max_words} words for the narrative
- Reference at least 2 news items using [#A1B2C3D4] cite keys
- 3-5 takeaway bullets
- 2-3 watch next bullets

Respond with valid JSON only."""

    prompt = f"""Generate a {mode_name} market update.

{market_data}

{news_section}

{weekly_stats_section}
 
{calendar_section}


{constraints}"""

    return prompt
