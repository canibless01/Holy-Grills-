BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.ss_assert(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Staff settings: %',label;END IF;END$$;
DO $$
DECLARE c uuid:=gen_random_uuid();other_c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();b uuid:=gen_random_uuid();sa uuid:=gen_random_uuid();student uuid:=gen_random_uuid();kitchen uuid:=gen_random_uuid();cm uuid:=gen_random_uuid();actor uuid;marker text:='audit_settings_'||replace(gen_random_uuid()::text,'-','');n integer;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Settings','audit-settings-'||c),(other_c,'[AUDIT rollback] Foreign','audit-settings-'||other_c);
 FOREACH actor IN ARRAY ARRAY[a,b,sa,student,kitchen,cm] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(actor,'audit-settings-'||actor||'@example.invalid','{"full_name":"[AUDIT rollback] Settings"}');
  UPDATE profiles SET campus_id=c,role='student' WHERE id=actor;
 END LOOP;
 UPDATE profiles SET role='admin' WHERE id=a;UPDATE profiles SET role='admin',campus_id=other_c WHERE id=b;
 UPDATE profiles SET role='super_admin' WHERE id=sa;UPDATE profiles SET role='kitchen' WHERE id=kitchen;UPDATE profiles SET role='community_manager' WHERE id=cm;
 INSERT INTO system_settings(key,value,campus_id,is_public) VALUES(marker,'7',c,false),(marker,'8',other_c,false),(marker,'9',NULL,false),(marker||'_public','13',NULL,true),('welcome_bonus_hp','25',c,false);
 INSERT INTO kitchen_settings(key,value,campus_id) VALUES(marker,'initial',c);
 INSERT INTO feature_flags(feature_name,is_active,campus_id) VALUES(marker,true,NULL),(marker,false,c);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',sa)::text,true);PERFORM set_config('role','authenticated',true);
 PERFORM pg_temp.ss_assert(hg_is_admin() AND hg_current_user_role()='super_admin','active super admin unchanged');
 UPDATE system_settings SET value='10' WHERE key=marker AND campus_id IS NULL;GET DIAGNOSTICS n=ROW_COUNT;
 PERFORM pg_temp.ss_assert(n=1,'super admin global edit');
 UPDATE feature_flags SET is_active=false WHERE feature_name=marker AND campus_id IS NULL;
 PERFORM pg_temp.ss_assert((SELECT NOT is_active FROM feature_flags WHERE feature_name=marker AND campus_id=c),'campus override preserved');
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);PERFORM set_config('role','authenticated',true);
 PERFORM pg_temp.ss_assert(hg_is_admin() AND hg_current_user_role()='admin','active campus admin unchanged');
 PERFORM pg_temp.ss_assert((SELECT count(*)=1 FROM system_settings WHERE key=marker),'private rows scope to own campus');
 UPDATE system_settings SET value='11' WHERE key=marker AND campus_id=c;GET DIAGNOSTICS n=ROW_COUNT;PERFORM pg_temp.ss_assert(n=1,'own campus edit');
 UPDATE system_settings SET value='12' WHERE key=marker AND (campus_id IS NULL OR campus_id=other_c);GET DIAGNOSTICS n=ROW_COUNT;PERFORM pg_temp.ss_assert(n=0,'global and foreign settings denied');
 UPDATE feature_flags SET is_active=true WHERE feature_name=marker;GET DIAGNOSTICS n=ROW_COUNT;PERFORM pg_temp.ss_assert(n=0,'ordinary admin cannot change release switches');
 BEGIN UPDATE system_settings SET value='-1' WHERE key='welcome_bonus_hp' AND campus_id=c;RAISE EXCEPTION 'invalid setting accepted';EXCEPTION WHEN OTHERS THEN IF SQLERRM='invalid setting accepted' THEN RAISE;END IF;END;
 PERFORM pg_temp.ss_assert((SELECT value='25'::jsonb FROM system_settings WHERE key='welcome_bonus_hp' AND campus_id=c),'invalid reward setting leaves original value');
 PERFORM set_config('role','none',true);
 FOREACH actor IN ARRAY ARRAY[student,cm] LOOP
  PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
  PERFORM pg_temp.ss_assert(NOT EXISTS(SELECT 1 FROM system_settings WHERE key=marker),'student/community manager cannot read private config');
  UPDATE system_settings SET value='14' WHERE key=marker;GET DIAGNOSTICS n=ROW_COUNT;PERFORM pg_temp.ss_assert(n=0,'student/community manager cannot write config');
  PERFORM pg_temp.ss_assert(EXISTS(SELECT 1 FROM system_settings WHERE key=marker||'_public'),'ordinary public config remains visible');
  PERFORM set_config('role','none',true);
 END LOOP;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',kitchen)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE kitchen_settings SET value='allowed' WHERE key=marker AND campus_id=c;GET DIAGNOSTICS n=ROW_COUNT;PERFORM pg_temp.ss_assert(n=1,'active kitchen can manage own settings');
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE profiles SET is_active=false WHERE id IN(kitchen,a,sa);
 FOREACH actor IN ARRAY ARRAY[kitchen,a,sa] LOOP
  -- Reuse the same JWT identity: only the persisted active bit changed.
  PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
  PERFORM pg_temp.ss_assert(NOT hg_is_admin() AND hg_current_user_role() IS NULL,'old access token loses elevated role after deactivation');
  UPDATE kitchen_settings SET value='forbidden' WHERE key=marker;GET DIAGNOSTICS n=ROW_COUNT;PERFORM pg_temp.ss_assert(n=0,'inactive staff cannot edit kitchen settings');
  UPDATE system_settings SET value='15' WHERE key=marker;GET DIAGNOSTICS n=ROW_COUNT;PERFORM pg_temp.ss_assert(n=0,'inactive staff cannot edit system settings');
  PERFORM set_config('role','none',true);
 END LOOP;
END$$;
ROLLBACK;
SELECT 'passed: active super/campus admin, global versus campus writes, private config, public reads, student/community-manager denial, invalid reward settings and deactivated existing-token kitchen/admin policy boundaries; all fixtures rolled back' evidence;
