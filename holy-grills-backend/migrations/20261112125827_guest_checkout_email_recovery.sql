-- Guests use the existing durable email dispatcher; no synthetic account,
-- push subscription, newsletter signup or new scheduler is created.
CREATE TABLE hg_internal.guest_cart_email_optouts (
 campus_id uuid NOT NULL REFERENCES public.campuses(id),
 email extensions.citext NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(campus_id,email)
);
ALTER TABLE hg_internal.guest_cart_email_optouts ENABLE ROW LEVEL SECURITY;
CREATE POLICY guest_cart_optouts_service ON hg_internal.guest_cart_email_optouts FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.guest_cart_email_optouts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON hg_internal.guest_cart_email_optouts TO service_role;
CREATE INDEX guest_cart_recovery_scan ON public.abandoned_carts(campus_id,last_active_at) WHERE user_id IS NULL AND NOT is_recovered;
CREATE INDEX guest_order_recovery_lookup ON public.orders(campus_id,guest_email,created_at DESC) WHERE user_id IS NULL AND NOT is_test;
CREATE INDEX guest_cart_dispatch_recipient ON public.notification_deliveries(campus_id,(dispatch_payload->'notification'->>'email'),created_at) WHERE dispatch_payload->>'kind'='guest_cart_recovery_email';

CREATE FUNCTION public.hg_guest_cart_recovery_valid(p_cart uuid,p_step integer,p_deadline timestamptz,p_email text,p_order uuid)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE c abandoned_carts%rowtype;o orders%rowtype;cfg jsonb;first_minutes integer;repeat_minutes integer;max_hours integer;enabled boolean;address text;
BEGIN
 SELECT * INTO c FROM abandoned_carts WHERE id=p_cart;
 IF NOT FOUND OR c.user_id IS NOT NULL OR c.is_recovered OR c.last_active_at IS NULL OR c.campus_id IS NULL THEN RETURN false;END IF;
 address:=lower(btrim(c.guest_email::text));
 IF nullif(address,'') IS NULL OR address IS DISTINCT FROM p_email OR length(address)>254 OR address !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' THEN RETURN false;END IF;
 SELECT * INTO o FROM orders WHERE id=p_order;
 IF NOT FOUND OR o.user_id IS NOT NULL OR o.is_test OR o.campus_id IS DISTINCT FROM c.campus_id
  OR c.cart_payload->>'pending_order_id' IS DISTINCT FROM o.id::text OR o.claim_token IS NULL
  OR lower(btrim(o.guest_email::text)) IS DISTINCT FROM address OR o.guest_phone IS DISTINCT FROM c.guest_phone
  OR o.payment_status::text<>'pending' OR o.status::text<>'received' THEN RETURN false;END IF;
 IF NOT EXISTS(SELECT 1 FROM campuses WHERE id=c.campus_id AND is_active) THEN RETURN false;END IF;
 SELECT is_active INTO enabled FROM feature_flags WHERE feature_name='abandoned_cart_nudge' AND (campus_id=c.campus_id OR campus_id IS NULL) ORDER BY campus_id IS NOT NULL DESC LIMIT 1;
 IF NOT coalesce(enabled,false) THEN RETURN false;END IF;
 SELECT value INTO cfg FROM system_settings WHERE key='campus_cart_recovery' AND campus_id=c.campus_id;
 first_minutes:=greatest(30,coalesce((cfg->>'initial_minutes')::integer,30));
 repeat_minutes:=greatest(30,coalesce((cfg->>'repeat_minutes')::integer,1440));
 max_hours:=least(48,coalesce((cfg->>'max_hours')::integer,48));
 IF p_deadline IS NULL OR now()>=p_deadline OR p_deadline>c.last_active_at+interval '48 hours'
  OR now()<greatest(c.last_active_at,o.created_at)+make_interval(mins=>first_minutes)
  OR c.last_active_at<=now()-make_interval(hours=>max_hours)
  OR p_step IS NULL OR p_step<0 OR p_step<>floor((extract(epoch FROM now()-c.last_active_at)/60-first_minutes)/repeat_minutes)::integer THEN RETURN false;END IF;
 IF EXISTS(SELECT 1 FROM hg_internal.guest_cart_email_optouts WHERE campus_id=c.campus_id AND lower(btrim(email::text))=address)
  OR EXISTS(SELECT 1 FROM newsletter_subscriptions WHERE lower(btrim(email::text))=address AND unsubscribed_at IS NOT NULL)
  OR EXISTS(SELECT 1 FROM profiles p LEFT JOIN notification_preferences n ON n.user_id=p.id WHERE lower(btrim(p.email::text))=address
   AND (NOT p.is_active OR p.role::text='super_admin' OR p.email_notifications IS FALSE OR n.email_enabled IS FALSE OR n.promotions IS FALSE)) THEN RETURN false;END IF;
 -- Newer guest checkouts supersede old ones. A later successful checkout,
 -- including one paid after signing in, ends recovery for this email.
 IF EXISTS(SELECT 1 FROM orders newer WHERE newer.campus_id=c.campus_id AND NOT newer.is_test
  AND ((lower(btrim(newer.guest_email::text))=address AND newer.user_id IS NULL) OR newer.user_id IN(SELECT id FROM profiles WHERE lower(btrim(email::text))=address))
  AND ((newer.payment_status::text IN ('paid','partially_refunded','refunded') AND newer.created_at>=c.last_active_at)
   OR (newer.user_id IS NULL AND newer.payment_status::text='pending' AND newer.status::text='received'
    AND (newer.created_at,newer.id)>(o.created_at,o.id)))) THEN RETURN false;END IF;
 RETURN true;
