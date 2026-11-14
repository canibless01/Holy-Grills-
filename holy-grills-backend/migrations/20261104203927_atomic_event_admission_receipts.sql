-- Admission, immutable reward receipt, ledger and counters commit together.
ALTER TABLE public.event_checkins ADD COLUMN IF NOT EXISTS reward_receipt jsonb;
-- Receipts are server-owned. All customer/staff admissions use the checked API.
REVOKE INSERT, UPDATE, DELETE ON public.event_checkins FROM PUBLIC, anon, authenticated;

-- Event milestones share the admission transaction; no completion can strand its HP.
CREATE OR REPLACE FUNCTION public.hg_complete_event_milestones(p_user_id uuid, p_multiplier numeric)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE m record; um public.user_milestones%rowtype; h public.hp_transactions%rowtype;
 c uuid; period text; since timestamptz; progress integer; amount integer; txn jsonb;
 receipts jsonb:='[]'; existed boolean;
BEGIN
 SELECT campus_id INTO c FROM public.profiles WHERE id=p_user_id FOR UPDATE;
 FOR m IN SELECT * FROM public.milestones WHERE is_active AND trigger_type IN ('first_event','event_checkins')
  AND (campus_id=c OR campus_id IS NULL) ORDER BY id LOOP
  period:=CASE m.time_window WHEN 'weekly' THEN to_char(now() AT TIME ZONE 'Africa/Lagos','IYYY-"W"IW')
    WHEN 'monthly' THEN to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM') END;
  since:=CASE m.time_window WHEN 'weekly' THEN date_trunc('week',now() AT TIME ZONE 'Africa/Lagos') AT TIME ZONE 'Africa/Lagos'
    WHEN 'monthly' THEN date_trunc('month',now() AT TIME ZONE 'Africa/Lagos') AT TIME ZONE 'Africa/Lagos' END;
  SELECT count(*) INTO progress FROM public.event_checkins ci JOIN public.event_tickets t ON t.id=ci.ticket_id
    WHERE t.user_id=p_user_id AND (since IS NULL OR ci.created_at>=since);
  IF progress<greatest(coalesce(m.trigger_value,1),1) THEN CONTINUE; END IF;
  SELECT * INTO um FROM public.user_milestones WHERE user_id=p_user_id AND milestone_id=m.id AND period_key IS NOT DISTINCT FROM period FOR UPDATE;
  existed:=FOUND;
  IF NOT existed THEN
   amount:=greatest(coalesce(m.hp_awarded,0),0);
   IF p_multiplier>1 THEN amount:=amount*p_multiplier; END IF;
   INSERT INTO public.user_milestones(user_id,milestone_id,hp_awarded,period_key,campus_id)
    VALUES(p_user_id,m.id,amount,period,c) RETURNING * INTO um;
  END IF;
  -- Persisted completion amount wins over subsequent configuration changes.
  SELECT * INTO h FROM public.hp_transactions WHERE user_id=p_user_id AND reference_type='milestone' AND reference_id=um.id;
  IF NOT FOUND AND um.hp_awarded>0 THEN
   txn:=public.record_hp_transaction_atomic(p_user_id,um.hp_awarded,'earn','active','challenge','milestone',um.id,NULL,'Milestone: '||m.title,c);
   IF txn ? 'error' THEN RAISE EXCEPTION 'Milestone ledger failed'; END IF;
   IF NOT coalesce((txn->>'replayed')::boolean,false) THEN
    PERFORM public.increment_monthly_hp_tracker(p_user_id,to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'),um.hp_awarded);
   END IF;
  END IF;
  IF NOT existed THEN receipts:=receipts||jsonb_build_array(jsonb_build_object('milestone_id',m.id,'hp_awarded',um.hp_awarded)); END IF;
 END LOOP;
 PERFORM public.hg_set_profile_tier_from_balance(p_user_id);
 RETURN receipts;
END $$;
REVOKE ALL ON FUNCTION public.hg_complete_event_milestones(uuid,numeric) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_complete_event_milestones(uuid,numeric) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_admit_event_ticket(
 p_event_id uuid, p_ticket_id uuid, p_actor_id uuid, p_door_token text,
 p_campus_id uuid, p_default_hp integer DEFAULT 50
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
 t public.event_tickets%rowtype; e public.events%rowtype; a public.profiles%rowtype;
 ci public.event_checkins%rowtype; h public.hp_transactions%rowtype;
 reward integer; mult numeric:=1; raw text; expires text; enabled boolean;
 receipt jsonb; txn jsonb; milestone_receipts jsonb:='[]'; recovering boolean; is_staff boolean:=false;
BEGIN
 -- Same profile-first order as the financial ledger, then lock the ticket.
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket_id AND event_id=p_event_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Ticket not found'; END IF;
 IF t.user_id IS NOT NULL THEN
  PERFORM 1 FROM public.profiles WHERE id=t.user_id AND is_active FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Attendee unavailable'; END IF;
 END IF;
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket_id AND event_id=p_event_id FOR UPDATE;
 SELECT * INTO e FROM public.events WHERE id=p_event_id FOR SHARE;
 IF NOT FOUND OR NOT e.is_published OR (e.ends_at IS NOT NULL AND e.ends_at<=now()) THEN
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
  is_staff:=a.role::text IN ('admin','super_admin');
  IF is_staff AND a.role::text<>'super_admin' AND (e.campus_id IS NULL OR a.campus_id IS DISTINCT FROM e.campus_id) THEN
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
 END IF;
 receipt:=jsonb_build_object('checkin_id',ci.id,'ticket_id',t.id,'hp_transaction_id',h.id,
  'hp_added_to_active',reward,'hp_added_to_pending',0,'is_guest',t.user_id IS NULL,
  'completed',true,'replayed',false,'recovered',recovering,'milestone_receipts',milestone_receipts);
 UPDATE public.event_checkins SET hp_transaction_id=h.id,reward_receipt=receipt WHERE id=ci.id;
 RETURN receipt;
END $$;
REVOKE ALL ON FUNCTION public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer) TO service_role;
