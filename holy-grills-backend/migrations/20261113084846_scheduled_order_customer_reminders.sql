CREATE POLICY customer_reminder_receipts_private ON public.order_status_logs AS RESTRICTIVE FOR ALL TO anon,authenticated USING (NOT metadata ? 'customer_reminder_day') WITH CHECK (NOT metadata ? 'customer_reminder_day');
CREATE INDEX IF NOT EXISTS orders_scheduled_reminder_due ON public.orders(scheduled_for,id) WHERE is_scheduled AND NOT coalesce(is_test,false);
CREATE FUNCTION public.hg_scheduled_order_reminder_valid(p_order uuid,p_user uuid,p_day date,p_email text) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.orders o LEFT JOIN public.profiles p ON p.id=o.user_id JOIN public.campuses c ON c.id=o.campus_id AND c.is_active
 WHERE o.id=p_order AND o.user_id IS NOT DISTINCT FROM p_user AND o.is_scheduled AND NOT coalesce(o.is_test,false)
 AND o.payment_status::text IN ('paid','partially_refunded') AND o.status::text IN ('received','paid','preparing','ready','assigned','out_for_delivery')
 AND (o.scheduled_for AT TIME ZONE 'Africa/Lagos')::date=p_day AND p_day=(now() AT TIME ZONE 'Africa/Lagos')::date
 AND (p_user IS NULL OR (p.is_active AND p.role::text<>'super_admin'))
 AND lower(trim(coalesce(p.email::text,o.guest_email::text,'')))=lower(trim(coalesce(p_email,''))))
