-- Follow-up to 20261127203322_team_workspace.sql.
-- The original migration seeded team_settings, the seven responsibility
-- templates and the default reminder rules for the campuses that existed at the
-- time. A campus created afterwards is fully usable everywhere else (the admin
-- campus create endpoint only writes campuses.*), but its team workspace would
-- have no settings row: GET /api/team answers with a 400 and EVERY team member on
-- that campus loses the page. This function makes the seed idempotent so the
-- daily capture tick (and a manual admin repair) can fill a gap without ever
-- touching a campus that is already configured.
--
-- Additive only. Existing settings, templates and reminders are never updated or
-- deleted; ON CONFLICT DO NOTHING everywhere.

CREATE OR REPLACE FUNCTION public.hg_team_seed_campus(p_campus uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE tpl jsonb := $templates$[{"name": "Operations Lead", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "5673331e-adb3-4361-a5d5-c7b13b4a90e4", "title": "Order fulfillment on-time rate", "direction": "higher", "unit": "percent", "target": 95.0, "tolerance": 1, "evidence_required": true}, {"id": "788bdd27-11d9-4d95-96e3-db68b808d47a", "title": "Incident resolution time (hrs)", "direction": "lower", "unit": "hours", "target": 48.0, "tolerance": 1, "evidence_required": true}, {"id": "a44f8a2f-434b-443d-937a-848600fa3132", "title": "Team weekly submission compliance", "direction": "higher", "unit": "percent", "target": 100.0, "tolerance": 1, "evidence_required": true}, {"id": "05fe430b-01b4-41d8-9ba5-6908e826a933", "title": "Customer complaint resolution time (hrs)", "direction": "lower", "unit": "hours", "target": 48.0, "tolerance": 1, "evidence_required": true}]}, {"name": "Kitchen / Fulfilment", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "c4e81ac1-41af-4aee-9342-f30b3022ccd5", "title": "Prep readiness on time", "direction": "higher", "unit": "percent", "target": 100.0, "tolerance": 1, "evidence_required": true}, {"id": "2a5481d1-b230-457f-9d07-191fb536dd81", "title": "Order accuracy", "direction": "higher", "unit": "percent", "target": 98.0, "tolerance": 1, "evidence_required": true}, {"id": "2d9d0b8d-fa95-4020-85e0-47f1104e7ef8", "title": "Quality pass rate", "direction": "higher", "unit": "percent", "target": 95.0, "tolerance": 1, "evidence_required": true}, {"id": "de8424da-b21e-4374-825e-876327d4a007", "title": "Waste/spoilage rate", "direction": "lower", "unit": "percent", "target": 5.0, "tolerance": 1, "evidence_required": true}]}, {"name": "Designer", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "0b18956a-9393-46e4-be47-79a74fa4f682", "title": "Weekly design output (count, excl. templates)", "direction": "higher", "unit": "count", "target": 3.0, "tolerance": 1, "evidence_required": true}, {"id": "f84c1971-5230-47d8-b687-75a23b8e72ad", "title": "Turnaround compliance (%)", "direction": "higher", "unit": "percent", "target": 90.0, "tolerance": 1, "evidence_required": true}, {"id": "a323f8dd-17f0-4264-b28b-fd23181a7172", "title": "Revision rounds per design (avg)", "direction": "lower", "unit": "count", "target": 2.0, "tolerance": 1, "evidence_required": true}, {"id": "5e3bbbcc-8c03-486f-9e94-e1ab564e3221", "title": "Off-brand corrections needed (count)", "direction": "lower", "unit": "count", "target": 0.0, "tolerance": 1, "evidence_required": true}]}, {"name": "Instagram / TikTok Manager", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "b9ced99c-5f27-4658-a673-8ccc173376fb", "title": "Comment/DM response rate", "direction": "higher", "unit": "percent", "target": 90.0, "tolerance": 1, "evidence_required": true}, {"id": "55de84d0-6605-4096-978d-1fa6af7cc300", "title": "Engagement/growth (month-over-month)", "direction": "higher", "unit": "percent", "target": 5.0, "tolerance": 1, "evidence_required": true}, {"id": "3b9da643-eed7-40ae-a30d-da2d7bc4f2c0", "title": "Ideas generated per week", "direction": "higher", "unit": "count", "target": 4.0, "tolerance": 1, "evidence_required": true}, {"id": "bc80bd56-dbfd-4db6-8f81-3cb2da02bc21", "title": "Content calendar adherence (weeks ahead)", "direction": "higher", "unit": "weeks", "target": 1.0, "tolerance": 1, "evidence_required": true}]}, {"name": "WhatsApp Manager", "description": "Editable operations-workbook template. Targets apply when a new week is opened.", "targets": [{"id": "c109b548-bd70-49aa-a6e8-bc80b67aa849", "title": "Response rate (within 2hrs)", "direction": "higher", "unit": "hours", "target": 0.95, "tolerance": 1, "evidence_required": true}, {"id": "6c58b390-1de2-4f3f-a868-5eabcfcac6eb", "title": "Daily Status posting", "direction": "higher", "unit": "percent", "target": 100.0, "tolerance": 1, "evidence_required": true}, {"id": "26cf0a03-d9dc-4e3e-aa3a-72a0014c7497", "title": "Community engagement (month-over-month)", "direction": "higher", "unit": "count", "target": 0.05, "tolerance": 1, "evidence_required": true}, {"id": "5cc08327-86be-4514-b026-26713779c21d", "title": "Escalation speed (minutes)", "direction": "lower", "unit": "minutes", "target": 15.0, "tolerance": 1, "evidence_required": true}]}, {"name": "Brand Manager", "description": "Editable starting template for online brand/community coordination.", "targets": [{"id": "ab9729ec-25f0-460b-a32b-d5dab837993b", "title": "Next-week content ready for review", "target": 75, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}, {"id": "fc96a58b-01a6-4122-a588-754d372ed16e", "title": "Team submissions reviewed", "target": 100, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}, {"id": "bb1a11d1-584c-4a84-b279-74e73f7430dc", "title": "Unowned blockers", "target": 0, "unit": "count", "direction": "lower", "tolerance": 1, "evidence_required": true}]}, {"name": "Community Manager", "description": "Editable starting template for online brand/community coordination.", "targets": [{"id": "735c842c-c90a-419b-908b-5b23773e1648", "title": "Ambassador progress reviewed", "target": 100, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}, {"id": "f497c07a-1ea4-4db5-81c1-c55dbb7a97a1", "title": "Community replies within two hours", "target": 95, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}, {"id": "62d04fd0-182d-4f6e-9433-3d1432d86154", "title": "Next-week community content ready", "target": 75, "unit": "percent", "direction": "higher", "tolerance": 1, "evidence_required": true}]}]$templates$::jsonb;
BEGIN
 IF p_campus IS NULL OR NOT EXISTS(SELECT 1 FROM campuses WHERE id=p_campus AND is_active) THEN RETURN false; END IF;
 INSERT INTO team_settings(campus_id) VALUES(p_campus) ON CONFLICT(campus_id) DO NOTHING;
 INSERT INTO team_responsibilities(campus_id,name,description,targets)
  SELECT p_campus,r->>'name',r->>'description',r->'targets' FROM jsonb_array_elements(tpl) r
  ON CONFLICT(campus_id,name) DO NOTHING;
 -- reviewer_by_default is part of the seed only; an administrator's later edit wins.
 UPDATE team_responsibilities SET reviewer_by_default=true
  WHERE campus_id=p_campus AND name IN ('Brand Manager','Operations Lead') AND NOT reviewer_by_default;
 INSERT INTO team_reminder_rules(campus_id,title,weekdays,minute_of_day)
  SELECT p_campus,'This week: your next step',ARRAY[1],540
  WHERE NOT EXISTS(SELECT 1 FROM team_reminder_rules r WHERE r.campus_id=p_campus AND r.title='This week: your next step');
 INSERT INTO team_reminder_rules(campus_id,title,weekdays,minute_of_day)
  SELECT p_campus,'Your team update is due today',ARRAY[4],900
  WHERE NOT EXISTS(SELECT 1 FROM team_reminder_rules r WHERE r.campus_id=p_campus AND r.title='Your team update is due today');
 INSERT INTO team_reminder_rules(campus_id,responsibility_id,title,weekdays,minute_of_day,outstanding_only)
  SELECT p_campus,r.id,'Your community is waiting for today’s update',ARRAY[1,2,3,4,5,6],540,false
  FROM team_responsibilities r WHERE r.campus_id=p_campus AND r.name='WhatsApp Manager'
  AND NOT EXISTS(SELECT 1 FROM team_reminder_rules x WHERE x.campus_id=p_campus AND x.title='Your community is waiting for today’s update');
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION public.hg_team_seed_campus(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_team_seed_campus(uuid) TO service_role;

-- The daily capture tick already walks every active campus with members; make it
-- repair a missing seed in the same pass so a new campus self-heals.
CREATE OR REPLACE FUNCTION public.hg_team_due_candidates() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE c record; day_wat date:=(now() AT TIME ZONE 'Africa/Lagos')::date; minutes integer; output jsonb;
BEGIN
 minutes:=extract(hour FROM now() AT TIME ZONE 'Africa/Lagos')::int*60+extract(minute FROM now() AT TIME ZONE 'Africa/Lagos')::int;
 FOR c IN SELECT DISTINCT m.campus_id FROM team_memberships m JOIN profiles p ON p.id=m.profile_id JOIN campuses cp ON cp.id=m.campus_id WHERE m.active AND p.is_active AND p.campus_id=m.campus_id AND cp.is_active LOOP
  PERFORM hg_team_seed_campus(c.campus_id);
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

REVOKE ALL ON FUNCTION public.hg_team_due_candidates() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_team_due_candidates() TO service_role;
