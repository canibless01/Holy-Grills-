SET LOCAL request.jwt.claims='{"role":"service_role"}';
INSERT INTO public.system_settings(key,value,description,is_public,campus_id)
 SELECT 'campus_operations_email','{"recipients":["grillthevibe@gmail.com"],"paid_order_alerts":true,"abandoned_cart_alerts":true,"daily_report":true,"weekly_report":true,"abandoned_minutes":10}'::jsonb,
 'Private operational email recipients and alert/report switches. WAT daily and weekly summaries.',false,id FROM public.campuses WHERE slug='futa-main' AND is_active
 AND NOT EXISTS(SELECT 1 FROM public.system_settings WHERE key='campus_operations_email' AND campus_id=campuses.id);
