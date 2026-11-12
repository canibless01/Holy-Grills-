-- Match existing HTTP authorization: deactivation removes staff privileges even
-- while a previously issued access token is still cryptographically valid.
-- Existing active identities and function execution grants remain unchanged.
CREATE OR REPLACE FUNCTION public.hg_current_user_role() RETURNS public.user_role
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT role FROM public.profiles WHERE id=auth.uid() AND is_active LIMIT 1
$$;
CREATE OR REPLACE FUNCTION public.hg_is_admin() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.profiles WHERE id=(SELECT auth.uid()) AND is_active AND role IN ('admin'::public.user_role,'super_admin'::public.user_role))
$$;
