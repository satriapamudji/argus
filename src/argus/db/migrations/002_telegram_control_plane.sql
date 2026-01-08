-- Migration: 002_telegram_control_plane
-- Description: Add Telegram control-plane tables (access requests + stream subscriptions + poller state)
-- Date: 2026-01-08

-- ============================================================================
-- telegram_chats: Known chats (DMs, groups, channels) that interacted with bot
-- ============================================================================
CREATE TABLE IF NOT EXISTS telegram_chats (
    chat_id BIGINT PRIMARY KEY,
    chat_type TEXT NOT NULL,
    chat_title TEXT,

    authorized BOOLEAN NOT NULL DEFAULT FALSE,
    authorized_at TIMESTAMPTZ,
    authorized_by_user_id BIGINT,

    blocked BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telegram_chats_authorized ON telegram_chats(authorized);

-- ============================================================================
-- telegram_chat_requests: Owner-approved access requests
-- ============================================================================
CREATE TABLE IF NOT EXISTS telegram_chat_requests (
    id BIGSERIAL PRIMARY KEY,

    chat_id BIGINT NOT NULL REFERENCES telegram_chats(chat_id) ON DELETE CASCADE,

    requested_by_user_id BIGINT,
    requested_by_username TEXT,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'denied')),

    deny_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by_user_id BIGINT
);

CREATE INDEX IF NOT EXISTS idx_telegram_chat_requests_status ON telegram_chat_requests(status);
CREATE INDEX IF NOT EXISTS idx_telegram_chat_requests_chat_id ON telegram_chat_requests(chat_id);

-- Prevent multiple pending requests per chat
CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_chat_requests_one_pending_per_chat
    ON telegram_chat_requests(chat_id)
    WHERE status = 'pending';

-- ============================================================================
-- telegram_stream_subscriptions: Self-serve subscriptions for authorized chats
-- ============================================================================
CREATE TABLE IF NOT EXISTS telegram_stream_subscriptions (
    chat_id BIGINT NOT NULL REFERENCES telegram_chats(chat_id) ON DELETE CASCADE,
    stream_name TEXT NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    enabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enabled_by_user_id BIGINT,
    disabled_at TIMESTAMPTZ,

    PRIMARY KEY (chat_id, stream_name)
);

CREATE INDEX IF NOT EXISTS idx_telegram_stream_subscriptions_stream_enabled
    ON telegram_stream_subscriptions(stream_name)
    WHERE enabled = TRUE;

-- ============================================================================
-- telegram_bot_state: Persist poller offset across restarts
-- ============================================================================
CREATE TABLE IF NOT EXISTS telegram_bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Record this migration
INSERT INTO schema_migrations (version) VALUES ('002_telegram_control_plane');
