BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid(); u uuid:=gen_random_uuid(); a uuid:=gen_random_uuid(); other_a uuid:=gen_random_uuid();
 e uuid:=gen_random_uuid(); p uuid:=gen_random_uuid(); legacy uuid:=gen_random_uuid(); review_id uuid:=gen_random_uuid();
 claim jsonb; again jsonb; token uuid; key_before text; payload jsonb:='{"subject":"Frozen","html_body":"Hello"}'; r jsonb; denied boolean;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Dispatch','audit-dispatch-'||c),(other_c,'[AUDIT rollback] Other','audit-dispatch-'||other_c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-dispatch-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Dispatch"}'),
 (a,'audit-dispatch-'||a||'@example.invalid','{}'),(other_a,'audit-dispatch-'||other_a||'@example.invalid','{}');
 UPDATE public.profiles SET campus_id=c,role='student' WHERE id=u;
 UPDATE public.profiles SET campus_id=c,role='admin' WHERE id=a;
 UPDATE public.profiles SET campus_id=other_c,role='admin' WHERE id=other_a;
 INSERT INTO public.notifications(id,user_id,type,channel,title,body,campus_id,metadata) VALUES
 (e,u,'order_confirmed','email','Receipt','Saved receipt',c,'{"_dispatch_version":1}'),
 (p,u,'order_confirmed','push','Receipt','Saved receipt',c,'{"_dispatch_version":1}'),
 (legacy,u,'order_confirmed','email','Legacy','Do not replay',c,'{}');
 IF (SELECT count(*) FROM public.notification_deliveries WHERE notification_id IN(e,p))<>2
 OR EXISTS(SELECT 1 FROM public.notification_deliveries WHERE notification_id=legacy) THEN RAISE EXCEPTION 'capture or rollout isolation failed'; END IF;
 claim:=public.hg_claim_notification_dispatch(e); token:=(claim->>'token')::uuid;
 IF claim->>'state'<>'claimed' OR claim->'payload'->'notification'->>'title'<>'Receipt' THEN RAISE EXCEPTION 'snapshot claim failed'; END IF;
 IF public.hg_claim_notification_dispatch(e)->>'state'<>'busy' THEN RAISE EXCEPTION 'second worker claimed active lease'; END IF;
 IF public.hg_begin_notification_dispatch(e,gen_random_uuid(),payload) THEN RAISE EXCEPTION 'stale token began send'; END IF;
 IF NOT public.hg_begin_notification_dispatch(e,token,payload) THEN RAISE EXCEPTION 'valid worker could not begin'; END IF;
 UPDATE public.notification_deliveries SET dispatch=jsonb_set(dispatch,'{lease_until}',to_jsonb(now()-interval '1 minute')) WHERE id=e;
 IF public.hg_claim_notification_dispatch(e)->>'state'<>'uncertain' THEN RAISE EXCEPTION 'uncertain email automatically resent'; END IF;
 IF (public.hg_due_notification_dispatch(100)) @> jsonb_build_array(e) THEN RAISE EXCEPTION 'uncertain email still auto queued'; END IF;
 IF public.hg_finish_notification_dispatch(e,gen_random_uuid(),'{"state":"accepted"}') THEN RAISE EXCEPTION 'stale completion accepted'; END IF;
 denied:=false;
 BEGIN PERFORM public.hg_reconcile_notification_dispatch(u,e,review_id,'not_sent','resend',NULL,'Provider log rejected sender'); EXCEPTION WHEN insufficient_privilege THEN denied:=true; END;
 IF NOT denied THEN RAISE EXCEPTION 'student could reconcile delivery'; END IF;
 denied:=false;
 BEGIN PERFORM public.hg_reconcile_notification_dispatch(other_a,e,review_id,'not_sent','resend',NULL,'Provider log rejected sender'); EXCEPTION WHEN insufficient_privilege THEN denied:=true; END;
 IF NOT denied THEN RAISE EXCEPTION 'foreign campus could reconcile delivery'; END IF;
 BEGIN PERFORM public.hg_reconcile_notification_dispatch(a,e,review_id,NULL,'resend',NULL,'Provider log rejected sender'); RAISE EXCEPTION 'TEST null outcome accepted'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 key_before:=(SELECT dispatch->>'key' FROM public.notification_deliveries WHERE id=e);
 r:=public.hg_reconcile_notification_dispatch(a,e,review_id,'not_sent','resend',NULL,'Provider log confirms sender rejected');
 IF r->>'status'<>'queued' OR (SELECT dispatch->>'key' FROM public.notification_deliveries WHERE id=e)=key_before
 OR (SELECT dispatch_payload ? 'prepared' FROM public.notification_deliveries WHERE id=e) THEN RAISE EXCEPTION 'confirmed no-send retry did not reset intent'; END IF;
 again:=public.hg_reconcile_notification_dispatch(a,e,review_id,'not_sent','resend',NULL,'Provider log confirms sender rejected');
 IF NOT (again->>'idempotent')::boolean OR (SELECT count(*) FROM public.admin_audit_logs WHERE entity_id=e::text)<>1 THEN RAISE EXCEPTION 'review replay duplicated audit'; END IF;
 BEGIN PERFORM public.hg_reconcile_notification_dispatch(a,e,review_id,'sent','resend','changed','Provider log confirms sender rejected'); RAISE EXCEPTION 'TEST conflicting review accepted'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 claim:=public.hg_claim_notification_dispatch(e); token:=(claim->>'token')::uuid;
 PERFORM public.hg_begin_notification_dispatch(e,token,payload);
 PERFORM public.hg_finish_notification_dispatch(e,token,'{"state":"accepted_fallback","provider":"resend","delivered_by":"onesignal","fallback":{"provider_message_id":"fallback-id"}}');
 IF (SELECT status<>'sent' OR provider<>'onesignal' OR provider_message_id<>'fallback-id' FROM public.notification_deliveries WHERE id=e) THEN RAISE EXCEPTION 'actual fallback receipt lost'; END IF;
 IF public.hg_claim_notification_dispatch(e)->>'state'<>'sent' THEN RAISE EXCEPTION 'sent message reclaimed'; END IF;
 claim:=public.hg_claim_notification_dispatch(p); token:=(claim->>'token')::uuid; key_before:=claim->>'key';
 PERFORM public.hg_begin_notification_dispatch(p,token,payload);
 UPDATE public.notification_deliveries SET dispatch=jsonb_set(dispatch,'{lease_until}',to_jsonb(now()-interval '1 minute')) WHERE id=p;
 again:=public.hg_claim_notification_dispatch(p);
 IF again->>'key'<>key_before OR again->'payload'->'prepared' IS DISTINCT FROM payload OR again->>'token'=token::text THEN RAISE EXCEPTION 'push replay changed idempotency/payload/lease'; END IF;
 IF public.hg_finish_notification_dispatch(p,token,'{"state":"accepted"}') THEN RAISE EXCEPTION 'expired worker finished newer claim'; END IF;
 token:=(again->>'token')::uuid;
 BEGIN PERFORM public.hg_begin_notification_dispatch(p,token,'{"subject":"Changed"}'); RAISE EXCEPTION 'TEST changed push replay accepted'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 PERFORM public.hg_begin_notification_dispatch(p,token,payload);
 PERFORM public.hg_finish_notification_dispatch(p,token,'{"state":"retry","provider":"onesignal"}');
 IF public.hg_claim_notification_dispatch(p)->>'state'<>'deferred' THEN RAISE EXCEPTION 'retry backoff ignored'; END IF;
 UPDATE public.notification_deliveries SET dispatch=dispatch||jsonb_build_object('next_at',now()-interval '1 minute','attempts',6) WHERE id=p;
 IF public.hg_claim_notification_dispatch(p)->>'state'<>'failed' THEN RAISE EXCEPTION 'retry budget ignored'; END IF;
 r:=public.hg_reconcile_notification_dispatch(a,p,gen_random_uuid(),'sent','onesignal','accepted-push-id','Provider log confirms accepted push');
 IF r->>'status'<>'sent' THEN RAISE EXCEPTION 'review accepted delivery failed'; END IF;
 IF has_function_privilege('authenticated','public.hg_claim_notification_dispatch(uuid)','execute') OR has_function_privilege('anon','public.hg_reconcile_notification_dispatch(uuid,uuid,uuid,text,text,text,text)','execute') THEN RAISE EXCEPTION 'private RPC publicly executable'; END IF;
 denied:=false;
 BEGIN PERFORM public.hg_notification_recovery_list(a,other_c); EXCEPTION WHEN insufficient_privilege THEN denied:=true; END;
 IF NOT denied THEN RAISE EXCEPTION 'foreign recovery list accepted'; END IF;
 -- Reclaimed work before external handoff is safe to attempt, unlike email sending.
 UPDATE public.notification_deliveries SET status='sending', dispatch=dispatch||jsonb_build_object('state','claimed','next_at',now()-interval '1 minute','lease_until',now()-interval '1 minute','attempts',1,'expires_at',now()+interval '1 hour') WHERE id=e;
 IF public.hg_claim_notification_dispatch(e)->>'state'<>'claimed' THEN RAISE EXCEPTION 'pre-handoff crash not recovered'; END IF;
 UPDATE public.notification_deliveries SET dispatch=dispatch||jsonb_build_object('state','queued','next_at',now()-interval '1 minute','expires_at',now()-interval '1 minute') WHERE id=e;
 IF public.hg_claim_notification_dispatch(e)->>'state'<>'failed' THEN RAISE EXCEPTION 'dispatch expiry ignored'; END IF;
 IF public.hg_notification_recovery_list(a,c)->0->>'recipient' IS NULL THEN RAISE EXCEPTION 'scoped review projection missing'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_policy WHERE polname='notification_dispatch_private' AND NOT polpermissive) THEN RAISE EXCEPTION 'snapshot privacy policy absent'; END IF;
END $verify$;
SET LOCAL ROLE authenticated;
DO $privacy$ BEGIN
 IF EXISTS(SELECT 1 FROM public.notification_deliveries WHERE dispatch->>'version'='1') THEN RAISE EXCEPTION 'private dispatch visible to authenticated role'; END IF;
END $privacy$;
RESET ROLE;
SELECT 'notification dispatch capture/leases/replay/privacy/provider-review checks passed; all fixtures rolled back' AS result;
ROLLBACK;
