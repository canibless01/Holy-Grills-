CREATE SCHEMA IF NOT EXISTS hg_internal;
GRANT USAGE ON SCHEMA hg_internal TO service_role;
CREATE TABLE hg_internal.wallet_transfers (
 id uuid PRIMARY KEY,
 -- Immutable party IDs preserve retry identity if an account is later removed.
 sender_id uuid NOT NULL,
 recipient_id uuid NOT NULL,
 campus_id uuid, amount_kobo bigint NOT NULL CHECK(amount_kobo BETWEEN 1 AND 100000000000),
 sender_name text NOT NULL, recipient_name text NOT NULL,
 sender_code text, recipient_code text NOT NULL,
 note text NOT NULL DEFAULT '' CHECK(length(note)<=200),
 sender_transaction_id uuid REFERENCES public.wallet_transactions(id) ON DELETE SET NULL,
 recipient_transaction_id uuid REFERENCES public.wallet_transactions(id) ON DELETE SET NULL,
 sender_balance_after numeric NOT NULL, recipient_balance_after numeric NOT NULL,
 notifications_done boolean NOT NULL DEFAULT false,
 next_notice_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(sender_id<>recipient_id)
);
ALTER TABLE hg_internal.wallet_transfers ENABLE ROW LEVEL SECURITY;
CREATE POLICY wallet_transfers_service ON hg_internal.wallet_transfers FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.wallet_transfers FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.wallet_transfers TO service_role;
CREATE INDEX wallet_transfers_sender_day ON hg_internal.wallet_transfers(sender_id,created_at);
CREATE INDEX wallet_transfers_notices ON hg_internal.wallet_transfers(next_notice_at) WHERE NOT notifications_done;
CREATE INDEX wallet_transfer_recipient_lookup ON public.profiles(campus_id,upper(referral_code)) WHERE is_active;

