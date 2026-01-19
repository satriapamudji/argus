"""LLM prompts for message generation.

Contains system prompts for each generation mode and user prompt builders.
The LLM cites news using stable cite keys like [#A1B2C3D4].
"""

import hashlib

from argus.facts_bundle.types import (
    CryptoFactsBundle,
    CryptoMarketSnapshotBundle,
    FactsBundle,
)
from argus.generator.types import GenerationMode, NewsContext
from argus.generator.prompts_crypto import (
    format_crypto_user_prompt,
    get_crypto_daily_prompt,
)

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

DATA INTERPRETATION:
- Don't just report numbers — explain what they SIGNAL about market structure
- "Yield +5bps" is data; "real rates +4bps, inflation breakevens unchanged" is interpretation
- When you cite a data point, always answer: "what does this tell us about positioning/flows/mechanics?"

ANTI-CLICHÉ RULES:
- NEVER state the obvious: "stocks rose on optimism", "investors reacted to news"
- NEVER use content-free phrases: "closely watched", "in focus", "key drivers"
- NEVER explain prices with sentiment: "up on hopes", "down on fears"
- INSTEAD: Explain mechanisms, positioning, flows, unintended consequences
- INSTEAD: Connect dots others miss: cross-asset signals, divergences, anomalies

Examples of BAD vs GOOD:
❌ "Tech stocks rose as investors grew optimistic about earnings"
✅ "Tech outperformed despite mixed earnings, suggesting positioning squeeze more than fundamentals"

❌ "The Fed statement was closely watched by market participants"
✅ "The Fed's language shift on 'moderate' vs 'solid' growth suggests data-dependency deepening, increasing near-term volatility risk"

❌ "Yields rose on inflation concerns"
✅ "The 10Y yield's 8bp jump came with real rates +5bp — the inflation narrative masks a growth repricing"

INSIGHT DENSITY:
Each paragraph must contain at least ONE non-obvious insight:
- A specific mechanism (e.g., "gamma hedging flows amplified the move")
- A cross-asset divergence (e.g., "credit spreads tightened despite equity weakness")
- A positioning implication (e.g., "CTA trend followers are now 80% long US equities, leaving room for a deleveraging event")
- A second-order effect (e.g., "higher Treasury term premium is compressing equity valuations via discount rates more than earnings expectations")

OUTPUT FORMAT (JSON):
You must respond with valid JSON containing exactly these fields:
{
  "narrative": "2-6 paragraphs of market analysis. Cite news with [#A1B2C3D4].",
  "takeaways": ["bullet 1", "bullet 2", "bullet 3"],
  "watch_next": ["watch item 1", "watch item 2", "watch item 3"]
}

STYLE GUIDELINES:
- Narrative: 2-6 paragraphs of MECHANISTIC, not descriptive, analysis
  * Describe HOW markets move, not THAT they moved
  * Include SPECIFIC DATA POINTS (exact values, not approximations)
  * Show causal chains: X data → Y positioning → Z price action
  * Highlight anomalies, divergences, and non-linear effects
- Takeaways: 3-5 bullets with actionable, non-generic insights
  * Each must have a specific level, threshold, or actionable angle
  * Avoid: "monitor", "watch", "keep an eye on"
  * Prefer: "if X breaks Y, expect Z"
- Watch Next: 2-3 bullets on specific catalysts with binary outcomes

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

Remember: Institutional readers expect precise data, not vague descriptions.

