-- One optional, paused-by-default repeating campaign per campus. No sends on rollout.
CREATE TABLE hg_internal.engagement_campaigns (
 id uuid PRIMARY KEY, campus_id uuid NOT NULL UNIQUE REFERENCES public.campuses(id),
 name text NOT NULL, start_date date NOT NULL, morning_time time NOT NULL DEFAULT '09:00',
 afternoon_time time NOT NULL DEFAULT '15:00', steps jsonb NOT NULL,
 is_active boolean NOT NULL DEFAULT false, revision integer NOT NULL DEFAULT 1,
 updated_by uuid NOT NULL REFERENCES public.profiles(id), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(morning_time<'12:00' AND afternoon_time>='12:00' AND morning_time<afternoon_time)
);
CREATE TABLE hg_internal.engagement_campaign_history (
 campaign_id uuid NOT NULL REFERENCES hg_internal.engagement_campaigns(id), revision integer NOT NULL,
 actor_id uuid NOT NULL, before_config jsonb, after_config jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(campaign_id,revision)
);
CREATE TABLE hg_internal.engagement_campaign_receipts (
 user_id uuid NOT NULL REFERENCES public.profiles(id), local_date date NOT NULL, slot text NOT NULL CHECK(slot IN ('morning','afternoon')),
 campaign_id uuid NOT NULL REFERENCES hg_internal.engagement_campaigns(id), revision integer NOT NULL,
 notification_id uuid NOT NULL UNIQUE, queued_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,local_date,slot)
);
CREATE INDEX engagement_cycle_receipts_campaign_idx ON hg_internal.engagement_campaign_receipts(campaign_id,local_date);
ALTER TABLE hg_internal.engagement_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE hg_internal.engagement_campaign_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE hg_internal.engagement_campaign_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.engagement_campaigns,hg_internal.engagement_campaign_history,hg_internal.engagement_campaign_receipts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.engagement_campaigns,hg_internal.engagement_campaign_history,hg_internal.engagement_campaign_receipts TO service_role;

