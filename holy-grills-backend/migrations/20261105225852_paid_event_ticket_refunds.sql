CREATE SCHEMA IF NOT EXISTS hg_internal;
GRANT USAGE ON SCHEMA hg_internal TO service_role;
CREATE TABLE hg_internal.event_ticket_refunds (
 id uuid PRIMARY KEY, ticket_id uuid NOT NULL UNIQUE REFERENCES public.event_tickets(id),
 event_id uuid NOT NULL REFERENCES public.events(id),campus_id uuid,user_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
 actor_id uuid,reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 10 AND 500),
 destination text NOT NULL CHECK(destination IN ('wallet','paystack')),
 amount numeric(14,2) NOT NULL CHECK(amount>=0 AND amount::text NOT IN ('NaN','Infinity','-Infinity')),
 hp_amount integer NOT NULL CHECK(hp_amount>=0),state text NOT NULL CHECK(state IN ('queued','claimed','sending','processing','checking','completed','uncertain','failed')),
 payment_reference text,provider_refund_id text UNIQUE,wallet_transaction_id uuid,hp_transaction_id uuid,
 recipient_email text,recipient_name text,token uuid,lease_until timestamptz,next_at timestamptz NOT NULL DEFAULT now(),
 attempts integer NOT NULL DEFAULT 0,error text,review jsonb,notified boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE hg_internal.event_ticket_refunds ENABLE ROW LEVEL SECURITY;
CREATE POLICY event_refunds_service_only ON hg_internal.event_ticket_refunds FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.event_ticket_refunds FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.event_ticket_refunds TO service_role;
CREATE INDEX event_ticket_refunds_due ON hg_internal.event_ticket_refunds(state,next_at);
-- Ticket money/ownership transitions are API/RPC owned. Client reads retain RLS.
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.event_tickets FROM PUBLIC,anon,authenticated;
-- Preserve old checkout initialization during a rolling API deployment. These
-- fields cannot forge ownership, payment state, prices, attendance or refunds.
GRANT UPDATE(metadata,payment_reference,updated_at) ON public.event_tickets TO anon,authenticated;

