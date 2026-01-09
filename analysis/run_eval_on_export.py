#!/usr/bin/env python3
"""Run the locked eval contract on an exported dataset JSON.

This evaluates the *current scorer output* (impact_score ranking) against the
A/B/C/D macro-heavy contract.

Usage:
  python analysis/run_eval_on_export.py analysis/scoring_dataset_20260109.json
"""

from __future__ import annotations

import json
import sys

import os

# Ensure repo root on sys.path so `analysis/` can be imported when running as a script
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from analysis.eval_framework import annotate, evaluate, assert_contract


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python analysis/run_eval_on_export.py <dataset.json>")
        return 2

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)

    # Ensure ranking is by impact_score desc (export already is, but enforce)
    items_sorted = sorted(items, key=lambda x: x.get("impact_score", 0), reverse=True)

    annotated = annotate(items_sorted)
    res = evaluate(annotated)
    violations = assert_contract(res)

    print("=" * 80)
    print("US_CLOSE MACRO-HEAVY EVAL (contract)")
    print("=" * 80)

    def fmt_counts(c: dict[str, int]) -> str:
        return f"A={c['A']} B={c['B']} C={c['C']} D={c['D']}"

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

    print()
    print("Top12 breakdown:")
    for i, it in enumerate(annotated[:12], 1):
        label = it["_class"]["label"]
        reasons = ",".join(it["_class"]["reasons"])[:120]
        title = (it.get("title") or "")[:80]
        print(f"{i:2}. [{it.get('impact_score'):2}] {label} {title}")
        print(f"    reasons: {reasons}")

    # Spot-check expected D detections in top 50
    print()
    print("D items in Top50:")
    d_items = [(i + 1, it) for i, it in enumerate(annotated[:50]) if it["_class"]["label"] == "D"]
    if not d_items:
        print("(none)")
    else:
        for rank, it in d_items:
            title = (it.get("title") or "")[:80]
            reasons = ",".join(it["_class"]["reasons"])[:120]
            print(f"[{rank:2}] Score={it.get('impact_score'):2} {title}")
            print(f"     reasons: {reasons}")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
