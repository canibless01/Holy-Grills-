-- Global release flags: campus admins can read; active super admins can write.
-- Reuses the existing active-profile helper and policy name. No new objects.
BEGIN;
DROP POLICY IF EXISTS feature_flags_admin_write ON public.feature_flags;
CREATE POLICY feature_flags_admin_write ON public.feature_flags FOR ALL TO authenticated
USING (public.hg_is_campus_admin(NULL::uuid))
WITH CHECK (public.hg_is_campus_admin(NULL::uuid) AND campus_id IS NULL);
REVOKE ALL ON public.feature_flags FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.feature_flags TO anon,authenticated;
GRANT INSERT,UPDATE,DELETE ON public.feature_flags TO authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.feature_flags TO service_role;
COMMIT;
