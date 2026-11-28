-- Additive team workspace. Existing commerce roles and all financial ledgers are preserved.
CREATE TABLE public.team_responsibilities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), campus_id uuid NOT NULL REFERENCES public.campuses(id),
 name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 100), description text NOT NULL DEFAULT '',
 reviewer_by_default boolean NOT NULL DEFAULT false,
 targets jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(targets)='array' AND jsonb_array_length(targets)<=30),
 active boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1,
 UNIQUE(campus_id,name), UNIQUE(id,campus_id)
);
CREATE TABLE public.team_settings (
 campus_id uuid PRIMARY KEY REFERENCES public.campuses(id), due_weekday integer NOT NULL DEFAULT 4 CHECK(due_weekday BETWEEN 1 AND 7),
 due_minute integer NOT NULL DEFAULT 1260 CHECK(due_minute BETWEEN 0 AND 1439),
 digest_enabled boolean NOT NULL DEFAULT true, digest_minute integer NOT NULL DEFAULT 1260 CHECK(digest_minute BETWEEN 0 AND 1439),
 coverage_target numeric NOT NULL DEFAULT 75 CHECK(coverage_target BETWEEN 0 AND 100), version integer NOT NULL DEFAULT 1
);
CREATE TABLE public.team_memberships (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), campus_id uuid NOT NULL REFERENCES public.campuses(id), profile_id uuid NOT NULL REFERENCES public.profiles(id),
 responsibility_id uuid NOT NULL, can_review boolean NOT NULL DEFAULT false, active boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1,
 FOREIGN KEY(responsibility_id,campus_id) REFERENCES public.team_responsibilities(id,campus_id),
 UNIQUE(profile_id,campus_id), UNIQUE(id,campus_id)
);
CREATE TABLE public.team_weeks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), campus_id uuid NOT NULL REFERENCES public.campuses(id), week_start date NOT NULL CHECK(extract(isodow FROM week_start)=1),
 due_at timestamptz NOT NULL, meeting_at timestamptz NOT NULL, reopened_until timestamptz,
 period_start date NOT NULL, period_end date NOT NULL CHECK(period_end>=period_start AND period_end-period_start<=13),
 coverage_target numeric NOT NULL DEFAULT 75 CHECK(coverage_target BETWEEN 0 AND 100), version integer NOT NULL DEFAULT 1,
 UNIQUE(campus_id,week_start), UNIQUE(id,campus_id)
);
CREATE TABLE public.team_entries (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), campus_id uuid NOT NULL, week_id uuid NOT NULL, member_id uuid NOT NULL,
 targets jsonb NOT NULL DEFAULT '[]', results jsonb NOT NULL DEFAULT '{}', daily_results jsonb NOT NULL DEFAULT '{}', narrative jsonb NOT NULL DEFAULT '{}', content jsonb NOT NULL DEFAULT '[]',
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','changes_requested','approved')),
 feedback text NOT NULL DEFAULT '', submitted_at timestamptz, reviewed_at timestamptz, reviewed_by uuid REFERENCES public.profiles(id), version integer NOT NULL DEFAULT 1,
 FOREIGN KEY(week_id,campus_id) REFERENCES public.team_weeks(id,campus_id), FOREIGN KEY(member_id,campus_id) REFERENCES public.team_memberships(id,campus_id), UNIQUE(week_id,member_id)
);
CREATE TABLE public.team_logs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), campus_id uuid NOT NULL REFERENCES public.campuses(id), week_id uuid NOT NULL,
 author_id uuid NOT NULL REFERENCES public.profiles(id), kind text NOT NULL CHECK(kind IN ('meeting','action','incident','change')),
 title text NOT NULL CHECK(length(btrim(title)) BETWEEN 1 AND 200), body text NOT NULL DEFAULT '' CHECK(length(body)<=8000),
 owner_id uuid REFERENCES public.profiles(id), due_at timestamptz, status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','resolved')),
 private boolean NOT NULL DEFAULT false, version integer NOT NULL DEFAULT 1,
 FOREIGN KEY(week_id,campus_id) REFERENCES public.team_weeks(id,campus_id)
);
CREATE TABLE public.team_reminder_rules (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), campus_id uuid NOT NULL REFERENCES public.campuses(id), responsibility_id uuid,
 title text NOT NULL CHECK(length(btrim(title)) BETWEEN 1 AND 150), body text NOT NULL DEFAULT '' CHECK(length(body)<=2000),
 weekdays integer[] NOT NULL DEFAULT ARRAY[1,3,4] CHECK(cardinality(weekdays) BETWEEN 1 AND 7 AND weekdays <@ ARRAY[1,2,3,4,5,6,7]),
 minute_of_day integer NOT NULL DEFAULT 900 CHECK(minute_of_day BETWEEN 0 AND 1439), outstanding_only boolean NOT NULL DEFAULT true,
 enabled boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1,
 FOREIGN KEY(responsibility_id,campus_id) REFERENCES public.team_responsibilities(id,campus_id)
);
CREATE TABLE public.team_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, campus_id uuid NOT NULL, actor_id uuid NOT NULL REFERENCES public.profiles(id),
 request_id uuid NOT NULL, action text NOT NULL, payload jsonb NOT NULL, result jsonb NOT NULL, before_state jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(actor_id,request_id)
);
CREATE TABLE public.team_notice_receipts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), member_id uuid NOT NULL REFERENCES public.team_memberships(id),
 notice_key text NOT NULL, notification_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(member_id,notice_key)
);
CREATE INDEX team_members_active_scope ON public.team_memberships(campus_id,profile_id) WHERE active;
CREATE INDEX team_entries_scope_week ON public.team_entries(campus_id,week_id);
CREATE INDEX team_logs_scope_week ON public.team_logs(campus_id,week_id);
CREATE INDEX team_reminders_enabled ON public.team_reminder_rules(campus_id) WHERE enabled;
CREATE INDEX team_audit_scope_date ON public.team_audit(campus_id,created_at DESC);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['team_responsibilities','team_settings','team_memberships','team_weeks','team_entries','team_logs','team_reminder_rules','team_audit','team_notice_receipts'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON public.%I TO service_role',t);
 END LOOP;
END $$;
GRANT USAGE,SELECT ON SEQUENCE public.team_audit_id_seq TO service_role;
ALTER TABLE public.profiles ADD COLUMN team_workspace boolean NOT NULL DEFAULT false;
CREATE FUNCTION public.hg_team_member_flag() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 UPDATE profiles SET team_workspace=EXISTS(SELECT 1 FROM team_memberships m WHERE m.profile_id=NEW.profile_id AND m.active AND m.campus_id=profiles.campus_id AND profiles.is_active) WHERE id=NEW.profile_id;
 RETURN NEW;
END $$;
CREATE TRIGGER team_member_flag AFTER INSERT OR UPDATE ON public.team_memberships FOR EACH ROW EXECUTE FUNCTION public.hg_team_member_flag();
CREATE FUNCTION public.hg_team_protect_flag() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF NEW.team_workspace IS DISTINCT FROM OLD.team_workspace AND current_user NOT IN ('postgres','service_role','supabase_admin') THEN RAISE EXCEPTION 'Team membership is managed by administrators'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER team_protect_flag BEFORE UPDATE OF team_workspace ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.hg_team_protect_flag();

CREATE FUNCTION public.hg_team_targets_valid(v jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE t jsonb; seen text[]:=ARRAY[]::text[];
BEGIN
 IF v IS NULL OR jsonb_typeof(v)<>'array' OR jsonb_array_length(v)>30 THEN RETURN false; END IF;
 FOR t IN SELECT * FROM jsonb_array_elements(v) LOOP
  IF jsonb_typeof(t)<>'object' OR coalesce(length(btrim(t->>'title')),0) NOT BETWEEN 1 AND 180
   OR (t->>'direction') NOT IN ('higher','lower') OR (t->>'unit') NOT IN ('count','percent','hours','minutes','weeks')
   OR jsonb_typeof(t->'target') IS DISTINCT FROM 'number' OR jsonb_typeof(t->'tolerance') IS DISTINCT FROM 'number'
   OR (t->>'target')::numeric<0 OR (t->>'tolerance')::numeric<0 OR (t->>'target')::numeric>1000000
   OR (t->>'unit'='percent' AND (t->>'target')::numeric>100)
   OR (coalesce(t->>'cadence','weekly') NOT IN ('weekly','daily')) OR (t->>'id') IS NULL OR (t->>'id')=ANY(seen) THEN RETURN false; END IF;
  PERFORM (t->>'id')::uuid; seen:=array_append(seen,t->>'id');
  IF NOT (t ? 'target' AND t ? 'tolerance' AND t ? 'direction' AND t ? 'unit') THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
END $$;
CREATE FUNCTION public.hg_team_ensure_week(p_campus uuid,p_start date) RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE wid uuid; cfg team_settings%ROWTYPE;
BEGIN
 SELECT * INTO cfg FROM team_settings WHERE campus_id=p_campus;
 IF NOT FOUND OR extract(isodow FROM p_start)<>1 THEN RETURN NULL; END IF;
 INSERT INTO team_weeks(campus_id,week_start,due_at,meeting_at,coverage_target,period_start,period_end)
 VALUES(p_campus,p_start,((p_start+cfg.due_weekday-1)::timestamp+make_interval(mins=>cfg.due_minute)) AT TIME ZONE 'Africa/Lagos',
 ((p_start+cfg.due_weekday-1)::timestamp+make_interval(mins=>cfg.due_minute)) AT TIME ZONE 'Africa/Lagos',cfg.coverage_target,p_start+cfg.due_weekday-7,p_start+cfg.due_weekday-1)
 ON CONFLICT(campus_id,week_start) DO NOTHING;
 SELECT id INTO wid FROM team_weeks WHERE campus_id=p_campus AND week_start=p_start;
 INSERT INTO team_entries(campus_id,week_id,member_id,targets)
 SELECT p_campus,wid,m.id,r.targets FROM team_memberships m JOIN team_responsibilities r ON r.id=m.responsibility_id
 WHERE m.campus_id=p_campus AND m.active AND r.active ON CONFLICT(week_id,member_id) DO NOTHING;
 RETURN wid;
END $$;

CREATE FUNCTION public.hg_team_workspace(p_actor uuid,p_scope uuid,p_action text,p_data jsonb DEFAULT '{}',p_request uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE actor profiles%ROWTYPE; membership team_memberships%ROWTYPE; adm boolean; reviewer boolean; scope uuid; start_day date;
 w team_weeks%ROWTYPE; e team_entries%ROWTYPE; r team_responsibilities%ROWTYPE; rec record; obj jsonb; item jsonb; vals jsonb;
 result jsonb; before_state jsonb:='{}'; daily_vals jsonb; day_rec record; result_rec record; seen_daily boolean; previous team_audit%ROWTYPE; entry_id uuid; mid uuid; rid uuid; n integer; closed boolean; read_only boolean;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND THEN RETURN '{"error":"forbidden"}'; END IF;
 adm:=actor.role::text IN ('admin','super_admin');
 scope:=CASE WHEN actor.role::text='super_admin' THEN coalesce(p_scope,actor.campus_id) ELSE actor.campus_id END;
 IF scope IS NULL OR NOT EXISTS(SELECT 1 FROM campuses WHERE id=scope AND is_active) THEN RETURN '{"error":"campus_required"}'; END IF;
 IF p_scope IS NOT NULL AND p_scope<>scope THEN RETURN '{"error":"forbidden"}'; END IF;
 SELECT * INTO membership FROM team_memberships WHERE profile_id=p_actor AND campus_id=scope AND active;
 reviewer:=adm OR coalesce(membership.can_review,false);
 IF p_action='access' THEN RETURN jsonb_build_object('member',membership.id IS NOT NULL,'admin',adm,'reviewer',reviewer,'campus_id',scope); END IF;
 IF NOT adm AND membership.id IS NULL THEN RETURN '{"error":"forbidden"}'; END IF;
 IF p_action='snapshot' THEN
  start_day:=coalesce((p_data->>'week')::date,(SELECT week_start FROM team_weeks WHERE campus_id=scope AND week_start>=date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date AND due_at>now() ORDER BY week_start LIMIT 1),date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date);
  SELECT * INTO w FROM team_weeks WHERE campus_id=scope AND week_start=start_day;
  RETURN jsonb_build_object('campus_id',scope,'actor_id',p_actor,'member_id',membership.id,'admin',adm,'reviewer',reviewer,
   'settings',(SELECT to_jsonb(s) FROM team_settings s WHERE campus_id=scope),'week',to_jsonb(w),
   'responsibilities',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY name),'[]') FROM team_responsibilities t WHERE campus_id=scope),
   'members',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.name),'[]') FROM (SELECT m.*,coalesce(nullif(p.nickname,''),p.full_name,'Team member') name FROM team_memberships m JOIN profiles p ON p.id=m.profile_id WHERE m.campus_id=scope AND p.is_active) t),
   'entries',(SELECT coalesce(jsonb_agg(CASE WHEN reviewer OR t.member_id=membership.id THEN to_jsonb(t) ELSE to_jsonb(t)-'narrative'-'feedback' END ORDER BY t.id),'[]') FROM team_entries t JOIN team_memberships m ON m.id=t.member_id WHERE t.week_id=w.id AND m.active),
   'logs',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id),'[]') FROM team_logs t WHERE t.week_id=w.id AND (NOT t.private OR reviewer OR t.author_id=p_actor)),
   'rules',CASE WHEN adm THEN (SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY title),'[]') FROM team_reminder_rules t WHERE campus_id=scope) ELSE '[]'::jsonb END,
   'audit',CASE WHEN reviewer THEN (SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') FROM (SELECT id,actor_id,action,created_at FROM team_audit WHERE campus_id=scope ORDER BY id DESC LIMIT 40) t) ELSE '[]'::jsonb END);
 END IF;
 IF p_request IS NULL OR jsonb_typeof(p_data)<>'object' OR octet_length(p_data::text)>100000 THEN RETURN '{"error":"invalid"}'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_actor::text||p_request::text,0));
 SELECT * INTO previous FROM team_audit WHERE actor_id=p_actor AND request_id=p_request;
 IF FOUND THEN
  IF previous.action<>p_action OR previous.payload<>p_data OR previous.campus_id<>scope THEN RETURN '{"error":"request_conflict"}'; END IF;
  RETURN previous.result;
 END IF;
 IF p_action='responsibility' THEN
  IF NOT adm THEN RETURN '{"error":"forbidden"}'; END IF;
  IF NOT hg_team_targets_valid(p_data->'targets') OR coalesce(length(btrim(p_data->>'name')),0) NOT BETWEEN 1 AND 100 THEN RETURN '{"error":"invalid"}'; END IF;
  IF p_data->>'id' IS NOT NULL THEN
   SELECT * INTO r FROM team_responsibilities WHERE id=(p_data->>'id')::uuid AND campus_id=scope FOR UPDATE;
   IF NOT FOUND THEN RETURN '{"error":"forbidden"}'; END IF;
   IF r.version IS DISTINCT FROM (p_data->>'version')::int THEN RETURN '{"error":"stale"}'; END IF;
   UPDATE team_responsibilities SET reviewer_by_default=coalesce((p_data->>'reviewer_by_default')::boolean,false),name=btrim(p_data->>'name'),description=left(coalesce(p_data->>'description',''),2000),targets=p_data->'targets',active=coalesce((p_data->>'active')::boolean,true),version=version+1 WHERE id=r.id RETURNING id INTO rid;
  ELSE
   INSERT INTO team_responsibilities(campus_id,name,reviewer_by_default,description,targets) VALUES(scope,btrim(p_data->>'name'),coalesce((p_data->>'reviewer_by_default')::boolean,false),left(coalesce(p_data->>'description',''),2000),p_data->'targets') RETURNING id INTO rid;
  END IF;
  result:=jsonb_build_object('id',rid);
 ELSIF p_action='member' THEN
  IF NOT adm THEN RETURN '{"error":"forbidden"}'; END IF;
  rid:=(p_data->>'responsibility_id')::uuid;
  IF NOT EXISTS(SELECT 1 FROM team_responsibilities WHERE id=rid AND campus_id=scope AND active)
   OR NOT EXISTS(SELECT 1 FROM profiles WHERE id=(p_data->>'profile_id')::uuid AND campus_id=scope AND is_active) THEN RETURN '{"error":"forbidden"}'; END IF;
  SELECT m.id,m.version INTO rec FROM team_memberships m WHERE profile_id=(p_data->>'profile_id')::uuid AND campus_id=scope FOR UPDATE;
  IF FOUND AND rec.version IS DISTINCT FROM (p_data->>'version')::int THEN RETURN '{"error":"stale"}'; END IF;
  INSERT INTO team_memberships(campus_id,profile_id,responsibility_id,can_review,active)
  VALUES(scope,(p_data->>'profile_id')::uuid,rid,coalesce((p_data->>'can_review')::boolean,false),coalesce((p_data->>'active')::boolean,true))
  ON CONFLICT(profile_id,campus_id) DO UPDATE SET responsibility_id=excluded.responsibility_id,can_review=excluded.can_review,active=excluded.active,version=team_memberships.version+1 RETURNING id INTO mid;
  PERFORM hg_team_ensure_week(scope,date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date);
  IF EXISTS(SELECT 1 FROM team_weeks WHERE campus_id=scope AND week_start=date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date AND due_at<=now()) THEN PERFORM hg_team_ensure_week(scope,date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date+7); END IF;
  result:=jsonb_build_object('id',mid);
 ELSIF p_action='settings' THEN
  IF NOT adm THEN RETURN '{"error":"forbidden"}'; END IF;
  SELECT version INTO n FROM team_settings WHERE campus_id=scope FOR UPDATE;
  IF n IS DISTINCT FROM (p_data->>'version')::int THEN RETURN '{"error":"stale"}'; END IF;
  UPDATE team_settings SET due_weekday=(p_data->>'due_weekday')::int,due_minute=(p_data->>'due_minute')::int,
   digest_enabled=coalesce((p_data->>'digest_enabled')::boolean,false),digest_minute=(p_data->>'digest_minute')::int,coverage_target=(p_data->>'coverage_target')::numeric,version=version+1 WHERE campus_id=scope;
  result:='{"saved":true}';
 ELSIF p_action='week' THEN
  IF NOT adm THEN RETURN '{"error":"forbidden"}'; END IF;
  start_day:=(p_data->>'week_start')::date;
  IF start_day IS NULL OR extract(isodow FROM start_day)<>1 OR start_day<current_date-interval '366 days' OR start_day>current_date+interval '90 days' THEN RETURN '{"error":"invalid"}'; END IF;
  IF p_data->>'due_at' IS NULL OR p_data->>'meeting_at' IS NULL THEN RETURN '{"error":"invalid"}'; END IF;
  IF p_data->>'reopened_until' IS NOT NULL AND coalesce(length(btrim(p_data->>'reason')),0)<3 THEN RETURN '{"error":"invalid"}'; END IF;
  PERFORM (p_data->>'due_at')::timestamptz; PERFORM (p_data->>'meeting_at')::timestamptz;
  PERFORM pg_advisory_xact_lock(hashtextextended('team-week:'||scope||start_day,0));
  SELECT * INTO w FROM team_weeks WHERE campus_id=scope AND week_start=start_day FOR UPDATE;
  IF FOUND THEN
   IF w.version IS DISTINCT FROM (p_data->>'version')::int THEN RETURN '{"error":"stale"}'; END IF;
   IF coalesce(length(btrim(p_data->>'reason')),0)<3 THEN RETURN '{"error":"invalid"}'; END IF;
  ELSE
   PERFORM hg_team_ensure_week(scope,start_day);
   SELECT * INTO w FROM team_weeks WHERE campus_id=scope AND week_start=start_day FOR UPDATE;
  END IF;
  UPDATE team_weeks SET due_at=(p_data->>'due_at')::timestamptz,meeting_at=(p_data->>'meeting_at')::timestamptz,
   reopened_until=CASE WHEN adm THEN (p_data->>'reopened_until')::timestamptz ELSE reopened_until END,version=version+1 WHERE id=w.id;
  result:=jsonb_build_object('id',w.id);
 ELSIF p_action IN ('save','submit','review','targets') THEN
  SELECT * INTO e FROM team_entries WHERE id=(p_data->>'id')::uuid AND campus_id=scope FOR UPDATE;
  IF NOT FOUND THEN RETURN '{"error":"forbidden"}'; END IF;
  before_state:=to_jsonb(e);
  SELECT * INTO w FROM team_weeks WHERE id=e.week_id FOR SHARE;
  IF e.version IS DISTINCT FROM (p_data->>'version')::int THEN RETURN '{"error":"stale"}'; END IF;
  closed:=clock_timestamp()>=greatest(w.due_at,coalesce(w.reopened_until,w.due_at));
  IF p_action IN ('save','submit') THEN
   IF membership.id IS DISTINCT FROM e.member_id THEN RETURN '{"error":"forbidden"}'; END IF;
   IF closed THEN RETURN '{"error":"closed"}'; END IF;
   vals:=p_data->'results';
   IF vals IS NULL OR jsonb_typeof(vals)<>'object' OR jsonb_typeof(p_data->'narrative') IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_data->'content') IS DISTINCT FROM 'array' OR jsonb_array_length(p_data->'content')>50
    OR octet_length((p_data->'narrative')::text)>16000 THEN RETURN '{"error":"invalid"}'; END IF;
   FOR rec IN SELECT key,value FROM jsonb_each(vals) LOOP
    SELECT t INTO obj FROM jsonb_array_elements(e.targets) t WHERE t->>'id'=rec.key;
    IF NOT FOUND OR coalesce(obj->>'cadence','weekly')='daily' OR jsonb_typeof(rec.value)<>'object' THEN RETURN '{"error":"invalid"}'; END IF;
    IF rec.value->>'actual' IS NOT NULL AND rec.value->>'actual'<>'' THEN
     IF (rec.value->>'actual')::numeric<0 OR (rec.value->>'actual')::numeric>1000000 OR (obj->>'unit'='percent' AND (rec.value->>'actual')::numeric>100) THEN RETURN '{"error":"invalid"}'; END IF;
    END IF;
    IF length(coalesce(rec.value->>'evidence',''))>2000 OR (coalesce(rec.value->>'evidence','')<>'' AND rec.value->>'evidence' !~ '^https://[^[:space:]]+$') THEN RETURN '{"error":"invalid"}'; END IF;
   END LOOP;
   FOR item IN SELECT * FROM jsonb_array_elements(p_data->'content') LOOP
    IF jsonb_typeof(item)<>'object' OR length(coalesce(item->>'title','')) NOT BETWEEN 1 AND 200 OR length(coalesce(item->>'caption',''))>6000
     OR (item->>'status') NOT IN ('planned','ready','scheduled','published') OR (coalesce(item->>'asset_url','')<>'' AND item->>'asset_url' !~ '^https://[^[:space:]]+$') THEN RETURN '{"error":"invalid"}'; END IF;
   END LOOP;
   daily_vals:=coalesce(p_data->'daily_results','{}'::jsonb);
   IF jsonb_typeof(daily_vals)<>'object' THEN RETURN '{"error":"invalid"}'; END IF;
   FOR day_rec IN SELECT key,value FROM jsonb_each(daily_vals) LOOP
    IF day_rec.key !~ '^\d{4}-\d{2}-\d{2}$' OR day_rec.key::date NOT BETWEEN w.period_start AND w.period_end
     OR day_rec.key::date>(now() AT TIME ZONE 'Africa/Lagos')::date OR jsonb_typeof(day_rec.value)<>'object' THEN RETURN '{"error":"invalid"}'; END IF;
    FOR result_rec IN SELECT key,value FROM jsonb_each(day_rec.value) LOOP
     SELECT t INTO obj FROM jsonb_array_elements(e.targets) t WHERE t->>'id'=result_rec.key AND t->>'cadence'='daily';
     IF NOT FOUND OR jsonb_typeof(result_rec.value)<>'object' THEN RETURN '{"error":"invalid"}'; END IF;
     IF coalesce(result_rec.value->>'actual','')<>'' AND ((result_rec.value->>'actual')::numeric<0 OR (result_rec.value->>'actual')::numeric>1000000 OR (obj->>'unit'='percent' AND (result_rec.value->>'actual')::numeric>100)) THEN RETURN '{"error":"invalid"}'; END IF;
     IF length(coalesce(result_rec.value->>'evidence',''))>2000 OR (coalesce(result_rec.value->>'evidence','')<>'' AND result_rec.value->>'evidence' !~ '^https://[^[:space:]]+$') THEN RETURN '{"error":"invalid"}'; END IF;
     IF p_action='submit' AND coalesce(result_rec.value->>'actual','')<>'' AND coalesce((obj->>'evidence_required')::boolean,true) AND coalesce(result_rec.value->>'evidence','')='' THEN RETURN '{"error":"incomplete"}'; END IF;
    END LOOP;
   END LOOP;
   IF p_action='submit' THEN
    FOR obj IN SELECT * FROM jsonb_array_elements(e.targets) LOOP
     IF obj->>'cadence'='daily' THEN
      SELECT EXISTS(SELECT 1 FROM jsonb_each(daily_vals) d WHERE coalesce(d.value->(obj->>'id')->>'actual','')<>'') INTO seen_daily;
      IF NOT seen_daily THEN RETURN '{"error":"incomplete"}'; END IF;
     ELSE
      item:=vals->(obj->>'id');
      IF item IS NULL OR coalesce(item->>'actual','')='' OR (coalesce((obj->>'evidence_required')::boolean,true) AND coalesce(item->>'evidence','')='') THEN RETURN '{"error":"incomplete"}'; END IF;
     END IF;
    END LOOP;
   END IF;
   UPDATE team_entries SET results=vals,daily_results=daily_vals,narrative=p_data->'narrative',content=p_data->'content',status=CASE WHEN p_action='submit' THEN 'submitted' ELSE 'draft' END,
    submitted_at=CASE WHEN p_action='submit' THEN now() ELSE submitted_at END,reviewed_at=NULL,reviewed_by=NULL,feedback='',version=version+1 WHERE id=e.id;
  ELSIF p_action='review' THEN
   IF NOT reviewer OR membership.id=e.member_id THEN RETURN '{"error":"forbidden"}'; END IF;
   IF p_data->>'status'='changes_requested' AND coalesce(length(btrim(p_data->>'feedback')),0)=0 THEN RETURN '{"error":"invalid"}'; END IF;
   IF e.status<>'submitted' OR p_data->>'status' NOT IN ('approved','changes_requested') THEN RETURN '{"error":"invalid"}'; END IF;
   UPDATE team_entries SET status=p_data->>'status',feedback=left(coalesce(p_data->>'feedback',''),4000),reviewed_by=p_actor,reviewed_at=now(),version=version+1 WHERE id=e.id;
  ELSE
   IF NOT adm THEN RETURN '{"error":"forbidden"}'; END IF;
   IF closed THEN RETURN '{"error":"closed"}'; END IF;
   IF NOT hg_team_targets_valid(p_data->'targets') THEN RETURN '{"error":"invalid"}'; END IF;
   UPDATE team_entries SET targets=p_data->'targets',status='draft',reviewed_at=NULL,reviewed_by=NULL,feedback='',
    results=(SELECT coalesce(jsonb_object_agg(k,v),'{}') FROM jsonb_each(e.results) x(k,v) WHERE EXISTS(SELECT 1 FROM jsonb_array_elements(p_data->'targets') t WHERE t->>'id'=k AND coalesce(t->>'cadence','weekly')<>'daily')),daily_results=(SELECT coalesce(jsonb_object_agg(dk,(SELECT coalesce(jsonb_object_agg(k,v),'{}') FROM jsonb_each(dv) x(k,v) WHERE EXISTS(SELECT 1 FROM jsonb_array_elements(p_data->'targets') t WHERE t->>'id'=k AND t->>'cadence'='daily'))),'{}') FROM jsonb_each(e.daily_results) d(dk,dv)),version=version+1 WHERE id=e.id;
  END IF;
  result:=jsonb_build_object('id',e.id,'version',e.version+1);
 ELSIF p_action='log' THEN
  IF p_data->>'kind' NOT IN ('meeting','action','incident','change') OR coalesce(length(btrim(p_data->>'title')),0) NOT BETWEEN 1 AND 200 THEN RETURN '{"error":"invalid"}'; END IF;
  IF p_data->>'kind' IN ('meeting','change') AND NOT reviewer THEN RETURN '{"error":"forbidden"}'; END IF;
  SELECT * INTO w FROM team_weeks WHERE id=(p_data->>'week_id')::uuid AND campus_id=scope;
  IF NOT FOUND THEN RETURN '{"error":"forbidden"}'; END IF;
  IF p_data->>'owner_id' IS NOT NULL AND NOT EXISTS(SELECT 1 FROM team_memberships WHERE profile_id=(p_data->>'owner_id')::uuid AND campus_id=scope AND active) THEN RETURN '{"error":"forbidden"}'; END IF;
  IF p_data->>'id' IS NOT NULL THEN
   SELECT t.author_id,t.version INTO rec FROM team_logs t WHERE id=(p_data->>'id')::uuid AND campus_id=scope FOR UPDATE;
   IF NOT FOUND OR (NOT reviewer AND rec.author_id<>p_actor) THEN RETURN '{"error":"forbidden"}'; END IF;
   IF rec.version IS DISTINCT FROM (p_data->>'version')::int THEN RETURN '{"error":"stale"}'; END IF;
   UPDATE team_logs SET title=btrim(p_data->>'title'),body=coalesce(p_data->>'body',''),owner_id=(p_data->>'owner_id')::uuid,due_at=(p_data->>'due_at')::timestamptz,
    status=coalesce(p_data->>'status','open'),private=coalesce((p_data->>'private')::boolean,p_data->>'kind'='incident'),version=version+1 WHERE id=(p_data->>'id')::uuid RETURNING id INTO rid;
  ELSE
   INSERT INTO team_logs(campus_id,week_id,author_id,kind,title,body,owner_id,due_at,private) VALUES(scope,w.id,p_actor,p_data->>'kind',btrim(p_data->>'title'),coalesce(p_data->>'body',''),(p_data->>'owner_id')::uuid,(p_data->>'due_at')::timestamptz,coalesce((p_data->>'private')::boolean,p_data->>'kind'='incident')) RETURNING id INTO rid;
  END IF;
  result:=jsonb_build_object('id',rid);
 ELSIF p_action='rule' THEN
  IF NOT adm THEN RETURN '{"error":"forbidden"}'; END IF;
  IF p_data->>'responsibility_id' IS NOT NULL AND NOT EXISTS(SELECT 1 FROM team_responsibilities WHERE id=(p_data->>'responsibility_id')::uuid AND campus_id=scope AND active) THEN RETURN '{"error":"forbidden"}'; END IF;
  IF coalesce(length(btrim(p_data->>'title')),0) NOT BETWEEN 1 AND 150 THEN RETURN '{"error":"invalid"}'; END IF;
  IF p_data->>'id' IS NOT NULL THEN
   SELECT version INTO n FROM team_reminder_rules WHERE id=(p_data->>'id')::uuid AND campus_id=scope FOR UPDATE;
   IF NOT FOUND THEN RETURN '{"error":"forbidden"}'; END IF;
   IF n IS DISTINCT FROM (p_data->>'version')::int THEN RETURN '{"error":"stale"}'; END IF;
   UPDATE team_reminder_rules SET title=btrim(p_data->>'title'),body=coalesce(p_data->>'body',''),responsibility_id=(p_data->>'responsibility_id')::uuid,
    weekdays=ARRAY(SELECT jsonb_array_elements_text(p_data->'weekdays')::int),minute_of_day=(p_data->>'minute_of_day')::int,
    outstanding_only=coalesce((p_data->>'outstanding_only')::boolean,true),enabled=coalesce((p_data->>'enabled')::boolean,true),version=version+1 WHERE id=(p_data->>'id')::uuid RETURNING id INTO rid;
  ELSE
   INSERT INTO team_reminder_rules(campus_id,title,body,responsibility_id,weekdays,minute_of_day,outstanding_only,enabled)
   VALUES(scope,btrim(p_data->>'title'),coalesce(p_data->>'body',''),(p_data->>'responsibility_id')::uuid,ARRAY(SELECT jsonb_array_elements_text(p_data->'weekdays')::int),(p_data->>'minute_of_day')::int,coalesce((p_data->>'outstanding_only')::boolean,true),coalesce((p_data->>'enabled')::boolean,true)) RETURNING id INTO rid;
  END IF;
  result:=jsonb_build_object('id',rid);
 ELSE RETURN '{"error":"invalid"}';
 END IF;
 INSERT INTO team_audit(campus_id,actor_id,request_id,action,payload,result,before_state) VALUES(scope,p_actor,p_request,p_action,p_data,result,before_state);
 RETURN result;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR check_violation OR not_null_violation OR invalid_datetime_format OR datetime_field_overflow THEN RETURN '{"error":"invalid"}';
 WHEN unique_violation THEN RETURN '{"error":"conflict"}';
