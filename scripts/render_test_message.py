#!/usr/bin/env python3
"""Generate a test message using the renderer pipeline and output escaped MarkdownV2.

This script replicates what the smoke test does, but writes the escaped output
to a file that can be sent to Telegram for visual verification.
"""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from argus.facts_bundle.types import FactsBundle
from argus.generator import build_news_contexts
from argus.generator.renderer import extract_referenced_ids, render_message
from argus.generator.types import LLMGeneratedContent


def main():
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures"

    # 1. Load facts bundle
    bundle_path = fixtures_dir / "facts_bundle.json"
    print(f"Loading bundle from: {bundle_path}")

    with open(bundle_path, "r", encoding="utf-8") as f:
        bundle_data = json.load(f)
    bundle = FactsBundle.from_dict(bundle_data)
    print(f"  - Trading date: {bundle.trading_date.isoformat()}")
    print(f"  - News items: {len(bundle.news_items)}")

    # 2. Build news contexts
    news_contexts = build_news_contexts(bundle)
    print(f"Built {len(news_contexts)} news contexts")

    # 3. Load the narrative fixture
    valid_message_path = fixtures_dir / "generated_message_valid.md"
    fixture_text = valid_message_path.read_text(encoding="utf-8")
    print(f"Loaded narrative fixture ({len(fixture_text)} chars)")

    # 4. Extract referenced IDs from cite keys
    referenced_ids = extract_referenced_ids(fixture_text, news_contexts)
    print(f"Referenced IDs: {referenced_ids}")

    # 5. Build LLM content (same as smoke test)
    llm_content = LLMGeneratedContent(
        narrative=fixture_text,
        takeaways=[
            "Leadership is broadening—rotate exposure toward earnings quality and avoid single-theme concentration.",
            'Cross-asset hedges still matter: the gold bid alongside equity strength points to "risk-on with protection."',
            "Treat headline spikes as catalysts for positioning review, not automatic trend breaks, unless confirmed by follow-through in rates/FX.",
        ],
        watch_next=[
            "Whether yields confirm the risk rally (further declines in real yields would support equities).",
            "Follow-through in cyclicals vs. a quick reversal back to defensives.",
        ],
        referenced_item_ids=referenced_ids,
        raw_response="test-render-script",
    )

    # 6. Render the message
    escaped_message, raw_message = render_message(bundle, news_contexts, llm_content, True)

    print(f"\nRendered message:")
    print(f"  - Raw length: {len(raw_message)} chars")
    print(f"  - Escaped length: {len(escaped_message)} chars")
    print(f"  - Word count: {len(raw_message.split())}")

    # 7. Write outputs
    output_dir = Path(__file__).parent.parent

    escaped_path = output_dir / "test_message_escaped.txt"
    escaped_path.write_text(escaped_message, encoding="utf-8")
    print(f"\nEscaped message written to: {escaped_path}")

    raw_path = output_dir / "test_message_raw.txt"
    raw_path.write_text(raw_message, encoding="utf-8")
    print(f"Raw message written to: {raw_path}")

    # 8. Show a preview
    print("\n" + "=" * 60)
    print("ESCAPED MESSAGE PREVIEW (first 2000 chars):")
    print("=" * 60)
    print(escaped_message[:2000])
    if len(escaped_message) > 2000:
        print(f"\n... [{len(escaped_message) - 2000} more chars]")


if __name__ == "__main__":
    main()
