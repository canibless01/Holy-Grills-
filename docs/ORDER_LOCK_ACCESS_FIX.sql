-- Lock date, reward and state mutations belong to the validated backend.
-- Reuses the existing table, owner/admin SELECT policy, and unique active-lock index.
-- Deploy order_locks.py's bounded service writes together with this grant change.
BEGIN;
DROP POLICY IF EXISTS "order_locks: admin insert" ON public.order_locks;
DROP POLICY IF EXISTS "order_locks: admin delete" ON public.order_locks;
DROP POLICY IF EXISTS "order_locks: owner or admin update" ON public.order_locks;
REVOKE ALL ON public.order_locks FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.order_locks TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.order_locks TO service_role;
REVOKE EXECUTE ON FUNCTION public.hg_protect_order_locks_columns() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_protect_order_locks_columns() TO service_role;
COMMIT;
