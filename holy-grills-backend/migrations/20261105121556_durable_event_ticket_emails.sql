-- These new RPCs opt new API calls into atomic ticket + email capture. Historical
-- paid tickets are not backfilled, avoiding replay of email sent by old code.
CREATE OR REPLACE FUNCTION public.hg_queue_event_ticket_email(p_ticket_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE t public.event_tickets%rowtype; e public.events%rowtype; email_address text; recipient_name text;
BEGIN
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket_id FOR UPDATE;
 IF NOT FOUND OR t.status NOT IN ('confirmed','checked_in') OR t.payment_status NOT IN ('paid','not_required') THEN RETURN NULL; END IF;
 SELECT * INTO e FROM public.events WHERE id=t.event_id;
 IF t.user_id IS NOT NULL THEN SELECT email::text,coalesce(nullif(full_name,''),nullif(nickname,''),'there') INTO email_address,recipient_name FROM public.profiles WHERE id=t.user_id;
 ELSE email_address:=t.guest_email::text; recipient_name:=coalesce(nullif(t.guest_name,''),'there'); END IF;
 INSERT INTO public.notification_deliveries(id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
 VALUES(t.id,t.user_id,'email','queued',t.campus_id,
  jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
  jsonb_build_object('kind','event_ticket_email','ticket_id',t.id,'event_id',t.event_id,'notification',
   jsonb_build_object('user_id',t.user_id,'type','event_registered','title','Your ticket for '||e.title,'body','Your confirmed event ticket',
    'email',lower(btrim(email_address)),'name',recipient_name,'metadata',jsonb_build_object('event_title',e.title,'event_date',e.starts_at,'event_location',e.location))))
 ON CONFLICT(id) DO NOTHING;
 RETURN t.id;
END $$;

CREATE OR REPLACE FUNCTION public.hg_register_event_with_delivery(p_event_id uuid,p_user_id uuid,p_tier_id uuid DEFAULT NULL,
 p_use_hp boolean DEFAULT false,p_wallet_amount numeric DEFAULT 0,p_promo_code_id uuid DEFAULT NULL,p_metadata jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb;
BEGIN
 result:=public.register_for_event_paid(p_event_id,p_user_id,p_tier_id,p_use_hp,p_wallet_amount,p_promo_code_id,p_metadata);
 IF NOT (result ? 'error') AND NOT coalesce((result->>'already_registered')::boolean,false)
 AND result->>'payment_status' IN ('paid','not_required') THEN PERFORM public.hg_queue_event_ticket_email((result->>'ticket_id')::uuid); END IF;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.hg_register_guest_event_with_delivery(p_event_id uuid,p_guest_email extensions.citext,p_guest_name text,
 p_guest_phone text DEFAULT NULL,p_tier_id uuid DEFAULT NULL,p_promo_code_id uuid DEFAULT NULL,p_metadata jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb;
BEGIN
 result:=public.register_for_event_guest_paid(p_event_id,p_guest_email,p_guest_name,p_guest_phone,p_tier_id,p_promo_code_id,p_metadata);
 IF NOT (result ? 'error') AND NOT coalesce((result->>'already_registered')::boolean,false)
 AND result->>'payment_status' IN ('paid','not_required') THEN PERFORM public.hg_queue_event_ticket_email((result->>'ticket_id')::uuid); END IF;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.hg_pay_event_with_delivery(p_ticket_id uuid,p_provider text DEFAULT NULL,p_provider_reference text DEFAULT NULL,
 p_amount numeric DEFAULT NULL,p_metadata jsonb DEFAULT '{}')
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE was_paid boolean; result uuid;
BEGIN
 SELECT payment_status='paid' INTO was_paid FROM public.event_tickets WHERE id=p_ticket_id FOR UPDATE;
 result:=public.hg_mark_event_ticket_paid(p_ticket_id,p_provider,p_provider_reference,p_amount,p_metadata);
 IF was_paid IS FALSE THEN PERFORM public.hg_queue_event_ticket_email(p_ticket_id); END IF;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.hg_queue_event_ticket_email(uuid),public.hg_register_event_with_delivery(uuid,uuid,uuid,boolean,numeric,uuid,jsonb),
 public.hg_register_guest_event_with_delivery(uuid,extensions.citext,text,text,uuid,uuid,jsonb),public.hg_pay_event_with_delivery(uuid,text,text,numeric,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_queue_event_ticket_email(uuid),public.hg_register_event_with_delivery(uuid,uuid,uuid,boolean,numeric,uuid,jsonb),
 public.hg_register_guest_event_with_delivery(uuid,extensions.citext,text,text,uuid,uuid,jsonb),public.hg_pay_event_with_delivery(uuid,text,text,numeric,jsonb) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_claim_notification_dispatch_v2(p_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE d public.notification_deliveries%rowtype; token uuid;
BEGIN
 SELECT * INTO d FROM public.notification_deliveries WHERE id=p_id AND dispatch->>'version'='1' FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('state','missing'); END IF;
 IF d.dispatch->>'state' NOT IN ('queued','claimed','sending') THEN RETURN jsonb_build_object('state',d.dispatch->>'state'); END IF;
 IF d.dispatch->>'state' IN ('claimed','sending') AND (d.dispatch->>'lease_until')::timestamptz>now() THEN RETURN jsonb_build_object('state','busy'); END IF;
 IF d.channel='email' AND d.dispatch->>'state'='sending' THEN
  UPDATE public.notification_deliveries SET status='uncertain',error_message='email_worker_interrupted_after_handoff',
   dispatch=dispatch||jsonb_build_object('state','uncertain') WHERE id=d.id;
  RETURN jsonb_build_object('state','uncertain');
 END IF;
 IF (d.dispatch->>'expires_at')::timestamptz<=now() OR (d.dispatch->>'attempts')::integer>=6 THEN
  UPDATE public.notification_deliveries SET status='failed',error_message='dispatch_retry_expired',dispatch=dispatch||jsonb_build_object('state','failed') WHERE id=d.id;
  RETURN jsonb_build_object('state','failed');
 END IF;
 IF (d.dispatch->>'next_at')::timestamptz>now() THEN RETURN jsonb_build_object('state','deferred'); END IF;
 token:=gen_random_uuid();
 UPDATE public.notification_deliveries SET status='sending',dispatch=dispatch||jsonb_build_object('state','claimed',
  'token',token,'lease_until',now()+interval '2 minutes','attempts',(dispatch->>'attempts')::integer+1) WHERE id=d.id RETURNING * INTO d;
 RETURN jsonb_build_object('state','claimed','token',token,'key',d.dispatch->>'key','channel',d.channel,'payload',d.dispatch_payload);
END $$;


REVOKE ALL ON FUNCTION public.hg_claim_notification_dispatch_v2(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_claim_notification_dispatch_v2(uuid) TO service_role;
