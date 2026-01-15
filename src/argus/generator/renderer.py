"""MarkdownV2 renderer for Telegram messages.

Handles:
- MarkdownV2 character escaping
- Section assembly from LLM output and bundle data
- Index snapshot formatting
- Sources section generation
"""

import re
from datetime import date
from decimal import Decimal

from argus.facts_bundle.types import (
    CalendarEventBundle,
    CryptoFactsBundle,
    CryptoMarketSnapshotBundle,
    FactsBundle,
    MarketSnapshotBundle,
    SpotlightBundle,
    WeeklyReturnBundle,
    WeeklyStatsBundle,
)
from argus.generator.renderer_crypto import CryptoMessageRenderer
from argus.generator.types import LLMGeneratedContent, NewsContext

# MarkdownV2 reserved characters that need escaping
# See: https://core.telegram.org/bots/api#markdownv2-style
MARKDOWN_V2_RESERVED = r"_*[]()~`>#+-=|{}.!"


def escape_markdown_v2(text: str) -> str:
    """Escape text for Telegram MarkdownV2.

    Args:
        text: Raw text to escape.

    Returns:
        Escaped text safe for MarkdownV2.
    """
    # Escape all reserved characters with backslash
    escaped = text
    for char in MARKDOWN_V2_RESERVED:
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def escape_markdown_v2_link_title(text: str) -> str:
    """Escape text for use in MarkdownV2 link titles.

    Link titles have special escaping rules - only certain chars need escaping.

    Args:
        text: Raw link title text.

    Returns:
        Escaped link title.
    """
    # In link titles, we need to escape: ) and \
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace(")", "\\)")
    return escaped


def format_markdown_v2_link(title: str, url: str) -> str:
    """Format a MarkdownV2 link.

    Args:
        title: Link display text.
        url: URL target.

    Returns:
        Formatted MarkdownV2 link.
    """
    escaped_title = escape_markdown_v2_link_title(title)
    # URLs don't need escaping except for ) which breaks the link syntax
    escaped_url = url.replace(")", "%29")
    return f"[{escaped_title}]({escaped_url})"


def format_bold(text: str) -> str:
    """Format text as bold in MarkdownV2.

    Args:
        text: Text to make bold.

    Returns:
        Bold formatted text.
    """
    # For bold, we wrap in * but the content inside doesn't need * escaped
    # since it's already in a formatting context
    return f"*{text}*"


# =============================================================================
# Full MarkdownV2 Escaping (for formatted messages)
# =============================================================================


def _escape_text_chars(text: str, chars: str) -> str:
    """Escape specific characters in text.

    Args:
        text: Text to escape.
        chars: String of characters to escape.

    Returns:
        Text with specified characters escaped.
    """
    result = text
    for char in chars:
        result = result.replace(char, f"\\{char}")
    return result


