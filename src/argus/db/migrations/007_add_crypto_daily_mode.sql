-- Add crypto_daily to allowed run_mode values in runs table
-- This is required for Task 28 - Crypto Stream Implementation

ALTER TABLE runs DROP CONSTRAINT runs_run_mode_check;

ALTER TABLE runs
ADD CONSTRAINT runs_run_mode_check
CHECK (run_mode IN ('us_close', 'weekend_wrap', 'monday_preview', 'crypto_daily'));
