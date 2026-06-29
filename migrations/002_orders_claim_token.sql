-- Migration: Add claim_token column to orders table for guest order claiming
-- Run once against the live database.
-- Safe to re-run (IF NOT EXISTS / idempotent).

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS claim_token UUID DEFAULT NULL;

-- Index for fast lookup when a guest submits their claim token
CREATE INDEX IF NOT EXISTS idx_orders_claim_token
  ON orders (claim_token)
  WHERE claim_token IS NOT NULL;

COMMENT ON COLUMN orders.claim_token IS 'UUID token set on guest orders; used by POST /orders/:id/claim to link a guest order to a newly registered account';
