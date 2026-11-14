-- Reuse the existing notification + durable dispatch tables. A committed
-- organizer action must not depend on a later HTTP/Python notification write.
CREATE OR REPLACE FUNCTION hg_internal.capture_organizer_notice(p_event uuid,p_kind text,p_version text,p_status text,p_copy jsonb)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE e public.events%rowtype;target public.profiles%rowtype;prefs public.notification_preferences%rowtype;channel_name text;ref uuid;notice_id uuid;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 IF nullif(p_copy->>'title','') IS NULL OR nullif(p_copy->>'body','') IS NULL THEN RETURN;END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event;
 ref:=md5('organizer:'||p_event||':'||p_kind||':'||coalesce(p_version,''))::uuid;
 FOR target IN SELECT * FROM public.profiles WHERE is_active AND
  CASE WHEN p_kind IN('event_review_submitted','event_payout_requested') THEN role::text='super_admin' OR (role::text='admin' AND campus_id=e.campus_id)
  ELSE id=e.organizer_id END LOOP
  SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=target.id;
  IF prefs.order_updates IS FALSE THEN CONTINUE;END IF;
  FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
   IF channel_name='push' AND (target.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
   notice_id:=md5(ref::text||':'||target.id||':'||channel_name)::uuid;
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
   VALUES(notice_id,target.id,p_kind,p_copy->>'title',replace(replace(p_copy->>'body','{title}',e.title),'{status}',p_status),channel_name,
    '/event-manager?event='||p_event,e.campus_id,ref,
    jsonb_build_object('_dispatch_version',1,'reference_type','event_organizer','organizer_event_id',p_event))
   ON CONFLICT(id) DO NOTHING;
  END LOOP;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION hg_internal.capture_organizer_notice(uuid,text,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.capture_organizer_notice(uuid,text,text,text,jsonb) TO service_role;

DO $migration$
DECLARE definition text; signature text;call text;
BEGIN
 FOREACH signature IN ARRAY ARRAY['public.hg_organizer_event_draft(uuid,uuid,text,jsonb)','public.hg_review_organizer_event(uuid,uuid,text,jsonb)','public.hg_event_payout_action(uuid,uuid,uuid,text,jsonb)'] LOOP
  definition:=pg_get_functiondef(signature::regprocedure);
  IF position(E'\nBEGIN' IN definition)=0 OR position('p_data jsonb' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected organizer function %',signature;END IF;
  definition:=regexp_replace(definition,E'\nBEGIN',E'\n notice_copy jsonb:=p_data->''_notice'';\nBEGIN\n p_data:=p_data-''_notice'';');
  IF signature LIKE '%hg_organizer_event_draft%' THEN
   call:='IF p_action=''submit'' THEN PERFORM hg_internal.capture_organizer_notice(p_event,''event_review_submitted'',(SELECT submitted_at::text FROM hg_internal.event_organizer_reviews WHERE event_id=p_event),e.review_status,notice_copy);END IF; ';
   definition:=replace(definition,'RETURN to_jsonb(e);',call||'RETURN to_jsonb(e);');
  ELSIF signature LIKE '%hg_review_organizer_event%' THEN
   -- A lost review response retried with identical notes is the same action.
   definition:=replace(definition,'IF p_action=''configure'' THEN',
    'IF (p_action=''approve'' AND e.review_status=''approved'' OR p_action=''changes_requested'' AND e.review_status=''changes_requested'') AND coalesce((SELECT review_notes FROM hg_internal.event_organizer_reviews WHERE event_id=p_event),'''')=coalesce(p_data->>''notes'','''') THEN RETURN to_jsonb(e);END IF; IF p_action=''configure'' THEN');
   call:='IF p_action IN(''approve'',''changes_requested'') THEN PERFORM hg_internal.capture_organizer_notice(p_event,''event_review_updated'',e.updated_at::text,e.review_status,notice_copy);END IF; ';
   definition:=replace(definition,'RETURN to_jsonb(e);',call||'RETURN to_jsonb(e);');
  ELSE
   call:='PERFORM hg_internal.capture_organizer_notice(p_event,CASE WHEN p_action=''request'' THEN ''event_payout_requested'' ELSE ''event_payout_updated'' END,r.id::text||'':''||r.state||'':''||r.updated_at::text,r.state,notice_copy); ';
   definition:=replace(definition,'RETURN to_jsonb(r);',call||'RETURN to_jsonb(r);');
  END IF;
  EXECUTE definition;
 END LOOP;
END $migration$;