END $$;
REVOKE ALL ON FUNCTION public.hg_team_member_flag(),public.hg_team_protect_flag(),public.hg_team_targets_valid(jsonb),public.hg_team_ensure_week(uuid,date),public.hg_team_workspace(uuid,uuid,text,jsonb,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_team_targets_valid(jsonb),public.hg_team_ensure_week(uuid,date),public.hg_team_workspace(uuid,uuid,text,jsonb,uuid) TO service_role;

-- Editable starting templates only; no accounts are enrolled by this migration.
INSERT INTO public.team_settings(campus_id) SELECT id FROM public.campuses WHERE is_active ON CONFLICT DO NOTHING;
INSERT INTO public.team_responsibilities(campus_id,name,description,targets) SELECT c.id,r->>'name',r->>'description',r->'targets' FROM public.campuses c CROSS JOIN jsonb_array_elements($templates$[{"name": "Operations Lead", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "5673331e-adb3-4361-a5d5-c7b13b4a90e4", "title": "Order fulfillment on-time rate", "direction": "higher", "unit": "percent", "target": 95.0, "tolerance": 1, "evidence_required": true}, {"id": "788bdd27-11d9-4d95-96e3-db68b808d47a", "title": "Incident resolution time (hrs)", "direction": "lower", "unit": "hours", "target": 48.0, "tolerance": 1, "evidence_required": true}, {"id": "a44f8a2f-434b-443d-937a-848600fa3132", "title": "Team weekly submission compliance", "direction": "higher", "unit": "percent", "target": 100.0, "tolerance": 1, "evidence_required": true}, {"id": "05fe430b-01b4-41d8-9ba5-6908e826a933", "title": "Customer complaint resolution time (hrs)", "direction": "lower", "unit": "hours", "target": 48.0, "tolerance": 1, "evidence_required": true}]}, {"name": "Kitchen / Fulfilment", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "c4e81ac1-41af-4aee-9342-f30b3022ccd5", "title": "Prep readiness on time", "direction": "higher", "unit": "percent", "target": 100.0, "tolerance": 1, "evidence_required": true}, {"id": "2a5481d1-b230-457f-9d07-191fb536dd81", "title": "Order accuracy", "direction": "higher", "unit": "percent", "target": 98.0, "tolerance": 1, "evidence_required": true}, {"id": "2d9d0b8d-fa95-4020-85e0-47f1104e7ef8", "title": "Quality pass rate", "direction": "higher", "unit": "percent", "target": 95.0, "tolerance": 1, "evidence_required": true}, {"id": "de8424da-b21e-4374-825e-876327d4a007", "title": "Waste/spoilage rate", "direction": "lower", "unit": "percent", "target": 5.0, "tolerance": 1, "evidence_required": true}]}, {"name": "Designer", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "0b18956a-9393-46e4-be47-79a74fa4f682", "title": "Weekly design output (count, excl. templates)", "direction": "higher", "unit": "count", "target": 3.0, "tolerance": 1, "evidence_required": true}, {"id": "f84c1971-5230-47d8-b687-75a23b8e72ad", "title": "Turnaround compliance (%)", "direction": "higher", "unit": "percent", "target": 90.0, "tolerance": 1, "evidence_required": true}, {"id": "a323f8dd-17f0-4264-b28b-fd23181a7172", "title": "Revision rounds per design (avg)", "direction": "lower", "unit": "count", "target": 2.0, "tolerance": 1, "evidence_required": true}, {"id": "5e3bbbcc-8c03-486f-9e94-e1ab564e3221", "title": "Off-brand corrections needed (count)", "direction": "lower", "unit": "count", "target": 0.0, "tolerance": 1, "evidence_required": true}]}, {"name": "Instagram / TikTok Manager", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "b9ced99c-5f27-4658-a673-8ccc173376fb", "title": "Comment/DM response rate", "direction": "higher", "unit": "percent", "target": 90.0, "tolerance": 1, "evidence_required": true}, {"id": "55de84d0-6605-4096-978d-1fa6af7cc300", "title": "Engagement/growth (month-over-month)", "direction": "higher", "unit": "percent", "target": 5.0, "tolerance": 1, "evidence_required": true}, {"id": "3b9da643-eed7-40ae-a30d-da2d7bc4f2c0", "title": "Ideas generated per week", "direction": "higher", "unit": "count", "target": 4.0, "tolerance": 1, "evidence_required": true}, {"id": "bc80bd56-dbfd-4db6-8f81-3cb2da02bc21", "title": "Content calendar adherence (weeks ahead)", "direction": "higher", "unit": "weeks", "target": 1.0, "tolerance": 1, "evidence_required": true}]}, {"name": "WhatsApp Manager", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "c109b548-bd70-49aa-a6e8-bc80b67aa849", "title": "Response rate (within 2hrs)", "direction": "higher", "unit": "hours", "target": 0.95, "tolerance": 1, "evidence_required": true}, {"id": "6c58b390-1de2-4f3f-a868-5eabcfcac6eb", "title": "Daily Status posting", "direction": "higher", "unit": "percent", "target": 100.0, "tolerance": 1, "evidence_required": true}, {"id": "26cf0a03-d9dc-4e3e-aa3a-72a0014c7497", "title": "Community engagement (month-over-month)", "direction": "higher", "unit": "count", "target": 0.05, "tolerance": 1, "evidence_required": true}, {"id": "5cc08327-86be-4514-b026-26713779c21d", "title": "Escalation speed (minutes)", "direction": "lower", "unit": "minutes", "target": 15.0, "tolerance": 1, "evidence_required": true}]}, {"name": "Brand Manager", "description": "Editable starting template for online brand/community coordination.", "targets": [{"id": "ab9729ec-25f0-460b-a32b-d5dab837993b", "title": "Next-week content ready for review", "target": 75, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}, {"id": "fc96a58b-01a6-4122-a588-754d372ed16e", "title": "Team submissions reviewed", "target": 100, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}, {"id": "bb1a11d1-584c-4a84-b279-74e73f7430dc", "title": "Unowned blockers", "target": 0, "unit": "count", "direction": "lower", "tolerance": 1, "evidence_required": true}]}, {"name": "Community Manager", "description": "Editable starting template for online brand/community coordination.", "targets": [{"id": "735c842c-c90a-419b-908b-5b23773e1648", "title": "Ambassador progress reviewed", "target": 100, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}, {"id": "f497c07a-1ea4-4db5-81c1-c55dbb7a97a1", "title": "Community replies within two hours", "target": 95, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}, {"id": "62d04fd0-182d-4f6e-9433-3d1432d86154", "title": "Next-week community content ready", "target": 75, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}]}]$templates$::jsonb) r WHERE c.is_active ON CONFLICT(campus_id,name) DO NOTHING;
UPDATE public.team_responsibilities SET reviewer_by_default=true WHERE name IN ('Brand Manager','Operations Lead');
INSERT INTO public.team_reminder_rules(campus_id,title,weekdays,minute_of_day) SELECT id,'This week: your next step',ARRAY[1],540 FROM public.campuses WHERE is_active;
INSERT INTO public.team_reminder_rules(campus_id,title,weekdays,minute_of_day) SELECT id,'Your team update is due today',ARRAY[4],900 FROM public.campuses WHERE is_active;
INSERT INTO public.team_reminder_rules(campus_id,responsibility_id,title,weekdays,minute_of_day,outstanding_only) SELECT campus_id,id,'Your community is waiting for today’s update',ARRAY[1,2,3,4,5,6],540,false FROM public.team_responsibilities WHERE name='WhatsApp Manager';

