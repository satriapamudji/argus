"""Crypto-specific message renderer.

Formats crypto daily update messages for Telegram publishing.
"""

import re
from datetime import date
from decimal import Decimal

from argus.facts_bundle.types import CryptoFactsBundle, CryptoMarketSnapshotBundle
from argus.generator.types import LLMGeneratedContent, NewsContext


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


def format_crypto_header(trading_date: date) -> str:
    """Format the crypto daily header.

    Args:
        trading_date: The trading date.

    Returns:
        The formatted header string.
    """
    date_str = trading_date.strftime("%A, %B %d, %Y")
    return f"*Crypto Daily Recap*\n{date_str}"


def format_fear_greed_section(fear_greed: int, previous: int | None = None) -> str:
    """Format the Fear & Greed Index section.

    Args:
        fear_greed: Current Fear & Greed Index value (0-100).
        previous: Previous value for comparison.

    Returns:
        The formatted Fear & Greed section, or None if data unavailable.
    """
    # Determine emoji based on value
    if fear_greed <= 20:
        emoji = "\U0001f631"  # 😰
    elif fear_greed <= 40:
        emoji = "\U0001f628"  # 😨
    elif fear_greed <= 60:
        emoji = "\U0001f610"  # 😐
    elif fear_greed <= 80:
        emoji = "\U0001f604"  # 😃
    else:
        emoji = "\U0001f929"  # 🤩

    change_str = ""
    if previous is not None:
        diff = fear_greed - previous
        if diff > 0:
            change_str = f" (+{diff})"
        elif diff < 0:
            change_str = f" ({diff})"
        else:
            change_str = " (unchanged)"

    return f"{emoji} Fear & Greed: {fear_greed}/100{change_str}"


def format_crypto_snapshot(snapshot: CryptoMarketSnapshotBundle) -> str:
    """Format the crypto market snapshot section.

    Args:
        snapshot: The crypto market snapshot bundle.

    Returns:
        The formatted snapshot section.
    """
    lines = []

    # BTC
    btc_change = float(snapshot.btc.change_1d_pct)
    btc_change_str = f"+{btc_change:.2f}%" if btc_change >= 0 else f"{btc_change:.2f}%"
    btc_price = float(snapshot.btc.price_usd)
    lines.append(f"BTC: ${btc_price:,.2f} ({btc_change_str})")

    # ETH
    eth_change = float(snapshot.eth.change_1d_pct)
    eth_change_str = f"+{eth_change:.2f}%" if eth_change >= 0 else f"{eth_change:.2f}%"
    eth_price = float(snapshot.eth.price_usd)
    lines.append(f"ETH: ${eth_price:,.2f} ({eth_change_str})")

    # Market metrics
    if snapshot.crypto_metrics:
        metrics = snapshot.crypto_metrics
        if metrics.total_market_cap:
            total_mcap = float(metrics.total_market_cap) / 1e9
            lines.append(f"Total Market Cap: ${total_mcap:.1f}B")
        if metrics.btc_dominance:
            btc_dom = float(metrics.btc_dominance)
            lines.append(f"BTC Dominance: {btc_dom:.1f}%")

    return "\n".join(lines)


