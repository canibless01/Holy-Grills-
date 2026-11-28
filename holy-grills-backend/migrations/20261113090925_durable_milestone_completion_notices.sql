CREATE FUNCTION hg_internal.capture_milestone_completion_notice() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE person public.profiles%rowtype;m public.milestones%rowtype;prefs public.notification_preferences%rowtype;hp integer;title text;body text;channel_name text;notice uuid;meta jsonb;ledger_count integer;
BEGIN
 IF NEW.reward_receipt IS NULL OR NEW.reward_receipt IS NOT DISTINCT FROM OLD.reward_receipt OR NEW.reward_receipt->>'completed'<>'true' THEN RETURN NEW;END IF;
 IF NEW.reward_receipt->>'completion_id' IS DISTINCT FROM NEW.id::text THEN RAISE EXCEPTION 'Milestone receipt identity mismatch';END IF;
 hp:=(NEW.reward_receipt->>'recorded_hp_awarded')::integer;
 IF hp IS NULL OR hp<0 THEN RAISE EXCEPTION 'Milestone receipt amount invalid';END IF;
 SELECT * INTO person FROM public.profiles WHERE id=NEW.user_id AND is_active;
 SELECT * INTO m FROM public.milestones WHERE id=NEW.milestone_id;
 IF person.id IS NULL OR person.campus_id IS DISTINCT FROM NEW.campus_id OR m.id IS NULL THEN RAISE EXCEPTION 'Milestone receipt scope invalid';END IF;
 IF hp>0 THEN
  SELECT count(*) INTO ledger_count FROM public.hp_transactions WHERE user_id=NEW.user_id AND reference_id=NEW.id AND reference_type IN ('milestone','challenge') AND type='earn' AND amount=hp AND campus_id IS NOT DISTINCT FROM NEW.campus_id;
  IF ledger_count<>1 THEN RAISE EXCEPTION 'Milestone receipt ledger needs review';END IF;
 END IF;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=person.id;
 IF prefs.hp_updates IS FALSE THEN RETURN NEW;END IF;
 title:=CASE WHEN m.time_window IS NULL THEN 'Milestone completed!' ELSE 'Challenge completed!' END;
 body:=m.title||CASE WHEN hp=0 THEN '' WHEN NEW.reward_receipt->>'hp_destination'='pending' THEN ' — '||hp||' HP added to pending.' ELSE ' — '||hp||' HP earned!' END;
 meta:=jsonb_build_object('_dispatch_version',1,'reference_type','milestone_completion','reference_id',NEW.id,'hp_awarded',hp,'hp_destination',NEW.reward_receipt->>'hp_destination');
 FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
  IF channel_name='push' AND (person.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
  notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:request-notification:'||NEW.user_id||':milestone_achieved:milestone_completion:'||NEW.id||':'||channel_name);
  INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
  VALUES(notice,person.id,'milestone_achieved',title,body,channel_name,'/rewards',person.campus_id,NEW.id,meta) ON CONFLICT(id) DO NOTHING;
 END LOOP;
 RETURN NEW;
END$$;
REVOKE ALL ON FUNCTION hg_internal.capture_milestone_completion_notice() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.capture_milestone_completion_notice() TO service_role;
CREATE TRIGGER capture_milestone_completion_notice AFTER UPDATE OF reward_receipt ON public.user_milestones FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_milestone_completion_notice();
-- Challenge periods and their pending-HP monthly counter use the same WAT month.
DO $$DECLARE definition text;needle text:='now() AT TIME ZONE ''UTC''';BEGIN
 definition:=pg_get_functiondef('public.hg_complete_pending_milestone(uuid,uuid,text,integer)'::regprocedure);
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected pending milestone month definition';END IF;
 EXECUTE replace(definition,needle,'now() AT TIME ZONE ''Africa/Lagos''');
END$$;
