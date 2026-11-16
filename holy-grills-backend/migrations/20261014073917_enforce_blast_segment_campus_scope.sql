DROP POLICY IF EXISTS notification_blasts_segment_scope ON public.notification_blasts;
CREATE POLICY notification_blasts_segment_scope ON public.notification_blasts AS RESTRICTIVE
FOR ALL TO authenticated USING (public.hg_is_campus_admin(campus_id))
WITH CHECK (
 public.hg_is_campus_admin(campus_id)
 AND jsonb_typeof(COALESCE(segment,'{}'::jsonb))='object'
 AND (campus_id IS NULL OR (
  (segment->>'campus_id' IS NULL OR segment->>'campus_id'=campus_id::text)
  AND (segment->>'campus' IS NULL OR segment->>'campus'=campus_id::text)
 ))
);
