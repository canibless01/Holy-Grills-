-- Saved order choices are immutable through the public Data API. A viewer may
-- read them only when the parent item AND order are visible through their RLS.
DROP POLICY IF EXISTS "order_addon_selections: admins all" ON public.order_addon_selections;
DROP POLICY IF EXISTS "order_addon_selections: visible parent order read" ON public.order_addon_selections;
CREATE POLICY "order_addon_selections: visible parent order read"
 ON public.order_addon_selections FOR SELECT TO authenticated
 USING (EXISTS (
   SELECT 1 FROM public.order_items i JOIN public.orders o ON o.id=i.order_id
   WHERE i.id=order_addon_selections.order_item_id
     AND o.campus_id IS NOT DISTINCT FROM order_addon_selections.campus_id
 ));
REVOKE ALL ON TABLE public.order_addon_selections FROM anon;
REVOKE INSERT,UPDATE,DELETE ON TABLE public.order_addon_selections FROM authenticated;
GRANT SELECT ON TABLE public.order_addon_selections TO authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.order_addon_selections TO service_role;