CREATE OR REPLACE FUNCTION public.hg_request_event_ticket_refund(p_actor_id uuid,p_event_id uuid,p_ticket_id uuid,p_request_id uuid,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;t public.event_tickets%rowtype;r hg_internal.event_ticket_refunds%rowtype;
 w uuid;h uuid;n integer;cost_before jsonb;email_address text;recipient_name text;
BEGIN
 SELECT * INTO a FROM public.profiles WHERE id=p_actor_id AND is_active;
 IF NOT FOUND OR a.role::text NOT IN ('admin','super_admin') THEN RAISE EXCEPTION 'Refund access denied' USING ERRCODE='42501'; END IF;
 IF p_request_id IS NULL OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 10 AND 500 THEN RAISE EXCEPTION 'Invalid refund request'; END IF;
 PERFORM 1 FROM public.events WHERE id=p_event_id FOR UPDATE;
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket_id AND event_id=p_event_id FOR UPDATE;
 IF NOT FOUND OR (a.role::text<>'super_admin' AND (t.campus_id IS NULL OR t.campus_id IS DISTINCT FROM a.campus_id)) THEN RAISE EXCEPTION 'Refund access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE ticket_id=t.id;
 IF FOUND THEN
  IF r.id=p_request_id AND (r.reason<>btrim(p_reason) OR r.actor_id IS DISTINCT FROM p_actor_id) THEN RAISE EXCEPTION 'Refund intent conflict'; END IF;
  RETURN jsonb_build_object('id',r.id,'state',r.state,'destination',r.destination,'amount',r.amount,'hp_returned',r.hp_amount,'idempotent',true);
 END IF;
 IF EXISTS(SELECT 1 FROM hg_internal.event_ticket_refunds WHERE id=p_request_id) THEN RAISE EXCEPTION 'Refund intent conflict'; END IF;
 IF t.status<>'confirmed' OR t.payment_status<>'paid' OR EXISTS(SELECT 1 FROM public.event_checkins WHERE ticket_id=t.id) THEN RAISE EXCEPTION 'Only paid tickets before check-in can be refunded'; END IF;
 IF coalesce(t.wallet_amount_used,0)<0 OR coalesce(t.card_amount_used,0)<0 OR coalesce(t.hp_amount_paid,0)<0
 OR abs(coalesce(t.wallet_amount_used,0)+coalesce(t.card_amount_used,0)-greatest(0,coalesce(t.price_naira,0)-coalesce(t.discount_amount,0)))>0.01 THEN RAISE EXCEPTION 'Ticket financial breakdown invalid'; END IF;
 IF coalesce(t.card_amount_used,0)>0 AND NOT EXISTS(SELECT 1 FROM public.payments WHERE ticket_id=t.id AND provider='paystack'
 AND status='paid' AND reference=t.payment_reference AND abs(amount-t.card_amount_used)<=0.01) THEN RAISE EXCEPTION 'Confirmed card payment receipt required'; END IF;
 IF t.user_id IS NULL AND (coalesce(t.wallet_amount_used,0)>0 OR coalesce(t.hp_amount_paid,0)>0 OR coalesce(t.card_amount_used,0)<=0) THEN RAISE EXCEPTION 'Guest ticket financial breakdown invalid'; END IF;
 IF t.user_id IS NOT NULL THEN
  PERFORM 1 FROM public.wallets WHERE user_id=t.user_id FOR UPDATE;
  PERFORM 1 FROM public.profiles WHERE id=t.user_id FOR UPDATE;
  SELECT email::text,coalesce(nullif(full_name,''),'there') INTO email_address,recipient_name FROM public.profiles WHERE id=t.user_id;
  IF coalesce(t.wallet_amount_used,0)+coalesce(t.card_amount_used,0)>0 THEN
   w:=public.hg_add_wallet_transaction(t.user_id,'refund',coalesce(t.wallet_amount_used,0)+coalesce(t.card_amount_used,0),'Event ticket refund',
    'event_ticket_refund',t.id,'internal-refund','event-ticket-refund:'||t.id,p_actor_id,jsonb_build_object('event_id',t.event_id),t.campus_id);
  END IF;
  IF coalesce(t.hp_amount_paid,0)>0 THEN
   h:=public.hg_add_hp_transaction(t.user_id,'adjustment',t.hp_amount_paid,'event_ticket_refund','event_ticket_refund',t.id,p_actor_id,jsonb_build_object('event_id',t.event_id),NULL,t.campus_id);
  END IF;
 ELSE email_address:=t.guest_email::text;recipient_name:=coalesce(t.guest_name,'there'); END IF;
 WITH released AS (DELETE FROM public.promo_code_uses WHERE ticket_id=t.id RETURNING id) SELECT count(*) INTO n FROM released;
 IF n>0 THEN UPDATE public.promo_codes SET used_count=greatest(0,used_count-n) WHERE id=t.promo_code_id; END IF;
 IF t.tier_id IS NOT NULL THEN UPDATE public.event_ticket_tiers SET sold_count=greatest(0,sold_count-1),updated_at=now() WHERE id=t.tier_id; END IF;
 INSERT INTO hg_internal.event_ticket_refunds(id,ticket_id,event_id,campus_id,user_id,actor_id,reason,destination,amount,hp_amount,state,payment_reference,
 wallet_transaction_id,hp_transaction_id,recipient_email,recipient_name)
 VALUES(p_request_id,t.id,t.event_id,t.campus_id,t.user_id,p_actor_id,btrim(p_reason),CASE WHEN t.user_id IS NOT NULL THEN 'wallet' ELSE 'paystack' END,
 coalesce(t.wallet_amount_used,0)+coalesce(t.card_amount_used,0),coalesce(t.hp_amount_paid,0),CASE WHEN t.user_id IS NOT NULL THEN 'completed' ELSE 'queued' END,
 t.payment_reference,w,h,email_address,recipient_name) RETURNING * INTO r;
 SELECT jsonb_agg(to_jsonb(x)) INTO cost_before FROM public.redemption_cost_log x WHERE event_ticket_id=t.id;
 UPDATE public.redemption_cost_log SET actual_cost=0,hp_spent=0 WHERE event_ticket_id=t.id;
 UPDATE public.event_tickets SET status='cancelled',payment_status=CASE WHEN t.user_id IS NOT NULL THEN 'refunded' ELSE 'refund_pending' END,updated_at=now() WHERE id=t.id;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value)
 VALUES(a.id,a.role::text,'event_ticket_refund',t.id::text,'refund_requested',jsonb_build_object('refund_id',r.id,'destination',r.destination,'amount',r.amount,'hp_returned',r.hp_amount,'reason',r.reason,'redemption_cost_before',cost_before));
 RETURN jsonb_build_object('id',r.id,'state',r.state,'destination',r.destination,'amount',r.amount,'hp_returned',r.hp_amount,'idempotent',false);
