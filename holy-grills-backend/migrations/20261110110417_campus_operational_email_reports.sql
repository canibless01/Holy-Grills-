SET LOCAL request.jwt.claims='{"role":"service_role"}';
-- Explicit campus recipients only. Never expose these addresses in public settings.
CREATE FUNCTION public.hg_validate_operations_email_setting() RETURNS trigger
LANGUAGE plpgsql SET search_path=public AS $$
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
 IF coalesce(NEW.value->>'abandoned_minutes','') !~ '^[0-9]+$' OR (NEW.value->>'abandoned_minutes')::integer NOT BETWEEN 10 AND 1440 THEN RAISE EXCEPTION 'Abandonment delay must be 10 to 1440 minutes'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.hg_validate_operations_email_setting() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER aa_validate_operations_email_setting BEFORE INSERT OR UPDATE ON public.system_settings
 FOR EACH ROW EXECUTE FUNCTION public.hg_validate_operations_email_setting();

CREATE TABLE hg_internal.operations_emails (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),campus_id uuid NOT NULL REFERENCES public.campuses(id),
 kind text NOT NULL CHECK(kind IN ('paid_order','abandoned_cart','daily_report','weekly_report')),
 reference text NOT NULL,recipient text NOT NULL,payload jsonb NOT NULL DEFAULT '{}',
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','claimed','sending','accepted','failed','uncertain','cancelled')),
 token uuid,lease_until timestamptz,receipt jsonb,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(campus_id,kind,reference,recipient)
);
ALTER TABLE hg_internal.operations_emails ENABLE ROW LEVEL SECURITY;
CREATE POLICY operations_emails_service ON hg_internal.operations_emails FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.operations_emails FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.operations_emails TO service_role;
CREATE INDEX operations_emails_pending ON hg_internal.operations_emails(created_at) WHERE state IN ('pending','claimed','sending');

ALTER TABLE public.abandoned_carts ADD COLUMN recovered_at timestamptz;
CREATE OR REPLACE VIEW public.reporting_abandoned_carts WITH(security_invoker=true) AS SELECT t.* FROM public.abandoned_carts t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
CREATE INDEX operations_cart_scan ON public.cart_items(campus_id,user_id,updated_at);

CREATE FUNCTION public.hg_queue_operations_email(p_campus uuid,p_kind text,p_reference text,p_payload jsonb DEFAULT '{}')
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE cfg jsonb;recipient text;flag text;
BEGIN
 flag:=CASE p_kind WHEN 'paid_order' THEN 'paid_order_alerts' WHEN 'abandoned_cart' THEN 'abandoned_cart_alerts' ELSE p_kind END;
 SELECT value INTO cfg FROM public.system_settings WHERE key='campus_operations_email' AND campus_id=p_campus AND NOT is_public;
 IF cfg IS NULL OR NOT coalesce((cfg->>flag)::boolean,false) THEN RETURN; END IF;
 FOR recipient IN SELECT DISTINCT lower(btrim(v)) FROM jsonb_array_elements_text(cfg->'recipients') v LOOP
  INSERT INTO hg_internal.operations_emails(campus_id,kind,reference,recipient,payload)
   VALUES(p_campus,p_kind,p_reference,recipient,p_payload) ON CONFLICT DO NOTHING;
 END LOOP;
END $$;
CREATE FUNCTION public.hg_capture_paid_order_alert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF NEW.is_test OR NEW.payment_status::text<>'paid' THEN RETURN NEW; END IF;
 IF TG_OP='UPDATE' AND OLD.payment_status::text='paid' THEN RETURN NEW; END IF;
 PERFORM public.hg_queue_operations_email(NEW.campus_id,'paid_order',NEW.id::text,jsonb_build_object('order_id',NEW.id));
 RETURN NEW;
END $$;
CREATE TRIGGER orders_capture_operations_alert AFTER INSERT OR UPDATE OF payment_status ON public.orders
 FOR EACH ROW EXECUTE FUNCTION public.hg_capture_paid_order_alert();
