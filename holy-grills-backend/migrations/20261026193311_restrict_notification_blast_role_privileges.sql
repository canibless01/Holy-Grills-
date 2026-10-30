-- Anonymous clients never administer campaigns. RLS continues to restrict
-- authenticated CRUD to campus administrators; workers retain service access.
REVOKE ALL PRIVILEGES ON TABLE public.notification_blasts FROM anon;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE public.notification_blasts FROM authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.notification_blasts TO authenticated;
GRANT ALL PRIVILEGES ON TABLE public.notification_blasts TO service_role;