END $$;

CREATE OR REPLACE FUNCTION public.hg_event_refund_list(p_actor_id uuid,p_event_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;e public.events%rowtype;result jsonb;
BEGIN
 SELECT * INTO a FROM public.profiles WHERE id=p_actor_id AND is_active;
 SELECT * INTO e FROM public.events WHERE id=p_event_id;
 IF a.id IS NULL OR e.id IS NULL OR a.role::text NOT IN ('admin','super_admin') OR (a.role::text<>'super_admin' AND (e.campus_id IS NULL OR e.campus_id IS DISTINCT FROM a.campus_id)) THEN RAISE EXCEPTION 'Refund access denied' USING ERRCODE='42501'; END IF;
 SELECT coalesce(jsonb_agg(x),'[]') INTO result FROM (SELECT id,ticket_id,event_id,destination,amount,hp_amount,state,provider_refund_id,error,recipient_name,recipient_email,reason,created_at
 FROM hg_internal.event_ticket_refunds WHERE event_id=p_event_id ORDER BY created_at DESC LIMIT 200)x;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.hg_due_event_refunds(p_limit integer DEFAULT 10)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce(jsonb_agg(id),'[]') FROM (SELECT id FROM hg_internal.event_ticket_refunds WHERE
 (state='completed' AND user_id IS NOT NULL AND NOT notified) OR (destination='paystack' AND next_at<=now() AND
 (state IN ('queued','processing') OR (state IN ('claimed','sending','checking') AND lease_until<=now()))) ORDER BY created_at LIMIT greatest(1,least(coalesce(p_limit,10),50)))q;
$$;

CREATE OR REPLACE FUNCTION public.hg_claim_event_refund(p_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE r hg_internal.event_ticket_refunds%rowtype;v_token uuid;
BEGIN
 SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('state','missing'); END IF;
 IF r.state='completed' THEN RETURN jsonb_build_object('state','completed','user_id',r.user_id,'notified',r.notified,'ticket_id',r.ticket_id,'id',r.id,'amount',r.amount,'hp_amount',r.hp_amount); END IF;
 IF r.state IN ('uncertain','failed') THEN RETURN jsonb_build_object('state',r.state); END IF;
 IF r.lease_until>now() AND r.state IN ('claimed','sending','checking') THEN RETURN jsonb_build_object('state','busy'); END IF;
 IF r.state='sending' THEN UPDATE hg_internal.event_ticket_refunds SET state='uncertain',error='worker_interrupted_after_provider_handoff',updated_at=now() WHERE id=r.id; RETURN jsonb_build_object('state','uncertain'); END IF;
 IF r.provider_refund_id IS NULL AND r.attempts>=8 THEN UPDATE hg_internal.event_ticket_refunds SET state='failed',error='refund_attempt_budget_exhausted' WHERE id=r.id;RETURN jsonb_build_object('state','failed');END IF;
 IF r.next_at>now() THEN RETURN jsonb_build_object('state','deferred'); END IF;
 v_token:=gen_random_uuid();
 UPDATE hg_internal.event_ticket_refunds SET state=CASE WHEN provider_refund_id IS NULL THEN 'claimed' ELSE 'checking' END,token=v_token,lease_until=now()+interval '2 minutes',attempts=attempts+1,updated_at=now() WHERE id=r.id RETURNING * INTO r;
 RETURN jsonb_build_object('state',r.state,'id',r.id,'token',v_token,'amount',r.amount,'reference',r.payment_reference,'provider_refund_id',r.provider_refund_id);
END $$;

CREATE OR REPLACE FUNCTION public.hg_begin_event_refund(p_id uuid,p_token uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE n integer;
BEGIN
 UPDATE hg_internal.event_ticket_refunds SET state='sending',updated_at=now() WHERE id=p_id AND token=p_token AND state='claimed' AND lease_until>now();
 GET DIAGNOSTICS n=ROW_COUNT;RETURN n=1;
END $$;

CREATE OR REPLACE FUNCTION public.hg_finish_event_refund(p_id uuid,p_token uuid,p_state text,p_provider_id text DEFAULT NULL,p_error text DEFAULT NULL)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE r hg_internal.event_ticket_refunds%rowtype;t public.event_tickets%rowtype;e public.events%rowtype;
BEGIN
 SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR r.token IS DISTINCT FROM p_token OR r.state NOT IN ('claimed','sending','checking','uncertain') THEN RETURN false; END IF;
 IF p_state IS NULL OR p_state NOT IN ('queued','processing','completed','uncertain','failed') THEN RAISE EXCEPTION 'Invalid refund outcome'; END IF;
 IF p_state IN ('processing','completed') AND nullif(btrim(p_provider_id),'') IS NULL THEN RAISE EXCEPTION 'Provider refund ID required'; END IF;
 IF r.provider_refund_id IS NOT NULL AND r.provider_refund_id IS DISTINCT FROM p_provider_id THEN RAISE EXCEPTION 'Provider refund ID changed'; END IF;
 UPDATE hg_internal.event_ticket_refunds SET state=p_state,provider_refund_id=coalesce(p_provider_id,provider_refund_id),error=left(p_error,500),
 lease_until=NULL,next_at=now()+CASE WHEN r.attempts<4 THEN interval '15 minutes' ELSE interval '1 hour' END,updated_at=now() WHERE id=r.id;
 IF p_state='completed' THEN
  UPDATE public.event_tickets SET payment_status='refunded',updated_at=now() WHERE id=r.ticket_id;
  SELECT * INTO t FROM public.event_tickets WHERE id=r.ticket_id;
  SELECT * INTO e FROM public.events WHERE id=r.event_id;
  INSERT INTO public.notification_deliveries(id,channel,status,campus_id,dispatch,dispatch_payload)
  VALUES(r.id,'email','queued',r.campus_id,jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
   jsonb_build_object('kind','event_refund_email','ticket_id',t.id,'event_id',t.event_id,'refund_id',r.id,'notification',jsonb_build_object('user_id',NULL,'type','event_ticket_refunded',
   'title','Your event ticket refund','body','Your refund for '||e.title||' has been processed. ₦'||r.amount::text||' was returned to your original payment method. Your bank may take time to display it.',
   'email',lower(btrim(r.recipient_email)),'name',r.recipient_name,'metadata','{}'::jsonb))) ON CONFLICT(id) DO NOTHING;
 END IF;
 RETURN true;
END $$;

CREATE OR REPLACE FUNCTION public.hg_ack_event_refund_notice(p_id uuid)
RETURNS void LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 UPDATE hg_internal.event_ticket_refunds SET notified=true WHERE id=p_id AND state='completed' AND user_id IS NOT NULL;
$$;

CREATE OR REPLACE FUNCTION public.hg_review_event_refund(p_actor_id uuid,p_event_id uuid,p_id uuid,p_review_id uuid,p_outcome text,p_provider_id text,p_evidence text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;r hg_internal.event_ticket_refunds%rowtype;v_review jsonb;
BEGIN
 SELECT * INTO a FROM public.profiles WHERE id=p_actor_id AND is_active;
 SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE id=p_id FOR UPDATE;
 IF a.id IS NULL OR r.id IS NULL OR r.event_id IS DISTINCT FROM p_event_id OR a.role::text NOT IN ('admin','super_admin') OR (a.role::text<>'super_admin' AND (r.campus_id IS NULL OR r.campus_id IS DISTINCT FROM a.campus_id)) THEN RAISE EXCEPTION 'Refund access denied' USING ERRCODE='42501'; END IF;
 IF p_review_id IS NULL OR p_outcome IS NULL OR p_outcome NOT IN ('not_sent','lookup') OR p_evidence IS NULL OR length(btrim(p_evidence)) NOT BETWEEN 10 AND 500
 OR (p_outcome='lookup' AND (nullif(btrim(p_provider_id),'') IS NULL OR p_provider_id !~ '^[0-9]{1,30}$')) THEN RAISE EXCEPTION 'Provider evidence required'; END IF;
 v_review:=jsonb_build_object('id',p_review_id,'actor',p_actor_id,'outcome',p_outcome,'provider_id',p_provider_id,'evidence',btrim(p_evidence));
 IF r.review->>'id'=p_review_id::text THEN IF r.review IS DISTINCT FROM v_review THEN RAISE EXCEPTION 'Review intent conflict'; END IF;RETURN jsonb_build_object('id',r.id,'state',r.state,'idempotent',true);END IF;
 IF r.destination<>'paystack' OR r.state NOT IN ('uncertain','failed') THEN RAISE EXCEPTION 'Refund is not awaiting review'; END IF;
 IF p_outcome='not_sent' AND r.provider_refund_id IS NOT NULL THEN RAISE EXCEPTION 'Existing provider refund must be checked'; END IF;
 UPDATE hg_internal.event_ticket_refunds SET state=CASE WHEN p_outcome='lookup' THEN 'processing' ELSE 'queued' END,
 provider_refund_id=CASE WHEN p_outcome='lookup' THEN p_provider_id ELSE NULL END,review=v_review,attempts=0,token=NULL,lease_until=NULL,next_at=now(),error=NULL,updated_at=now() WHERE id=r.id;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value) VALUES(a.id,a.role::text,'event_ticket_refund',r.ticket_id::text,'refund_provider_review',v_review);
 RETURN jsonb_build_object('id',r.id,'state',CASE WHEN p_outcome='lookup' THEN 'processing' ELSE 'queued' END,'idempotent',false);
END $$;

REVOKE ALL ON FUNCTION public.hg_request_event_ticket_refund(uuid,uuid,uuid,uuid,text),public.hg_event_refund_list(uuid,uuid),public.hg_due_event_refunds(integer),public.hg_claim_event_refund(uuid),public.hg_begin_event_refund(uuid,uuid),public.hg_finish_event_refund(uuid,uuid,text,text,text),public.hg_ack_event_refund_notice(uuid),public.hg_review_event_refund(uuid,uuid,uuid,uuid,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_request_event_ticket_refund(uuid,uuid,uuid,uuid,text),public.hg_event_refund_list(uuid,uuid),public.hg_due_event_refunds(integer),public.hg_claim_event_refund(uuid),public.hg_begin_event_refund(uuid,uuid),public.hg_finish_event_refund(uuid,uuid,text,text,text),public.hg_ack_event_refund_notice(uuid),public.hg_review_event_refund(uuid,uuid,uuid,uuid,text,text,text) TO service_role;
-- Serialize admission with registration/refund before profile/ticket locks.
DO $patch$ DECLARE src text;BEGIN
 SELECT pg_get_functiondef('public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer)'::regprocedure) INTO src;
 IF src NOT LIKE '%-- Same profile-first order%' THEN RAISE EXCEPTION 'Unexpected admission definition';END IF;
 src:=replace(src,' -- Same profile-first order',' PERFORM 1 FROM public.events WHERE id=p_event_id FOR UPDATE;'||E'\n -- Same profile-first order');
 EXECUTE src;
END $patch$;
-- An abandoned HP reservation did not consume an event subsidy either.
DO $patch$ DECLARE src text;marker text:=' UPDATE public.event_tickets SET status=''cancelled''';BEGIN
 SELECT pg_get_functiondef('public.hg_release_expired_event_reservation(uuid)'::regprocedure) INTO src;
 IF position(marker in src)=0 THEN RAISE EXCEPTION 'Unexpected expiry definition';END IF;
 src:=replace(src,marker,' receipt:=receipt||jsonb_build_object(''redemption_cost_before'',(SELECT jsonb_agg(to_jsonb(x)) FROM public.redemption_cost_log x WHERE event_ticket_id=t.id));'||E'\n UPDATE public.redemption_cost_log SET actual_cost=0,hp_spent=0 WHERE event_ticket_id=t.id;\n'||marker);
 EXECUTE src;
END $patch$;
