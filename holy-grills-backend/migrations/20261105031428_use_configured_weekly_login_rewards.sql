CREATE OR REPLACE FUNCTION public.hg_rollover_login_week(p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE p public.profiles%rowtype; s public.login_streaks%rowtype; h public.hp_transactions%rowtype;
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
 monday date:=date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date; previous date;
 effective integer:=0; missed integer; completed boolean; cycle integer; consecutive integer;
 base integer:=0; v_amount integer:=0; cap integer:=1000; earned integer:=0;
 reward_map jsonb; raw text; expires text; mult_scope uuid; flag boolean; multiplier numeric:=1; ref uuid; txn jsonb; receipt jsonb;
 month_key text:=to_char(now() AT TIME ZONE 'UTC','YYYY-MM'); legacy boolean:=false; capped boolean:=false;
BEGIN
 SELECT * INTO p FROM public.profiles WHERE id=p_user_id AND is_active AND NOT coalesce(is_fraud_flagged,false) FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'reason','excluded'); END IF;
 SELECT * INTO s FROM public.login_streaks WHERE user_id=p_user_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'reason','missing_streak'); END IF;
 IF s.current_week_start=monday THEN
  RETURN jsonb_build_object('success',true,'replayed',true,'hp_awarded',0,'receipt',s.last_week_receipt,'streak',to_jsonb(s),'today',today);
 END IF;
 IF s.current_week_start>monday THEN RAISE EXCEPTION 'Future attendance week'; END IF;
 previous:=monday-7;
 IF s.current_week_start=previous THEN
  SELECT count(*) INTO effective FROM jsonb_each_text(coalesce(s.week_state,'{}'))
   WHERE key ~ '^[0-6]$' AND value IN ('checked','reclaimed');
 END IF;
 missed:=7-effective;completed:=missed<=2;
 cycle:=greatest(coalesce(s.cycle_week_number,1),1);
 consecutive:=coalesce(s.consecutive_weeks,0);
 ref:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holygrills:login_streak:'||p.id::text||':'||previous::text);
 IF completed THEN
  SELECT * INTO h FROM public.hp_transactions WHERE user_id=p.id AND reference_type='streak' AND reference_id=ref;
  IF FOUND THEN
   IF h.type<>'earn' THEN RAISE EXCEPTION 'Unexpected weekly streak ledger'; END IF;
   -- Older payouts may already have incremented the tracker or been partly unlocked.
   -- Link the existing business receipt without re-crediting/re-counting it.
   legacy:=true;
  ELSE
   -- Match the setting rendered by the customer app; retain the legacy table as fallback.
   SELECT value INTO reward_map FROM public.system_settings WHERE key='login_streak_rewards'
    AND (campus_id=p.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
   IF jsonb_typeof(reward_map)='string' THEN reward_map:=(reward_map #>> '{}')::jsonb; END IF;
   IF reward_map IS NOT NULL AND jsonb_typeof(reward_map)<>'object' THEN RAISE EXCEPTION 'Invalid weekly reward configuration'; END IF;
   raw:=CASE WHEN cycle>=4 THEN coalesce(reward_map->>'4',reward_map->>'4+') ELSE reward_map->>cycle::text END;
   IF raw IS NOT NULL THEN
    IF raw !~ '^\d+$' THEN RAISE EXCEPTION 'Invalid weekly HP amount'; END IF;
    base:=raw::integer;
   ELSE
    SELECT hp_awarded INTO base FROM public.login_streak_rewards WHERE week_number=least(cycle,4) AND is_active
     AND (campus_id=p.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
    base:=greatest(coalesce(base,0),0);
   END IF;
   SELECT is_active INTO flag FROM public.feature_flags WHERE feature_name='hp_multiplier'
    AND (campus_id=p.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
   IF coalesce(flag,false) THEN
    SELECT value #>> '{}',campus_id INTO raw,mult_scope FROM public.system_settings WHERE key='hp_multiplier'
     AND (campus_id=p.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
    IF raw ~ '^2([.]0+)?$' THEN multiplier:=2; END IF;
    SELECT value #>> '{}' INTO expires FROM public.system_settings WHERE key='multiplier_expires_at' AND campus_id IS NOT DISTINCT FROM mult_scope;
    BEGIN
     IF nullif(expires,'') IS NOT NULL AND expires::timestamptz<=now() THEN multiplier:=1; END IF;
    EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN multiplier:=1; END;
   END IF;
   SELECT value #>> '{}' INTO raw FROM public.system_settings WHERE key='monthly_pending_cap' AND campus_id IS NULL;
   IF FOUND THEN
    IF raw IS NULL OR raw !~ '^\d+$' THEN RAISE EXCEPTION 'Invalid monthly pending cap configuration'; END IF;
    cap:=raw::integer;
   END IF;
   SELECT total_earned INTO earned FROM public.monthly_hp_tracker WHERE user_id=p.id AND month=month_key FOR UPDATE;
   v_amount:=least(base*multiplier,greatest(0,cap-coalesce(earned,0)));
   capped:=v_amount<base*multiplier;
   IF v_amount>0 THEN
    txn:=public.record_hp_transaction_atomic(p.id,v_amount,'earn','pending','streak','streak',ref,NULL,'Completed login streak week '||cycle,p.campus_id);
    IF txn ? 'error' THEN RAISE EXCEPTION 'Weekly pending HP remains uncredited'; END IF;
    IF coalesce((txn->>'replayed')::boolean,false) THEN RAISE EXCEPTION 'Unresolved concurrent weekly receipt'; END IF;
    UPDATE public.hp_transactions SET metadata=coalesce(metadata,'{}')||jsonb_build_object('login_week_award',jsonb_build_object('week_start',previous,'amount',v_amount,'cycle_week',cycle))
     WHERE id=(txn->>'transaction_id')::uuid;
    PERFORM public.increment_monthly_hp_tracker(p.id,month_key,v_amount);
   END IF;
  END IF;
  consecutive:=consecutive+1;
 ELSE
  consecutive:=0;
 END IF;
 receipt:=jsonb_build_object('version',1,'reference_id',ref,'week_start',previous,'missed_days',missed,
  'previous_week_completed',completed,'cycle_week',cycle,'hp_awarded',v_amount,'capped',capped,
  'legacy_replayed',legacy,'notified',legacy);
 UPDATE public.login_streaks SET current_week_start=monday,
  week_state=jsonb_build_object((today-monday)::text,'checked'),
  cycle_week_number=CASE WHEN completed THEN least(cycle+1,4) ELSE 1 END,
  consecutive_weeks=consecutive,last_login_date=today,last_updated=now(),
  streak_count=CASE WHEN completed THEN coalesce(streak_count,0)+1 ELSE 1 END,
  last_week_receipt=receipt WHERE id=s.id RETURNING * INTO s;
 RETURN jsonb_build_object('success',true,'replayed',false,'hp_awarded',v_amount,'receipt',receipt,'streak',to_jsonb(s),'today',today);
END $$;
REVOKE ALL ON FUNCTION public.hg_rollover_login_week(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_rollover_login_week(uuid) TO service_role;

