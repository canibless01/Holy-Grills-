DO $$ BEGIN IF md5(pg_get_functiondef('public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer)'::regprocedure))<>'45ff3082cc821ecd5382e62e92728be4' THEN RAISE EXCEPTION 'Admission source changed';END IF;END $$;
CREATE OR REPLACE FUNCTION public.hg_admit_event_ticket(p_event_id uuid, p_ticket_id uuid, p_actor_id uuid, p_door_token text, p_campus_id uuid, p_default_hp integer DEFAULT 50)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE
 t public.event_tickets%rowtype; e public.events%rowtype; a public.profiles%rowtype;
 ci public.event_checkins%rowtype; h public.hp_transactions%rowtype;
 reward integer; mult numeric:=1; raw text; expires text; enabled boolean;
 receipt jsonb; txn jsonb; milestone_receipts jsonb:='[]'; recovering boolean; guest_reward integer; is_staff boolean:=false;
BEGIN
 PERFORM 1 FROM public.events WHERE id=p_event_id FOR UPDATE;
 -- Same profile-first order as the financial ledger, then lock the ticket.
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket_id AND event_id=p_event_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Ticket not found'; END IF;
 IF t.user_id IS NOT NULL THEN
  PERFORM 1 FROM public.profiles WHERE id=t.user_id AND is_active FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Attendee unavailable'; END IF;
 END IF;
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket_id AND event_id=p_event_id FOR UPDATE;
 SELECT * INTO e FROM public.events WHERE id=p_event_id FOR SHARE;
 IF NOT FOUND OR e.metadata->>'lifecycle_status'='cancelled' OR NOT e.is_published OR (e.ends_at IS NOT NULL AND e.ends_at<=now()) THEN
  RAISE EXCEPTION 'Event not available';
 END IF;
 IF p_campus_id IS NOT NULL AND e.campus_id IS DISTINCT FROM p_campus_id AND NOT coalesce(e.is_global,false) AND e.campus_id IS NOT NULL THEN
  RAISE EXCEPTION 'Event campus mismatch';
 END IF;
 SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='events'
 AND (campus_id=e.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
 IF NOT coalesce(enabled,false) THEN RAISE EXCEPTION 'Events disabled'; END IF;
 IF p_actor_id IS NOT NULL THEN
  SELECT * INTO a FROM public.profiles WHERE id=p_actor_id AND is_active;
  IF NOT FOUND THEN RAISE EXCEPTION 'Actor unavailable'; END IF;
  is_staff:=a.role::text IN ('admin','super_admin') OR (a.role::text='event_organizer' AND e.organizer_id=a.id);
  IF is_staff AND a.role::text='admin' AND (e.campus_id IS NULL OR a.campus_id IS DISTINCT FROM e.campus_id) THEN
   RAISE EXCEPTION 'Staff campus mismatch';
  END IF;
  IF NOT is_staff AND t.user_id IS DISTINCT FROM p_actor_id THEN RAISE EXCEPTION 'Ticket owner mismatch'; END IF;
 END IF;
 IF NOT is_staff AND NOT EXISTS(SELECT 1 FROM public.event_door_tokens WHERE event_id=e.id AND qr_token=p_door_token AND qr_token<>'') THEN
  RAISE EXCEPTION 'Invalid door proof';
 END IF;
 IF t.status<>'confirmed' OR t.payment_status NOT IN ('paid','not_required') OR
 (t.qr_expires_at IS NOT NULL AND t.qr_expires_at<=now()) THEN RAISE EXCEPTION 'Ticket not admissible'; END IF;
 SELECT * INTO ci FROM public.event_checkins WHERE ticket_id=t.id FOR UPDATE;
 recovering:=FOUND;
 IF ci.reward_receipt IS NOT NULL THEN RETURN ci.reward_receipt || jsonb_build_object('replayed',true,'recovered',true); END IF;
 IF NOT recovering THEN
  INSERT INTO public.event_checkins(ticket_id,checked_in_by,qr_code,campus_id)
  VALUES(t.id,p_actor_id,coalesce(p_door_token,t.id::text),e.campus_id) RETURNING * INTO ci;
 END IF;
 reward:=0;
 IF t.user_id IS NOT NULL THEN
  -- Historical awards are authoritative even if the configured amount changed.
  SELECT * INTO h FROM public.hp_transactions WHERE user_id=t.user_id AND reference_type='event' AND reference_id=e.id;
  IF FOUND THEN
   IF h.type<>'earn' OR h.status<>'active' THEN RAISE EXCEPTION 'Unexpected historical event ledger'; END IF;
   reward:=h.amount;
   -- The old separate tracker may already have run. Do not add it again.
  ELSE
   SELECT value #>> '{}' INTO raw FROM public.system_settings WHERE key='event_checkin_hp'
    AND (campus_id=e.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
   reward:=coalesce(e.hp_per_attendee,e.hp_reward,CASE WHEN raw ~ '^\d+$' THEN least(raw::integer,10000) END,p_default_hp);
   IF reward<0 OR reward>10000 THEN RAISE EXCEPTION 'Invalid event reward configuration'; END IF;
   SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='hp_multiplier'
    AND (campus_id=e.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
   IF coalesce(enabled,false) THEN
    SELECT value #>> '{}',campus_id INTO raw,p_campus_id FROM public.system_settings WHERE key='hp_multiplier'
     AND (campus_id=e.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
    IF raw IN ('0.5','1','1.0','2','2.0') THEN mult:=raw::numeric; END IF;
    SELECT value #>> '{}' INTO expires FROM public.system_settings WHERE key='multiplier_expires_at' AND campus_id IS NOT DISTINCT FROM p_campus_id;
    IF nullif(expires,'') IS NOT NULL AND expires::timestamptz<=now() THEN mult:=1; END IF;
   END IF;
   -- Preserve prior event semantics: only boosts, with Python-compatible half-even rounding.
   IF mult>1 THEN reward:=reward*mult; END IF;
   IF reward>0 THEN
    txn:=public.record_hp_transaction_atomic(t.user_id,reward,'earn','active','event','event',e.id,NULL,'Event check-in HP: '||e.title,e.campus_id);
    IF txn ? 'error' THEN RAISE EXCEPTION 'Event reward ledger failed: %',txn->>'error'; END IF;
    SELECT * INTO h FROM public.hp_transactions WHERE id=(txn->>'transaction_id')::uuid;
    IF NOT coalesce((txn->>'replayed')::boolean,false) THEN
     PERFORM public.increment_monthly_hp_tracker(t.user_id,to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'),reward);
    END IF;
   END IF;
  END IF;
  milestone_receipts:=public.hg_complete_event_milestones(t.user_id,mult);
 ELSE
   SELECT value #>> '{}' INTO raw FROM public.system_settings WHERE key='event_checkin_hp'
    AND (campus_id=e.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
   reward:=coalesce(e.hp_per_attendee,e.hp_reward,CASE WHEN raw ~ '^\d+$' THEN least(raw::integer,10000) END,p_default_hp);
   IF reward<0 OR reward>10000 THEN RAISE EXCEPTION 'Invalid event reward configuration'; END IF;
   SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='hp_multiplier'
    AND (campus_id=e.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
   IF coalesce(enabled,false) THEN
    SELECT value #>> '{}',campus_id INTO raw,p_campus_id FROM public.system_settings WHERE key='hp_multiplier'
     AND (campus_id=e.campus_id OR campus_id IS NULL) ORDER BY campus_id NULLS LAST LIMIT 1;
    IF raw IN ('0.5','1','1.0','2','2.0') THEN mult:=raw::numeric; END IF;
    SELECT value #>> '{}' INTO expires FROM public.system_settings WHERE key='multiplier_expires_at' AND campus_id IS NOT DISTINCT FROM p_campus_id;
    IF nullif(expires,'') IS NOT NULL AND expires::timestamptz<=now() THEN mult:=1; END IF;
   END IF;
   -- Preserve prior event semantics: only boosts, with Python-compatible half-even rounding.
   IF mult>1 THEN reward:=reward*mult; END IF;
  guest_reward:=reward;reward:=0;
 END IF;
 receipt:=jsonb_build_object('checkin_id',ci.id,'ticket_id',t.id,'hp_transaction_id',h.id,
  'hp_added_to_active',reward,'hp_added_to_pending',0,'is_guest',t.user_id IS NULL,
  'claimable_hp',guest_reward,'claimable_multiplier',mult,'completed',true,'replayed',false,'recovered',recovering,'milestone_receipts',milestone_receipts);
 UPDATE public.event_checkins SET hp_transaction_id=h.id,reward_receipt=receipt WHERE id=ci.id;
 RETURN receipt;
END $function$;


CREATE OR REPLACE FUNCTION hg_internal.finish_guest_event_hp(p_ticket uuid,p_user uuid,p_amount integer,p_mult numeric,p_admin uuid DEFAULT NULL,p_reason text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE t public.event_tickets%rowtype;e public.events%rowtype;ci public.event_checkins%rowtype;h public.hp_transactions%rowtype;txn jsonb;receipt jsonb;milestones jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket FOR UPDATE;
 SELECT * INTO ci FROM public.event_checkins WHERE ticket_id=p_ticket FOR UPDATE;
 IF NOT FOUND OR t.user_id IS DISTINCT FROM p_user OR t.status<>'confirmed' OR t.payment_status NOT IN('paid','not_required') THEN RAISE EXCEPTION 'HG_GUEST_HP_INVALID';END IF;
 IF ci.hp_transaction_id IS NOT NULL OR ci.reward_receipt->>'guest_claim_state'='completed' THEN
  IF p_admin IS NOT NULL AND (ci.reward_receipt->>'hp_added_to_active')::integer IS DISTINCT FROM p_amount THEN RAISE EXCEPTION 'HG_GUEST_HP_CONFLICT';END IF;
  RETURN ci.reward_receipt||'{"replayed":true}';
 END IF;
 IF p_amount IS NULL OR p_amount<0 OR p_amount>20000 OR p_mult IS NULL OR p_mult NOT IN(0.5,1,2) THEN RAISE EXCEPTION 'HG_GUEST_HP_INVALID';END IF;
 SELECT * INTO e FROM public.events WHERE id=t.event_id;
 SELECT * INTO h FROM public.hp_transactions WHERE user_id=p_user AND reference_type='event' AND reference_id=e.id;
 IF FOUND THEN
  IF h.type<>'earn' OR h.status<>'active' THEN RAISE EXCEPTION 'HG_GUEST_HP_CONFLICT';END IF;
  p_amount:=h.amount;
 ELSIF p_amount>0 THEN
  txn:=public.record_hp_transaction_atomic(p_user,p_amount,'earn','active','event','event',e.id,NULL,'Event check-in HP: '||e.title,e.campus_id);
  IF txn ? 'error' THEN RAISE EXCEPTION 'Event reward ledger failed';END IF;
  SELECT * INTO h FROM public.hp_transactions WHERE id=(txn->>'transaction_id')::uuid;
  IF NOT coalesce((txn->>'replayed')::boolean,false) THEN PERFORM public.increment_monthly_hp_tracker(p_user,to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'),p_amount);END IF;
 END IF;
 milestones:=public.hg_complete_event_milestones(p_user,p_mult);
 receipt:=coalesce(ci.reward_receipt,'{}')||jsonb_build_object('checkin_id',ci.id,'ticket_id',t.id,'hp_transaction_id',h.id,'hp_added_to_active',p_amount,'hp_added_to_pending',0,'is_guest',false,'completed',true,'replayed',false,'guest_claim_state','completed','guest_claimed_at',now(),'milestone_receipts',milestones);
 UPDATE public.event_checkins SET hp_transaction_id=h.id,reward_receipt=receipt WHERE id=ci.id;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,after_value)
 VALUES(p_admin,CASE WHEN p_admin IS NULL THEN 'system' ELSE (SELECT role::text FROM public.profiles WHERE id=p_admin) END,'event_checkin',ci.id::text,'guest_attendance_hp_claimed',jsonb_build_object('ticket_id',t.id,'user_id',p_user,'amount',p_amount,'reason',p_reason));
 RETURN receipt;
END $$;
REVOKE ALL ON FUNCTION hg_internal.finish_guest_event_hp(uuid,uuid,integer,numeric,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.finish_guest_event_hp(uuid,uuid,integer,numeric,uuid,text) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_claim_guest_attendance_hp(p_actor uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE verified_email text;ids uuid[];candidate uuid;t public.event_tickets%rowtype;ci public.event_checkins%rowtype;amount integer;mult numeric;done integer:=0;reviewed integer:=0;receipt jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT hg_internal.verified_event_ticket_email(p_actor) INTO verified_email FROM public.profiles WHERE id=p_actor AND is_active;
 IF verified_email IS NULL THEN RETURN jsonb_build_object('claimed',0,'review',0);END IF;
 SELECT array_agg(id) INTO ids FROM (
  SELECT et.id FROM public.event_tickets et JOIN public.event_checkins c ON c.ticket_id=et.id
  WHERE (et.user_id IS NULL OR et.user_id=p_actor) AND lower(btrim(et.guest_email::text))=verified_email
   AND et.status='confirmed' AND et.payment_status IN('paid','not_required') AND c.hp_transaction_id IS NULL
   AND coalesce(c.reward_receipt->>'guest_claim_state','') NOT IN('completed','review_required')
   AND (et.is_guest OR c.reward_receipt->>'is_guest'='true') ORDER BY et.event_id,et.id LIMIT 100
 ) eligible;
 IF ids IS NULL THEN RETURN jsonb_build_object('claimed',0,'review',0);END IF;
 PERFORM id FROM public.events WHERE id IN(SELECT event_id FROM public.event_tickets WHERE id=ANY(ids)) ORDER BY id FOR UPDATE;
 PERFORM 1 FROM public.profiles WHERE id=p_actor AND is_active FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('claimed',0,'review',0);END IF;
 FOREACH candidate IN ARRAY ids LOOP
  SELECT * INTO t FROM public.event_tickets WHERE id=candidate FOR UPDATE;
  SELECT * INTO ci FROM public.event_checkins WHERE ticket_id=t.id FOR UPDATE;
  IF ci.hp_transaction_id IS NOT NULL OR ci.reward_receipt->>'guest_claim_state' IN('completed','review_required') OR (t.user_id IS NOT NULL AND t.user_id<>p_actor) OR lower(btrim(t.guest_email::text)) IS DISTINCT FROM verified_email THEN CONTINUE;END IF;
  IF EXISTS(SELECT 1 FROM public.event_tickets WHERE event_id=t.event_id AND user_id=p_actor AND id<>t.id AND status NOT IN('cancelled','canceled','expired')) THEN CONTINUE;END IF;
  UPDATE public.event_tickets SET user_id=p_actor,is_guest=false WHERE id=t.id;
  IF coalesce(jsonb_typeof(ci.reward_receipt->'claimable_hp'),'null')<>'number' OR NOT(ci.reward_receipt ? 'claimable_hp') THEN
   UPDATE public.event_checkins SET reward_receipt=coalesce(reward_receipt,'{}')||'{"guest_claim_state":"review_required","is_guest":false}' WHERE id=ci.id;
   reviewed:=reviewed+1;CONTINUE;
  END IF;
  amount:=(ci.reward_receipt->>'claimable_hp')::integer;mult:=coalesce((ci.reward_receipt->>'claimable_multiplier')::numeric,1);
  receipt:=hg_internal.finish_guest_event_hp(t.id,p_actor,amount,mult);done:=done+1;
 END LOOP;
 RETURN jsonb_build_object('claimed',done,'review',reviewed);
END $$;
REVOKE ALL ON FUNCTION public.hg_claim_guest_attendance_hp(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_claim_guest_attendance_hp(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_review_guest_attendance_hp(p_actor uuid,p_event uuid,p_ticket uuid,p_amount integer,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;t public.event_tickets%rowtype;ci public.event_checkins%rowtype;recipient text;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 PERFORM 1 FROM public.events WHERE id=p_event AND (a.role::text='super_admin' OR campus_id=a.campus_id) FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket AND event_id=p_event;
 IF NOT FOUND OR t.user_id IS NULL THEN RAISE EXCEPTION 'HG_GUEST_HP_INVALID';END IF;
 PERFORM 1 FROM public.profiles WHERE id=t.user_id AND is_active FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_GUEST_HP_INVALID';END IF;
 SELECT hg_internal.verified_event_ticket_email(t.user_id) INTO recipient;
 IF recipient IS NULL OR recipient IS DISTINCT FROM lower(btrim(t.guest_email::text)) OR length(btrim(coalesce(p_reason,''))) NOT BETWEEN 10 AND 500 THEN RAISE EXCEPTION 'HG_GUEST_HP_INVALID';END IF;
 SELECT * INTO ci FROM public.event_checkins WHERE ticket_id=t.id;
 IF NOT FOUND OR coalesce(ci.reward_receipt->>'guest_claim_state','') NOT IN('review_required','completed') THEN RAISE EXCEPTION 'HG_GUEST_HP_INVALID';END IF;
 RETURN hg_internal.finish_guest_event_hp(t.id,t.user_id,p_amount,1,p_actor,p_reason);
END $$;
REVOKE ALL ON FUNCTION public.hg_review_guest_attendance_hp(uuid,uuid,uuid,integer,text),public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_review_guest_attendance_hp(uuid,uuid,uuid,integer,text),public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer) TO service_role;

DO $$ DECLARE definition text;BEGIN
 definition:=pg_get_functiondef('public.hg_organizer_event_attendees(uuid,uuid,text,integer,integer)'::regprocedure);
 IF position('(ci.id IS NOT NULL) AS checked_in' IN definition)=0 THEN RAISE EXCEPTION 'Attendee projection changed';END IF;
 IF position(' AS hp_claim_status' IN definition)=0 THEN definition:=replace(definition,'(ci.id IS NOT NULL) AS checked_in','ci.reward_receipt->>''guest_claim_state'' AS hp_claim_status,(ci.id IS NOT NULL) AS checked_in');END IF;
 EXECUTE definition;
END $$;
