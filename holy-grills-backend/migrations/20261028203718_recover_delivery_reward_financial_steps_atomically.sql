-- Reuse existing order logs as durable receipts; no new table or column.
CREATE OR REPLACE FUNCTION public.unlock_pending_hp_fifo_atomic(p_user_id uuid,p_order_id uuid,p_amount_to_unlock integer,p_campus_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_order public.orders%ROWTYPE; v_balance integer; v_remaining integer; v_unlocked integer:=0; v_old jsonb; r record;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'unlock_forbidden' USING ERRCODE='42501'; END IF;
 SELECT * INTO v_order FROM public.orders WHERE id=p_order_id FOR UPDATE;
 IF NOT FOUND OR v_order.user_id IS DISTINCT FROM p_user_id OR p_user_id IS NULL OR v_order.status::text<>'delivered' THEN RETURN jsonb_build_object('error','paid_delivery_required'); END IF;
 IF p_amount_to_unlock IS NULL OR p_amount_to_unlock<0 THEN RETURN jsonb_build_object('error','invalid_unlock_amount'); END IF;
 SELECT metadata->'pending_hp_unlock' INTO v_old FROM public.order_status_logs WHERE order_id=p_order_id AND metadata ? 'pending_hp_unlock' ORDER BY created_at,id LIMIT 1;
 IF v_old IS NOT NULL THEN RETURN jsonb_build_object('success',true,'replayed',true,'unlocked_amount',(v_old->>'unlocked_amount')::integer); END IF;
 -- Old partial-split receipts are identifiable; old whole-row unlocks are not.
 IF EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=p_user_id AND source='unlock' AND reference_type='order' AND reference_id=p_order_id) THEN RETURN jsonb_build_object('error','legacy_unlock_review_required'); END IF;
 SELECT hp_balance INTO v_balance FROM public.profiles WHERE id=p_user_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','user_not_found'); END IF;
 v_remaining:=p_amount_to_unlock;
 FOR r IN SELECT id,amount FROM public.hp_transactions WHERE user_id=p_user_id AND status='pending' AND (expires_at IS NULL OR expires_at>now()) ORDER BY created_at,id FOR UPDATE LOOP
  EXIT WHEN v_remaining<=0;
  IF r.amount<=v_remaining THEN
   UPDATE public.hp_transactions SET status='active',balance_after=v_balance+v_unlocked+r.amount WHERE id=r.id;
   v_unlocked:=v_unlocked+r.amount;v_remaining:=v_remaining-r.amount;
  ELSE
   UPDATE public.hp_transactions SET amount=amount-v_remaining,remaining_amount=least(remaining_amount,amount-v_remaining) WHERE id=r.id;
   INSERT INTO public.hp_transactions(user_id,amount,type,status,balance_after,source,reference_type,reference_id,metadata,campus_id)
   VALUES(p_user_id,v_remaining,'earn','active',v_balance+v_unlocked+v_remaining,'unlock','order_pending_unlock',p_order_id,'{}'::jsonb,v_order.campus_id);
   v_unlocked:=v_unlocked+v_remaining;v_remaining:=0;
  END IF;
 END LOOP;
 IF v_unlocked>0 THEN
  UPDATE public.profiles SET hp_balance=v_balance+v_unlocked WHERE id=p_user_id;
 END IF;
 INSERT INTO public.order_status_logs(order_id,status,campus_id,metadata)
 VALUES(p_order_id,'delivered',v_order.campus_id,jsonb_build_object('pending_hp_unlock',jsonb_build_object('requested',p_amount_to_unlock,'unlocked_amount',v_unlocked)));
 RETURN jsonb_build_object('success',true,'unlocked_amount',v_unlocked,'new_balance',v_balance+v_unlocked);
