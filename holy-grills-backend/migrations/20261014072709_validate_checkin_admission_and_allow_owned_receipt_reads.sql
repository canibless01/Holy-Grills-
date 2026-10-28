-- Service-backed check-in remains compatible with the current backend.
DROP POLICY IF EXISTS event_checkins_valid_admission ON public.event_checkins;
CREATE POLICY event_checkins_valid_admission ON public.event_checkins AS RESTRICTIVE
FOR INSERT TO authenticated WITH CHECK (
 checked_in_by=(SELECT auth.uid()) AND EXISTS (
  SELECT 1 FROM public.event_tickets t JOIN public.events e ON e.id=t.event_id
  WHERE t.id=event_checkins.ticket_id AND t.status='confirmed'
   AND t.payment_status IN ('paid','not_required')
   AND (t.qr_expires_at IS NULL OR t.qr_expires_at>now())
   AND e.is_published AND e.ends_at>now()
   AND event_checkins.campus_id IS NOT DISTINCT FROM t.campus_id
 ));
DROP POLICY IF EXISTS event_checkins_owner_read ON public.event_checkins;
CREATE POLICY event_checkins_owner_read ON public.event_checkins
FOR SELECT TO authenticated USING (
 EXISTS (SELECT 1 FROM public.event_tickets t WHERE t.id=event_checkins.ticket_id AND t.user_id=(SELECT auth.uid()))
);
