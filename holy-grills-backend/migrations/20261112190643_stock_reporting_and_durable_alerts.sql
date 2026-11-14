-- Read-only stock reporting and transactional alerts. No balance/ledger backfill.
CREATE FUNCTION public.hg_stock_report(p_actor uuid,p_campus uuid,p_from date,p_to date)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE actor public.profiles%rowtype;result jsonb;start_at timestamptz;end_at timestamptz;
BEGIN
 SELECT * INTO actor FROM public.profiles WHERE id=p_actor;
 IF NOT FOUND OR NOT actor.is_active OR actor.role::text NOT IN ('admin','super_admin') OR
  (actor.role::text<>'super_admin' AND (p_campus IS NULL OR actor.campus_id IS DISTINCT FROM p_campus)) THEN RAISE EXCEPTION 'Stock report access denied' USING ERRCODE='42501';END IF;
 IF p_from IS NULL OR p_to IS NULL OR p_from>p_to OR p_to-p_from>366 OR p_to>(now() AT TIME ZONE 'Africa/Lagos')::date THEN RAISE EXCEPTION 'Invalid stock report dates' USING ERRCODE='22023';END IF;
 IF (SELECT count(*) FROM public.stock_items WHERE p_campus IS NULL OR campus_id=p_campus)>5000 THEN RAISE EXCEPTION 'Select a campus to report fewer than 5001 ingredients' USING ERRCODE='22023';END IF;
 start_at:=p_from::timestamp AT TIME ZONE 'Africa/Lagos';end_at:=(p_to+1)::timestamp AT TIME ZONE 'Africa/Lagos';
 WITH scoped AS (SELECT * FROM public.stock_items WHERE p_campus IS NULL OR campus_id=p_campus), totals AS (
  SELECT s.id,
   coalesce(sum(l.quantity_in_usage_units),0) ledger_balance,
   coalesce(sum(l.quantity_in_usage_units) FILTER(WHERE l.created_at<start_at),0) opening,
   coalesce(sum(l.quantity_in_usage_units) FILTER(WHERE l.created_at<end_at),0) closing,
   coalesce(sum(l.quantity_in_usage_units) FILTER(WHERE l.type='purchase' AND l.created_at>=start_at AND l.created_at<end_at),0) purchased,
   coalesce(-sum(l.quantity_in_usage_units) FILTER(WHERE l.type='usage' AND l.created_at>=start_at AND l.created_at<end_at),0) used,
   coalesce(-sum(l.quantity_in_usage_units) FILTER(WHERE l.type='waste' AND l.created_at>=start_at AND l.created_at<end_at),0) wasted,
   coalesce(sum(l.quantity_in_usage_units) FILTER(WHERE l.type='correction' AND l.created_at>=start_at AND l.created_at<end_at),0) corrected,
   coalesce(sum(l.cost) FILTER(WHERE l.type='purchase' AND l.created_at>=start_at AND l.created_at<end_at),0) purchase_cost,
   count(l.id) FILTER(WHERE l.type='purchase' AND l.cost IS NULL AND l.created_at>=start_at AND l.created_at<end_at) uncosted_purchases,
   count(l.id) FILTER(WHERE l.campus_id IS DISTINCT FROM s.campus_id) scope_mismatches
  FROM scoped s LEFT JOIN public.stock_ledger l ON l.stock_item_id=s.id GROUP BY s.id
 ) SELECT coalesce(jsonb_agg(jsonb_build_object('id',s.id,'campus_id',s.campus_id,'campus',c.name,'name',s.name,
   'unit',u.name,'archived',s.archived_at IS NOT NULL,'current_balance',s.current_balance,'ledger_balance',t.ledger_balance,
   'drift',s.current_balance-t.ledger_balance,'opening',t.opening,'closing',t.closing,'purchased',t.purchased,'used',t.used,'wasted',t.wasted,
   'corrected',t.corrected,'purchase_cost',t.purchase_cost,'uncosted_purchases',t.uncosted_purchases,'scope_mismatches',t.scope_mismatches,
   'low_stock',s.archived_at IS NULL AND s.current_balance<s.low_stock_threshold,'threshold',s.low_stock_threshold) ORDER BY c.name,s.name,s.id),'[]'::jsonb)
 INTO result FROM scoped s JOIN totals t ON t.id=s.id JOIN public.campuses c ON c.id=s.campus_id LEFT JOIN public.measurement_units u ON u.id=s.usage_unit_id;
 RETURN jsonb_build_object('items',result,'from_date',p_from,'to_date',p_to,'as_of',now());