END $function$;
REVOKE ALL ON FUNCTION public.unlock_pending_hp_fifo_atomic(uuid,uuid,integer,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.unlock_pending_hp_fifo_atomic(uuid,uuid,integer,uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_complete_delivery_rewards_atomic(p_order_id uuid,p_plan jsonb,p_notes jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_order public.orders%ROWTYPE; v_receipt public.order_status_logs%ROWTYPE; v_state jsonb; v_plan jsonb; v_result jsonb;
 v_member jsonb; v_hp integer; v_bonus integer; v_welcome integer:=0; v_unlocked integer:=0; v_sum integer:=0; v_month text:=to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM');
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'delivery_rewards_forbidden' USING ERRCODE='42501'; END IF;
 SELECT * INTO v_order FROM public.orders WHERE id=p_order_id FOR UPDATE;
 IF NOT FOUND OR v_order.user_id IS NULL OR v_order.status::text<>'delivered' OR v_order.hp_credited_at IS NULL THEN RETURN jsonb_build_object('error','delivery_award_required'); END IF;
 SELECT * INTO v_receipt FROM public.order_status_logs WHERE order_id=p_order_id AND metadata ? 'delivery_reward_recovery' ORDER BY created_at,id LIMIT 1 FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','legacy_delivery_reward_review_required'); END IF;
 v_state:=v_receipt.metadata->'delivery_reward_recovery';
 IF coalesce((v_state->>'financial_complete')::boolean,false) THEN RETURN (v_state->'result')||jsonb_build_object('success',true,'replayed',true); END IF;
 v_plan:=coalesce(v_state->'plan',p_plan);
 IF jsonb_typeof(v_plan) IS DISTINCT FROM 'object' OR jsonb_typeof(v_plan->'members') IS DISTINCT FROM 'array'
 OR NOT (v_plan ?& ARRAY['unlock_amount','welcome_amount','squad_bonus']) OR (v_plan->>'unlock_amount') IS NULL OR (v_plan->>'welcome_amount') IS NULL OR (v_plan->>'squad_bonus') IS NULL
 OR (v_plan->>'unlock_amount')::integer<0 OR (v_plan->>'welcome_amount')::integer<0 OR (v_plan->>'squad_bonus')::integer<0 THEN RETURN jsonb_build_object('error','invalid_delivery_reward_plan'); END IF;
 FOR v_member IN SELECT value FROM jsonb_array_elements(v_plan->'members') LOOP
  v_hp:=(v_member->>'hp')::integer;
  IF v_hp IS NULL OR v_hp<0 OR ((v_member->>'user_id') IS NULL AND coalesce(v_member->>'email','')='') OR v_member->>'user_id'=v_order.user_id::text THEN RETURN jsonb_build_object('error','invalid_squad_recipient'); END IF;
  v_sum:=v_sum+v_hp;
 END LOOP;
 IF v_sum+(v_state->>'owner_hp')::integer<>(v_state->>'total_hp')::integer THEN RETURN jsonb_build_object('error','delivery_reward_plan_changed'); END IF;
 -- Save terms even when the following financial subtransaction fails.
 v_state:=v_state||jsonb_build_object('plan',v_plan,'attempted_at',now());
 UPDATE public.order_status_logs SET metadata=jsonb_set(metadata,'{delivery_reward_recovery}',v_state) WHERE id=v_receipt.id;
 BEGIN
  -- Stable profile lock ordering across squad grants and HP transfers.
  PERFORM id FROM public.profiles WHERE id=v_order.user_id OR id IN (SELECT (value->>'user_id')::uuid FROM jsonb_array_elements(v_plan->'members') WHERE value->>'user_id' IS NOT NULL) ORDER BY id FOR UPDATE;
  v_result:=public.unlock_pending_hp_fifo_atomic(v_order.user_id,p_order_id,(v_plan->>'unlock_amount')::integer,v_order.campus_id);
  IF v_result ? 'error' THEN RAISE EXCEPTION '%',v_result->>'error'; END IF;
  v_unlocked:=(v_result->>'unlocked_amount')::integer;
  IF NOT EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=v_order.user_id AND source='welcome' AND type='earn') THEN
   v_welcome:=(v_plan->>'welcome_amount')::integer;
   IF v_welcome>0 THEN
    v_result:=public.record_hp_transaction_atomic(v_order.user_id,v_welcome,'earn','active','welcome','welcome_bonus',p_order_id,NULL,p_notes->>'welcome',v_order.campus_id);
    IF v_result ? 'error' THEN RAISE EXCEPTION '%',v_result->>'error'; END IF;
    IF NOT coalesce((v_result->>'replayed')::boolean,false) THEN PERFORM public.increment_monthly_hp_tracker(v_order.user_id,v_month,v_welcome); END IF;
   END IF;
  END IF;
  FOR v_member IN SELECT value FROM jsonb_array_elements(v_plan->'members') LOOP
   v_hp:=(v_member->>'hp')::integer;
   IF v_hp=0 THEN CONTINUE; END IF;
   IF v_member->>'user_id' IS NOT NULL THEN
    IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=(v_member->>'user_id')::uuid AND is_active AND campus_id IS NOT DISTINCT FROM v_order.campus_id) THEN RAISE EXCEPTION 'squad_recipient_unavailable'; END IF;
    v_result:=public.record_hp_transaction_atomic((v_member->>'user_id')::uuid,v_hp,'earn','active','squad_split','squad_split',p_order_id,NULL,p_notes->>'squad_split',v_order.campus_id);
    IF v_result ? 'error' THEN RAISE EXCEPTION '%',v_result->>'error'; END IF;
    IF NOT coalesce((v_result->>'replayed')::boolean,false) THEN PERFORM public.increment_monthly_hp_tracker((v_member->>'user_id')::uuid,v_month,v_hp); END IF;
   ELSE
    IF EXISTS(SELECT 1 FROM public.pending_squad_hp WHERE order_id=p_order_id AND lower(email)=lower(v_member->>'email') AND hp_amount<>v_hp) THEN RAISE EXCEPTION 'pending_squad_amount_mismatch'; END IF;
    IF NOT EXISTS(SELECT 1 FROM public.pending_squad_hp WHERE order_id=p_order_id AND lower(email)=lower(v_member->>'email')) THEN
     INSERT INTO public.pending_squad_hp(email,order_id,hp_amount,campus_id,status) VALUES(lower(v_member->>'email'),p_order_id,v_hp,v_order.campus_id,'pending');
    END IF;
   END IF;
  END LOOP;
  v_bonus:=(v_plan->>'squad_bonus')::integer;
  IF v_bonus>0 THEN
   v_result:=public.record_hp_transaction_atomic(v_order.user_id,v_bonus,'earn','active','squad_bonus','squad_bonus',p_order_id,NULL,p_notes->>'squad_bonus',v_order.campus_id);
   IF v_result ? 'error' THEN RAISE EXCEPTION '%',v_result->>'error'; END IF;
   IF NOT coalesce((v_result->>'replayed')::boolean,false) THEN PERFORM public.increment_monthly_hp_tracker(v_order.user_id,v_month,v_bonus); END IF;
  END IF;
  UPDATE public.squad_members sm SET hp_share=(m.value->>'hp')::integer FROM jsonb_array_elements(v_plan->'members') m WHERE sm.order_id=p_order_id AND lower(sm.email)=lower(m.value->>'email');
  UPDATE public.orders SET squad_hp_distributed=true,squad_hp_distributed_at=now() WHERE id=p_order_id;
  v_result:=jsonb_build_object('success',true,'unlocked_hp',v_unlocked,'welcome_hp',v_welcome,'squad_bonus',v_bonus,'owner_hp',(v_state->>'owner_hp')::integer,'total_hp',(v_state->>'total_hp')::integer);
  v_state:=v_state||jsonb_build_object('financial_complete',true,'result',v_result,'completed_at',now());
  UPDATE public.order_status_logs SET metadata=jsonb_set(metadata,'{delivery_reward_recovery}',v_state) WHERE id=v_receipt.id;
  RETURN v_result;
 EXCEPTION WHEN OTHERS THEN
  UPDATE public.order_status_logs SET metadata=jsonb_set(metadata,'{delivery_reward_recovery}',v_state||jsonb_build_object('last_error',SQLERRM)) WHERE id=v_receipt.id;
  RETURN jsonb_build_object('error','delivery_reward_financial_pending');
 END;
END $function$;
REVOKE ALL ON FUNCTION public.hg_complete_delivery_rewards_atomic(uuid,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_complete_delivery_rewards_atomic(uuid,jsonb,jsonb) TO service_role;

-- Same seven-argument primary helper: its ledger and recovery marker commit together.
DO $patch$
DECLARE definition text; anchor text:=E'  RETURN jsonb_build_object(\'success\',true,\'order_id\',p_order_id,\'hp_earned\',v_total_hp,';
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_credit_delivery_hp_atomic' AND p.pronargs=7;
 IF definition IS NULL OR strpos(definition,anchor)=0 THEN RAISE EXCEPTION 'primary_delivery_signature_changed'; END IF;
 IF strpos(definition,'delivery_reward_recovery')=0 THEN
  definition:=replace(definition,anchor,E'  INSERT INTO public.order_status_logs(order_id,status,campus_id,metadata)\n  VALUES(p_order_id,\'delivered\',v_order.campus_id,jsonb_build_object(\'delivery_reward_recovery\',jsonb_build_object(\'version\',1,\'owner_hp\',v_owner_hp,\'total_hp\',v_total_hp,\'financial_complete\',false)));\n'||anchor);
  EXECUTE definition;
 END IF;
END $patch$;