END $$;

CREATE FUNCTION public.hg_due_guest_cart_recovery(p_campus uuid,p_initial integer DEFAULT 30,p_repeat integer DEFAULT 1440,p_hours integer DEFAULT 48)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb;
BEGIN
 IF p_initial NOT BETWEEN 10 AND 1440 OR p_repeat NOT BETWEEN 30 AND 1440 OR p_hours NOT BETWEEN 1 AND 48 THEN RAISE EXCEPTION 'Invalid cart recovery timing';END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(candidate)),'[]') INTO result FROM (
  SELECT a.*,CASE WHEN o.is_scheduled THEN o.scheduled_for END recovery_scheduled_for,
   floor((extract(epoch FROM now()-a.last_active_at)/60-greatest(30,p_initial))/p_repeat)::integer recovery_step
  FROM abandoned_carts a JOIN orders o ON o.id::text=a.cart_payload->>'pending_order_id'
  WHERE a.user_id IS NULL AND a.campus_id=p_campus AND NOT a.is_recovered
   AND a.last_active_at<=now()-make_interval(mins=>greatest(30,p_initial)) AND a.last_active_at>now()-make_interval(hours=>p_hours)
   AND public.hg_guest_cart_recovery_valid(a.id,floor((extract(epoch FROM now()-a.last_active_at)/60-greatest(30,p_initial))/p_repeat)::integer,
    a.last_active_at+make_interval(hours=>p_hours),lower(btrim(a.guest_email::text)),o.id)
   AND NOT EXISTS(SELECT 1 FROM hg_internal.cart_recovery_steps s WHERE s.cart_id=a.id AND s.step=floor((extract(epoch FROM now()-a.last_active_at)/60-greatest(30,p_initial))/p_repeat)::integer)
  ORDER BY a.last_active_at,a.id LIMIT 50
 ) candidate;
 RETURN result;
END $$;

