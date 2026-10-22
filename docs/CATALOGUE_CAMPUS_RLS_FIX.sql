-- Campus selection is enforced by the backend for guests. Guest catalogue reads
-- use service credentials only after validating/filtering the selected campus.
-- Direct authenticated REST reads can access global and own-campus catalogue.
DO $scope$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['menu_items','menu_categories','menu_item_variation_groups','menu_item_variation_options','menu_addon_groups','menu_addons','menu_item_availability'] LOOP
    EXECUTE format('CREATE POLICY %I ON public.%I AS RESTRICTIVE FOR SELECT TO anon, authenticated USING (campus_id IS NULL OR campus_id = public.hg_user_campus_id() OR public.hg_is_campus_admin(campus_id))', target || ': enforce catalogue campus reads', target);
  END LOOP;
END
$scope$;

CREATE POLICY "menu_items: category scope on insert" ON public.menu_items AS RESTRICTIVE FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_categories c WHERE c.id = menu_items.category_id AND (c.campus_id IS NULL OR c.campus_id = menu_items.campus_id)));
CREATE POLICY "menu_items: category scope on update" ON public.menu_items AS RESTRICTIVE FOR UPDATE TO authenticated USING (true)
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_categories c WHERE c.id = menu_items.category_id AND (c.campus_id IS NULL OR c.campus_id = menu_items.campus_id)));

CREATE POLICY "variation_groups: parent scope on insert" ON public.menu_item_variation_groups AS RESTRICTIVE FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_items m WHERE m.id = menu_item_variation_groups.menu_item_id AND m.campus_id IS NOT DISTINCT FROM menu_item_variation_groups.campus_id));
CREATE POLICY "variation_groups: parent scope on update" ON public.menu_item_variation_groups AS RESTRICTIVE FOR UPDATE TO authenticated USING (true)
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_items m WHERE m.id = menu_item_variation_groups.menu_item_id AND m.campus_id IS NOT DISTINCT FROM menu_item_variation_groups.campus_id));

CREATE POLICY "variation_options: parent scope on insert" ON public.menu_item_variation_options AS RESTRICTIVE FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_item_variation_groups v WHERE v.id = menu_item_variation_options.variation_group_id AND v.campus_id IS NOT DISTINCT FROM menu_item_variation_options.campus_id));
CREATE POLICY "variation_options: parent scope on update" ON public.menu_item_variation_options AS RESTRICTIVE FOR UPDATE TO authenticated USING (true)
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_item_variation_groups v WHERE v.id = menu_item_variation_options.variation_group_id AND v.campus_id IS NOT DISTINCT FROM menu_item_variation_options.campus_id));

CREATE POLICY "addon_groups: parent scope on insert" ON public.menu_addon_groups AS RESTRICTIVE FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_items m WHERE m.id = menu_addon_groups.menu_item_id AND m.campus_id IS NOT DISTINCT FROM menu_addon_groups.campus_id));
CREATE POLICY "addon_groups: parent scope on update" ON public.menu_addon_groups AS RESTRICTIVE FOR UPDATE TO authenticated USING (true)
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_items m WHERE m.id = menu_addon_groups.menu_item_id AND m.campus_id IS NOT DISTINCT FROM menu_addon_groups.campus_id));

CREATE POLICY "addons: parent scope on insert" ON public.menu_addons AS RESTRICTIVE FOR INSERT TO authenticated
WITH CHECK (group_id IS NULL OR EXISTS (SELECT 1 FROM public.menu_addon_groups a WHERE a.id = menu_addons.group_id AND a.campus_id IS NOT DISTINCT FROM menu_addons.campus_id));
CREATE POLICY "addons: parent scope on update" ON public.menu_addons AS RESTRICTIVE FOR UPDATE TO authenticated USING (true)
WITH CHECK (group_id IS NULL OR EXISTS (SELECT 1 FROM public.menu_addon_groups a WHERE a.id = menu_addons.group_id AND a.campus_id IS NOT DISTINCT FROM menu_addons.campus_id));

CREATE POLICY "availability: parent scope on insert" ON public.menu_item_availability AS RESTRICTIVE FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_items m WHERE m.id = menu_item_availability.menu_item_id AND (m.campus_id IS NULL OR m.campus_id = menu_item_availability.campus_id)));
CREATE POLICY "availability: parent scope on update" ON public.menu_item_availability AS RESTRICTIVE FOR UPDATE TO authenticated USING (true)
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_items m WHERE m.id = menu_item_availability.menu_item_id AND (m.campus_id IS NULL OR m.campus_id = menu_item_availability.campus_id)));

CREATE POLICY "cart_items: own campus menu on insert" ON public.cart_items AS RESTRICTIVE FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_items m WHERE m.id = cart_items.menu_item_id AND (m.campus_id IS NULL OR m.campus_id = public.hg_user_campus_id())));
CREATE POLICY "cart_items: own campus menu on update" ON public.cart_items AS RESTRICTIVE FOR UPDATE TO authenticated USING (true)
WITH CHECK (EXISTS (SELECT 1 FROM public.menu_items m WHERE m.id = cart_items.menu_item_id AND (m.campus_id IS NULL OR m.campus_id = public.hg_user_campus_id())));
