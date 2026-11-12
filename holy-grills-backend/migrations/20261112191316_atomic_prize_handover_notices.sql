-- Prize status, audit and inbox/push receipt commit together. No historical replay.
CREATE FUNCTION hg_internal.prize_handover_effects() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE actor_id uuid;actor public.profiles%rowtype;target public.profiles%rowtype;prefs public.notification_preferences%rowtype;
 changed boolean;before_data jsonb;after_data jsonb;label text;word text;body text;notice uuid;channel_name text;meta jsonb;
BEGIN
 IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME NOT IN ('leaderboard_reward_fulfillments','hall_of_fame_rewards','exclusive_spin_fulfillments') THEN RAISE EXCEPTION 'Invalid prize trigger';END IF;
 before_data:=to_jsonb(OLD);after_data:=to_jsonb(NEW);
 IF TG_TABLE_NAME='exclusive_spin_fulfillments' AND coalesce(after_data->'result_snapshot'->>'prize_type','physical')<>'physical' THEN RETURN NEW;END IF;
 changed:=NEW.status IS DISTINCT FROM OLD.status;
 IF NOT changed AND after_data->'notes' IS NOT DISTINCT FROM before_data->'notes' THEN
  IF TG_WHEN='BEFORE' THEN NEW.fulfilled_at:=OLD.fulfilled_at;NEW.fulfilled_by:=OLD.fulfilled_by;END IF;
  RETURN NEW;
 END IF;
 actor_id:=coalesce(auth.uid(),CASE WHEN NEW.status='fulfilled' THEN NEW.fulfilled_by END);
 SELECT * INTO actor FROM public.profiles WHERE id=actor_id AND is_active AND
  (role::text='super_admin' OR (role::text='admin' AND campus_id=NEW.campus_id));
 IF NOT FOUND THEN RAISE EXCEPTION 'Prize campus permission denied' USING ERRCODE='42501';END IF;
 IF TG_WHEN='BEFORE' THEN
  IF OLD.status IN ('fulfilled','cancelled') AND changed THEN RAISE EXCEPTION 'Prize already closed' USING ERRCODE='23514';END IF;
  IF NEW.status NOT IN ('pending','fulfilled','cancelled') AND NOT (TG_TABLE_NAME='hall_of_fame_rewards' AND NEW.status='box_prepared') THEN RAISE EXCEPTION 'Invalid prize status' USING ERRCODE='23514';END IF;
  IF NEW.status='fulfilled' AND OLD.status<>'fulfilled' THEN NEW.fulfilled_by:=actor.id;NEW.fulfilled_at:=now();
  ELSE NEW.fulfilled_by:=OLD.fulfilled_by;NEW.fulfilled_at:=OLD.fulfilled_at;END IF;
  RETURN NEW;
 END IF;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,before_value,after_value,campus_id)
 VALUES(actor.id,actor.role,TG_TABLE_NAME,NEW.id::text,'prize_'||CASE WHEN changed THEN NEW.status ELSE 'notes_updated' END,
  jsonb_build_object('status',OLD.status,'notes',before_data->'notes'),
  jsonb_build_object('status',NEW.status,'notes',after_data->'notes','fulfilled_by',NEW.fulfilled_by,'fulfilled_at',NEW.fulfilled_at),NEW.campus_id);
 IF NOT changed OR NEW.status='pending' THEN RETURN NEW;END IF;
 SELECT * INTO target FROM public.profiles WHERE id=NEW.user_id AND is_active;
 IF NOT FOUND THEN RETURN NEW;END IF;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=target.id;
 IF prefs.hp_updates IS FALSE THEN RETURN NEW;END IF;
 label:=CASE TG_TABLE_NAME WHEN 'hall_of_fame_rewards' THEN 'Hall of Fame box'
  WHEN 'leaderboard_reward_fulfillments' THEN '#'||(after_data->>'rank')||' leaderboard prize ('||(after_data->>'month')||')'
  ELSE coalesce(nullif(after_data->>'prize_name',''),'exclusive spin prize') END;
 word:=CASE WHEN NEW.status='box_prepared' THEN 'ready (box prepared)' ELSE NEW.status END;
 body:='Your '||label||' is now '||word||'.';
 FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
  IF channel_name='push' AND (target.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
  notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:prize-status:'||TG_TABLE_NAME||':'||NEW.id||':'||NEW.status||':'||target.id||':'||channel_name);
  meta:=jsonb_build_object('_dispatch_version',1,'reference_type',TG_TABLE_NAME,'reference_id',NEW.id,'prize_status',NEW.status);
  INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
  VALUES(notice,target.id,'prize_fulfilment_update','Update on your prize',body,channel_name,'/rewards',NEW.campus_id,NEW.id,meta) ON CONFLICT(id) DO NOTHING;
  IF channel_name='push' THEN
   INSERT INTO public.notification_deliveries(id,notification_id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
   VALUES(notice,notice,target.id,channel_name,'queued',NEW.campus_id,
    jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
    jsonb_build_object('notification',jsonb_build_object('user_id',target.id,'type','prize_fulfilment_update','title','Update on your prize','body',body,
     'action_url','/rewards','metadata',meta,'email',lower(trim(target.email::text)),'name',coalesce(nullif(target.nickname,''),nullif(target.full_name,''),'there')))) ON CONFLICT(id) DO NOTHING;
  END IF;
 END LOOP;
 RETURN NEW;
END$$;
REVOKE ALL ON FUNCTION hg_internal.prize_handover_effects() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.prize_handover_effects() TO service_role;
DO $$DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['leaderboard_reward_fulfillments','hall_of_fame_rewards','exclusive_spin_fulfillments'] LOOP
  EXECUTE format('CREATE TRIGGER prize_handover_guard BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION hg_internal.prize_handover_effects()',t);
  EXECUTE format('CREATE TRIGGER prize_handover_receipt AFTER UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION hg_internal.prize_handover_effects()',t);
 END LOOP;
END$$;

-- Save the episode identity so replenishment invalidates queued stale notices.
CREATE OR REPLACE FUNCTION hg_internal.capture_stock_low_notice() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE recipient public.profiles%rowtype;prefs public.notification_preferences%rowtype;channel_name text;notice uuid;body text;meta jsonb;episode uuid;
BEGIN
 IF NEW.archived_at IS NOT NULL OR NEW.current_balance>=NEW.low_stock_threshold THEN
  DELETE FROM hg_internal.stock_low_episodes WHERE stock_item_id=NEW.id;
  RETURN NULL;
 END IF;
 INSERT INTO hg_internal.stock_low_episodes(stock_item_id) VALUES(NEW.id) ON CONFLICT(stock_item_id) DO NOTHING RETURNING episode_id INTO episode;
 IF NOT FOUND THEN RETURN NULL;END IF;
 body:='Low stock alert: '''||NEW.name||''' balance ('||NEW.current_balance||') is below threshold ('||NEW.low_stock_threshold||').';
 FOR recipient IN SELECT * FROM public.profiles WHERE is_active AND (role::text='super_admin' OR (role::text='admin' AND campus_id=NEW.campus_id)) LOOP
  SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=recipient.id;
  FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
   IF channel_name='push' AND (recipient.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
   notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:stock-low:'||NEW.id||':'||episode||':'||recipient.id||':'||channel_name);
   meta:=jsonb_build_object('_dispatch_version',1,'reference_type','stock_item','reference_id',NEW.id,'stock_low_episode',episode,
    'template_data',jsonb_build_object('name',NEW.name,'balance',NEW.current_balance,'threshold',NEW.low_stock_threshold));
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
   VALUES(notice,recipient.id,'low_stock_ingredient','Low Stock Alert',body,channel_name,'/admin?section=store',NEW.campus_id,NEW.id,meta) ON CONFLICT(id) DO NOTHING;
   -- The normal INSERT trigger captures service-role calls. Authenticated
   -- metadata edits need the same private outbox receipt explicitly.
   IF channel_name='push' THEN
    INSERT INTO public.notification_deliveries(id,notification_id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
    VALUES(notice,notice,recipient.id,channel_name,'queued',NEW.campus_id,
     jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
     jsonb_build_object('notification',jsonb_build_object('user_id',recipient.id,'type','low_stock_ingredient','title','Low Stock Alert','body',body,
      'action_url','/admin?section=store','metadata',meta,'email',lower(trim(recipient.email::text)),'name',coalesce(nullif(recipient.nickname,''),nullif(recipient.full_name,''),'there')))) ON CONFLICT(id) DO NOTHING;
   END IF;
  END LOOP;
 END LOOP;
 RETURN NULL;
END$$;
CREATE FUNCTION public.hg_stock_low_notice_valid(p_notice uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.notifications n JOIN public.stock_items s ON s.id=n.reference_id JOIN public.profiles p ON p.id=n.user_id
  LEFT JOIN hg_internal.stock_low_episodes e ON e.stock_item_id=s.id WHERE n.id=p_notice AND n.type='low_stock_ingredient'
  AND s.archived_at IS NULL AND s.current_balance<s.low_stock_threshold AND p.is_active
  AND (p.role::text='super_admin' OR (p.role::text='admin' AND p.campus_id=s.campus_id))
  AND (NOT n.metadata ? 'stock_low_episode' OR n.metadata->>'stock_low_episode'=e.episode_id::text))
$$;
CREATE FUNCTION public.hg_prize_notice_valid(p_notice uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE n public.notifications%rowtype;record_owner uuid;record_status text;record_campus uuid;source_table text;
BEGIN
 SELECT * INTO n FROM public.notifications WHERE id=p_notice AND type='prize_fulfilment_update';
 IF NOT FOUND THEN RETURN false;END IF;
 source_table:=n.metadata->>'reference_type';
 IF source_table NOT IN ('leaderboard_reward_fulfillments','hall_of_fame_rewards','exclusive_spin_fulfillments') OR source_table IS NULL THEN RETURN false;END IF;
 EXECUTE format('SELECT user_id,status,campus_id FROM public.%I WHERE id=$1',source_table) INTO record_owner,record_status,record_campus USING n.reference_id;
 RETURN record_owner IS NOT DISTINCT FROM n.user_id AND record_status IS NOT DISTINCT FROM n.metadata->>'prize_status' AND record_campus IS NOT DISTINCT FROM n.campus_id;
END$$;
REVOKE ALL ON FUNCTION public.hg_stock_low_notice_valid(uuid),public.hg_prize_notice_valid(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_stock_low_notice_valid(uuid),public.hg_prize_notice_valid(uuid) TO service_role;
DO $$DECLARE definition text;needle text;BEGIN
 definition:=pg_get_functiondef('public.hg_begin_notification_dispatch(uuid,uuid,jsonb)'::regprocedure);
 needle:=' UPDATE public.notification_deliveries SET dispatch_payload=';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected dispatch function';END IF;
 definition:=replace(definition,needle,E' IF (d.dispatch_payload->''notification''->>''type''=''low_stock_ingredient'' AND NOT public.hg_stock_low_notice_valid(d.notification_id))\n'
  ||E' OR (d.dispatch_payload->''notification''->>''type''=''prize_fulfilment_update'' AND d.dispatch_payload->''notification''->''metadata'' ? ''prize_status'' AND NOT public.hg_prize_notice_valid(d.notification_id)) THEN\n'
  ||E'  UPDATE public.notification_deliveries SET status=''skipped'',last_error=''notice_no_longer_current'',dispatch=dispatch||jsonb_build_object(''state'',''skipped'') WHERE id=d.id;RETURN false;\n END IF;\n'||needle);
 EXECUTE definition;
END$$;