CREATE FUNCTION public.hg_engagement_campaign_config(p_actor uuid,p_scope uuid,p_values jsonb DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE actor profiles%ROWTYPE; old hg_internal.engagement_campaigns%ROWTYPE; saved hg_internal.engagement_campaigns%ROWTYPE; s jsonb;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin') OR p_scope IS NULL OR
 (actor.role::text='admin' AND p_scope IS DISTINCT FROM actor.campus_id) THEN RETURN '{"error":"forbidden"}'; END IF;
 IF NOT EXISTS(SELECT 1 FROM campuses WHERE id=p_scope AND is_active) THEN RETURN '{"error":"invalid"}'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('engagement-campaign:'||p_scope,0));
 SELECT * INTO old FROM hg_internal.engagement_campaigns WHERE campus_id=p_scope FOR UPDATE;
 IF p_values IS NULL THEN RETURN jsonb_build_object('campaign',CASE WHEN old.id IS NULL THEN NULL ELSE to_jsonb(old) END); END IF;
 IF jsonb_typeof(p_values)<>'object' OR jsonb_typeof(p_values->'steps')<>'array' OR jsonb_array_length(p_values->'steps')<>28
 OR jsonb_typeof(p_values->'is_active')<>'boolean' OR coalesce(length(trim(p_values->>'name')),0) NOT BETWEEN 1 AND 100
 OR p_values->>'id' IS NULL OR p_values->>'revision' IS NULL OR p_values->>'start_date' IS NULL
 OR p_values->>'morning_time' IS NULL OR p_values->>'afternoon_time' IS NULL THEN RETURN '{"error":"invalid"}'; END IF;
 IF (SELECT count(DISTINCT (x->>'day',x->>'slot')) FROM jsonb_array_elements(p_values->'steps') x)<>28 THEN RETURN '{"error":"invalid"}'; END IF;
 FOR s IN SELECT * FROM jsonb_array_elements(p_values->'steps') LOOP
  IF coalesce(s->>'day','')!~'^(1[0-4]|[1-9])$' OR coalesce(s->>'slot','') NOT IN ('morning','afternoon')
   OR coalesce(length(trim(s->>'title')),0) NOT BETWEEN 1 AND 100 OR coalesce(length(trim(s->>'body')),0) NOT BETWEEN 1 AND 500
   OR coalesce(s->>'action_url','')!~'^/(menu|dashboard|rewards|wallet|events|orders|leaderboard)(/[a-zA-Z0-9_-]+)?$'
   OR (coalesce(s->>'push_image','')<>'' AND (s->>'push_image' !~ '^https://res[.]cloudinary[.]com/[^/]+/image/upload/' OR s->>'push_image' ~ '[[:space:]]'))
  THEN RETURN '{"error":"invalid"}'; END IF;
 END LOOP;
 IF old.id IS NOT NULL AND (old.id<>(p_values->>'id')::uuid OR old.revision<>(p_values->>'revision')::int) THEN RETURN '{"error":"stale"}'; END IF;
 IF old.id IS NULL AND (p_values->>'revision')::int<>0 THEN RETURN '{"error":"stale"}'; END IF;
 INSERT INTO hg_internal.engagement_campaigns(id,campus_id,name,start_date,morning_time,afternoon_time,steps,is_active,updated_by)
 VALUES((p_values->>'id')::uuid,p_scope,trim(p_values->>'name'),(p_values->>'start_date')::date,(p_values->>'morning_time')::time,(p_values->>'afternoon_time')::time,p_values->'steps',(p_values->>'is_active')::boolean,p_actor)
 ON CONFLICT(campus_id) DO UPDATE SET name=excluded.name,start_date=excluded.start_date,morning_time=excluded.morning_time,
 afternoon_time=excluded.afternoon_time,steps=excluded.steps,is_active=excluded.is_active,revision=old.revision+1,updated_by=p_actor,updated_at=now() RETURNING * INTO saved;
 INSERT INTO hg_internal.engagement_campaign_history VALUES(saved.id,saved.revision,p_actor,CASE WHEN old.id IS NULL THEN NULL ELSE to_jsonb(old) END,to_jsonb(saved),now());
 RETURN jsonb_build_object('campaign',to_jsonb(saved));
EXCEPTION WHEN invalid_datetime_format OR invalid_parameter_value OR invalid_text_representation OR datetime_field_overflow OR check_violation OR unique_violation THEN RETURN '{"error":"invalid"}';
END $$;

CREATE FUNCTION public.hg_due_engagement_campaigns()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce(jsonb_agg(to_jsonb(c)||jsonb_build_object('slot',s.slot,'scheduled_at',s.at,'cycle_day',((now() AT TIME ZONE 'Africa/Lagos')::date-c.start_date)%14+1,'campus_name',p.name)),'[]')
 FROM hg_internal.engagement_campaigns c JOIN campuses p ON p.id=c.campus_id AND p.is_active
 CROSS JOIN LATERAL(VALUES('morning',((now() AT TIME ZONE 'Africa/Lagos')::date+c.morning_time) AT TIME ZONE 'Africa/Lagos'),('afternoon',((now() AT TIME ZONE 'Africa/Lagos')::date+c.afternoon_time) AT TIME ZONE 'Africa/Lagos')) s(slot,at)
 WHERE c.is_active AND c.start_date<=(now() AT TIME ZONE 'Africa/Lagos')::date AND now()>=s.at AND now()<s.at+interval '30 minutes'
$$;