EXAMPLE OUTPUT (learn the style):
{
  "narrative": "Today's 0.8% S&P gain masks a significant rotation: cyclical value outperformed growth by 280bp, the widest spread since March. This wasn't broad optimism — defensive sectors barely participated, suggesting capital is staying invested but becoming more selective. The 10Y yield's 5bp jump to 4.28% failed to derail growth stocks, indicating investors are discounting a soft landing rather than fearing Fed overtightening. [#A1B2C3D4] Positioning data shows institutional bearishness on crude near a 5-year high, a setup that could amplify price moves if supply risks escalate. Cross-asset tells are nuanced: credit spreads tightened 7bp even as high-beta underperformed, revealing institutional de-risking into strength rather than retail FOMO. [#B2C3D4E5] Third-quarter productivity surged 4.9%, the fastest pace in two years, while unit labor costs fell 1.9% — the first time since 2019 that labor costs declined for two consecutive quarters, supporting the soft-landing narrative. [#C3D4E5F6]",
  "takeaways": [
    "Rotation favors value over growth — if 10Y breaks 4.35%, expect further cyclical outperformance as the reflation trade gains traction",
    "Productivity +4.9% with labor costs -1.9% marks the best disinflationary combo since 2019 — this fundamental backdrop supports higher equity multiples",
    "Crude positioning is extremely crowded short — any supply disruption could force a violent squeeze, pressuring energy costs and breakeven inflation"
  ],
  "watch_next": [
    "Thursday's CPI: core <0.2% MoM would reinforce the disinflation narrative, while >0.3% forces a hawkish Fed repricing",
    "FOMC minutes release Wednesday: look for dots shifting below 4.5% as the most bullish signal for equities since last October"
  ]
}"""
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
}

EXAMPLE OUTPUT (learn the style):
{
  "narrative": "This week's 2.1% S&P advance masked growing fragmentation beneath the surface. Small caps lagged by 180bp while the equal-weight index underperformed the cap-weighted by 140bp — signaling the rally narrowed to mega-cap tech. This wasn't broad risk-on but rather capital becoming more selective, with investors trimming last year's tech winners and reallocating toward value and energy. The 10Y yield's 12bp climb to 4.33% failed to derail growth stocks, suggesting markets are rotating rather than selling off. [#A1B2C3D4] Cross-asset tells reveal nuanced positioning: VIX compressed to 13.2, but gold jumped 2.4% and DXY slipped 0.8% — indicating hedging beneath the surface. Mortgage bonds outperformed Treasuries after policy support signals, highlighting how government intervention can compress spreads and directly influence borrowing costs. [#B2C3D4E5] October trade deficit narrowed to $29.4 billion, down nearly 40% month-on-month and the smallest since 2009, driven by falling imports rather than collapsing exports — a signal that domestic demand is moderating faster than global demand for US goods. [#C3D4E5F6]",
  "takeaways": [
    "Rally concentration in mega-caps is now above the 2021 peak — the top 5 stocks account for 28% of S&P market cap, leaving breadth fragile",
    "Trade deficit at 15-year low with imports falling 40% MoM while exports held steady — domestic demand contraction is real, not just export weakness",
    "Gold's best week since October combined with mortgage spread compression suggests investors are hedging policy risk while positioning for government-driven rate support"
  ],
  "watch_next": [],
  "sign_off": "Markets are not rolling over but rotating into a more selective, policy-driven phase. Have a restful weekend."
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
}

EXAMPLE OUTPUT (learn the style):
{
  "narrative": "This week markets enter a phase where rotation and policy matter more than outright direction, with two binary outcomes that could reset rate expectations. Wednesday's FOMC decision comes with markets pricing just 18bps of cuts by December — meaning any dovish signal will force a rapid repricing. The Fed's Summary of Economic Projections will be scrutinized for dots moving lower; three or more dots dropping below 4.5% would be the most bullish signal for equities since last October. [#A1B2C3D4] Policy expectations remain a key swing factor. Treasury Secretary indicated the President may decide on the next Fed chair around the Davos window on January 19-23, keeping markets sensitive to rate policy headlines. Meanwhile, Thursday's CPI is the make-or-break data point: core <0.2% MoM would reinforce the soft-landing narrative, while >0.3% would force a hawkish repricing. Positioning is asymmetric — institutional bearishness on crude is near a 5-year high, a setup that could amplify price moves if supply risks escalate. [#B2C3D4E5]",
  "takeaways": [
    "Wednesday FOMC: dots shifting below 4.5% would signal a policy pivot, forcing a rapid repricing of rate cut expectations from current 18bps to 75bps+",
    "Davos window January 19-23: Fed chair decision announcement could trigger volatility — markets are pricing continuity but any surprise candidate would reset expectations",
    "Thursday CPI: core print above 0.3% MoM forces a hawkish Fed repricing, with S&P downside to 4,300 support as the soft-landing narrative fractures"
  ],
  "watch_next": [],
  "opening_line": "Hope you had a restful weekend. This week brings a Fed decision and CPI data that could shift markets from rotation to regime change."
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
        GenerationMode.CRYPTO_DAILY: get_crypto_daily_prompt(),
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
            impact_score=item.impact_score,
        )
        contexts.append(context)

    return contexts


def format_market_data_for_prompt(bundle: FactsBundle | CryptoFactsBundle) -> str:
    """Format market snapshot data for inclusion in prompt.

    Args:
        bundle: The facts bundle.

    Returns:
        Formatted market data string.
    """
    snapshot = bundle.market_snapshot

    # Check if this is a crypto bundle
    if isinstance(snapshot, CryptoMarketSnapshotBundle):
        lines = [
            "MARKET DATA:",
            f"Trading Date: {bundle.trading_date.strftime('%d %b %Y')}",
            "",
            "Crypto Performance (1D):",
            f"- BTC: ${snapshot.btc.price_usd} ({snapshot.btc.change_1d_pct:+}%)",
            f"- ETH: ${snapshot.eth.price_usd} ({snapshot.eth.change_1d_pct:+}%)",
        ]

        # Add major alts
        if snapshot.major_alts:
            lines.append("")
            lines.append("Major Alts:")
            for alt in snapshot.major_alts[:5]:  # Top 5
                lines.append(f"- {alt.symbol}: ${alt.price_usd} ({alt.change_1d_pct:+}%)")

        # Add crypto metrics if available
        if snapshot.crypto_metrics:
            metrics = snapshot.crypto_metrics
            lines.append("")
            lines.append("Market Metrics:")
            if metrics.total_market_cap:
                lines.append(f"- Total Market Cap: ${float(metrics.total_market_cap) / 1e9:.1f}B")
            if metrics.btc_dominance:
                lines.append(f"- BTC Dominance: {float(metrics.btc_dominance):.1f}%")
            if metrics.fear_greed_index:
                lines.append(f"- Fear & Greed Index: {metrics.fear_greed_index}/100")

        # Add DeFi TVL if available
        if snapshot.defi_tvl:
            defi = snapshot.defi_tvl
            lines.append("")
            lines.append("DeFi TVL:")
            lines.append(f"- Total: ${float(defi.total_tvl_usd) / 1e9:.1f}B")

        return "\n".join(lines)

    # US Markets bundle
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


def format_weekly_stats_for_prompt(bundle: FactsBundle | CryptoFactsBundle, mode: GenerationMode) -> str:
    """Format weekly stats for inclusion in prompt (if available)."""
    # Crypto bundles don't have weekly stats
    if isinstance(bundle, CryptoFactsBundle):
        return ""
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


def format_calendar_for_prompt(bundle: FactsBundle | CryptoFactsBundle) -> str:
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


def _classify_fear_greed(value: int) -> str:
    """Classify Fear & Greed Index value into text description."""
    if value >= 75:
        return "Extreme Greed"
    elif value >= 60:
        return "Greed"
    elif value >= 45:
        return "Neutral"
    elif value >= 25:
        return "Fear"
    else:
        return "Extreme Fear"


def _format_crypto_news_summary(news_contexts: list[NewsContext]) -> str:
    """Format news items for crypto prompt with content, topics, and impact scores.

    Groups news by topic and includes full content excerpts for investor context.

    Args:
        news_contexts: Pre-processed news items with citation keys.

    Returns:
        Formatted news summary string.
    """
    if not news_contexts:
        return "No news items."

    # Group by topic (items without topic go to "General")
    topic_groups: dict[str, list[NewsContext]] = {}
    for ctx in news_contexts:
        topic = ctx.topic or "General"
        if topic not in topic_groups:
            topic_groups[topic] = []
        topic_groups[topic].append(ctx)

    # Topic display order (high-signal topics first)
    topic_order = [
        "protocol_risk",
        "regulation",
        "derivatives",
        "defi",
        "onchain",
        "technical",
        "asset_news",
        "General",
    ]

    lines = []

    for topic in topic_order:
        if topic not in topic_groups:
            continue

        items = topic_groups[topic]
        # Sort by impact score descending
        items.sort(key=lambda c: c.impact_score or 0, reverse=True)

        # Topic header
        topic_display = topic.replace("_", " ").upper()
        lines.append(f"{topic_display}:")
        lines.append("")

        for ctx in items:
            # Impact score badge
            impact_badge = f"[{ctx.impact_score}] " if ctx.impact_score is not None else ""

            # Title line with cite key and impact
            lines.append(f"{impact_badge}[#{ctx.cite_key}] {ctx.title}")

            # Source and date
            source_parts = [ctx.source_name]
            if ctx.published_date:
                source_parts.append(f"({ctx.published_date})")
            lines.append(f"Source: {' '.join(source_parts)}")

            # Content excerpt (prefer full content, fall back to snippet)
            content = ctx.content_excerpt or ctx.snippet or "(no content)"
            # Truncate to 800 chars to keep prompt manageable
            if len(content) > 800:
                content = content[:797] + "..."
            lines.append(f"Content: {content}")
            lines.append("")

    return "\n".join(lines)


def _format_top_movers(bundle: CryptoFactsBundle) -> str:
    """Format top movers from major alts for crypto prompt.

    Shows top 3 gainers and top 3 losers (excluding stablecoins).

    Args:
        bundle: The crypto facts bundle.

    Returns:
        Formatted top movers string (empty if no alts available).
    """
    alts = bundle.market_snapshot.major_alts
    if not alts:
        return ""

    # Sort by 24h change
    sorted_alts = sorted(alts, key=lambda a: float(a.change_1d_pct), reverse=True)

    # Top 3 gainers and losers
    gainers = [a for a in sorted_alts if float(a.change_1d_pct) > 0][:3]
    losers = [a for a in reversed(sorted_alts) if float(a.change_1d_pct) < 0][:3]

    parts = []
    if gainers:
        gainer_strs = [f"{a.symbol} +{float(a.change_1d_pct):.1f}%" for a in gainers]
        parts.append("Top: " + ", ".join(gainer_strs))
    if losers:
        loser_strs = [f"{a.symbol} {float(a.change_1d_pct):.1f}%" for a in losers]
        parts.append("Lagging: " + ", ".join(loser_strs))

    if parts:
        return "Top Movers: " + " | ".join(parts) + "\n"
    return ""


def _format_crypto_derivatives_summary(bundle: CryptoFactsBundle) -> str:
    """Format derivatives data for crypto prompt with interpretations.

    Includes insights about what the derivatives data signals about market positioning.

    Args:
        bundle: The crypto facts bundle.

    Returns:
        Formatted derivatives summary string.
    """
    snapshot = bundle.market_snapshot
    metrics = snapshot.crypto_metrics

    if not metrics:
        return "No derivatives data available."

    lines = []

    # Funding rates with interpretation
    if metrics.funding_rates:
        lines.append("Funding Rates:")
        for symbol, rate in sorted(metrics.funding_rates.items()):
            rate_bps = float(rate) * 10000  # Convert to bps

            # Interpretation based on funding rate level
            if rate_bps > 2:
                signal = "strong long bias — longs paying shorts, overcrowding risk"
            elif rate_bps > 0:
                signal = "mild long bias — fresh long positioning entering"
            elif rate_bps < -2:
                signal = "strong short bias — shorts paying longs, flushout risk"
            else:
                signal = "neutral positioning"

            lines.append(f"  {symbol}: {rate_bps:+.1f} bps — {signal}")

    # Open interest with interpretation
    if metrics.open_interest:
        if lines:
            lines.append("")
        lines.append("Open Interest:")

        for symbol, oi in sorted(metrics.open_interest.items()):
            oi_billion = float(oi) / 1e9
            # Only show if significant (> $100M)
            if oi_billion > 0.1:
                # Interpretation based on absolute OI level
                if oi_billion > 10:
                    signal = "high liquidity — deep derivatives market"
                elif oi_billion > 5:
                    signal = "active derivatives market — good liquidity"
                else:
                    signal = "moderate derivatives activity"

                lines.append(f"  {symbol}: ${oi_billion:.2f}B — {signal}")

    return "\n".join(lines) if lines else "No derivatives data available."


def build_user_prompt(
    bundle: FactsBundle | CryptoFactsBundle,
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
    # Crypto mode uses specialized prompt formatting
    if mode == GenerationMode.CRYPTO_DAILY and isinstance(bundle, CryptoFactsBundle):
        snapshot = bundle.market_snapshot
        metrics = snapshot.crypto_metrics

        # Extract required parameters for crypto prompt
        news_summary = _format_crypto_news_summary(news_contexts)
        derivatives_summary = _format_crypto_derivatives_summary(bundle)
        top_movers = _format_top_movers(bundle)

        # Get market data values
        btc_price = float(snapshot.btc.price_usd)
        btc_change = float(snapshot.btc.change_1d_pct)
        eth_price = float(snapshot.eth.price_usd)
        eth_change = float(snapshot.eth.change_1d_pct)

        # Total market cap and BTC dominance (with None safety)
        total_mcap = float(metrics.total_market_cap) / 1e9 if metrics and metrics.total_market_cap else 0
        btc_dom = float(metrics.btc_dominance) if metrics and metrics.btc_dominance else 0

        # Fear & Greed (with None safety)
        fear_greed = int(metrics.fear_greed_index) if metrics and metrics.fear_greed_index else 50
        fear_greed_classification = _classify_fear_greed(fear_greed)

        # DeFi TVL
        defi_tvl = float(snapshot.defi_tvl.total_tvl_usd) / 1e9 if snapshot.defi_tvl else 0

        # Trading date
        trading_date = bundle.trading_date.isoformat()

        # Use crypto-specific formatter
        return format_crypto_user_prompt(
            trading_date=trading_date,
            btc_price=btc_price,
            btc_change=btc_change,
            eth_price=eth_price,
            eth_change=eth_change,
            total_mcap=total_mcap,
            btc_dom=btc_dom,
            fear_greed=fear_greed,
            fear_greed_classification=fear_greed_classification,
            news_count=len(news_contexts),
            news_summary=news_summary,
            derivatives_summary=derivatives_summary,
            defi_tvl=defi_tvl,
            top_movers=top_movers,
        )

    # Standard mode: use generic prompt building
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
        GenerationMode.CRYPTO_DAILY: "Crypto Daily",
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
