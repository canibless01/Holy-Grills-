BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE c uuid:=gen_random_uuid();foreign_c uuid:=gen_random_uuid();dept uuid:=gen_random_uuid();other_dept uuid:=gen_random_uuid();a uuid:=gen_random_uuid();peer uuid:=gen_random_uuid();other uuid:=gen_random_uuid();faculty_only uuid:=gen_random_uuid();foreign_peer uuid:=gen_random_uuid();u uuid;result jsonb;today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
BEGIN
 INSERT INTO campuses(id,name,slug,is_active) VALUES(c,'[AUDIT rollback] Birthday A','audit-'||c,true),(foreign_c,'[AUDIT rollback] Birthday B','audit-'||foreign_c,true);
 INSERT INTO departments(id,name,slug,faculty,is_active) VALUES(dept,'Audit medicine','audit-'||dept,'Audit faculty',true),(other_dept,'Audit science','audit-'||other_dept,'Audit faculty',true);
 FOREACH u IN ARRAY ARRAY[a,peer,other,faculty_only,foreign_peer] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-birthday-'||u||'@example.invalid','{}');
  UPDATE profiles SET campus_id=c,is_active=true,push_enabled=true,email_notifications=true,department_id=dept,faculty='Audit faculty',department='Audit medicine',referral_code='HG'||left(replace(u::text,'-',''),16) WHERE id=u;
  INSERT INTO notification_preferences(user_id,campus_id,hp_updates,push_enabled,email_enabled) VALUES(u,c,true,true,true) ON CONFLICT(user_id) DO UPDATE SET hp_updates=true,push_enabled=true,email_enabled=true;
 END LOOP;
 UPDATE profiles SET date_of_birth=make_date(2000,extract(month FROM today)::integer,extract(day FROM today)::integer),phone='+2348000000000',nickname='Celebrant' WHERE id=a;
 UPDATE profiles SET department_id=other_dept,department='Audit science' WHERE id=other;
 UPDATE profiles SET department_id=null,department=null WHERE id=faculty_only;
 UPDATE profiles SET campus_id=foreign_c WHERE id=foreign_peer;
 INSERT INTO system_settings(key,value,is_public,campus_id) VALUES('campus_operations_email','{"recipients":["birthday-audit@example.invalid"],"paid_order_alerts":true,"abandoned_cart_alerts":true,"daily_report":true,"weekly_report":true,"abandoned_minutes":30,"birthday_report":true}',false,c);
 PERFORM set_config('hg.audit_birthday',jsonb_build_object('a',a,'peer',peer,'other',other,'faculty',faculty_only,'foreign',foreign_peer,'campus',c)::text,true);
 result:=public.hg_process_birthday(a,100);IF NOT coalesce((result->>'processed')::boolean,false) THEN RAISE EXCEPTION '%',result;END IF;
 result:=public.hg_process_birthday(a,999);IF NOT coalesce((result->>'replayed')::boolean,false) THEN RAISE EXCEPTION 'Birthday replay not recognized';END IF;
 IF (SELECT hp_balance FROM profiles WHERE id=a)<>100 THEN RAISE EXCEPTION 'Birthday grant duplicated or repriced';END IF;
 PERFORM public.hg_queue_birthday_reports(c);PERFORM public.hg_queue_birthday_reports(c);
 IF (SELECT count(*) FROM hg_internal.operations_emails WHERE campus_id=c AND kind='birthday_report')<>1 THEN RAISE EXCEPTION 'Monthly birthday digest duplicated';END IF;
 IF NOT EXISTS(SELECT 1 FROM hg_internal.operations_emails WHERE campus_id=c AND payload->'people'->0->>'faculty'='Audit faculty' AND payload->'people'->0->>'phone'='+2348000000000') THEN RAISE EXCEPTION 'Digest lacks outreach details';END IF;
END $$;
SET CONSTRAINTS ALL IMMEDIATE;
DO $$
DECLARE ids jsonb:=current_setting('hg.audit_birthday')::jsonb;n integer;
BEGIN
 SELECT count(*) INTO n FROM notifications WHERE user_id=(ids->>'peer')::uuid AND type='birthday_blast';IF n<>2 THEN RAISE EXCEPTION 'Department peer did not receive both channels: %',n;END IF;
 IF EXISTS(SELECT 1 FROM notifications WHERE user_id IN((ids->>'other')::uuid,(ids->>'faculty')::uuid,(ids->>'foreign')::uuid) AND type='birthday_blast') THEN RAISE EXCEPTION 'Birthday peer scope leaked';END IF;
 SELECT count(*) INTO n FROM notifications WHERE user_id=(ids->>'a')::uuid AND type='birthday_bonus';IF n<>3 THEN RAISE EXCEPTION 'Own birthday notice channels: %',n;END IF;
 IF EXISTS(SELECT 1 FROM notifications WHERE user_id=(ids->>'a')::uuid AND type='hp_balance_changed') THEN RAISE EXCEPTION 'Duplicate generic birthday balance notice';END IF;
 IF NOT EXISTS(SELECT 1 FROM notifications WHERE user_id=(ids->>'peer')::uuid AND action_url LIKE '/wallet?gift_to=%&birthday=%') THEN RAISE EXCEPTION 'Birthday gift destination missing';END IF;
 IF has_function_privilege('authenticated','public.hg_process_birthday(uuid,integer)','EXECUTE') OR has_table_privilege('authenticated','hg_internal.birthday_celebrations','SELECT') THEN RAISE EXCEPTION 'Birthday worker exposed';END IF;
END $$;
ROLLBACK;
