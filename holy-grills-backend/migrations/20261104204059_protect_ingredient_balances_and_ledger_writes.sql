-- Keep ingredient adjustments on the existing actor-checked, service-only RPC.
-- Metadata reads and zero-balance creation retain the existing campus RLS.
REVOKE UPDATE, DELETE ON public.stock_items FROM PUBLIC, anon, authenticated;
GRANT UPDATE (name, low_stock_threshold) ON public.stock_items TO authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.stock_ledger FROM PUBLIC, anon, authenticated;
DROP POLICY IF EXISTS stock_items_zero_opening_balance ON public.stock_items;
CREATE POLICY stock_items_zero_opening_balance ON public.stock_items AS RESTRICTIVE
FOR INSERT TO authenticated WITH CHECK (current_balance = 0);
