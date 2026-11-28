-- One purchaser/payment; each attendee retains a separate ticket, answers and HP.
CREATE TABLE hg_internal.event_ticket_groups (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_id uuid NOT NULL REFERENCES public.events(id),
 buyer_user_id uuid REFERENCES public.profiles(id), buyer_email text NOT NULL, buyer_name text NOT NULL, buyer_phone text NOT NULL,
 idempotency_key text NOT NULL, fingerprint text NOT NULL, total numeric(14,2) NOT NULL DEFAULT 0,
 wallet_amount numeric(14,2) NOT NULL DEFAULT 0, card_amount numeric(14,2) NOT NULL DEFAULT 0,
 payment_status text NOT NULL DEFAULT 'pending' CHECK(payment_status IN('pending','paid','not_required')),
 payment_reference text UNIQUE, authorization_url text, expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(total>=0 AND wallet_amount>=0 AND card_amount>=0 AND total=wallet_amount+card_amount),
 UNIQUE(event_id,idempotency_key)
);
ALTER TABLE hg_internal.event_ticket_groups ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.event_ticket_groups FROM PUBLIC,anon,authenticated;
GRANT ALL ON hg_internal.event_ticket_groups TO service_role;
ALTER TABLE public.event_tickets ADD COLUMN group_id uuid REFERENCES hg_internal.event_ticket_groups(id);
CREATE INDEX event_tickets_group ON public.event_tickets(group_id) WHERE group_id IS NOT NULL;
CREATE INDEX event_groups_buyer ON hg_internal.event_ticket_groups(buyer_user_id,created_at DESC) WHERE buyer_user_id IS NOT NULL;
CREATE INDEX event_groups_guest_buyer ON hg_internal.event_ticket_groups(lower(btrim(buyer_email))) WHERE buyer_user_id IS NULL;

CREATE FUNCTION hg_internal.event_financial_ticket(p_id uuid) RETURNS public.event_tickets
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,extensions AS $$
DECLARE t public.event_tickets; g hg_internal.event_ticket_groups;
BEGIN
 SELECT * INTO t FROM public.event_tickets WHERE id=p_id;
 IF t.group_id IS NOT NULL THEN
  SELECT * INTO STRICT g FROM hg_internal.event_ticket_groups WHERE id=t.group_id;
  t.user_id:=g.buyer_user_id;t.guest_email:=g.buyer_email;t.guest_name:=g.buyer_name;
 END IF;
 RETURN t;
