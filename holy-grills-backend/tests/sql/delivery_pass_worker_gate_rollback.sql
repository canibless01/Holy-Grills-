BEGIN;
SET LOCAL search_path=public,extensions;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();u uuid:=gen_random_uuid();p uuid:=gen_random_uuid();result jsonb;
BEGIN
 -- Do not hide or rewrite real outstanding payments to manufacture an idle gate.
 IF EXISTS(SELECT 1 FROM hg_internal.delivery_pass_receipts) THEN RAISE EXCEPTION 'Use an isolated database: pass receipts already exist';END IF;
 INSERT INTO campuses(id,name,slug) VALUES(c,'[ROLLBACK] Worker gate',c::text);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'pass-gate-'||a||'@example.invalid','{}'),(u,'pass-gate-'||u||'@example.invalid','{}');
 UPDATE profiles SET role='admin',campus_id=c,is_active=true WHERE id=a;
 UPDATE profiles SET role='student',campus_id=c,is_active=true WHERE id=u;
 UPDATE feature_flags SET is_active=false WHERE feature_name='delivery_pass';
 result:=hg_delivery_pass(NULL,'scan');
 IF result->>'skipped' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Disabled idle worker was not skipped';END IF;
 PERFORM hg_delivery_pass(a,'configure',NULL,jsonb_build_object('campus_id',c,'price_kobo',10000,'is_active',true));
 result:=hg_delivery_pass(NULL,'scan');
 IF result->>'skipped' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Active offer bypassed disabled flag';END IF;
 -- A campus-specific release is sufficient, even while the global flag is off.
 INSERT INTO feature_flags(feature_name,is_active,campus_id) VALUES('delivery_pass',true,c);
 result:=hg_delivery_pass(NULL,'scan');
 IF result ? 'skipped' THEN RAISE EXCEPTION 'Enabled campus worker skipped';END IF;
 PERFORM hg_delivery_pass(u,'buy',p,'{"method":"card","price_kobo":10000,"auto_renew":false}');
 UPDATE feature_flags SET is_active=false WHERE feature_name='delivery_pass';
 result:=hg_delivery_pass(NULL,'scan');
 IF result ? 'skipped' OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(result->'pending')x WHERE x->>'id'=p::text) THEN RAISE EXCEPTION 'Disabled flag abandoned original payment';END IF;
 PERFORM hg_delivery_pass(NULL,'confirm',p,jsonb_build_object('reference','HG-PASS-'||p::text,'amount_kobo',10000,'currency','NGN'));
 result:=hg_delivery_pass(NULL,'scan');
 IF result ? 'skipped' OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(result->'notices')x WHERE x->>'id'=p::text) THEN RAISE EXCEPTION 'Disabled flag dropped payment notice';END IF;
 PERFORM hg_delivery_pass(NULL,'notice_done',p,'{"status":"paid"}');
 result:=hg_delivery_pass(NULL,'scan');
 IF result->>'skipped' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Settled disabled worker did not return idle';END IF;
 IF NOT(hg_delivery_pass(u,'benefit',NULL,jsonb_build_object('campus_id',c)) ? 'id') THEN RAISE EXCEPTION 'Gating removed paid coverage';END IF;
END $verify$;
SELECT 'PASS disabled idle skip, campus enable, pending payment/notice recovery and preserved paid entitlement; all changes rolled back' AS evidence;
ROLLBACK;