CREATE FUNCTION public.hg_team_due_candidates() RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE c record; day_wat date:=(now() AT TIME ZONE 'Africa/Lagos')::date; minutes integer; output jsonb;
BEGIN
 minutes:=extract(hour FROM now() AT TIME ZONE 'Africa/Lagos')::int*60+extract(minute FROM now() AT TIME ZONE 'Africa/Lagos')::int;
 FOR c IN SELECT DISTINCT m.campus_id FROM team_memberships m JOIN profiles p ON p.id=m.profile_id JOIN campuses cp ON cp.id=m.campus_id WHERE m.active AND p.is_active AND p.campus_id=m.campus_id AND cp.is_active LOOP
  PERFORM hg_team_ensure_week(c.campus_id,date_trunc('week',day_wat)::date);
  IF EXISTS(SELECT 1 FROM team_weeks WHERE campus_id=c.campus_id AND week_start=date_trunc('week',day_wat)::date AND due_at<=now()) THEN PERFORM hg_team_ensure_week(c.campus_id,date_trunc('week',day_wat)::date+7); END IF;
 END LOOP;
 WITH members AS (
 SELECT m.*,coalesce(nullif(p.nickname,''),split_part(p.full_name,' ',1),'friend') nickname,r.name responsibility,w.id week_id,w.due_at,w.reopened_until,w.version week_version,e.id entry_id,e.status
 FROM team_memberships m JOIN profiles p ON p.id=m.profile_id JOIN campuses cp ON cp.id=m.campus_id
 JOIN team_responsibilities r ON r.id=m.responsibility_id JOIN team_weeks w ON w.campus_id=m.campus_id AND w.week_start=date_trunc('week',day_wat)::date
 JOIN team_entries e ON e.week_id=w.id AND e.member_id=m.id WHERE m.active AND p.is_active AND p.campus_id=m.campus_id AND cp.is_active
 ), candidates AS (
 SELECT m.id member_id,m.profile_id user_id,m.campus_id,m.nickname,m.responsibility,m.week_id,m.entry_id,m.week_version,m.due_at,
 'reminder'::text kind,rule.title,rule.body,rule.id rule_id,rule.version rule_version,
 'rule:'||rule.id||':'||rule.version||':'||m.week_version||':'||day_wat notice_key
 FROM members m JOIN team_reminder_rules rule ON rule.campus_id=m.campus_id AND (rule.responsibility_id IS NULL OR rule.responsibility_id=m.responsibility_id)
 WHERE rule.enabled AND extract(isodow FROM day_wat)::int=ANY(rule.weekdays) AND minutes>=rule.minute_of_day AND minutes<rule.minute_of_day+120
 AND (NOT rule.outstanding_only OR (m.status IN ('draft','changes_requested') AND now()<greatest(m.due_at,coalesce(m.reopened_until,m.due_at))))
 UNION ALL
 SELECT m.id,m.profile_id,m.campus_id,m.nickname,m.responsibility,m.week_id,m.entry_id,m.week_version,m.due_at,
 'digest',NULL,NULL,NULL,NULL,'digest:'||day_wat FROM members m JOIN team_settings cfg ON cfg.campus_id=m.campus_id
 WHERE cfg.digest_enabled AND minutes>=cfg.digest_minute AND minutes<cfg.digest_minute+120
 ) SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') INTO output FROM (
 SELECT q.*,jsonb_build_object('members',(SELECT count(*) FROM team_memberships tm JOIN profiles tp ON tp.id=tm.profile_id WHERE tm.campus_id=q.campus_id AND tm.active AND tp.is_active AND tp.campus_id=tm.campus_id),
 'own_targets',(SELECT jsonb_array_length(targets) FROM team_entries WHERE id=q.entry_id),
 'own_reported',(SELECT count(*) FROM team_entries e CROSS JOIN LATERAL jsonb_each(e.results) v WHERE e.id=q.entry_id AND coalesce(v.value->>'actual','')<>''),
 'submitted',(SELECT count(*) FROM team_entries x JOIN team_memberships m ON m.id=x.member_id WHERE x.week_id=q.week_id AND m.active AND x.status IN ('submitted','approved')),
 'approved',(SELECT count(*) FROM team_entries x JOIN team_memberships m ON m.id=x.member_id WHERE x.week_id=q.week_id AND m.active AND x.status='approved'),
 'signups',(SELECT count(*) FROM profiles WHERE campus_id=q.campus_id AND role::text='student' AND created_at>=day_wat::timestamp AT TIME ZONE 'Africa/Lagos' AND created_at<(day_wat+1)::timestamp AT TIME ZONE 'Africa/Lagos')) counts
 FROM candidates q WHERE NOT EXISTS(SELECT 1 FROM team_notice_receipts n WHERE n.member_id=q.member_id AND n.notice_key=q.notice_key)
 ORDER BY q.campus_id,q.member_id,q.notice_key LIMIT 100) t;
 RETURN output;
