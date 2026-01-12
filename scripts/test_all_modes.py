#!/usr/bin/env python3
"""Generate and optionally publish test messages for all run modes.

Usage:
    python scripts/test_all_modes.py                    # Generate all modes, no publish
    python scripts/test_all_modes.py --publish          # Generate and publish all modes
    python scripts/test_all_modes.py --mode weekend_wrap --publish  # Specific mode
"""

import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from argus.facts_bundle.types import (
    FactsBundle,
    WeeklyReturnBundle,
    WeeklyStatsBundle,
)
from argus.generator import build_news_contexts
from argus.generator.renderer import extract_referenced_ids, render_message
from argus.generator.types import LLMGeneratedContent


def load_base_bundle() -> FactsBundle:
    """Load the base facts bundle from fixtures."""
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures"
    bundle_path = fixtures_dir / "facts_bundle.json"

    with open(bundle_path, "r", encoding="utf-8") as f:
        bundle_data = json.load(f)
    return FactsBundle.from_dict(bundle_data)


def create_weekly_stats() -> WeeklyStatsBundle:
    """Create sample weekly stats for weekend_wrap and monday_preview modes."""
    return WeeklyStatsBundle(
        week_start=date(2026, 1, 5),
        week_end=date(2026, 1, 9),
        sp500_return=WeeklyReturnBundle(
            return_pct=Decimal("1.25"),
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 9),
            label="Week",
        ),
        dow_return=WeeklyReturnBundle(
            return_pct=Decimal("0.85"),
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 9),
            label="Week",
        ),
        nasdaq_return=WeeklyReturnBundle(
            return_pct=Decimal("1.75"),
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 9),
            label="Week",
        ),
    )


def modify_bundle_for_mode(base_bundle: FactsBundle, run_mode: str) -> FactsBundle:
    """Create a modified bundle for the specified run mode."""
    weekly_stats = None
    if run_mode in ("weekend_wrap", "monday_preview"):
        weekly_stats = create_weekly_stats()

    return FactsBundle(
        version=base_bundle.version,
        stream_name=base_bundle.stream_name,
        run_mode=run_mode,
        generated_at=base_bundle.generated_at,
        trading_date=base_bundle.trading_date,
        market_snapshot=base_bundle.market_snapshot,
        news_items=base_bundle.news_items,
        calendar_events=base_bundle.calendar_events,
        spotlight=base_bundle.spotlight,
        weekly_stats=weekly_stats,
    )


def get_llm_content_for_mode(run_mode: str, referenced_ids: list[int]) -> LLMGeneratedContent:
    """Get appropriate LLM content for each run mode."""

    if run_mode == "us_close":
        return LLMGeneratedContent(
            narrative=(
                "U.S. equities rallied as risk appetite improved, with strength concentrated "
                "in cyclicals and selected tech. Markets appeared to treat geopolitical headlines "
                "as near-term noise rather than a broader escalation, while softer manufacturing "
                "data supported the 'easing later' narrative for rates.\n\n"
                "Energy and defense names outperformed after reports that U.S. officials were "
                "discussing potential investment and security arrangements tied to Venezuela's "
                "oil sector [#C9FB1023]. The move coincided with a sharp bid in gold as investors "
                "added hedges, suggesting positioning is shifting toward 'risk-on with protection' [#8589F577].\n\n"
                "In tech, semiconductor leadership remained supportive, but dispersion within "
                "software pointed to a more selective market [#2CAD28AF]."
            ),
            takeaways=[
                "Leadership is broadening - rotate exposure toward earnings quality.",
                "Cross-asset hedges still matter: gold bid alongside equity strength.",
                "Treat headline spikes as catalysts for review, not automatic trend breaks.",
            ],
            watch_next=[
                "Whether yields confirm the risk rally.",
                "Follow-through in cyclicals vs. reversal to defensives.",
            ],
            referenced_item_ids=referenced_ids,
            raw_response="test-us-close",
        )

    elif run_mode == "weekend_wrap":
        return LLMGeneratedContent(
            narrative=(
                "Markets closed the week on a strong note, with the S&P 500 notching gains for "
                "the fourth consecutive session. The rally was broad-based, with 9 of 11 sectors "
                "finishing higher.\n\n"
                "The week's narrative centered on dovish Fed expectations following softer inflation "
                "prints [#C9FB1023]. Treasury yields retreated, providing a tailwind for rate-sensitive "
                "sectors. Gold continued its climb as investors hedged geopolitical risks [#8589F577].\n\n"
                "Looking ahead, the focus shifts to earnings season kickoff and key economic data [#2CAD28AF]."
            ),
            takeaways=[
                "Breadth improved throughout the week - healthy sign for continuation.",
                "Rate sensitivity remains elevated - watch Treasury moves closely.",
                "Position for earnings season with quality bias.",
            ],
            watch_next=[
                "Bank earnings starting next week.",
                "Retail sales data for holiday period.",
            ],
            referenced_item_ids=referenced_ids,
            raw_response="test-weekend-wrap",
        )

    elif run_mode == "monday_preview":
        return LLMGeneratedContent(
            narrative=(
                "Markets enter the new week with momentum, following last week's strong gains. "
                "The S&P 500 is testing key resistance levels as investors digest mixed signals "
                "from economic data.\n\n"
                "This week brings a heavy calendar of Fed speakers and critical inflation data "
                "[#C9FB1023]. Market pricing suggests high sensitivity to any hawkish surprises. "
                "Geopolitical tensions remain a wildcard, with gold prices reflecting ongoing "
                "hedging demand [#8589F577].\n\n"
                "Earnings season begins in earnest with major banks reporting [#2CAD28AF]."
            ),
            takeaways=[
                "Heavy event risk this week - size positions accordingly.",
                "CPI print on Wednesday is the week's key catalyst.",
                "Bank earnings will set the tone for the broader season.",
            ],
            watch_next=[
                "Wednesday CPI release (consensus: 2.9% y/y).",
                "JPMorgan, Citi, Wells Fargo earnings Friday.",
            ],
            referenced_item_ids=referenced_ids,
            raw_response="test-monday-preview",
        )

    raise ValueError(f"Unknown run mode: {run_mode}")


