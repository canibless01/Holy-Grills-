-- service_role deliberately cannot SELECT auth.users. Expose one bounded,
-- private verified-email read rather than broad Auth-table grants.
CREATE OR REPLACE FUNCTION hg_internal.verified_event_ticket_email(p_actor uuid)
RETURNS text LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT lower(btrim(u.email)) FROM auth.users u
 WHERE u.id=p_actor AND u.email_confirmed_at IS NOT NULL
 AND coalesce(auth.role(),'')='service_role';
$$;
REVOKE ALL ON FUNCTION hg_internal.verified_event_ticket_email(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.verified_event_ticket_email(uuid) TO service_role;
DO $migration$
DECLARE definition text;
BEGIN
 definition:=pg_get_functiondef('public.hg_link_verified_event_tickets(uuid)'::regprocedure);
 IF position('FROM auth.users u JOIN public.profiles' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected verified ticket helper';END IF;
 definition:=replace(definition,
 'SELECT lower(btrim(u.email)) INTO verified_email FROM auth.users u JOIN public.profiles p ON p.id=u.id WHERE u.id=p_actor AND u.email_confirmed_at IS NOT NULL AND p.is_active;',
 'SELECT hg_internal.verified_event_ticket_email(p_actor) INTO verified_email FROM public.profiles p WHERE p.id=p_actor AND p.is_active;');
 EXECUTE definition;
END $migration$;
