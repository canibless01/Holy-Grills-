-- Save recovery receipts within the existing attendance transaction. No new job.
CREATE FUNCTION hg_internal.capture_checkin_reclaim_notice(p_user uuid,p_reference uuid,p_day date,p_source text) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE recipient public.profiles%rowtype;prefs public.notification_preferences%rowtype;channel_name text;notice uuid;body text;meta jsonb;
BEGIN
 SELECT * INTO recipient FROM public.profiles WHERE id=p_user AND is_active;
 IF NOT FOUND THEN RETURN;END IF;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=p_user;
 IF prefs.hp_updates IS FALSE THEN RETURN;END IF;
 body:='Your '||CASE p_source WHEN 'wallet_topup' THEN 'wallet top-up' ELSE 'order' END||' recovered your check-in for '||to_char(p_day,'FMDD Mon YYYY')||'. Check your weekly progress.';
 meta:=jsonb_build_object('_dispatch_version',1,'reference_type','streak_reclaim','reference_id',p_reference,'source_date',p_day,'source_type',p_source);
 FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
  IF channel_name='push' AND (recipient.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
  -- Same key as the former Python path: replay must not duplicate old notices.
  notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:request-notification:'||p_user||':checkin_reclaimed:streak_reclaim:'||p_reference||':'||channel_name);
  INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
  VALUES(notice,p_user,'checkin_reclaimed','Missed Day Recovered ✅',body,channel_name,'/streak',recipient.campus_id,p_reference,meta) ON CONFLICT(id) DO NOTHING;
 END LOOP;
END$$;
REVOKE ALL ON FUNCTION hg_internal.capture_checkin_reclaim_notice(uuid,uuid,date,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.capture_checkin_reclaim_notice(uuid,uuid,date,text) TO service_role;
DO $$DECLARE definition text;old_branch text;new_branch text;BEGIN
 definition:=pg_get_functiondef('public.hg_reclaim_login_checkin(uuid,text,uuid,numeric)'::regprocedure);
 old_branch:=' IF coalesce(s.week_state,''{}'') ? day_key THEN';
 new_branch:=' RETURN jsonb_build_object(''reclaimed'',true,''already_reclaimed'',false,';
 IF position(old_branch IN definition)=0 OR position(new_branch IN definition)=0 THEN RAISE EXCEPTION 'Unexpected checkin reclaim definition';END IF;
 definition:=replace(definition,old_branch,old_branch||E'\n  IF prior=''reclaimed'' THEN PERFORM hg_internal.capture_checkin_reclaim_notice(p_user_id,ref,source_day,p_source_type);END IF;');
 definition:=replace(definition,new_branch,E' PERFORM hg_internal.capture_checkin_reclaim_notice(p_user_id,ref,source_day,p_source_type);\n'||new_branch);
 EXECUTE definition;
END$$;