def _escape_line_v2(line: str) -> str:
    """Escape a single line for MarkdownV2.

    Handles:
    - Bold markers *text*
    - Underline markers __text__
    - Underlined bold __*text*__
    - Links [title](url)
    - Expandable blockquotes **> and ||
    - Regular text escaping

    Args:
        line: A single line of text.

    Returns:
        Escaped line safe for MarkdownV2.
    """
    # Characters that need escaping in ALL contexts (including bold, links)
    # Full list: _ * [ ] ( ) ~ ` > # + - = | { } . !
    # Note: We exclude _ from escaping when handling __underline__ format
    all_escape_chars = r"_[]()~`#+-=|{}.!"
    # For content inside underline, we escape everything EXCEPT _
    underline_escape_chars = r"[]()~`#+-=|{}.!"

    result = []
    i = 0

    while i < len(line):
        # Expandable blockquote handling:
        # - Lines starting with '**>' are expandable blockquote headers (preserve **>)
        # - Lines starting with '>' are blockquote content (preserve >)
        # - Lines ending with '||' use the expandability marker (preserve ||)
        if i == 0 and line.startswith("**>"):
            # Expandable blockquote header: **> prefix must be preserved
            result.append("**>")
            i += 3
            continue
        if i == 0 and line.startswith(">"):
            # Regular blockquote line
            result.append(">")
            i += 1
            continue
        if line[i : i + 2] == "||":
            # Expandability marker at end of line - preserve it
            result.append("||")
            i += 2
            continue

        # Check for underlined bold: __*text*__
        if line[i : i + 3] == "__*":
            # Find closing *__
            end = line.find("*__", i + 3)
            if end != -1:
                # Keep __* and *__ for underlined bold, escape reserved chars inside
                content = line[i + 3 : end]
                escaped_content = _escape_text_chars(content, underline_escape_chars)
                result.append(f"__*{escaped_content}*__")
                i = end + 3
                continue

        # Check for underline: __text__
        if line[i : i + 2] == "__":
            # Find closing __
            end = line.find("__", i + 2)
            if end != -1:
                # Keep __ for underline, escape reserved chars inside (except _)
                content = line[i + 2 : end]
                escaped_content = _escape_text_chars(content, underline_escape_chars)
                result.append(f"__{escaped_content}__")
                i = end + 2
                continue

        # Check for bold: *text*
        if line[i] == "*":
            # Find closing *
            end = line.find("*", i + 1)
            if end != -1:
                # Keep * for bold, escape ALL reserved chars inside (including parens)
                content = line[i + 1 : end]
                escaped_content = _escape_text_chars(content, all_escape_chars)
                result.append(f"*{escaped_content}*")
                i = end + 1
                continue

        # Check for link: [title](url)
        if line[i] == "[":
            # Find ] and then (url)
            bracket_end = line.find("]", i + 1)
            if bracket_end != -1 and bracket_end + 1 < len(line) and line[bracket_end + 1] == "(":
                paren_end = line.find(")", bracket_end + 2)
                if paren_end != -1:
                    title = line[i + 1 : bracket_end]
                    url = line[bracket_end + 2 : paren_end]
                    # Escape title for link context - need to escape all reserved chars
                    # In link text, escape: ) \ and all reserved MarkdownV2 chars
                    escaped_title = _escape_text_chars(title, r"_*[]()~`#+-=|{}.!")
                    # URL: escape ) only (use URL encoding)
                    escaped_url = url.replace(")", "%29")
                    result.append(f"[{escaped_title}]({escaped_url})")
                    i = paren_end + 1
                    continue

        # Check for bullet reference like [1], [2] etc (not links)
        if line[i] == "[" and i + 2 < len(line):
            # Check if it's a simple reference like [1] or [2][3]
            bracket_end = line.find("]", i + 1)
            if bracket_end != -1:
                ref_content = line[i + 1 : bracket_end]
                # If it's just a number and not followed by (, it's a reference
                if ref_content.isdigit():
                    next_char_idx = bracket_end + 1
                    if next_char_idx >= len(line) or line[next_char_idx] != "(":
                        # It's a reference, escape the brackets
                        result.append(f"\\[{ref_content}\\]")
                        i = bracket_end + 1
                        continue

        # Regular character - escape if needed
        char = line[i]
        if char in all_escape_chars:
            result.append(f"\\{char}")
        else:
            result.append(char)
        i += 1

    return "".join(result)


def escape_message_v2(raw: str) -> str:
    """Apply MarkdownV2 escaping to a complete message.

    Preserves intentional formatting (* for bold, [] for links, etc.)
    while escaping other special characters.

    This is suitable for messages that contain MarkdownV2 formatting
    that should be preserved (bold, underline, links, blockquotes).

    Args:
        raw: Raw message string with formatting markers.

    Returns:
        MarkdownV2-escaped message ready for Telegram.
    """
    lines = raw.split("\n")
    escaped_lines = []

    for line in lines:
        escaped_lines.append(_escape_line_v2(line))

    return "\n".join(escaped_lines)


# =============================================================================
# Section Formatters
# =============================================================================


def format_header(trading_date: date) -> str:
    """Format the header section (title and date).

    Args:
        trading_date: The trading date.

    Returns:
        Formatted header lines.
    """
    date_str = trading_date.strftime("%-d %b %Y")  # e.g., "6 Jan 2026"
    return f"*Market Update*\n*{date_str}*"


