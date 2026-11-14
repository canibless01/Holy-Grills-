SET LOCAL request.jwt.claims='{"role":"service_role"}';
ALTER TABLE hg_internal.operations_emails ADD COLUMN available_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX operations_emails_available ON hg_internal.operations_emails(available_at,created_at) WHERE state='pending';
CREATE OR REPLACE FUNCTION public.hg_operations_summary_window(p_campus uuid, p_start timestamptz, p_end timestamptz)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'public'
AS $function$
DECLARE result jsonb;v_start_at timestamptz:=p_start;v_end_at timestamptz:=p_end;
BEGIN
 IF p_campus IS NULL OR p_start IS NULL OR p_end IS NULL OR p_end<=p_start OR p_end-p_start>interval '32 days' THEN RAISE EXCEPTION 'Invalid report range'; END IF;
 SELECT jsonb_build_object(
  'from',(p_start AT TIME ZONE 'Africa/Lagos')::date,'to',(p_end AT TIME ZONE 'Africa/Lagos')::date,'period_start',p_start,'period_end',p_end,'as_of',now(),
  'signups',(SELECT count(*) FROM public.reporting_profiles WHERE campus_id=p_campus AND created_at>=v_start_at AND created_at<v_end_at),
  'paid_orders',count(*) FILTER(WHERE payment_status::text IN ('paid','partially_refunded','refunded')),
  'order_value',coalesce(sum(total_amount) FILTER(WHERE payment_status::text IN ('paid','partially_refunded','refunded')),0),
  'refunds_on_orders',coalesce(sum(coalesce(card_refund_total,0)+coalesce(wallet_refund_total,0)) FILTER(WHERE payment_status::text IN ('paid','partially_refunded','refunded')),0),
  'wallet_funded',(SELECT coalesce(sum(amount),0) FROM public.reporting_wallet_transactions WHERE campus_id=p_campus AND created_at>=v_start_at AND created_at<v_end_at AND type='credit' AND provider='paystack' AND reference_type IN ('topup','bank_transfer')),
  'auto_funding_setups',(SELECT count(*) FROM hg_internal.wallet_funding_plans f JOIN public.reporting_profiles p ON p.id=f.user_id WHERE f.campus_id=p_campus AND f.created_at>=v_start_at AND f.created_at<v_end_at AND successful_payments>0),
  'auto_funded',(SELECT coalesce(sum(t.amount),0) FROM public.reporting_wallet_transactions t WHERE t.campus_id=p_campus AND t.created_at>=v_start_at AND t.created_at<v_end_at AND EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts a WHERE a.transaction_id=t.id AND a.state='succeeded')),
  'event_tickets',(SELECT coalesce(sum(quantity),0) FROM public.reporting_event_tickets WHERE campus_id=p_campus AND created_at>=v_start_at AND created_at<v_end_at AND status='confirmed' AND payment_status IN ('paid','free')),
  'marketplace_purchases',(SELECT count(*) FROM public.reporting_marketplace_purchases WHERE campus_id=p_campus AND created_at>=v_start_at AND created_at<v_end_at AND status NOT IN ('cancelled','refunded','pending')),
  'abandoned_carts',(SELECT count(*) FROM public.reporting_abandoned_carts WHERE campus_id=p_campus AND created_at>=v_start_at AND created_at<v_end_at),
  'recovered_carts',(SELECT count(*) FROM public.reporting_abandoned_carts c JOIN public.reporting_orders o ON o.id=c.recovered_order_id WHERE c.campus_id=p_campus AND c.is_recovered AND o.payment_status::text IN ('paid','partially_refunded') AND c.recovered_at>=v_start_at AND c.recovered_at<v_end_at)
 ) INTO result FROM public.reporting_orders WHERE campus_id=p_campus AND created_at>=v_start_at AND created_at<v_end_at;
 RETURN result;
