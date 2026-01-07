-- Migration: 002_economic_calendar
-- Description: Create economic calendar events table for ForexFactory data
-- Date: 2026-01-07

-- ============================================================================
-- economic_calendar_events: Economic calendar data from ForexFactory
-- Stores high-impact economic events for the "Key Dates (UTC)" section.
-- ============================================================================
CREATE TABLE economic_calendar_events (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    country VARCHAR(10) NOT NULL,          -- 'USD', 'EUR', 'GBP', etc.
    event_timestamp TIMESTAMPTZ NOT NULL,  -- Event time in UTC
    impact TEXT NOT NULL                   -- 'High', 'Medium', 'Low', 'Holiday'
        CHECK (impact IN ('High', 'Medium', 'Low', 'Holiday')),
    forecast TEXT,                         -- e.g., '66K', '3.2%'
    previous TEXT,                         -- e.g., '64K', '3.1%'
    actual TEXT,                           -- Filled after event occurs
    source TEXT NOT NULL DEFAULT 'forexfactory',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Unique constraint for deduplication
    -- Same event from same source/country at same time = same record
    UNIQUE(title, event_timestamp, source, country)
);

-- Index for upcoming events query (filtered by High impact)
-- This is the most common query pattern for bundle building
CREATE INDEX idx_econ_cal_upcoming 
    ON economic_calendar_events(event_timestamp, impact) 
    WHERE impact = 'High';

-- Index for country filtering
CREATE INDEX idx_econ_cal_country 
    ON economic_calendar_events(country);

-- Index for staleness check (most recent fetch)
-- Used to determine if data needs refresh
CREATE INDEX idx_econ_cal_fetched 
    ON economic_calendar_events(fetched_at DESC);

-- Index for source queries (future-proofing for multiple sources)
CREATE INDEX idx_econ_cal_source 
    ON economic_calendar_events(source);

-- Record this migration
INSERT INTO schema_migrations (version) VALUES ('002_economic_calendar');