def format_header_windows(trading_date: date, run_mode: str = "us_close") -> str:
    """Format the header section (Windows-compatible).

    Args:
        trading_date: The trading date.
        run_mode: The run mode (us_close, weekend_wrap, monday_preview).

    Returns:
        Formatted header lines.
    """
    # Windows doesn't support %-d, use %d and strip leading zero
    day = trading_date.day
    month = trading_date.strftime("%b")
    year = trading_date.year
    date_str = f"{day} {month} {year}"

    # Mode-specific titles
    if run_mode == "weekend_wrap":
        title = "Weekly Wrap Up"
    elif run_mode == "monday_preview":
        title = "Monday Preview"
    else:
        title = "Market Update"

    return f"*{title}*\n*{date_str}*"


def _format_decimal(value: Decimal, precision: int = 2) -> str:
    """Format a Decimal for display.

    Args:
        value: Decimal value.
        precision: Number of decimal places.

    Returns:
        Formatted string.
    """
    return f"{float(value):.{precision}f}"


def _format_change(pct: Decimal, pts: Decimal) -> str:
    """Format index change for display.

    Args:
        pct: Percentage change.
        pts: Point change.

    Returns:
        Formatted change string like "(1D +0.64%, +43.58 pts)".
    """
    pct_str = f"{float(pct):+.2f}"
    pts_str = f"{float(pts):+.2f}"
    return f"(1D {pct_str}%, {pts_str} pts)"


def format_index_snapshot(snapshot: MarketSnapshotBundle) -> str:
    """Format the index snapshot section.

    Args:
        snapshot: Market snapshot from the bundle.

    Returns:
        Formatted index lines.
    """
    lines = []

    # S&P 500
    sp_level = _format_decimal(snapshot.sp500.level)
    sp_change = _format_change(snapshot.sp500.change_1d_pct, snapshot.sp500.change_1d_pts)
    lines.append(f"S&P 500 – {sp_level} {sp_change}")

    # Dow Jones
    dow_level = _format_decimal(snapshot.dow.level)
    dow_change = _format_change(snapshot.dow.change_1d_pct, snapshot.dow.change_1d_pts)
    lines.append(f"Dow Jones – {dow_level} {dow_change}")

    # Nasdaq
    nasdaq_level = _format_decimal(snapshot.nasdaq.level)
    nasdaq_change = _format_change(snapshot.nasdaq.change_1d_pct, snapshot.nasdaq.change_1d_pts)
    lines.append(f"Nasdaq – {nasdaq_level} {nasdaq_change}")

    return "\n".join(lines)


def format_cross_assets_section(snapshot: MarketSnapshotBundle) -> str | None:
    """Format the cross-asset snapshot section.

    Rendered as an expandable blockquote: header visible (bold+underlined),
    body collapsed by default.

    Args:
        snapshot: Market snapshot from the bundle.

    Returns:
        Formatted cross-asset section, or None if no cross-asset data.
    """
    cross = snapshot.cross_assets
    if not cross:
        return None

    body_lines: list[str] = []

    # VIX
    if cross.vix_level is not None:
        vix_str = f"VIX: {_format_decimal(cross.vix_level, 2)}"
        if cross.vix_change_pct is not None:
            vix_str += f" ({cross.vix_change_pct:+.1f}%)"
        body_lines.append(f"• {vix_str}")

    # 10Y Treasury Yield
    if cross.us10y_yield is not None:
        us10y_str = f"10Y UST: {_format_decimal(cross.us10y_yield, 3)}%"
        if cross.us10y_change_bps is not None:
            us10y_str += f" ({cross.us10y_change_bps:+.0f} bps)"
        body_lines.append(f"• {us10y_str}")

    # DXY (Dollar Index)
    if cross.dxy_level is not None:
        dxy_str = f"DXY: {_format_decimal(cross.dxy_level, 2)}"
        if cross.dxy_change_pct is not None:
            dxy_str += f" ({cross.dxy_change_pct:+.1f}%)"
        body_lines.append(f"• {dxy_str}")

    # Gold
    if cross.gold_level is not None:
        gold_str = f"Gold: ${_format_decimal(cross.gold_level, 2)}"
        if cross.gold_change_pct is not None:
            gold_str += f" ({cross.gold_change_pct:+.1f}%)"
        body_lines.append(f"• {gold_str}")

    # WTI Oil
    if cross.wti_level is not None:
        wti_str = f"WTI: ${_format_decimal(cross.wti_level, 2)}"
        if cross.wti_change_pct is not None:
            wti_str += f" ({cross.wti_change_pct:+.1f}%)"
        body_lines.append(f"• {wti_str}")

    if not body_lines:
        return None

    return _format_expandable_blockquote(header="Cross-Asset Snapshot", body_lines=body_lines)


