-- Additive ambassador management. Preserve deleted messages, assignments and create receipts.
ALTER TABLE public.ambassador_promo_messages
 ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1,
 ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
 ADD COLUMN IF NOT EXISTS creation_fingerprint text;
ALTER TABLE public.ambassadors ADD COLUMN IF NOT EXISTS whatsapp_phone text;
CREATE UNIQUE INDEX IF NOT EXISTS ambassador_promo_creation_receipt
 ON public.ambassador_promo_messages((coalesce(campus_id::text,'global')),creation_fingerprint)
 WHERE creation_fingerprint IS NOT NULL;
CREATE TABLE IF NOT EXISTS public.ambassador_promo_history(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), message_id uuid NOT NULL REFERENCES public.ambassador_promo_messages(id),
 actor_id uuid NOT NULL REFERENCES public.profiles(id), action text NOT NULL CHECK(action IN ('edit','delete')),
 before_value jsonb NOT NULL, after_value jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ambassador_promo_history_message ON public.ambassador_promo_history(message_id,created_at);
CREATE INDEX IF NOT EXISTS ambassador_promo_history_actor ON public.ambassador_promo_history(actor_id);
ALTER TABLE public.ambassador_promo_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ambassador_promo_history FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON public.ambassador_promo_history TO service_role;
-- Save the message and its recipient assignments together; retry the same intent.
CREATE OR REPLACE FUNCTION public.hg_create_ambassador_promo_atomic(
 p_actor_id uuid,p_message_id uuid,p_campus_id uuid,p_caption text,p_image_url text,
 p_month text,p_target_all boolean,p_ambassador_ids uuid[] DEFAULT '{}'::uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_actor public.profiles%ROWTYPE; v_scope uuid; v_existing public.ambassador_promo_messages%ROWTYPE;
 v_fingerprint text; v_message public.ambassador_promo_messages%ROWTYPE; v_targets uuid[]; v_requested uuid[]; v_replay boolean:=false;
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
 IF p_target_all THEN v_requested:='{}'::uuid[]; END IF;
 IF p_image_url IS NOT NULL AND p_image_url !~ '^https://res[.]cloudinary[.]com/[^[:space:]]+$' THEN RETURN jsonb_build_object('error','promo_invalid'); END IF;
 v_fingerprint:=encode(sha256(convert_to(jsonb_build_object('caption',p_caption,'image',p_image_url,'month',p_month,'all',p_target_all,'targets',v_requested)::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('hg-amb-promo-fingerprint:'||coalesce(v_scope::text,'global')||':'||v_fingerprint,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('hg-amb-promo:'||p_message_id::text,0));
 SELECT * INTO v_existing FROM public.ambassador_promo_messages WHERE id=p_message_id;
 IF FOUND THEN
   IF v_existing.deleted_at IS NOT NULL THEN RETURN jsonb_build_object('error','promo_deleted'); END IF;
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
   SELECT * INTO v_existing FROM public.ambassador_promo_messages
     WHERE campus_id IS NOT DISTINCT FROM v_scope AND creation_fingerprint=v_fingerprint;
   IF FOUND THEN
     IF v_existing.deleted_at IS NOT NULL THEN RETURN jsonb_build_object('error','promo_deleted'); END IF;
     RETURN jsonb_build_object('message',to_jsonb(v_existing),'recipient_count',(SELECT count(*) FROM public.ambassador_promo_assignments WHERE message_id=v_existing.id),'idempotent',true);
   END IF;
   SELECT coalesce(array_agg(a.profile_id ORDER BY a.profile_id),'{}'::uuid[]) INTO v_targets
   FROM public.ambassadors a JOIN public.profiles p ON p.id=a.profile_id
   WHERE a.status='active' AND p.is_active AND p.campus_id IS NOT DISTINCT FROM a.campus_id
     AND (v_scope IS NULL OR a.campus_id=v_scope)
     AND (p_target_all OR a.profile_id=ANY(v_requested));
   IF cardinality(v_targets)=0 OR (NOT p_target_all AND v_requested IS DISTINCT FROM v_targets) THEN
     RETURN jsonb_build_object('error','promo_no_targets'); END IF;
   INSERT INTO public.ambassador_promo_messages(id,created_by,campus_id,image_url,caption,target_all,month,creation_fingerprint)
    VALUES(p_message_id,p_actor_id,v_scope,p_image_url,p_caption,p_target_all,p_month,v_fingerprint) RETURNING * INTO v_message;
   INSERT INTO public.ambassador_promo_assignments(message_id,ambassador_id,month,status)
    SELECT p_message_id,id,p_month,'pending' FROM unnest(v_targets) id;
 END IF;
 RETURN jsonb_build_object('message',to_jsonb(v_message),'recipient_count',cardinality(v_targets),
                          'ambassador_ids',to_jsonb(v_targets),'idempotent',v_replay);
END $$;
REVOKE ALL ON FUNCTION public.hg_create_ambassador_promo_atomic(uuid,uuid,uuid,text,text,text,boolean,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_create_ambassador_promo_atomic(uuid,uuid,uuid,text,text,text,boolean,uuid[]) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_manage_ambassador_promo(p_actor uuid,p_id uuid,p_revision integer,p_action text,p_values jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE; old public.ambassador_promo_messages%ROWTYPE; saved public.ambassador_promo_messages%ROWTYPE;
 v_caption text; v_image text;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin','community_manager') THEN RETURN jsonb_build_object('error','promo_forbidden'); END IF;
 SELECT * INTO old FROM ambassador_promo_messages WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','promo_not_found'); END IF;
 IF actor.role::text<>'super_admin' AND (actor.campus_id IS NULL OR old.campus_id IS DISTINCT FROM actor.campus_id) THEN RETURN jsonb_build_object('error','promo_forbidden'); END IF;
 IF p_action NOT IN ('edit','delete') THEN RETURN jsonb_build_object('error','promo_invalid'); END IF;
 IF old.deleted_at IS NOT NULL THEN
   IF p_action='delete' THEN RETURN jsonb_build_object('message',to_jsonb(old),'idempotent',true); END IF;
   RETURN jsonb_build_object('error','promo_deleted'); END IF;
 IF p_revision IS NULL OR p_revision<>old.revision THEN RETURN jsonb_build_object('error','promo_stale'); END IF;
 v_caption:=CASE WHEN p_values ? 'caption' THEN btrim(p_values->>'caption') ELSE old.caption END;
 v_image:=CASE WHEN p_values ? 'image_url' THEN nullif(p_values->>'image_url','') ELSE old.image_url END;
 IF p_action='edit' AND (v_caption IS NULL OR length(v_caption)=0 OR length(v_caption)>10000
  OR (position('{{link}}' in v_caption)=0 AND position('{link}' in v_caption)=0 AND position('{{LINK}}' in v_caption)=0)
  OR (v_image IS NOT NULL AND v_image !~ '^https://res[.]cloudinary[.]com/[^[:space:]]+$')) THEN RETURN jsonb_build_object('error','promo_invalid'); END IF;
 UPDATE ambassador_promo_messages SET caption=v_caption, image_url=v_image,
   deleted_at=CASE WHEN p_action='delete' THEN now() ELSE NULL END, revision=revision+1,updated_at=now()
   WHERE id=p_id RETURNING * INTO saved;
 INSERT INTO ambassador_promo_history(message_id,actor_id,action,before_value,after_value) VALUES(p_id,p_actor,p_action,to_jsonb(old),to_jsonb(saved));
 RETURN jsonb_build_object('message',to_jsonb(saved),'idempotent',false);
END $$;
REVOKE ALL ON FUNCTION public.hg_manage_ambassador_promo(uuid,uuid,integer,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_manage_ambassador_promo(uuid,uuid,integer,text,jsonb) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_set_ambassador_whatsapp(p_actor uuid,p_ambassador uuid,p_phone text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE; target public.ambassadors%ROWTYPE;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin','community_manager') THEN RETURN jsonb_build_object('error','promo_forbidden'); END IF;
 SELECT * INTO target FROM ambassadors WHERE profile_id=p_ambassador AND status='active' FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','promo_not_found'); END IF;
 IF actor.role::text<>'super_admin' AND (actor.campus_id IS NULL OR target.campus_id IS DISTINCT FROM actor.campus_id) THEN RETURN jsonb_build_object('error','promo_forbidden'); END IF;
 IF p_phone IS NOT NULL AND p_phone !~ '^[+][1-9][0-9]{7,14}$' THEN RETURN jsonb_build_object('error','promo_invalid'); END IF;
 UPDATE ambassadors SET whatsapp_phone=p_phone,updated_at=now() WHERE profile_id=p_ambassador;
 RETURN jsonb_build_object('ambassador_id',p_ambassador,'whatsapp_phone',p_phone);
END $$;
REVOKE ALL ON FUNCTION public.hg_set_ambassador_whatsapp(uuid,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_set_ambassador_whatsapp(uuid,uuid,text) TO service_role;