-- Recovery means successful payment, not an abandoned Paystack checkout.
CREATE OR REPLACE FUNCTION public.hg_mark_abandoned_cart_recovered() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF NEW.payment_status::text='paid' AND NOT NEW.is_test THEN
  UPDATE public.abandoned_carts SET is_recovered=true,recovered_order_id=NEW.id,recovered_at=now(),updated_at=now()
   WHERE NOT is_recovered AND campus_id=NEW.campus_id
    AND ((NEW.user_id IS NOT NULL AND user_id=NEW.user_id)
      OR (NEW.user_id IS NULL AND user_id IS NULL AND guest_email=NEW.guest_email));
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER trg_orders_mark_cart_recovered ON public.orders;
CREATE TRIGGER trg_orders_mark_cart_recovered AFTER INSERT OR UPDATE OF payment_status ON public.orders
 FOR EACH ROW EXECUTE FUNCTION public.hg_mark_abandoned_cart_recovered();

CREATE FUNCTION public.hg_operations_summary(p_campus uuid,p_first date,p_last date)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb;v_start_at timestamptz:=p_first::timestamp AT TIME ZONE 'Africa/Lagos';v_end_at timestamptz:=(p_last+1)::timestamp AT TIME ZONE 'Africa/Lagos';
BEGIN
 IF p_campus IS NULL OR p_first IS NULL OR p_last IS NULL OR p_last<p_first OR p_last-p_first>31 THEN RAISE EXCEPTION 'Invalid report range'; END IF;
 SELECT jsonb_build_object(
  'from',p_first,'to',p_last,
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
END $$;

CREATE FUNCTION public.hg_capture_operations_emails(p_campus uuid DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE cfg record;c record;day date;first_day date;last_day date;sync_delay interval;today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;delay interval;n integer:=0;
BEGIN
 IF NOT pg_try_advisory_xact_lock(hashtextextended('hg-operations-capture',0)) THEN RETURN '{"skipped":true}'; END IF;
 FOR cfg IN SELECT campus.id campus_id,coalesce(s.value,'{"recipients":[],"abandoned_minutes":10,"daily_report":false,"weekly_report":false}'::jsonb) value,coalesce(s.updated_at,now()-interval '48 hours') updated_at FROM public.campuses campus LEFT JOIN public.system_settings s ON s.campus_id=campus.id AND s.key='campus_operations_email' AND NOT s.is_public WHERE campus.is_active AND (p_campus IS NULL OR campus.id=p_campus) LOOP
  delay:=make_interval(mins=>(cfg.value->>'abandoned_minutes')::integer);
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
    PERFORM public.hg_queue_operations_email(cfg.campus_id,'abandoned_cart',c.id::text,jsonb_build_object('cart_id',c.id));
  END LOOP;
  -- Bounded catch-up, persisted per period + recipient. WAT dates, previous completed periods only.
  FOR day IN SELECT generate_series(today-7,today-1,interval '1 day')::date LOOP
   IF day >= (cfg.updated_at AT TIME ZONE 'Africa/Lagos')::date AND (cfg.value->>'daily_report')::boolean
    AND NOT EXISTS(SELECT 1 FROM hg_internal.operations_emails e WHERE e.campus_id=cfg.campus_id AND e.kind='daily_report' AND e.reference=day::text) THEN
     PERFORM public.hg_queue_operations_email(cfg.campus_id,'daily_report',day::text,public.hg_operations_summary(cfg.campus_id,day,day));
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
END $$;

CREATE FUNCTION public.hg_operations_email_outbox(p_action text,p_id uuid DEFAULT NULL,p_token uuid DEFAULT NULL,p_data jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb;row hg_internal.operations_emails%rowtype;cfg jsonb;flag text;
BEGIN
 IF p_action='claim' THEN
  UPDATE hg_internal.operations_emails SET state='uncertain',updated_at=now() WHERE state='sending' AND lease_until<now();
  UPDATE hg_internal.operations_emails SET state='pending',token=NULL,updated_at=now() WHERE state='claimed' AND lease_until<now();
  WITH due AS (SELECT id FROM hg_internal.operations_emails WHERE state='pending' AND (p_data->>'campus_id' IS NULL OR campus_id=(p_data->>'campus_id')::uuid) ORDER BY created_at LIMIT 20 FOR UPDATE SKIP LOCKED),
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
  UPDATE hg_internal.operations_emails SET state='sending',updated_at=now() WHERE id=row.id;
  RETURN to_jsonb(row);
 END IF;
 RAISE EXCEPTION 'Invalid operations email action';
END $$;
REVOKE ALL ON FUNCTION public.hg_queue_operations_email(uuid,text,text,jsonb),public.hg_capture_paid_order_alert(),public.hg_mark_abandoned_cart_recovered(),public.hg_operations_summary(uuid,date,date),public.hg_capture_operations_emails(uuid),public.hg_operations_email_outbox(text,uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_queue_operations_email(uuid,text,text,jsonb),public.hg_operations_summary(uuid,date,date),public.hg_capture_operations_emails(uuid),public.hg_operations_email_outbox(text,uuid,uuid,jsonb) TO service_role;
-- User supplied destination; no hardcoded campus UUID. New campuses opt in explicitly.
INSERT INTO public.system_settings(key,value,description,is_public,campus_id)
 SELECT 'campus_operations_email','{"recipients":["grillthevibe@gmail.com"],"paid_order_alerts":true,"abandoned_cart_alerts":true,"daily_report":true,"weekly_report":true,"abandoned_minutes":10}'::jsonb,
 'Private operational email recipients and alert/report switches. Daily and weekly summaries use WAT calendar periods.',false,id FROM public.campuses WHERE lower(slug)='futa'
 AND NOT EXISTS(SELECT 1 FROM public.system_settings WHERE key='campus_operations_email' AND campus_id=campuses.id);
NOTIFY pgrst,'reload schema';
CREATE FUNCTION public.hg_operations_email_status(p_actor uuid,p_campus uuid,p_retry uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles%rowtype;result jsonb;
BEGIN
 SELECT * INTO actor FROM public.profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin') OR p_campus IS NULL
  OR (actor.role::text<>'super_admin' AND actor.campus_id IS DISTINCT FROM p_campus) THEN
  RAISE EXCEPTION 'Operations email scope forbidden' USING ERRCODE='42501';
 END IF;
 IF p_retry IS NOT NULL THEN
  -- Only proven unsent failures. Never resend accepted or uncertain deliveries.
  UPDATE hg_internal.operations_emails SET state='pending',token=NULL,lease_until=NULL,updated_at=now()
   WHERE id=p_retry AND campus_id=p_campus AND state='failed';
  IF NOT FOUND THEN RAISE EXCEPTION 'Only an unsent failure can be retried'; END IF;
 END IF;
 SELECT jsonb_build_object('counts',(SELECT coalesce(jsonb_object_agg(state,n),'{}') FROM
  (SELECT state,count(*) n FROM hg_internal.operations_emails WHERE campus_id=p_campus GROUP BY state) totals),
  'recent',(SELECT coalesce(jsonb_agg(to_jsonb(recent)),'[]') FROM
   (SELECT id,kind,recipient,state,created_at,updated_at FROM hg_internal.operations_emails WHERE campus_id=p_campus ORDER BY created_at DESC LIMIT 20) recent)) INTO result;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.hg_operations_email_status(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_operations_email_status(uuid,uuid,uuid) TO service_role;
-- Customer reminders share the existing durable notification dispatcher. A step
-- and all permitted channel records commit together; provider receipt != inbox delivery.
CREATE TABLE hg_internal.cart_recovery_steps (
 cart_id uuid NOT NULL REFERENCES public.abandoned_carts(id) ON DELETE CASCADE,
 step integer NOT NULL,deadline timestamptz NOT NULL,notification_ids uuid[] NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(cart_id,step)
);
ALTER TABLE hg_internal.cart_recovery_steps ENABLE ROW LEVEL SECURITY;
CREATE POLICY cart_recovery_steps_service ON hg_internal.cart_recovery_steps FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.cart_recovery_steps FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON hg_internal.cart_recovery_steps TO service_role;

CREATE FUNCTION public.hg_due_cart_recovery(p_campus uuid,p_initial integer DEFAULT 30,p_repeat integer DEFAULT 1440,p_hours integer DEFAULT 48)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb;
BEGIN
 IF p_initial NOT BETWEEN 10 AND 1440 OR p_repeat NOT BETWEEN 30 AND 1440 OR p_hours NOT BETWEEN 1 AND 48 THEN RAISE EXCEPTION 'Invalid cart recovery timing'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(due)),'[]') INTO result FROM (
  SELECT a.*,(SELECT scheduled_for FROM public.orders pending WHERE pending.id::text=a.cart_payload->>'pending_order_id' AND pending.user_id=a.user_id AND pending.campus_id=a.campus_id AND pending.is_scheduled) recovery_scheduled_for,floor((extract(epoch FROM now()-a.last_active_at)/60-p_initial)/p_repeat)::integer recovery_step
  FROM public.reporting_abandoned_carts a JOIN public.reporting_profiles p ON p.id=a.user_id AND p.is_active
  WHERE a.campus_id=p_campus AND NOT a.is_recovered AND a.last_active_at<=now()-make_interval(mins=>p_initial)
   AND a.last_active_at>now()-make_interval(hours=>p_hours)
   AND NOT EXISTS(SELECT 1 FROM hg_internal.cart_recovery_steps s WHERE s.cart_id=a.id AND s.step=floor((extract(epoch FROM now()-a.last_active_at)/60-p_initial)/p_repeat)::integer)
   AND NOT EXISTS(SELECT 1 FROM public.orders pending WHERE pending.user_id=a.user_id AND pending.campus_id=a.campus_id AND pending.payment_status::text='pending' AND pending.created_at>a.last_active_at)
   AND NOT EXISTS(SELECT 1 FROM public.cart_items i WHERE i.user_id=a.user_id AND i.campus_id=a.campus_id AND i.updated_at>a.last_active_at)
  ORDER BY a.last_active_at LIMIT 50
 ) due;RETURN result;
END $$;
CREATE FUNCTION public.hg_capture_cart_recovery_step(p_cart uuid,p_step integer,p_deadline timestamptz,p_initial integer DEFAULT 30,p_repeat integer DEFAULT 1440,p_hours integer DEFAULT 48)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE cart public.abandoned_carts%rowtype;owner public.profiles%rowtype;prefs public.notification_preferences%rowtype;
 channel_name text;notice uuid;notices uuid[]:='{}';enabled boolean;pending uuid;step_due integer;
BEGIN
 IF p_initial NOT BETWEEN 10 AND 1440 OR p_repeat NOT BETWEEN 30 AND 1440 OR p_hours NOT BETWEEN 1 AND 48 THEN RAISE EXCEPTION 'Invalid cart recovery timing'; END IF;
 SELECT * INTO cart FROM public.abandoned_carts WHERE id=p_cart FOR UPDATE;
 IF NOT FOUND OR cart.is_recovered OR cart.user_id IS NULL OR cart.last_active_at<=now()-make_interval(hours=>p_hours) OR p_deadline IS NULL OR now()>=p_deadline THEN RETURN '{"saved":false,"reason":"expired_or_recovered"}'; END IF;
 SELECT * INTO owner FROM public.profiles WHERE id=cart.user_id AND is_active AND role::text<>'super_admin';
 IF NOT FOUND THEN RETURN '{"saved":false,"reason":"account_unavailable"}'; END IF;
 SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='abandoned_cart_nudge' AND (campus_id=cart.campus_id OR campus_id IS NULL) ORDER BY campus_id IS NOT NULL DESC LIMIT 1;
 IF NOT coalesce(enabled,false) THEN RETURN '{"saved":false,"reason":"disabled"}'; END IF;
 step_due:=floor((extract(epoch FROM now()-cart.last_active_at)/60-p_initial)/p_repeat)::integer;
 IF p_step IS NULL OR p_step<0 OR p_step IS DISTINCT FROM step_due THEN RETURN '{"saved":false,"reason":"not_due"}'; END IF;
 IF EXISTS(SELECT 1 FROM hg_internal.cart_recovery_steps WHERE cart_id=cart.id AND step=p_step) THEN RETURN '{"saved":false,"reason":"already_saved"}'; END IF;
 pending:=nullif(cart.cart_payload->>'pending_order_id','')::uuid;
 IF EXISTS(SELECT 1 FROM public.orders pending WHERE pending.user_id=cart.user_id AND pending.campus_id=cart.campus_id AND pending.payment_status::text='pending' AND pending.created_at>cart.last_active_at)
  OR EXISTS(SELECT 1 FROM public.cart_items WHERE user_id=cart.user_id AND campus_id=cart.campus_id AND updated_at>cart.last_active_at)
  OR (NOT EXISTS(SELECT 1 FROM public.cart_items WHERE user_id=cart.user_id AND campus_id=cart.campus_id) AND NOT EXISTS(SELECT 1 FROM public.orders WHERE id=pending AND user_id=cart.user_id AND campus_id=cart.campus_id AND payment_status::text='pending' AND status::text='received'))
  OR EXISTS(SELECT 1 FROM public.orders WHERE user_id=cart.user_id AND campus_id=cart.campus_id AND payment_status::text IN ('paid','partially_refunded') AND created_at>=cart.last_active_at) THEN RETURN '{"saved":false,"reason":"cart_changed_or_paid"}'; END IF;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=owner.id;
 IF prefs.promotions IS NOT FALSE THEN
  FOREACH channel_name IN ARRAY ARRAY['in_app','email','push'] LOOP
   IF channel_name='email' AND (owner.email_notifications IS FALSE OR prefs.email_enabled IS FALSE OR nullif(owner.email::text,'') IS NULL) THEN CONTINUE; END IF;
   IF channel_name='push' AND (owner.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE; END IF;
   notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:cart-recovery:'||cart.id||':'||p_step||':'||channel_name);
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
    VALUES(notice,owner.id,'abandoned_cart','Your cart is waiting 🛒','Your checkout is not confirmed yet. Return to your cart and complete payment when you are ready.',channel_name,'/cart',cart.campus_id,cart.id,
    jsonb_build_object('_dispatch_version',1,'reference_type','abandoned_cart','reference_id',cart.id,'body_html','Your checkout is not confirmed yet. Return to your cart and complete payment when you are ready.','cta_blocks',jsonb_build_array(jsonb_build_object('label','Resume checkout','url','https://holygrills.online/cart','style','primary')),'cart_recovery',jsonb_build_object('cart_id',cart.id,'step',p_step,'deadline',p_deadline))) ON CONFLICT(id) DO NOTHING;
   notices:=array_append(notices,notice);
  END LOOP;
 END IF;
 INSERT INTO hg_internal.cart_recovery_steps(cart_id,step,deadline,notification_ids) VALUES(cart.id,p_step,p_deadline,notices);
 UPDATE public.abandoned_carts SET recovery_attempts=(SELECT count(*) FROM hg_internal.cart_recovery_steps WHERE cart_id=cart.id AND cardinality(notification_ids)>0),
  last_recovery_sent_at=CASE WHEN cardinality(notices)>0 THEN now() ELSE last_recovery_sent_at END WHERE id=cart.id;
 RETURN jsonb_build_object('saved',cardinality(notices)>0,'notification_ids',notices,'reason',CASE WHEN cardinality(notices)=0 THEN 'preferences_disabled' ELSE 'queued' END);
END $$;
REVOKE ALL ON FUNCTION public.hg_due_cart_recovery(uuid,integer,integer,integer),public.hg_capture_cart_recovery_step(uuid,integer,timestamptz,integer,integer,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_due_cart_recovery(uuid,integer,integer,integer),public.hg_capture_cart_recovery_step(uuid,integer,timestamptz,integer,integer,integer) TO service_role;
CREATE FUNCTION public.hg_cart_recovery_metrics(p_ids uuid[]) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce(jsonb_object_agg(id,jsonb_build_object('saved_nudges',saved,'email_accepted',email_accepted,'push_accepted',push_accepted,'delivery_pending',pending,'delivery_issues',issues)),'{}') FROM (
  SELECT a.id,(SELECT count(*) FROM hg_internal.cart_recovery_steps s WHERE s.cart_id=a.id AND cardinality(s.notification_ids)>0) saved,
   count(*) FILTER(WHERE d.channel='email' AND d.status='sent') email_accepted,
   count(*) FILTER(WHERE d.channel='push' AND d.status='sent') push_accepted,
   count(*) FILTER(WHERE d.status IN ('queued','sending')) pending,
   count(*) FILTER(WHERE d.status IN ('failed','uncertain')) issues
  FROM public.abandoned_carts a LEFT JOIN public.notifications n ON n.reference_id=a.id AND n.type='abandoned_cart'
  LEFT JOIN public.notification_deliveries d ON d.notification_id=n.id
  WHERE a.id=ANY(p_ids) GROUP BY a.id
 ) counts
$$;
REVOKE ALL ON FUNCTION public.hg_cart_recovery_metrics(uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_cart_recovery_metrics(uuid[]) TO service_role;

INSERT INTO public.system_settings(key,value,description,is_public,campus_id)
 SELECT 'campus_cart_recovery','{"initial_minutes":30,"repeat_minutes":1440,"max_hours":48}'::jsonb,
 'Customer cart reminder timing in minutes/hours. Stops after payment, cart change/clear, 48h, or the applicable preparation cutoff. Respects channel preferences.',false,id FROM public.campuses WHERE is_active
 AND NOT EXISTS(SELECT 1 FROM public.system_settings WHERE key='campus_cart_recovery' AND campus_id=campuses.id);
NOTIFY pgrst,'reload schema';
