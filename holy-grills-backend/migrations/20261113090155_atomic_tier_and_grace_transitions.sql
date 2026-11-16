CREATE FUNCTION public.hg_recalculate_tier_atomic(p_user uuid,p_mode text DEFAULT 'upgrade',p_grace_days integer DEFAULT 7) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE person public.profiles%rowtype;current_tier public.hp_tiers%rowtype;candidate public.hp_tiers%rowtype;scope uuid;
 event text;kind text;title text;body text;history uuid;prefs public.notification_preferences%rowtype;channel_name text;notice uuid;meta jsonb;
BEGIN
 IF p_mode NOT IN ('upgrade','grace') OR p_mode IS NULL OR p_grace_days IS NULL OR p_grace_days<1 OR p_grace_days>90 THEN RAISE EXCEPTION 'Invalid tier transition arguments';END IF;
 SELECT * INTO person FROM public.profiles WHERE id=p_user FOR UPDATE;
 IF person.id IS NULL OR person.is_active IS NOT TRUE OR person.role::text<>'student' OR person.campus_id IS NULL OR coalesce(person.is_fraud_flagged,false)
 OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=person.campus_id AND is_active) THEN RETURN jsonb_build_object('changed',false,'tier',NULL,'reason','excluded');END IF;
 scope:=CASE WHEN EXISTS(SELECT 1 FROM public.hp_tiers WHERE campus_id=person.campus_id) THEN person.campus_id ELSE NULL END;
 SELECT * INTO candidate FROM public.hp_tiers WHERE is_active AND campus_id IS NOT DISTINCT FROM scope AND min_points<=coalesce(person.hp_earned_120day,0)
 ORDER BY min_points DESC,sort_order DESC,id LIMIT 1;
 IF candidate.id IS NULL THEN RETURN jsonb_build_object('changed',false,'tier',NULL,'reason','no_eligible_active_tier');END IF;
 SELECT * INTO current_tier FROM public.hp_tiers WHERE id=person.current_tier_id;
 IF current_tier.id IS NOT NULL AND (current_tier.campus_id IS NOT NULL AND current_tier.campus_id<>person.campus_id) THEN RAISE EXCEPTION 'Current tier belongs to another campus';END IF;
 IF person.current_tier_id IS NULL OR (candidate.id<>person.current_tier_id AND candidate.min_points>coalesce(current_tier.min_points,-1)) THEN
  event:='upgrade';kind:='tier_upgrade';title:='Your Holy Grills tier has grown';body:='You have reached '||candidate.name||'. Open Rewards to see your tier perks.';
 ELSIF p_mode='upgrade' THEN
  RETURN jsonb_build_object('changed',false,'tier',to_jsonb(current_tier),'event',CASE WHEN candidate.id<>person.current_tier_id THEN 'downgrade_deferred_to_grace_job' ELSE 'unchanged' END);
 ELSIF current_tier.id IS NULL OR current_tier.is_active IS NOT TRUE THEN
  RAISE EXCEPTION 'Current tier configuration needs review';
 ELSIF coalesce(person.hp_earned_120day,0)>=current_tier.maintenance_points OR current_tier.maintenance_points=0 THEN
  IF person.tier_grace_ends_at IS NOT NULL OR person.tier_grace_started_at IS NOT NULL THEN
   UPDATE public.profiles SET tier_grace_started_at=NULL,tier_grace_ends_at=NULL WHERE id=p_user;
   INSERT INTO public.user_tiers(user_id,tier_id,previous_tier_id,event,hp_at_event,campus_id) VALUES(p_user,current_tier.id,current_tier.id,'maintain',person.hp_earned_120day,person.campus_id);
  END IF;
  RETURN jsonb_build_object('changed',false,'tier',to_jsonb(current_tier),'event','maintained');
 ELSIF person.tier_grace_ends_at IS NULL THEN
  event:='grace';kind:='tier_grace_period';title:='Time to keep your tier';
  body:='Your '||current_tier.name||' tier has a '||p_grace_days||'-day grace period. Earn enough eligible HP to reach its maintenance target of '||current_tier.maintenance_points||' HP.';
  candidate:=current_tier;
 ELSIF person.tier_grace_ends_at>now() THEN
  RETURN jsonb_build_object('changed',false,'tier',to_jsonb(current_tier),'event','grace_pending');
 ELSIF candidate.id=current_tier.id OR candidate.min_points>=current_tier.min_points THEN
  RAISE EXCEPTION 'Tier maintenance and entry thresholds need review';
 ELSE
  event:='downgrade';kind:='tier_downgrade';title:='Your Holy Grills tier has changed';body:='Your tier changed from '||current_tier.name||' to '||candidate.name||' after the grace period. You can build it back through eligible HP.';
 END IF;
 IF event='grace' THEN
  UPDATE public.profiles SET tier_grace_started_at=now(),tier_grace_ends_at=now()+make_interval(days=>p_grace_days) WHERE id=p_user;
 ELSE
  UPDATE public.profiles SET current_tier_id=candidate.id,tier_grace_started_at=NULL,tier_grace_ends_at=NULL WHERE id=p_user;
 END IF;
 INSERT INTO public.user_tiers(user_id,tier_id,previous_tier_id,event,hp_at_event,campus_id)
 VALUES(p_user,candidate.id,person.current_tier_id,event,coalesce(person.hp_earned_120day,0),person.campus_id) RETURNING id INTO history;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=p_user;
 -- Assigning the initial base tier is quiet, matching signup's normal behavior.
 IF prefs.hp_updates IS DISTINCT FROM false AND NOT (person.current_tier_id IS NULL AND candidate.min_points=0) THEN
  meta:=jsonb_build_object('_dispatch_version',1,'reference_type','tier_transition','reference_id',history,'tier_id',candidate.id);
  FOREACH channel_name IN ARRAY ARRAY['in_app','push','email'] LOOP
   IF channel_name='push' AND (person.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
   IF channel_name='email' AND (person.email_notifications IS FALSE OR prefs.email_enabled IS FALSE OR coalesce(person.email::text,'')='') THEN CONTINUE;END IF;
   notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:tier-transition:'||history||':'||channel_name);
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
   VALUES(notice,p_user,kind,title,body,channel_name,'/rewards',person.campus_id,history,meta) ON CONFLICT(id) DO NOTHING;
  END LOOP;
 END IF;
 RETURN jsonb_build_object('changed',event<>'grace','tier',to_jsonb(candidate),'previous_tier_id',person.current_tier_id,'event',event,'reference_id',history);
END$$;
CREATE FUNCTION public.hg_tier_maintenance_batch(p_campus uuid,p_mode text,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 200,p_grace_days integer DEFAULT 7) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE person record;last_id uuid;counted integer:=0;errors integer:=0;r jsonb;started integer:=0;dropped integer:=0;earned bigint;
BEGIN
 IF p_mode NOT IN ('refresh','grace') OR p_mode IS NULL OR p_campus IS NULL OR p_limit IS NULL OR p_limit<1 OR p_limit>200 THEN RAISE EXCEPTION 'Invalid tier batch';END IF;
 FOR person IN SELECT id FROM public.profiles WHERE campus_id=p_campus AND is_active AND role::text='student' AND (p_after IS NULL OR id>p_after) ORDER BY id LIMIT p_limit LOOP
  counted:=counted+1;last_id:=person.id;
  BEGIN
   -- Lock before the ledger snapshot, matching all active HP mutations.
   PERFORM 1 FROM public.profiles WHERE id=person.id FOR UPDATE;
   IF p_mode='refresh' THEN
    SELECT coalesce(sum(amount),0) INTO earned FROM public.hp_transactions WHERE user_id=person.id AND campus_id=p_campus AND type='earn' AND status='active' AND created_at>=now()-interval '120 days';
    UPDATE public.profiles SET hp_earned_120day=earned WHERE id=person.id;
   END IF;
   r:=public.hg_recalculate_tier_atomic(person.id,CASE WHEN p_mode='refresh' THEN 'upgrade' ELSE 'grace' END,p_grace_days);
   IF r->>'event'='grace' THEN started:=started+1;END IF;
   IF r->>'event'='downgrade' THEN dropped:=dropped+1;END IF;
  EXCEPTION WHEN OTHERS THEN errors:=errors+1;END;
 END LOOP;
 RETURN jsonb_build_object('checked',counted,'errors',errors,'next_after',last_id,'has_more',counted=p_limit,'started_grace',started,'dropped_tier',dropped);
END$$;
REVOKE ALL ON FUNCTION public.hg_recalculate_tier_atomic(uuid,text,integer),public.hg_tier_maintenance_batch(uuid,text,uuid,integer,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_recalculate_tier_atomic(uuid,text,integer),public.hg_tier_maintenance_batch(uuid,text,uuid,integer,integer) TO service_role;
