CREATE FUNCTION public.hg_tier_notice_valid(p_notice uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.notifications n JOIN public.user_tiers h ON h.id=n.reference_id JOIN public.profiles p ON p.id=n.user_id
 WHERE n.id=p_notice AND n.metadata->>'reference_type'='tier_transition' AND h.user_id=p.id AND p.is_active AND p.role::text='student'
 AND h.campus_id IS NOT DISTINCT FROM p.campus_id AND n.campus_id IS NOT DISTINCT FROM p.campus_id AND p.current_tier_id=h.tier_id
 AND (n.type<>'tier_grace_period' OR (h.event='grace' AND p.tier_grace_started_at=h.created_at AND p.tier_grace_ends_at>now())))
$$;
REVOKE ALL ON FUNCTION public.hg_tier_notice_valid(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_tier_notice_valid(uuid) TO service_role;
DO $$DECLARE definition text;needle text:=' UPDATE public.notification_deliveries SET dispatch_payload=';BEGIN
 definition:=pg_get_functiondef('public.hg_begin_notification_dispatch(uuid,uuid,jsonb)'::regprocedure);
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected dispatch definition';END IF;
 definition:=replace(definition,needle,E' IF d.dispatch_payload->''notification''->''metadata''->>''reference_type''=''tier_transition'' AND NOT public.hg_tier_notice_valid(d.notification_id) THEN\n'
  ||E'  UPDATE public.notification_deliveries SET status=''skipped'',error_message=''tier_notice_superseded'',dispatch=dispatch||jsonb_build_object(''state'',''skipped'') WHERE id=d.id;RETURN false;\n END IF;\n'||needle);
 EXECUTE definition;
END$$;
