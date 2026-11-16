-- Event operations reuse the private review row and existing refund/dispatch
-- receipts. No ticket prices, organizer contracts or earned HP are rewritten.
ALTER TABLE hg_internal.event_organizer_reviews ADD COLUMN lifecycle_receipts jsonb NOT NULL DEFAULT '[]',ADD COLUMN cancelled_by uuid REFERENCES public.profiles(id);

CREATE OR REPLACE FUNCTION hg_internal.queue_event_change_notices(p_event uuid,p_request uuid,p_copy jsonb)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE e events%rowtype;t event_tickets%rowtype;p profiles%rowtype;prefs notification_preferences%rowtype;kind text;heading text;message text;address text;person text;ch text;notice uuid;meta jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM events WHERE id=p_event;
 kind:=CASE WHEN e.metadata->>'lifecycle_status'='cancelled' THEN 'event_cancelled' ELSE 'event_rescheduled' END;
 heading:=p_copy->>(kind||'_title');message:=p_copy->>(kind||'_body');
 IF nullif(heading,'') IS NULL OR nullif(message,'') IS NULL THEN RAISE EXCEPTION 'HG_EVENT_CHANGE_INVALID';END IF;
 heading:=replace(heading,'{title}',e.title);
 message:=replace(replace(replace(replace(message,'{title}',e.title),'{date}',to_char(e.starts_at AT TIME ZONE 'Africa/Lagos','Dy, DD Mon YYYY HH24:MI')||' WAT'),'{venue}',coalesce(e.location,'')),'{reason}',e.metadata->>'change_reason');
 meta:=jsonb_build_object('_dispatch_version',1,'event_id',e.id,'event_change_id',p_request);
 FOR t IN SELECT * FROM event_tickets WHERE event_id=p_event AND metadata->>'event_change_id'=p_request::text ORDER BY id LOOP
  IF t.user_id IS NOT NULL THEN
   SELECT * INTO p FROM profiles WHERE id=t.user_id AND is_active;
   IF NOT FOUND THEN CONTINUE;END IF;
   SELECT * INTO prefs FROM notification_preferences WHERE user_id=t.user_id;
   IF prefs.order_updates IS FALSE THEN CONTINUE;END IF;
   FOREACH ch IN ARRAY ARRAY['in_app','push','email'] LOOP
    IF ch='push' AND (p.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) OR ch='email' AND (p.email_notifications IS FALSE OR prefs.email_enabled IS FALSE) THEN CONTINUE;END IF;
    notice:=md5('event-change:'||p_request||':'||t.id||':'||ch)::uuid;
    INSERT INTO notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
     VALUES(notice,t.user_id,kind,heading,message,ch,'/events/'||p_event,t.campus_id,p_request,meta) ON CONFLICT(id) DO NOTHING;
   END LOOP;
  ELSE
   address:=lower(btrim(t.guest_email::text));person:=coalesce(nullif(t.guest_name,''),'there');
   IF nullif(address,'') IS NULL THEN CONTINUE;END IF;
   notice:=md5('event-change:'||p_request||':'||t.id||':email')::uuid;
   INSERT INTO notification_deliveries(id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
    VALUES(notice,NULL,'email','queued',t.campus_id,
     jsonb_build_object('version',1,'state','queued','key',gen_random_uuid(),'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
     jsonb_build_object('kind','event_status_email','ticket_id',t.id,'event_id',e.id,'notification',jsonb_build_object('user_id',NULL,'type',kind,'title',heading,'body',message,'email',address,'name',person,'action_url','/events/'||p_event,'metadata',meta)))
    ON CONFLICT(id) DO NOTHING;
  END IF;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION hg_internal.queue_event_change_notices(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.queue_event_change_notices(uuid,uuid,jsonb) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_change_event_operation(p_actor uuid,p_event uuid,p_request uuid,p_action text,p_data jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a profiles%rowtype;e events%rowtype;t event_tickets%rowtype;prior jsonb;result jsonb;start_time timestamptz;end_time timestamptz;venue text;reason text;refund_result jsonb;refund_count integer:=0;free_count integer:=0;waiting_count integer:=0;previous_operation text;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM profiles WHERE id=p_actor AND is_active AND role::text IN('admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM events WHERE id=p_event FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_NOT_FOUND' USING ERRCODE='P0002';END IF;
 IF a.role::text<>'super_admin' AND (e.campus_id IS NULL OR e.campus_id IS DISTINCT FROM a.campus_id) THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 IF p_request IS NULL OR p_action NOT IN('reschedule','cancel') OR p_action IS NULL OR jsonb_typeof(p_data) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'HG_EVENT_CHANGE_INVALID';END IF;
 SELECT item INTO prior FROM hg_internal.event_organizer_reviews r CROSS JOIN LATERAL jsonb_array_elements(r.lifecycle_receipts)item WHERE r.event_id=e.id AND item->>'id'=p_request::text;
 IF prior IS NOT NULL THEN
  IF prior->>'actor'<>p_actor::text OR prior->>'action'<>p_action OR prior->'arguments' IS DISTINCT FROM p_data-'_copy' THEN RAISE EXCEPTION 'HG_ORGANIZER_CONFLICT' USING ERRCODE='23505';END IF;
  RETURN prior->'result'||jsonb_build_object('replayed',true);
 END IF;
 IF e.metadata->>'lifecycle_status'='cancelled' THEN RAISE EXCEPTION 'HG_EVENT_ALREADY_CANCELLED';END IF;
 IF nullif(p_data->>'expected_updated_at','') IS NULL OR (p_data->>'expected_updated_at')::timestamptz IS DISTINCT FROM e.updated_at THEN RAISE EXCEPTION 'HG_EVENT_CHANGE_STALE' USING ERRCODE='40001';END IF;
 reason:=btrim(coalesce(p_data->>'reason',''));
 IF length(reason) NOT BETWEEN 10 AND 500 OR e.review_status<>'approved' THEN RAISE EXCEPTION 'HG_EVENT_CHANGE_INVALID';END IF;
 IF p_action='reschedule' THEN
  start_time:=(p_data->>'starts_at')::timestamptz;end_time:=(p_data->>'ends_at')::timestamptz;venue:=btrim(coalesce(p_data->>'location',e.location));
  IF start_time IS NULL OR end_time IS NULL OR start_time<=now() OR end_time<=start_time OR length(venue) NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'HG_EVENT_CHANGE_INVALID';END IF;
  IF EXISTS(SELECT 1 FROM event_checkins ci JOIN event_tickets ticket ON ticket.id=ci.ticket_id WHERE ticket.event_id=e.id) THEN RAISE EXCEPTION 'HG_EVENT_ADMISSION_STARTED';END IF;
  IF start_time=e.starts_at AND end_time=e.ends_at AND venue=e.location THEN RAISE EXCEPTION 'HG_EVENT_CHANGE_UNCHANGED';END IF;
  previous_operation:=current_setting('hg.event_operation',true);PERFORM set_config('hg.event_operation',e.id::text,true);
  UPDATE events SET starts_at=start_time,ends_at=end_time,location=venue,metadata=coalesce(metadata,'{}')||jsonb_build_object('lifecycle_status','rescheduled','latest_change_id',p_request,'change_reason',reason,'changed_at',now()) WHERE id=e.id;
  PERFORM set_config('hg.event_operation',coalesce(previous_operation,''),true);
  UPDATE event_tickets SET metadata=coalesce(metadata,'{}')||jsonb_build_object('event_change_id',p_request),qr_expires_at=CASE WHEN qr_expires_at IS NULL THEN NULL ELSE end_time+greatest(qr_expires_at-coalesce(e.ends_at,e.starts_at),interval '0 seconds') END WHERE event_id=e.id AND status NOT IN('cancelled','canceled','expired');
 ELSE
  -- The approval is durable, so later successful payments can be refunded even
  -- if the approving account is subsequently deactivated or changes role.
  INSERT INTO hg_internal.event_organizer_reviews(event_id,cancelled_by) VALUES(e.id,p_actor) ON CONFLICT(event_id) DO UPDATE SET cancelled_by=EXCLUDED.cancelled_by;
  previous_operation:=current_setting('hg.event_operation',true);PERFORM set_config('hg.event_operation',e.id::text,true);
  UPDATE events SET metadata=coalesce(metadata,'{}')||jsonb_build_object('lifecycle_status','cancelled','latest_change_id',p_request,'change_reason',reason,'changed_at',now()) WHERE id=e.id;
  PERFORM set_config('hg.event_operation',coalesce(previous_operation,''),true);
  FOR t IN SELECT * FROM event_tickets WHERE event_id=e.id AND status NOT IN('cancelled','canceled','expired') ORDER BY id FOR UPDATE LOOP
   UPDATE event_tickets SET metadata=coalesce(metadata,'{}')||jsonb_build_object('event_change_id',p_request) WHERE id=t.id;
   IF EXISTS(SELECT 1 FROM event_checkins WHERE ticket_id=t.id) THEN CONTINUE;END IF;
   IF t.status='confirmed' AND t.payment_status='paid' THEN
    refund_result:=hg_request_event_ticket_refund(p_actor,e.id,t.id,md5('event-cancel-refund:'||e.id||':'||t.id)::uuid,reason);refund_count:=refund_count+1;
   ELSIF t.status='confirmed' AND t.payment_status='not_required' THEN
    UPDATE event_tickets SET status='cancelled',updated_at=now() WHERE id=t.id;
    IF t.tier_id IS NOT NULL THEN UPDATE event_ticket_tiers SET sold_count=greatest(0,sold_count-1) WHERE id=t.tier_id;END IF;
    free_count:=free_count+1;
   ELSE waiting_count:=waiting_count+1;
   END IF;
  END LOOP;
 END IF;
 PERFORM hg_internal.queue_event_change_notices(e.id,p_request,p_data->'_copy');
 result:=jsonb_build_object('id',p_request,'action',p_action,'refunds',refund_count,'free_cancelled',free_count,'awaiting_payment',waiting_count,'replayed',false);
 INSERT INTO hg_internal.event_organizer_reviews(event_id,lifecycle_receipts) VALUES(e.id,jsonb_build_array(jsonb_build_object('id',p_request,'actor',p_actor,'action',p_action,'arguments',p_data-'_copy','result',result,'at',now(),'previous_starts_at',e.starts_at,'previous_ends_at',e.ends_at,'previous_location',e.location)))
 ON CONFLICT(event_id) DO UPDATE SET lifecycle_receipts=event_organizer_reviews.lifecycle_receipts||EXCLUDED.lifecycle_receipts;
 INSERT INTO admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value) VALUES(p_actor,a.role::text,'event',e.id::text,'event_'||p_action,result);
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.hg_change_event_operation(uuid,uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_change_event_operation(uuid,uuid,uuid,text,jsonb) TO service_role;

-- No caller, including an older API during deployment, may issue a new ticket
-- for a cancelled event. Existing tickets keep their history and receipts.
CREATE OR REPLACE FUNCTION hg_internal.guard_cancelled_event_ticket()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 PERFORM 1 FROM events WHERE id=NEW.event_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM events WHERE id=NEW.event_id AND metadata->>'lifecycle_status'='cancelled') THEN RAISE EXCEPTION 'HG_EVENT_ALREADY_CANCELLED';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.guard_cancelled_event_ticket() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_cancelled_event_ticket() TO service_role;
CREATE TRIGGER guard_cancelled_event_ticket BEFORE INSERT ON event_tickets FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_cancelled_event_ticket();

DO $migration$
DECLARE definition text;
BEGIN
 definition:=pg_get_functiondef('public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer)'::regprocedure);
 IF position('IF NOT FOUND OR NOT e.is_published' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected admission definition';END IF;
 definition:=replace(definition,'IF NOT FOUND OR NOT e.is_published','IF NOT FOUND OR e.metadata->>''lifecycle_status''=''cancelled'' OR NOT e.is_published');EXECUTE definition;
 definition:=pg_get_functiondef('public.hg_request_event_ticket_refund(uuid,uuid,uuid,uuid,text)'::regprocedure);
 IF position('WHERE id=p_actor_id AND is_active;' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected refund actor check';END IF;
 definition:=replace(definition,'WHERE id=p_actor_id AND is_active;','WHERE id=p_actor_id AND (is_active OR EXISTS(SELECT 1 FROM hg_internal.event_organizer_reviews cancel_approval JOIN public.events event ON event.id=cancel_approval.event_id WHERE cancel_approval.event_id=p_event_id AND cancel_approval.cancelled_by=p_actor_id AND event.metadata->>''lifecycle_status''=''cancelled''));');
 definition:=replace(definition,'IF NOT FOUND OR a.role::text NOT IN (''admin'',''super_admin'') THEN','IF NOT FOUND OR (a.role::text NOT IN (''admin'',''super_admin'') AND NOT EXISTS(SELECT 1 FROM hg_internal.event_organizer_reviews cancel_approval JOIN public.events event ON event.id=cancel_approval.event_id WHERE cancel_approval.event_id=p_event_id AND cancel_approval.cancelled_by=p_actor_id AND event.metadata->>''lifecycle_status''=''cancelled'')) THEN');definition:=replace(definition,'IF NOT FOUND OR (a.role::text<>''super_admin'' AND (t.campus_id IS NULL OR t.campus_id IS DISTINCT FROM a.campus_id)) THEN','IF NOT FOUND OR (a.role::text<>''super_admin'' AND (t.campus_id IS NULL OR t.campus_id IS DISTINCT FROM a.campus_id) AND NOT EXISTS(SELECT 1 FROM hg_internal.event_organizer_reviews cancel_approval JOIN public.events event ON event.id=cancel_approval.event_id WHERE cancel_approval.event_id=p_event_id AND cancel_approval.cancelled_by=p_actor_id AND event.metadata->>''lifecycle_status''=''cancelled'')) THEN');EXECUTE definition;
END $migration$;

CREATE OR REPLACE FUNCTION public.hg_pay_event_with_delivery(p_ticket_id uuid,p_provider text DEFAULT NULL,p_provider_reference text DEFAULT NULL,p_amount numeric DEFAULT NULL,p_metadata jsonb DEFAULT '{}')
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE t event_tickets%rowtype;e events%rowtype;result uuid;actor uuid;refund_result jsonb;expired boolean:=false;
BEGIN
 SELECT event_id INTO e.id FROM event_tickets WHERE id=p_ticket_id;
 SELECT * INTO e FROM events WHERE id=e.id FOR UPDATE;
 SELECT * INTO t FROM event_tickets WHERE id=p_ticket_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Ticket not found';END IF;
 IF p_amount IS NOT NULL AND (p_amount::text IN('NaN','Infinity','-Infinity') OR abs(p_amount-t.card_amount_used)>0.01) THEN RAISE EXCEPTION 'Amount mismatch';END IF;
 IF t.payment_reference IS NOT NULL AND p_provider_reference IS DISTINCT FROM t.payment_reference THEN RAISE EXCEPTION 'Payment reference mismatch';END IF;
 IF e.metadata->>'lifecycle_status'='cancelled' THEN
  IF EXISTS(SELECT 1 FROM hg_internal.event_ticket_refunds WHERE ticket_id=t.id) THEN SELECT id INTO result FROM payments WHERE ticket_id=t.id AND reference=p_provider_reference;RETURN result;END IF;
  SELECT cancelled_by INTO actor FROM hg_internal.event_organizer_reviews WHERE event_id=e.id;
  IF actor IS NULL THEN RAISE EXCEPTION 'HG_EVENT_CANCEL_REFUND_UNAVAILABLE';END IF;
  IF t.status='cancelled' AND t.metadata ? 'expiry_receipt' AND t.payment_status='expired' THEN
   expired:=true;
   -- The expiry receipt already returned wallet/HP and released the seat. Only
   -- this newly received card amount is refundable; do not release it twice.
   UPDATE event_tickets SET status='pending_payment',payment_status='pending',tier_id=NULL,wallet_amount_used=0,hp_amount_paid=0,discount_amount=0,price_naira=card_amount_used WHERE id=t.id;
  END IF;
  result:=hg_mark_event_ticket_paid(t.id,p_provider,p_provider_reference,p_amount,p_metadata);
  IF NOT EXISTS(SELECT 1 FROM event_checkins WHERE ticket_id=t.id) THEN
   refund_result:=hg_request_event_ticket_refund(actor,e.id,t.id,md5('event-cancel-refund:'||e.id||':'||t.id)::uuid,e.metadata->>'change_reason');
  END IF;
  IF expired THEN UPDATE event_tickets SET tier_id=t.tier_id,wallet_amount_used=t.wallet_amount_used,hp_amount_paid=t.hp_amount_paid,discount_amount=t.discount_amount,price_naira=t.price_naira WHERE id=t.id;END IF;
  RETURN result;
 END IF;
 result:=hg_mark_event_ticket_paid(p_ticket_id,p_provider,p_provider_reference,p_amount,p_metadata);
 IF t.payment_status<>'paid' THEN PERFORM hg_queue_event_ticket_email(p_ticket_id);END IF;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.hg_pay_event_with_delivery(uuid,text,text,numeric,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_pay_event_with_delivery(uuid,text,text,numeric,jsonb) TO service_role;

-- Protect the legacy editor and direct row updates from silently moving sold
-- tickets. The checked operation above temporarily authorizes its own event.
CREATE OR REPLACE FUNCTION hg_internal.guard_booked_event_schedule()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF current_setting('hg.event_operation',true) IS DISTINCT FROM OLD.id::text AND (
 NEW.metadata->'lifecycle_status' IS DISTINCT FROM OLD.metadata->'lifecycle_status' OR NEW.metadata->'latest_change_id' IS DISTINCT FROM OLD.metadata->'latest_change_id' OR NEW.metadata->'change_reason' IS DISTINCT FROM OLD.metadata->'change_reason' OR NEW.metadata->'changed_at' IS DISTINCT FROM OLD.metadata->'changed_at'
 OR ((NEW.starts_at IS DISTINCT FROM OLD.starts_at OR NEW.ends_at IS DISTINCT FROM OLD.ends_at OR NEW.location IS DISTINCT FROM OLD.location) AND EXISTS(SELECT 1 FROM event_tickets WHERE event_id=OLD.id))) THEN
  RAISE EXCEPTION 'HG_EVENT_CHANGE_USE_WORKSPACE' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.guard_booked_event_schedule() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_booked_event_schedule() TO service_role;
CREATE TRIGGER guard_booked_event_schedule BEFORE UPDATE ON events FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_booked_event_schedule();