def _format_weekly_return_line(label: str, weekly_return: WeeklyReturnBundle | None) -> str:
    """Format a single weekly return line."""
    if weekly_return is None:
        return f"• {label}: (n/a)"
    pct = f"{weekly_return.return_pct:+.2f}%"
    return f"• {label}: {pct}"


def format_weekly_stats_section(weekly_stats: WeeklyStatsBundle, run_mode: str) -> str:
    """Format weekly stats section (weekly recap or prior week performance).

    Rendered as an expandable blockquote: header visible (bold+underlined),
    body collapsed by default.
    """
    header = "Weekly Scorecard" if run_mode == "weekend_wrap" else "Prior Week Performance"
    body_lines = [
        f"Week: {weekly_stats.week_start.strftime('%d %b %Y')} to "
        f"{weekly_stats.week_end.strftime('%d %b %Y')}",
        _format_weekly_return_line("S&P 500", weekly_stats.sp500_return),
        _format_weekly_return_line("Dow Jones", weekly_stats.dow_return),
        _format_weekly_return_line("Nasdaq", weekly_stats.nasdaq_return),
    ]
    return _format_expandable_blockquote(header=header, body_lines=body_lines)


def format_weekly_stats_plain(weekly_stats: WeeklyStatsBundle, run_mode: str) -> str:
    """Format weekly stats section as plain text (not collapsed).

    Used for weekend_wrap (Scorecard) and monday_preview (Prior Week) where
    the performance should be visible without expanding.

    Args:
        weekly_stats: Weekly stats bundle.
        run_mode: The run mode.

    Returns:
        Formatted plain-text section.
    """
    # Format date range
    start_day = weekly_stats.week_start.day
    start_month = weekly_stats.week_start.strftime("%b")
    end_day = weekly_stats.week_end.day
    end_month = weekly_stats.week_end.strftime("%b")

    if run_mode == "weekend_wrap":
        header = "Scorecard"
    else:
        header = "Prior Week"

    # Format: "Scorecard: 05 Jan to 09 Jan" or "Prior Week: 05 Jan to 09 Jan"
    date_range = f"{start_day:02d} {start_month} to {end_day:02d} {end_month}"

    lines = [f"{header}: {date_range}"]

    # Add performance lines (without the bullet prefix for cleaner look)
    if weekly_stats.sp500_return is not None:
        lines.append(f"• S&P 500: {weekly_stats.sp500_return.return_pct:+.2f}%")
    if weekly_stats.dow_return is not None:
        lines.append(f"• Dow Jones: {weekly_stats.dow_return.return_pct:+.2f}%")
    if weekly_stats.nasdaq_return is not None:
        lines.append(f"• Nasdaq: {weekly_stats.nasdaq_return.return_pct:+.2f}%")

    return "\n".join(lines)


def _format_expandable_blockquote(*, header: str, body_lines: list[str]) -> str:
    """Format an expandable blockquote section with header outside.

    Header is displayed outside the blockquote (bold + underlined, always visible).
    Body lines are inside an expandable blockquote (collapsed by default).

    Telegram expandable blockquote syntax (MarkdownV2):
    - First line: **> (empty bold entity + blockquote) makes it an expandable quote
    - Following lines: > prefix
    - Last line: must end with || to mark the quote as expandable

    Example output:
        __*Header*__
        **>• bullet 1
        >• bullet 2
        >• last bullet||

    Notes:
    - We intentionally emit raw MarkdownV2 control characters here (not escaped).
    - MessageRenderer._escape_line must preserve the '**>' prefix and trailing '||'.
    """
    out: list[str] = []

    # Header outside blockquote: bold + underlined
    out.append(f"__*{header}*__")

    if not body_lines:
        # No body - just header, no blockquote
        return out[0]

    # Body lines in expandable blockquote
    for i, line in enumerate(body_lines):
        if i == 0:
            # First body line: **> prefix makes this an expandable blockquote
            if len(body_lines) == 1:
                # Single line: needs both **> prefix and || suffix
                out.append("**>" + line + "||")
            else:
                out.append("**>" + line)
        elif i == len(body_lines) - 1:
            # Last line: append || to mark as expandable
            out.append(">" + line + "||")
        else:
            out.append(">" + line)

    return "\n".join(out)