END$$;
REVOKE ALL ON FUNCTION public.hg_stock_report(uuid,uuid,date,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_stock_report(uuid,uuid,date,date) TO service_role;

CREATE TABLE hg_internal.stock_low_episodes (
 stock_item_id uuid PRIMARY KEY REFERENCES public.stock_items(id),
 episode_id uuid NOT NULL DEFAULT gen_random_uuid(), opened_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE hg_internal.stock_low_episodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY stock_low_service ON hg_internal.stock_low_episodes FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.stock_low_episodes FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,DELETE ON hg_internal.stock_low_episodes TO service_role;

-- A trigger-only private definer allows authorized metadata edits to enqueue
-- operational notices without granting browser roles private outbox access.
CREATE FUNCTION hg_internal.capture_stock_low_notice() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE recipient public.profiles%rowtype;prefs public.notification_preferences%rowtype;channel_name text;notice uuid;body text;meta jsonb;episode uuid;
BEGIN
 IF NEW.archived_at IS NOT NULL OR NEW.current_balance>=NEW.low_stock_threshold THEN
  DELETE FROM hg_internal.stock_low_episodes WHERE stock_item_id=NEW.id;
  RETURN NULL;
 END IF;
 INSERT INTO hg_internal.stock_low_episodes(stock_item_id) VALUES(NEW.id) ON CONFLICT(stock_item_id) DO NOTHING RETURNING episode_id INTO episode;
 IF NOT FOUND THEN RETURN NULL;END IF;
 body:='Low stock alert: '''||NEW.name||''' balance ('||NEW.current_balance||') is below threshold ('||NEW.low_stock_threshold||').';
 FOR recipient IN SELECT * FROM public.profiles WHERE is_active AND (role::text='super_admin' OR (role::text='admin' AND campus_id=NEW.campus_id)) LOOP
  SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=recipient.id;
  FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
   IF channel_name='push' AND (recipient.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
   notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:stock-low:'||NEW.id||':'||episode||':'||recipient.id||':'||channel_name);
   meta:=jsonb_build_object('_dispatch_version',1,'reference_type','stock_item','reference_id',NEW.id,
    'template_data',jsonb_build_object('name',NEW.name,'balance',NEW.current_balance,'threshold',NEW.low_stock_threshold));
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
   VALUES(notice,recipient.id,'low_stock_ingredient','Low Stock Alert',body,channel_name,'/admin?section=store',NEW.campus_id,NEW.id,meta) ON CONFLICT(id) DO NOTHING;
   -- The normal INSERT trigger captures service-role calls. Authenticated
   -- metadata edits need the same private outbox receipt explicitly.
   IF channel_name='push' THEN
    INSERT INTO public.notification_deliveries(id,notification_id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
    VALUES(notice,notice,recipient.id,channel_name,'queued',NEW.campus_id,
     jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
     jsonb_build_object('notification',jsonb_build_object('user_id',recipient.id,'type','low_stock_ingredient','title','Low Stock Alert','body',body,
      'action_url','/admin?section=store','metadata',meta,'email',lower(trim(recipient.email::text)),'name',coalesce(nullif(recipient.nickname,''),nullif(recipient.full_name,''),'there')))) ON CONFLICT(id) DO NOTHING;
   END IF;
  END LOOP;
 END LOOP;
 RETURN NULL;
END$$;
REVOKE ALL ON FUNCTION hg_internal.capture_stock_low_notice() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.capture_stock_low_notice() TO service_role;
CREATE TRIGGER capture_stock_low_notice AFTER UPDATE OF current_balance,low_stock_threshold,archived_at ON public.stock_items
 FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_stock_low_notice();