CREATE FUNCTION public.hg_wallet_transfer_receipt(p_actor uuid,p_id uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT jsonb_build_object('id',id,'status','completed','currency','NGN','amount',amount_kobo::numeric/100,'fee',0,
  'sender_id',sender_id,'recipient_id',recipient_id,'sender_name',sender_name,'recipient_name',recipient_name,
  'sender_code',sender_code,'recipient_code',recipient_code,'note',note,'created_at',created_at,
  'direction',CASE WHEN sender_id=p_actor THEN 'sent' ELSE 'received' END,
  'balance_after',CASE WHEN sender_id=p_actor THEN sender_balance_after ELSE recipient_balance_after END)
 FROM hg_internal.wallet_transfers WHERE id=p_id AND p_actor IN (sender_id,recipient_id)
$$;

CREATE FUNCTION public.hg_wallet_transfer_limit(p_key text,p_campus uuid,p_default numeric)
RETURNS numeric LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v text;
BEGIN
 IF p_key NOT IN ('wallet_transfer_min_amount','wallet_transfer_max_amount','wallet_transfer_daily_limit') THEN RAISE EXCEPTION 'invalid_setting'; END IF;
 SELECT value#>>'{}' INTO v FROM public.system_settings WHERE key=p_key AND (campus_id=p_campus OR campus_id IS NULL)
  ORDER BY campus_id IS NOT NULL DESC LIMIT 1;
 IF v IS NULL OR v!~'^[0-9]+([.][0-9]{1,2})?$' THEN RETURN p_default; END IF;
 RETURN CASE WHEN v::numeric BETWEEN 0.01 AND 1000000000 THEN v::numeric ELSE p_default END;
END $$;

CREATE FUNCTION public.hg_wallet_transfer(p_action text,p_actor uuid DEFAULT NULL,p_id uuid DEFAULT NULL,p_data jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE s public.profiles%rowtype;r public.profiles%rowtype;t hg_internal.wallet_transfers%rowtype;
 ids uuid[];uid uuid;amount bigint;minimum numeric;maximum numeric;daily numeric;spent numeric;available numeric;
 enabled boolean;receipt jsonb;source_balance numeric;target_balance numeric;out_id uuid;in_id uuid;
 code text;memo text;result jsonb;day_start timestamptz;
BEGIN
 IF p_action='due' THEN
  WITH due AS (
   SELECT id FROM hg_internal.wallet_transfers WHERE NOT notifications_done AND next_notice_at<=now()
   ORDER BY next_notice_at LIMIT least(greatest(coalesce((p_data->>'limit')::integer,10),0),20) FOR UPDATE SKIP LOCKED
  ), claimed AS (UPDATE hg_internal.wallet_transfers wallet_outbox SET next_notice_at=now()+interval '15 minutes' FROM due WHERE wallet_outbox.id=due.id
   RETURNING wallet_outbox.id,wallet_outbox.sender_id,wallet_outbox.recipient_id,wallet_outbox.sender_name,wallet_outbox.recipient_name,wallet_outbox.amount_kobo)
  SELECT coalesce(jsonb_agg(to_jsonb(c)||jsonb_build_object('sender_id',sender_profile.id,'recipient_id',recipient_profile.id)),'[]') INTO result
   FROM claimed c LEFT JOIN public.profiles sender_profile ON sender_profile.id=c.sender_id LEFT JOIN public.profiles recipient_profile ON recipient_profile.id=c.recipient_id;
  RETURN result;
 ELSIF p_action='notice' THEN
  SELECT jsonb_build_object('id',transfer_row.id,'sender_id',sender_profile.id,'recipient_id',recipient_profile.id,'sender_name',transfer_row.sender_name,'recipient_name',transfer_row.recipient_name,'amount_kobo',transfer_row.amount_kobo)
   INTO result FROM hg_internal.wallet_transfers transfer_row LEFT JOIN public.profiles sender_profile ON sender_profile.id=transfer_row.sender_id LEFT JOIN public.profiles recipient_profile ON recipient_profile.id=transfer_row.recipient_id
   WHERE transfer_row.id=p_id AND NOT transfer_row.notifications_done;
  RETURN result;
 ELSIF p_action='notified' THEN
  UPDATE hg_internal.wallet_transfers SET notifications_done=true WHERE id=p_id; RETURN '{}';
 END IF;
 SELECT * INTO s FROM public.profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND THEN RAISE EXCEPTION 'account_unavailable'; END IF;
 IF p_action='get' THEN
  receipt:=public.hg_wallet_transfer_receipt(p_actor,p_id);
  IF receipt IS NULL THEN RAISE EXCEPTION 'transfer_not_found'; END IF;
  RETURN receipt;
 END IF;
 IF p_action='send' THEN
  IF p_id IS NULL OR jsonb_typeof(p_data->'amount_kobo')<>'number' OR coalesce(p_data->>'amount_kobo','')!~'^[0-9]+$' THEN RAISE EXCEPTION 'invalid_transfer'; END IF;
  amount:=(p_data->>'amount_kobo')::bigint;code:=upper(btrim(p_data->>'recipient_code'));memo:=btrim(coalesce(p_data->>'note',''));
  IF amount NOT BETWEEN 1 AND 100000000000 OR length(memo)>200 OR code IS NULL OR length(code) NOT BETWEEN 3 AND 80 THEN RAISE EXCEPTION 'invalid_transfer'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('hg-wallet-transfer-intent:'||p_id::text,0));
  SELECT * INTO t FROM hg_internal.wallet_transfers WHERE id=p_id;
  IF FOUND THEN
   IF t.sender_id IS DISTINCT FROM p_actor THEN RAISE EXCEPTION 'transfer_not_found'; END IF;
   IF t.recipient_id IS DISTINCT FROM (p_data->>'recipient_id')::uuid OR t.amount_kobo<>amount OR t.note<>memo OR upper(t.recipient_code)<>code THEN RAISE EXCEPTION 'transfer_intent_conflict'; END IF;
   RETURN public.hg_wallet_transfer_receipt(p_actor,t.id)||jsonb_build_object('replayed',true);
  END IF;
 END IF;
 IF s.campus_id IS NULL THEN RAISE EXCEPTION 'campus_required'; END IF;
 SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='wallet_transfer' AND (campus_id=s.campus_id OR campus_id IS NULL)
  ORDER BY campus_id IS NOT NULL DESC LIMIT 1;
 IF p_action<>'limits' AND NOT coalesce(enabled,false) THEN RAISE EXCEPTION 'transfers_paused'; END IF;
 minimum:=public.hg_wallet_transfer_limit('wallet_transfer_min_amount',s.campus_id,1);
 maximum:=public.hg_wallet_transfer_limit('wallet_transfer_max_amount',s.campus_id,1000000);
 daily:=public.hg_wallet_transfer_limit('wallet_transfer_daily_limit',s.campus_id,1000000);
 IF minimum>maximum THEN RAISE EXCEPTION 'transfer_configuration_unavailable'; END IF;
 day_start:=date_trunc('day',now() AT TIME ZONE 'Africa/Lagos') AT TIME ZONE 'Africa/Lagos';
 IF p_action='limits' THEN
  SELECT coalesce(balance,0) INTO available FROM public.wallets WHERE user_id=s.id;
  SELECT coalesce(sum(amount_kobo),0)::numeric/100 INTO spent FROM hg_internal.wallet_transfers WHERE sender_id=s.id AND created_at>=day_start;
  RETURN jsonb_build_object('enabled',coalesce(enabled,false),'minimum_amount',minimum,'maximum_amount',maximum,
   'daily_limit',daily,'daily_remaining',greatest(0,daily-spent),'available_balance',coalesce(available,0),'fee',0,'same_campus_only',true,'my_code',s.referral_code);
 ELSIF p_action='lookup' THEN
  code:=upper(btrim(p_data->>'code'));
  IF code IS NULL OR code!~'^[A-Z0-9_-]{3,80}$' THEN RAISE EXCEPTION 'invalid_recipient_code'; END IF;
  SELECT array_agg(id) INTO ids FROM (SELECT id FROM public.profiles WHERE is_active AND campus_id=s.campus_id AND upper(referral_code)=code LIMIT 2) candidates;
  IF coalesce(cardinality(ids),0)<>1 THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
  SELECT * INTO r FROM public.profiles WHERE id=ids[1];
  IF r.id=s.id THEN RAISE EXCEPTION 'self_transfer'; END IF;
  RETURN jsonb_build_object('id',r.id,'name',left(coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus member'),100),'code',r.referral_code);
 ELSIF p_action<>'send' THEN RAISE EXCEPTION 'invalid_transfer_action'; END IF;
 uid:=(p_data->>'recipient_id')::uuid;
 IF uid IS NULL OR uid=s.id THEN RAISE EXCEPTION 'self_transfer'; END IF;
 SELECT * INTO r FROM public.profiles WHERE id=uid AND is_active AND campus_id=s.campus_id AND upper(referral_code)=code;
 IF NOT FOUND THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
 -- Same lock order for opposing transfers; coordinate wallet creation with
 -- existing card credits, then lock both wallets and profiles before movement.
 FOR uid IN SELECT unnest(ARRAY[s.id,r.id]) ORDER BY 1 LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('hg-wallet-credit:'||uid::text,0));
 END LOOP;
 INSERT INTO public.wallets(user_id,balance,currency,campus_id)
  SELECT id,0,'NGN',campus_id FROM public.profiles WHERE id IN (s.id,r.id) ORDER BY id ON CONFLICT(user_id) DO NOTHING;
 PERFORM user_id FROM public.wallets WHERE user_id IN (s.id,r.id) ORDER BY user_id FOR UPDATE;
 PERFORM id FROM public.profiles WHERE id IN (s.id,r.id) ORDER BY id FOR UPDATE;
 SELECT * INTO s FROM public.profiles WHERE id=p_actor AND is_active;
 SELECT * INTO r FROM public.profiles WHERE id=(p_data->>'recipient_id')::uuid AND is_active;
 IF s.id IS NULL OR r.id IS NULL OR s.campus_id IS NULL OR r.campus_id IS DISTINCT FROM s.campus_id OR upper(r.referral_code) IS DISTINCT FROM code THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
 SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='wallet_transfer' AND (campus_id=s.campus_id OR campus_id IS NULL)
  ORDER BY campus_id IS NOT NULL DESC LIMIT 1;
 IF NOT coalesce(enabled,false) THEN RAISE EXCEPTION 'transfers_paused'; END IF;
 SELECT balance INTO source_balance FROM public.wallets WHERE user_id=s.id AND currency='NGN';
 SELECT balance INTO target_balance FROM public.wallets WHERE user_id=r.id AND currency='NGN';
 IF source_balance IS NULL OR target_balance IS NULL OR source_balance::text IN ('NaN','Infinity','-Infinity') OR target_balance::text IN ('NaN','Infinity','-Infinity') THEN RAISE EXCEPTION 'wallet_unavailable'; END IF;
 -- Limits and spend are checked under the sender lock; concurrent sends cannot
 -- overdraw or each consume the same daily allowance.
 minimum:=public.hg_wallet_transfer_limit('wallet_transfer_min_amount',s.campus_id,1);
 maximum:=public.hg_wallet_transfer_limit('wallet_transfer_max_amount',s.campus_id,1000000);
 daily:=public.hg_wallet_transfer_limit('wallet_transfer_daily_limit',s.campus_id,1000000);
 IF minimum>maximum THEN RAISE EXCEPTION 'transfer_configuration_unavailable'; END IF;
 IF amount::numeric/100<minimum OR amount::numeric/100>maximum THEN RAISE EXCEPTION 'transfer_amount_out_of_range'; END IF;
 SELECT coalesce(sum(amount_kobo),0) INTO spent FROM hg_internal.wallet_transfers WHERE sender_id=s.id AND created_at>=day_start;
 IF spent+amount>daily*100 THEN RAISE EXCEPTION 'transfer_daily_limit'; END IF;
 IF source_balance<amount::numeric/100 THEN RAISE EXCEPTION 'insufficient_wallet_balance'; END IF;
 source_balance:=source_balance-amount::numeric/100;target_balance:=target_balance+amount::numeric/100;
 UPDATE public.wallets SET balance=source_balance,updated_at=now() WHERE user_id=s.id;
 UPDATE public.wallets SET balance=target_balance,updated_at=now() WHERE user_id=r.id;
 -- The existing wallets trigger keeps profiles.wallet_balance synchronized.
 INSERT INTO public.wallet_transactions(user_id,type,amount,balance_after,reason,reference_type,reference_id,provider,provider_reference,metadata,campus_id)
 VALUES(s.id,'debit',amount::numeric/100,source_balance,'Sent to '||left(coalesce(nullif(r.nickname,''),r.full_name,'Campus member'),100),
  'wallet_transfer',p_id,'internal','wallet-transfer:'||p_id||':out',jsonb_build_object('transfer_id',p_id,'counterparty_id',r.id),s.campus_id) RETURNING id INTO out_id;
 INSERT INTO public.wallet_transactions(user_id,type,amount,balance_after,reason,reference_type,reference_id,provider,provider_reference,metadata,campus_id)
 VALUES(r.id,'credit',amount::numeric/100,target_balance,'Received from '||left(coalesce(nullif(s.nickname,''),s.full_name,'Campus member'),100),
  'wallet_transfer',p_id,'internal','wallet-transfer:'||p_id||':in',jsonb_build_object('transfer_id',p_id,'counterparty_id',s.id),s.campus_id) RETURNING id INTO in_id;
 INSERT INTO hg_internal.wallet_transfers(id,sender_id,recipient_id,campus_id,amount_kobo,sender_name,recipient_name,sender_code,recipient_code,note,
  sender_transaction_id,recipient_transaction_id,sender_balance_after,recipient_balance_after)
 VALUES(p_id,s.id,r.id,s.campus_id,amount,left(coalesce(nullif(btrim(s.nickname),''),nullif(btrim(s.full_name),''),'Campus member'),100),
  left(coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus member'),100),s.referral_code,r.referral_code,memo,out_id,in_id,source_balance,target_balance);
 RETURN public.hg_wallet_transfer_receipt(p_actor,p_id)||jsonb_build_object('replayed',false);
END $$;

REVOKE ALL ON FUNCTION public.hg_wallet_transfer_receipt(uuid,uuid),public.hg_wallet_transfer_limit(text,uuid,numeric),public.hg_wallet_transfer(text,uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_wallet_transfer_receipt(uuid,uuid),public.hg_wallet_transfer_limit(text,uuid,numeric),public.hg_wallet_transfer(text,uuid,uuid,jsonb) TO service_role;
INSERT INTO public.system_settings(key,value,description,is_public,campus_id)
 SELECT x.key,x.value,x.description,true,NULL FROM (VALUES
 ('wallet_transfer_min_amount','1'::jsonb,'Minimum wallet transfer in naira'),
 ('wallet_transfer_max_amount','1000000'::jsonb,'Maximum wallet transfer in naira'),
 ('wallet_transfer_daily_limit','1000000'::jsonb,'Maximum outgoing wallet transfers per Nigerian calendar day in naira')) x(key,value,description)
 WHERE NOT EXISTS(SELECT 1 FROM public.system_settings s WHERE s.key=x.key AND s.campus_id IS NULL);
INSERT INTO public.feature_flags(feature_name,is_active,description,campus_id)
 SELECT 'wallet_transfer',true,'Same-campus wallet transfers with no additional fee. Existing receipts remain readable while disabled.',NULL
 WHERE NOT EXISTS(SELECT 1 FROM public.feature_flags WHERE feature_name='wallet_transfer' AND campus_id IS NULL);
