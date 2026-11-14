-- Reuse the existing audit ledger as the request receipt. No new table/column.
CREATE OR REPLACE FUNCTION public.hg_write_ambassador_milestone(p_actor uuid,p_request uuid,p_id uuid,p_scope uuid,p_values jsonb,p_expected timestamptz,p_create boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;m public.ambassador_milestones%rowtype;old_row public.ambassador_milestones%rowtype;receipt public.admin_audit_logs%rowtype;intent jsonb;merged jsonb;action_name text;reused boolean:=false;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_AMB_MILESTONE_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('admin','super_admin');
 IF NOT FOUND OR (a.role::text<>'super_admin' AND (p_scope IS NULL OR p_scope IS DISTINCT FROM a.campus_id)) THEN RAISE EXCEPTION 'HG_AMB_MILESTONE_ACCESS' USING ERRCODE='42501';END IF;
 IF p_request IS NULL OR p_id IS NULL OR p_create IS NULL OR jsonb_typeof(p_values) IS DISTINCT FROM 'object' OR p_values='{}' OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_values) k WHERE k NOT IN('metric','threshold','reward_type','reward_amount','reward_uses','validity_days','auto_issue','is_active')) THEN RAISE EXCEPTION 'HG_AMB_MILESTONE_INVALID';END IF;
 intent:=jsonb_build_object('id',p_id,'scope',p_scope,'values',p_values,'expected',p_expected,'create',p_create);
 PERFORM pg_advisory_xact_lock(hashtextextended('ambassador-milestone-intent:'||p_request,0));
 SELECT * INTO receipt FROM public.admin_audit_logs WHERE id=p_request;
 IF FOUND THEN
  IF receipt.actor_id IS DISTINCT FROM p_actor OR receipt.entity_type IS DISTINCT FROM 'ambassador_milestone' OR receipt.after_value->'request' IS DISTINCT FROM intent THEN RAISE EXCEPTION 'HG_AMB_MILESTONE_CONFLICT';END IF;
  RETURN jsonb_build_object('milestone',receipt.after_value->'milestone','replayed',true);
 END IF;
 IF p_create THEN
  PERFORM pg_advisory_xact_lock(hashtextextended('ambassador-milestone:'||coalesce(p_scope::text,'global')||':'||p_values::text,0));
  merged:=jsonb_build_object('reward_uses',1,'validity_days',14,'auto_issue',false,'is_active',true)||p_values;
 ELSE
  SELECT * INTO old_row FROM public.ambassador_milestones WHERE id=p_id AND campus_id IS NOT DISTINCT FROM p_scope FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'HG_AMB_MILESTONE_ACCESS' USING ERRCODE='42501';END IF;
  IF p_expected IS NULL OR old_row.updated_at IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'HG_AMB_MILESTONE_STALE';END IF;
  merged:=to_jsonb(old_row)||p_values;
 END IF;
 m:=jsonb_populate_record(NULL::public.ambassador_milestones,merged);
 IF m.metric IS NULL OR m.reward_type IS NULL OR m.reward_uses IS NULL OR m.validity_days IS NULL OR m.metric NOT IN('orders','signups','shares') OR m.threshold IS NULL OR m.threshold<=0 OR m.reward_type NOT IN('hp','free_side','meal_discount') OR m.reward_amount IS NULL OR m.reward_amount<=0 OR m.reward_amount>1000000 OR m.reward_uses NOT BETWEEN 1 AND 100 OR m.validity_days NOT BETWEEN 1 AND 365 OR m.auto_issue IS NULL OR m.is_active IS NULL OR (m.reward_type IN('hp','free_side') AND m.reward_amount<>trunc(m.reward_amount)) OR (m.reward_type='free_side' AND m.reward_amount>20) THEN RAISE EXCEPTION 'HG_AMB_MILESTONE_INVALID';END IF;
 IF p_create THEN
  -- Older clients without a saved UUID still cannot race identical policies.
  SELECT * INTO old_row FROM public.ambassador_milestones x WHERE x.campus_id IS NOT DISTINCT FROM p_scope AND x.created_by=p_actor AND x.created_at>now()-interval '10 minutes' AND x.metric=m.metric AND x.threshold=m.threshold AND x.reward_type=m.reward_type AND x.reward_amount=m.reward_amount AND x.reward_uses=m.reward_uses AND x.validity_days=m.validity_days AND x.auto_issue=m.auto_issue AND x.is_active=m.is_active ORDER BY x.created_at,x.id LIMIT 1;
  IF FOUND THEN m:=old_row;reused:=true;
  ELSE INSERT INTO public.ambassador_milestones(id,campus_id,metric,threshold,reward_type,reward_amount,reward_uses,validity_days,auto_issue,is_active,created_by) VALUES(p_id,p_scope,m.metric,m.threshold,m.reward_type,m.reward_amount,m.reward_uses,m.validity_days,m.auto_issue,m.is_active,p_actor) RETURNING * INTO m;END IF;
  action_name:=CASE WHEN reused THEN 'ambassador_milestone_reused' ELSE 'ambassador_milestone_created' END;
 ELSE
  UPDATE public.ambassador_milestones SET metric=m.metric,threshold=m.threshold,reward_type=m.reward_type,reward_amount=m.reward_amount,reward_uses=m.reward_uses,validity_days=m.validity_days,auto_issue=m.auto_issue,is_active=m.is_active WHERE id=p_id RETURNING * INTO m;
  action_name:='ambassador_milestone_updated';
 END IF;
 INSERT INTO public.admin_audit_logs(id,actor_id,actor_role,entity_type,entity_id,action,before_value,after_value) VALUES(p_request,a.id,a.role::text,'ambassador_milestone',m.id::text,action_name,CASE WHEN p_create THEN NULL ELSE to_jsonb(old_row) END,jsonb_build_object('request',intent,'milestone',to_jsonb(m)));
 RETURN jsonb_build_object('milestone',to_jsonb(m),'replayed',reused);
EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'HG_AMB_MILESTONE_CONFLICT';
END $$;
REVOKE ALL ON FUNCTION public.hg_write_ambassador_milestone(uuid,uuid,uuid,uuid,jsonb,timestamptz,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_write_ambassador_milestone(uuid,uuid,uuid,uuid,jsonb,timestamptz,boolean) TO service_role;
