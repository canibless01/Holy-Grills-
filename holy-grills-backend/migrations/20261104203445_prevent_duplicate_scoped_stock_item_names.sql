-- One ingredient name identifies one tracked balance in each campus.
-- Existing scoped names were checked for duplicates before applying.
CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_items_campus_normalized_name
ON public.stock_items (campus_id, lower(btrim(name)));
