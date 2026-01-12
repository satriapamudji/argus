-- Migration: 005_daily_market_snapshots
-- Description: Persist daily market snapshots for weekly stats
-- Date: 2026-01-12
--
-- Stores end-of-day market snapshot data (indices + optional cross-assets)
-- for weekly recap stats and historical context.

BEGIN;

-- ============================================================================
-- daily_market_snapshots: Immutable daily market snapshot per stream
-- ============================================================================
CREATE TABLE IF NOT EXISTS daily_market_snapshots (
    id BIGSERIAL PRIMARY KEY,
    stream_name VARCHAR(100) NOT NULL,

    -- Trading date in market's local calendar (for US markets: America/New_York)
    trading_date DATE NOT NULL,

    -- US indices
    sp500_close DOUBLE PRECISION,
    sp500_change_pct DOUBLE PRECISION,
    dow_close DOUBLE PRECISION,
    dow_change_pct DOUBLE PRECISION,
    nasdaq_close DOUBLE PRECISION,
    nasdaq_change_pct DOUBLE PRECISION,

    -- Optional cross-assets (nullable)
    vix_close DOUBLE PRECISION,
    vix_change_pct DOUBLE PRECISION,
    usd_dxy_close DOUBLE PRECISION,
    usd_dxy_change_pct DOUBLE PRECISION,
    us10y_yield DOUBLE PRECISION,
    us10y_change_bp DOUBLE PRECISION,
    wti_crude_close DOUBLE PRECISION,
    wti_crude_change_pct DOUBLE PRECISION,
    gold_close DOUBLE PRECISION,
    gold_change_pct DOUBLE PRECISION,

    -- Metadata
    source_name VARCHAR(100) NOT NULL DEFAULT 'market_data_provider',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Assert at least the core indices are present
    CHECK (
        sp500_close IS NOT NULL
        AND dow_close IS NOT NULL
        AND nasdaq_close IS NOT NULL
    )
);

-- One snapshot per stream per trading date
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_market_snapshots_stream_date
    ON daily_market_snapshots(stream_name, trading_date);

-- Common access patterns: pull ranges + latest-before-anchor
CREATE INDEX IF NOT EXISTS idx_daily_market_snapshots_stream_date_desc
    ON daily_market_snapshots(stream_name, trading_date DESC);

-- Support ad-hoc lookups by date
CREATE INDEX IF NOT EXISTS idx_daily_market_snapshots_trading_date
    ON daily_market_snapshots(trading_date);

-- ============================================================================
-- Record migration
-- ============================================================================
INSERT INTO schema_migrations (version) VALUES ('005_daily_market_snapshots');

COMMIT;