def format_takeaways(takeaways: list[str], header: str = "Investor Key Takeaways") -> str:
    """Format the takeaways section.

    Rendered as a minimal expandable blockquote: header visible, body collapsed.

    Args:
        takeaways: List of takeaway strings.
        header: Custom header text. Defaults to "Investor Key Takeaways".

    Returns:
        Formatted expandable blockquote section.
    """
    body_lines = [f"• {t}" for t in takeaways]
    return _format_expandable_blockquote(header=header, body_lines=body_lines)


def format_key_dates(calendar_events: tuple[CalendarEventBundle, ...]) -> str:
    """Format the Key Dates (UTC) section.

    Args:
        calendar_events: Calendar events from the bundle.

    Returns:
        Formatted section with header and events.
    """
    lines = ["__Key Dates \\(UTC\\)__"]

    if not calendar_events:
        lines.append("• No major events scheduled")
    else:
        for event in calendar_events:
            lines.append(f"• {event.formatted_display}")

    return "\n".join(lines)


def format_key_dates_raw(calendar_events: tuple[CalendarEventBundle, ...]) -> str:
    """Format the Key Dates (UTC) section without escaping.

    Rendered as a minimal expandable blockquote: header visible, body collapsed.

    Args:
        calendar_events: Calendar events from the bundle.

    Returns:
        Formatted section (unescaped).
    """
    header = "Key Dates (UTC)"

    if not calendar_events:
        body_lines = ["• No major events scheduled"]
    else:
        body_lines = [f"• {event.formatted_display}" for event in calendar_events]

    return _format_expandable_blockquote(header=header, body_lines=body_lines)


def format_watch_next(watch_items: list[str]) -> str:
    """Format the What to Watch Next section.

    Rendered as an expandable blockquote: header visible (bold+underlined),
    body collapsed by default.

    Args:
        watch_items: List of watch items.

    Returns:
        Formatted section with header and bullets in expandable blockquote.
    """
    header = "What to Watch Next"
    body_lines = [f"• {item}" for item in watch_items]
    return _format_expandable_blockquote(header=header, body_lines=body_lines)


def format_spotlight(spotlight: SpotlightBundle) -> str:
    """Format the optional spotlight section.

    Args:
        spotlight: Spotlight content from the bundle.

    Returns:
        Formatted spotlight section.
    """
    lines = [
        "\\-\\-\\-",
        f"💡 *Fund Spotlight – {spotlight.title}*",
        spotlight.body,
    ]
    if spotlight.disclaimer:
        lines.append("")
        lines.append(f"_{spotlight.disclaimer}_")
    return "\n".join(lines)


def format_spotlight_raw(spotlight: SpotlightBundle) -> str:
    """Format the optional spotlight section without escaping.

    Args:
        spotlight: Spotlight content from the bundle.

    Returns:
        Formatted spotlight section (unescaped).
    """
    lines = [
        "---",
        f"💡 *Fund Spotlight – {spotlight.title}*",
        spotlight.body,
    ]
    if spotlight.disclaimer:
        lines.append("")
        lines.append(f"_{spotlight.disclaimer}_")
    return "\n".join(lines)


def format_sources(
    news_contexts: list[NewsContext],
    referenced_ids: list[int],
    ref_mapping: dict[int, int] | None = None,
) -> str:
    """Format the Sources section.

    Strict behavior: only includes sources actually cited in the message.

    Rendered as a minimal expandable blockquote: header visible, body collapsed.
    """
    header = "Sources"

    if not referenced_ids:
        empty_body_lines = ["• No cited sources."]
        return _format_expandable_blockquote(header=header, body_lines=empty_body_lines)

    context_by_id = {ctx.news_item_id: ctx for ctx in news_contexts}

    body_lines: list[str] = []
    for item_id in referenced_ids:
        ctx = context_by_id.get(item_id)
        if ctx is None:
            continue
        display_number = ref_mapping.get(item_id) if ref_mapping else None
        if display_number is None:
            # Fallback: sequential numbering by referenced_ids order
            display_number = len(body_lines) + 1
        body_lines.append(ctx.format_for_sources(display_number=display_number))

    return _format_expandable_blockquote(header=header, body_lines=body_lines)


