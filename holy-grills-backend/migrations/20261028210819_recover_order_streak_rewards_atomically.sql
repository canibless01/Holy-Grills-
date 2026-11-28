-- Streak state, award and monthly counter commit together. Reuse existing order logs.
CREATE OR REPLACE FUNCTION public.hg_process_order_streak_atomic(p_order_id uuid,p_multiplier numeric,p_notes text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE o public.orders%ROWTYPE; s public.order_streaks%ROWTYPE; receipt public.order_status_logs%ROWTYPE;
 state jsonb; plan jsonb; result jsonb; award jsonb; wk date; latest date; period text; ref uuid;
 v_streak integer; latest_weeks integer; reward integer; max_week integer; paid integer:=0; old_hp integer;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'order_streak_forbidden' USING ERRCODE='42501'; END IF;
 SELECT * INTO o FROM public.orders WHERE id=p_order_id FOR UPDATE;
 IF NOT FOUND OR o.user_id IS NULL OR o.status::text<>'delivered' OR o.hp_credited_at IS NULL OR coalesce(o.subtotal,0)<=0 THEN
  RETURN jsonb_build_object('error','qualifying_delivery_required');
 END IF;
 IF o.delivered_at IS NULL OR o.delivered_at>now()+interval '5 minutes' THEN RETURN jsonb_build_object('error','delivery_date_review_required'); END IF;
 PERFORM 1 FROM public.profiles WHERE id=o.user_id AND is_active FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','active_recipient_required'); END IF;
 SELECT * INTO receipt FROM public.order_status_logs WHERE order_id=o.id AND metadata ? 'order_streak_recovery' ORDER BY created_at,id LIMIT 1 FOR UPDATE;
 state:=receipt.metadata->'order_streak_recovery';
 IF coalesce((state->>'complete')::boolean,false) THEN RETURN (state->'result')||jsonb_build_object('replayed',true,'hp_awarded',0); END IF;
 wk:=date_trunc('week',o.delivered_at AT TIME ZONE 'Africa/Lagos')::date;
 period:=to_char(wk,'IYYY-IW');
 ref:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,'holygrills:order_streak:'||o.user_id::text||':'||period);
 SELECT * INTO s FROM public.order_streaks WHERE user_id=o.user_id FOR UPDATE;
 -- Count consecutive actual delivery weeks; recovery is independent of today's date.
 WITH dates AS (SELECT DISTINCT date_trunc('week',delivered_at AT TIME ZONE 'Africa/Lagos')::date d
 FROM public.orders WHERE user_id=o.user_id AND status::text='delivered' AND subtotal>0 AND delivered_at IS NOT NULL AND delivered_at<=(wk+7)::timestamp AT TIME ZONE 'Africa/Lagos'),
 ranked AS (SELECT d,row_number() OVER(ORDER BY d DESC) n FROM dates WHERE d<=wk)
 SELECT count(*)::integer INTO v_streak FROM ranked WHERE d=wk-((n-1)::integer*7);
 -- Preserve an established legacy prefix when its source dates predate this implementation.
 IF s.last_order_week=to_char(wk-7,'IYYY-IW') THEN v_streak:=greatest(v_streak,s.streak_weeks+1); END IF;
 IF s.last_order_week=period THEN v_streak:=greatest(v_streak,s.streak_weeks); END IF;
 plan:=state->'plan';
 IF plan IS NULL THEN
  SELECT l.metadata->'order_streak_recovery'->'plan' INTO plan FROM public.order_status_logs l
   JOIN public.orders other ON other.id=l.order_id WHERE other.user_id=o.user_id
   AND l.metadata->'order_streak_recovery'->'plan'->>'week'=period ORDER BY l.created_at,l.id LIMIT 1;
 END IF;
 IF plan IS NULL THEN
  IF p_multiplier IS NULL OR p_multiplier<1 OR p_multiplier>100 THEN RETURN jsonb_build_object('error','invalid_streak_multiplier'); END IF;
  WITH effective AS (SELECT DISTINCT ON(weeks) weeks,hp_awarded,is_active FROM public.order_streak_rewards
   WHERE campus_id IS NULL OR campus_id=o.campus_id ORDER BY weeks,(campus_id IS NOT NULL) DESC,created_at DESC,id)
  SELECT max(weeks) INTO max_week FROM effective WHERE is_active AND hp_awarded>0;
  WITH effective AS (SELECT DISTINCT ON(r.weeks) r.weeks,r.hp_awarded,r.is_active FROM public.order_streak_rewards r
   WHERE r.campus_id IS NULL OR r.campus_id=o.campus_id ORDER BY r.weeks,(r.campus_id IS NOT NULL) DESC,r.created_at DESC,r.id)
  SELECT e.hp_awarded INTO reward FROM effective e WHERE e.weeks=least(v_streak,max_week) AND e.is_active AND e.hp_awarded>0;
  reward:=round(coalesce(reward,0)*p_multiplier)::integer;
  plan:=jsonb_build_object('week',period,'streak_weeks',v_streak,'hp',reward,'reference_id',ref,'campus_id',o.campus_id);
 END IF;
 IF receipt.id IS NULL THEN
   INSERT INTO public.order_status_logs(order_id,status,campus_id,metadata) VALUES(o.id,'delivered',o.campus_id,jsonb_build_object('order_streak_recovery',jsonb_build_object('plan',plan,'complete',false))) RETURNING * INTO receipt;
  ELSE
   UPDATE public.order_status_logs SET metadata=jsonb_set(metadata,'{order_streak_recovery,plan}',plan) WHERE id=receipt.id;
 END IF;
 reward:=(plan->>'hp')::integer; v_streak:=(plan->>'streak_weeks')::integer; ref:=(plan->>'reference_id')::uuid;
 BEGIN
  -- Same weekly reference as the old Python path: existing grants are adopted, never paid again.
  SELECT amount INTO old_hp FROM public.hp_transactions WHERE user_id=o.user_id AND reference_type='streak' AND reference_id=ref AND type='earn' AND source='streak' AND status='active';
  IF old_hp IS NULL AND reward>0 THEN
   award:=public.record_hp_transaction_atomic(o.user_id,reward,'earn','active','streak','streak',ref,NULL,p_notes,(plan->>'campus_id')::uuid);
   IF NOT coalesce((award->>'success')::boolean,false) THEN RAISE EXCEPTION 'streak_award_failed'; END IF;
   IF NOT coalesce((award->>'replayed')::boolean,false) THEN
    paid:=reward;
    PERFORM public.increment_monthly_hp_tracker(o.user_id,to_char(now() AT TIME ZONE 'UTC','YYYY-MM'),paid);
   END IF;
  END IF;
  SELECT max(date_trunc('week',delivered_at AT TIME ZONE 'Africa/Lagos')::date) INTO latest FROM public.orders
   WHERE user_id=o.user_id AND status::text='delivered' AND subtotal>0 AND delivered_at IS NOT NULL AND delivered_at<=now()+interval '5 minutes';
  WITH dates AS (SELECT DISTINCT date_trunc('week',delivered_at AT TIME ZONE 'Africa/Lagos')::date d FROM public.orders
   WHERE user_id=o.user_id AND status::text='delivered' AND subtotal>0 AND delivered_at IS NOT NULL AND delivered_at<=now()+interval '5 minutes'),
  ranked AS (SELECT d,row_number() OVER(ORDER BY d DESC) n FROM dates)
  SELECT count(*)::integer INTO latest_weeks FROM ranked WHERE d=latest-((n-1)::integer*7);
  IF latest=wk THEN latest_weeks:=greatest(latest_weeks,v_streak); END IF;
  IF s.last_order_week=to_char(latest,'IYYY-IW') THEN latest_weeks:=greatest(latest_weeks,s.streak_weeks); END IF;
  INSERT INTO public.order_streaks(user_id,streak_weeks,longest_streak,last_order_week,last_updated,campus_id)
   VALUES(o.user_id,latest_weeks,greatest(latest_weeks,v_streak,coalesce(s.longest_streak,0)),to_char(latest,'IYYY-IW'),now(),o.campus_id)
  ON CONFLICT(user_id) DO UPDATE SET streak_weeks=excluded.streak_weeks,longest_streak=greatest(order_streaks.longest_streak,excluded.longest_streak),last_order_week=excluded.last_order_week,last_updated=excluded.last_updated;
  result:=jsonb_build_object('success',true,'streak_weeks',v_streak,'week',period,'hp_awarded',paid,'reference_id',ref,'new_week',old_hp IS NULL,'replayed',false);
  UPDATE public.order_status_logs SET metadata=jsonb_set(metadata,'{order_streak_recovery}',jsonb_build_object('plan',plan,'complete',true,'result',result)) WHERE id=receipt.id;
 EXCEPTION WHEN OTHERS THEN
  UPDATE public.order_status_logs SET metadata=jsonb_set(metadata,'{order_streak_recovery,error}',to_jsonb(SQLSTATE)) WHERE id=receipt.id;
  RETURN jsonb_build_object('error','order_streak_pending');
 END;
 RETURN result;
END $function$;
REVOKE ALL ON FUNCTION public.hg_process_order_streak_atomic(uuid,numeric,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_process_order_streak_atomic(uuid,numeric,text) TO service_role;
DROP POLICY IF EXISTS order_streak_recovery_private ON public.order_status_logs;
CREATE POLICY order_streak_recovery_private ON public.order_status_logs AS RESTRICTIVE FOR ALL TO anon,authenticated
 USING (NOT (metadata ? 'order_streak_recovery')) WITH CHECK (NOT (metadata ? 'order_streak_recovery'));
