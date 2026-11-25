-- A campus delivery entitlement, not another wallet or per-store tariff.
CREATE TABLE hg_internal.delivery_pass_offers(
 campus_id uuid PRIMARY KEY REFERENCES public.campuses(id),price_kobo integer NOT NULL CHECK(price_kobo BETWEEN 10000 AND 100000000),
 is_active boolean NOT NULL DEFAULT false,updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE hg_internal.delivery_pass_memberships(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid NOT NULL REFERENCES public.profiles(id),campus_id uuid NOT NULL REFERENCES public.campuses(id),
 price_kobo integer NOT NULL CHECK(price_kobo BETWEEN 10000 AND 100000000),paid_from timestamptz,paid_until timestamptz,
 auto_renew boolean NOT NULL DEFAULT false,consent_version text,consented_at timestamptz,latest_receipt_id uuid,
 renewal_issue text,issue_notified boolean NOT NULL DEFAULT true,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(user_id,campus_id),CHECK(NOT auto_renew OR (consent_version='delivery-pass-wallet-v1' AND consented_at IS NOT NULL))
);
CREATE TABLE hg_internal.delivery_pass_receipts(
 id uuid PRIMARY KEY,membership_id uuid NOT NULL REFERENCES hg_internal.delivery_pass_memberships(id),amount_kobo integer NOT NULL CHECK(amount_kobo BETWEEN 10000 AND 100000000),
 method text NOT NULL CHECK(method IN ('wallet','card')),status text NOT NULL CHECK(status IN ('pending','paid','cancelled','failed','credited','refunded')),
 reference text NOT NULL UNIQUE,checkout_url text,expires_at timestamptz NOT NULL DEFAULT now()+interval '30 minutes',
 auto_renew boolean NOT NULL DEFAULT false,period_from timestamptz,period_until timestamptz,
 wallet_transaction_id uuid REFERENCES public.wallet_transactions(id),notified_status text,notes text,is_test boolean NOT NULL DEFAULT false,
 next_check_at timestamptz NOT NULL DEFAULT now(),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE hg_internal.delivery_pass_memberships ADD CONSTRAINT delivery_pass_latest_receipt_fk FOREIGN KEY(latest_receipt_id) REFERENCES hg_internal.delivery_pass_receipts(id);
CREATE UNIQUE INDEX delivery_pass_one_pending ON hg_internal.delivery_pass_receipts(membership_id) WHERE status='pending';
CREATE INDEX delivery_pass_due ON hg_internal.delivery_pass_memberships(paid_until,id) WHERE auto_renew;
CREATE INDEX delivery_pass_reconcile ON hg_internal.delivery_pass_receipts(next_check_at,id) WHERE method='card' AND status IN ('pending','cancelled');
CREATE INDEX delivery_pass_notices ON hg_internal.delivery_pass_receipts(updated_at,id) WHERE status IN ('paid','credited','refunded') AND notified_status IS DISTINCT FROM status;
CREATE INDEX delivery_pass_campus ON hg_internal.delivery_pass_memberships(campus_id,paid_until);
DO $secure$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['delivery_pass_offers','delivery_pass_memberships','delivery_pass_receipts'] LOOP
  EXECUTE format('ALTER TABLE hg_internal.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON hg_internal.%I FROM PUBLIC,anon,authenticated',t);
  EXECUTE format('GRANT ALL ON hg_internal.%I TO service_role',t);
 END LOOP;
END$secure$;
INSERT INTO public.feature_flags(feature_name,is_active,campus_id) VALUES('delivery_pass',false,NULL) ON CONFLICT DO NOTHING;

CREATE FUNCTION hg_internal.delivery_pass_sale_enabled(p_campus uuid) RETURNS boolean
LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce((SELECT is_active FROM public.feature_flags WHERE feature_name='delivery_pass' AND (campus_id=p_campus OR campus_id IS NULL)
  ORDER BY (campus_id IS NULL) LIMIT 1),false) AND EXISTS(SELECT 1 FROM hg_internal.delivery_pass_offers WHERE campus_id=p_campus AND is_active)
$$;
CREATE FUNCTION hg_internal.delivery_pass_worker_ready() RETURNS boolean
LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM public.admin_audit_logs WHERE entity_type='cron_jobs' AND entity_id='delivery-pass-renewals'
  AND action='scheduled_execution_success' AND created_at>=now()-interval '2 hours')
$$;
REVOKE ALL ON FUNCTION hg_internal.delivery_pass_sale_enabled(uuid),hg_internal.delivery_pass_worker_ready() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.delivery_pass_sale_enabled(uuid),hg_internal.delivery_pass_worker_ready() TO service_role;

CREATE FUNCTION public.hg_delivery_pass(p_actor uuid,p_action text,p_id uuid DEFAULT NULL,p_data jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE u public.profiles%rowtype;buyer public.profiles%rowtype;o hg_internal.delivery_pass_offers%rowtype;
 m hg_internal.delivery_pass_memberships%rowtype;r hg_internal.delivery_pass_receipts%rowtype;
 c uuid;owner_id uuid;mid uuid;rows jsonb;receipt jsonb;begins timestamptz;ends timestamptz;renew boolean;amount integer;fee integer;expected integer;
BEGIN
 IF p_actor IS NULL AND p_action NOT IN ('scan','renew','checked','notice_done','issue_done','confirm','receipt') THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
 IF p_action IN ('scan','renew','checked','notice_done','issue_done') AND p_actor IS NOT NULL THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
 IF p_action='scan' THEN
  RETURN jsonb_build_object(
   'due',(SELECT coalesce(jsonb_agg(x),'[]') FROM(SELECT id FROM hg_internal.delivery_pass_memberships WHERE auto_renew AND paid_until<=now() ORDER BY paid_until,id LIMIT 50)x),
   'pending',(SELECT coalesce(jsonb_agg(x),'[]') FROM(SELECT id,reference FROM hg_internal.delivery_pass_receipts WHERE method='card' AND status IN ('pending','cancelled') AND next_check_at<=now() ORDER BY next_check_at,id LIMIT 25)x),
   'notices',(SELECT coalesce(jsonb_agg(x),'[]') FROM(SELECT pr.id FROM hg_internal.delivery_pass_receipts pr WHERE pr.status IN ('paid','credited','refunded') AND pr.notified_status IS DISTINCT FROM pr.status ORDER BY pr.updated_at,pr.id LIMIT 50)x),
   'issues',(SELECT coalesce(jsonb_agg(x),'[]') FROM(SELECT id,user_id,campus_id,paid_until,renewal_issue FROM hg_internal.delivery_pass_memberships WHERE renewal_issue IS NOT NULL AND NOT issue_notified ORDER BY updated_at,id LIMIT 50)x));
 END IF;
 IF p_action IN ('checked','notice_done') THEN
  UPDATE hg_internal.delivery_pass_receipts SET next_check_at=now()+interval '1 hour',
   status=CASE WHEN p_action='checked' AND p_data->>'terminal'='true' AND status IN ('pending','cancelled') THEN 'failed' ELSE status END,
   notified_status=CASE WHEN p_action='notice_done' AND status=p_data->>'status' THEN status ELSE notified_status END
   WHERE id=p_id;
  RETURN '{}';
 ELSIF p_action='issue_done' THEN
  UPDATE hg_internal.delivery_pass_memberships SET issue_notified=true WHERE id=p_id AND renewal_issue=p_data->>'issue' AND paid_until=(p_data->>'paid_until')::timestamptz;
  RETURN '{}';
 END IF;
 IF p_actor IS NOT NULL THEN
  SELECT * INTO u FROM public.profiles WHERE id=p_actor AND is_active;
  IF NOT FOUND THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
 END IF;
 IF p_action IN ('report','configure') THEN
  c:=(p_data->>'campus_id')::uuid;
  IF (u.role::text='super_admin' OR (u.role::text='admin' AND u.campus_id=c)) IS DISTINCT FROM true THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
  IF p_action='configure' THEN
   IF c IS NULL OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=c AND is_active) OR jsonb_typeof(p_data->'price_kobo') IS DISTINCT FROM 'number' OR jsonb_typeof(p_data->'is_active') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'pass_invalid';END IF;
   amount:=(p_data->>'price_kobo')::integer;
   IF amount NOT BETWEEN 10000 AND 100000000 THEN RAISE EXCEPTION 'pass_invalid';END IF;
   PERFORM pg_advisory_xact_lock(hashtextextended('delivery-pass-offer:'||c::text,0));
   SELECT * INTO o FROM hg_internal.delivery_pass_offers WHERE campus_id=c FOR UPDATE;
   IF FOUND THEN
    IF o.price_kobo=amount AND o.is_active=(p_data->>'is_active')::boolean THEN RETURN to_jsonb(o);END IF;
    IF o.updated_at IS DISTINCT FROM (p_data->>'expected_updated_at')::timestamptz THEN RAISE EXCEPTION 'pass_conflict';END IF;
    UPDATE hg_internal.delivery_pass_offers SET price_kobo=amount,is_active=(p_data->>'is_active')::boolean,updated_at=clock_timestamp() WHERE campus_id=c RETURNING * INTO o;
   ELSE
    IF p_data->>'expected_updated_at' IS NOT NULL THEN RAISE EXCEPTION 'pass_conflict';END IF;
    INSERT INTO hg_internal.delivery_pass_offers(campus_id,price_kobo,is_active) VALUES(c,amount,(p_data->>'is_active')::boolean) RETURNING * INTO o;
   END IF;
   INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value,campus_id)
    VALUES(p_actor,u.role::text,'delivery_pass_offers',c::text,'configure_delivery_pass',to_jsonb(o),c);
   RETURN to_jsonb(o);
  END IF;
  RETURN jsonb_build_object('offer',(SELECT to_jsonb(x) FROM hg_internal.delivery_pass_offers x WHERE campus_id=c),
   'enabled',CASE WHEN c IS NULL THEN false ELSE hg_internal.delivery_pass_sale_enabled(c) END,
   'renewals_ready',hg_internal.delivery_pass_worker_ready(),
   'active_members',(SELECT count(*) FROM hg_internal.delivery_pass_memberships WHERE (c IS NULL OR campus_id=c) AND paid_until>now() AND NOT EXISTS(SELECT 1 FROM public.profiles pp WHERE pp.id=user_id AND pp.role::text='super_admin')),
   'renewing_members',(SELECT count(*) FROM hg_internal.delivery_pass_memberships WHERE (c IS NULL OR campus_id=c) AND auto_renew AND NOT EXISTS(SELECT 1 FROM public.profiles pp WHERE pp.id=user_id AND pp.role::text='super_admin')),
   'revenue_kobo',(SELECT coalesce(sum(pr.amount_kobo),0) FROM hg_internal.delivery_pass_receipts pr JOIN hg_internal.delivery_pass_memberships pm ON pm.id=pr.membership_id WHERE (c IS NULL OR pm.campus_id=c) AND pr.status='paid' AND NOT pr.is_test),
   'refunds_kobo',(SELECT coalesce(sum(pr.amount_kobo),0) FROM hg_internal.delivery_pass_receipts pr JOIN hg_internal.delivery_pass_memberships pm ON pm.id=pr.membership_id WHERE (c IS NULL OR pm.campus_id=c) AND pr.status='refunded' AND NOT pr.is_test),
   'receipts',(SELECT coalesce(jsonb_agg(x),'[]') FROM(SELECT pr.id,pr.amount_kobo,pr.method,pr.status,pr.created_at,pr.period_until,pr.is_test,pm.campus_id,pm.user_id,pp.full_name
    FROM hg_internal.delivery_pass_receipts pr JOIN hg_internal.delivery_pass_memberships pm ON pm.id=pr.membership_id JOIN public.profiles pp ON pp.id=pm.user_id
    WHERE c IS NULL OR pm.campus_id=c ORDER BY pr.created_at DESC,pr.id LIMIT 50)x));
 ELSIF p_action IN ('status','benefit') THEN
  IF p_actor IS NULL THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
  c:=u.campus_id;
  IF p_data->>'campus_id' IS NOT NULL AND (p_data->>'campus_id')::uuid IS DISTINCT FROM c THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
  SELECT * INTO m FROM hg_internal.delivery_pass_memberships WHERE user_id=p_actor AND campus_id=c;
  IF p_action='benefit' THEN RETURN CASE WHEN m.paid_until>now() THEN jsonb_build_object('id',m.id,'paid_until',m.paid_until,'campus_id',m.campus_id) ELSE '{}'::jsonb END;END IF;
  RETURN jsonb_build_object('campus_id',c,'campus_name',(SELECT name FROM campuses WHERE id=c),
   'available',hg_internal.delivery_pass_sale_enabled(c),'renewals_ready',hg_internal.delivery_pass_worker_ready() AND hg_internal.delivery_pass_sale_enabled(c),
   'offer',(SELECT to_jsonb(x) FROM hg_internal.delivery_pass_offers x WHERE campus_id=c AND is_active),
   'membership',CASE WHEN m.id IS NOT NULL THEN to_jsonb(m)||jsonb_build_object('active',m.paid_until>now()) END,
   'pending',(SELECT to_jsonb(x) FROM hg_internal.delivery_pass_receipts x WHERE x.membership_id=m.id AND x.status='pending' ORDER BY created_at DESC LIMIT 1),
   'history',(SELECT coalesce(jsonb_agg(x),'[]') FROM(SELECT pr.id,pr.amount_kobo,pr.method,pr.status,pr.period_until,pr.created_at FROM hg_internal.delivery_pass_receipts pr JOIN hg_internal.delivery_pass_memberships m2 ON m2.id=pr.membership_id WHERE m2.user_id=p_actor ORDER BY pr.created_at DESC,pr.id LIMIT 10)x));
 END IF;
 IF p_action IN ('receipt','confirm','checkout','cancel','refund') THEN
  SELECT r0.* INTO r FROM hg_internal.delivery_pass_receipts r0 JOIN hg_internal.delivery_pass_memberships m0 ON m0.id=r0.membership_id WHERE r0.id=p_id;
  -- Owner is selected separately to keep the receipt's stable row type.
  SELECT m0.user_id,m0.id INTO owner_id,mid FROM hg_internal.delivery_pass_receipts r0 JOIN hg_internal.delivery_pass_memberships m0 ON m0.id=r0.membership_id WHERE r0.id=p_id;
  IF owner_id IS NULL THEN RAISE EXCEPTION 'pass_not_found';END IF;
  IF p_action<>'refund' AND p_actor IS NOT NULL AND p_actor<>owner_id THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
  IF p_action='receipt' THEN RETURN to_jsonb(r)||jsonb_build_object('user_id',owner_id,'campus_id',(SELECT campus_id FROM hg_internal.delivery_pass_memberships WHERE id=mid));END IF;
 ELSIF p_action='renew' THEN
  SELECT user_id,id INTO owner_id,mid FROM hg_internal.delivery_pass_memberships WHERE id=p_id;
  IF owner_id IS NULL THEN RETURN '{}';END IF;
 ELSE owner_id:=p_actor;END IF;
 IF owner_id IS NULL THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
 -- Every financial path and order admission shares wallet -> profile -> membership.
 PERFORM 1 FROM public.wallets WHERE user_id=owner_id FOR UPDATE;
 SELECT * INTO buyer FROM public.profiles WHERE id=owner_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
 IF mid IS NOT NULL THEN SELECT * INTO m FROM hg_internal.delivery_pass_memberships WHERE id=mid FOR UPDATE;
 ELSE SELECT * INTO m FROM hg_internal.delivery_pass_memberships WHERE user_id=owner_id AND campus_id=buyer.campus_id FOR UPDATE;END IF;
 IF p_action IN ('checkout','cancel','refund','confirm') THEN
  SELECT * INTO r FROM hg_internal.delivery_pass_receipts WHERE id=p_id FOR UPDATE;
  IF p_action='checkout' THEN
   IF r.status='pending' THEN
    IF p_data->>'url' NOT LIKE 'https://checkout.paystack.com/%' THEN RAISE EXCEPTION 'pass_invalid';END IF;
    UPDATE hg_internal.delivery_pass_receipts SET checkout_url=p_data->>'url',updated_at=now() WHERE id=r.id RETURNING * INTO r;
   END IF;
   RETURN to_jsonb(r);
  ELSIF p_action='cancel' THEN
   UPDATE hg_internal.delivery_pass_receipts SET status='cancelled',checkout_url=NULL,updated_at=now() WHERE id=r.id AND status='pending' RETURNING * INTO r;
   IF NOT FOUND THEN SELECT * INTO r FROM hg_internal.delivery_pass_receipts WHERE id=p_id;END IF;
   RETURN to_jsonb(r);
  ELSIF p_action='refund' THEN
   IF (u.role::text='super_admin' OR (u.role::text='admin' AND u.campus_id=m.campus_id)) IS DISTINCT FROM true THEN RAISE EXCEPTION 'pass_denied' USING ERRCODE='42501';END IF;
   IF r.status='refunded' THEN RETURN to_jsonb(r)||'{"replayed":true}';END IF;
   IF r.status<>'paid' OR length(btrim(coalesce(p_data->>'reason',''))) NOT BETWEEN 1 AND 1000 THEN RAISE EXCEPTION 'pass_invalid';END IF;
   receipt:=public.credit_wallet_atomic(owner_id,r.amount_kobo::numeric/100,p_data->>'ledger_reason','delivery_pass_refund',r.id,'internal-refund','HG-PASS-REFUND-'||r.id::text,jsonb_build_object('reason',p_data->>'reason'),m.campus_id);
   IF NOT coalesce((receipt->>'success')::boolean,false) THEN RAISE EXCEPTION 'pass_wallet_failed';END IF;
   UPDATE hg_internal.delivery_pass_receipts SET status='refunded',notes=p_data->>'reason',wallet_transaction_id=(receipt->>'transaction_id')::uuid,updated_at=now() WHERE id=r.id RETURNING * INTO r;
   IF m.latest_receipt_id=r.id THEN UPDATE hg_internal.delivery_pass_memberships SET paid_until=least(paid_until,now()),auto_renew=false,renewal_issue=NULL,updated_at=now() WHERE id=m.id;END IF;
   INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value,campus_id)
    VALUES(p_actor,u.role::text,'delivery_pass_receipts',r.id::text,'refund_delivery_pass',jsonb_build_object('amount_kobo',r.amount_kobo,'reason',p_data->>'reason','user_id',owner_id),m.campus_id);
   RETURN to_jsonb(r)||jsonb_build_object('user_id',owner_id,'campus_id',m.campus_id);
  END IF;
  amount:=(p_data->>'amount_kobo')::integer;fee:=(p_data->>'fees_kobo')::integer;expected:=(p_data->>'requested_amount_kobo')::integer;
  IF p_data->>'reference' IS DISTINCT FROM r.reference OR p_data->>'currency' IS DISTINCT FROM 'NGN' OR amount IS NULL OR amount<r.amount_kobo OR fee<0
   OR (expected IS NOT NULL AND expected<>r.amount_kobo)
   OR NOT(amount=r.amount_kobo OR (fee IS NOT NULL AND amount-fee=r.amount_kobo) OR (fee IS NULL AND amount<=r.amount_kobo+greatest(15000,floor(r.amount_kobo*0.02)::integer))) THEN RAISE EXCEPTION 'pass_payment_mismatch';END IF;
  IF r.method<>'card' THEN RAISE EXCEPTION 'pass_payment_mismatch';END IF;
  IF r.status IN ('paid','credited','refunded') THEN RETURN to_jsonb(r)||jsonb_build_object('user_id',owner_id,'campus_id',m.campus_id,'replayed',true);END IF;
  IF r.status<>'pending' OR r.expires_at<=now() OR m.paid_until>now() OR NOT buyer.is_active OR buyer.campus_id IS DISTINCT FROM m.campus_id THEN
   receipt:=public.credit_wallet_atomic(owner_id,r.amount_kobo::numeric/100,p_data->>'ledger_reason','delivery_pass_recovery',r.id,'paystack',r.reference,'{}',m.campus_id);
   IF NOT coalesce((receipt->>'success')::boolean,false) THEN RAISE EXCEPTION 'pass_wallet_failed';END IF;
   UPDATE hg_internal.delivery_pass_receipts SET status='credited',checkout_url=NULL,wallet_transaction_id=(receipt->>'transaction_id')::uuid,updated_at=now() WHERE id=r.id RETURNING * INTO r;
   RETURN to_jsonb(r)||jsonb_build_object('user_id',owner_id,'campus_id',m.campus_id);
  END IF;
  renew:=r.auto_renew;begins:=now();ends:=begins+interval '1 month';
 ELSIF p_action='renewal' THEN
  IF m.id IS NULL OR jsonb_typeof(p_data->'enabled') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'pass_invalid';END IF;
  renew:=(p_data->>'enabled')::boolean;
  IF renew AND (m.paid_until IS NULL OR m.paid_until<=now() OR NOT hg_internal.delivery_pass_sale_enabled(m.campus_id) OR NOT hg_internal.delivery_pass_worker_ready()
    OR p_data->>'consent_version' IS DISTINCT FROM 'delivery-pass-wallet-v1' OR (p_data->>'price_kobo')::integer IS DISTINCT FROM m.price_kobo) THEN RAISE EXCEPTION 'pass_renewal_unavailable';END IF;
  UPDATE hg_internal.delivery_pass_memberships SET auto_renew=renew,consent_version=CASE WHEN renew THEN 'delivery-pass-wallet-v1' ELSE consent_version END,
   consented_at=CASE WHEN renew THEN now() ELSE consented_at END,updated_at=now() WHERE id=m.id RETURNING * INTO m;
  RETURN to_jsonb(m);
 ELSIF p_action IN ('buy','renew') THEN
  IF p_action='buy' THEN
   IF p_id IS NULL OR coalesce(p_data->>'method','') NOT IN ('wallet','card') OR jsonb_typeof(p_data->'auto_renew') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'pass_invalid';END IF;
   SELECT * INTO r FROM hg_internal.delivery_pass_receipts WHERE id=p_id;
   IF FOUND THEN
    IF r.membership_id IS DISTINCT FROM m.id OR r.method IS DISTINCT FROM p_data->>'method' OR r.amount_kobo IS DISTINCT FROM (p_data->>'price_kobo')::integer OR r.auto_renew IS DISTINCT FROM (p_data->>'auto_renew')::boolean THEN RAISE EXCEPTION 'pass_conflict';END IF;
    RETURN to_jsonb(r)||'{"replayed":true}';
   END IF;
   IF NOT buyer.is_active OR buyer.campus_id IS NULL OR NOT hg_internal.delivery_pass_sale_enabled(buyer.campus_id) THEN RAISE EXCEPTION 'pass_unavailable';END IF;
   SELECT * INTO o FROM hg_internal.delivery_pass_offers WHERE campus_id=buyer.campus_id FOR SHARE;
   IF o.price_kobo IS DISTINCT FROM (p_data->>'price_kobo')::integer THEN RAISE EXCEPTION 'pass_price_changed';END IF;
   IF m.paid_until>now() THEN RAISE EXCEPTION 'pass_already_active';END IF;
   renew:=(p_data->>'auto_renew')::boolean;
   IF renew AND (NOT hg_internal.delivery_pass_worker_ready() OR p_data->>'consent_version' IS DISTINCT FROM 'delivery-pass-wallet-v1') THEN RAISE EXCEPTION 'pass_renewal_unavailable';END IF;
   IF m.id IS NULL THEN
    INSERT INTO hg_internal.delivery_pass_memberships(user_id,campus_id,price_kobo) VALUES(owner_id,buyer.campus_id,o.price_kobo) RETURNING * INTO m;
   END IF;
   UPDATE hg_internal.delivery_pass_receipts SET status='cancelled',checkout_url=NULL,updated_at=now() WHERE membership_id=m.id AND status='pending' AND expires_at<=now();
   IF EXISTS(SELECT 1 FROM hg_internal.delivery_pass_receipts WHERE membership_id=m.id AND status='pending') THEN RAISE EXCEPTION 'pass_payment_pending';END IF;
   INSERT INTO hg_internal.delivery_pass_receipts(id,membership_id,amount_kobo,method,status,reference,auto_renew,is_test)
    VALUES(p_id,m.id,o.price_kobo,p_data->>'method','pending','HG-PASS-'||p_id::text,renew,buyer.role::text='super_admin') RETURNING * INTO r;
   IF r.method='card' THEN RETURN to_jsonb(r)||jsonb_build_object('created',true,'authorization_email',buyer.email);END IF;
  ELSE
   IF m.id IS NULL OR NOT m.auto_renew OR m.paid_until>now() THEN RETURN '{}';END IF;
   IF NOT buyer.is_active OR buyer.campus_id IS DISTINCT FROM m.campus_id OR m.paid_until<now()-interval '48 hours' THEN
    UPDATE hg_internal.delivery_pass_memberships SET auto_renew=false,renewal_issue='renew_manually',issue_notified=false,updated_at=now() WHERE id=m.id;RETURN '{}';END IF;
   IF NOT hg_internal.delivery_pass_sale_enabled(m.campus_id) THEN RETURN '{}';END IF;
   IF EXISTS(SELECT 1 FROM hg_internal.delivery_pass_receipts WHERE membership_id=m.id AND status='pending') THEN RETURN '{}';END IF;
   renew:=true;
   INSERT INTO hg_internal.delivery_pass_receipts(id,membership_id,amount_kobo,method,status,reference,auto_renew,is_test)
    VALUES(md5('renew:'||m.id::text||':'||m.latest_receipt_id::text)::uuid,m.id,m.price_kobo,'wallet','pending','HG-PASS-RENEW-'||m.latest_receipt_id::text,true,buyer.role::text='super_admin') RETURNING * INTO r;
  END IF;
  IF coalesce((SELECT balance FROM public.wallets WHERE user_id=owner_id),0)<r.amount_kobo::numeric/100 THEN
   IF p_action='buy' THEN RAISE EXCEPTION 'pass_wallet_insufficient';END IF;
   UPDATE hg_internal.delivery_pass_receipts SET status='failed',updated_at=now() WHERE id=r.id;
   UPDATE hg_internal.delivery_pass_memberships SET auto_renew=false,renewal_issue='needs_funding',issue_notified=false,updated_at=now() WHERE id=m.id;
   RETURN '{}';
  END IF;
  receipt:=public.debit_wallet_atomic(owner_id,r.amount_kobo::numeric/100,p_data->>'ledger_reason','delivery_pass',r.id,'{}',m.campus_id);
  IF NOT coalesce((receipt->>'success')::boolean,false) THEN RAISE EXCEPTION 'pass_wallet_failed';END IF;
  r.wallet_transaction_id:=(receipt->>'transaction_id')::uuid;begins:=now();ends:=begins+interval '1 month';
 ELSE RAISE EXCEPTION 'pass_invalid';END IF;
 UPDATE hg_internal.delivery_pass_receipts SET status='paid',checkout_url=NULL,period_from=begins,period_until=ends,wallet_transaction_id=r.wallet_transaction_id,updated_at=now() WHERE id=r.id RETURNING * INTO r;
 UPDATE hg_internal.delivery_pass_memberships SET paid_from=begins,paid_until=ends,price_kobo=r.amount_kobo,auto_renew=renew,
  consent_version=CASE WHEN renew THEN 'delivery-pass-wallet-v1' ELSE consent_version END,consented_at=CASE WHEN renew THEN now() ELSE consented_at END,
  latest_receipt_id=r.id,renewal_issue=NULL,issue_notified=true,updated_at=now() WHERE id=m.id;
 RETURN to_jsonb(r)||jsonb_build_object('user_id',owner_id,'campus_id',m.campus_id);
END$$;
REVOKE ALL ON FUNCTION public.hg_delivery_pass(uuid,text,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_delivery_pass(uuid,text,uuid,jsonb) TO service_role;

-- Preserve the original order helper signature, financial checks and grants.
DO $benefit$
DECLARE body text;needle text:=$old$        IF v_benefit_source='monthly' THEN
            IF p_is_squad_order$old$;replacement text:=$new$        IF v_benefit_source='delivery_pass' THEN
            PERFORM 1 FROM hg_internal.delivery_pass_memberships WHERE id=(v_benefit->>'subscription_id')::uuid
              AND user_id=p_user_id AND campus_id=p_campus_id AND paid_until>now() FOR SHARE;
            IF NOT FOUND THEN RAISE EXCEPTION 'delivery_benefit_changed';END IF;
            v_benefit_cap:=v_benefit_fee;
        ELSIF v_benefit_source='monthly' THEN
            IF p_is_squad_order$new$;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_create_order_atomic';
 IF body IS NULL OR strpos(body,needle)=0 THEN RAISE EXCEPTION 'Order benefit source changed';END IF;
 EXECUTE replace(body,needle,replacement);
END$benefit$;
