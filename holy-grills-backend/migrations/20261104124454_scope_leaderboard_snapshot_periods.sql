-- One archive per campus and period. No existing snapshot or customer row is removed.
ALTER TABLE public.leaderboard_snapshots DROP CONSTRAINT leaderboard_snapshots_period_key_key;
ALTER TABLE public.leaderboard_snapshots DROP CONSTRAINT uq_leaderboard_snapshots_period_type;
CREATE UNIQUE INDEX leaderboard_snapshots_campus_period_type_uidx
 ON public.leaderboard_snapshots(campus_id,period_key,ranking_type) NULLS NOT DISTINCT;

-- Service-only, invoker privileges: archive and monthly perks commit together.
-- A failed grant rolls back the archive so a retry can recover without doubling perks.
CREATE FUNCTION public.hg_finalize_monthly_leaderboard(
 p_campus_id uuid,p_period text,p_entries jsonb,p_hof boolean,p_spins boolean,
 p_prizes boolean,p_free_days integer,p_spin_days integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $fn$
DECLARE
 snapshot_id uuid; entry jsonb; uid uuid; place integer; sides integer; finishes integer;
 inducted jsonb:='[]'; free_until timestamptz:=now()+make_interval(days=>p_free_days);
 spin_until timestamptz:=now()+make_interval(days=>p_spin_days);
BEGIN
 IF p_campus_id IS NULL OR p_period !~ '^\d{4}-\d{2}$' OR jsonb_typeof(p_entries) IS DISTINCT FROM 'array'
 OR jsonb_array_length(p_entries)>10 OR p_free_days<1 OR p_spin_days<1 THEN
  RAISE EXCEPTION 'invalid leaderboard finalization';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_entries) e LEFT JOIN public.profiles p
  ON p.id=(e->>'user_id')::uuid AND p.campus_id=p_campus_id AND p.is_active AND p.role::text='student'
  WHERE p.id IS NULL OR (e->>'rank')::int NOT BETWEEN 1 AND 10 OR (e->>'hp_earned')::numeric<=0)
 OR (SELECT count(*)<>count(DISTINCT e->>'user_id') OR count(*)<>count(DISTINCT e->>'rank') FROM jsonb_array_elements(p_entries) e) THEN
  RAISE EXCEPTION 'invalid leaderboard entries';
 END IF;
 INSERT INTO public.leaderboard_snapshots(campus_id,period_key,ranking_type,entries)
 VALUES(p_campus_id,p_period,'monthly',p_entries)
 ON CONFLICT(campus_id,period_key,ranking_type) DO NOTHING RETURNING id INTO snapshot_id;
 IF snapshot_id IS NULL THEN RETURN jsonb_build_object('idempotent',true,'period',p_period); END IF;
 FOR entry IN SELECT * FROM jsonb_array_elements(p_entries) LOOP
  uid:=(entry->>'user_id')::uuid; place:=(entry->>'rank')::int;
  IF p_hof AND place<=4 THEN
   UPDATE public.profiles SET top4_finish_count=coalesce(top4_finish_count,0)+1 WHERE id=uid AND campus_id=p_campus_id RETURNING top4_finish_count INTO finishes;
   IF finishes=3 THEN
    INSERT INTO public.hall_of_fame_inductees(user_id,full_name,tier_at_induction,top4_finish_count,campus_id)
    SELECT uid,entry->>'full_name',coalesce(t.name,'Unknown'),finishes,p_campus_id
    FROM public.profiles p LEFT JOIN public.hp_tiers t ON t.id=p.current_tier_id WHERE p.id=uid;
    INSERT INTO public.hall_of_fame_rewards(user_id,inducted_at,status,campus_id) VALUES(uid,now(),'pending',p_campus_id);
    inducted:=inducted||jsonb_build_array(uid);
   END IF;
  END IF;
  IF p_spins THEN
   INSERT INTO public.exclusive_spins(user_id,spin_count,source,month,expires_at,campus_id)
   VALUES(uid,1,'leaderboard_prize',p_period,spin_until,p_campus_id);
  END IF;
  sides:=CASE WHEN place IN(1,2) THEN 2 WHEN place=3 THEN 1 ELSE 0 END;
  IF p_prizes THEN
   IF sides>0 THEN
    INSERT INTO public.free_side_credits(user_id,credits_remaining,source,month,expires_at,campus_id)
    VALUES(uid,sides,'leaderboard_prize',p_period,free_until,p_campus_id);
   END IF;
   INSERT INTO public.leaderboard_reward_fulfillments(user_id,rank,month,reward_type,status,free_sides,free_spins,campus_id)
   VALUES(uid,place,p_period,'leaderboard_prize','pending',sides,CASE WHEN p_spins THEN 1 ELSE 0 END,p_campus_id);
  END IF;
 END LOOP;
 IF p_hof THEN
  INSERT INTO public.free_side_credits(user_id,credits_remaining,source,month,expires_at,campus_id)
  SELECT DISTINCT h.user_id,1,'hall_of_fame_monthly',p_period,free_until,p_campus_id
  FROM public.hall_of_fame_inductees h WHERE h.campus_id=p_campus_id
   AND NOT EXISTS(SELECT 1 FROM public.free_side_credits f WHERE f.user_id=h.user_id AND f.source='hall_of_fame_monthly' AND f.month=p_period);
 END IF;
 RETURN jsonb_build_object('idempotent',false,'period',p_period,'snapshot_id',snapshot_id,'inducted',inducted,'top_count',jsonb_array_length(p_entries));
END $fn$;
REVOKE ALL ON FUNCTION public.hg_finalize_monthly_leaderboard(uuid,text,jsonb,boolean,boolean,boolean,integer,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_finalize_monthly_leaderboard(uuid,text,jsonb,boolean,boolean,boolean,integer,integer) TO service_role;
