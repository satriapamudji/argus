"""Crypto-specific message renderer.

Formats crypto daily update messages for Telegram publishing.
"""

import re
from datetime import date
from decimal import Decimal

from argus.facts_bundle.types import CryptoFactsBundle, CryptoMarketSnapshotBundle
from argus.generator.types import LLMGeneratedContent, NewsContext


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


def format_derivatives_section(
    funding_rates: dict[str, Decimal] | None,
    open_interest: dict[str, Decimal] | None,
    long_short_ratio: dict[str, Decimal] | None,
) -> str | None:
    """Format the derivatives section.

    Args:
        funding_rates: Funding rates by symbol.
        open_interest: Open interest by symbol.
        long_short_ratio: Long/short ratio by symbol.

    Returns:
        The formatted derivatives section, or None if no data.
    """
    if not any([funding_rates, open_interest, long_short_ratio]):
        return None

    lines = ["*Derivatives:*"]

    if funding_rates:
        lines.append("Funding Rates:")
        for symbol, rate in funding_rates.items():
            rate_float = float(rate)
            basis_points = rate_float * 10000
            interpretation = (
                "bullish" if rate_float > 0 else "bearish" if rate_float < 0 else "neutral"
            )
            lines.append(f"  {symbol}: {basis_points:.1f} bps ({interpretation})")

    if open_interest:
        lines.append("Open Interest:")
        for symbol, oi in open_interest.items():
            oi_float = float(oi) / 1e9
            lines.append(f"  {symbol}: ${oi_float:.2f}B")

    if long_short_ratio:
        lines.append("Long/Short Ratio:")
        for symbol, ratio in long_short_ratio.items():
            ratio_float = float(ratio)
            lines.append(f"  {symbol}: {ratio_float:.2f}")

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

        Args:
            bundle: The crypto facts bundle.
            llm_content: The LLM-generated content.

        Returns:
            A tuple of (message_text, message_type) where message_type
            is "crypto_daily".
        """
        lines = []

        # Header
        lines.append(format_crypto_header(bundle.trading_date))
        lines.append("")  # Blank line

        # Market snapshot (above the fold)
        lines.append(format_crypto_snapshot(bundle.market_snapshot))
        lines.append("")  # Blank line

        # Fear & Greed (if available)
        if (
            bundle.market_snapshot.crypto_metrics
            and bundle.market_snapshot.crypto_metrics.fear_greed_index
        ):
            fg = bundle.market_snapshot.crypto_metrics.fear_greed_index
            lines.append(format_fear_greed_section(fg))
            lines.append("")  # Blank line

        # LLM narrative
        lines.append(llm_content.narrative)
        lines.append("")  # Blank line

        # Takeaways
        if llm_content.takeaways:
            lines.append("*Investor Key Takeaways:*")
            for takeaway in llm_content.takeaways:
                lines.append(f"  {takeaway}")
            lines.append("")  # Blank line

        # Watch Next
        if llm_content.watch_next:
            lines.append("*What to Watch:*")
            for watch in llm_content.watch_next:
                lines.append(f"  {watch}")
            lines.append("")  # Blank line

        # Derivatives (expandable section)
        if bundle.market_snapshot.crypto_metrics:
            metrics = bundle.market_snapshot.crypto_metrics
            # Only show if we have at least one type of derivatives data
            if metrics.funding_rates or metrics.open_interest:
                derivatives = format_derivatives_section(
                    funding_rates=metrics.funding_rates,
                    open_interest=metrics.open_interest,
                    long_short_ratio=None,  # Not currently populated
                )
                if derivatives:
                    lines.append(derivatives)
                    lines.append("")  # Blank line
        # Remove trailing blank line
        if lines and lines[-1] == "":
            lines.pop()

        # Sources section for crypto messages
        if llm_content.narrative and self.news_contexts:
            cite_pattern = re.compile(r"\[#([0-9A-Fa-f]{8})\]")

            # Extract cite keys in order of first appearance (deduplicated)
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

            if cited_contexts:
                # Build renumbering map: cite_key -> new sequential number
                key_to_new: dict[str, int] = {}
                for i, ctx in enumerate(cited_contexts, start=1):
                    key_to_new[ctx.cite_key.upper()] = i

                # Update lines[index of narrative] with renumbered citations
                # Find and update the narrative in lines
                for idx, line in enumerate(lines):
                    if line == llm_content.narrative:
                        def _replace(m: re.Match[str]) -> str:
                            key = m.group(1).upper()
                            new_num = key_to_new.get(key)
                            return f"[{new_num}]" if new_num else m.group(0)
                        lines[idx] = cite_pattern.sub(_replace, line)
                        break

                # Build Sources section as expandable blockquote
                lines.append("")
                lines.append("__*Sources*__")
                for i, ctx in enumerate(cited_contexts):
                    prefix = "**>" if i == 0 else ">"
                    suffix = "||" if i == len(cited_contexts) - 1 else ""
                    lines.append(f"{prefix}{ctx.format_for_sources(display_number=i+1)}{suffix}")

                lines.append("")  # Blank line

        message_text = "\n".join(lines)
        message_type = "crypto_daily"

        return message_text, message_type
