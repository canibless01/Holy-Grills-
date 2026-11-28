-- Attendance only; no monetary grant or weekly reward configuration changes.
CREATE OR REPLACE FUNCTION public.hg_mark_current_login_checkin(p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE s public.login_streaks%rowtype; today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
 monday date:=date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date; day_key text; outcome text;
BEGIN
 PERFORM 1 FROM public.profiles WHERE id=p_user_id AND is_active AND NOT coalesce(is_fraud_flagged,false) FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'reason','excluded'); END IF;
 SELECT * INTO s FROM public.login_streaks WHERE user_id=p_user_id FOR UPDATE;
 IF NOT FOUND OR s.current_week_start IS DISTINCT FROM monday THEN
  RETURN jsonb_build_object('success',false,'reason','week_changed');
 END IF;
 day_key:=(today-monday)::text;
 outcome:='same_day';
 IF NOT (coalesce(s.week_state,'{}') ? day_key) THEN
  UPDATE public.login_streaks SET week_state=jsonb_set(coalesce(week_state,'{}'),ARRAY[day_key],'"checked"'),
   last_login_date=today,last_updated=now(),streak_count=coalesce(streak_count,0)+1
   WHERE id=s.id RETURNING * INTO s;
  outcome:='checked_in';
 END IF;
 RETURN jsonb_build_object('success',true,'action',outcome,'streak',to_jsonb(s));
END $$;
REVOKE ALL ON FUNCTION public.hg_mark_current_login_checkin(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_mark_current_login_checkin(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_reclaim_login_checkin(p_user_id uuid,p_source_type text,p_source_id uuid,p_min_topup numeric DEFAULT 1000)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE s public.login_streaks%rowtype; source_at timestamptz; source_day date; day_key text; prior text; ref uuid;
BEGIN
 IF p_source_id IS NULL OR p_source_type IS NULL OR p_source_type NOT IN ('order','wallet_topup') OR p_min_topup IS NULL OR p_min_topup<0 THEN
  RETURN jsonb_build_object('reclaimed',false,'day_offset',NULL,'reason','invalid_source');
 END IF;
 PERFORM 1 FROM public.profiles WHERE id=p_user_id AND is_active AND NOT coalesce(is_fraud_flagged,false) FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('reclaimed',false,'day_offset',NULL,'reason','excluded'); END IF;
 IF p_source_type='wallet_topup' THEN
  SELECT created_at INTO source_at FROM public.wallet_transactions WHERE id=p_source_id AND user_id=p_user_id
   AND type='credit' AND reference_type IN ('topup','bank_transfer') AND amount>=p_min_topup;
 ELSE
  SELECT o.delivered_at INTO source_at FROM public.orders o WHERE o.id=p_source_id AND o.user_id=p_user_id
   AND o.status='delivered' AND o.payment_status::text IN ('paid','partially_refunded')
   AND EXISTS(SELECT 1 FROM public.order_items oi WHERE oi.order_id=o.id AND NOT coalesce(oi.is_addon,false) AND oi.line_total>0);
 END IF;
 IF source_at IS NULL OR source_at>now() THEN
  RETURN jsonb_build_object('reclaimed',false,'day_offset',NULL,'reason','unqualified_source');
 END IF;
 source_day:=(source_at AT TIME ZONE 'Africa/Lagos')::date;
 SELECT * INTO s FROM public.login_streaks WHERE user_id=p_user_id FOR UPDATE;
 IF NOT FOUND OR s.current_week_start IS NULL OR source_day<s.current_week_start OR source_day>s.current_week_start+6 THEN
  RETURN jsonb_build_object('reclaimed',false,'day_offset',NULL,'reason','outside_saved_week');
 END IF;
 day_key:=(source_day-s.current_week_start)::text;
 prior:=s.week_state->>day_key;
 ref:=md5('holygrills:checkin_reclaim:'||p_user_id::text||':'||source_day::text)::uuid;
 IF coalesce(s.week_state,'{}') ? day_key THEN
  RETURN jsonb_build_object('reclaimed',false,'already_reclaimed',prior='reclaimed','day_offset',day_key::integer,'source_date',source_day,'reference_id',ref);
 END IF;
 UPDATE public.login_streaks SET week_state=jsonb_set(coalesce(week_state,'{}'),ARRAY[day_key],'"reclaimed"'),last_updated=now() WHERE id=s.id;
 RETURN jsonb_build_object('reclaimed',true,'already_reclaimed',false,'day_offset',day_key::integer,'source_date',source_day,'reference_id',ref);
END $$;
REVOKE ALL ON FUNCTION public.hg_reclaim_login_checkin(uuid,text,uuid,numeric) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_reclaim_login_checkin(uuid,text,uuid,numeric) TO service_role;
