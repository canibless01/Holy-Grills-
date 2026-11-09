BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $test$
DECLARE c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();o uuid:=gen_random_uuid();e uuid:=gen_random_uuid();s uuid;ids uuid[]:='{}';expected jsonb;result jsonb;before_count integer;i integer;
 copy jsonb:='{"title":"Event workspace update","body":"{title}: {status}. Open the event workspace for details."}';
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Reliability '||c,'audit-reliability-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-'||a||'@example.invalid','{}'),(o,'audit-'||o||'@example.invalid','{}');
 UPDATE profiles SET role='admin',campus_id=c WHERE id=a;
 UPDATE profiles SET role='event_organizer',campus_id=c WHERE id=o;
 result:=hg_organizer_event_draft(o,e,'create',jsonb_build_object('title','[AUDIT rollback] Reliability','location','FUTA','starts_at',now()+interval '1 day','ends_at',now()+interval '2 days','capacity',10));
 BEGIN
  PERFORM hg_organizer_event_draft(o,e,'submit',jsonb_build_object('_notice',copy));
  RAISE EXCEPTION 'controlled interruption';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled interruption' THEN RAISE;END IF;END;
 IF (SELECT review_status FROM events WHERE id=e)<>'draft' OR EXISTS(SELECT 1 FROM notifications WHERE metadata->>'organizer_event_id'=e::text) THEN RAISE EXCEPTION 'Interruption left notice/state';END IF;
 PERFORM hg_organizer_event_draft(o,e,'submit',jsonb_build_object('_notice',copy));
 SELECT count(*) INTO before_count FROM notifications WHERE user_id=a AND metadata->>'organizer_event_id'=e::text;
 IF before_count<>2 THEN RAISE EXCEPTION 'Submission did not capture own-admin notices';END IF;
 PERFORM hg_organizer_event_draft(o,e,'submit',jsonb_build_object('_notice',copy));
 IF (SELECT count(*) FROM notifications WHERE user_id=a AND metadata->>'organizer_event_id'=e::text)<>before_count THEN RAISE EXCEPTION 'Submission replay duplicated notice';END IF;
 IF (SELECT count(*) FROM notification_deliveries WHERE id IN(SELECT id FROM notifications WHERE user_id=a AND metadata->>'organizer_event_id'=e::text AND channel='push'))<>1 THEN RAISE EXCEPTION 'Durable dispatch not captured';END IF;
 PERFORM hg_review_organizer_event(a,e,'approve',jsonb_build_object('notes','Approved test','_notice',copy));
 PERFORM hg_review_organizer_event(a,e,'approve',jsonb_build_object('notes','Approved test','_notice',copy));
 IF (SELECT count(*) FROM notifications WHERE user_id=o AND metadata->>'organizer_event_id'=e::text)<>2 THEN RAISE EXCEPTION 'Review replay duplicated notice';END IF;
 FOR i IN 1..5 LOOP
  s:=gen_random_uuid();ids:=ids||s;
  INSERT INTO storefront_sections(id,section_type,key,title,content,sort_order,campus_id,created_at) VALUES(s,'hero','audit-'||s,'[AUDIT rollback] Sort '||i,'{"placement":"home"}',0,c,now()+i*interval '1 millisecond');
 END LOOP;
 SELECT jsonb_agg(jsonb_build_object('id',id,'sort_order',sort_order,'updated_at',updated_at)) INTO expected FROM storefront_sections WHERE id=ANY(ids);
 PERFORM hg_move_storefront_section(a,ids[5],-1,expected);
 IF (SELECT array_agg(id ORDER BY sort_order,created_at,id) FROM storefront_sections WHERE id=ANY(ids))<>ARRAY[ids[1],ids[2],ids[3],ids[5],ids[4]] THEN RAISE EXCEPTION 'Equal-rank move did not persist';END IF;
 BEGIN PERFORM hg_move_storefront_section(a,ids[5],-1,expected);RAISE EXCEPTION 'Stale reorder accepted';EXCEPTION WHEN serialization_failure THEN NULL;END;
 ids:='{}';
 FOR i IN 1..5 LOOP
  s:=gen_random_uuid();ids:=ids||s;
  INSERT INTO banners(id,title,image_url,placement,sort_order,campus_id,created_at) VALUES(s,'[AUDIT rollback] Banner '||i,'https://res.cloudinary.com/audit/image/upload/banner.png','hero',0,c,now()+i*interval '1 millisecond');
 END LOOP;
 SELECT jsonb_agg(jsonb_build_object('id',id,'sort_order',sort_order,'updated_at',updated_at)) INTO expected FROM banners WHERE id=ANY(ids);
 PERFORM hg_move_storefront_banner(a,ids[5],-1,expected);
 IF (SELECT array_agg(id ORDER BY sort_order,created_at,id) FROM banners WHERE id=ANY(ids))<>ARRAY[ids[1],ids[2],ids[3],ids[5],ids[4]] THEN RAISE EXCEPTION 'Equal-rank banner move did not persist';END IF;
 BEGIN PERFORM hg_move_storefront_banner(a,ids[5],-1,expected);RAISE EXCEPTION 'Stale banner reorder accepted';EXCEPTION WHEN serialization_failure THEN NULL;END;
 s:=gen_random_uuid();INSERT INTO banners(id,title,image_url,placement,campus_id) VALUES(s,'[AUDIT rollback] Global','https://res.cloudinary.com/audit/image/upload/banner.png','hero',NULL);
 BEGIN PERFORM hg_move_storefront_banner(a,s,1,'[]');RAISE EXCEPTION 'Campus admin reordered global banner';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 IF has_function_privilege('authenticated','hg_move_storefront_banner(uuid,uuid,integer,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'Browser can reorder banners directly';END IF;
 IF has_function_privilege('authenticated','hg_move_storefront_section(uuid,uuid,integer,jsonb)','EXECUTE') OR has_function_privilege('anon','hg_internal.capture_organizer_notice(uuid,text,text,text,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'Browser can mutate privileged state';END IF;
END $test$;
ROLLBACK;
SELECT 'PASS atomic/replayed organizer notices, dispatch capture, equal-rank ordering, stale rejection and service-only access; all fixtures rolled back' AS evidence;
