-- Reuse the HP ledger and metadata for a safe, previewed administrative expiry.
CREATE OR REPLACE FUNCTION public.hg_admin_expire_hp(
 p_actor_id uuid,p_user_id uuid,p_amount integer,p_expected_balance integer,p_notes text,p_request_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE;target public.profiles%ROWTYPE;receipt public.hp_transactions%ROWTYPE;removed integer;r jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'Service access required' USING ERRCODE='42501';END IF;
 IF p_request_id IS NULL OR p_expected_balance IS NULL OR p_expected_balance<0 OR (p_amount IS NOT NULL AND p_amount<=0) OR p_notes IS NULL OR length(trim(p_notes)) NOT BETWEEN 1 AND 200 THEN RETURN jsonb_build_object('error','invalid_expiry');END IF;
 SELECT * INTO actor FROM public.profiles WHERE id=p_actor_id AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin') THEN RETURN jsonb_build_object('error','expiry_forbidden');END IF;
 SELECT * INTO target FROM public.profiles WHERE id=p_user_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','expiry_target_missing');END IF;
 IF actor.role::text<>'super_admin' AND (target.campus_id IS NULL OR actor.campus_id IS DISTINCT FROM target.campus_id) THEN RETURN jsonb_build_object('error','expiry_forbidden');END IF;
 SELECT * INTO receipt FROM public.hp_transactions WHERE user_id=p_user_id AND reference_type='admin_expiry' AND reference_id=p_request_id;
 IF FOUND THEN
  IF receipt.type::text<>'expire' OR receipt.issued_by_admin_id IS DISTINCT FROM p_actor_id OR receipt.metadata->>'notes' IS DISTINCT FROM p_notes OR receipt.metadata->'requested_amount' IS DISTINCT FROM coalesce(to_jsonb(p_amount),'null'::jsonb) OR receipt.metadata->'expected_balance' IS DISTINCT FROM to_jsonb(p_expected_balance) THEN RETURN jsonb_build_object('error','expiry_conflict');END IF;
  RETURN jsonb_build_object('success',true,'replayed',true,'expired',receipt.amount,'new_balance',target.hp_balance,'transaction_id',receipt.id);
 END IF;
 IF target.hp_balance IS DISTINCT FROM p_expected_balance THEN RETURN jsonb_build_object('error','expiry_balance_changed');END IF;
 removed:=coalesce(p_amount,target.hp_balance);
 IF removed<=0 THEN RETURN jsonb_build_object('error','nothing_to_expire');END IF;
 IF removed>target.hp_balance THEN RETURN jsonb_build_object('error','expiry_insufficient');END IF;
 r:=public.record_hp_transaction_atomic(p_user_id,-removed,'expire','active','admin_expiry','admin_expiry',p_request_id,p_actor_id,p_notes,target.campus_id);
 IF NOT coalesce((r->>'success')::boolean,false) THEN RAISE EXCEPTION 'Expiry receipt failed' USING ERRCODE='23514';END IF;
 UPDATE public.hp_transactions SET metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object('requested_amount',p_amount,'expected_balance',p_expected_balance) WHERE id=(r->>'transaction_id')::uuid;
 RETURN jsonb_build_object('success',true,'replayed',false,'expired',removed,'new_balance',(r->>'new_balance')::integer,'transaction_id',r->>'transaction_id');
END;$$;
REVOKE ALL ON FUNCTION public.hg_admin_expire_hp(uuid,uuid,integer,integer,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_admin_expire_hp(uuid,uuid,integer,integer,text,uuid) TO service_role;
