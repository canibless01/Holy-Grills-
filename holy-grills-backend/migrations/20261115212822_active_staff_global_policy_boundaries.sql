-- Inline role predicates must revoke elevated access when the persisted account is deactivated.
ALTER POLICY "academic_calendar: super_admin manages global entries" ON public.academic_calendar USING (campus_id IS NULL AND public.hg_is_campus_admin(NULL::uuid)) WITH CHECK (campus_id IS NULL AND public.hg_is_campus_admin(NULL::uuid));
ALTER POLICY "academic_levels: super_admin manages global" ON public.academic_levels USING (campus_id IS NULL AND public.hg_is_campus_admin(NULL::uuid)) WITH CHECK (campus_id IS NULL AND public.hg_is_campus_admin(NULL::uuid));
ALTER POLICY "departments: super_admin manages global" ON public.departments USING (campus_id IS NULL AND public.hg_is_campus_admin(NULL::uuid)) WITH CHECK (campus_id IS NULL AND public.hg_is_campus_admin(NULL::uuid));
ALTER POLICY "brand_partnership_requests: super_admin manages" ON public.brand_partnership_requests USING (public.hg_is_campus_admin(NULL::uuid)) WITH CHECK (public.hg_is_campus_admin(NULL::uuid));
ALTER POLICY "measurement_units: super_admin manages" ON public.measurement_units USING (public.hg_is_campus_admin(NULL::uuid)) WITH CHECK (public.hg_is_campus_admin(NULL::uuid));
-- Keep the direct kitchen predicate aligned with the same active-account rule.
ALTER POLICY "orders: kitchen campus update" ON public.orders
USING (EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=auth.uid() AND p.role='kitchen'::public.user_role AND p.is_active AND p.campus_id=orders.campus_id));
