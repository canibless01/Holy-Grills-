BEGIN;
DO $$
DECLARE c uuid:=gen_random_uuid();other uuid:=gen_random_uuid();boss uuid:=gen_random_uuid();admin uuid:=gen_random_uuid();student uuid:=gen_random_uuid();cid uuid:=gen_random_uuid();r jsonb;
BEGIN
 INSERT INTO campuses(id,name,slug,is_active) VALUES(c,'Local observer','local-'||c,true),(other,'Foreign observer','local-'||other,true);
 INSERT INTO auth.users(id,email) SELECT id,id||'@example.invalid' FROM unnest(ARRAY[boss,admin,student]) id;
 INSERT INTO profiles(id,email,full_name,role,campus_id,is_active) SELECT id,id||'@example.invalid','Local observer',CASE WHEN id=boss THEN 'super_admin' WHEN id=admin THEN 'admin' ELSE 'student' END::user_role,CASE WHEN id=student THEN c ELSE other END,true FROM unnest(ARRAY[boss,admin,student]) id ON CONFLICT(id) DO UPDATE SET role=excluded.role,campus_id=excluded.campus_id,is_active=true;
 INSERT INTO hg_internal.engagement_campaigns(id,campus_id,name,start_date,steps,is_active,updated_by) VALUES(cid,c,'Local observe',current_date-1,'[]',true,boss);
 INSERT INTO device_tokens(user_id,token,platform) VALUES(boss,'local-invalid','web'),(admin,gen_random_uuid()::text,'web'),(student,gen_random_uuid()::text,'web');
 r:=hg_engagement_campaign_recipients(cid,'morning');
 IF jsonb_array_length(r)<>1 THEN RAISE EXCEPTION 'staff enrolled without explicit observer'; END IF;
 INSERT INTO hg_internal.engagement_campaign_observers(campaign_id,user_id,added_by) VALUES(cid,boss,boss),(cid,admin,boss);
 IF hg_engagement_cycle_owner(cid,boss) IS NOT TRUE OR hg_engagement_cycle_owner(cid,admin) IS TRUE THEN RAISE EXCEPTION 'observer campus role guard'; END IF;
 UPDATE device_tokens SET token=gen_random_uuid()::text WHERE user_id=boss;
 r:=hg_engagement_campaign_recipients(cid,'morning');
 IF jsonb_array_length(r)<>2 THEN RAISE EXCEPTION 'owner missing from recipient page: %',r; END IF;
 IF hg_engagement_campaign_notice_valid(cid,1,boss) IS NOT TRUE THEN RAISE EXCEPTION 'owner validation'; END IF;
 INSERT INTO notification_preferences(user_id,promotions) VALUES(boss,false);
 r:=hg_engagement_campaign_recipients(cid,'morning');
 IF jsonb_array_length(r)<>1 THEN RAISE EXCEPTION 'observer optout bypass'; END IF;
 DELETE FROM hg_internal.engagement_campaign_observers WHERE campaign_id=cid;
 IF hg_engagement_campaign_notice_valid(cid,1,boss) IS TRUE THEN RAISE EXCEPTION 'removed observer still valid'; END IF;
 IF has_function_privilege('authenticated','hg_engagement_cycle_owner(uuid,uuid)','EXECUTE') OR has_table_privilege('authenticated','hg_internal.engagement_campaign_observers','INSERT') THEN RAISE EXCEPTION 'self enrolment permitted'; END IF;
END $$;
ROLLBACK;
SELECT 'passed explicit-owner preview, global super scope, foreign-campus admin rejection, optouts, removal and private grants; rolled back' AS evidence;
