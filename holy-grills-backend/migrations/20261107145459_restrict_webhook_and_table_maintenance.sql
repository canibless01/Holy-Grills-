-- Browser/Data API roles do not perform table maintenance. TRUNCATE bypasses RLS.
REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon, authenticated;
-- Application migrations create tables as postgres. Keep future app tables safe too.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
 REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM PUBLIC, anon, authenticated;

-- A stored provider payload is trusted on administrative replay. Only the backend
-- may create/alter/delete it; scoped admins retain read access through RLS.
REVOKE INSERT, UPDATE, DELETE ON public.webhook_events FROM PUBLIC, anon, authenticated;
DROP POLICY IF EXISTS "Admins manage webhook_events" ON public.webhook_events;
DROP POLICY IF EXISTS "webhook_events: campus admins read own" ON public.webhook_events;
CREATE POLICY webhook_events_admin_read ON public.webhook_events
 FOR SELECT TO authenticated USING (public.hg_is_campus_admin(campus_id));
GRANT SELECT ON public.webhook_events TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.webhook_events TO service_role;