$$;
CREATE FUNCTION public.hg_queue_scheduled_order_reminders(p_hour integer DEFAULT 10,p_campus uuid DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;ord public.orders%rowtype;person public.profiles%rowtype;prefs public.notification_preferences%rowtype;
 ref uuid;notice uuid;channel_name text;channels text[];email text;body text;meta jsonb;ids jsonb:='[]';orders_count integer:=0;day_end timestamptz:=(today+1)::timestamp AT TIME ZONE 'Africa/Lagos';
BEGIN
 IF p_hour IS NULL OR p_hour<0 OR p_hour>23 THEN RAISE EXCEPTION 'Invalid reminder hour';END IF;
 IF extract(hour from now() AT TIME ZONE 'Africa/Lagos')<p_hour THEN RETURN jsonb_build_object('orders',0,'notification_ids',ids);END IF;
 FOR ord IN SELECT o.* FROM public.orders o JOIN public.campuses c ON c.id=o.campus_id AND c.is_active
 WHERE (p_campus IS NULL OR o.campus_id=p_campus) AND o.is_scheduled AND NOT coalesce(o.is_test,false) AND o.payment_status::text IN ('paid','partially_refunded')
 AND o.status::text IN ('received','paid','preparing','ready','assigned','out_for_delivery')
 AND o.scheduled_for>=today::timestamp AT TIME ZONE 'Africa/Lagos' AND o.scheduled_for<day_end
 AND NOT EXISTS(SELECT 1 FROM public.order_status_logs l WHERE l.order_id=o.id AND l.metadata->>'customer_reminder_day'=today::text)
 ORDER BY o.scheduled_for,o.id LIMIT 100 FOR UPDATE OF o SKIP LOCKED LOOP
  SELECT * INTO person FROM public.profiles WHERE id=ord.user_id;
  SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=ord.user_id;
  email:=lower(trim(coalesce(person.email::text,ord.guest_email::text,'')));
  IF ord.user_id IS NOT NULL AND (person.id IS NULL OR person.is_active IS NOT TRUE OR person.role::text='super_admin') THEN CONTINUE;END IF;
  ref:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:scheduled-order-day:'||ord.id||':'||today);
  body:='Your Holy Grills order #'||upper(left(ord.id::text,8))||' is due for delivery today. Please keep your phone switched on, nearby and available for our rider''s call. If you chose gate pickup, please be ready to meet the rider at your selected gate.';
  meta:=jsonb_build_object('_dispatch_version',1,'reference_type','scheduled_order_reminder','reference_id',ref,'order_id',ord.id,'scheduled_date',today);
  channels:=CASE WHEN ord.user_id IS NULL THEN ARRAY['email'] ELSE ARRAY['in_app','push','email'] END;
  FOREACH channel_name IN ARRAY channels LOOP
   IF ord.user_id IS NOT NULL AND (prefs.order_updates IS FALSE OR (channel_name='push' AND (person.push_enabled IS FALSE OR prefs.push_enabled IS FALSE)) OR (channel_name='email' AND (person.email_notifications IS FALSE OR prefs.email_enabled IS FALSE))) THEN CONTINUE;END IF;
   IF channel_name='email' AND (email='' OR (ord.user_id IS NULL AND ord.claim_token IS NULL)) THEN CONTINUE;END IF;
   notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:scheduled-order-notice:'||ref||':'||channel_name);
   IF ord.user_id IS NOT NULL THEN
    INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
    VALUES(notice,ord.user_id,'scheduled_order_reminder','Your Holy Grills order is coming today',body,channel_name,'/orders/'||ord.id,ord.campus_id,ref,meta) ON CONFLICT(id) DO NOTHING;
   ELSE
    INSERT INTO public.notification_deliveries(id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
    VALUES(notice,NULL,'email','queued',ord.campus_id,
     jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',day_end),
     jsonb_build_object('notification',jsonb_build_object('user_id',NULL,'type','scheduled_order_reminder','title','Your Holy Grills order is coming today','body',body,'email',email,'name',coalesce(nullif(ord.guest_name,''),'there'),'metadata',meta))) ON CONFLICT(id) DO NOTHING;
   END IF;
   IF channel_name IN ('email','push') THEN
    UPDATE public.notification_deliveries SET dispatch=jsonb_set(dispatch,'{expires_at}',to_jsonb(day_end)) WHERE id=notice;
    ids:=ids||jsonb_build_array(notice);
   END IF;
  END LOOP;
  INSERT INTO public.order_status_logs(order_id,status,campus_id,metadata) VALUES(ord.id,ord.status,ord.campus_id,jsonb_build_object('customer_reminder_day',today));
  orders_count:=orders_count+1;
 END LOOP;
 RETURN jsonb_build_object('orders',orders_count,'notification_ids',ids);
END$$;
REVOKE ALL ON FUNCTION public.hg_queue_scheduled_order_reminders(integer,uuid),public.hg_scheduled_order_reminder_valid(uuid,uuid,date,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_queue_scheduled_order_reminders(integer,uuid),public.hg_scheduled_order_reminder_valid(uuid,uuid,date,text) TO service_role;
-- Last eligibility check at external-provider handoff, not just at generation.
DO $$DECLARE definition text;needle text:=' UPDATE public.notification_deliveries SET dispatch_payload=';BEGIN
 definition:=pg_get_functiondef('public.hg_begin_notification_dispatch(uuid,uuid,jsonb)'::regprocedure);
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected dispatch definition';END IF;
 definition:=replace(definition,needle,E' IF d.dispatch_payload->''notification''->>''type''=''scheduled_order_reminder'' AND NOT public.hg_scheduled_order_reminder_valid(\n'
  ||E'  (d.dispatch_payload->''notification''->''metadata''->>''order_id'')::uuid,(d.dispatch_payload->''notification''->>''user_id'')::uuid,\n'
  ||E'  (d.dispatch_payload->''notification''->''metadata''->>''scheduled_date'')::date,d.dispatch_payload->''notification''->>''email'') THEN\n'
  ||E'  UPDATE public.notification_deliveries SET status=''cancelled'',error_message=''scheduled_order_no_longer_due'',dispatch=dispatch||jsonb_build_object(''state'',''cancelled'') WHERE id=d.id;RETURN false;\n END IF;\n'||needle);
 EXECUTE definition;
END$$;
