DO $source_guard$ BEGIN
 IF md5(pg_get_functiondef('public.hg_request_event_ticket_refund(uuid,uuid,uuid,uuid,text)'::regprocedure))<>'4f070ec13da808180346f57e8393ff7e' THEN RAISE EXCEPTION 'Source changed: hg_request_event_ticket_refund';END IF;
 IF md5(pg_get_functiondef('public.hg_pay_event_with_delivery(uuid,text,text,numeric,jsonb)'::regprocedure))<>'26021d0212ead719e654887c6d82bdf2' THEN RAISE EXCEPTION 'Source changed: hg_pay_event_with_delivery';END IF;
 IF md5(pg_get_functiondef('public.hg_claim_event_refund(uuid)'::regprocedure))<>'c5c08913eba6a1b15e313d1d615cc43c' THEN RAISE EXCEPTION 'Source changed: hg_claim_event_refund';END IF;
 IF md5(pg_get_functiondef('public.hg_link_verified_event_tickets(uuid)'::regprocedure))<>'a39be7fa996d6d63391c01182b5ad16e' THEN RAISE EXCEPTION 'Source changed: hg_link_verified_event_tickets';END IF;
END $source_guard$;
-- New approvals stay in the ecosystem; existing provider refunds are unchanged.
DO $$ DECLARE item record;BEGIN
 FOR item IN SELECT conname FROM pg_constraint WHERE conrelid='hg_internal.event_ticket_refunds'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%state = ANY%' LOOP
  EXECUTE format('ALTER TABLE hg_internal.event_ticket_refunds DROP CONSTRAINT %I',item.conname);
 END LOOP;
END $$;
ALTER TABLE hg_internal.event_ticket_refunds ADD CONSTRAINT event_ticket_refunds_state_check CHECK(state IN('queued','claimed','sending','processing','checking','completed','uncertain','failed','awaiting_account'));

CREATE OR REPLACE FUNCTION public.hg_request_event_ticket_refund(p_actor_id uuid, p_event_id uuid, p_ticket_id uuid, p_request_id uuid, p_reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE a public.profiles%rowtype;t public.event_tickets%rowtype;r hg_internal.event_ticket_refunds%rowtype;
 automatic boolean:=p_actor_id IS NULL AND coalesce(auth.role(),'')='service_role' AND current_setting('hg.event_late_refund',true)=p_ticket_id::text;
 w uuid;h uuid;n integer;cost_before jsonb;email_address text;recipient_name text;
BEGIN
 IF automatic THEN a.id:=NULL;a.role:='super_admin';ELSE
 SELECT * INTO a FROM public.profiles WHERE id=p_actor_id AND (is_active OR EXISTS(SELECT 1 FROM hg_internal.event_organizer_reviews cancel_approval JOIN public.events event ON event.id=cancel_approval.event_id WHERE cancel_approval.event_id=p_event_id AND cancel_approval.cancelled_by=p_actor_id AND event.metadata->>'lifecycle_status'='cancelled'));
 IF NOT FOUND OR (a.role::text NOT IN ('admin','super_admin') AND NOT EXISTS(SELECT 1 FROM hg_internal.event_organizer_reviews cancel_approval JOIN public.events event ON event.id=cancel_approval.event_id WHERE cancel_approval.event_id=p_event_id AND cancel_approval.cancelled_by=p_actor_id AND event.metadata->>'lifecycle_status'='cancelled')) THEN RAISE EXCEPTION 'Refund access denied' USING ERRCODE='42501'; END IF;
 END IF;
 IF p_request_id IS NULL OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 10 AND 500 THEN RAISE EXCEPTION 'Invalid refund request'; END IF;
 PERFORM 1 FROM public.events WHERE id=p_event_id FOR UPDATE;
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket_id AND event_id=p_event_id FOR UPDATE;
 IF NOT FOUND OR (a.role::text<>'super_admin' AND (t.campus_id IS NULL OR t.campus_id IS DISTINCT FROM a.campus_id) AND NOT EXISTS(SELECT 1 FROM hg_internal.event_organizer_reviews cancel_approval JOIN public.events event ON event.id=cancel_approval.event_id WHERE cancel_approval.event_id=p_event_id AND cancel_approval.cancelled_by=p_actor_id AND event.metadata->>'lifecycle_status'='cancelled')) THEN RAISE EXCEPTION 'Refund access denied' USING ERRCODE='42501'; END IF;
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
 VALUES(p_request_id,t.id,t.event_id,t.campus_id,t.user_id,p_actor_id,btrim(p_reason),'wallet',
 coalesce(t.wallet_amount_used,0)+coalesce(t.card_amount_used,0),coalesce(t.hp_amount_paid,0),CASE WHEN t.user_id IS NOT NULL THEN 'completed' ELSE 'awaiting_account' END,
 t.payment_reference,w,h,email_address,recipient_name) RETURNING * INTO r;
 SELECT jsonb_agg(to_jsonb(x)) INTO cost_before FROM public.redemption_cost_log x WHERE event_ticket_id=t.id;
 UPDATE public.redemption_cost_log SET actual_cost=0,hp_spent=0 WHERE event_ticket_id=t.id;
 UPDATE public.event_tickets SET status='cancelled',payment_status=CASE WHEN t.user_id IS NOT NULL THEN 'refunded' ELSE 'refund_pending' END,updated_at=now() WHERE id=t.id;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value)
 VALUES(a.id,CASE WHEN automatic THEN 'system' ELSE a.role::text END,'event_ticket_refund',t.id::text,'refund_requested',jsonb_build_object('refund_id',r.id,'destination',r.destination,'amount',r.amount,'hp_returned',r.hp_amount,'reason',r.reason,'redemption_cost_before',cost_before));
 RETURN jsonb_build_object('id',r.id,'state',r.state,'destination',r.destination,'amount',r.amount,'hp_returned',r.hp_amount,'idempotent',false);