def publish_to_telegram(escaped_message: str) -> dict:
    """Publish message to Telegram and return the response."""
    from dotenv import load_dotenv

    load_dotenv()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": escaped_message,
        "parse_mode": "MarkdownV2",
        "link_preview_options": {"is_disabled": True},
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(url, json=payload)
        return response.json()


def generate_and_publish(run_mode: str, publish: bool = False) -> tuple[str, str]:
    """Generate message for a run mode and optionally publish."""
    print(f"\n{'=' * 60}")
    print(f"Generating {run_mode.upper()} message")
    print("=" * 60)

    # Load and modify bundle
    base_bundle = load_base_bundle()
    bundle = modify_bundle_for_mode(base_bundle, run_mode)
    print(f"  - Run mode: {bundle.run_mode}")
    print(f"  - Trading date: {bundle.trading_date}")
    print(f"  - Weekly stats: {'Yes' if bundle.weekly_stats else 'No'}")

    # Build contexts
    news_contexts = build_news_contexts(bundle)
    print(f"  - News contexts: {len(news_contexts)}")

    # Get referenced IDs from base fixture
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures"
    fixture_text = (fixtures_dir / "generated_message_valid.md").read_text(encoding="utf-8")
    referenced_ids = extract_referenced_ids(fixture_text, news_contexts)

    # Get LLM content for this mode
    llm_content = get_llm_content_for_mode(run_mode, referenced_ids)

    # Render
    escaped_message, raw_message = render_message(bundle, news_contexts, llm_content, True)
    print(f"  - Raw length: {len(raw_message)} chars")
    print(f"  - Escaped length: {len(escaped_message)} chars")

    # Show preview
    print(f"\n--- RAW MESSAGE PREVIEW ---")
    print(raw_message[:1500])
    if len(raw_message) > 1500:
        print(f"... [{len(raw_message) - 1500} more chars]")

    # Publish if requested
    if publish:
        print(f"\n--- PUBLISHING TO TELEGRAM ---")
        try:
            result = publish_to_telegram(escaped_message)
            if result.get("ok"):
                msg_id = result["result"]["message_id"]
                print(f"SUCCESS: message_id={msg_id}")

                # Check for expandable blockquotes
                entities = result["result"].get("entities", [])
                expandable_count = sum(
                    1 for e in entities if e.get("type") == "expandable_blockquote"
                )
                bold_underline_count = sum(
                    1 for e in entities if e.get("type") in ("bold", "underline")
                )
                print(f"  - Expandable blockquotes: {expandable_count}")
                print(f"  - Bold/underline entities: {bold_underline_count}")
            else:
                print(f"FAILED: {result}")
        except Exception as e:
            print(f"ERROR: {e}")

    return escaped_message, raw_message


def main():
    parser = argparse.ArgumentParser(description="Generate and publish test messages")
    parser.add_argument(
        "--mode",
        choices=["us_close", "weekend_wrap", "monday_preview", "all"],
        default="all",
        help="Run mode to generate",
    )
    parser.add_argument("--publish", action="store_true", help="Publish to Telegram")
    args = parser.parse_args()

    modes = ["us_close", "weekend_wrap", "monday_preview"] if args.mode == "all" else [args.mode]

    for mode in modes:
        generate_and_publish(mode, args.publish)

    print(f"\n{'=' * 60}")
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
