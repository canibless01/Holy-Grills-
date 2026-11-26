BEGIN;
SET LOCAL search_path=public,extensions;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE a uuid:=gen_random_uuid();b uuid:=gen_random_uuid();current_token text:=gen_random_uuid()::text;other_token text:=gen_random_uuid()::text;n integer;
BEGIN
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'push-rollback-'||a||'@example.invalid','{}'),(b,'push-rollback-'||b||'@example.invalid','{}');
 INSERT INTO device_tokens(user_id,token,platform) VALUES(a,current_token,'web'),(a,other_token,'web'),(b,current_token,'web');
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);
 PERFORM set_config('role','authenticated',true);
 DELETE FROM device_tokens WHERE user_id=b AND token=current_token;GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>0 THEN RAISE EXCEPTION 'Cross-account device revocation';END IF;
 DELETE FROM device_tokens WHERE user_id=a AND token=current_token;GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>1 THEN RAISE EXCEPTION 'Own device could not be revoked';END IF;
 DELETE FROM device_tokens WHERE user_id=a AND token=current_token;GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>0 THEN RAISE EXCEPTION 'Repeated revocation not idempotent';END IF;
 PERFORM set_config('role','none',true);
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 IF (SELECT count(*) FROM device_tokens WHERE user_id IN(a,b))<>2 OR NOT EXISTS(SELECT 1 FROM device_tokens WHERE user_id=b AND token=current_token) OR NOT EXISTS(SELECT 1 FROM device_tokens WHERE user_id=a AND token=other_token) THEN RAISE EXCEPTION 'Other devices affected';END IF;
END $verify$;
SELECT 'PASS own-device revocation, cross-account refusal, replay and other-device preservation; all synthetic records rolled back' AS evidence;
ROLLBACK;
