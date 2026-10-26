-- Migration: Add email tracking support to notification_blasts
-- Date: 2026-10-26
-- Description: Add tracking_enabled flag to enable/disable open and click tracking

ALTER TABLE notification_blasts 
  ADD COLUMN IF NOT EXISTS tracking_enabled BOOLEAN DEFAULT FALSE;

-- Add index for faster analytics queries
CREATE INDEX IF NOT EXISTS idx_notification_blasts_tracking_enabled 
  ON notification_blasts(tracking_enabled) 
  WHERE tracking_enabled = TRUE;

-- Update metadata column comment to document analytics fields
COMMENT ON COLUMN notification_blasts.metadata IS 'JSONB field containing:
- open_events: Array of open events (timestamp, ip, user_agent)
- open_count: Total number of opens
- last_opened_at: Timestamp of last open
- click_events: Array of click events (timestamp, url, label, ip, user_agent)
- click_count: Total number of clicks
- link_clicks: Object mapping URLs to click counts and labels
';
