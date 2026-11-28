-- Fixture setup: insert immediately after BEGIN, before a rollback verification script.
-- Never execute outside its enclosing BEGIN/ROLLBACK transaction.
SET LOCAL request.jwt.claims='{"role":"service_role"}';

DO $fixtures$ DECLARE c uuid:=gen_random_uuid(); u uuid; i integer; BEGIN
INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Acceptance','audit-acceptance-'||c);
FOR i IN 1..6 LOOP
u:=gen_random_uuid();
INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-acceptance-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Acceptance"}');
UPDATE auth.users SET created_at=now()-interval '30 days' WHERE id=u;
UPDATE public.profiles SET campus_id=c,role='student',is_active=true WHERE id=u;
INSERT INTO public.wallets(user_id,balance) VALUES(u,0) ON CONFLICT(user_id) DO NOTHING;
END LOOP; END $fixtures$;