END $function$;

CREATE OR REPLACE FUNCTION public.hg_pay_event_with_delivery(p_ticket_id uuid, p_provider text DEFAULT NULL::text, p_provider_reference text DEFAULT NULL::text, p_amount numeric DEFAULT NULL::numeric, p_metadata jsonb DEFAULT '{}'::jsonb)
 RETURNS uuid
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE t event_tickets%rowtype;e events%rowtype;result uuid;actor uuid;refund_result jsonb;expired boolean:=false;previous_mode text:=coalesce(current_setting('hg.event_late_refund',true),'');refund_reason text;
BEGIN
 SELECT event_id INTO e.id FROM event_tickets WHERE id=p_ticket_id;
 SELECT * INTO e FROM events WHERE id=e.id FOR UPDATE;
 SELECT * INTO t FROM event_tickets WHERE id=p_ticket_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Ticket not found';END IF;
 IF p_amount IS NOT NULL AND (p_amount::text IN('NaN','Infinity','-Infinity') OR abs(p_amount-t.card_amount_used)>0.01) THEN RAISE EXCEPTION 'Amount mismatch';END IF;
 IF t.payment_reference IS NOT NULL AND p_provider_reference IS DISTINCT FROM t.payment_reference THEN RAISE EXCEPTION 'Payment reference mismatch';END IF;
  IF EXISTS(SELECT 1 FROM hg_internal.event_ticket_refunds WHERE ticket_id=t.id) THEN SELECT id INTO result FROM payments WHERE ticket_id=t.id AND reference=p_provider_reference;RETURN result;END IF;
 IF e.metadata->>'lifecycle_status'='cancelled' OR (t.status='cancelled' AND t.payment_status='expired' AND t.metadata ? 'expiry_receipt') THEN
  SELECT cancelled_by INTO actor FROM hg_internal.event_organizer_reviews WHERE event_id=e.id;
  IF actor IS NULL AND e.metadata->>'lifecycle_status'='cancelled' THEN RAISE EXCEPTION 'HG_EVENT_CANCEL_REFUND_UNAVAILABLE';END IF;
  refund_reason:=CASE WHEN e.metadata->>'lifecycle_status'='cancelled' THEN e.metadata->>'change_reason' ELSE p_metadata->>'_recovery_reason' END;
  IF length(coalesce(refund_reason,'')) NOT BETWEEN 10 AND 500 THEN RAISE EXCEPTION 'Recovery explanation unavailable';END IF;
  IF actor IS NULL THEN PERFORM set_config('hg.event_late_refund',t.id::text,true);END IF;
  IF t.status='cancelled' AND t.metadata ? 'expiry_receipt' AND t.payment_status='expired' THEN
   expired:=true;
   -- The expiry receipt already returned wallet/HP and released the seat. Only
   -- this newly received card amount is refundable; do not release it twice.
   UPDATE event_tickets SET status='pending_payment',payment_status='pending',tier_id=NULL,wallet_amount_used=0,hp_amount_paid=0,discount_amount=0,price_naira=card_amount_used WHERE id=t.id;
  END IF;
  result:=hg_mark_event_ticket_paid(t.id,p_provider,p_provider_reference,p_amount,p_metadata);
  IF NOT EXISTS(SELECT 1 FROM event_checkins WHERE ticket_id=t.id) THEN
   refund_result:=hg_request_event_ticket_refund(actor,e.id,t.id,md5('event-cancel-refund:'||e.id||':'||t.id)::uuid,refund_reason);
  END IF;
  IF expired THEN UPDATE event_tickets SET tier_id=t.tier_id,wallet_amount_used=t.wallet_amount_used,hp_amount_paid=t.hp_amount_paid,discount_amount=t.discount_amount,price_naira=t.price_naira WHERE id=t.id;END IF;
  PERFORM set_config('hg.event_late_refund',previous_mode,true);
  RETURN result;
 END IF;
 result:=hg_mark_event_ticket_paid(p_ticket_id,p_provider,p_provider_reference,p_amount,p_metadata);
 IF t.payment_status<>'paid' THEN PERFORM hg_queue_event_ticket_email(p_ticket_id);END IF;
 RETURN result;
