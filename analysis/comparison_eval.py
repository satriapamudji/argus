#!/usr/bin/env python3
"""Compare old vs new scored rankings on the same DB item window.

This script builds an apples-to-apples comparison between:
- OLD: existing scores in news_scores (typically heuristic_v1)
- NEW: in-memory heuristic_v2 scores computed on the same items (NO DB writes)

It then runs the deterministic us_close macro-heavy evaluation rubric
(analysis/eval_framework.py) on both ranked lists and prints:
- Contract pass/fail + violations
- TopK A/B/C/D compositions
- Spam + inversion checks
- Biggest rank movers (old->new)

Usage:
  python analysis/comparison_eval.py --days 1
  python analysis/comparison_eval.py --days 7 --limit 800

Requires:
  DATABASE_URL in environment (.env supported)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
import json
from pathlib import Path

import os

import psycopg2
from dotenv import load_dotenv

# Allow importing sibling analysis modules when running as a script
# (python analysis/comparison_eval.py)
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from argus.config import ArgusConfig
from argus.scoring.heuristics_v2 import score_candidates_v2
from argus.scoring.types import ScoringCandidate

from eval_framework import annotate, assert_contract, evaluate

# Windows consoles can default to legacy encodings (cp1252) that throw on some
# Unicode characters in titles/snippets. Ensure we never crash while printing.
try:
    sys.stdout.reconfigure(errors="backslashreplace")
except Exception:
    pass


@dataclass(frozen=True)
class DbRow:
    id: int
    fingerprint_id: int
    source_name: str
    source_url: str
    title: str
    snippet: str
    feed_url: Optional[str]
    ingested_at: datetime
    published_at: Optional[datetime]
    simhash: Optional[int]
    old_impact_score: int
    old_scorer_version: Optional[str]


def _load_db_rows(days: float, limit: int) -> list[DbRow]:
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set in environment")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    try:
        query = """
        SELECT
            ni.id,
            ni.fingerprint_id,
            ni.source_name,
            ni.source_url,
            ni.title,
            COALESCE(ni.snippet, '') AS snippet,
            ni.raw_metadata->>'feed_url' AS feed_url,
            ni.ingested_at,
            ni.published_at,
            nf.simhash,
            ns.impact_score,
            ns.scorer_version
        FROM news_items ni
        JOIN news_fingerprints nf ON ni.fingerprint_id = nf.id
        JOIN news_scores ns ON ni.id = ns.news_item_id
        WHERE ni.ingested_at >= NOW() - INTERVAL %s
        ORDER BY ns.impact_score DESC
        LIMIT %s
        """
        # psycopg2 doesn't allow binding interval with numeric directly; bind as text, e.g. '1 days'
        cur.execute(query, (f"{days} days", limit))
        rows = cur.fetchall()
    finally:
        conn.close()

    out: list[DbRow] = []
    for r in rows:
        out.append(
            DbRow(
                id=r[0],
                fingerprint_id=r[1],
                source_name=r[2],
                source_url=r[3],
                title=r[4],
                snippet=r[5],
                feed_url=r[6],
                ingested_at=r[7],
                published_at=r[8],
                simhash=r[9],
                old_impact_score=int(r[10]),
                old_scorer_version=r[11],
            )
        )

    return out


def _to_eval_item(row: DbRow, impact_score: int) -> dict[str, Any]:
    return {
        "id": row.id,
        "source_name": row.source_name,
        "source_url": row.source_url,
        "title": row.title,
        "snippet": row.snippet,
        "feed_url": row.feed_url,
        "impact_score": int(impact_score),
    }


def _print_eval(
    name: str,
    items_ranked: list[dict[str, Any]],
    *,
    topk: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    annotated = annotate(items_ranked)
    res = evaluate(annotated)
    violations = assert_contract(res)

    def _counts_str(counts: dict[str, int]) -> str:
        return f"A={counts['A']} B={counts['B']} C={counts['C']} D={counts['D']}"

    summary: dict[str, Any] = {
        "name": name,
        "contract": {
            "pass": len(violations) == 0,
            "violations": violations,
        },
        "top12": {
            "counts": res.top12.counts,
            "spam_market_today": res.spam12.market_wrap_templates,
        },
        "top20": {
            "counts": res.top20.counts,
        },
        "top50": {
            "counts": res.top50.counts,
            "inversions_hard_D_over_A_or_B": res.inversions50.hard_D_over_A_or_B,
            "D_rate": float(res.top50.counts["D"]) / 50.0,
        },
    }

    # Emit TopK items as JSON with enough metadata to inspect content quality.
    def _short(s: Any, n: int = 100) -> str:
        txt = ("" if s is None else str(s)).replace("\n", " ").strip()
        return txt if len(txt) <= n else txt[:n]

    top_items: list[dict[str, Any]] = []
    for i, it in enumerate(annotated[:topk], 1):
        c = it["_class"]
        top_items.append(
            {
                "rank": i,
                "id": it.get("id"),
                "impact_score": it.get("impact_score"),
                "class": c.get("label"),
                "title": _short(it.get("title"), 100),
                "snippet": ("" if it.get("snippet") is None else str(it.get("snippet")))
                .replace("\n", " ")
                .strip(),
                "source_name": _short(it.get("source_name"), 80),
                "source_url": _short(it.get("source_url"), 500),
                "feed_url": _short(it.get("feed_url"), 500),
                "class_reasons": c.get("reasons", []),
            }
        )

    print("\n" + "=" * 80)
    print(f"{name}")
    print("=" * 80)
    print(
        f"Top12: {_counts_str(res.top12.counts)} | spam_market_today={res.spam12.market_wrap_templates}"
    )
    print(f"Top20: {_counts_str(res.top20.counts)}")
    print(
        f"Top50: {_counts_str(res.top50.counts)} | inv_hard(D above A/B)={res.inversions50.hard_D_over_A_or_B}"
    )
    print("Contract: PASS" if len(violations) == 0 else "Contract: FAIL")
    if violations:
        for v in violations:
            print(f"- {v}")

    print(f"\nTop{topk}_json:")
    print(json.dumps(top_items, indent=2, ensure_ascii=False))

    return summary, top_items


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare old vs new scoring rankings")
    parser.add_argument("--days", type=float, default=1.0, help="Lookback window in days")
    parser.add_argument(
        "--limit",
        type=int,
        default=800,
        help="Max items to load from DB for this window (ranked by old score)",
    )
    parser.add_argument(
        "--movers",
        type=int,
        default=25,
        help="How many biggest movers to print",
    )
    parser.add_argument(
        "--topk",
        type=int,
        default=12,
        help="How many top-ranked items to include in the JSON output (contract checks remain fixed at Top12/Top20/Top50)",
    )
    args = parser.parse_args()

    rows = _load_db_rows(days=args.days, limit=args.limit)
    if not rows:
        print("No scored rows found in window")
        return 1

    # OLD ranking = as loaded (ORDER BY old impact_score desc)
    old_ranked = [_to_eval_item(r, r.old_impact_score) for r in rows]

    # NEW ranking = compute in-memory v2 scores for exact same candidates
    cfg = ArgusConfig.load()

    candidates = [
        ScoringCandidate(
            news_item_id=r.id,
            fingerprint_id=r.fingerprint_id,
            source_name=r.source_name,
            source_url=r.source_url,
            title=r.title,
            snippet=r.snippet,
            published_at=r.published_at,
            ingested_at=r.ingested_at,
            simhash=r.simhash,
        )
        for r in rows
    ]

    # Provide simhash context from this same set. This isn't identical to the worker's
    # "recent simhashes" (which includes other items), but keeps the comparison deterministic.
    recent_simhashes = [r.simhash for r in rows if r.simhash is not None]
    v2_results = score_candidates_v2(
        candidates, cfg.stream.scoring, recent_simhashes=recent_simhashes
    )

    v2_score_by_id = {res.news_item_id: res.impact_score for res in v2_results}
    new_ranked = [_to_eval_item(r, v2_score_by_id.get(r.id, 0)) for r in rows]
    new_ranked.sort(key=lambda it: it["impact_score"], reverse=True)

    # Print evaluations
    print(
        f"\n=== RUN REPORT days={args.days} limit={args.limit} movers={args.movers} topk={args.topk} ==="
    )
    report_dir = Path(__file__).resolve().parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    old_summary, old_top_items = _print_eval(
        "OLD (DB: news_scores.impact_score)",
        old_ranked,
        topk=args.topk,
    )
    new_summary, new_top_items = _print_eval(
        "NEW (in-memory: heuristic_v2)",
        new_ranked,
        topk=args.topk,
    )

    # Biggest movers: compute rank delta
    old_rank = {it["id"]: i for i, it in enumerate(old_ranked, 1)}
    new_rank = {it["id"]: i for i, it in enumerate(new_ranked, 1)}

    movers = []
    for r in rows:
        oid = r.id
        if oid not in old_rank or oid not in new_rank:
            continue
        delta = old_rank[oid] - new_rank[oid]  # positive = moved up in new
        movers.append(
            {
                "id": oid,
                "delta": delta,
                "old_rank": old_rank[oid],
                "new_rank": new_rank[oid],
                "old": r.old_impact_score,
                "new": v2_score_by_id.get(oid, 0),
                "title": r.title,
            }
        )

    movers.sort(key=lambda m: abs(m["delta"]), reverse=True)
    print("\n" + "=" * 80)
    print(f"Biggest rank movers (top {args.movers})")
    print("=" * 80)
    for m in movers[: args.movers]:
        sign = "+" if m["delta"] >= 0 else ""
        print(
            f"{sign}{m['delta']:4} | {m['old_rank']:4} -> {m['new_rank']:4}"
            f" | {m['old']:3} -> {m['new']:3} | {m['title'][:90]}"
        )

    def _report_filename() -> str:
        # Date-first, sortable filename.
        # Example: 20260109_171230__comparison_eval__days1.0__limit300.json
        return f"{ts}__comparison_eval__days{args.days}__limit{args.limit}.json"

    report = {
        "meta": {
            "created_at": ts,
            "days": args.days,
            "limit": args.limit,
            "movers_requested": args.movers,
        },
        "old": {
            "summary": old_summary,
            "top_items": old_top_items,
        },
        "new": {
            "summary": new_summary,
            "top_items": new_top_items,
        },
        "movers": movers[: args.movers],
    }

    out_path = report_dir / _report_filename()
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote combined report: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
