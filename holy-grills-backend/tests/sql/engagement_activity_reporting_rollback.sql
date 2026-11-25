BEGIN;
DO $$
DECLARE c uuid:=gen_random_uuid();c2 uuid:=gen_random_uuid();manager uuid:=gen_random_uuid();student uuid:=gen_random_uuid();boss uuid:=gen_random_uuid();visitor uuid:=gen_random_uuid();eid uuid:=gen_random_uuid();oid uuid:=gen_random_uuid();r jsonb;t timestamptz:=date_trunc('week',now() AT TIME ZONE 'Africa/Lagos') AT TIME ZONE 'Africa/Lagos';
BEGIN
 INSERT INTO campuses(id,name,slug,is_active) VALUES(c,'Local activity','local-'||c,true),(c2,'Foreign activity','local-'||c2,true);
 INSERT INTO auth.users(id,email) SELECT id,id||'@example.invalid' FROM unnest(ARRAY[manager,student,boss]) id;
 INSERT INTO profiles(id,email,full_name,role,campus_id,is_active,last_seen_at) SELECT id,id||'@example.invalid','Local activity',CASE WHEN id=manager THEN 'admin' WHEN id=boss THEN 'super_admin' ELSE 'student' END::user_role,c,true,now() FROM unnest(ARRAY[manager,student,boss]) id ON CONFLICT(id) DO UPDATE SET role=excluded.role,campus_id=excluded.campus_id,is_active=true,last_seen_at=excluded.last_seen_at;
 r:=hg_record_engagement_page(eid,visitor,null,c,'/menu');
 r:=hg_record_engagement_page(eid,visitor,null,c,'/menu');
 IF (SELECT count(*) FROM hg_internal.engagement_page_events WHERE campus_id=c)<>1 THEN RAISE EXCEPTION 'duplicate receipt'; END IF;
 r:=hg_record_engagement_page(gen_random_uuid(),visitor,student,c2,'/menu');
 IF r->>'error'<>'forbidden' THEN RAISE EXCEPTION 'spoofed campus'; END IF;
 r:=hg_record_engagement_page(gen_random_uuid(),visitor,boss,c,'/menu');
 IF r->>'ignored_staff'<>'true' THEN RAISE EXCEPTION 'staff included'; END IF;
 r:=hg_record_engagement_page(gen_random_uuid(),visitor,null,c,'/menu?claim=private');
 IF r->>'error'<>'invalid' THEN RAISE EXCEPTION 'URL secret stored'; END IF;
 r:=hg_record_engagement_page(gen_random_uuid(),visitor,student,c,'/checkout');
 INSERT INTO orders(id,user_id,campus_id,subtotal,delivery_fee,total_amount,status,payment_status,paid_at)
 VALUES(oid,student,c,2000,500,2500,'received','paid',now()+interval '1 second');
 INSERT INTO login_streaks(user_id,campus_id,last_week_receipt) VALUES(student,c,jsonb_build_object('week_start',(t AT TIME ZONE 'Africa/Lagos')::date-7,'previous_week_completed',true));
 r:=hg_engagement_report(manager,c,t,t+interval '7 days');
 IF r->>'error' IS NOT NULL OR (r->>'page_views')::int<>2 OR (r->>'dau')::int<>1 OR (r->'funnel'->>'paid_linked_accounts')::int<>1 OR (r->'streaks'->>'qualified_weeks')::int<>1 THEN RAISE EXCEPTION 'summary mismatch: %',r; END IF;
 r:=hg_engagement_report(manager,c2,t,t+interval '7 days');
 IF r->>'error'<>'forbidden' THEN RAISE EXCEPTION 'foreign report'; END IF;
 r:=hg_engagement_report(student,c,t,t+interval '7 days');
 IF r->>'error'<>'forbidden' THEN RAISE EXCEPTION 'student report'; END IF;
 IF has_table_privilege('anon','hg_internal.engagement_page_events','SELECT') OR has_function_privilege('authenticated','hg_engagement_summary(uuid,timestamptz,timestamptz,boolean)','EXECUTE') THEN RAISE EXCEPTION 'public analytics access'; END IF;
END $$;
ROLLBACK;
SELECT 'duplicate-safe page measurement, no URL secrets, activity/funnel/streak records and scope passed; rolled back' AS evidence;