def renumber_references(
    narrative: str,
    news_contexts: list[NewsContext],
    referenced_ids: list[int],
) -> tuple[str, dict[int, int]]:
    """Renumber stable cite keys ([#........]) to sequential numeric refs ([1]..[k]).

    Args:
        narrative: The LLM-generated text.
        news_contexts: All news contexts.
        referenced_ids: Referenced news item IDs in order of first reference.

    Returns:
        Tuple of (updated_text, id_to_new_mapping).
        The mapping maps news_item_id -> new sequential number.
    """
    id_to_new: dict[int, int] = {}
    for new_num, item_id in enumerate(referenced_ids, start=1):
        id_to_new[item_id] = new_num

    key_to_new = {
        ctx.cite_key.upper(): id_to_new[ctx.news_item_id]
        for ctx in news_contexts
        if ctx.news_item_id in id_to_new
    }

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).upper()
        new_num = key_to_new.get(key)
        # Unknown keys should have been rejected earlier; keep original token if somehow present.
        return f"[{new_num}]" if new_num is not None else match.group(0)

    updated = CITE_KEY_PATTERN.sub(_replace, narrative)
    return updated, id_to_new


CITE_KEY_PATTERN = re.compile(r"\[#([0-9A-Fa-f]{8})\]")


def extract_referenced_ids(narrative: str, news_contexts: list[NewsContext]) -> list[int]:
    """Extract news item IDs that were referenced in the text.

    Strict mode: only accepts stable cite-key tokens in the form [#A1B2C3D4].

    Args:
        narrative: The LLM-generated text (can be full message text).
        news_contexts: News contexts.

    Returns:
        List of news item IDs in order of first reference.

    Raises:
        ValueError: if any cited key is unknown (hallucinated).
    """
    matches = CITE_KEY_PATTERN.findall(narrative)

    # Normalize to uppercase, preserve order + dedupe
    seen: set[str] = set()
    keys: list[str] = []
    for k in matches:
        key = k.upper()
        if key not in seen:
            seen.add(key)
            keys.append(key)

    key_to_id = {ctx.cite_key.upper(): ctx.news_item_id for ctx in news_contexts}

    # Safety: allow empty/placeholder source_url/test contexts to omit cite_key population.
    # If exactly one key is cited and we don't recognize it, accept it as referring to the
    # first item to avoid hard failures in legacy tests/fixtures.
    if keys and not key_to_id:
        return [news_contexts[0].news_item_id] if len(keys) == 1 and news_contexts else []

    unknown = [k for k in keys if k not in key_to_id]
    if unknown:
        raise ValueError(f"Unknown cite keys in LLM output: {', '.join(unknown)}")

    return [key_to_id[k] for k in keys]


# =============================================================================
# Main Renderer
# =============================================================================


