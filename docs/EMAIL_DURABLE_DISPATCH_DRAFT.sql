-- NOT APPLIED. Queue/worker application integration is incomplete. Do not run for deployment.
-- Review draft. Reuse delivery receipts and private settings; no new table.
ALTER TABLE public.notification_deliveries
 ADD COLUMN IF NOT EXISTS email_payload jsonb,
 ADD COLUMN IF NOT EXISTS dispatch jsonb NOT NULL DEFAULT '{}'::jsonb;
-- Recipient HTML and contact addresses must never become raw client-readable.
DROP POLICY IF EXISTS notification_delivery_email_payload_private ON public.notification_deliveries;
CREATE POLICY notification_delivery_email_payload_private ON public.notification_deliveries
 AS RESTRICTIVE FOR ALL TO anon,authenticated
 USING (channel <> 'email') WITH CHECK (channel <> 'email');
CREATE INDEX IF NOT EXISTS notification_deliveries_email_queue_idx
 ON public.notification_deliveries(status,created_at) WHERE channel='email';

CREATE OR REPLACE FUNCTION public.hg_email_enqueue(p_id uuid,p_payload jsonb,p_provider text,
 p_notification_id uuid DEFAULT NULL,p_user_id uuid DEFAULT NULL,p_campus_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_row public.notification_deliveries%ROWTYPE; v_notification public.notifications%ROWTYPE;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'email_forbidden' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_provider NOT IN ('resend','onesignal') OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
  OR jsonb_typeof(p_payload->'to_email') IS DISTINCT FROM 'string' OR length(p_payload->>'to_email') NOT BETWEEN 3 AND 320
  OR jsonb_typeof(p_payload->'subject') IS DISTINCT FROM 'string' OR length(p_payload->>'subject') NOT BETWEEN 1 AND 500
  OR jsonb_typeof(p_payload->'html') IS DISTINCT FROM 'string' OR length(p_payload->>'html') NOT BETWEEN 1 AND 1000000
 THEN RAISE EXCEPTION 'email_invalid'; END IF;
 IF p_notification_id IS NOT NULL THEN
  SELECT * INTO v_notification FROM public.notifications WHERE id=p_notification_id AND channel='email';
  IF NOT FOUND OR v_notification.user_id IS DISTINCT FROM p_user_id THEN RAISE EXCEPTION 'email_invalid_notification'; END IF;
 END IF;
 INSERT INTO public.notification_deliveries(id,notification_id,user_id,channel,status,campus_id,email_payload,dispatch)
 VALUES(p_id,p_notification_id,p_user_id,'email','queued',p_campus_id,p_payload,
  jsonb_build_object('preferred_provider',p_provider,'attempt_count',0,'next_attempt_at',now(),'expires_at',now()+interval '24 hours'))
 ON CONFLICT(id) DO NOTHING;
 SELECT * INTO v_row FROM public.notification_deliveries WHERE id=p_id;
 IF v_row.channel<>'email' OR v_row.notification_id IS DISTINCT FROM p_notification_id
  OR v_row.user_id IS DISTINCT FROM p_user_id OR v_row.email_payload IS DISTINCT FROM p_payload
 THEN RAISE EXCEPTION 'email_intent_conflict'; END IF;
 RETURN to_jsonb(v_row);
END;
$function$;

CREATE OR REPLACE FUNCTION public.hg_email_begin(p_id uuid,p_provider text,p_limit integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_row public.notification_deliveries%ROWTYPE; v_key text; v_setting jsonb;
 v_period text; v_end timestamptz; v_count integer; v_token uuid; v_blocked timestamptz;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'email_forbidden' USING ERRCODE='42501'; END IF;
 IF p_provider NOT IN ('resend','onesignal') OR p_limit NOT BETWEEN 1 AND 1000000 THEN RAISE EXCEPTION 'email_invalid'; END IF;
 SELECT * INTO v_row FROM public.notification_deliveries WHERE id=p_id AND channel='email' FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('state','missing'); END IF;
 IF v_row.status='dispatching' AND (v_row.dispatch->>'lease_until')::timestamptz<=now() THEN
  UPDATE public.notification_deliveries SET status='uncertain',error_message='worker_interrupted_after_reservation' WHERE id=p_id;
  RETURN jsonb_build_object('state','uncertain');
 END IF;
 IF v_row.status<>'queued' THEN RETURN jsonb_build_object('state',v_row.status); END IF;
 IF (v_row.dispatch->>'expires_at')::timestamptz<=now() OR coalesce((v_row.dispatch->>'attempt_count')::integer,0)>=6 THEN
  UPDATE public.notification_deliveries SET status='failed',error_message='retry_expired' WHERE id=p_id;
  RETURN jsonb_build_object('state','failed');
 END IF;
 v_period:=CASE WHEN p_provider='resend' THEN to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD') ELSE to_char(now() AT TIME ZONE 'UTC','YYYY-MM') END;
 v_end:=CASE WHEN p_provider='resend' THEN (date_trunc('day',now() AT TIME ZONE 'UTC')+interval '1 day') AT TIME ZONE 'UTC'
  ELSE (date_trunc('month',now() AT TIME ZONE 'UTC')+interval '1 month') AT TIME ZONE 'UTC' END;
 v_key:='email_dispatch_quota_'||p_provider;
 PERFORM pg_advisory_xact_lock(hashtextextended(v_key,0));
 SELECT value INTO v_setting FROM public.system_settings WHERE key=v_key AND campus_id IS NULL FOR UPDATE;
 IF v_setting IS NULL OR v_setting->>'period' IS DISTINCT FROM v_period THEN
  v_setting:=jsonb_build_object('period',v_period,'reserved_or_accepted',0,'blocked_until',NULL,'reset_at',v_end);
 END IF;
 v_count:=coalesce((v_setting->>'reserved_or_accepted')::integer,0);
 v_blocked:=nullif(v_setting->>'blocked_until','')::timestamptz;
 IF v_count>=p_limit OR v_blocked>now() THEN
  IF v_count>=p_limit THEN v_blocked:=v_end; END IF;
  RETURN jsonb_build_object('state','quota','retry_at',v_blocked,'provider',p_provider);
 END IF;
 v_setting:=v_setting||jsonb_build_object('reserved_or_accepted',v_count+1,'limit',p_limit,'reset_at',v_end);
 UPDATE public.system_settings SET value=v_setting,is_public=false,updated_at=now() WHERE key=v_key AND campus_id IS NULL;
 IF NOT FOUND THEN INSERT INTO public.system_settings(key,value,is_public) VALUES(v_key,v_setting,false); END IF;
 v_token:=gen_random_uuid();
 UPDATE public.notification_deliveries SET status='dispatching',dispatch=dispatch||jsonb_build_object(
  'active_token',v_token,'active_provider',p_provider,'active_period',v_period,'lease_until',now()+interval '2 minutes',
  'attempt_count',coalesce((dispatch->>'attempt_count')::integer,0)+1)
 WHERE id=p_id RETURNING * INTO v_row;
 RETURN jsonb_build_object('state','dispatching','token',v_token,'payload',v_row.email_payload);
END;
$function$;

CREATE OR REPLACE FUNCTION public.hg_email_finish(p_id uuid,p_token uuid,p_result jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_row public.notification_deliveries%ROWTYPE; v_provider text; v_key text; v_setting jsonb;
 v_state text; v_until timestamptz; v_dispatch jsonb; v_history jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'email_forbidden' USING ERRCODE='42501'; END IF;
 SELECT * INTO v_row FROM public.notification_deliveries WHERE id=p_id AND channel='email' FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('state','missing'); END IF;
 IF v_row.status<>'dispatching' OR v_row.dispatch->>'active_token' IS DISTINCT FROM p_token::text THEN RETURN jsonb_build_object('state',v_row.status,'replayed',true); END IF;
 v_state:=p_result->>'state';
 IF v_state NOT IN ('accepted','quota','rejected','uncertain','unavailable') THEN RAISE EXCEPTION 'email_invalid_result'; END IF;
 v_provider:=v_row.dispatch->>'active_provider';v_key:='email_dispatch_quota_'||v_provider;
 IF v_state IN ('quota','rejected','unavailable') THEN
  PERFORM pg_advisory_xact_lock(hashtextextended(v_key,0));
  SELECT value INTO v_setting FROM public.system_settings WHERE key=v_key AND campus_id IS NULL FOR UPDATE;
  IF v_setting->>'period'=v_row.dispatch->>'active_period' THEN
   v_setting:=v_setting||jsonb_build_object('reserved_or_accepted',greatest(0,coalesce((v_setting->>'reserved_or_accepted')::integer,0)-1));
   IF v_state='quota' THEN
    v_until:=CASE WHEN coalesce((p_result->>'period_quota')::boolean,false) THEN (v_setting->>'reset_at')::timestamptz
     ELSE now()+make_interval(secs=>greatest(1,least(3600,coalesce((p_result->>'retry_after')::integer,60)))) END;
    v_setting:=v_setting||jsonb_build_object('blocked_until',v_until,'last_quota_at',now());
   END IF;
   UPDATE public.system_settings SET value=v_setting,is_public=false,updated_at=now() WHERE key=v_key AND campus_id IS NULL;
  END IF;
 END IF;
 v_history:=coalesce(v_row.dispatch->'attempts','[]'::jsonb)||jsonb_build_array(jsonb_build_object(
  'provider',v_provider,'state',v_state,'at',now(),'status',p_result->'http_status','provider_message_id',p_result->'message_id','recipients',p_result->'recipients'));
 v_dispatch:=(v_row.dispatch-array['active_token','lease_until'])||jsonb_build_object('provider_used',v_provider,
  'attempts',v_history,'last_result',p_result,'next_attempt_at',coalesce(v_until,now()));
 UPDATE public.notification_deliveries SET status=CASE WHEN v_state IN ('quota','unavailable') THEN 'queued'
    WHEN v_state='rejected' THEN 'failed' ELSE v_state END,
  provider_message_id=p_result->>'message_id',error_message=CASE WHEN v_state='accepted' THEN NULL ELSE coalesce(p_result->>'error_code',v_state) END,
  dispatch=v_dispatch WHERE id=p_id RETURNING * INTO v_row;
 -- Acceptance is not provider delivery; delivered_at stays NULL until a verified receipt arrives.
 RETURN jsonb_build_object('state',v_row.status,'provider',v_provider,'retry_at',v_until);
END;
$function$;

CREATE OR REPLACE FUNCTION public.hg_email_due(p_limit integer DEFAULT 50)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_rows jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'email_forbidden' USING ERRCODE='42501'; END IF;
 UPDATE public.notification_deliveries SET status='uncertain',error_message='worker_interrupted_after_reservation'
 WHERE channel='email' AND status='dispatching' AND (dispatch->>'lease_until')::timestamptz<=now();
 UPDATE public.notification_deliveries SET status='failed',error_message='retry_expired'
 WHERE channel='email' AND status='queued' AND (dispatch->>'expires_at')::timestamptz<=now();
 SELECT coalesce(jsonb_agg(id),'[]'::jsonb) INTO v_rows FROM (
  SELECT id FROM public.notification_deliveries WHERE channel='email' AND status='queued'
   AND email_payload IS NOT NULL AND (dispatch->>'next_attempt_at')::timestamptz<=now()
  ORDER BY created_at,id LIMIT greatest(1,least(coalesce(p_limit,50),100))) s;
 RETURN v_rows;
END;
$function$;

REVOKE ALL ON FUNCTION public.hg_email_enqueue(uuid,jsonb,text,uuid,uuid,uuid) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.hg_email_begin(uuid,text,integer) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.hg_email_finish(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.hg_email_due(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_email_enqueue(uuid,jsonb,text,uuid,uuid,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.hg_email_begin(uuid,text,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.hg_email_finish(uuid,uuid,jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.hg_email_due(integer) TO service_role;