END $$;
REVOKE ALL ON FUNCTION hg_internal.event_financial_ticket(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.event_financial_ticket(uuid) TO service_role;

CREATE FUNCTION public.hg_event_group_read(p_id uuid) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path=public,extensions AS $$
 SELECT to_jsonb(g)||jsonb_build_object('tickets',coalesce((SELECT jsonb_agg(to_jsonb(t)||jsonb_build_object('tier_name',tier.name,'checked_in',EXISTS(SELECT 1 FROM public.event_checkins ci WHERE ci.ticket_id=t.id)) ORDER BY t.created_at,t.id)
 FROM public.event_tickets t LEFT JOIN public.event_ticket_tiers tier ON tier.id=t.tier_id WHERE t.group_id=g.id),'[]'::jsonb))
 FROM hg_internal.event_ticket_groups g WHERE g.id=p_id;
$$;
REVOKE ALL ON FUNCTION public.hg_event_group_read(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_event_group_read(uuid) TO service_role;

CREATE FUNCTION hg_internal.queue_event_group_email(p_id uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,extensions AS $$
DECLARE g hg_internal.event_ticket_groups;e public.events;
BEGIN
 SELECT * INTO g FROM hg_internal.event_ticket_groups WHERE id=p_id;
 IF NOT FOUND OR g.payment_status NOT IN('paid','not_required') THEN RETURN NULL;END IF;
 SELECT * INTO e FROM public.events WHERE id=g.event_id;
 INSERT INTO public.notification_deliveries(id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
 VALUES(g.id,g.buyer_user_id,'email','queued',e.campus_id,
  jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
  jsonb_build_object('kind','event_group_email','group_id',g.id,'event_id',g.event_id,'notification',
   jsonb_build_object('user_id',g.buyer_user_id,'type','event_group_booked','title','','body','',
    'email',lower(btrim(g.buyer_email)),'name',g.buyer_name,'metadata','{}'::jsonb))) ON CONFLICT(id) DO NOTHING;
 RETURN g.id;
END $$;
REVOKE ALL ON FUNCTION hg_internal.queue_event_group_email(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.queue_event_group_email(uuid) TO service_role;

CREATE FUNCTION public.hg_create_event_group(p_event uuid,p_buyer uuid,p_contact jsonb,p_attendees jsonb,
 p_method text,p_wallet numeric,p_promo uuid,p_key text,p_fingerprint text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,extensions AS $$
DECLARE e public.events; g hg_internal.event_ticket_groups; a jsonb; r jsonb; t public.event_tickets;
 ids uuid[]:='{}'; tid uuid; remaining numeric; share numeric; amount numeric; v_total numeric:=0;v_subtotal numeric:=0; claimed text;
BEGIN
 IF jsonb_typeof(p_attendees)<>'array' OR jsonb_array_length(p_attendees) NOT BETWEEN 1 AND 10
 OR p_method NOT IN('wallet','card','split') OR length(coalesce(p_key,'')) NOT BETWEEN 10 AND 200
 OR length(coalesce(p_fingerprint,''))<>64 OR p_contact->>'email' IS NULL
 OR p_wallet IS NULL OR p_wallet<0 OR p_wallet::text IN('NaN','Infinity','-Infinity') THEN RAISE EXCEPTION 'HG_GROUP_INVALID';END IF;
 -- Same lock order as individual reservation: event, then account/financial rows.
 SELECT * INTO e FROM public.events WHERE id=p_event FOR UPDATE;
 SELECT * INTO g FROM hg_internal.event_ticket_groups WHERE event_id=p_event AND idempotency_key=p_key;
 IF FOUND THEN
  IF g.fingerprint<>p_fingerprint OR g.buyer_user_id IS DISTINCT FROM p_buyer OR lower(g.buyer_email)<>lower(p_contact->>'email') THEN RAISE EXCEPTION 'HG_GROUP_INTENT_CONFLICT';END IF;
  RETURN public.hg_event_group_read(g.id);
 END IF;
 IF e.id IS NULL OR NOT e.is_published OR e.metadata->>'lifecycle_status'='cancelled' OR e.ends_at<=now() THEN RAISE EXCEPTION 'HG_GROUP_EVENT_UNAVAILABLE';END IF;
 IF NOT coalesce((SELECT is_active FROM public.feature_flags WHERE feature_name='events' AND (campus_id=e.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1),false) THEN RAISE EXCEPTION 'HG_GROUP_EVENT_UNAVAILABLE';END IF;
 IF p_buyer IS NULL AND (p_method<>'card' OR p_wallet<>0) THEN RAISE EXCEPTION 'HG_GROUP_GUEST_CARD_ONLY';END IF;
 IF p_buyer IS NOT NULL THEN
  PERFORM 1 FROM public.wallets WHERE user_id=p_buyer FOR UPDATE NOWAIT;
  PERFORM 1 FROM public.profiles WHERE id=p_buyer AND is_active AND (e.campus_id IS NULL OR campus_id=e.campus_id) FOR UPDATE NOWAIT;
  IF NOT FOUND THEN RAISE EXCEPTION 'HG_GROUP_BUYER_UNAVAILABLE';END IF;
 END IF;
 IF (SELECT count(DISTINCT lower(btrim(x->>'email'))) FROM jsonb_array_elements(p_attendees)x)<>jsonb_array_length(p_attendees) THEN RAISE EXCEPTION 'HG_GROUP_DUPLICATE_ATTENDEE';END IF;
 INSERT INTO hg_internal.event_ticket_groups(event_id,buyer_user_id,buyer_email,buyer_name,buyer_phone,idempotency_key,fingerprint)
 VALUES(p_event,p_buyer,lower(btrim(p_contact->>'email')),p_contact->>'name',p_contact->>'phone',p_key,p_fingerprint) RETURNING * INTO g;
 FOR a IN SELECT * FROM jsonb_array_elements(p_attendees) LOOP
  IF EXISTS(SELECT 1 FROM public.event_tickets ticket LEFT JOIN auth.users owner ON owner.id=ticket.user_id
   WHERE ticket.event_id=p_event AND ticket.status NOT IN('cancelled','canceled','expired')
   AND (lower(btrim(ticket.guest_email::text))=lower(btrim(a->>'email')) OR (owner.email_confirmed_at IS NOT NULL AND lower(btrim(owner.email))=lower(btrim(a->>'email'))))) THEN RAISE EXCEPTION 'HG_GROUP_ATTENDEE_REGISTERED';END IF;
  IF e.is_paid AND (a->>'tier_id') IS NULL THEN RAISE EXCEPTION 'Ticket tier required';END IF;
  r:=public.register_for_event_guest_paid(p_event,(a->>'email')::citext,a->>'name',a->>'phone',(a->>'tier_id')::uuid,p_promo,
   jsonb_build_object('registration_answers',coalesce(a->'answers','{}'::jsonb)));
  IF r ? 'error' THEN RAISE EXCEPTION '%',r->>'error';END IF;
  IF coalesce((r->>'already_registered')::boolean,false) THEN RAISE EXCEPTION 'HG_GROUP_ATTENDEE_REGISTERED';END IF;
  tid:=(r->>'ticket_id')::uuid;ids:=array_append(ids,tid);
  UPDATE public.event_tickets SET group_id=g.id WHERE id=tid;
  SELECT price_naira-discount_amount INTO amount FROM public.event_tickets WHERE id=tid;
  v_total:=v_total+amount;
  v_subtotal:=v_subtotal+(SELECT price_naira FROM public.event_tickets WHERE id=tid);
 END LOOP;
 IF p_contact ? '_expected_subtotal' AND (p_contact->>'_expected_subtotal')::numeric IS DISTINCT FROM v_subtotal THEN RAISE EXCEPTION 'HG_GROUP_PRICE_CHANGED';END IF;
 remaining:=CASE p_method WHEN 'wallet' THEN v_total WHEN 'split' THEN least(p_wallet,v_total) ELSE 0 END;
 IF p_method='split' AND (remaining<=0 OR remaining>=v_total) THEN RAISE EXCEPTION 'HG_GROUP_SPLIT_INVALID';END IF;
 UPDATE hg_internal.event_ticket_groups SET total=v_total,wallet_amount=remaining,card_amount=v_total-remaining,
   payment_status=CASE WHEN v_total=0 THEN 'not_required' WHEN v_total=remaining THEN 'paid' ELSE 'pending' END,
   payment_reference='HG-EVGRP-'||replace(id::text,'-',''),expires_at=CASE WHEN v_total>remaining THEN now()+interval '30 minutes' END WHERE id=g.id RETURNING * INTO g;
 IF remaining>0 THEN
  PERFORM public.hg_add_wallet_transaction(p_buyer,'debit',remaining,coalesce(p_contact->>'_wallet_description','event_group_payment'),'event_group',g.id,
   'internal','event-group:'||g.id,NULL,jsonb_build_object('event_id',e.id,'ticket_count',cardinality(ids)),e.campus_id);
 END IF;
 FOREACH tid IN ARRAY ids LOOP
  SELECT * INTO t FROM public.event_tickets WHERE id=tid;
  share:=least(remaining,t.price_naira-t.discount_amount);remaining:=remaining-share;
  UPDATE public.event_tickets SET wallet_amount_used=share,card_amount_used=t.price_naira-t.discount_amount-share,
   payment_method=CASE WHEN t.price_naira-t.discount_amount=0 THEN 'none' WHEN share=0 THEN 'card' WHEN share=t.price_naira-t.discount_amount THEN 'wallet' ELSE 'split' END,
   payment_status=g.payment_status,status=CASE WHEN g.payment_status='pending' THEN 'pending_payment' ELSE 'confirmed' END,
   payment_reference=CASE WHEN g.card_amount>0 THEN g.payment_reference||':'||id::text END,payment_expires_at=g.expires_at WHERE id=tid;
  IF g.payment_status IN('paid','not_required') THEN PERFORM public.hg_queue_event_ticket_email(tid);END IF;
 END LOOP;
 PERFORM hg_internal.queue_event_group_email(g.id);
 RETURN public.hg_event_group_read(g.id);
END $$;
REVOKE ALL ON FUNCTION public.hg_create_event_group(uuid,uuid,jsonb,jsonb,text,numeric,uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_create_event_group(uuid,uuid,jsonb,jsonb,text,numeric,uuid,text,text) TO service_role;

CREATE FUNCTION public.hg_event_group_authorization(p_id uuid,p_url text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,extensions AS $$
BEGIN
 UPDATE hg_internal.event_ticket_groups SET authorization_url=p_url WHERE id=p_id AND payment_status='pending';
 RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION public.hg_event_group_authorization(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_event_group_authorization(uuid,text) TO service_role;

CREATE FUNCTION public.hg_pay_event_group(p_id uuid,p_reference text,p_amount numeric,p_metadata jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,extensions AS $$
DECLARE g hg_internal.event_ticket_groups;t public.event_tickets;e uuid;cancelled boolean;
BEGIN
 SELECT event_id INTO e FROM hg_internal.event_ticket_groups WHERE id=p_id;
 SELECT metadata->>'lifecycle_status'='cancelled' INTO cancelled FROM public.events WHERE id=e FOR UPDATE;
 SELECT * INTO g FROM hg_internal.event_ticket_groups WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR p_reference IS DISTINCT FROM g.payment_reference OR p_amount IS DISTINCT FROM g.card_amount THEN RAISE EXCEPTION 'HG_GROUP_PAYMENT_MISMATCH';END IF;
 IF g.payment_status='paid' THEN RETURN public.hg_event_group_read(g.id);END IF;
 IF g.payment_status<>'pending' OR g.card_amount<=0 THEN RAISE EXCEPTION 'HG_GROUP_PAYMENT_NOT_PENDING';END IF;
 FOR t IN SELECT * FROM public.event_tickets WHERE group_id=g.id ORDER BY id LOOP
  IF t.payment_status='pending' AND t.payment_expires_at<now() THEN PERFORM public.hg_release_expired_event_reservation(t.id);SELECT * INTO t FROM public.event_tickets WHERE id=t.id;END IF;
  IF t.card_amount_used>0 THEN
   PERFORM public.hg_pay_event_with_delivery(t.id,'paystack',g.payment_reference||':'||t.id::text,t.card_amount_used,
    p_metadata||jsonb_build_object('group_id',g.id,'group_reference',g.payment_reference));
  ELSIF t.payment_status='pending' THEN
   IF coalesce(cancelled,false) THEN
    UPDATE public.event_tickets SET payment_expires_at=now()-interval '1 second' WHERE id=t.id;
    PERFORM public.hg_release_expired_event_reservation(t.id);
   ELSE
    IF t.price_naira-t.discount_amount=0 THEN
     UPDATE public.event_tickets SET payment_status='not_required',status='confirmed',payment_expires_at=NULL WHERE id=t.id;
    ELSE
     PERFORM public.hg_mark_event_ticket_paid(t.id,NULL,NULL,0,p_metadata||jsonb_build_object('group_id',g.id,'group_reference',g.payment_reference));
    END IF;
    PERFORM public.hg_queue_event_ticket_email(t.id);
   END IF;
  END IF;
 END LOOP;
 UPDATE hg_internal.event_ticket_groups SET payment_status='paid' WHERE id=g.id;
 PERFORM hg_internal.queue_event_group_email(g.id);
 RETURN public.hg_event_group_read(g.id);
END $$;
REVOKE ALL ON FUNCTION public.hg_pay_event_group(uuid,text,numeric,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_pay_event_group(uuid,text,numeric,jsonb) TO service_role;

DO $patch$
DECLARE body text; BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_release_expired_event_reservation';
 IF strpos(body,' IF t.user_id IS NULL AND')=0 THEN RAISE EXCEPTION 'Unexpected hg_release_expired_event_reservation definition';END IF;
 body:=replace(body,' IF t.user_id IS NULL AND',' IF t.group_id IS NOT NULL THEN t:=hg_internal.event_financial_ticket(t.id);END IF;
 IF t.user_id IS NULL AND');
 EXECUTE body;
END $patch$;

DO $patch$
DECLARE body text; BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_request_event_ticket_refund';
 IF strpos(body,' IF coalesce(t.wallet_amount_used,0)<0')=0 THEN RAISE EXCEPTION 'Unexpected hg_request_event_ticket_refund definition';END IF;
 body:=replace(body,' IF coalesce(t.wallet_amount_used,0)<0',' IF t.group_id IS NOT NULL THEN t:=hg_internal.event_financial_ticket(t.id);END IF;
 IF coalesce(t.wallet_amount_used,0)<0');
 EXECUTE body;
END $patch$;

DO $patch$
DECLARE body text; BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_mark_event_ticket_paid';
 IF strpos(body,'  -- Defense in depth:')=0 THEN RAISE EXCEPTION 'Unexpected hg_mark_event_ticket_paid definition';END IF;
 body:=replace(body,'  -- Defense in depth:','  IF v_ticket.group_id IS NOT NULL THEN v_ticket.user_id:=(SELECT buyer_user_id FROM hg_internal.event_ticket_groups WHERE id=v_ticket.group_id);END IF;

  -- Defense in depth:');
 EXECUTE body;
END $patch$;

DO $patch$
DECLARE body text; BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_claim_guest_event_refunds';
 IF strpos(body,'JOIN public.event_tickets et ON et.id=f.ticket_id')=0 THEN RAISE EXCEPTION 'Unexpected hg_claim_guest_event_refunds definition';END IF;
 body:=replace(body,'JOIN public.event_tickets et ON et.id=f.ticket_id','JOIN public.event_tickets et ON et.id=f.ticket_id LEFT JOIN hg_internal.event_ticket_groups purchase ON purchase.id=et.group_id');
 IF strpos(body,'lower(btrim(et.guest_email::text))=verified_email AND (et.user_id IS NULL OR et.user_id=p_actor)')=0 THEN RAISE EXCEPTION 'Unexpected hg_claim_guest_event_refunds definition';END IF;
 body:=replace(body,'lower(btrim(et.guest_email::text))=verified_email AND (et.user_id IS NULL OR et.user_id=p_actor)','lower(btrim(coalesce(purchase.buyer_email,et.guest_email::text)))=verified_email AND (CASE WHEN et.group_id IS NOT NULL THEN purchase.buyer_user_id IS NULL OR purchase.buyer_user_id=p_actor ELSE et.user_id IS NULL OR et.user_id=p_actor END)');
 IF strpos(body,'  SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE id=candidate.id FOR UPDATE;')=0 THEN RAISE EXCEPTION 'Unexpected hg_claim_guest_event_refunds definition';END IF;
 body:=replace(body,'  SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE id=candidate.id FOR UPDATE;','  IF t.group_id IS NOT NULL THEN t:=hg_internal.event_financial_ticket(t.id);END IF;
  SELECT * INTO r FROM hg_internal.event_ticket_refunds WHERE id=candidate.id FOR UPDATE;');
 IF strpos(body,'UPDATE public.event_tickets SET user_id=p_actor,is_guest=false,payment_status=''refunded'',updated_at=now() WHERE id=t.id;')=0 THEN RAISE EXCEPTION 'Unexpected hg_claim_guest_event_refunds definition';END IF;
 body:=replace(body,'UPDATE public.event_tickets SET user_id=p_actor,is_guest=false,payment_status=''refunded'',updated_at=now() WHERE id=t.id;','UPDATE public.event_tickets SET user_id=CASE WHEN group_id IS NULL THEN p_actor ELSE user_id END,is_guest=CASE WHEN group_id IS NULL THEN false ELSE is_guest END,payment_status=''refunded'',updated_at=now() WHERE id=t.id;');
 EXECUTE body;
END $patch$;

CREATE FUNCTION public.hg_event_groups_for_buyer(p_event uuid,p_actor uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,extensions AS $$
DECLARE email_address text;
BEGIN
 SELECT hg_internal.verified_event_ticket_email(p_actor) INTO email_address FROM public.profiles WHERE id=p_actor AND is_active;
 IF email_address IS NOT NULL THEN
  UPDATE hg_internal.event_ticket_groups SET buyer_user_id=p_actor WHERE buyer_user_id IS NULL AND lower(btrim(buyer_email))=email_address;
 END IF;
 RETURN coalesce((SELECT jsonb_agg(to_jsonb(row)) FROM (SELECT id,created_at,payment_status,total FROM hg_internal.event_ticket_groups WHERE buyer_user_id=p_actor AND event_id=p_event ORDER BY created_at DESC LIMIT 100) row),'[]'::jsonb);
END $$;
REVOKE ALL ON FUNCTION public.hg_event_groups_for_buyer(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_event_groups_for_buyer(uuid,uuid) TO service_role;

CREATE FUNCTION hg_internal.guard_event_group_ticket() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,extensions AS $$
BEGIN
 IF TG_OP='UPDATE' AND OLD.group_id IS NOT NULL AND NEW.group_id IS DISTINCT FROM OLD.group_id THEN RAISE EXCEPTION 'HG_GROUP_TICKET_IMMUTABLE';END IF;
 IF NEW.group_id IS NOT NULL AND (TG_OP='INSERT' OR NEW.group_id IS DISTINCT FROM OLD.group_id) THEN
  IF coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'role','')<>'service_role' THEN RAISE EXCEPTION 'HG_GROUP_ACCESS' USING ERRCODE='42501';END IF;
  IF NOT EXISTS(SELECT 1 FROM hg_internal.event_ticket_groups WHERE id=NEW.group_id AND event_id=NEW.event_id) THEN RAISE EXCEPTION 'HG_GROUP_EVENT_MISMATCH';END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.guard_event_group_ticket() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_event_group_ticket() TO service_role;
CREATE TRIGGER event_group_ticket_guard BEFORE INSERT OR UPDATE OF group_id ON public.event_tickets FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_event_group_ticket();


CREATE FUNCTION public.hg_event_group_by_intent(p_event uuid,p_key text) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT public.hg_event_group_read(id) FROM hg_internal.event_ticket_groups WHERE event_id=p_event AND idempotency_key=p_key;
$$;
REVOKE ALL ON FUNCTION public.hg_event_group_by_intent(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_event_group_by_intent(uuid,text) TO service_role;

NOTIFY pgrst, 'reload schema';
