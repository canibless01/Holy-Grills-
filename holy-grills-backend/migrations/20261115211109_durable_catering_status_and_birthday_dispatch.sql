-- Capture status intent with the edit; reuse the existing bounded, leased mail dispatcher.
ALTER TABLE hg_internal.operations_emails DROP CONSTRAINT operations_emails_kind_check;
ALTER TABLE hg_internal.operations_emails ADD CONSTRAINT operations_emails_kind_check CHECK(kind IN('paid_order','abandoned_cart','daily_report','weekly_report','birthday_report','catering_status'));
CREATE FUNCTION hg_internal.capture_catering_status_email() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 -- A protocol marker avoids duplicate legacy thread + outbox sends during rolling API deploys.
 IF coalesce(nullif(current_setting('request.headers',true),''),'{}')::jsonb->>'x-hg-write-protocol' IS DISTINCT FROM 'catering-status-v1' THEN RETURN NEW;END IF;
 IF NEW.status IS NOT DISTINCT FROM OLD.status OR nullif(btrim(NEW.email),'') IS NULL OR NEW.campus_id IS NULL THEN RETURN NEW;END IF;
 INSERT INTO hg_internal.operations_emails(campus_id,kind,reference,recipient,payload)
 VALUES(NEW.campus_id,'catering_status',NEW.id||':'||NEW.updated_at||':'||NEW.status,lower(btrim(NEW.email)),jsonb_build_object('request_id',NEW.id,'status',NEW.status,'version',NEW.updated_at,'name',NEW.organizer_name))
 ON CONFLICT DO NOTHING;
 RETURN NEW;
END$$;
REVOKE ALL ON FUNCTION hg_internal.capture_catering_status_email() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.capture_catering_status_email() TO service_role;
CREATE TRIGGER capture_catering_status_email AFTER UPDATE OF status ON public.catering_requests FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_catering_status_email();
-- Guest/member submission uses the rate-limited service API, not direct PostgREST inserts.
-- Admin status edits retain UPDATE and the current campus RLS.
REVOKE INSERT ON public.catering_requests FROM PUBLIC,anon,authenticated;

CREATE OR REPLACE FUNCTION public.hg_operations_email_outbox(p_action text, p_id uuid DEFAULT NULL::uuid, p_token uuid DEFAULT NULL::uuid, p_data jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE due_at timestamptz;result jsonb;row hg_internal.operations_emails%rowtype;cfg jsonb;flag text;
BEGIN
 IF p_action='claim' THEN
  UPDATE hg_internal.operations_emails SET state='uncertain',updated_at=now() WHERE state='sending' AND lease_until<now();
  UPDATE hg_internal.operations_emails SET state='pending',token=NULL,updated_at=now() WHERE state='claimed' AND lease_until<now();
  WITH due AS (SELECT id FROM hg_internal.operations_emails WHERE state='pending' AND available_at<=now() AND (p_data->>'campus_id' IS NULL OR campus_id=(p_data->>'campus_id')::uuid) AND (p_data->>'catering_request_id' IS NULL OR (kind='catering_status' AND payload->>'request_id'=p_data->>'catering_request_id')) ORDER BY created_at LIMIT 20 FOR UPDATE SKIP LOCKED),
  claimed AS (UPDATE hg_internal.operations_emails e SET state='claimed',token=gen_random_uuid(),lease_until=now()+interval '10 minutes',updated_at=now() FROM due WHERE e.id=due.id RETURNING e.*)
  SELECT coalesce(jsonb_agg(to_jsonb(c)),'[]') INTO result FROM claimed c;RETURN result;
 ELSIF p_action IN ('begin','finish') THEN
  SELECT * INTO row FROM hg_internal.operations_emails WHERE id=p_id AND token=p_token FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF p_action='finish' THEN
   IF row.state<>'sending' OR p_data->>'state' NOT IN ('accepted','failed','uncertain','cancelled') THEN RETURN NULL; END IF;
   UPDATE hg_internal.operations_emails SET state=p_data->>'state',receipt=p_data->'receipt',updated_at=now() WHERE id=row.id;
   RETURN '{"saved":true}';
  END IF;
  IF row.state<>'claimed' OR row.lease_until<now() THEN RETURN NULL; END IF;
  IF row.kind='catering_status' THEN
   IF NOT EXISTS(SELECT 1 FROM public.catering_requests r JOIN public.campuses c ON c.id=r.campus_id AND c.is_active
     WHERE r.id=(row.payload->>'request_id')::uuid AND r.campus_id=row.campus_id AND lower(btrim(r.email))=row.recipient
       AND r.status=row.payload->>'status'
       AND NOT EXISTS(SELECT 1 FROM hg_internal.operations_emails newer WHERE newer.kind='catering_status' AND newer.payload->>'request_id'=row.payload->>'request_id' AND (newer.payload->>'version')::timestamptz>(row.payload->>'version')::timestamptz)) THEN
    UPDATE hg_internal.operations_emails SET state='cancelled',updated_at=now() WHERE id=row.id;RETURN NULL;
   END IF;
  ELSE
  flag:=CASE row.kind WHEN 'paid_order' THEN 'paid_order_alerts' WHEN 'abandoned_cart' THEN 'abandoned_cart_alerts' ELSE row.kind END;
  SELECT value INTO cfg FROM public.system_settings WHERE key='campus_operations_email' AND campus_id=row.campus_id AND NOT is_public;
  IF cfg IS NULL OR NOT coalesce((cfg->>flag)::boolean,row.kind='birthday_report') OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(cfg->'recipients') email WHERE lower(btrim(email))=row.recipient)
   OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=row.campus_id AND is_active) THEN
   UPDATE hg_internal.operations_emails SET state='cancelled',updated_at=now() WHERE id=row.id;RETURN NULL;
  END IF;
  END IF;
  IF row.kind='abandoned_cart' THEN
   due_at:=public.hg_operations_cart_alert_due((row.payload->>'cart_id')::uuid);
   IF due_at IS NULL THEN
    UPDATE hg_internal.operations_emails SET state='cancelled',updated_at=now() WHERE id=row.id;RETURN NULL;
   ELSIF due_at>now() THEN
    UPDATE hg_internal.operations_emails SET state='pending',available_at=due_at,token=NULL,lease_until=NULL,updated_at=now() WHERE id=row.id;RETURN NULL;
   END IF;
  END IF;
  UPDATE hg_internal.operations_emails SET state='sending',updated_at=now() WHERE id=row.id;
  RETURN to_jsonb(row);
 END IF;
 RAISE EXCEPTION 'Invalid operations email action';
END $function$;
