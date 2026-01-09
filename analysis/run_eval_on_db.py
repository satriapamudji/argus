#!/usr/bin/env python3
"""Run the locked eval contract on a DB window (last N days).

This evaluates the *current scorer output* (impact_score ranking) against the
A/B/C/D macro-heavy contract, sourcing items directly from Postgres.

Usage:
  python analysis/run_eval_on_db.py --days 1
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure repo root on sys.path so `analysis/` can be imported when running as a script
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval_framework import load_ranked_items_from_db, annotate, evaluate, assert_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Run us_close macro-heavy eval on DB window")
    parser.add_argument(
        "--days", type=float, default=1.0, help="Lookback window in days (default 1.0 = 24h)"
    )
    args = parser.parse_args()

    items = load_ranked_items_from_db(days=args.days)
    if not items:
        print(f"No items found for last {args.days} days")
        return 2

    annotated = annotate(items)
    res = evaluate(annotated)
    violations = assert_contract(res)

    print("=" * 80)
    print(f"US_CLOSE MACRO-HEAVY EVAL (DB window: {args.days} days)")
    print("=" * 80)

    def fmt_counts(c: dict[str, int]) -> str:
        return f"A={c['A']} B={c['B']} C={c['C']} D={c['D']}"

    print(f"Items: {len(items)}")
    print(f"Top12: {fmt_counts(res.top12.counts)}")
    print(f"Top20: {fmt_counts(res.top20.counts)}")
    print(f"Top50: {fmt_counts(res.top50.counts)}")
    print()

    print(f"Hard inversions (Top50, D above A/B): {res.inversions50.hard_D_over_A_or_B}")
    print(f"D in Top20: {res.inversions20.D_in_top_k}")
    print(f"Spam (Top12) market_wrap_templates: {res.spam12.market_wrap_templates}")
    print()

    if violations:
        print("CONTRACT: FAIL")
        for v in violations:
            print(f"- {v}")
    else:
        print("CONTRACT: PASS")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