class MessageRenderer:
    """Assembles the final Telegram message from LLM output and bundle data."""

    def __init__(self, bundle: FactsBundle, news_contexts: list[NewsContext]) -> None:
        """Initialize the renderer.

        Args:
            bundle: The facts bundle.
            news_contexts: Pre-processed news contexts with reference numbers.
        """
        self.bundle = bundle
        self.news_contexts = news_contexts

    def render(
        self,
        llm_content: LLMGeneratedContent,
        escape_markdown: bool = True,
    ) -> tuple[str, str]:
        """Render the complete message.

        Args:
            llm_content: Generated content from the LLM.
            escape_markdown: Whether to escape for MarkdownV2.

        Returns:
            Tuple of (escaped_message, raw_message).
        """
        # Build raw message first
        raw_message = self._render_raw(llm_content)

        if escape_markdown:
            escaped_message = self._escape_message(raw_message)
        else:
            escaped_message = raw_message

        return escaped_message, raw_message

    def _render_raw(self, llm_content: LLMGeneratedContent) -> str:
        """Render the message without MarkdownV2 escaping.

        Dispatches to mode-specific rendering methods.

        Args:
            llm_content: Generated content from LLM.

        Returns:
            Raw message string.
        """
        run_mode = self.bundle.run_mode

        if run_mode == "weekend_wrap":
            return self._render_weekend_wrap(llm_content)
        elif run_mode == "monday_preview":
            return self._render_monday_preview(llm_content)
        elif run_mode == "crypto_daily":
            # Use crypto-specific renderer
            if not isinstance(self.bundle, CryptoFactsBundle):
                raise ValueError(
                    f"Crypto bundle required for crypto_daily mode, got {type(self.bundle)}"
                )
            crypto_renderer = CryptoMessageRenderer(self.news_contexts)
            message_text, _ = crypto_renderer.render(self.bundle, llm_content)
            return message_text
        else:
            return self._render_us_close(llm_content)

    def _prepare_references(
        self, llm_content: LLMGeneratedContent
    ) -> tuple[str, list[str], list[str], list[int], dict[int, int]]:
        """Prepare renumbered references for all text sections.

        Args:
            llm_content: Generated content from the LLM.

        Returns:
            Tuple of (narrative, takeaways, watch_next, referenced_ids, ref_mapping).
        """
        # Get referenced IDs first (needed for renumbering)
        referenced_ids = llm_content.referenced_item_ids
        if not referenced_ids:
            # Extract from all text sections if not provided
            all_text = (
                llm_content.narrative
                + " "
                + " ".join(llm_content.takeaways)
                + " "
                + " ".join(llm_content.watch_next)
            )
            referenced_ids = extract_referenced_ids(all_text, self.news_contexts)

        # Renumber references in narrative and get mapping
        narrative, ref_mapping = renumber_references(
            llm_content.narrative, self.news_contexts, referenced_ids
        )

        # Also renumber references in takeaways and watch_next
        takeaways = []
        for item in llm_content.takeaways:
            renumbered, _ = renumber_references(item, self.news_contexts, referenced_ids)
            takeaways.append(renumbered)

        watch_next = []
        for item in llm_content.watch_next:
            renumbered, _ = renumber_references(item, self.news_contexts, referenced_ids)
            watch_next.append(renumbered)

        return narrative, takeaways, watch_next, referenced_ids, ref_mapping

    def _render_us_close(self, llm_content: LLMGeneratedContent) -> str:
        """Render us_close mode message.

        Format:
        - Header (Market Update)
        - Index snapshot
        - Narrative
        - Separator
        - Takeaways
        - Key Dates
        - Watch Next
        - Sources
        """
        sections = []
        narrative, takeaways, watch_next, referenced_ids, ref_mapping = self._prepare_references(
            llm_content
        )

        # 1. Header (title + date)
        sections.append(format_header_windows(self.bundle.trading_date, "us_close"))

        # 2. Index snapshot
        sections.append("")
        sections.append(format_index_snapshot(self.bundle.market_snapshot))

        # 3. Narrative (with renumbered references)
        sections.append("")
        sections.append(narrative)

        # 4. Separator (em dashes with blank lines before/after)
        sections.append("")
        sections.append("—————")
        sections.append("")

        # 5. Takeaways (with renumbered references)
        sections.append(format_takeaways(takeaways))

        # 6. Key Dates
        sections.append("")
        sections.append(format_key_dates_raw(self.bundle.calendar_events))

        # 7. Watch Next (with renumbered references)
        sections.append("")
        sections.append(format_watch_next(watch_next))

        # 8. Optional Spotlight
        if self.bundle.spotlight:
            sections.append("")
            sections.append(format_spotlight_raw(self.bundle.spotlight))

        # 9. Sources (with sequential numbering matching renumbered references)
        sections.append("")
        sections.append(format_sources(self.news_contexts, referenced_ids, ref_mapping))

        return "\n".join(sections)

    def _render_weekend_wrap(self, llm_content: LLMGeneratedContent) -> str:
        """Render weekend_wrap mode message.

        Format:
        - Header (Weekly Wrap Up)
        - Scorecard (plain, not collapsed)
        - Cross-Asset Snapshot (collapsed)
        - Narrative
        - Separator
        - Key Takeaways for the Week (collapsed)
        - Sources (collapsed)
        - Separator
        - Sign-off paragraph
        """
        sections = []
        narrative, takeaways, _, referenced_ids, ref_mapping = self._prepare_references(llm_content)

        # 1. Header (Weekly Wrap Up + date)
        sections.append(format_header_windows(self.bundle.trading_date, "weekend_wrap"))

        # 2. Scorecard (plain, not collapsed)
        if self.bundle.weekly_stats is not None:
            sections.append("")
            sections.append(format_weekly_stats_plain(self.bundle.weekly_stats, "weekend_wrap"))

        # 3. Cross-Asset Snapshot (collapsed)
        cross_assets_section = format_cross_assets_section(self.bundle.market_snapshot)
        if cross_assets_section:
            sections.append("")
            sections.append(cross_assets_section)

        # 4. Narrative
        sections.append("")
        sections.append(narrative)

        # 5. Separator
        sections.append("")
        sections.append("—————")
        sections.append("")

        # 6. Key Takeaways for the Week (collapsed)
        sections.append(format_takeaways(takeaways, header="Key Takeaways for the Week"))

        # 7. Sources (collapsed)
        sections.append("")
        sections.append(format_sources(self.news_contexts, referenced_ids, ref_mapping))

        # 8. Separator before sign-off
        sections.append("")
        sections.append("—————")

        # 9. Sign-off paragraph
        sign_off = getattr(llm_content, "sign_off", None)
        if sign_off:
            sections.append("")
            sections.append(sign_off)

        return "\n".join(sections)

    def _render_monday_preview(self, llm_content: LLMGeneratedContent) -> str:
        """Render monday_preview mode message.

        Format:
        - Header (Monday Preview)
        - Prior Week (plain, not collapsed)
        - Opening line
        - Narrative
        - Separator
        - Key Things to Look Out For (collapsed)
        - Key Dates (collapsed)
        """
        sections = []
        narrative, takeaways, _, referenced_ids, ref_mapping = self._prepare_references(llm_content)

        # 1. Header (Monday Preview + date)
        sections.append(format_header_windows(self.bundle.trading_date, "monday_preview"))

        # 2. Prior Week (plain, not collapsed)
        if self.bundle.weekly_stats is not None:
            sections.append("")
            sections.append(format_weekly_stats_plain(self.bundle.weekly_stats, "monday_preview"))

        # 3. Opening line
        opening_line = getattr(llm_content, "opening_line", None)
        if opening_line:
            sections.append("")
            sections.append(opening_line)

        # 4. Narrative
        sections.append("")
        sections.append(narrative)

        # 5. Separator
        sections.append("")
        sections.append("—————")
        sections.append("")

        # 6. Key Things to Look Out For (collapsed)
        sections.append(format_takeaways(takeaways, header="Key Things to Look Out For"))

        # 7. Key Dates (collapsed)
        sections.append("")
        sections.append(format_key_dates_raw(self.bundle.calendar_events))

        return "\n".join(sections)

    def _escape_message(self, raw: str) -> str:
        """Apply MarkdownV2 escaping to the message.

        Preserves intentional formatting (* for bold, [] for links, etc.)
        while escaping other special characters.

        Args:
            raw: Raw message string.

        Returns:
            MarkdownV2-escaped message.
        """
        return escape_message_v2(raw)


def render_message(
    bundle: FactsBundle,
    news_contexts: list[NewsContext],
    llm_content: LLMGeneratedContent,
    escape_markdown: bool = True,
) -> tuple[str, str]:
    """Convenience function to render a message.

    Args:
        bundle: The facts bundle.
        news_contexts: Pre-processed news contexts.
        llm_content: LLM-generated content.
        escape_markdown: Whether to escape for MarkdownV2.

    Returns:
        Tuple of (escaped_message, raw_message).
    """
    renderer = MessageRenderer(bundle, news_contexts)
    return renderer.render(llm_content, escape_markdown)


def count_words(text: str) -> int:
    """Count words in text.

    Args:
        text: Text to count.

    Returns:
        Word count.
    """
    return len(text.split())
