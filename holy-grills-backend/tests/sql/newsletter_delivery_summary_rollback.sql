BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();a uuid:=gen_random_uuid();s1 uuid:=gen_random_uuid();s2 uuid:=gen_random_uuid();foreign_s uuid:=gen_random_uuid();late_s uuid:=gen_random_uuid();c1 uuid:=gen_random_uuid();c2 uuid:=gen_random_uuid();c3 uuid:=gen_random_uuid();d jsonb;r jsonb;cancelled_at timestamptz;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Newsletter worker','audit-'||ca),(cb,'[AUDIT rollback] Foreign subscriber','audit-'||cb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-newsletter-worker-'||a||'@example.invalid','{}');UPDATE profiles SET role='admin',is_active=true,campus_id=ca WHERE id=a;
 INSERT INTO newsletter_subscriptions(id,email,campus_id,is_confirmed,created_at) VALUES(s1,'audit-'||s1||'@example.invalid',ca,true,now()-interval '1 day'),(s2,'audit-'||s2||'@example.invalid',ca,true,now()-interval '1 day'),(foreign_s,'audit-'||foreign_s||'@example.invalid',cb,true,now()-interval '1 day'),(late_s,'audit-'||late_s||'@example.invalid',ca,true,now()+interval '1 day');
 INSERT INTO newsletter_campaigns(id,campus_id,created_by,subject,body,status) VALUES(c1,ca,a,'Worker one','Body','sending'),(c2,ca,a,'Worker cancel','Body','sending'),(c3,ca,a,'Worker unknown','Body','sending');
 IF hg_claim_newsletter_delivery(c1,s1,'wrong@example.invalid') IS NOT NULL OR hg_claim_newsletter_delivery(c1,foreign_s,'audit-'||foreign_s||'@example.invalid') IS NOT NULL OR hg_claim_newsletter_delivery(c1,late_s,'audit-'||late_s||'@example.invalid') IS NOT NULL THEN RAISE EXCEPTION 'Recipient/campus/audience snapshot bypass';END IF;
 EXECUTE 'SET LOCAL ROLE service_role';d:=hg_claim_newsletter_delivery(c1,s1,'audit-'||s1||'@example.invalid');EXECUTE 'RESET ROLE';
 IF d->>'id' IS NULL OR hg_claim_newsletter_delivery(c1,s1,'audit-'||s1||'@example.invalid') IS NOT NULL THEN RAISE EXCEPTION 'Recipient handoff did not dedupe';END IF;
 r:=hg_refresh_newsletter_summary(c1,'Unconfirmed send');IF r->>'status'<>'sending' OR (r->>'inflight')::integer<>1 OR NOT(r->>'pending')::boolean THEN RAISE EXCEPTION 'Campaign completed while pending/inflight';END IF;
 UPDATE newsletter_subscriptions SET unsubscribed_at=now() WHERE id=s2;
 IF hg_claim_newsletter_delivery(c1,s2,'audit-'||s2||'@example.invalid') IS NOT NULL THEN RAISE EXCEPTION 'Unsubscribed recipient handed off';END IF;
 r:=hg_refresh_newsletter_summary(c1,'Unconfirmed send');IF r->>'status'<>'sending' OR (r->>'pending')::boolean THEN RAISE EXCEPTION 'Unsubscribe/inflight completion incorrect';END IF;
 UPDATE newsletter_deliveries SET status='sent',sent_at=now() WHERE id=(d->>'id')::uuid;
 r:=hg_refresh_newsletter_summary(c1,'Unconfirmed send');IF r->>'status'<>'sent' OR (r->>'sent')::integer<>1 OR (r->>'failed')::integer<>0 THEN RAISE EXCEPTION 'Receipt-derived accepted count incorrect';END IF;
 r:=hg_refresh_newsletter_summary(c1,'Unconfirmed send');IF (r->>'sent')::integer<>1 THEN RAISE EXCEPTION 'Summary retry incremented total';END IF;
 r:=hg_cancel_newsletter_campaign(a,c2,ca);cancelled_at:=(r->'campaign'->>'completed_at')::timestamptz;
 IF hg_claim_newsletter_delivery(c2,s1,'audit-'||s1||'@example.invalid') IS NOT NULL THEN RAISE EXCEPTION 'Cancelled campaign handed off';END IF;
 r:=hg_refresh_newsletter_summary(c2,'Unconfirmed send');IF r->>'status'<>'cancelled' OR (SELECT completed_at FROM newsletter_campaigns WHERE id=c2) IS DISTINCT FROM cancelled_at THEN RAISE EXCEPTION 'Worker overwrote cancellation receipt';END IF;
 d:=hg_claim_newsletter_delivery(c3,s1,'audit-'||s1||'@example.invalid');UPDATE newsletter_deliveries SET status='uncertain',error='Unconfirmed send' WHERE id=(d->>'id')::uuid;
 r:=hg_refresh_newsletter_summary(c3,'Unconfirmed send');IF r->>'status'<>'partial' OR (r->>'uncertain')::integer<>1 OR (r->>'failed')::integer<>0 OR (SELECT last_error FROM newsletter_campaigns WHERE id=c3)<>'Unconfirmed send' THEN RAISE EXCEPTION 'Unknown outcome reported as definite failure/success';END IF;
 IF has_function_privilege('authenticated','public.hg_claim_newsletter_delivery(uuid,uuid,text)','execute') OR has_function_privilege('anon','public.hg_refresh_newsletter_summary(uuid,text)','execute') THEN RAISE EXCEPTION 'Worker helper exposed';END IF;
END $$;
ROLLBACK;
