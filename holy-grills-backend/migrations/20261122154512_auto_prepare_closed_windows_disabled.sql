-- Separate release control: pickup never changes delivery preparation timing.
-- Uses the existing service-role worker and order state machine; no new RPC/table.
INSERT INTO public.feature_flags(feature_name,is_active,description,campus_id)
 SELECT 'auto_prepare_closed_windows',false,
   'Move paid orders due today to preparing after their own ordering cutoff. Staff still mark ready. Requires worker and beat; checks once per minute by default.',NULL
 WHERE NOT EXISTS(SELECT 1 FROM public.feature_flags WHERE feature_name='auto_prepare_closed_windows' AND campus_id IS NULL)
 ON CONFLICT DO NOTHING;
