ALTER TABLE public.notification_deliveries
 ADD COLUMN IF NOT EXISTS dispatch jsonb NOT NULL DEFAULT '{}',
 ADD COLUMN IF NOT EXISTS dispatch_payload jsonb;
CREATE INDEX IF NOT EXISTS notification_dispatch_pending_idx ON public.notification_deliveries(status,created_at)
 WHERE dispatch->>'version'='1';
-- Private recipient/content snapshots and worker leases stay on the server.
CREATE POLICY notification_dispatch_private ON public.notification_deliveries AS RESTRICTIVE
 FOR ALL TO anon,authenticated USING(dispatch='{}'::jsonb AND dispatch_payload IS NULL)
 WITH CHECK(dispatch='{}'::jsonb AND dispatch_payload IS NULL);

CREATE OR REPLACE FUNCTION public.hg_capture_notification_dispatch()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE p public.profiles%rowtype; blast uuid;
BEGIN
 -- New code tags only new sends. Old/history rows are never replayed on rollout.
 IF NEW.channel NOT IN ('email','push') OR NEW.metadata->>'_dispatch_version' IS DISTINCT FROM '1'
 OR coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'role','')<>'service_role' THEN RETURN NEW; END IF;
 SELECT * INTO p FROM public.profiles WHERE id=NEW.user_id;
 IF NOT FOUND THEN RETURN NEW; END IF;
 IF NEW.type LIKE 'blast_%' THEN SELECT id INTO blast FROM public.notification_blasts WHERE id=NEW.reference_id; END IF;
 INSERT INTO public.notification_deliveries(id,notification_id,blast_id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
 VALUES(NEW.id,NEW.id,blast,NEW.user_id,NEW.channel,'queued',NEW.campus_id,
  jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
  jsonb_build_object('notification',jsonb_build_object('user_id',NEW.user_id,'type',NEW.type,'title',NEW.title,'body',NEW.body,
   'action_url',NEW.action_url,'metadata',coalesce(NEW.metadata,'{}'),'blast_id',blast,
   'email',lower(trim(p.email::text)),'name',coalesce(nullif(p.nickname,''),nullif(p.full_name,''),'there'))));
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.hg_capture_notification_dispatch() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_capture_notification_dispatch() TO service_role;
CREATE TRIGGER hg_capture_notification_dispatch_trg AFTER INSERT ON public.notifications
 FOR EACH ROW EXECUTE FUNCTION public.hg_capture_notification_dispatch();

CREATE OR REPLACE FUNCTION public.hg_claim_notification_dispatch(p_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE d public.notification_deliveries%rowtype; token uuid;
BEGIN
 SELECT * INTO d FROM public.notification_deliveries WHERE id=p_id AND notification_id=p_id AND dispatch->>'version'='1' FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('state','missing'); END IF;
 IF d.dispatch->>'state' NOT IN ('queued','claimed','sending') THEN RETURN jsonb_build_object('state',d.dispatch->>'state'); END IF;
 IF d.dispatch->>'state' IN ('claimed','sending') AND (d.dispatch->>'lease_until')::timestamptz>now() THEN RETURN jsonb_build_object('state','busy'); END IF;
 IF d.channel='email' AND d.dispatch->>'state'='sending' THEN
  UPDATE public.notification_deliveries SET status='uncertain',error_message='email_worker_interrupted_after_handoff',
   dispatch=dispatch||jsonb_build_object('state','uncertain') WHERE id=d.id;
  RETURN jsonb_build_object('state','uncertain');
 END IF;
 IF (d.dispatch->>'expires_at')::timestamptz<=now() OR (d.dispatch->>'attempts')::integer>=6 THEN
  UPDATE public.notification_deliveries SET status='failed',error_message='dispatch_retry_expired',dispatch=dispatch||jsonb_build_object('state','failed') WHERE id=d.id;
  RETURN jsonb_build_object('state','failed');
 END IF;
 IF (d.dispatch->>'next_at')::timestamptz>now() THEN RETURN jsonb_build_object('state','deferred'); END IF;
 token:=gen_random_uuid();
 UPDATE public.notification_deliveries SET status='sending',dispatch=dispatch||jsonb_build_object('state','claimed',
  'token',token,'lease_until',now()+interval '2 minutes','attempts',(dispatch->>'attempts')::integer+1) WHERE id=d.id RETURNING * INTO d;
 RETURN jsonb_build_object('state','claimed','token',token,'key',d.dispatch->>'key','channel',d.channel,'payload',d.dispatch_payload);
END $$;

CREATE OR REPLACE FUNCTION public.hg_begin_notification_dispatch(p_id uuid,p_token uuid,p_prepared jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE d public.notification_deliveries%rowtype;
BEGIN
 SELECT * INTO d FROM public.notification_deliveries WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR d.dispatch->>'state'<>'claimed' OR d.dispatch->>'token' IS DISTINCT FROM p_token::text
 OR (d.dispatch->>'lease_until')::timestamptz<=now() THEN RETURN false; END IF;
 IF jsonb_typeof(p_prepared) IS DISTINCT FROM 'object' OR octet_length(p_prepared::text)>1000000 THEN RAISE EXCEPTION 'Invalid dispatch payload'; END IF;
 IF d.dispatch_payload->'prepared' IS NOT NULL AND d.dispatch_payload->'prepared' IS DISTINCT FROM p_prepared THEN RAISE EXCEPTION 'Dispatch payload changed on replay'; END IF;
 UPDATE public.notification_deliveries SET dispatch_payload=jsonb_set(dispatch_payload,'{prepared}',p_prepared),
  dispatch=dispatch||jsonb_build_object('state','sending') WHERE id=d.id;
 RETURN true;
END $$;

CREATE OR REPLACE FUNCTION public.hg_finish_notification_dispatch(p_id uuid,p_token uuid,p_outcome jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE d public.notification_deliveries%rowtype; state text; provider_name text; message text;
BEGIN
 SELECT * INTO d FROM public.notification_deliveries WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR d.dispatch->>'state' NOT IN ('claimed','sending','uncertain') OR d.dispatch->>'token' IS DISTINCT FROM p_token::text THEN RETURN false; END IF;
 state:=p_outcome->>'state';
 IF state IS NULL OR state NOT IN ('accepted','accepted_fallback','retry','uncertain','failed','skipped','cancelled') THEN RAISE EXCEPTION 'Invalid dispatch outcome'; END IF;
 provider_name:=coalesce(p_outcome->>'delivered_by',p_outcome->>'provider');
 message:=CASE WHEN state='accepted_fallback' THEN p_outcome->'fallback'->>'provider_message_id' ELSE p_outcome->>'provider_message_id' END;
 UPDATE public.notification_deliveries SET
  status=CASE WHEN state IN ('accepted','accepted_fallback') THEN 'sent' WHEN state='retry' THEN 'queued' ELSE state END,
  provider=provider_name,provider_message_id=message,error_message=left(p_outcome->>'error',500),
  delivered_at=CASE WHEN state IN ('accepted','accepted_fallback') THEN now() ELSE NULL END,
  dispatch=dispatch||jsonb_build_object('state',CASE WHEN state IN ('accepted','accepted_fallback') THEN 'sent' WHEN state='retry' THEN 'queued' ELSE state END,
   'outcome',p_outcome,'next_at',now()+make_interval(mins=>least(60,greatest(1,(dispatch->>'attempts')::integer*2))),
   'history',coalesce(dispatch->'history','[]')||jsonb_build_array(jsonb_build_object('at',now(),'state',state,'provider',provider_name))) WHERE id=d.id;
 RETURN true;
END $$;

CREATE OR REPLACE FUNCTION public.hg_due_notification_dispatch(p_limit integer DEFAULT 50)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce(jsonb_agg(id),'[]') FROM (SELECT id FROM public.notification_deliveries
 WHERE dispatch->>'version'='1' AND ((dispatch->>'state'='queued' AND (dispatch->>'next_at')::timestamptz<=now())
 OR (dispatch->>'state' IN ('claimed','sending') AND (dispatch->>'lease_until')::timestamptz<=now()))
 ORDER BY created_at,id LIMIT greatest(1,least(coalesce(p_limit,50),100))) due;
$$;

CREATE OR REPLACE FUNCTION public.hg_notification_recovery_list(p_actor_id uuid,p_campus_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype; result jsonb;
BEGIN
 SELECT * INTO a FROM public.profiles WHERE id=p_actor_id AND is_active;
 IF NOT FOUND OR a.role::text NOT IN ('admin','super_admin') THEN RAISE EXCEPTION 'Recovery access denied' USING ERRCODE='42501'; END IF;
 IF a.role::text<>'super_admin' THEN
  IF p_campus_id IS NOT NULL AND p_campus_id IS DISTINCT FROM a.campus_id THEN RAISE EXCEPTION 'Recovery campus mismatch' USING ERRCODE='42501'; END IF;
  p_campus_id:=a.campus_id;
  IF p_campus_id IS NULL THEN RAISE EXCEPTION 'Recovery campus required' USING ERRCODE='42501'; END IF;
 END IF;
 SELECT coalesce(jsonb_agg(x),'[]') INTO result FROM (SELECT id,notification_id,channel,status,provider,provider_message_id,error_message,created_at,
  dispatch->>'state' as state,dispatch->>'attempts' as attempts,dispatch_payload->'notification'->>'title' as title,
  dispatch_payload->'notification'->>'email' as recipient
  FROM public.notification_deliveries WHERE dispatch->>'version'='1' AND status IN ('queued','sending','uncertain','failed')
  AND (p_campus_id IS NULL OR campus_id=p_campus_id) ORDER BY created_at DESC LIMIT 50) x;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.hg_reconcile_notification_dispatch(p_actor_id uuid,p_id uuid,p_review_id uuid,p_outcome text,p_provider text,p_message_id text,p_evidence text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype; d public.notification_deliveries%rowtype; review jsonb;
BEGIN
 SELECT * INTO a FROM public.profiles WHERE id=p_actor_id AND is_active;
 IF NOT FOUND OR a.role::text NOT IN ('admin','super_admin') THEN RAISE EXCEPTION 'Recovery access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO d FROM public.notification_deliveries WHERE id=p_id AND dispatch->>'version'='1' FOR UPDATE;
 IF NOT FOUND OR (a.role::text<>'super_admin' AND (d.campus_id IS NULL OR a.campus_id IS DISTINCT FROM d.campus_id)) THEN RAISE EXCEPTION 'Recovery access denied' USING ERRCODE='42501'; END IF;
 IF p_review_id IS NULL OR p_outcome IS NULL OR p_provider IS NULL OR p_outcome NOT IN ('sent','not_sent') OR p_provider NOT IN ('onesignal','resend')
 OR p_evidence IS NULL OR length(trim(p_evidence)) NOT BETWEEN 10 AND 500 OR (d.channel='push' AND p_provider<>'onesignal')
 OR (p_outcome='sent' AND (nullif(trim(p_message_id),'') IS NULL OR length(p_message_id)>300)) THEN RAISE EXCEPTION 'Invalid provider evidence'; END IF;
 review:=jsonb_build_object('id',p_review_id,'actor',p_actor_id,'outcome',p_outcome,'provider',p_provider,'message_id',p_message_id,'evidence',trim(p_evidence));
 IF d.dispatch->'review'->>'id'=p_review_id::text THEN
  IF d.dispatch->'review' IS DISTINCT FROM review THEN RAISE EXCEPTION 'Review intent conflict'; END IF;
  RETURN jsonb_build_object('status',d.status,'idempotent',true);
 END IF;
 IF d.dispatch->>'state' NOT IN ('uncertain','failed') THEN RAISE EXCEPTION 'Delivery is not awaiting review'; END IF;
 UPDATE public.notification_deliveries SET status=CASE WHEN p_outcome='sent' THEN 'sent' ELSE 'queued' END,
  provider=p_provider,provider_message_id=CASE WHEN p_outcome='sent' THEN p_message_id ELSE NULL END,
  error_message=NULL,delivered_at=CASE WHEN p_outcome='sent' THEN now() ELSE NULL END,
  dispatch_payload=CASE WHEN p_outcome='sent' THEN dispatch_payload ELSE dispatch_payload-'prepared' END,
  dispatch=dispatch||jsonb_build_object('state',CASE WHEN p_outcome='sent' THEN 'sent' ELSE 'queued' END,'review',review,'token',NULL,
    'attempts',0,'key',CASE WHEN p_outcome='not_sent' THEN gen_random_uuid()::text ELSE dispatch->>'key' END,
    'next_at',now(),'expires_at',now()+interval '24 hours') WHERE id=d.id;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value)
 VALUES(a.id,a.role::text,'notification_delivery',d.id::text,'delivery_reconciled',review);
 RETURN jsonb_build_object('status',CASE WHEN p_outcome='sent' THEN 'sent' ELSE 'queued' END,'idempotent',false);
END $$;

REVOKE ALL ON FUNCTION public.hg_claim_notification_dispatch(uuid),public.hg_begin_notification_dispatch(uuid,uuid,jsonb),public.hg_finish_notification_dispatch(uuid,uuid,jsonb),public.hg_due_notification_dispatch(integer),public.hg_notification_recovery_list(uuid,uuid),public.hg_reconcile_notification_dispatch(uuid,uuid,uuid,text,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_claim_notification_dispatch(uuid),public.hg_begin_notification_dispatch(uuid,uuid,jsonb),public.hg_finish_notification_dispatch(uuid,uuid,jsonb),public.hg_due_notification_dispatch(integer),public.hg_notification_recovery_list(uuid,uuid),public.hg_reconcile_notification_dispatch(uuid,uuid,uuid,text,text,text,text) TO service_role;
