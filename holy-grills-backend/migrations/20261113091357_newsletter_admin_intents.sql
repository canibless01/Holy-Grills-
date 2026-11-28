-- Existing campaign IDs are the durable create intent. No extra table/column.
CREATE OR REPLACE FUNCTION public.hg_queue_newsletter_campaign(p_actor uuid,p_request uuid,p_campus uuid,p_subject text,p_body text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;c public.newsletter_campaigns%rowtype;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_NEWSLETTER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('admin','super_admin') FOR SHARE;
 IF NOT FOUND OR (a.role::text<>'super_admin' AND (p_campus IS NULL OR p_campus IS DISTINCT FROM a.campus_id)) THEN RAISE EXCEPTION 'HG_NEWSLETTER_ACCESS' USING ERRCODE='42501';END IF;
 IF p_request IS NULL OR length(btrim(coalesce(p_subject,''))) NOT BETWEEN 1 AND 200 OR length(btrim(coalesce(p_body,''))) NOT BETWEEN 1 AND 20000 THEN RAISE EXCEPTION 'HG_NEWSLETTER_INVALID';END IF;
 IF p_campus IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=p_campus AND is_active) THEN RAISE EXCEPTION 'HG_NEWSLETTER_INVALID';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('newsletter:'||coalesce(p_campus::text,'global')||':'||p_subject||':'||p_body,0));
 SELECT * INTO c FROM public.newsletter_campaigns WHERE id=p_request;
 IF FOUND THEN
  IF c.created_by IS DISTINCT FROM p_actor OR c.campus_id IS DISTINCT FROM p_campus OR c.subject IS DISTINCT FROM p_subject OR c.body IS DISTINCT FROM p_body THEN RAISE EXCEPTION 'HG_NEWSLETTER_CONFLICT';END IF;
  RETURN jsonb_build_object('campaign',to_jsonb(c),'replayed',true);
 END IF;
 IF EXISTS(SELECT 1 FROM public.newsletter_campaigns WHERE campus_id IS NOT DISTINCT FROM p_campus AND subject=p_subject AND body=p_body AND created_at>now()-interval '10 minutes') THEN RAISE EXCEPTION 'HG_NEWSLETTER_DUPLICATE';END IF;
 INSERT INTO public.newsletter_campaigns(id,campus_id,subject,body,status,created_by) VALUES(p_request,p_campus,p_subject,p_body,'queued',p_actor) RETURNING * INTO c;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value) VALUES(a.id,a.role::text,'newsletter_campaign',c.id::text,'newsletter_queued',jsonb_build_object('campus_id',p_campus,'subject',p_subject));
 RETURN jsonb_build_object('campaign',to_jsonb(c),'replayed',false);
EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'HG_NEWSLETTER_CONFLICT';
END $$;
CREATE OR REPLACE FUNCTION public.hg_cancel_newsletter_campaign(p_actor uuid,p_campaign uuid,p_scope uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;c public.newsletter_campaigns%rowtype;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_NEWSLETTER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('admin','super_admin') FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_NEWSLETTER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO c FROM public.newsletter_campaigns WHERE id=p_campaign FOR UPDATE;
 IF NOT FOUND OR (a.role::text<>'super_admin' AND (c.campus_id IS NULL OR c.campus_id IS DISTINCT FROM a.campus_id)) OR (p_scope IS NOT NULL AND c.campus_id IS DISTINCT FROM p_scope) THEN RAISE EXCEPTION 'HG_NEWSLETTER_ACCESS' USING ERRCODE='42501';END IF;
 IF c.status='cancelled' THEN RETURN jsonb_build_object('campaign',to_jsonb(c),'replayed',true);END IF;
 IF c.status NOT IN('queued','sending') THEN RAISE EXCEPTION 'HG_NEWSLETTER_TERMINAL';END IF;
 UPDATE public.newsletter_campaigns SET status='cancelled',completed_at=now() WHERE id=c.id RETURNING * INTO c;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value) VALUES(a.id,a.role::text,'newsletter_campaign',c.id::text,'newsletter_cancelled',jsonb_build_object('status','cancelled'));
 RETURN jsonb_build_object('campaign',to_jsonb(c),'replayed',false);
END $$;
REVOKE ALL ON FUNCTION public.hg_queue_newsletter_campaign(uuid,uuid,uuid,text,text),public.hg_cancel_newsletter_campaign(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_queue_newsletter_campaign(uuid,uuid,uuid,text,text),public.hg_cancel_newsletter_campaign(uuid,uuid,uuid) TO service_role;
