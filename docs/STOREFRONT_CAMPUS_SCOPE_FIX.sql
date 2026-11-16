-- Public CMS reads are global or own-campus; an active super admin keeps all scopes.
-- Guests use the backend's bounded query after _get_campus_id validates selection.
-- Reuses existing campus helpers, table keys, JSON content and write policies.
DO $cms_scope$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['storefront_sections', 'banners'] LOOP
    EXECUTE format(
      'CREATE POLICY %I ON public.%I AS RESTRICTIVE FOR SELECT TO anon, authenticated USING (campus_id IS NULL OR campus_id = (SELECT public.hg_user_campus_id()) OR public.hg_is_campus_admin(campus_id))',
      target || ': enforce CMS campus reads', target
    );
  END LOOP;
END
$cms_scope$;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON public.storefront_sections, public.banners FROM anon, authenticated;

-- Supplemental migration: restrict_anonymous_cms_writes.
-- Authenticated staff keep INSERT/UPDATE/DELETE under existing campus RLS.
REVOKE INSERT, UPDATE, DELETE ON public.storefront_sections, public.banners FROM anon;
