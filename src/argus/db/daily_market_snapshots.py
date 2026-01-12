"""Repository helpers for persisted daily market snapshots.

Separated from argus.db.repository to avoid circular imports:
- argus.db.repository imports MarketSnapshot (adapter)
- adapters import facts_bundle types
- facts_bundle.builder needs snapshot repo helpers

This module must stay DB-only (no imports from adapters/facts_bundle/orchestrator).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection as Connection


def upsert_daily_market_snapshot(
    conn: Connection,
    *,
    stream_name: str,
    trading_date: date,
    sp500_close: float,
    sp500_change_pct: float | None,
    dow_close: float,
    dow_change_pct: float | None,
    nasdaq_close: float,
    nasdaq_change_pct: float | None,
    # Optional cross-assets
    vix_close: float | None = None,
    vix_change_pct: float | None = None,
    usd_dxy_close: float | None = None,
    usd_dxy_change_pct: float | None = None,
    us10y_yield: float | None = None,
    us10y_change_bp: float | None = None,
    wti_crude_close: float | None = None,
    wti_crude_change_pct: float | None = None,
    gold_close: float | None = None,
    gold_change_pct: float | None = None,
    source_name: str = "market_data_provider",
) -> None:
    """Insert or update a daily snapshot row keyed by (stream_name, trading_date)."""

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO daily_market_snapshots (
                stream_name,
                trading_date,
                sp500_close,
                sp500_change_pct,
                dow_close,
                dow_change_pct,
                nasdaq_close,
                nasdaq_change_pct,
                vix_close,
                vix_change_pct,
                usd_dxy_close,
                usd_dxy_change_pct,
                us10y_yield,
                us10y_change_bp,
                wti_crude_close,
                wti_crude_change_pct,
                gold_close,
                gold_change_pct,
                source_name
            ) VALUES (
                %(stream_name)s,
                %(trading_date)s,
                %(sp500_close)s,
                %(sp500_change_pct)s,
                %(dow_close)s,
                %(dow_change_pct)s,
                %(nasdaq_close)s,
                %(nasdaq_change_pct)s,
                %(vix_close)s,
                %(vix_change_pct)s,
                %(usd_dxy_close)s,
                %(usd_dxy_change_pct)s,
                %(us10y_yield)s,
                %(us10y_change_bp)s,
                %(wti_crude_close)s,
                %(wti_crude_change_pct)s,
                %(gold_close)s,
                %(gold_change_pct)s,
                %(source_name)s
            )
            ON CONFLICT (stream_name, trading_date) DO UPDATE SET
                sp500_close = EXCLUDED.sp500_close,
                sp500_change_pct = EXCLUDED.sp500_change_pct,
                dow_close = EXCLUDED.dow_close,
                dow_change_pct = EXCLUDED.dow_change_pct,
                nasdaq_close = EXCLUDED.nasdaq_close,
                nasdaq_change_pct = EXCLUDED.nasdaq_change_pct,
                vix_close = EXCLUDED.vix_close,
                vix_change_pct = EXCLUDED.vix_change_pct,
                usd_dxy_close = EXCLUDED.usd_dxy_close,
                usd_dxy_change_pct = EXCLUDED.usd_dxy_change_pct,
                us10y_yield = EXCLUDED.us10y_yield,
                us10y_change_bp = EXCLUDED.us10y_change_bp,
                wti_crude_close = EXCLUDED.wti_crude_close,
                wti_crude_change_pct = EXCLUDED.wti_crude_change_pct,
                gold_close = EXCLUDED.gold_close,
                gold_change_pct = EXCLUDED.gold_change_pct,
                source_name = EXCLUDED.source_name,
                fetched_at = NOW()
            """,
            {
                "stream_name": stream_name,
                "trading_date": trading_date,
                "sp500_close": sp500_close,
                "sp500_change_pct": sp500_change_pct,
                "dow_close": dow_close,
                "dow_change_pct": dow_change_pct,
                "nasdaq_close": nasdaq_close,
                "nasdaq_change_pct": nasdaq_change_pct,
                "vix_close": vix_close,
                "vix_change_pct": vix_change_pct,
                "usd_dxy_close": usd_dxy_close,
                "usd_dxy_change_pct": usd_dxy_change_pct,
                "us10y_yield": us10y_yield,
                "us10y_change_bp": us10y_change_bp,
                "wti_crude_close": wti_crude_close,
                "wti_crude_change_pct": wti_crude_change_pct,
                "gold_close": gold_close,
                "gold_change_pct": gold_change_pct,
                "source_name": source_name,
            },
        )