END $$;

CREATE FUNCTION public.hg_team_notice_valid(p_user uuid,p_metadata jsonb) RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE m team_memberships%ROWTYPE; w team_weeks%ROWTYPE; rule team_reminder_rules%ROWTYPE;
BEGIN
 SELECT tm.* INTO m FROM team_memberships tm JOIN profiles p ON p.id=tm.profile_id JOIN campuses c ON c.id=tm.campus_id
 WHERE tm.id=(p_metadata->>'member_id')::uuid AND tm.profile_id=p_user AND tm.active AND p.is_active AND p.campus_id=tm.campus_id AND c.is_active;
 IF NOT FOUND OR (p_metadata->>'expires_at') IS NULL OR now()>=(p_metadata->>'expires_at')::timestamptz THEN RETURN false; END IF;
 SELECT * INTO w FROM team_weeks WHERE id=(p_metadata->>'week_id')::uuid AND campus_id=m.campus_id;
 IF NOT FOUND OR w.version IS DISTINCT FROM (p_metadata->>'week_version')::int THEN RETURN false; END IF;
 IF p_metadata->>'kind'='digest' THEN RETURN EXISTS(SELECT 1 FROM team_settings WHERE campus_id=m.campus_id AND digest_enabled); END IF;
 SELECT * INTO rule FROM team_reminder_rules WHERE id=(p_metadata->>'rule_id')::uuid AND campus_id=m.campus_id AND enabled;
 IF NOT FOUND OR rule.version IS DISTINCT FROM (p_metadata->>'rule_version')::int OR (rule.responsibility_id IS NOT NULL AND rule.responsibility_id<>m.responsibility_id) THEN RETURN false; END IF;
 RETURN NOT rule.outstanding_only OR (now()<greatest(w.due_at,coalesce(w.reopened_until,w.due_at)) AND EXISTS(SELECT 1 FROM team_entries WHERE week_id=w.id AND member_id=m.id AND status IN ('draft','changes_requested')));
