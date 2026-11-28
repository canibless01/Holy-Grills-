BEGIN;
INSERT INTO profiles(id,campus_id,role,full_name) VALUES
('10000001-0000-0000-0000-000000000001','00000001-0000-0000-0000-000000000001','admin','Admin'),
('10000001-0000-0000-0000-000000000002','00000001-0000-0000-0000-000000000001','student','Designer'),
('10000001-0000-0000-0000-000000000003','00000001-0000-0000-0000-000000000001','community_manager','Brand lead'),
('10000001-0000-0000-0000-000000000004','00000001-0000-0000-0000-000000000002','admin','Foreign admin'),
('10000001-0000-0000-0000-000000000005','00000001-0000-0000-0000-000000000001','student','Unassigned student');
DO $$
DECLARE a uuid:='10000001-0000-0000-0000-000000000001'; u uuid:='10000001-0000-0000-0000-000000000002'; lead uuid:='10000001-0000-0000-0000-000000000003';
 c uuid:='00000001-0000-0000-0000-000000000001'; r jsonb; rid uuid; mid uuid; wid uuid; eid uuid; targets jsonb; vals jsonb; req uuid; data jsonb; ver int; rule_id uuid; meta jsonb;
BEGIN
 IF (SELECT count(*) FROM team_responsibilities WHERE campus_id=c)<>7 THEN RAISE EXCEPTION 'default templates missing'; END IF;
 SELECT id INTO rid FROM team_responsibilities WHERE campus_id=c AND name='Designer';
 r:=hg_team_workspace(a,c,'member',jsonb_build_object('profile_id',u,'responsibility_id',rid),gen_random_uuid());
 IF r ? 'error' THEN RAISE EXCEPTION 'membership %',r; END IF; mid:=(r->>'id')::uuid;
 IF (SELECT role FROM profiles WHERE id=u)<>'student' OR NOT (SELECT team_workspace FROM profiles WHERE id=u) THEN RAISE EXCEPTION 'commerce identity changed'; END IF;
 r:=hg_team_workspace(a,c,'member',jsonb_build_object('profile_id',lead,'responsibility_id',rid,'can_review',true),gen_random_uuid());
 IF r ? 'error' THEN RAISE EXCEPTION 'review membership %',r; END IF;
 r:=hg_team_workspace('10000001-0000-0000-0000-000000000005',c,'snapshot');
 IF r->>'error'<>'forbidden' THEN RAISE EXCEPTION 'unassigned member access'; END IF;
 r:=hg_team_workspace('10000001-0000-0000-0000-000000000004',c,'snapshot');
 IF r->>'error'<>'forbidden' THEN RAISE EXCEPTION 'foreign admin access'; END IF;
 r:=hg_team_workspace(lead,c,'member',jsonb_build_object('profile_id',u,'responsibility_id',rid),gen_random_uuid());
 IF r->>'error'<>'forbidden' THEN RAISE EXCEPTION 'reviewer escalated membership'; END IF;
 SELECT id INTO wid FROM team_weeks WHERE campus_id=c AND week_start=date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date;
 UPDATE team_weeks SET due_at=now()+interval '1 day' WHERE id=wid;
 SELECT id,team_entries.targets INTO eid,targets FROM team_entries WHERE member_id=mid AND week_id=wid;
 SELECT jsonb_object_agg(t->>'id',jsonb_build_object('actual',t->'target','evidence','https://example.test/proof')) INTO vals FROM jsonb_array_elements(targets) t;
 data:=jsonb_build_object('id',eid,'version',1,'results',vals,'narrative','{}'::jsonb,'content','[]'::jsonb); req:=gen_random_uuid();
 r:=hg_team_workspace(u,c,'save',data,req); IF r->>'version'<>'2' THEN RAISE EXCEPTION 'save %',r; END IF;
 IF hg_team_workspace(u,c,'save',data,req)<>r THEN RAISE EXCEPTION 'idempotent repeat'; END IF;
 IF (hg_team_workspace(u,c,'save',data||'{"version":2}',req))->>'error'<>'request_conflict' THEN RAISE EXCEPTION 'reused request content'; END IF;
 IF (hg_team_workspace(u,c,'save',data,gen_random_uuid()))->>'error'<>'stale' THEN RAISE EXCEPTION 'stale update'; END IF;
 IF (hg_team_workspace(lead,c,'save',data||'{"version":2}',gen_random_uuid()))->>'error'<>'forbidden' THEN RAISE EXCEPTION 'other member mutation'; END IF;
 r:=hg_team_workspace(u,c,'submit',data||'{"version":2,"results":{}}',gen_random_uuid()); IF r->>'error'<>'incomplete' THEN RAISE EXCEPTION 'incomplete accepted %',r; END IF;
 r:=hg_team_workspace(u,c,'submit',data||'{"version":2}',gen_random_uuid()); IF r->>'version'<>'3' THEN RAISE EXCEPTION 'submit %',r; END IF;
 IF (hg_team_workspace(u,c,'save',data||'{"version":3}',gen_random_uuid()))->>'version'<>'4' THEN RAISE EXCEPTION 'submitted update should stay editable'; END IF;
 r:=hg_team_workspace(u,c,'submit',data||'{"version":4}',gen_random_uuid()); IF r->>'version'<>'5' THEN RAISE EXCEPTION 'resubmit'; END IF;
 r:=hg_team_workspace(lead,c,'review',jsonb_build_object('id',eid,'version',5,'status','changes_requested','feedback','Add detail'),gen_random_uuid());
 IF r->>'version'<>'6' THEN RAISE EXCEPTION 'review %',r; END IF;
 UPDATE team_weeks SET due_at=now()-interval '1 second' WHERE id=wid;
 IF (hg_team_workspace(u,c,'save',data||'{"version":6}',gen_random_uuid()))->>'error'<>'closed' THEN RAISE EXCEPTION 'late save accepted'; END IF;
 SELECT version INTO ver FROM team_weeks WHERE id=wid;
 r:=hg_team_workspace(lead,c,'week',jsonb_build_object('week_start',date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date,'version',ver,'due_at',now()-interval '1 second','meeting_at',now(),'reopened_until',now()+interval '1 day','reason','Correction approved'),gen_random_uuid());
 IF (SELECT reopened_until FROM team_weeks WHERE id=wid) IS NOT NULL THEN RAISE EXCEPTION 'reviewer reopened deadline'; END IF;
 SELECT version INTO ver FROM team_weeks WHERE id=wid;
 r:=hg_team_workspace(a,c,'week',jsonb_build_object('week_start',date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date,'version',ver,'due_at',now()-interval '1 second','meeting_at',now(),'reopened_until',now()+interval '1 day','reason','Correction approved'),gen_random_uuid());
 IF r ? 'error' THEN RAISE EXCEPTION 'admin reopening %',r; END IF;
 IF (hg_team_workspace(u,c,'save',data||'{"version":6}',gen_random_uuid()))->>'version'<>'7' THEN RAISE EXCEPTION 'reopened save'; END IF;
 IF (SELECT count(*) FROM team_audit WHERE action='week' AND actor_id=a)=0 THEN RAISE EXCEPTION 'no reopening audit'; END IF;
 SELECT id,version INTO rule_id,ver FROM team_reminder_rules WHERE campus_id=c AND outstanding_only LIMIT 1;
 meta:=jsonb_build_object('member_id',mid,'week_id',wid,'week_version',(SELECT version FROM team_weeks WHERE id=wid),'kind','reminder','rule_id',rule_id,'rule_version',ver,'expires_at',now()+interval '1 hour');
 r:=hg_team_queue_notice(u,meta,'test-dedup','Test title','Test body'); IF NOT (r->>'queued')::boolean THEN RAISE EXCEPTION 'queue %',r; END IF;
 IF NOT (hg_team_queue_notice(u,meta,'test-dedup','Test title','Test body')->>'duplicate')::boolean THEN RAISE EXCEPTION 'duplicate queue'; END IF;
 IF (SELECT count(*) FROM notifications WHERE user_id=u)<>3 THEN RAISE EXCEPTION 'distinct channel rows missing'; END IF;
 UPDATE team_memberships SET active=false WHERE id=mid;
 IF hg_team_notice_valid(u,meta) OR (SELECT team_workspace FROM profiles WHERE id=u) THEN RAISE EXCEPTION 'removed member retained access'; END IF;
 IF has_function_privilege('authenticated','hg_team_workspace(uuid,uuid,text,jsonb,uuid)','EXECUTE') OR has_function_privilege('authenticated','hg_team_seed_campus(uuid)','EXECUTE') OR has_table_privilege('anon','team_entries','SELECT') THEN RAISE EXCEPTION 'public access'; END IF;
 -- A campus created AFTER the first migration has no seed row; the backfill
 -- function must repair it without touching an already-configured campus.
 INSERT INTO campuses(id,name) VALUES('00000002-0000-0000-0000-000000000002','Late campus');
 DELETE FROM team_settings WHERE campus_id='00000002-0000-0000-0000-000000000002';
 DELETE FROM team_reminder_rules WHERE campus_id='00000002-0000-0000-0000-000000000002';
 DELETE FROM team_responsibilities WHERE campus_id='00000002-0000-0000-0000-000000000002';
 IF NOT hg_team_seed_campus('00000002-0000-0000-0000-000000000002') THEN RAISE EXCEPTION 'late campus not seeded'; END IF;
 IF (SELECT count(*) FROM team_responsibilities WHERE campus_id='00000002-0000-0000-0000-000000000002')<>7
  OR NOT EXISTS(SELECT 1 FROM team_settings WHERE campus_id='00000002-0000-0000-0000-000000000002')
  OR (SELECT count(*) FROM team_reminder_rules WHERE campus_id='00000002-0000-0000-0000-000000000002')<3 THEN RAISE EXCEPTION 'late campus seed incomplete'; END IF;
 UPDATE team_settings SET coverage_target=64,version=version+1 WHERE campus_id='00000002-0000-0000-0000-000000000002';
 IF NOT hg_team_seed_campus('00000002-0000-0000-0000-000000000002') THEN RAISE EXCEPTION 'seed is not idempotent'; END IF;
 IF (SELECT coverage_target FROM team_settings WHERE campus_id='00000002-0000-0000-0000-000000000002')<>64 THEN RAISE EXCEPTION 'seed overwrote admin settings'; END IF;
 IF (SELECT count(*) FROM team_reminder_rules WHERE campus_id='00000002-0000-0000-0000-000000000002')<>3 THEN RAISE EXCEPTION 'seed duplicated reminders'; END IF;
 IF hg_team_seed_campus(NULL) OR hg_team_seed_campus('00000002-0000-0000-0000-ffffffffffff') THEN RAISE EXCEPTION 'seed accepted an unknown campus'; END IF;
 IF hg_team_targets_valid('[{"id":"20000001-0000-0000-0000-000000000001","title":"Bad","target":null,"tolerance":1,"direction":"higher","unit":"count"}]') THEN RAISE EXCEPTION 'null target'; END IF;
END $$;
ROLLBACK;
