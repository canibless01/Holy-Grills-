-- Run only in an isolated schema copy, or a single rollback-only transaction.
BEGIN;
DO $$
DECLARE c uuid:=gen_random_uuid(); c2 uuid:=gen_random_uuid(); manager uuid:=gen_random_uuid(); boss uuid:=gen_random_uuid(); student uuid:=gen_random_uuid(); other uuid:=gen_random_uuid();
 mid uuid:=gen_random_uuid(); global_id uuid:=gen_random_uuid(); r jsonb; r2 jsonb;
BEGIN
 INSERT INTO campuses(id,name,slug,is_active) VALUES(c,'Local ambassador test','local-'||c,true),(c2,'Local other test','local-'||c2,true);
 INSERT INTO auth.users(id,email) VALUES(manager,manager||'@example.invalid'),(boss,boss||'@example.invalid'),(student,student||'@example.invalid'),(other,other||'@example.invalid');
 INSERT INTO profiles(id,email,full_name,role,campus_id,is_active,phone) VALUES
  (manager,manager||'@example.invalid','Manager','community_manager',c,true,'08000000000'),(boss,boss||'@example.invalid','Boss','super_admin',c,true,null),
  (student,student||'@example.invalid','Student','student',c,true,'08012345678'),(other,other||'@example.invalid','Other','student',c2,true,null)
 ON CONFLICT(id) DO UPDATE SET role=excluded.role,campus_id=excluded.campus_id,is_active=excluded.is_active,phone=excluded.phone;
 INSERT INTO ambassadors(profile_id,campus_id,status) VALUES(student,c,'active'),(other,c2,'active');
 r:=hg_create_ambassador_promo_atomic(manager,mid,c,'Hello {{link}}',null,'2026-11',true,'{}');
 IF (r->>'recipient_count')::int<>1 THEN RAISE EXCEPTION 'scoped creation: %',r; END IF;
 r2:=hg_create_ambassador_promo_atomic(manager,gen_random_uuid(),c,'Hello {{link}}',null,'2026-11',true,'{}');
 IF r2->'message'->>'id'<>mid::text OR NOT (r2->>'idempotent')::boolean THEN RAISE EXCEPTION 'durable identical intent receipt: %',r2; END IF;
 IF (SELECT count(*) FROM ambassador_promo_assignments WHERE message_id=mid)<>1 THEN RAISE EXCEPTION 'duplicate assignment'; END IF;
 r2:=hg_manage_ambassador_promo(student,mid,1,'edit','{"caption":"Changed {{link}}"}');
 IF r2->>'error'<>'promo_forbidden' THEN RAISE EXCEPTION 'student permission'; END IF;
 UPDATE profiles SET campus_id=c2 WHERE id=manager;
 r2:=hg_manage_ambassador_promo(manager,mid,1,'delete');
 IF r2->>'error'<>'promo_forbidden' THEN RAISE EXCEPTION 'foreign campus permission'; END IF;
 UPDATE profiles SET campus_id=c WHERE id=manager;
 r2:=hg_manage_ambassador_promo(manager,mid,1,'edit','{"caption":"Changed {{link}}"}');
 IF (r2->'message'->>'revision')::int<>2 THEN RAISE EXCEPTION 'edit revision: %',r2; END IF;
 IF (SELECT count(*) FROM ambassador_promo_assignments WHERE message_id=mid)<>1 OR (SELECT count(*) FROM ambassador_promo_history WHERE message_id=mid)<>1 THEN RAISE EXCEPTION 'edit must preserve assignment and history'; END IF;
 r2:=hg_manage_ambassador_promo(manager,mid,1,'edit','{"caption":"Lost update {{link}}"}');
 IF r2->>'error'<>'promo_stale' THEN RAISE EXCEPTION 'lost update accepted'; END IF;
 r2:=hg_set_ambassador_whatsapp(manager,student,'+2348019998888');
 IF r2->>'whatsapp_phone'<>'+2348019998888' OR (SELECT phone FROM profiles WHERE id=student)<>'08012345678' THEN RAISE EXCEPTION 'contact override modified account phone'; END IF;
 r2:=hg_set_ambassador_whatsapp(manager,other,'+2348019998888');
 IF r2->>'error'<>'promo_forbidden' THEN RAISE EXCEPTION 'foreign contact mutation'; END IF;
 r2:=hg_set_ambassador_whatsapp(manager,student,null);
 IF r2->>'whatsapp_phone' IS NOT NULL THEN RAISE EXCEPTION 'contact clear failed'; END IF;
 r2:=hg_manage_ambassador_promo(manager,mid,2,'delete');
 IF r2->'message'->>'deleted_at' IS NULL THEN RAISE EXCEPTION 'delete failed'; END IF;
 IF (SELECT count(*) FROM ambassador_promo_history WHERE message_id=mid)<>2 THEN RAISE EXCEPTION 'history missing'; END IF;
 r2:=hg_create_ambassador_promo_atomic(manager,gen_random_uuid(),c,'Hello {{link}}',null,'2026-11',true,'{}');
 IF r2->>'error'<>'promo_deleted' THEN RAISE EXCEPTION 'deleted create receipt resurrected'; END IF;
 r2:=hg_manage_ambassador_promo(manager,mid,2,'delete');
 IF NOT (r2->>'idempotent')::boolean OR (SELECT count(*) FROM ambassador_promo_history WHERE message_id=mid)<>2 THEN RAISE EXCEPTION 'delete replay duplicated history'; END IF;
 r2:=hg_create_ambassador_promo_atomic(boss,global_id,null,'Global {{link}}',null,'2026-11',true,'{}');
 r2:=hg_manage_ambassador_promo(manager,global_id,1,'edit','{"caption":"Campus overwrite {{link}}"}');
 IF r2->>'error'<>'promo_forbidden' THEN RAISE EXCEPTION 'campus manager overwrote global message'; END IF;
 UPDATE profiles SET is_active=false WHERE id=manager;
 r2:=hg_set_ambassador_whatsapp(manager,student,'+2348019998888');
 IF r2->>'error'<>'promo_forbidden' THEN RAISE EXCEPTION 'inactive staff accepted'; END IF;
 IF has_function_privilege('authenticated','hg_manage_ambassador_promo(uuid,uuid,integer,text,jsonb)','EXECUTE') OR has_function_privilege('anon','hg_set_ambassador_whatsapp(uuid,uuid,text)','EXECUTE') THEN RAISE EXCEPTION 'public mutation privilege'; END IF;
END $$;
ROLLBACK;
SELECT 'promo lifecycle, durable duplicate receipts, contact isolation and role/campus checks passed; rolled back' AS evidence;