EXCEPTION WHEN invalid_text_representation THEN RETURN false;
END $$;

CREATE FUNCTION public.hg_team_queue_notice(p_user uuid,p_metadata jsonb,p_key text,p_title text,p_body text) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE nid uuid:=gen_random_uuid(); added integer; mid uuid; campus uuid; channel_name text; first_notice boolean:=true;
BEGIN
 IF (p_metadata->>'expires_at')::timestamptz>now()+interval '121 minutes' THEN RETURN '{"error":"invalid"}'; END IF;
 IF NOT hg_team_notice_valid(p_user,p_metadata) THEN RETURN '{"skipped":true}'; END IF;
 IF length(p_title) NOT BETWEEN 1 AND 200 OR length(p_body) NOT BETWEEN 1 AND 12000 OR length(p_key) NOT BETWEEN 1 AND 250 THEN RETURN '{"error":"invalid"}'; END IF;
 mid:=(p_metadata->>'member_id')::uuid;
 SELECT campus_id INTO campus FROM team_memberships WHERE id=mid FOR SHARE;
 INSERT INTO team_notice_receipts(member_id,notice_key,notification_id) VALUES(mid,p_key,nid) ON CONFLICT DO NOTHING;
 GET DIAGNOSTICS added=ROW_COUNT;
 IF added=0 THEN RETURN '{"duplicate":true}'; END IF;
 FOREACH channel_name IN ARRAY CASE WHEN p_metadata->>'kind'='digest' THEN ARRAY['email'] ELSE ARRAY['in_app','push','email'] END LOOP
  INSERT INTO notifications(id,user_id,campus_id,title,body,type,channel,action_url,metadata)
  VALUES(CASE WHEN first_notice THEN nid ELSE gen_random_uuid() END,p_user,campus,p_title,p_body,
   CASE WHEN p_metadata->>'kind'='digest' THEN 'team_digest' ELSE 'team_reminder' END,channel_name,'/team',p_metadata||'{"_dispatch_version":1}'::jsonb);
  first_notice:=false;
 END LOOP;
 RETURN jsonb_build_object('queued',true,'notification_id',nid);
