BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();a uuid:=gen_random_uuid();manager uuid:=gen_random_uuid();super_id uuid:=gen_random_uuid();r1 uuid:=gen_random_uuid();r2 uuid:=gen_random_uuid();r3 uuid:=gen_random_uuid();reply jsonb;version timestamptz;values_json jsonb:='{"metric":"orders","threshold":3,"reward_type":"meal_discount","reward_amount":3000,"reward_uses":1,"validity_days":14,"auto_issue":false,"is_active":true}';
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Ambassador policy A','audit-'||ca),(cb,'[AUDIT rollback] Ambassador policy B','audit-'||cb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-amb-policy-'||a||'@example.invalid','{}'),(manager,'audit-amb-policy-'||manager||'@example.invalid','{}'),(super_id,'audit-amb-policy-'||super_id||'@example.invalid','{}');UPDATE profiles SET is_active=true,campus_id=ca WHERE id IN(a,manager,super_id);UPDATE profiles SET role='admin' WHERE id=a;UPDATE profiles SET role='community_manager' WHERE id=manager;UPDATE profiles SET role='super_admin' WHERE id=super_id;
 EXECUTE 'SET LOCAL ROLE service_role';reply:=hg_write_ambassador_milestone(a,r1,r1,ca,values_json,null,true);EXECUTE 'RESET ROLE';
 IF reply->'milestone'->>'id'<>r1::text THEN RAISE EXCEPTION 'Milestone create failed';END IF;
 version:=(reply->'milestone'->>'updated_at')::timestamptz;
 reply:=hg_write_ambassador_milestone(a,r1,r1,ca,values_json,null,true);IF NOT(reply->>'replayed')::boolean THEN RAISE EXCEPTION 'Create did not replay';END IF;
 IF (SELECT count(*) FROM ambassador_milestones WHERE id=r1)<>1 OR (SELECT count(*) FROM admin_audit_logs WHERE id=r1)<>1 THEN RAISE EXCEPTION 'Duplicate policy/audit on retry';END IF;
 reply:=hg_write_ambassador_milestone(a,r2,r2,ca,values_json,null,true);IF reply->'milestone'->>'id'<>r1::text OR EXISTS(SELECT 1 FROM ambassador_milestones WHERE id=r2) THEN RAISE EXCEPTION 'Different UUID duplicated identical recent policy';END IF;
 BEGIN PERFORM hg_write_ambassador_milestone(a,r1,r1,ca,values_json||'{"threshold":5}',null,true);RAISE EXCEPTION 'Changed request accepted';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_AMB_MILESTONE_CONFLICT' THEN RAISE;END IF;END;
 reply:=hg_write_ambassador_milestone(a,r3,r1,ca,'{"reward_amount":3500,"is_active":false}',version,false);IF (reply->'milestone'->>'reward_amount')::numeric<>3500 OR (reply->'milestone'->>'is_active')::boolean THEN RAISE EXCEPTION 'Edit/archive did not persist';END IF;
 reply:=hg_write_ambassador_milestone(a,r3,r1,ca,'{"reward_amount":3500,"is_active":false}',version,false);IF NOT(reply->>'replayed')::boolean OR (SELECT count(*) FROM admin_audit_logs WHERE id=r3)<>1 THEN RAISE EXCEPTION 'Edit replay changed receipt';END IF;
 BEGIN PERFORM hg_write_ambassador_milestone(a,gen_random_uuid(),r1,ca,'{"is_active":true}',version-interval '1 minute',false);RAISE EXCEPTION 'Stale edit accepted';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_AMB_MILESTONE_STALE' THEN RAISE;END IF;END;
 BEGIN PERFORM hg_write_ambassador_milestone(a,gen_random_uuid(),gen_random_uuid(),cb,values_json,null,true);RAISE EXCEPTION 'Foreign policy created';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM hg_write_ambassador_milestone(manager,gen_random_uuid(),gen_random_uuid(),ca,values_json,null,true);RAISE EXCEPTION 'Manager configured financial policy';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM hg_write_ambassador_milestone(a,gen_random_uuid(),gen_random_uuid(),null,values_json,null,true);RAISE EXCEPTION 'Campus admin created global policy';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 reply:=hg_write_ambassador_milestone(super_id,gen_random_uuid(),gen_random_uuid(),null,values_json,null,true);IF reply->'milestone'->'campus_id'<>'null'::jsonb THEN RAISE EXCEPTION 'Super admin global policy not global';END IF;
 UPDATE profiles SET is_active=false WHERE id=a;
 BEGIN PERFORM hg_write_ambassador_milestone(a,r1,r1,ca,values_json,null,true);RAISE EXCEPTION 'Inactive admin replayed policy';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 IF has_function_privilege('anon','public.hg_write_ambassador_milestone(uuid,uuid,uuid,uuid,jsonb,timestamptz,boolean)','execute') OR has_function_privilege('authenticated','public.hg_write_ambassador_milestone(uuid,uuid,uuid,uuid,jsonb,timestamptz,boolean)','execute') THEN RAISE EXCEPTION 'Policy writer exposed';END IF;
END $$;
ROLLBACK;
