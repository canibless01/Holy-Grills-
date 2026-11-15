ALTER TABLE hg_internal.wallet_transfers ADD COLUMN gift_options jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(gift_options)='object');
CREATE OR REPLACE FUNCTION public.hg_wallet_transfer_receipt(p_actor uuid, p_id uuid)
 RETURNS jsonb
 LANGUAGE sql
 SET search_path TO 'public'
AS $function$
 SELECT jsonb_build_object('id',id,'status','completed','currency','NGN','amount',amount_kobo::numeric/100,'fee',0,
  'sender_id',CASE WHEN p_actor=recipient_id AND coalesce((gift_options->>'anonymous')::boolean,false) THEN null ELSE sender_id END,'recipient_id',recipient_id,'sender_name',CASE WHEN p_actor=recipient_id AND coalesce((gift_options->>'anonymous')::boolean,false) THEN 'Anonymous' ELSE sender_name END,'recipient_name',recipient_name,
  'sender_code',CASE WHEN p_actor=recipient_id AND coalesce((gift_options->>'anonymous')::boolean,false) THEN null ELSE sender_code END,'recipient_code',recipient_code,'note',note,'created_at',created_at,
  'anonymous',coalesce((gift_options->>'anonymous')::boolean,false),'share_contact',coalesce((gift_options->>'share_contact')::boolean,false),
  'shared_contact',CASE WHEN p_actor=recipient_id AND coalesce((gift_options->>'share_contact')::boolean,false) AND NOT coalesce((gift_options->>'anonymous')::boolean,false) THEN jsonb_build_object('phone',gift_options->>'sender_phone') ELSE null END,
  'direction',CASE WHEN sender_id=p_actor THEN 'sent' ELSE 'received' END,
  'balance_after',CASE WHEN sender_id=p_actor THEN sender_balance_after ELSE recipient_balance_after END)
 FROM hg_internal.wallet_transfers WHERE id=p_id AND p_actor IN (sender_id,recipient_id)
$function$

