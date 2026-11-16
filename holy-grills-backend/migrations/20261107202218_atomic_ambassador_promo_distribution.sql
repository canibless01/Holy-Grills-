-- Save the message and its recipient assignments together; retry the same intent.
CREATE OR REPLACE FUNCTION public.hg_create_ambassador_promo_atomic(
 p_actor_id uuid,p_message_id uuid,p_campus_id uuid,p_caption text,p_image_url text,
 p_month text,p_target_all boolean,p_ambassador_ids uuid[] DEFAULT '{}'::uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_actor public.profiles%ROWTYPE; v_scope uuid; v_existing public.ambassador_promo_messages%ROWTYPE;
 v_message public.ambassador_promo_messages%ROWTYPE; v_targets uuid[]; v_requested uuid[]; v_replay boolean:=false;
BEGIN
 SELECT * INTO v_actor FROM public.profiles WHERE id=p_actor_id AND is_active;
 IF NOT FOUND OR v_actor.role::text NOT IN ('admin','super_admin','community_manager') THEN
   RETURN jsonb_build_object('error','promo_forbidden'); END IF;
 IF v_actor.role::text='super_admin' THEN v_scope:=p_campus_id;
 ELSE
   v_scope:=v_actor.campus_id;
   IF v_scope IS NULL OR (p_campus_id IS NOT NULL AND p_campus_id<>v_scope) THEN
     RETURN jsonb_build_object('error','promo_forbidden'); END IF;
 END IF;
 IF v_scope IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=v_scope AND is_active) THEN
   RETURN jsonb_build_object('error','promo_scope_invalid'); END IF;
 IF p_message_id IS NULL OR p_target_all IS NULL OR p_caption IS NULL OR length(btrim(p_caption))=0
    OR p_month IS NULL OR p_month !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
    OR (position('{{link}}' in p_caption)=0 AND position('{link}' in p_caption)=0 AND position('{{LINK}}' in p_caption)=0) THEN
   RETURN jsonb_build_object('error','promo_invalid'); END IF;
 SELECT coalesce(array_agg(DISTINCT id ORDER BY id),'{}'::uuid[]) INTO v_requested FROM unnest(coalesce(p_ambassador_ids,'{}')) id;
 IF array_position(v_requested,NULL) IS NOT NULL THEN RETURN jsonb_build_object('error','promo_invalid'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('hg-amb-promo:'||p_message_id::text,0));
 SELECT * INTO v_existing FROM public.ambassador_promo_messages WHERE id=p_message_id;
 IF FOUND THEN
   IF v_existing.created_by<>p_actor_id OR v_existing.campus_id IS DISTINCT FROM v_scope
      OR v_existing.caption IS DISTINCT FROM p_caption OR v_existing.image_url IS DISTINCT FROM p_image_url
      OR v_existing.month IS DISTINCT FROM p_month OR v_existing.target_all IS DISTINCT FROM p_target_all THEN
     RETURN jsonb_build_object('error','promo_intent_conflict'); END IF;
   SELECT coalesce(array_agg(ambassador_id ORDER BY ambassador_id),'{}'::uuid[]) INTO v_targets
    FROM public.ambassador_promo_assignments WHERE message_id=p_message_id;
   IF NOT p_target_all AND v_requested IS DISTINCT FROM v_targets THEN
     RETURN jsonb_build_object('error','promo_intent_conflict'); END IF;
   v_message:=v_existing; v_replay:=true;
 ELSE
   SELECT coalesce(array_agg(a.profile_id ORDER BY a.profile_id),'{}'::uuid[]) INTO v_targets
   FROM public.ambassadors a JOIN public.profiles p ON p.id=a.profile_id
   WHERE a.status='active' AND p.is_active AND p.campus_id IS NOT DISTINCT FROM a.campus_id
     AND (v_scope IS NULL OR a.campus_id=v_scope)
     AND (p_target_all OR a.profile_id=ANY(v_requested));
   IF cardinality(v_targets)=0 OR (NOT p_target_all AND v_requested IS DISTINCT FROM v_targets) THEN
     RETURN jsonb_build_object('error','promo_no_targets'); END IF;
   INSERT INTO public.ambassador_promo_messages(id,created_by,campus_id,image_url,caption,target_all,month)
    VALUES(p_message_id,p_actor_id,v_scope,p_image_url,p_caption,p_target_all,p_month) RETURNING * INTO v_message;
   INSERT INTO public.ambassador_promo_assignments(message_id,ambassador_id,month,status)
    SELECT p_message_id,id,p_month,'pending' FROM unnest(v_targets) id;
 END IF;
 RETURN jsonb_build_object('message',to_jsonb(v_message),'recipient_count',cardinality(v_targets),
                          'ambassador_ids',to_jsonb(v_targets),'idempotent',v_replay);
END $$;
REVOKE ALL ON FUNCTION public.hg_create_ambassador_promo_atomic(uuid,uuid,uuid,text,text,text,boolean,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_create_ambassador_promo_atomic(uuid,uuid,uuid,text,text,text,boolean,uuid[]) TO service_role;