END $function$;

CREATE OR REPLACE FUNCTION public.hg_claim_event_refund(p_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE r hg_internal.event_ticket_refunds%rowtype;v_token uuid;
BEGIN
 SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('state','missing'); END IF;
 IF r.state='completed' THEN RETURN jsonb_build_object('state','completed','user_id',r.user_id,'notified',r.notified,'ticket_id',r.ticket_id,'id',r.id,'amount',r.amount,'hp_amount',r.hp_amount); END IF;
 IF r.destination='wallet' AND r.state<>'completed' THEN RETURN jsonb_build_object('state',r.state);END IF;
 IF r.state IN ('uncertain','failed') THEN RETURN jsonb_build_object('state',r.state); END IF;
 IF r.lease_until>now() AND r.state IN ('claimed','sending','checking') THEN RETURN jsonb_build_object('state','busy'); END IF;
 IF r.state='sending' THEN UPDATE hg_internal.event_ticket_refunds SET state='uncertain',error='worker_interrupted_after_provider_handoff',updated_at=now() WHERE id=r.id; RETURN jsonb_build_object('state','uncertain'); END IF;
 IF r.provider_refund_id IS NULL AND r.attempts>=8 THEN UPDATE hg_internal.event_ticket_refunds SET state='failed',error='refund_attempt_budget_exhausted' WHERE id=r.id;RETURN jsonb_build_object('state','failed');END IF;
 IF r.next_at>now() THEN RETURN jsonb_build_object('state','deferred'); END IF;
 v_token:=gen_random_uuid();
 UPDATE hg_internal.event_ticket_refunds SET state=CASE WHEN provider_refund_id IS NULL THEN 'claimed' ELSE 'checking' END,token=v_token,lease_until=now()+interval '2 minutes',attempts=attempts+1,updated_at=now() WHERE id=r.id RETURNING * INTO r;
 RETURN jsonb_build_object('state',r.state,'id',r.id,'token',v_token,'amount',r.amount,'reference',r.payment_reference,'provider_refund_id',r.provider_refund_id);
END $function$;


CREATE OR REPLACE FUNCTION public.hg_claim_guest_event_refunds(p_actor uuid)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE verified_email text; candidate record; r hg_internal.event_ticket_refunds%rowtype;t public.event_tickets%rowtype;w uuid;credited integer:=0;claim_ids uuid[];
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT hg_internal.verified_event_ticket_email(p_actor) INTO verified_email FROM public.profiles WHERE id=p_actor AND is_active;
 IF verified_email IS NULL THEN RETURN 0;END IF;
 SELECT array_agg(id) INTO claim_ids FROM (
  SELECT f.id FROM hg_internal.event_ticket_refunds f JOIN public.event_tickets et ON et.id=f.ticket_id
  WHERE f.state='awaiting_account' AND f.destination='wallet' AND lower(btrim(et.guest_email::text))=verified_email AND (et.user_id IS NULL OR et.user_id=p_actor)
  ORDER BY f.event_id,f.ticket_id LIMIT 100
 ) eligible;
 IF claim_ids IS NULL THEN RETURN 0;END IF;
 -- Lock every selected event before any wallet/profile lock, including when
 -- several refunds for the same account are claimed together.
 PERFORM id FROM public.events WHERE id IN(SELECT event_id FROM hg_internal.event_ticket_refunds WHERE id=ANY(claim_ids)) ORDER BY id FOR UPDATE;
 FOR candidate IN SELECT id,event_id,ticket_id FROM hg_internal.event_ticket_refunds WHERE id=ANY(claim_ids) ORDER BY event_id,ticket_id LOOP
  PERFORM 1 FROM public.events WHERE id=candidate.event_id FOR UPDATE;
  PERFORM 1 FROM public.wallets WHERE user_id=p_actor FOR UPDATE;
  PERFORM 1 FROM public.profiles WHERE id=p_actor AND is_active FOR UPDATE;
  IF NOT FOUND THEN CONTINUE;END IF;
  SELECT * INTO t FROM public.event_tickets WHERE id=candidate.ticket_id FOR UPDATE;
  SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE id=candidate.id FOR UPDATE;
  IF r.state<>'awaiting_account' OR r.destination<>'wallet' OR lower(btrim(t.guest_email::text)) IS DISTINCT FROM verified_email OR (t.user_id IS NOT NULL AND t.user_id<>p_actor) THEN CONTINUE;END IF;
  IF r.amount>0 THEN
   w:=public.hg_add_wallet_transaction(p_actor,'refund',r.amount,'Event ticket refund','event_ticket_refund',t.id,'internal-refund','event-ticket-refund:'||t.id,r.actor_id,jsonb_build_object('event_id',t.event_id),t.campus_id);
  END IF;
  UPDATE public.event_tickets SET user_id=p_actor,is_guest=false,payment_status='refunded',updated_at=now() WHERE id=t.id;
  UPDATE hg_internal.event_ticket_refunds SET user_id=p_actor,wallet_transaction_id=w,state='completed',updated_at=now(),notified=false WHERE id=r.id;
  credited:=credited+1;
 END LOOP;
 RETURN credited;
END $$;
REVOKE ALL ON FUNCTION public.hg_claim_guest_event_refunds(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_claim_guest_event_refunds(uuid) TO service_role;

REVOKE ALL ON FUNCTION public.hg_request_event_ticket_refund(uuid,uuid,uuid,uuid,text),public.hg_pay_event_with_delivery(uuid,text,text,numeric,jsonb),public.hg_claim_event_refund(uuid),public.hg_link_verified_event_tickets(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_request_event_ticket_refund(uuid,uuid,uuid,uuid,text),public.hg_pay_event_with_delivery(uuid,text,text,numeric,jsonb),public.hg_claim_event_refund(uuid),public.hg_link_verified_event_tickets(uuid) TO service_role;
