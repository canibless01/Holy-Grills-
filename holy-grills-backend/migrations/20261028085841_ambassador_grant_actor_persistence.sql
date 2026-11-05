-- Grant ledger and benefit commit together. A failed award leaves neither.
CREATE OR REPLACE FUNCTION public.hg_issue_ambassador_grant_atomic(
 p_actor_id uuid,p_ambassador_id uuid,p_category text,p_amount numeric,p_month text,p_reason text,
 p_validity_days integer,p_uses integer,p_source text,p_claim_id uuid,p_override boolean,p_intent text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE; target public.profiles%ROWTYPE;
 grant_row public.ambassador_grants%ROWTYPE; discount public.ambassador_meal_discounts%ROWTYPE;
 hp jsonb; credit jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'ambassador_forbidden'; END IF;
 SELECT * INTO actor FROM public.profiles WHERE id=p_actor_id AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin') THEN RAISE EXCEPTION 'ambassador_forbidden'; END IF;
 PERFORM 1 FROM public.wallets WHERE user_id=p_ambassador_id FOR UPDATE;
 SELECT * INTO target FROM public.profiles WHERE id=p_ambassador_id AND is_active FOR UPDATE;
 IF NOT FOUND OR (actor.role::text<>'super_admin' AND actor.campus_id IS DISTINCT FROM target.campus_id)
 OR NOT EXISTS(SELECT 1 FROM public.ambassadors WHERE profile_id=p_ambassador_id AND status='active')
 THEN RAISE EXCEPTION 'ambassador_forbidden'; END IF;
 IF p_amount IS NULL OR p_amount::text IN ('NaN','Infinity','-Infinity') OR p_amount<=0 OR p_amount>1000000
 OR p_category NOT IN ('hp','free_side','meal_discount') OR p_month !~ '^\d{4}-(0[1-9]|1[0-2])$'
 OR nullif(btrim(p_reason),'') IS NULL OR length(p_reason)>500 OR nullif(p_intent,'') IS NULL
 OR p_validity_days IS NULL OR p_validity_days NOT BETWEEN 1 AND 365 OR p_uses IS NULL OR p_uses NOT BETWEEN 1 AND 100
 OR (p_category IN ('hp','free_side') AND p_amount<>trunc(p_amount))
 OR (p_category='free_side' AND p_amount>20) THEN RAISE EXCEPTION 'ambassador_grant_invalid'; END IF;
 SELECT * INTO grant_row FROM public.ambassador_grants WHERE idempotency_key=p_intent;
 IF FOUND THEN
   IF grant_row.ambassador_id<>p_ambassador_id OR grant_row.reward_category<>p_category OR grant_row.amount<>p_amount
   OR grant_row.reason<>p_reason OR grant_row.issued_by<>p_actor_id OR grant_row.month<>p_month
   OR grant_row.validity_days IS DISTINCT FROM p_validity_days OR grant_row.uses_count<>p_uses
   OR grant_row.source IS DISTINCT FROM p_source OR grant_row.milestone_claim_id IS DISTINCT FROM p_claim_id
   OR grant_row.duplicate_override IS DISTINCT FROM p_override THEN RAISE EXCEPTION 'ambassador_intent_conflict'; END IF;
   RETURN to_jsonb(grant_row)||jsonb_build_object('idempotent',true);
 END IF;
 IF NOT p_override AND EXISTS(SELECT 1 FROM public.ambassador_grants WHERE ambassador_id=p_ambassador_id
   AND month=p_month AND reward_category=p_category AND NOT duplicate_override) THEN
   RETURN jsonb_build_object('error','duplicate_monthly_grant'); END IF;
 INSERT INTO public.ambassador_grants(ambassador_id,month,reward_category,amount,uses_count,validity_days,
   reason,source,milestone_claim_id,duplicate_override,idempotency_key,issued_by)
 VALUES(p_ambassador_id,p_month,p_category,p_amount,p_uses,p_validity_days,p_reason,p_source,p_claim_id,p_override,p_intent,p_actor_id)
 RETURNING * INTO grant_row;
 IF p_category='hp' THEN
   hp:=public.record_hp_transaction_atomic(p_ambassador_id,p_amount::integer,'earn','active',
      'ambassador_grant','ambassador_grant',grant_row.id,p_actor_id,p_reason,target.campus_id);
   IF hp ? 'error' THEN RAISE EXCEPTION 'ambassador_award_failed'; END IF;
   UPDATE public.ambassador_grants SET hp_transaction_id=(SELECT id FROM public.hp_transactions
     WHERE user_id=p_ambassador_id AND reference_id=grant_row.id AND reference_type='ambassador_grant' LIMIT 1)
     WHERE id=grant_row.id RETURNING * INTO grant_row;
 ELSIF p_category='free_side' THEN
   credit:=public.hg_grant_free_sides_atomic(p_actor_id,p_ambassador_id,grant_row.id,p_amount::integer,p_validity_days,p_reason);
   IF credit ? 'error' OR credit->>'credit_id' IS NULL THEN RAISE EXCEPTION 'ambassador_award_failed'; END IF;
   UPDATE public.ambassador_grants SET free_side_grant_id=(credit->>'credit_id')::uuid,
     expires_at=(credit->>'expires_at')::timestamptz WHERE id=grant_row.id RETURNING * INTO grant_row;
 ELSE
   discount:=public.hg_grant_ambassador_meal_discount(p_actor_id,p_ambassador_id,p_amount,p_uses,p_validity_days,grant_row.id,p_reason);
   SELECT * INTO grant_row FROM public.ambassador_grants WHERE id=grant_row.id;
 END IF;
 IF p_claim_id IS NOT NULL THEN
   UPDATE public.ambassador_milestone_claims SET status='issued',grant_id=grant_row.id,
     decided_by=p_actor_id,decided_at=now() WHERE id=p_claim_id AND ambassador_id=p_ambassador_id;
   IF NOT FOUND THEN RAISE EXCEPTION 'ambassador_claim_invalid'; END IF;
 END IF;
 RETURN to_jsonb(grant_row)||jsonb_build_object('idempotent',false);
END; $$;
REVOKE ALL ON FUNCTION public.hg_issue_ambassador_grant_atomic(uuid,uuid,text,numeric,text,text,integer,integer,text,uuid,boolean,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_issue_ambassador_grant_atomic(uuid,uuid,text,numeric,text,text,integer,integer,text,uuid,boolean,text) TO service_role;