CREATE FUNCTION public.hg_engagement_campaign_recipients(p_campaign uuid,p_slot text,p_after uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce(jsonb_agg(to_jsonb(r)),'[]') FROM (
 SELECT p.id,p.nickname,p.full_name FROM profiles p JOIN hg_internal.engagement_campaigns c ON c.campus_id=p.campus_id
 LEFT JOIN notification_preferences n ON n.user_id=p.id
 WHERE c.id=p_campaign AND c.is_active AND p.is_active AND p.role::text='student'
 AND p.push_enabled IS DISTINCT FROM false AND n.push_enabled IS DISTINCT FROM false AND n.promotions IS DISTINCT FROM false
 AND (p_after IS NULL OR p.id>p_after) AND p_slot IN ('morning','afternoon')
 AND EXISTS(SELECT 1 FROM device_tokens t WHERE t.user_id=p.id AND length(trim(t.token))>0 AND t.token NOT LIKE 'local:%' AND t.token NOT LIKE 'local-%')
 AND NOT EXISTS(SELECT 1 FROM hg_internal.engagement_campaign_receipts x WHERE x.user_id=p.id AND x.local_date=(now() AT TIME ZONE 'Africa/Lagos')::date AND x.slot=p_slot)
 ORDER BY p.id LIMIT 200) r
$$;

CREATE FUNCTION public.hg_enqueue_engagement_campaign(p_campaign uuid,p_revision integer,p_slot text,p_messages jsonb,p_expires timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE c hg_internal.engagement_campaigns%ROWTYPE; local_day date:=(now() AT TIME ZONE 'Africa/Lagos')::date; at_time timestamptz; s jsonb; uid uuid; nid uuid; inserted integer; total integer:=0;
BEGIN
 SELECT * INTO c FROM hg_internal.engagement_campaigns WHERE id=p_campaign AND is_active FOR SHARE;
 IF NOT FOUND OR c.revision<>p_revision OR c.start_date>local_day OR p_slot NOT IN ('morning','afternoon') THEN RETURN '{"error":"stale"}'; END IF;
 at_time:=(local_day+CASE WHEN p_slot='morning' THEN c.morning_time ELSE c.afternoon_time END) AT TIME ZONE 'Africa/Lagos';
 IF now()<at_time OR now()>=at_time+interval '30 minutes' OR p_expires<=now() OR p_expires>at_time+interval '45 minutes' OR p_expires IS NULL THEN RETURN '{"error":"expired"}'; END IF;
 IF jsonb_typeof(p_messages)<>'array' OR jsonb_array_length(p_messages)>200 THEN RETURN '{"error":"invalid"}'; END IF;
 FOR s IN SELECT * FROM jsonb_array_elements(p_messages) LOOP
  uid:=(s->>'user_id')::uuid;
  IF NOT EXISTS(SELECT 1 FROM profiles p LEFT JOIN notification_preferences n ON n.user_id=p.id
   WHERE p.id=uid AND p.campus_id=c.campus_id AND p.role::text='student' AND p.is_active AND p.push_enabled IS DISTINCT FROM false AND n.push_enabled IS DISTINCT FROM false AND n.promotions IS DISTINCT FROM false
   AND EXISTS(SELECT 1 FROM device_tokens t WHERE t.user_id=p.id AND length(trim(t.token))>0 AND t.token NOT LIKE 'local:%' AND t.token NOT LIKE 'local-%')) THEN CONTINUE; END IF;
  IF coalesce(length(s->>'title'),0) NOT BETWEEN 1 AND 160 OR coalesce(length(s->>'body'),0) NOT BETWEEN 1 AND 1000 THEN RAISE EXCEPTION 'invalid rendered message'; END IF;
  nid:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8',uid||':'||local_day||':'||p_slot||':engagement-cycle');
  INSERT INTO hg_internal.engagement_campaign_receipts(user_id,local_date,slot,campaign_id,revision,notification_id) VALUES(uid,local_day,p_slot,c.id,c.revision,nid) ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS inserted=ROW_COUNT;
  IF inserted=0 THEN CONTINUE; END IF;
  INSERT INTO notifications(id,user_id,campus_id,title,body,type,channel,action_url,metadata)
  VALUES(nid,uid,c.campus_id,s->>'title',s->>'body','engagement_cycle','push',s->>'action_url',jsonb_build_object('_dispatch_version',1,'campaign_id',c.id,'campaign_revision',c.revision,'cycle_day',(local_day-c.start_date)%14+1,'slot',p_slot,'expires_at',p_expires,'push_image',s->>'push_image'));
  total:=total+1;
 END LOOP;
 RETURN jsonb_build_object('queued',total);
END $$;

CREATE FUNCTION public.hg_engagement_campaign_notice_valid(p_campaign uuid,p_revision integer,p_user uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM hg_internal.engagement_campaigns c JOIN profiles p ON p.campus_id=c.campus_id JOIN campuses x ON x.id=c.campus_id
 WHERE c.id=p_campaign AND c.is_active AND c.revision=p_revision AND p.id=p_user AND p.is_active AND x.is_active AND p.role::text='student')
$$;
REVOKE ALL ON FUNCTION public.hg_engagement_campaign_config(uuid,uuid,jsonb),public.hg_due_engagement_campaigns(),public.hg_engagement_campaign_recipients(uuid,text,uuid),public.hg_enqueue_engagement_campaign(uuid,integer,text,jsonb,timestamptz),public.hg_engagement_campaign_notice_valid(uuid,integer,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_engagement_campaign_config(uuid,uuid,jsonb),public.hg_due_engagement_campaigns(),public.hg_engagement_campaign_recipients(uuid,text,uuid),public.hg_enqueue_engagement_campaign(uuid,integer,text,jsonb,timestamptz),public.hg_engagement_campaign_notice_valid(uuid,integer,uuid) TO service_role;

-- Keep the existing outbox's frozen-content rule. Only this new push type may
-- shorten TTL on retry; user, content, URL, app and provider key cannot change.
DO $patch$
DECLARE definition text; needle text := 'IF d.dispatch_payload->''prepared'' IS NOT NULL AND d.dispatch_payload->''prepared'' IS DISTINCT FROM p_prepared THEN RAISE EXCEPTION ''Dispatch payload changed on replay''; END IF;';
BEGIN
 SELECT pg_get_functiondef('public.hg_begin_notification_dispatch(uuid,uuid,jsonb)'::regprocedure) INTO definition;
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Outbox guard changed; review before applying engagement migration'; END IF;
 definition:=replace(definition,needle,$guard$
 IF d.dispatch_payload->'prepared' IS NOT NULL AND d.dispatch_payload->'prepared' IS DISTINCT FROM p_prepared THEN
  IF (d.channel='push' AND d.dispatch_payload->'notification'->>'type'='engagement_cycle'
   AND ((d.dispatch_payload->'prepared')-'ttl')=(p_prepared-'ttl')
   AND jsonb_typeof(p_prepared->'ttl')='number' AND jsonb_typeof(d.dispatch_payload->'prepared'->'ttl')='number'
   AND (p_prepared->>'ttl')::numeric>0 AND (p_prepared->>'ttl')::numeric<=(d.dispatch_payload->'prepared'->>'ttl')::numeric) IS NOT TRUE
  THEN RAISE EXCEPTION 'Dispatch payload changed on replay'; END IF;
 END IF;
 IF d.dispatch_payload->'notification'->>'type'='engagement_cycle' AND (
  NOT public.hg_engagement_campaign_notice_valid((d.dispatch_payload->'notification'->'metadata'->>'campaign_id')::uuid,
   (d.dispatch_payload->'notification'->'metadata'->>'campaign_revision')::integer,(d.dispatch_payload->'notification'->>'user_id')::uuid)
  OR (d.dispatch_payload->'notification'->'metadata'->>'expires_at')::timestamptz<=clock_timestamp()) THEN
  UPDATE public.notification_deliveries SET status='cancelled',error_message='engagement_cycle_no_longer_due',dispatch=dispatch||jsonb_build_object('state','cancelled') WHERE id=d.id;RETURN false;
 END IF;
 $guard$);
 EXECUTE definition;
END $patch$;
