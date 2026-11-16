ALTER TABLE public.user_milestones ADD COLUMN IF NOT EXISTS reward_receipt jsonb;
-- Definitions remain readable through existing RLS; grant receipts are server-owned.
REVOKE INSERT, UPDATE, DELETE ON public.user_milestones FROM PUBLIC,anon,authenticated;
CREATE OR REPLACE FUNCTION public.hg_complete_active_milestone(
 p_user_id uuid,p_milestone_id uuid,p_period_key text,p_hp_amount integer,p_admin_id uuid DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE p public.profiles%rowtype; m public.milestones%rowtype; um public.user_milestones%rowtype;
 h public.hp_transactions%rowtype; actor public.profiles%rowtype; result jsonb; receipt jsonb;
BEGIN
 SELECT * INTO p FROM public.profiles WHERE id=p_user_id AND is_active FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Milestone recipient unavailable'; END IF;
 SELECT * INTO m FROM public.milestones WHERE id=p_milestone_id FOR SHARE;
 IF NOT FOUND OR (m.campus_id IS NOT NULL AND m.campus_id IS DISTINCT FROM p.campus_id) THEN
  RAISE EXCEPTION 'Milestone scope invalid';
 END IF;
 IF p_admin_id IS NOT NULL THEN
  SELECT * INTO actor FROM public.profiles WHERE id=p_admin_id AND is_active;
  IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin') OR
   (actor.role::text<>'super_admin' AND actor.campus_id IS DISTINCT FROM p.campus_id) THEN
   RAISE EXCEPTION 'Milestone issuer forbidden';
  END IF;
 ELSIF m.trigger_type IN ('department_leader','faculty_leader','social_follow') THEN
  RAISE EXCEPTION 'Milestone requires a different grant flow';
 END IF;
 SELECT * INTO um FROM public.user_milestones WHERE user_id=p.id AND milestone_id=m.id
  AND period_key IS NOT DISTINCT FROM p_period_key FOR UPDATE;
 IF FOUND THEN
  IF um.reward_receipt IS NOT NULL THEN
   RETURN um.reward_receipt||jsonb_build_object('replayed',true,'hp_awarded',0);
  END IF;
  -- Legacy completions are not proof of an unpaid entitlement. Link a known
  -- historical ledger; never manufacture HP or an ambiguous tracker increment.
  SELECT * INTO h FROM public.hp_transactions WHERE user_id=p.id AND reference_type='milestone' AND reference_id=um.id;
  IF NOT FOUND THEN
   RETURN jsonb_build_object('completed',false,'legacy_review_required',true,'completion_id',um.id);
  END IF;
  IF h.type<>'earn' THEN RAISE EXCEPTION 'Unexpected milestone ledger'; END IF;
  receipt:=jsonb_build_object('completed',true,'completion_id',um.id,'recorded_hp_awarded',h.amount,
   'hp_awarded',0,'hp_destination',h.status,'period_key',um.period_key,'replayed',true);
  UPDATE public.user_milestones SET hp_awarded=h.amount,reward_receipt=receipt WHERE id=um.id;
  RETURN receipt;
 END IF;
 IF NOT coalesce(m.is_active,false) AND p_admin_id IS NULL THEN RAISE EXCEPTION 'Milestone inactive'; END IF;
 IF p_hp_amount IS NULL OR p_hp_amount<0 OR p_hp_amount>1000000 THEN RAISE EXCEPTION 'Invalid milestone reward'; END IF;
 IF (m.time_window IS NULL AND p_period_key IS NOT NULL)
  OR (m.time_window='weekly' AND p_period_key IS DISTINCT FROM to_char(now() AT TIME ZONE 'Africa/Lagos','IYYY-"W"IW'))
  OR (m.time_window='monthly' AND p_period_key IS DISTINCT FROM to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'))
  THEN RAISE EXCEPTION 'Milestone period mismatch'; END IF;
 INSERT INTO public.user_milestones(user_id,milestone_id,hp_awarded,period_key,campus_id,granted_by_admin_id)
  VALUES(p.id,m.id,p_hp_amount,p_period_key,p.campus_id,p_admin_id) RETURNING * INTO um;
 IF p_hp_amount>0 THEN
  result:=public.record_hp_transaction_atomic(p.id,p_hp_amount,'earn','active','challenge','milestone',um.id,p_admin_id,'Milestone: '||m.title,p.campus_id);
  IF result ? 'error' THEN RAISE EXCEPTION 'Milestone HP ledger unavailable'; END IF;
  IF NOT coalesce((result->>'replayed')::boolean,false) THEN
   PERFORM public.increment_monthly_hp_tracker(p.id,to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'),p_hp_amount);
  END IF;
 END IF;
 PERFORM public.hg_set_profile_tier_from_balance(p.id);
 receipt:=jsonb_build_object('completed',true,'completion_id',um.id,'recorded_hp_awarded',p_hp_amount,
  'hp_awarded',p_hp_amount,'hp_destination','active','period_key',p_period_key,'replayed',false);
 UPDATE public.user_milestones SET reward_receipt=receipt WHERE id=um.id;
 RETURN receipt;
END $$;
REVOKE ALL ON FUNCTION public.hg_complete_active_milestone(uuid,uuid,text,integer,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_complete_active_milestone(uuid,uuid,text,integer,uuid) TO service_role;

-- Events use the same completion boundary as manual/self/callback active grants.
CREATE OR REPLACE FUNCTION public.hg_complete_event_milestones(p_user_id uuid,p_multiplier numeric)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE m record; c uuid; period text; since timestamptz; progress integer; amount integer;
 r jsonb; receipts jsonb:='[]';
BEGIN
 SELECT campus_id INTO c FROM public.profiles WHERE id=p_user_id FOR UPDATE;
 FOR m IN SELECT * FROM public.milestones WHERE is_active AND trigger_type IN ('first_event','event_checkins')
  AND (campus_id=c OR campus_id IS NULL) ORDER BY id LOOP
  period:=CASE m.time_window WHEN 'weekly' THEN to_char(now() AT TIME ZONE 'Africa/Lagos','IYYY-"W"IW')
    WHEN 'monthly' THEN to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM') END;
  since:=CASE m.time_window WHEN 'weekly' THEN date_trunc('week',now() AT TIME ZONE 'Africa/Lagos') AT TIME ZONE 'Africa/Lagos'
    WHEN 'monthly' THEN date_trunc('month',now() AT TIME ZONE 'Africa/Lagos') AT TIME ZONE 'Africa/Lagos' END;
  SELECT count(*) INTO progress FROM public.event_checkins ci JOIN public.event_tickets t ON t.id=ci.ticket_id
   WHERE t.user_id=p_user_id AND (since IS NULL OR ci.created_at>=since);
  IF progress<greatest(coalesce(m.trigger_value,1),1) THEN CONTINUE; END IF;
  amount:=greatest(coalesce(m.hp_awarded,0),0);
  IF p_multiplier>1 THEN amount:=amount*p_multiplier; END IF;
  r:=public.hg_complete_active_milestone(p_user_id,m.id,period,amount,NULL);
  IF NOT coalesce((r->>'completed')::boolean,false) THEN RAISE EXCEPTION 'Historical milestone requires reconciliation'; END IF;
  IF NOT (r->>'replayed')::boolean THEN
   receipts:=receipts||jsonb_build_array(jsonb_build_object('milestone_id',m.id,'completion_id',r->>'completion_id','hp_awarded',r->'hp_awarded'));
  END IF;
 END LOOP;
 PERFORM public.hg_set_profile_tier_from_balance(p_user_id);
 RETURN receipts;
END $$;
REVOKE ALL ON FUNCTION public.hg_complete_event_milestones(uuid,numeric) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_complete_event_milestones(uuid,numeric) TO service_role;
