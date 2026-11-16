-- Capture the existing in-app + push channels in the financial transaction.
-- The existing notification trigger/outbox handles process loss and dispatch.
CREATE OR REPLACE FUNCTION hg_internal.capture_ambassador_grant_notice(p_grant uuid)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE reward public.ambassador_grants%rowtype; target public.profiles%rowtype;
 prefs public.notification_preferences%rowtype; channel_name text; notice_id uuid;
BEGIN
 IF coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'role','')<>'service_role' THEN RAISE EXCEPTION 'ambassador_forbidden' USING ERRCODE='42501'; END IF;
 SELECT * INTO reward FROM public.ambassador_grants WHERE id=p_grant;
 IF NOT FOUND OR reward.status<>'issued' THEN RETURN; END IF;
 SELECT * INTO target FROM public.profiles WHERE id=reward.ambassador_id AND is_active;
 IF NOT FOUND THEN RETURN; END IF;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=target.id;
 IF prefs.hp_updates IS FALSE THEN RETURN; END IF;
 FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
  IF channel_name='push' AND (target.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE; END IF;
  -- Adopt historical random-ID notices; never resend them on a grant retry.
  IF EXISTS(SELECT 1 FROM public.notifications WHERE user_id=target.id AND type='ambassador_grant_issued'
    AND reference_id=reward.id AND channel=channel_name) THEN CONTINUE; END IF;
  -- Same UUIDv5 identity as notification_service.send_notification.
  notice_id:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8',
    'holy-grills:request-notification:'||target.id||':ambassador_grant_issued:ambassador_grant:'||reward.id||':'||channel_name);
  INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
  VALUES(notice_id,target.id,'ambassador_grant_issued','Ambassador reward approved',
    'Your '||replace(reward.reward_category,'_',' ')||' reward for '||reward.month||' has been issued.',channel_name,
    '/rewards',target.campus_id,reward.id,jsonb_build_object('_dispatch_version',1,'reference_type','ambassador_grant','reference_id',reward.id))
  ON CONFLICT(id) DO NOTHING;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION hg_internal.capture_ambassador_grant_notice(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.capture_ambassador_grant_notice(uuid) TO service_role;

DO $migration$
DECLARE definition text; needle text; replacement text;
BEGIN
 definition:=pg_get_functiondef('public.hg_issue_ambassador_grant_atomic(uuid,uuid,text,numeric,text,text,integer,integer,text,uuid,boolean,text)'::regprocedure);
 IF position('capture_ambassador_grant_notice' IN definition)>0 THEN RAISE EXCEPTION 'Ambassador grant function already changed'; END IF;
 needle:=E' hp jsonb; credit jsonb;';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected ambassador grant declaration'; END IF;
 definition:=replace(definition,needle,needle||E'\n claim_row public.ambassador_milestone_claims%rowtype;');
 needle:=' IF NOT p_override AND EXISTS';
 replacement:=E' IF p_claim_id IS NOT NULL THEN\n'
  ||E'  SELECT * INTO claim_row FROM public.ambassador_milestone_claims WHERE id=p_claim_id FOR UPDATE;\n'
  ||E'  IF NOT FOUND OR claim_row.ambassador_id IS DISTINCT FROM p_ambassador_id OR claim_row.period_month IS DISTINCT FROM p_month THEN RAISE EXCEPTION ''ambassador_claim_invalid''; END IF;\n'
  ||E'  IF claim_row.grant_id IS NOT NULL OR claim_row.status=''issued'' THEN RAISE EXCEPTION ''ambassador_claim_already_issued''; END IF;\n'
  ||E'  IF claim_row.status=''rejected'' THEN RAISE EXCEPTION ''ambassador_claim_rejected''; END IF;\n'
  ||E' END IF;\n';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected ambassador grant duplicate guard'; END IF;
 definition:=replace(definition,needle,replacement||needle);
 needle:='RETURN to_jsonb(grant_row)||jsonb_build_object(''idempotent'',true);';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected ambassador grant replay return'; END IF;
 definition:=replace(definition,needle,'PERFORM hg_internal.capture_ambassador_grant_notice(grant_row.id); '||needle);
 needle:='RETURN to_jsonb(grant_row)||jsonb_build_object(''idempotent'',false);';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected ambassador grant success return'; END IF;
 definition:=replace(definition,needle,'PERFORM hg_internal.capture_ambassador_grant_notice(grant_row.id); '||needle);
 EXECUTE definition;
END $migration$;