END $function$;
REVOKE ALL ON FUNCTION public.hg_operations_summary_window(uuid,timestamptz,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_operations_summary_window(uuid,timestamptz,timestamptz) TO service_role;

-- NULL means no longer actionable. A future time means wait, then read again.
CREATE FUNCTION public.hg_operations_cart_alert_due(p_cart uuid) RETURNS timestamptz
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE cart public.abandoned_carts%rowtype;owner public.profiles%rowtype;pending public.orders%rowtype;
 latest_item timestamptz;latest_checkout timestamptz;activity timestamptz;minutes integer;
BEGIN
 SELECT * INTO cart FROM public.reporting_abandoned_carts WHERE id=p_cart AND NOT is_recovered;
 IF NOT FOUND OR cart.last_active_at IS NULL THEN RETURN NULL; END IF;
 activity:=cart.last_active_at;
 IF cart.user_id IS NOT NULL THEN
  SELECT * INTO owner FROM public.profiles WHERE id=cart.user_id AND is_active AND role::text<>'super_admin';
  IF NOT FOUND THEN RETURN NULL; END IF;
  SELECT max(updated_at) INTO latest_item FROM public.cart_items WHERE user_id=cart.user_id AND campus_id=cart.campus_id;
  IF latest_item>cart.last_active_at THEN RETURN NULL; END IF;
  activity:=greatest(activity,owner.last_seen_at);
 END IF;
 IF cart.cart_payload->>'pending_order_id' IS NOT NULL THEN
  SELECT * INTO pending FROM public.reporting_orders WHERE id::text=cart.cart_payload->>'pending_order_id' AND campus_id=cart.campus_id;
  IF NOT FOUND OR pending.user_id IS DISTINCT FROM cart.user_id OR pending.payment_status::text<>'pending' OR pending.status::text<>'received' THEN RETURN NULL; END IF;
  IF cart.user_id IS NULL AND (pending.guest_email IS DISTINCT FROM cart.guest_email OR pending.guest_phone IS DISTINCT FROM cart.guest_phone) THEN RETURN NULL; END IF;
  activity:=greatest(activity,pending.created_at);
 ELSIF latest_item IS NULL THEN RETURN NULL;
 END IF;
 IF EXISTS(SELECT 1 FROM public.reporting_orders o WHERE o.campus_id=cart.campus_id AND o.created_at>=cart.last_active_at AND o.payment_status::text IN ('paid','partially_refunded')
  AND (o.user_id=cart.user_id OR (cart.user_id IS NULL AND o.user_id IS NULL AND o.guest_email=cart.guest_email))) THEN RETURN NULL; END IF;
 SELECT max(o.created_at) INTO latest_checkout FROM public.reporting_orders o WHERE o.campus_id=cart.campus_id AND o.payment_status::text='pending' AND o.status::text='received'
  AND (o.user_id=cart.user_id OR (cart.user_id IS NULL AND o.user_id IS NULL AND o.guest_email=cart.guest_email));
 IF pending.id IS NOT NULL AND latest_checkout>pending.created_at THEN RETURN NULL; END IF;
 activity:=greatest(activity,latest_checkout);
 SELECT greatest(30,(value->>'abandoned_minutes')::integer) INTO minutes FROM public.system_settings WHERE key='campus_operations_email' AND campus_id=cart.campus_id AND NOT is_public;
 RETURN activity+make_interval(mins=>coalesce(minutes,30));
END $$;
REVOKE ALL ON FUNCTION public.hg_operations_cart_alert_due(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_operations_cart_alert_due(uuid) TO service_role;
CREATE OR REPLACE FUNCTION public.hg_validate_operations_email_setting()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE email text; k text;
BEGIN
 IF NEW.key='campus_cart_recovery' THEN
  IF NEW.campus_id IS NULL OR NEW.is_public IS DISTINCT FROM false OR jsonb_typeof(NEW.value)<>'object'
    OR coalesce(NEW.value->>'initial_minutes','')!~'^[0-9]+$' OR (NEW.value->>'initial_minutes')::integer NOT BETWEEN 10 AND 1440
    OR coalesce(NEW.value->>'repeat_minutes','')!~'^[0-9]+$' OR (NEW.value->>'repeat_minutes')::integer NOT BETWEEN 30 AND 1440
    OR coalesce(NEW.value->>'max_hours','')!~'^[0-9]+$' OR (NEW.value->>'max_hours')::integer NOT BETWEEN 1 AND 48 THEN RAISE EXCEPTION 'Invalid private campus cart recovery timing'; END IF;
  RETURN NEW;
 END IF;
 IF NEW.key<>'campus_operations_email' THEN RETURN NEW; END IF;
 IF NEW.campus_id IS NULL OR NEW.is_public IS DISTINCT FROM false OR jsonb_typeof(NEW.value)<>'object'
  OR jsonb_typeof(NEW.value->'recipients') IS DISTINCT FROM 'array'
  OR jsonb_array_length(NEW.value->'recipients')>5 THEN RAISE EXCEPTION 'Operations email needs a private campus setting and up to five recipients'; END IF;
 FOR email IN SELECT jsonb_array_elements_text(NEW.value->'recipients') LOOP
  IF email IS NULL OR length(email)>254 OR email !~* '^[a-z0-9.!#$%&''*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}$' THEN RAISE EXCEPTION 'Invalid operations email recipient'; END IF;
 END LOOP;
 FOREACH k IN ARRAY ARRAY['paid_order_alerts','abandoned_cart_alerts','daily_report','weekly_report'] LOOP
  IF jsonb_typeof(NEW.value->k) IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'Operations email switches must be boolean'; END IF;
 END LOOP;
 IF coalesce(NEW.value->>'abandoned_minutes','') !~ '^[0-9]+$' OR (NEW.value->>'abandoned_minutes')::integer NOT BETWEEN 30 AND 1440 THEN RAISE EXCEPTION 'Abandonment delay must be 30 to 1440 minutes'; END IF;
 IF NEW.value ? 'daily_report_time' AND (jsonb_typeof(NEW.value->'daily_report_time') IS DISTINCT FROM 'string' OR NEW.value->>'daily_report_time' !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$') THEN RAISE EXCEPTION 'Daily report time must be HH:MM in Nigeria time'; END IF;
 RETURN NEW;
END $function$;
CREATE OR REPLACE FUNCTION public.hg_capture_operations_emails(p_campus uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE report_start timestamptz;report_end timestamptz;report_clock time;cfg record;c record;day date;first_day date;last_day date;sync_delay interval;today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;delay interval;n integer:=0;
BEGIN
 IF NOT pg_try_advisory_xact_lock(hashtextextended('hg-operations-capture',0)) THEN RETURN '{"skipped":true}'; END IF;
 FOR cfg IN SELECT campus.id campus_id,coalesce(s.value,'{"recipients":[],"abandoned_minutes":30,"daily_report":false,"weekly_report":false}'::jsonb) value,coalesce(s.updated_at,now()-interval '48 hours') updated_at FROM public.campuses campus LEFT JOIN public.system_settings s ON s.campus_id=campus.id AND s.key='campus_operations_email' AND NOT s.is_public WHERE campus.is_active AND (p_campus IS NULL OR campus.id=p_campus) LOOP
  delay:=make_interval(mins=>greatest(30,(cfg.value->>'abandoned_minutes')::integer));
  report_clock:=coalesce(cfg.value->>'daily_report_time','21:00')::time;
  sync_delay:=least(delay,make_interval(mins=>coalesce((SELECT (value->>'initial_minutes')::integer FROM public.system_settings WHERE key='campus_cart_recovery' AND campus_id=cfg.campus_id),30)));
  -- One persisted episode per unchanged cart. Touching the cart creates a new episode;
  -- saved notices retain their old episode IDs and are never blindly retried.
  FOR c IN SELECT i.user_id,max(i.updated_at) last_active,jsonb_build_object('items',jsonb_agg(jsonb_build_object('menu_item_id',i.menu_item_id,'quantity',i.quantity,'name',m.name,'base_price',m.price)),'item_count',sum(i.quantity)) payload
   FROM public.cart_items i JOIN public.reporting_profiles p ON p.id=i.user_id AND p.is_active
   LEFT JOIN public.menu_items m ON m.id=i.menu_item_id
   WHERE i.campus_id=cfg.campus_id GROUP BY i.user_id
   HAVING max(i.updated_at)<now()-sync_delay AND max(i.updated_at)>now()-interval '48 hours'
   ORDER BY max(i.updated_at) LIMIT 500 LOOP
    IF NOT EXISTS(SELECT 1 FROM public.abandoned_carts a WHERE a.user_id=c.user_id AND a.campus_id=cfg.campus_id AND a.last_active_at>=c.last_active AND NOT a.is_recovered) THEN
     INSERT INTO public.abandoned_carts(user_id,campus_id,cart_payload,last_active_at) VALUES(c.user_id,cfg.campus_id,c.payload,c.last_active);
    END IF;
  END LOOP;
  -- Include guests who reached payment, but avoid duplicate alerts for a member's same cart.
  FOR c IN SELECT o.* FROM public.reporting_orders o WHERE o.campus_id=cfg.campus_id AND o.payment_status::text='pending'
   AND o.status::text IN ('received','paid') AND o.created_at>now()-interval '48 hours' AND o.created_at<now()-sync_delay
   AND NOT EXISTS(SELECT 1 FROM public.reporting_orders paid WHERE paid.campus_id=o.campus_id AND paid.payment_status::text IN ('paid','partially_refunded') AND paid.created_at>=o.created_at
    AND (paid.user_id=o.user_id OR (o.user_id IS NULL AND paid.user_id IS NULL AND paid.guest_email=o.guest_email)))
   ORDER BY o.created_at LIMIT 500 LOOP
   IF NOT EXISTS(SELECT 1 FROM public.abandoned_carts a WHERE a.campus_id=cfg.campus_id AND NOT a.is_recovered
     AND (a.last_active_at>=c.created_at OR a.cart_payload->>'pending_order_id'=c.id::text)
     AND ((c.user_id IS NOT NULL AND a.user_id=c.user_id) OR (c.user_id IS NULL AND a.user_id IS NULL AND a.guest_email=c.guest_email))) THEN
    INSERT INTO public.abandoned_carts(user_id,guest_email,guest_phone,campus_id,last_active_at,cart_payload)
     VALUES(c.user_id,c.guest_email,c.guest_phone,c.campus_id,c.created_at,jsonb_build_object('pending_order_id',c.id));
   ELSE
    UPDATE public.abandoned_carts a SET cart_payload=a.cart_payload||jsonb_build_object('pending_order_id',c.id)
     WHERE a.campus_id=c.campus_id AND NOT a.is_recovered AND a.user_id=c.user_id AND a.last_active_at<=c.created_at
     AND (a.cart_payload->>'pending_order_id' IS NULL OR EXISTS(SELECT 1 FROM public.orders old WHERE old.id::text=a.cart_payload->>'pending_order_id' AND old.created_at<c.created_at));
   END IF;
  END LOOP;
  FOR c IN SELECT a.* FROM public.reporting_abandoned_carts a WHERE a.campus_id=cfg.campus_id AND NOT a.is_recovered AND a.last_active_at<now()-delay AND a.last_active_at>=cfg.updated_at
   AND NOT EXISTS(SELECT 1 FROM public.orders pending WHERE pending.user_id=a.user_id AND pending.campus_id=a.campus_id AND pending.payment_status::text='pending' AND pending.created_at>a.last_active_at)
   AND (a.user_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.cart_items i WHERE i.user_id=a.user_id AND i.campus_id=a.campus_id AND i.updated_at>a.last_active_at))
   ORDER BY a.last_active_at LIMIT 500 LOOP
    IF public.hg_operations_cart_alert_due(c.id)<=now() THEN
     PERFORM public.hg_queue_operations_email(cfg.campus_id,'abandoned_cart',c.id::text,jsonb_build_object('cart_id',c.id));
    END IF;
  END LOOP;
  -- Bounded catch-up, persisted per period + recipient. WAT dates, previous completed periods only.
  FOR day IN SELECT generate_series(today-7,today,interval '1 day')::date LOOP
   report_end:=(day+report_clock) AT TIME ZONE 'Africa/Lagos';
   report_start:=report_end-interval '24 hours';
   IF report_end<=now() AND day >= (cfg.updated_at AT TIME ZONE 'Africa/Lagos')::date AND (cfg.value->>'daily_report')::boolean
    AND NOT EXISTS(SELECT 1 FROM hg_internal.operations_emails e WHERE e.campus_id=cfg.campus_id AND e.kind='daily_report' AND e.reference=day::text) THEN
     PERFORM public.hg_queue_operations_email(cfg.campus_id,'daily_report',day::text,public.hg_operations_summary_window(cfg.campus_id,report_start,report_end));
   END IF;
  END LOOP;
  first_day:=date_trunc('week',today)::date-7;last_day:=first_day+6;
  IF last_day >= (cfg.updated_at AT TIME ZONE 'Africa/Lagos')::date AND (cfg.value->>'weekly_report')::boolean
   AND NOT EXISTS(SELECT 1 FROM hg_internal.operations_emails e WHERE e.campus_id=cfg.campus_id AND e.kind='weekly_report' AND e.reference=first_day::text) THEN
   PERFORM public.hg_queue_operations_email(cfg.campus_id,'weekly_report',first_day::text,public.hg_operations_summary(cfg.campus_id,first_day,last_day));
  END IF;
  n:=n+1;
 END LOOP;
 RETURN jsonb_build_object('campuses',n);
END $function$;
CREATE OR REPLACE FUNCTION public.hg_operations_email_outbox(p_action text, p_id uuid DEFAULT NULL::uuid, p_token uuid DEFAULT NULL::uuid, p_data jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE due_at timestamptz;result jsonb;row hg_internal.operations_emails%rowtype;cfg jsonb;flag text;
BEGIN
 IF p_action='claim' THEN
  UPDATE hg_internal.operations_emails SET state='uncertain',updated_at=now() WHERE state='sending' AND lease_until<now();
  UPDATE hg_internal.operations_emails SET state='pending',token=NULL,updated_at=now() WHERE state='claimed' AND lease_until<now();
  WITH due AS (SELECT id FROM hg_internal.operations_emails WHERE state='pending' AND available_at<=now() AND (p_data->>'campus_id' IS NULL OR campus_id=(p_data->>'campus_id')::uuid) ORDER BY created_at LIMIT 20 FOR UPDATE SKIP LOCKED),
  claimed AS (UPDATE hg_internal.operations_emails e SET state='claimed',token=gen_random_uuid(),lease_until=now()+interval '10 minutes',updated_at=now() FROM due WHERE e.id=due.id RETURNING e.*)
  SELECT coalesce(jsonb_agg(to_jsonb(c)),'[]') INTO result FROM claimed c;RETURN result;
 ELSIF p_action IN ('begin','finish') THEN
  SELECT * INTO row FROM hg_internal.operations_emails WHERE id=p_id AND token=p_token FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF p_action='finish' THEN
   IF row.state<>'sending' OR p_data->>'state' NOT IN ('accepted','failed','uncertain','cancelled') THEN RETURN NULL; END IF;
   UPDATE hg_internal.operations_emails SET state=p_data->>'state',receipt=p_data->'receipt',updated_at=now() WHERE id=row.id;
   RETURN '{"saved":true}';
  END IF;
  IF row.state<>'claimed' OR row.lease_until<now() THEN RETURN NULL; END IF;
  flag:=CASE row.kind WHEN 'paid_order' THEN 'paid_order_alerts' WHEN 'abandoned_cart' THEN 'abandoned_cart_alerts' ELSE row.kind END;
  SELECT value INTO cfg FROM public.system_settings WHERE key='campus_operations_email' AND campus_id=row.campus_id AND NOT is_public;
  IF cfg IS NULL OR NOT coalesce((cfg->>flag)::boolean,false) OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(cfg->'recipients') email WHERE lower(btrim(email))=row.recipient)
   OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=row.campus_id AND is_active) THEN
   UPDATE hg_internal.operations_emails SET state='cancelled',updated_at=now() WHERE id=row.id;RETURN NULL;
  END IF;
  IF row.kind='abandoned_cart' THEN
   due_at:=public.hg_operations_cart_alert_due((row.payload->>'cart_id')::uuid);
   IF due_at IS NULL THEN
    UPDATE hg_internal.operations_emails SET state='cancelled',updated_at=now() WHERE id=row.id;RETURN NULL;
   ELSIF due_at>now() THEN
    UPDATE hg_internal.operations_emails SET state='pending',available_at=due_at,token=NULL,lease_until=NULL,updated_at=now() WHERE id=row.id;RETURN NULL;
   END IF;
  END IF;
  UPDATE hg_internal.operations_emails SET state='sending',updated_at=now() WHERE id=row.id;
  RETURN to_jsonb(row);
 END IF;
 RAISE EXCEPTION 'Invalid operations email action';
END $function$;
UPDATE public.system_settings SET value=jsonb_set(jsonb_set(value,'{abandoned_minutes}',to_jsonb(greatest(30,(value->>'abandoned_minutes')::integer))),'{daily_report_time}',coalesce(value->'daily_report_time','"21:00"'::jsonb))
 WHERE key='campus_operations_email' AND campus_id IS NOT NULL;
NOTIFY pgrst,'reload schema';
