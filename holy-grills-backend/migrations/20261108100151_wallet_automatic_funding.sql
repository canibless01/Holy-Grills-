-- Reusable authorizations never enter public wallet metadata or browser tables.
CREATE SCHEMA IF NOT EXISTS hg_internal;
GRANT USAGE ON SCHEMA hg_internal TO service_role;
CREATE TABLE hg_internal.wallet_funding_plans (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES public.profiles(id), campus_id uuid,
 amount_kobo integer NOT NULL CHECK(amount_kobo BETWEEN 10000 AND 100000000),
 interval_days integer NOT NULL CHECK(interval_days BETWEEN 1 AND 365),
 stop_after integer CHECK(stop_after BETWEEN 1 AND 3650), end_at timestamptz,
 CHECK(stop_after IS NULL OR end_at IS NULL),
 state text NOT NULL CHECK(state IN ('draft','active','attention','stopped','completed')),
 consent_version text NOT NULL, consented_at timestamptz NOT NULL DEFAULT now(),
 authorization_email text NOT NULL, card_authorization jsonb, card_label text,
 setup_reference text NOT NULL UNIQUE, checkout_url text,
 successful_payments integer NOT NULL DEFAULT 0, total_credited_kobo bigint NOT NULL DEFAULT 0,
 next_due_at timestamptz, stopped_at timestamptz, last_issue text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX wallet_funding_one_open_plan ON hg_internal.wallet_funding_plans(user_id)
 WHERE state IN ('draft','active','attention');
CREATE INDEX wallet_funding_due ON hg_internal.wallet_funding_plans(next_due_at) WHERE state='active';
CREATE INDEX wallet_funding_owner ON hg_internal.wallet_funding_plans(user_id,created_at DESC);
CREATE TABLE hg_internal.wallet_funding_attempts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), plan_id uuid NOT NULL REFERENCES hg_internal.wallet_funding_plans(id),
 cycle integer NOT NULL CHECK(cycle>0), reference text NOT NULL UNIQUE,
 state text NOT NULL CHECK(state IN ('setup','handed_off','succeeded','failed')),
 scheduled_for timestamptz NOT NULL, next_check_at timestamptz NOT NULL DEFAULT now()+interval '15 minutes',
 transaction_id uuid REFERENCES public.wallet_transactions(id), effects_done boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(plan_id,cycle)
);
CREATE INDEX wallet_funding_pending ON hg_internal.wallet_funding_attempts(next_check_at)
 WHERE state IN ('setup','handed_off') OR (state='succeeded' AND NOT effects_done);
ALTER TABLE hg_internal.wallet_funding_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE hg_internal.wallet_funding_attempts ENABLE ROW LEVEL SECURITY;
CREATE POLICY wallet_funding_plans_service ON hg_internal.wallet_funding_plans FOR ALL TO service_role USING(true) WITH CHECK(true);
CREATE POLICY wallet_funding_attempts_service ON hg_internal.wallet_funding_attempts FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.wallet_funding_plans,hg_internal.wallet_funding_attempts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.wallet_funding_plans,hg_internal.wallet_funding_attempts TO service_role;

