-- Existing calendar is the single source for graduation/convocation dates.
ALTER TABLE public.academic_calendar DROP CONSTRAINT academic_calendar_period_type_check;
ALTER TABLE public.academic_calendar ADD CONSTRAINT academic_calendar_period_type_check
 CHECK (period_type IN ('semester','exam','break','holiday','orientation','graduation'));

CREATE OR REPLACE FUNCTION public.hg_graduation_eligibility(p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO public AS $function$
DECLARE
 v_profile public.profiles%ROWTYPE; v_min_text text; v_min_rank integer:=400;
 v_rank integer:=0; v_count integer:=0; v_period public.academic_calendar%ROWTYPE;
 v_claimed boolean; v_reason text; v_today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RETURN jsonb_build_object('error','forbidden'); END IF;
 SELECT * INTO v_profile FROM public.profiles WHERE id=p_user_id AND is_active;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','profile_not_found'); END IF;
 SELECT EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=p_user_id
               AND reference_type='graduation' AND type='earn') INTO v_claimed;
 v_claimed:=v_claimed OR coalesce(v_profile.graduation_claimed,false);
 IF v_claimed THEN
  RETURN jsonb_build_object('eligible',false,'claimed',true,'minimum_orders',3,
    'academic_level',v_profile.academic_level,'in_period',false,'period',NULL,'reason','claimed');
 END IF;
 IF v_profile.campus_id IS NULL THEN
  RETURN jsonb_build_object('eligible',false,'claimed',false,'minimum_orders',3,
    'academic_level',v_profile.academic_level,'in_period',false,'period',NULL,'reason','campus_required');
 END IF;
 SELECT value#>>'{}' INTO v_min_text FROM public.system_settings
  WHERE key='graduation_min_level' AND (campus_id=v_profile.campus_id OR campus_id IS NULL)
  ORDER BY (campus_id IS NOT NULL) DESC LIMIT 1;
 IF FOUND THEN
  IF v_min_text IS NULL OR v_min_text !~ '^[1-9][0-9]{0,5}$' THEN
   RETURN jsonb_build_object('eligible',false,'claimed',false,'minimum_orders',3,
     'academic_level',v_profile.academic_level,'in_period',false,'period',NULL,'reason','configuration');
  END IF;
  v_min_rank:=v_min_text::integer;
 END IF;
 SELECT coalesce(rank,0) INTO v_rank FROM public.academic_levels
  WHERE value=btrim(v_profile.academic_level) AND (campus_id=v_profile.campus_id OR campus_id IS NULL)
  ORDER BY (campus_id IS NOT NULL) DESC LIMIT 1;
 v_rank:=coalesce(v_rank,0);
 SELECT count(*) INTO v_count FROM public.orders
  WHERE user_id=p_user_id AND campus_id=v_profile.campus_id AND status::text='delivered'
    AND payment_status::text IN ('paid','partially_refunded');
 SELECT * INTO v_period FROM public.academic_calendar
  WHERE period_type='graduation' AND is_active
    AND (campus_id=v_profile.campus_id OR campus_id IS NULL)
    AND start_date<=v_today AND end_date>=v_today
  ORDER BY (campus_id IS NOT NULL) DESC,start_date DESC,id LIMIT 1;
 v_reason:=CASE WHEN v_rank<v_min_rank THEN 'level' WHEN v_count<3 THEN 'orders'
                WHEN v_period.id IS NULL THEN 'period' ELSE 'eligible' END;
 RETURN jsonb_build_object('eligible',v_reason='eligible','claimed',false,'minimum_orders',3,
   'delivered_orders',v_count,'required_level',v_min_rank,'academic_level',v_profile.academic_level,
   'user_rank',v_rank,'in_period',v_period.id IS NOT NULL,'reason',v_reason,
   'period',CASE WHEN v_period.id IS NULL THEN NULL ELSE jsonb_build_object('id',v_period.id,
               'name',v_period.name,'start_date',v_period.start_date,'end_date',v_period.end_date) END);
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_graduation_eligibility(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_graduation_eligibility(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_claim_graduation_atomic(p_user_id uuid,p_hp_amount integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO public AS $function$
DECLARE
 v_profile public.profiles%ROWTYPE; v_receipt public.hp_transactions%ROWTYPE;
 v_eligibility jsonb; v_award jsonb; v_row record;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RETURN jsonb_build_object('error','forbidden'); END IF;
 IF p_user_id IS NULL THEN RETURN jsonb_build_object('error','profile_not_found'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('hg-graduation:'||p_user_id::text,0));
 -- Order -> wallet -> profile follows delivery/refund lock order. Hold eligible
 -- delivered orders until the award commits, without allowing a refund race.
 FOR v_row IN SELECT id FROM public.orders WHERE user_id=p_user_id AND status::text='delivered'
                AND payment_status::text IN ('paid','partially_refunded')
              ORDER BY id FOR SHARE LOOP NULL; END LOOP;
 PERFORM 1 FROM public.wallets WHERE user_id=p_user_id FOR UPDATE;
 SELECT * INTO v_profile FROM public.profiles WHERE id=p_user_id AND is_active FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','profile_not_found'); END IF;
 -- Any historical earning (even expired or with a legacy reference) proves the
 -- lifetime bonus was already paid. Repair only its marker, before fresh gates.
 SELECT * INTO v_receipt FROM public.hp_transactions WHERE user_id=p_user_id
  AND reference_type='graduation' AND type='earn' ORDER BY created_at,id LIMIT 1;
 IF FOUND THEN
  UPDATE public.profiles SET graduation_claimed=true,updated_at=now() WHERE id=p_user_id;
  RETURN jsonb_build_object('success',true,'replayed',true,'hp_awarded',0,
    'academic_level',v_profile.academic_level,'transaction_id',v_receipt.id);
 END IF;
 IF coalesce(v_profile.graduation_claimed,false) THEN
  RETURN jsonb_build_object('error','already_claimed');
 END IF;
 IF p_hp_amount IS NULL OR p_hp_amount<=0 THEN RETURN jsonb_build_object('error','configuration'); END IF;
 -- Stabilize the level/config/calendar gate while its claim is evaluated.
 PERFORM 1 FROM public.academic_levels WHERE value=btrim(v_profile.academic_level)
  AND (campus_id=v_profile.campus_id OR campus_id IS NULL) FOR SHARE;
 PERFORM 1 FROM public.system_settings WHERE key='graduation_min_level'
  AND (campus_id=v_profile.campus_id OR campus_id IS NULL) FOR SHARE;
 PERFORM 1 FROM public.academic_calendar WHERE period_type='graduation'
  AND (campus_id=v_profile.campus_id OR campus_id IS NULL) FOR SHARE;
 v_eligibility:=public.hg_graduation_eligibility(p_user_id);
 IF NOT coalesce((v_eligibility->>'eligible')::boolean,false) THEN
  RETURN v_eligibility||jsonb_build_object('error',coalesce(v_eligibility->>'reason','configuration'));
 END IF;
 v_award:=public.record_hp_transaction_atomic(p_user_id,p_hp_amount,'earn','active','graduation',
   'graduation',p_user_id,NULL,'Graduation milestone HP',v_profile.campus_id);
 IF v_award ? 'error' OR NOT coalesce((v_award->>'success')::boolean,false) THEN
  RAISE EXCEPTION 'graduation_hp_award_failed';
 END IF;
 IF NOT coalesce((v_award->>'replayed')::boolean,false) THEN
  PERFORM public.increment_monthly_hp_tracker(p_user_id,to_char(now() AT TIME ZONE 'UTC','YYYY-MM'),p_hp_amount);
 END IF;
 PERFORM public.hg_set_profile_tier_from_balance(p_user_id);
 UPDATE public.profiles SET graduation_claimed=true,updated_at=now() WHERE id=p_user_id;
 RETURN jsonb_build_object('success',true,'replayed',coalesce((v_award->>'replayed')::boolean,false),
   'hp_awarded',CASE WHEN coalesce((v_award->>'replayed')::boolean,false) THEN 0 ELSE p_hp_amount END,
   'academic_level',v_profile.academic_level,'transaction_id',v_award->'transaction_id');
EXCEPTION WHEN OTHERS THEN
 -- Roll back the earning, monthly counter and marker together on any failure.
 RETURN jsonb_build_object('error','claim_unavailable','debug_code',SQLSTATE);
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_claim_graduation_atomic(uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_claim_graduation_atomic(uuid,integer) TO service_role;
