CREATE OR REPLACE FUNCTION public.hg_organizer_event_balance(p_actor uuid,p_event uuid)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE a public.profiles%rowtype;e public.events%rowtype;earned numeric;paid numeric;reserved numeric;requests jsonb;counts jsonb;tiers jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('event_organizer','admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_NOT_FOUND' USING ERRCODE='P0002';END IF;
 IF NOT ((a.role::text='event_organizer' AND e.organizer_id=p_actor) OR a.role::text='super_admin' OR (a.role::text='admin' AND e.campus_id=a.campus_id)) THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT coalesce(sum(organizer_amount_snapshot),0) INTO earned FROM public.event_tickets WHERE event_id=p_event AND organizer_id_snapshot=e.organizer_id AND status='confirmed' AND payment_status IN('paid','not_required');
 SELECT coalesce(sum(amount) FILTER(WHERE state='paid'),0),coalesce(sum(amount) FILTER(WHERE state IN('pending','approved')),0),coalesce(jsonb_agg(to_jsonb(p) ORDER BY created_at DESC),'[]') INTO paid,reserved,requests FROM hg_internal.event_payout_requests p WHERE event_id=p_event AND organizer_id=e.organizer_id;
 SELECT jsonb_build_object(
  'confirmed',count(*) FILTER(WHERE t.status='confirmed' AND t.payment_status IN('paid','not_required')),
  'paid_tickets',count(*) FILTER(WHERE t.status='confirmed' AND t.payment_status='paid'),
  'pending',count(*) FILTER(WHERE t.status NOT IN('cancelled','expired','refunded') AND t.payment_status NOT IN('paid','not_required')),
  'cancelled',count(*) FILTER(WHERE t.status IN('cancelled','expired','refunded')),
  'checked_in',count(*) FILTER(WHERE ci.id IS NOT NULL),
  'confirmed_cash',coalesce(sum(coalesce(t.wallet_amount_used,0)+coalesce(t.card_amount_used,0)) FILTER(WHERE t.status='confirmed' AND t.payment_status='paid'),0)
 ) INTO counts FROM public.event_tickets t LEFT JOIN public.event_checkins ci ON ci.ticket_id=t.id WHERE t.event_id=p_event;
 SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.price_naira,t.id),'[]') INTO tiers FROM public.event_ticket_tiers t WHERE t.event_id=p_event;
 RETURN jsonb_build_object('counts',counts,'tiers',tiers,'event',to_jsonb(e),'earned',earned,'paid',paid,'reserved',reserved,'available',greatest(0,earned-paid-reserved),'overpaid',greatest(0,paid-earned),'requests',requests);
END $$;