END $$;
REVOKE ALL ON FUNCTION public.hg_team_due_candidates(),public.hg_team_notice_valid(uuid,jsonb),public.hg_team_queue_notice(uuid,jsonb,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_team_due_candidates(),public.hg_team_notice_valid(uuid,jsonb),public.hg_team_queue_notice(uuid,jsonb,text,text,text) TO service_role;

CREATE FUNCTION public.hg_team_profile_flag() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 NEW.team_workspace:=NEW.is_active AND EXISTS(SELECT 1 FROM team_memberships WHERE profile_id=NEW.id AND campus_id=NEW.campus_id AND active);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.hg_team_profile_flag() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER team_profile_flag BEFORE UPDATE OF campus_id,is_active ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.hg_team_profile_flag();

UPDATE public.team_responsibilities SET targets=(SELECT jsonb_agg(t||jsonb_build_object('cadence',CASE WHEN name='WhatsApp Manager' THEN 'daily' ELSE 'weekly' END)) FROM jsonb_array_elements(targets) t);
UPDATE public.team_responsibilities SET targets=targets||jsonb_build_array(jsonb_build_object('id',gen_random_uuid(),'title','Views on today’s status','direction','higher','unit','count','target',0,'tolerance',0,'evidence_required',false,'cadence','daily','tracking_only',true)) WHERE name='WhatsApp Manager';