-- Only the API service role can call this state machine. User IDs are supplied
-- by authenticated routes; provider callbacks are verified before confirm.
CREATE FUNCTION public.hg_wallet_auto_funding(p_action text,p_user_id uuid DEFAULT NULL,p_id uuid DEFAULT NULL,p_data jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE p hg_internal.wallet_funding_plans%rowtype; a hg_internal.wallet_funding_attempts%rowtype;
 u public.profiles%rowtype; result jsonb; receipt jsonb; auth jsonb; next_at timestamptz; n integer; rows jsonb;
BEGIN
 IF p_action='create' THEN
  SELECT * INTO u FROM public.profiles WHERE id=p_user_id AND is_active FOR UPDATE;
  IF NOT FOUND OR nullif(u.email::text,'') IS NULL THEN RAISE EXCEPTION 'Funding account unavailable'; END IF;
  SELECT * INTO p FROM hg_internal.wallet_funding_plans WHERE id=p_id FOR UPDATE;
  IF FOUND THEN
   IF p.user_id<>p_user_id OR p.amount_kobo<>(p_data->>'amount_kobo')::integer
    OR p.interval_days<>(p_data->>'interval_days')::integer
    OR p.stop_after IS DISTINCT FROM (p_data->>'stop_after')::integer
    OR p.end_at IS DISTINCT FROM (p_data->>'end_at')::timestamptz
    OR p.consent_version IS DISTINCT FROM p_data->>'consent_version' THEN RAISE EXCEPTION 'Funding intent conflict'; END IF;
   RETURN jsonb_build_object('created',false,'plan',to_jsonb(p));
  END IF;
  IF p_data->>'consent_version'<>'wallet-auto-funding-v1' OR p_data->>'consent_version' IS NULL
   OR ((p_data->>'end_at')::timestamptz IS NOT NULL AND (p_data->>'end_at')::timestamptz<=now()) THEN RAISE EXCEPTION 'Invalid funding consent'; END IF;
  IF EXISTS(SELECT 1 FROM hg_internal.wallet_funding_plans WHERE user_id=u.id AND state IN ('draft','active','attention')) THEN
   RAISE EXCEPTION 'Stop the existing funding plan before creating another'; END IF;
  INSERT INTO hg_internal.wallet_funding_plans(id,user_id,campus_id,amount_kobo,interval_days,stop_after,end_at,state,
    consent_version,authorization_email,setup_reference)
   VALUES(p_id,u.id,u.campus_id,(p_data->>'amount_kobo')::integer,(p_data->>'interval_days')::integer,
    (p_data->>'stop_after')::integer,(p_data->>'end_at')::timestamptz,'draft',p_data->>'consent_version',u.email::text,'HG-AUTO-'||replace(p_id::text,'-','')||'-1') RETURNING * INTO p;
  INSERT INTO hg_internal.wallet_funding_attempts(plan_id,cycle,reference,state,scheduled_for)
   VALUES(p.id,1,p.setup_reference,'setup',now());
  RETURN jsonb_build_object('created',true,'plan',to_jsonb(p));
 END IF;
 IF p_action='list' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (
   SELECT f.*,EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts t WHERE t.plan_id=f.id AND t.state='handed_off') AS in_flight
   FROM hg_internal.wallet_funding_plans f WHERE user_id=p_user_id ORDER BY created_at DESC LIMIT 5) x;
  RETURN result;
 END IF;
 IF p_action='due' THEN
  -- Expiry blocks dispatch, but paid late webhooks still credit their owner.
  UPDATE hg_internal.wallet_funding_plans SET state='completed',next_due_at=NULL,card_authorization=NULL,updated_at=now()
   WHERE state='active' AND end_at<=now();
  UPDATE hg_internal.wallet_funding_plans SET state='stopped',stopped_at=now(),updated_at=now()
   WHERE state='draft' AND created_at<now()-interval '24 hours';
  UPDATE hg_internal.wallet_funding_plans f SET state='attention',last_issue='payment_uncertain',next_due_at=NULL,updated_at=now()
   WHERE state='active' AND EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts t WHERE t.plan_id=f.id AND t.state='handed_off' AND t.created_at<now()-interval '24 hours');
  -- Reserve only reconciliation work (safe GETs/effects), not money POSTs.
  WITH due AS (
   SELECT t.id FROM hg_internal.wallet_funding_attempts t
   WHERE next_check_at<=now() AND (t.state='handed_off'
    OR (t.state='setup' AND t.created_at>now()-interval '48 hours') OR (t.state='succeeded' AND NOT t.effects_done))
   ORDER BY next_check_at LIMIT least(greatest(coalesce((p_data->>'limit')::integer,20),1),20) FOR UPDATE SKIP LOCKED
  ), claimed AS (
   UPDATE hg_internal.wallet_funding_attempts t SET next_check_at=now()+CASE WHEN t.created_at<now()-interval '24 hours' THEN interval '6 hours' ELSE interval '15 minutes' END FROM due WHERE t.id=due.id RETURNING t.*
  ) SELECT coalesce(jsonb_agg(jsonb_build_object('action',CASE WHEN c.state='succeeded' THEN 'effects' ELSE 'verify' END,
    'reference',c.reference,'attempt_id',c.id,'transaction_id',c.transaction_id,'user_id',f.user_id,'amount_kobo',f.amount_kobo,'campus_id',f.campus_id)),'[]')
   INTO result FROM claimed c JOIN hg_internal.wallet_funding_plans f ON f.id=c.plan_id;
  SELECT coalesce(jsonb_agg(jsonb_build_object('action','dispatch','id',x.id)),'[]') INTO rows FROM (
   SELECT f.id FROM hg_internal.wallet_funding_plans f WHERE state='active' AND next_due_at<=now()
   AND NOT EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts t WHERE t.plan_id=f.id AND t.state IN ('setup','handed_off'))
   ORDER BY next_due_at LIMIT greatest(0,least(coalesce((p_data->>'limit')::integer,20),20)-jsonb_array_length(result))) x;
  RETURN result||rows;
 END IF;
 IF p_action IN ('confirm','failed','effects_done') THEN
  -- Always lock plan before attempt, including stop/dispatch races.
  SELECT f.* INTO p FROM hg_internal.wallet_funding_plans f JOIN hg_internal.wallet_funding_attempts t ON t.plan_id=f.id
   WHERE t.reference=p_data->>'reference' FOR UPDATE OF f;
  IF NOT FOUND THEN RAISE EXCEPTION 'Unknown funding payment'; END IF;
  IF (p_user_id IS NOT NULL AND p_user_id<>p.user_id) OR (p_id IS NOT NULL AND p_id<>p.id) THEN RAISE EXCEPTION 'Funding access denied' USING ERRCODE='42501'; END IF;
  SELECT * INTO a FROM hg_internal.wallet_funding_attempts WHERE reference=p_data->>'reference' FOR UPDATE;
 ELSE
  SELECT * INTO p FROM hg_internal.wallet_funding_plans WHERE id=p_id AND (p_user_id IS NULL OR user_id=p_user_id) FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Funding plan not found'; END IF;
 END IF;
 IF p_action='get' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO rows FROM (
   SELECT id,cycle,reference,state,scheduled_for,updated_at FROM hg_internal.wallet_funding_attempts WHERE plan_id=p.id ORDER BY cycle DESC LIMIT 10) x;
  RETURN to_jsonb(p)||jsonb_build_object('attempts',rows,'in_flight',EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts WHERE plan_id=p.id AND state='handed_off'));
 ELSIF p_action='checkout' THEN
  IF p.state='draft' THEN
   IF p_data->>'checkout_url' !~ '^https://checkout\.paystack\.com/[A-Za-z0-9._=-]+$' THEN RAISE EXCEPTION 'Invalid checkout URL'; END IF;
   UPDATE hg_internal.wallet_funding_plans SET checkout_url=p_data->>'checkout_url',updated_at=now() WHERE id=p.id RETURNING * INTO p;
  END IF;
  RETURN to_jsonb(p);
 ELSIF p_action='setup_failed' THEN
  UPDATE hg_internal.wallet_funding_plans SET state='attention',last_issue='setup_unavailable',updated_at=now() WHERE id=p.id AND state='draft';
  RETURN '{}';
 ELSIF p_action='stop' THEN
  UPDATE hg_internal.wallet_funding_plans SET state='stopped',next_due_at=NULL,stopped_at=coalesce(stopped_at,now()),card_authorization=NULL,updated_at=now()
   WHERE id=p.id AND state NOT IN ('stopped','completed') RETURNING * INTO p;
  IF NOT FOUND THEN SELECT * INTO p FROM hg_internal.wallet_funding_plans WHERE id=p_id; END IF;
  RETURN to_jsonb(p)||jsonb_build_object('in_flight',EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts WHERE plan_id=p.id AND state='handed_off'));
 ELSIF p_action='dispatch' THEN
  IF p.state<>'active' OR p.next_due_at>now() OR p.next_due_at IS NULL OR p.end_at<=now() OR p.successful_payments>=p.stop_after THEN RETURN '{}'; END IF;
  IF EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts WHERE plan_id=p.id AND state IN ('setup','handed_off')) THEN RETURN '{}'; END IF;
  SELECT * INTO u FROM public.profiles WHERE id=p.user_id AND is_active;
  IF NOT FOUND OR u.campus_id IS DISTINCT FROM p.campus_id OR nullif(p.card_authorization->>'authorization_code','') IS NULL THEN
   UPDATE hg_internal.wallet_funding_plans SET state='attention',last_issue='account_or_card_changed',next_due_at=NULL,updated_at=now() WHERE id=p.id;
   RETURN '{}'; END IF;
  SELECT coalesce(max(cycle),0)+1 INTO n FROM hg_internal.wallet_funding_attempts WHERE plan_id=p.id;
  INSERT INTO hg_internal.wallet_funding_attempts(plan_id,cycle,reference,state,scheduled_for)
   VALUES(p.id,n,'HG-AUTO-'||replace(p.id::text,'-','')||'-'||n,'handed_off',greatest(p.next_due_at,now())) RETURNING * INTO a;
  -- Committed before the external POST. Exactly one caller receives authority.
  RETURN jsonb_build_object('reference',a.reference,'authorization_code',p.card_authorization->>'authorization_code',
    'authorization_email',p.authorization_email,'amount_kobo',p.amount_kobo);
 ELSIF p_action='failed' THEN
  IF a.state='succeeded' THEN RETURN '{}'; END IF;
  UPDATE hg_internal.wallet_funding_attempts SET state='failed',updated_at=now() WHERE id=a.id;
  UPDATE hg_internal.wallet_funding_plans SET state='attention',last_issue='payment_failed',next_due_at=NULL,updated_at=now()
   WHERE id=p.id AND state NOT IN ('stopped','completed');
  RETURN '{}';
 ELSIF p_action='effects_done' THEN
  UPDATE hg_internal.wallet_funding_attempts SET effects_done=true,updated_at=now() WHERE id=a.id AND state='succeeded'; RETURN '{}';
 ELSIF p_action='confirm' THEN
  IF p_data->>'currency'<>'NGN' OR (p_data->>'amount_kobo')::integer IS DISTINCT FROM p.amount_kobo THEN RAISE EXCEPTION 'Funding amount mismatch'; END IF;
  IF a.state<>'succeeded' THEN
   receipt:=public.credit_wallet_atomic(p.user_id,p.amount_kobo::numeric/100,'Automatic wallet funding','topup',NULL,
     'paystack',a.reference,jsonb_build_object('auto_funding_plan_id',p.id,'cycle',a.cycle,'fees_kobo',p_data->'fees_kobo'),p.campus_id);
   IF NOT coalesce((receipt->>'success')::boolean,false) THEN RAISE EXCEPTION 'Wallet credit failed'; END IF;
   UPDATE hg_internal.wallet_funding_attempts SET state='succeeded',transaction_id=(receipt->>'transaction_id')::uuid,
     next_check_at=now(),updated_at=now() WHERE id=a.id RETURNING * INTO a;
   p.successful_payments:=p.successful_payments+1;
   p.total_credited_kobo:=p.total_credited_kobo+p.amount_kobo;
   IF a.cycle=1 AND p.state='draft' THEN
    auth:=p_data->'authorization';
    IF auth->'reusable'='true'::jsonb AND auth->>'channel'='card' AND nullif(auth->>'authorization_code','') IS NOT NULL THEN
     p.card_authorization:=auth;p.card_label:=left(coalesce(auth->>'brand','Card'),30)||' •••• '||right(coalesce(auth->>'last4',''),4);p.state:='active';
    ELSE p.state:='attention';p.last_issue:='card_not_reusable'; END IF;
   END IF;
   next_at:=greatest(a.scheduled_for+make_interval(days=>p.interval_days),now()+make_interval(days=>p.interval_days));
   IF p.state NOT IN ('stopped','completed') AND (p.successful_payments>=p.stop_after OR p.end_at<=next_at) THEN p.state:='completed'; END IF;
   IF p.state<>'active' THEN next_at:=NULL; END IF;
   UPDATE hg_internal.wallet_funding_plans SET state=p.state,successful_payments=p.successful_payments,total_credited_kobo=p.total_credited_kobo,
     card_authorization=CASE WHEN p.state IN ('stopped','completed') THEN NULL ELSE p.card_authorization END,card_label=p.card_label,
     last_issue=p.last_issue,next_due_at=next_at,checkout_url=NULL,updated_at=now() WHERE id=p.id RETURNING * INTO p;
  END IF;
  RETURN jsonb_build_object('plan',to_jsonb(p),'user_id',p.user_id,'amount_kobo',p.amount_kobo,'campus_id',p.campus_id,
    'transaction_id',a.transaction_id,'attempt_id',a.id,'reference',a.reference);
 END IF;
 RAISE EXCEPTION 'Unknown funding operation';
END $$;
REVOKE ALL ON FUNCTION public.hg_wallet_auto_funding(text,uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_wallet_auto_funding(text,uuid,uuid,jsonb) TO service_role;
