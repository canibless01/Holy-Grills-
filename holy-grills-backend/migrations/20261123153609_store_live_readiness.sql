-- Public choices expose safe store data, and only an operational campus team.
CREATE FUNCTION public.hg_order_store_choices(p_campus uuid,p_pickup boolean) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',s.id,'campus_id',s.campus_id,'name',s.name,'address',s.address,'instructions',s.instructions,'lat',s.lat,'lon',s.lon) ORDER BY s.name,s.id),'[]')
 FROM stores s JOIN campuses c ON c.id=s.campus_id WHERE c.id=p_campus AND c.is_active AND s.is_active
  AND (CASE WHEN p_pickup THEN s.pickup_enabled ELSE s.delivery_enabled AND s.lat IS NOT NULL AND s.lon IS NOT NULL END)
  AND EXISTS(SELECT 1 FROM hg_internal.store_staff m JOIN profiles p ON p.id=m.user_id WHERE m.store_id=s.id AND p.is_active AND p.campus_id=s.campus_id AND p.role::text='kitchen')
  AND (p_pickup OR EXISTS(SELECT 1 FROM hg_internal.store_staff m JOIN profiles p ON p.id=m.user_id WHERE m.store_id=s.id AND p.is_active AND p.campus_id=s.campus_id AND p.role::text='rider'));
$$;
REVOKE ALL ON FUNCTION public.hg_order_store_choices(uuid,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_order_store_choices(uuid,boolean) TO service_role;

DO $ready$
DECLARE body text;before_text text;after_text text;
BEGIN
 SELECT pg_get_functiondef('hg_internal.guard_order_store_attribution()'::regprocedure) INTO body;
 before_text:=$old$ NEW.fulfilment_store_snapshot:=$old$;
 after_text:=$new$ IF NOT EXISTS(SELECT 1 FROM hg_internal.store_staff m JOIN profiles p ON p.id=m.user_id WHERE m.store_id=s.id AND p.is_active AND p.campus_id=s.campus_id AND p.role::text='kitchen')
 OR (NEW.delivery_type<>'store_pickup' AND NOT EXISTS(SELECT 1 FROM hg_internal.store_staff m JOIN profiles p ON p.id=m.user_id WHERE m.store_id=s.id AND p.is_active AND p.campus_id=s.campus_id AND p.role::text='rider')) THEN RAISE EXCEPTION 'HG_STORE_ORDER_UNAVAILABLE' USING ERRCODE='23514';END IF;
 NEW.fulfilment_store_snapshot:=$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store attribution source changed';END IF;
 EXECUTE replace(body,before_text,after_text);
END $ready$;
NOTIFY pgrst,'reload schema';
