CREATE OR REPLACE FUNCTION public.hg_complete_pending_milestone(p_user_id uuid,p_milestone_id uuid,p_period_key text,p_hp_amount integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE p public.profiles%rowtype; m public.milestones%rowtype; um public.user_milestones%rowtype; h public.hp_transactions%rowtype;
 cap integer:=1000; earned integer:=0; amount integer; raw text; txn jsonb; receipt jsonb;
 month_key text:=to_char(now() AT TIME ZONE 'UTC','YYYY-MM');
BEGIN
 SELECT * INTO p FROM public.profiles WHERE id=p_user_id AND is_active FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Milestone recipient unavailable'; END IF;
 SELECT * INTO m FROM public.milestones WHERE id=p_milestone_id FOR SHARE;
 IF NOT FOUND OR m.trigger_type<>'social_follow' OR (m.campus_id IS NOT NULL AND m.campus_id IS DISTINCT FROM p.campus_id) THEN RAISE EXCEPTION 'Pending milestone scope invalid'; END IF;
 SELECT * INTO um FROM public.user_milestones WHERE user_id=p.id AND milestone_id=m.id AND period_key IS NOT DISTINCT FROM p_period_key FOR UPDATE;
 IF FOUND THEN
  IF um.reward_receipt IS NOT NULL THEN RETURN um.reward_receipt||jsonb_build_object('replayed',true,'hp_awarded',0); END IF;
  -- Historical completion alone is not proof of an unpaid reward. Old pending
  -- claims used reference_type=challenge; link its ledger without paying again.
  SELECT * INTO h FROM public.hp_transactions WHERE user_id=p.id AND reference_type='challenge' AND reference_id=um.id;
  IF NOT FOUND THEN RETURN jsonb_build_object('completed',false,'legacy_review_required',true,'completion_id',um.id); END IF;
  IF h.type<>'earn' THEN RAISE EXCEPTION 'Unexpected pending milestone ledger'; END IF;
  receipt:=jsonb_build_object('completed',true,'completion_id',um.id,'recorded_hp_awarded',h.amount,'hp_awarded',0,
   'hp_destination','pending','period_key',um.period_key,'replayed',true,'legacy_replayed',true);
  UPDATE public.user_milestones SET hp_awarded=h.amount,reward_receipt=receipt WHERE id=um.id;
  RETURN receipt;
 END IF;
 IF NOT coalesce(m.is_active,false) THEN RAISE EXCEPTION 'Milestone inactive'; END IF;
 IF p_hp_amount IS NULL OR p_hp_amount<0 OR p_hp_amount>1000000 THEN RAISE EXCEPTION 'Invalid milestone reward'; END IF;
 IF (m.time_window IS NULL AND p_period_key IS NOT NULL)
 OR (m.time_window='weekly' AND p_period_key IS DISTINCT FROM to_char(now() AT TIME ZONE 'Africa/Lagos','IYYY-"W"IW'))
 OR (m.time_window='monthly' AND p_period_key IS DISTINCT FROM to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM')) THEN RAISE EXCEPTION 'Milestone period mismatch'; END IF;
 SELECT value #>> '{}' INTO raw FROM public.system_settings WHERE key='monthly_pending_cap' AND campus_id IS NULL;
 IF FOUND THEN IF raw IS NULL OR raw !~ '^\d+$' THEN RAISE EXCEPTION 'Invalid monthly pending cap configuration'; END IF; cap:=raw::integer; END IF;
 SELECT total_earned INTO earned FROM public.monthly_hp_tracker WHERE user_id=p.id AND month=month_key FOR UPDATE;
 amount:=least(p_hp_amount,greatest(0,cap-coalesce(earned,0)));
 INSERT INTO public.user_milestones(user_id,milestone_id,hp_awarded,period_key,campus_id)
 VALUES(p.id,m.id,amount,p_period_key,p.campus_id) RETURNING * INTO um;
 IF amount>0 THEN
  txn:=public.record_hp_transaction_atomic(p.id,amount,'earn','pending','challenge','challenge',um.id,NULL,'Milestone: '||m.title||' pending',p.campus_id);
  IF txn ? 'error' OR coalesce((txn->>'replayed')::boolean,false) THEN RAISE EXCEPTION 'Pending milestone ledger unavailable'; END IF;
  PERFORM public.increment_monthly_hp_tracker(p.id,month_key,amount);
 END IF;
 receipt:=jsonb_build_object('completed',true,'completion_id',um.id,'recorded_hp_awarded',amount,'hp_awarded',amount,
  'hp_destination','pending','period_key',p_period_key,'replayed',false,'capped',amount<p_hp_amount);
 UPDATE public.user_milestones SET reward_receipt=receipt WHERE id=um.id;
 RETURN receipt;
END $$;
REVOKE ALL ON FUNCTION public.hg_complete_pending_milestone(uuid,uuid,text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_complete_pending_milestone(uuid,uuid,text,integer) TO service_role;