CREATE FUNCTION public.hg_capture_guest_cart_recovery_step(p_cart uuid,p_step integer,p_deadline timestamptz,p_initial integer DEFAULT 30,p_repeat integer DEFAULT 1440,p_hours integer DEFAULT 48)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE c abandoned_carts%rowtype;o orders%rowtype;notice uuid;address text;ends_at timestamptz;
BEGIN
 IF p_initial NOT BETWEEN 10 AND 1440 OR p_repeat NOT BETWEEN 30 AND 1440 OR p_hours NOT BETWEEN 1 AND 48 THEN RAISE EXCEPTION 'Invalid cart recovery timing';END IF;
 SELECT * INTO c FROM abandoned_carts WHERE id=p_cart FOR UPDATE;
 IF NOT FOUND OR c.user_id IS NOT NULL THEN RETURN '{"saved":false,"reason":"guest_unavailable"}';END IF;
 address:=lower(btrim(c.guest_email::text));
 PERFORM pg_advisory_xact_lock(hashtextextended('guest-cart-reminder:'||c.campus_id||':'||address,0));
 SELECT * INTO o FROM orders WHERE id::text=c.cart_payload->>'pending_order_id';
 ends_at:=least(p_deadline,c.last_active_at+make_interval(hours=>p_hours));
 IF p_deadline IS NULL OR NOT public.hg_guest_cart_recovery_valid(c.id,p_step,ends_at,address,o.id) THEN RETURN '{"saved":false,"reason":"not_due_changed_paid_or_opted_out"}';END IF;
 IF EXISTS(SELECT 1 FROM hg_internal.cart_recovery_steps WHERE cart_id=c.id AND step=p_step) THEN RETURN '{"saved":false,"reason":"already_saved"}';END IF;
 IF EXISTS(SELECT 1 FROM notification_deliveries WHERE campus_id=c.campus_id AND dispatch_payload->>'kind'='guest_cart_recovery_email'
  AND dispatch_payload->'notification'->>'email'=address AND created_at>now()-make_interval(mins=>p_repeat)) THEN RETURN '{"saved":false,"reason":"recipient_throttled"}';END IF;
 notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:guest-cart:'||c.id||':'||p_step);
 INSERT INTO notification_deliveries(id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
 VALUES(notice,NULL,'email','queued',c.campus_id,
  jsonb_build_object('version',1,'state','queued','key',notice,'attempts',0,'next_at',now(),'expires_at',ends_at),
  jsonb_build_object('kind','guest_cart_recovery_email','cart_id',c.id,'order_id',o.id,'step',p_step,'deadline',ends_at,
   'notification',jsonb_build_object('user_id',NULL,'email',address,'name',coalesce(nullif(o.guest_name,''),'there'),
    'type','guest_checkout_reminder','title','Your checkout is waiting','body','Your checkout is not confirmed yet. Complete payment when you are ready.')))
 ON CONFLICT(id) DO NOTHING;
 INSERT INTO hg_internal.cart_recovery_steps(cart_id,step,deadline,notification_ids) VALUES(c.id,p_step,ends_at,ARRAY[notice]);
 UPDATE abandoned_carts SET recovery_attempts=(SELECT count(*) FROM hg_internal.cart_recovery_steps WHERE cart_id=c.id AND cardinality(notification_ids)>0),last_recovery_sent_at=now() WHERE id=c.id;
 RETURN jsonb_build_object('saved',true,'notification_ids',jsonb_build_array(notice),'reason','queued');
END $$;

CREATE FUNCTION public.hg_begin_guest_cart_dispatch(p_id uuid,p_token uuid,p_prepared jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE d notification_deliveries%rowtype;
BEGIN
 SELECT * INTO d FROM notification_deliveries WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR d.dispatch_payload->>'kind' IS DISTINCT FROM 'guest_cart_recovery_email' OR d.channel<>'email' THEN RETURN false;END IF;
 IF NOT public.hg_guest_cart_recovery_valid((d.dispatch_payload->>'cart_id')::uuid,(d.dispatch_payload->>'step')::integer,
  (d.dispatch_payload->>'deadline')::timestamptz,d.dispatch_payload->'notification'->>'email',(d.dispatch_payload->>'order_id')::uuid) THEN
  PERFORM public.hg_finish_notification_dispatch(p_id,p_token,'{"state":"cancelled","error":"guest_checkout_no_longer_eligible"}');RETURN false;
 END IF;
 RETURN public.hg_begin_notification_dispatch(p_id,p_token,p_prepared);
END $$;

CREATE FUNCTION public.hg_unsubscribe_guest_cart_email(p_id uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE d notification_deliveries%rowtype;
BEGIN
 SELECT * INTO d FROM notification_deliveries WHERE id=p_id AND dispatch_payload->>'kind'='guest_cart_recovery_email';
 IF NOT FOUND THEN RETURN false;END IF;
 INSERT INTO hg_internal.guest_cart_email_optouts(campus_id,email) VALUES(d.campus_id,(d.dispatch_payload->'notification'->>'email')::extensions.citext) ON CONFLICT DO NOTHING;
 RETURN true;
END $$;

REVOKE ALL ON FUNCTION public.hg_guest_cart_recovery_valid(uuid,integer,timestamptz,text,uuid),public.hg_due_guest_cart_recovery(uuid,integer,integer,integer),public.hg_capture_guest_cart_recovery_step(uuid,integer,timestamptz,integer,integer,integer),public.hg_begin_guest_cart_dispatch(uuid,uuid,jsonb),public.hg_unsubscribe_guest_cart_email(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_guest_cart_recovery_valid(uuid,integer,timestamptz,text,uuid),public.hg_due_guest_cart_recovery(uuid,integer,integer,integer),public.hg_capture_guest_cart_recovery_step(uuid,integer,timestamptz,integer,integer,integer),public.hg_begin_guest_cart_dispatch(uuid,uuid,jsonb),public.hg_unsubscribe_guest_cart_email(uuid) TO service_role;

-- Existing operator counters include guest email receipts, without inventing an
-- in-app notification or treating a saved/queued reminder as delivered.
CREATE OR REPLACE FUNCTION public.hg_cart_recovery_metrics(p_ids uuid[])
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 WITH deliveries AS (
  SELECT n.reference_id cart_id,d.channel,d.status FROM notifications n JOIN notification_deliveries d ON d.notification_id=n.id
   WHERE n.type='abandoned_cart' AND n.reference_id=ANY(p_ids)
  UNION ALL
  SELECT (d.dispatch_payload->>'cart_id')::uuid,d.channel,d.status FROM notification_deliveries d
   WHERE d.dispatch_payload->>'kind'='guest_cart_recovery_email' AND d.dispatch_payload->>'cart_id'=ANY(p_ids::text[])
 ), counts AS (
  SELECT a.id,(SELECT count(*) FROM hg_internal.cart_recovery_steps s WHERE s.cart_id=a.id AND cardinality(s.notification_ids)>0) saved,
   count(*) FILTER(WHERE d.channel='email' AND d.status='sent') email_accepted,
   count(*) FILTER(WHERE d.channel='push' AND d.status='sent') push_accepted,
   count(*) FILTER(WHERE d.status IN ('queued','sending')) pending,
   count(*) FILTER(WHERE d.status IN ('failed','uncertain')) issues
  FROM abandoned_carts a LEFT JOIN deliveries d ON d.cart_id=a.id WHERE a.id=ANY(p_ids) GROUP BY a.id
 ) SELECT coalesce(jsonb_object_agg(id,jsonb_build_object('saved_nudges',saved,'email_accepted',email_accepted,'push_accepted',push_accepted,'delivery_pending',pending,'delivery_issues',issues)),'{}') FROM counts
$$;