class CryptoMessageRenderer:
    """Render crypto daily update messages.

    Combines LLM-generated content with crypto-specific metadata sections.
    """

    def __init__(self, news_contexts: list[NewsContext] | None = None) -> None:
        """Initialize the crypto renderer.

        Args:
            news_contexts: Pre-processed news contexts with cite keys.
        """
        self.news_contexts = news_contexts or []

    def render(
        self,
        bundle: CryptoFactsBundle,
        llm_content: LLMGeneratedContent,
    ) -> tuple[str, str]:
        """Render the complete crypto daily message.

        Format matches us_close structure but with crypto-specific content:
        - Header (Crypto Daily Recap + date)
        - Crypto snapshot (BTC, ETH, Market Cap, BTC Dominance)
        - Fear & Greed (if available)
        - Narrative (with renumbered citations)
        - Separator
        - Investor Key Takeaways (collapsed)
        - What to Watch Next (collapsed)
        - Derivatives Data (collapsed, if available)
        - Sources (collapsed)

        Args:
            bundle: The crypto facts bundle.
            llm_content: The LLM-generated content.

        Returns:
            A tuple of (message_text, message_type) where message_type
            is "crypto_daily".
        """
        sections = []

        # Prepare renumbered references
        narrative, takeaways, watch_next, referenced_ids, ref_mapping = self._prepare_references(
            llm_content
        )

        # 1. Header (Crypto Daily Recap + date)
        sections.append(format_crypto_header(bundle.trading_date))

        # 2. Crypto snapshot
        sections.append("")
        sections.append(format_crypto_snapshot(bundle.market_snapshot))

        # 3. Fear & Greed (if available)
        if (
            bundle.market_snapshot.crypto_metrics
            and bundle.market_snapshot.crypto_metrics.fear_greed_index
        ):
            sections.append("")
            fg = bundle.market_snapshot.crypto_metrics.fear_greed_index
            sections.append(format_fear_greed_section(fg))

        # 4. Narrative (with renumbered citations)
        sections.append("")
        sections.append(narrative)

        # 5. Separator (em dashes with blank lines before/after)
        sections.append("")
        sections.append("—————")
        sections.append("")

        # 6. Investor Key Takeaways (collapsed)
        if takeaways:
            sections.append(self._format_takeaways(takeaways))

        # 7. What to Watch Next (collapsed)
        if watch_next:
            sections.append("")
            sections.append(self._format_watch_next(watch_next))

        # 8. Derivatives Data (collapsed, if available)
        if bundle.market_snapshot.crypto_metrics:
            metrics = bundle.market_snapshot.crypto_metrics
            if metrics.funding_rates or metrics.open_interest:
                derivatives = self._format_derivatives_section(
                    funding_rates=metrics.funding_rates,
                    open_interest=metrics.open_interest,
                    long_short_ratio=None,  # Not currently populated
                )
                if derivatives:
                    sections.append("")
                    sections.append(derivatives)

        # 9. Sources (collapsed)
        if referenced_ids:
            sections.append("")
            sections.append(self._format_sources(referenced_ids, ref_mapping))

        return "\n".join(sections), "crypto_daily"

    def _prepare_references(
        self, llm_content: LLMGeneratedContent
    ) -> tuple[str, list[str], list[str], list[int], dict[int, int]]:
        """Prepare renumbered references for all text sections.

        Args:
            llm_content: Generated content from the LLM.

        Returns:
            Tuple of (narrative, takeaways, watch_next, referenced_ids, ref_mapping).
        """
        # Extract cite keys and build renumbering map
        cite_pattern = re.compile(r"\[#([0-9A-Fa-f]{8})\]")

        # Extract cited keys from narrative in order
        seen: set[str] = set()
        cited_keys: list[str] = []
        for match in cite_pattern.finditer(llm_content.narrative):
            key = match.group(1).upper()
            if key not in seen:
                seen.add(key)
                cited_keys.append(key)

        # Build cite_key -> NewsContext mapping
        key_to_ctx = {ctx.cite_key.upper(): ctx for ctx in self.news_contexts}

        # Filter to only valid cited contexts (in order)
        cited_contexts = [key_to_ctx[k] for k in cited_keys if k in key_to_ctx]

        # Build renumbering map: cite_key -> new sequential number
        key_to_new: dict[str, int] = {}
        referenced_ids: list[int] = []
        for i, ctx in enumerate(cited_contexts, start=1):
            key_to_new[ctx.cite_key.upper()] = i
            referenced_ids.append(ctx.news_item_id)

        # Build ref_mapping: news_item_id -> new sequential number
        ref_mapping = {ctx.news_item_id: i for i, ctx in enumerate(cited_contexts, start=1)}

        # Renumber citations in narrative
        def _replace(m: re.Match[str]) -> str:
            key = m.group(1).upper()
            new_num = key_to_new.get(key)
            return f"[{new_num}]" if new_num else m.group(0)

        narrative = cite_pattern.sub(_replace, llm_content.narrative)

        # Renumber citations in takeaways
        takeaways = []
        for takeaway in llm_content.takeaways:
            renumbered = cite_pattern.sub(_replace, takeaway)
            takeaways.append(renumbered)

        # Renumber citations in watch_next
        watch_next = []
        for watch in llm_content.watch_next:
            renumbered = cite_pattern.sub(_replace, watch)
            watch_next.append(renumbered)

        return narrative, takeaways, watch_next, referenced_ids, ref_mapping

    def _format_takeaways(self, takeaways: list[str]) -> str:
        """Format the takeaways section as expandable blockquote."""
        body_lines = [f"• {t}" for t in takeaways]
        return _format_expandable_blockquote(header="Investor Key Takeaways", body_lines=body_lines)

    def _format_watch_next(self, watch_items: list[str]) -> str:
        """Format the What to Watch Next section as expandable blockquote."""
        body_lines = [f"• {item}" for item in watch_items]
        return _format_expandable_blockquote(header="What to Watch Next", body_lines=body_lines)

    def _format_derivatives_section(
        self,
        funding_rates: dict[str, Decimal] | None,
        open_interest: dict[str, Decimal] | None,
        long_short_ratio: dict[str, Decimal] | None,
    ) -> str | None:
        """Format the derivatives section as expandable blockquote.

        Args:
            funding_rates: Funding rates by symbol.
            open_interest: Open interest by symbol.
            long_short_ratio: Long/short ratio by symbol.

        Returns:
            The formatted derivatives section, or None if no data.
        """
        body_lines: list[str] = []

        if funding_rates:
            body_lines.append("Funding Rates:")
            for symbol, rate in funding_rates.items():
                rate_float = float(rate)
                basis_points = rate_float * 10000
                interpretation = (
                    "bullish" if rate_float > 0 else "bearish" if rate_float < 0 else "neutral"
                )
                body_lines.append(f"  • {symbol}: {basis_points:.1f} bps ({interpretation})")

        if open_interest:
            body_lines.append("Open Interest:")
            for symbol, oi in open_interest.items():
                oi_float = float(oi) / 1e9
                body_lines.append(f"  • {symbol}: ${oi_float:.2f}B")

        if long_short_ratio:
            body_lines.append("Long/Short Ratio:")
            for symbol, ratio in long_short_ratio.items():
                ratio_float = float(ratio)
                body_lines.append(f"  • {symbol}: {ratio_float:.2f}")

        if not body_lines:
            return None

        return _format_expandable_blockquote(header="Derivatives Data", body_lines=body_lines)

    def _format_sources(self, referenced_ids: list[int], ref_mapping: dict[int, int]) -> str:
        """Format the Sources section as expandable blockquote.

        Args:
            referenced_ids: List of news item IDs in order of reference.
            ref_mapping: Mapping from news_item_id to sequential number.

        Returns:
            The formatted sources section.
        """
        if not referenced_ids:
            return _format_expandable_blockquote(
                header="Sources", body_lines=["• No cited sources."]
            )

        context_by_id = {ctx.news_item_id: ctx for ctx in self.news_contexts}

        body_lines: list[str] = []
        for item_id in referenced_ids:
            ctx = context_by_id.get(item_id)
            if ctx is None:
                continue
            display_number = ref_mapping.get(item_id, len(body_lines) + 1)
            body_lines.append(ctx.format_for_sources(display_number=display_number))

        return _format_expandable_blockquote(header="Sources", body_lines=body_lines)