;
CREATE OR REPLACE FUNCTION public.hg_wallet_transfer(p_action text, p_actor uuid DEFAULT NULL::uuid, p_id uuid DEFAULT NULL::uuid, p_data jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE s public.profiles%rowtype;r public.profiles%rowtype;t hg_internal.wallet_transfers%rowtype;
 ids uuid[];uid uuid;amount bigint;minimum numeric;maximum numeric;daily numeric;spent numeric;available numeric;
 enabled boolean;receipt jsonb;source_balance numeric;target_balance numeric;out_id uuid;in_id uuid;
 code text;memo text;result jsonb;day_start timestamptz;anon boolean;share boolean;opts jsonb;
BEGIN
 IF p_action='due' THEN
  WITH due AS (
   SELECT id FROM hg_internal.wallet_transfers WHERE NOT notifications_done AND next_notice_at<=now()
   ORDER BY next_notice_at LIMIT least(greatest(coalesce((p_data->>'limit')::integer,10),0),20) FOR UPDATE SKIP LOCKED
  ), claimed AS (UPDATE hg_internal.wallet_transfers wallet_outbox SET next_notice_at=now()+interval '15 minutes' FROM due WHERE wallet_outbox.id=due.id
   RETURNING wallet_outbox.id,wallet_outbox.sender_id,wallet_outbox.recipient_id,wallet_outbox.sender_name,wallet_outbox.recipient_name,wallet_outbox.amount_kobo,wallet_outbox.gift_options)
  SELECT coalesce(jsonb_agg(to_jsonb(c)||jsonb_build_object('sender_id',sender_profile.id,'recipient_id',recipient_profile.id,'sender_name',CASE WHEN coalesce((c.gift_options->>'anonymous')::boolean,false) THEN 'Anonymous' ELSE c.sender_name END)),'[]') INTO result
   FROM claimed c LEFT JOIN public.profiles sender_profile ON sender_profile.id=c.sender_id LEFT JOIN public.profiles recipient_profile ON recipient_profile.id=c.recipient_id;
  RETURN result;
 ELSIF p_action='notice' THEN
  SELECT jsonb_build_object('id',transfer_row.id,'sender_id',sender_profile.id,'recipient_id',recipient_profile.id,'sender_name',CASE WHEN coalesce((transfer_row.gift_options->>'anonymous')::boolean,false) THEN 'Anonymous' ELSE transfer_row.sender_name END,'recipient_name',transfer_row.recipient_name,'amount_kobo',transfer_row.amount_kobo)
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
  IF (p_data ? 'anonymous' AND jsonb_typeof(p_data->'anonymous') IS DISTINCT FROM 'boolean') OR (p_data ? 'share_contact' AND jsonb_typeof(p_data->'share_contact') IS DISTINCT FROM 'boolean') THEN RAISE EXCEPTION 'invalid_transfer';END IF;
  anon:=coalesce((p_data->>'anonymous')::boolean,false);share:=coalesce((p_data->>'share_contact')::boolean,false);
  IF anon AND share THEN RAISE EXCEPTION 'invalid_transfer';END IF;
  IF p_id IS NULL OR jsonb_typeof(p_data->'amount_kobo')<>'number' OR coalesce(p_data->>'amount_kobo','')!~'^[0-9]+$' THEN RAISE EXCEPTION 'invalid_transfer'; END IF;
  amount:=(p_data->>'amount_kobo')::bigint;code:=upper(btrim(p_data->>'recipient_code'));memo:=btrim(coalesce(p_data->>'note',''));
  IF amount NOT BETWEEN 1 AND 100000000000 OR length(memo)>200 OR code IS NULL OR length(code) NOT BETWEEN 3 AND 80 THEN RAISE EXCEPTION 'invalid_transfer'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('hg-wallet-transfer-intent:'||p_id::text,0));
  SELECT * INTO t FROM hg_internal.wallet_transfers WHERE id=p_id;
  IF FOUND THEN
   IF t.sender_id IS DISTINCT FROM p_actor THEN RAISE EXCEPTION 'transfer_not_found'; END IF;
   IF t.recipient_id IS DISTINCT FROM (p_data->>'recipient_id')::uuid OR t.amount_kobo<>amount OR t.note<>memo OR upper(t.recipient_code)<>code OR coalesce((t.gift_options->>'anonymous')::boolean,false)<>anon OR coalesce((t.gift_options->>'share_contact')::boolean,false)<>share THEN RAISE EXCEPTION 'transfer_intent_conflict'; END IF;
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
  code:=btrim(coalesce(p_data->>'value',p_data->>'code'));
  IF coalesce(p_data->>'lookup_type','code')='code' THEN
   code:=upper(code);
   IF code IS NULL OR code!~'^[A-Z0-9_-]{3,80}$' THEN RAISE EXCEPTION 'invalid_recipient_code'; END IF;
  ELSIF p_data->>'lookup_type'='email' THEN
   code:=lower(code);
   IF code IS NULL OR length(code)>254 OR code!~'^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$' THEN RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  ELSIF p_data->>'lookup_type'='phone' THEN
   IF code IS NULL OR code!~'^[1-9][0-9]{7,14}$' THEN RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  ELSE RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  SELECT array_agg(id) INTO ids FROM (
   SELECT id FROM public.profiles WHERE is_active AND campus_id=s.campus_id AND (role::text='super_admin')=(s.role::text='super_admin') AND
    CASE coalesce(p_data->>'lookup_type','code')
     WHEN 'code' THEN upper(referral_code)=code
     WHEN 'email' THEN lower(btrim(email::text))=code
     WHEN 'phone' THEN (CASE WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^2340[0-9]{10}$' THEN '234'||right(regexp_replace(phone,'[+() .-]','','g'),10) WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^0[0-9]{10}$' THEN '234'||right(regexp_replace(phone,'[+() .-]','','g'),10) WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^[0-9]{10}$' THEN '234'||regexp_replace(phone,'[+() .-]','','g') ELSE regexp_replace(phone,'[+() .-]','','g') END)=code
     ELSE false END LIMIT 2) candidates;
  IF coalesce(cardinality(ids),0)=0 THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
  IF cardinality(ids)>1 THEN RAISE EXCEPTION 'recipient_ambiguous'; END IF;
  SELECT * INTO r FROM public.profiles WHERE id=ids[1];
  IF r.id=s.id THEN RAISE EXCEPTION 'self_transfer'; END IF;
  IF coalesce(r.referral_code,'')!~'^[A-Za-z0-9_-]{3,80}$' THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
  RETURN jsonb_build_object('id',r.id,'name',left(coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus member'),100),'code',r.referral_code); ELSIF p_action<>'send' THEN RAISE EXCEPTION 'invalid_transfer_action'; END IF;
 uid:=(p_data->>'recipient_id')::uuid;
 IF uid IS NULL OR uid=s.id THEN RAISE EXCEPTION 'self_transfer'; END IF;
 SELECT * INTO r FROM public.profiles WHERE id=uid AND is_active AND campus_id=s.campus_id AND upper(referral_code)=code;
 IF NOT FOUND OR (s.role::text='super_admin') IS DISTINCT FROM (r.role::text='super_admin') THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
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
 IF (s.role::text='super_admin') IS DISTINCT FROM (r.role::text='super_admin') OR s.id IS NULL OR r.id IS NULL OR s.campus_id IS NULL OR r.campus_id IS DISTINCT FROM s.campus_id OR upper(r.referral_code) IS DISTINCT FROM code THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
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
 VALUES(r.id,'credit',amount::numeric/100,target_balance,'Received from '||CASE WHEN anon THEN 'Anonymous' ELSE left(coalesce(nullif(s.nickname,''),s.full_name,'Campus member'),100) END,
  'wallet_transfer',p_id,'internal','wallet-transfer:'||p_id||':in',jsonb_build_object('transfer_id',p_id,'counterparty_id',CASE WHEN anon THEN null ELSE s.id END,'anonymous',anon),s.campus_id) RETURNING id INTO in_id;
 INSERT INTO hg_internal.wallet_transfers(id,sender_id,recipient_id,campus_id,amount_kobo,sender_name,recipient_name,sender_code,recipient_code,note,
  sender_transaction_id,recipient_transaction_id,sender_balance_after,recipient_balance_after,gift_options)
 VALUES(p_id,s.id,r.id,s.campus_id,amount,left(coalesce(nullif(btrim(s.nickname),''),nullif(btrim(s.full_name),''),'Campus member'),100),
  left(coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus member'),100),s.referral_code,r.referral_code,memo,out_id,in_id,source_balance,target_balance,jsonb_build_object('anonymous',anon,'share_contact',share,'sender_phone',CASE WHEN share THEN s.phone ELSE null END));
 RETURN public.hg_wallet_transfer_receipt(p_actor,p_id)||jsonb_build_object('replayed',false);
END $function$

;
-- A dedicated named HP transfer notice replaces the generic balance summary.
DO $$DECLARE d text;BEGIN
 d:=pg_get_functiondef('hg_internal.save_balance_activity(uuid,text,uuid,numeric,boolean,jsonb,jsonb)'::regprocedure);
 IF position('''hp_transfer_recipient'',''checkin_streak_week''' IN d)=0 THEN RAISE EXCEPTION 'Unexpected balance notice helper';END IF;
 EXECUTE replace(d,'''hp_transfer_recipient'',''checkin_streak_week''','''hp_transfer_recipient'',''hp_transfer_sent'',''checkin_streak_week''');
END$$;
CREATE FUNCTION public.hg_transfer_hp_gift(p_sender uuid,p_recipient uuid,p_amount integer,p_request uuid,p_options jsonb DEFAULT '{}') RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE s public.profiles%rowtype;r public.profiles%rowtype;debit public.hp_transactions%rowtype;credit public.hp_transactions%rowtype;result jsonb;anon boolean;share boolean;memo text;label text;opts jsonb;ch text;uid uuid;person public.profiles%rowtype;prefs public.notification_preferences%rowtype;ref uuid;kind text;body text;
BEGIN
 IF p_request IS NULL OR p_sender=p_recipient OR p_amount IS NULL OR p_amount<=0 OR jsonb_typeof(p_options) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'invalid_transfer';END IF;
 IF (p_options ? 'anonymous' AND jsonb_typeof(p_options->'anonymous') IS DISTINCT FROM 'boolean') OR (p_options ? 'share_contact' AND jsonb_typeof(p_options->'share_contact') IS DISTINCT FROM 'boolean') THEN RAISE EXCEPTION 'invalid_transfer';END IF;
 anon:=coalesce((p_options->>'anonymous')::boolean,false);share:=coalesce((p_options->>'share_contact')::boolean,false);memo:=btrim(coalesce(p_options->>'note',''));
 IF (anon AND share) OR length(memo)>200 THEN RAISE EXCEPTION 'invalid_transfer';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('hg-hp-gift:'||p_request,0));
 PERFORM id FROM public.profiles WHERE id IN(p_sender,p_recipient) ORDER BY id FOR UPDATE;
 SELECT * INTO s FROM public.profiles WHERE id=p_sender AND is_active;
 SELECT * INTO r FROM public.profiles WHERE id=p_recipient AND is_active;
 IF s.id IS NULL OR r.id IS NULL OR s.campus_id IS NULL OR s.campus_id IS DISTINCT FROM r.campus_id OR (s.role::text='super_admin')<>(r.role::text='super_admin') THEN RAISE EXCEPTION 'recipient_unavailable';END IF;
 SELECT * INTO debit FROM public.hp_transactions WHERE user_id=p_sender AND reference_type='hp_transfer' AND reference_id=p_request AND source='hp_transfer_sent';
 IF FOUND THEN
  IF debit.amount<>p_amount OR debit.metadata->>'recipient_id' IS DISTINCT FROM p_recipient::text OR debit.metadata->>'gift_note' IS DISTINCT FROM memo OR coalesce((debit.metadata->>'anonymous')::boolean,false)<>anon OR coalesce((debit.metadata->>'share_contact')::boolean,false)<>share THEN RAISE EXCEPTION 'transfer_intent_conflict';END IF;
  RETURN jsonb_build_object('success',true,'transfer_id',p_request,'replayed',true,'sender_new_balance',debit.balance_after);
 END IF;
 IF EXISTS(SELECT 1 FROM public.hp_transactions WHERE reference_type='hp_transfer' AND reference_id=p_request) THEN RAISE EXCEPTION 'transfer_not_found';END IF;
 result:=public.record_hp_transaction_atomic(p_sender,-p_amount,'spend','active','hp_transfer_sent','hp_transfer',p_request,null,memo,s.campus_id);
 IF result ? 'error' THEN RAISE EXCEPTION 'insufficient_hp';END IF;
 SELECT * INTO debit FROM public.hp_transactions WHERE user_id=p_sender AND reference_id=p_request AND source='hp_transfer_sent';
 result:=public.record_hp_transaction_atomic(p_recipient,p_amount,'earn','active','hp_transfer_received','hp_transfer',p_request,null,memo,s.campus_id);
 IF result ? 'error' THEN RAISE EXCEPTION 'transfer_credit_failed';END IF;
 SELECT * INTO credit FROM public.hp_transactions WHERE user_id=p_recipient AND reference_id=p_request AND source='hp_transfer_received';
 opts:=jsonb_build_object('gift_note',memo,'anonymous',anon,'share_contact',share,'sender_name',coalesce(nullif(btrim(s.nickname),''),nullif(btrim(s.full_name),''),'Campus friend'),'recipient_name',coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus friend'),'recipient_id',r.id);
 UPDATE public.hp_transactions SET metadata=coalesce(metadata,'{}')||opts||jsonb_build_object('sender_id',s.id) WHERE id=debit.id;
 UPDATE public.hp_transactions SET metadata=coalesce(metadata,'{}')||opts||jsonb_build_object('sender_id',CASE WHEN anon THEN null ELSE s.id END,'sender_name',CASE WHEN anon THEN 'Anonymous' ELSE coalesce(nullif(btrim(s.nickname),''),nullif(btrim(s.full_name),''),'Campus friend') END,'shared_contact',CASE WHEN share THEN jsonb_build_object('phone',s.phone) ELSE null END) WHERE id=credit.id;
 FOREACH uid IN ARRAY ARRAY[p_sender,p_recipient] LOOP
  SELECT * INTO person FROM public.profiles WHERE id=uid;SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=uid;
  IF prefs.hp_updates IS FALSE THEN CONTINUE;END IF;
  kind:=CASE WHEN uid=p_sender THEN 'hp_transfer_sent' ELSE 'hp_transfer_recipient' END;
  body:=CASE WHEN uid=p_sender THEN 'You sent '||p_amount||' HP to '||coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus friend')||'. A little love goes a long way.' ELSE CASE WHEN anon THEN 'Someone from your campus' ELSE coalesce(nullif(btrim(s.nickname),''),nullif(btrim(s.full_name),''),'Campus friend') END||' sent you '||p_amount||' HP. Open your gift to read their message'||CASE WHEN share THEN ' and say thank you.' ELSE '.' END END;
  FOREACH ch IN ARRAY ARRAY['in_app','push','email'] LOOP
   IF ch='push' AND (person.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) OR ch='email' AND (person.email_notifications IS FALSE OR prefs.email_enabled IS FALSE) THEN CONTINUE;END IF;
   ref:=extensions.uuid_generate_v5(p_request,uid||':'||ch);
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
    VALUES(ref,uid,kind,CASE WHEN uid=p_sender THEN 'Your HP gift is on its way' ELSE 'A little HP love landed' END,body,ch,'/wallet?hp_gift='||p_request,person.campus_id,p_request,jsonb_build_object('_dispatch_version',1,'reference_type','hp_transfer','reference_id',p_request)) ON CONFLICT DO NOTHING;
  END LOOP;
 END LOOP;
 RETURN jsonb_build_object('success',true,'transfer_id',p_request,'replayed',false,'sender_new_balance',debit.balance_after);
END$$;
CREATE FUNCTION public.hg_hp_gift_receipt(p_actor uuid,p_request uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT jsonb_build_object('id',reference_id,'amount',amount,'currency','HP','direction',CASE WHEN type='spend' THEN 'sent' ELSE 'received' END,'sender_name',metadata->>'sender_name','recipient_name',metadata->>'recipient_name','anonymous',coalesce((metadata->>'anonymous')::boolean,false),'share_contact',coalesce((metadata->>'share_contact')::boolean,false),'recipient_id',metadata->>'recipient_id','note',metadata->>'gift_note','shared_contact',CASE WHEN type='earn' THEN metadata->'shared_contact' ELSE null END,'created_at',created_at,'balance_after',balance_after)
 FROM public.hp_transactions WHERE user_id=p_actor AND reference_type='hp_transfer' AND reference_id=p_request AND source IN('hp_transfer_sent','hp_transfer_received') LIMIT 1
$$;
REVOKE ALL ON FUNCTION public.hg_transfer_hp_gift(uuid,uuid,integer,uuid,jsonb),public.hg_hp_gift_receipt(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_transfer_hp_gift(uuid,uuid,integer,uuid,jsonb),public.hg_hp_gift_receipt(uuid,uuid) TO service_role;
