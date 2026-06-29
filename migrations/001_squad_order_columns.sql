-- Migration: Add Squad Order columns to orders table
-- Run once against the live database.
-- Safe to re-run (IF NOT EXISTS / idempotent defaults).

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS is_squad_order       BOOLEAN        NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS squad_discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS squad_item_count      INTEGER        NOT NULL DEFAULT 0;

-- Index for analytics queries filtering squad orders
CREATE INDEX IF NOT EXISTS idx_orders_is_squad_order
  ON orders (is_squad_order)
  WHERE is_squad_order = TRUE;

-- Backfill: any existing order with total_qty >= 3 can be flagged
-- (optional — leave commented out unless historical backfill is desired)
-- UPDATE orders
-- SET is_squad_order = TRUE
-- WHERE id IN (
--   SELECT order_id
--   FROM (
--     SELECT order_id, SUM(quantity) AS total_qty
--     FROM order_items
--     WHERE is_addon = FALSE
--     GROUP BY order_id
--   ) sub
--   WHERE total_qty >= 3
-- );

COMMENT ON COLUMN orders.is_squad_order        IS 'True when the cart qualified for a squad-order discount (MIN_ITEMS ≤ qty ≤ MAX_ITEMS)';
COMMENT ON COLUMN orders.squad_discount_amount IS 'Naira value discounted from the subtotal due to squad-order promotion (0 when not a squad order)';
COMMENT ON COLUMN orders.squad_item_count      IS 'Total non-addon item quantity used to determine squad eligibility';