def get_daily_market_snapshots_in_range(
    conn: Connection,
    *,
    stream_name: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Fetch snapshots for [start_date, end_date] inclusive, ascending by date."""

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                trading_date,
                sp500_close,
                dow_close,
                nasdaq_close
            FROM daily_market_snapshots
            WHERE stream_name = %(stream_name)s
              AND trading_date >= %(start_date)s
              AND trading_date <= %(end_date)s
            ORDER BY trading_date ASC
            """,
            {
                "stream_name": stream_name,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        rows = cur.fetchall()

    # RealDictCursor already returns dict-like rows, coerce explicitly to dict
    return [dict(r) for r in rows]


def get_last_daily_market_snapshot_before_date(
    conn: Connection,
    *,
    stream_name: str,
    before_date: date,
) -> Optional[dict[str, Any]]:
    """Fetch latest snapshot with trading_date < before_date."""

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                trading_date,
                sp500_close,
                dow_close,
                nasdaq_close
            FROM daily_market_snapshots
            WHERE stream_name = %(stream_name)s
              AND trading_date < %(before_date)s
            ORDER BY trading_date DESC
            LIMIT 1
            """,
            {"stream_name": stream_name, "before_date": before_date},
        )
        row = cur.fetchone()

    return dict(row) if row else None


def update_cross_assets_for_snapshot(
    conn: Connection,
    *,
    stream_name: str,
    trading_date: date,
    vix_close: float | None = None,
    vix_change_pct: float | None = None,
    usd_dxy_close: float | None = None,
    usd_dxy_change_pct: float | None = None,
    us10y_yield: float | None = None,
    us10y_change_bp: float | None = None,
    wti_crude_close: float | None = None,
    wti_crude_change_pct: float | None = None,
    gold_close: float | None = None,
    gold_change_pct: float | None = None,
    source_name: str = "market_data_provider",
) -> None:
    """Update cross-asset fields for an existing snapshot row."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE daily_market_snapshots
            SET
                vix_close = %(vix_close)s,
                vix_change_pct = %(vix_change_pct)s,
                usd_dxy_close = %(usd_dxy_close)s,
                usd_dxy_change_pct = %(usd_dxy_change_pct)s,
                us10y_yield = %(us10y_yield)s,
                us10y_change_bp = %(us10y_change_bp)s,
                wti_crude_close = %(wti_crude_close)s,
                wti_crude_change_pct = %(wti_crude_change_pct)s,
                gold_close = %(gold_close)s,
                gold_change_pct = %(gold_change_pct)s,
                source_name = %(source_name)s,
                fetched_at = NOW()
            WHERE stream_name = %(stream_name)s
              AND trading_date = %(trading_date)s
            """,
            {
                "stream_name": stream_name,
                "trading_date": trading_date,
                "vix_close": vix_close,
                "vix_change_pct": vix_change_pct,
                "usd_dxy_close": usd_dxy_close,
                "usd_dxy_change_pct": usd_dxy_change_pct,
                "us10y_yield": us10y_yield,
                "us10y_change_bp": us10y_change_bp,
                "wti_crude_close": wti_crude_close,
                "wti_crude_change_pct": wti_crude_change_pct,
                "gold_close": gold_close,
                "gold_change_pct": gold_change_pct,
                "source_name": source_name,
            },
        )
