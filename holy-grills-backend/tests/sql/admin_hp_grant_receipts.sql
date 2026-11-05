BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid();actor uuid:=gen_random_uuid();owner uuid:=gen_random_uuid();ref uuid:=gen_random_uuid();r jsonb;baseline integer;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Grant receipts','audit-grant-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(actor,'audit-grant-'||actor||'@example.invalid','{"full_name":"[AUDIT rollback] Grant admin"}'),(owner,'audit-grant-'||owner||'@example.invalid','{"full_name":"[AUDIT rollback] Grant target"}');
 UPDATE public.profiles SET campus_id=c,role='admin' WHERE id=actor;
 UPDATE public.profiles SET campus_id=c,role='student' WHERE id=owner;
 SELECT hp_balance INTO baseline FROM public.profiles WHERE id=owner;
 r:=public.record_hp_transaction_atomic(owner,50,'earn','active','admin_grant','admin_grant',ref,actor,'[AUDIT rollback] Grant',c);
 IF NOT coalesce((r->>'success')::boolean,false) THEN RAISE EXCEPTION 'grant did not succeed';END IF;
 r:=public.record_hp_transaction_atomic(owner,50,'earn','active','admin_grant','admin_grant',ref,actor,'[AUDIT rollback] Grant',c);
 IF NOT coalesce((r->>'replayed')::boolean,false) OR (SELECT hp_balance FROM public.profiles WHERE id=owner)<>baseline+50 THEN RAISE EXCEPTION 'grant replay duplicated balance';END IF;
 r:=public.record_hp_transaction_atomic(owner,99,'earn','active','admin_grant','admin_grant',ref,actor,'[AUDIT rollback] Grant',c);
 IF r->>'error' IS NULL OR (SELECT hp_balance FROM public.profiles WHERE id=owner)<>baseline+50 THEN RAISE EXCEPTION 'changed grant intent accepted';END IF;
 IF (SELECT count(*) FROM public.hp_transactions WHERE user_id=owner AND reference_type='admin_grant' AND reference_id=ref)<>1 OR NOT EXISTS(SELECT 1 FROM public.hp_transactions WHERE reference_id=ref AND issued_by_admin_id=actor AND metadata->>'notes'='[AUDIT rollback] Grant') THEN RAISE EXCEPTION 'grant receipt actor/reason missing';END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: fresh rollback grant actors; one identified grant updates balance once; matching retry replays; changed amount refused; actor and reason persisted' AS evidence;
