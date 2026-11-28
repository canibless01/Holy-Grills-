-- Store ownership is frozen on the order; campus menus/windows/capacity stay shared.
ALTER TABLE public.orders ADD COLUMN store_id uuid,ADD COLUMN fulfilment_store_snapshot jsonb;
ALTER TABLE public.orders ADD CONSTRAINT orders_store_campus_fk FOREIGN KEY(campus_id,store_id) REFERENCES public.stores(campus_id,id);
ALTER TABLE public.delivery_batches ADD COLUMN store_id uuid;
ALTER TABLE public.delivery_batches ADD CONSTRAINT batches_store_campus_fk FOREIGN KEY(campus_id,store_id) REFERENCES public.stores(campus_id,id);
CREATE INDEX orders_store_created ON public.orders(store_id,created_at) WHERE store_id IS NOT NULL;
CREATE INDEX batches_store_open ON public.delivery_batches(store_id,status) WHERE store_id IS NOT NULL;

CREATE FUNCTION public.hg_store_analytics(p_actor uuid,p_campus uuid,p_store uuid,p_start timestamptz,p_end timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles;result jsonb;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN('admin','super_admin') OR (actor.role::text='admin' AND actor.campus_id IS DISTINCT FROM p_campus) THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 IF p_start IS NULL OR p_end IS NULL OR p_start>=p_end OR p_end-p_start>interval '366 days' THEN RAISE EXCEPTION 'HG_STORE_REPORT_RANGE';END IF;
 IF p_store IS NOT NULL AND NOT EXISTS(SELECT 1 FROM stores WHERE id=p_store AND (p_campus IS NULL OR campus_id=p_campus)) THEN RAISE EXCEPTION 'HG_STORE_NOT_FOUND';END IF;
 WITH cohort AS (
  SELECT o.*,o.payment_status::text IN('paid','partially_refunded','refunded') AS settled,
   CASE WHEN o.payment_status::text IN('paid','partially_refunded','refunded') THEN greatest(0,o.total_amount-coalesce(o.card_refund_total,0)-coalesce(o.wallet_refund_total,0)) ELSE 0 END AS retained
  FROM orders o WHERE NOT coalesce(o.is_test,false) AND o.created_at>=p_start AND o.created_at<p_end
   AND (p_campus IS NULL OR o.campus_id=p_campus) AND (p_store IS NULL OR o.store_id=p_store)
 ),money AS (
  SELECT *,CASE WHEN total_amount>0 THEN round(greatest(0,total_amount-delivery_fee)*least(1,retained/total_amount),2) ELSE 0 END AS food_net FROM cohort
 ),by_store AS (
  SELECT campus_id,store_id,count(*) AS orders,count(*) FILTER(WHERE settled) AS paid_orders,
   coalesce(sum(total_amount) FILTER(WHERE settled),0) AS paid_volume,
   coalesce(sum(CASE WHEN settled THEN greatest(0,total_amount)-retained ELSE 0 END),0) AS refunds,
   coalesce(sum(retained),0) AS retained_revenue,coalesce(sum(food_net),0) AS retained_food_revenue,
   coalesce(sum(retained-food_net),0) AS retained_delivery_revenue,
   count(*) FILTER(WHERE status::text='delivered') AS completed_orders,
   count(*) FILTER(WHERE status::text IN('cancelled','refunded')) AS cancelled_orders
  FROM money GROUP BY campus_id,store_id
 )
 SELECT coalesce(jsonb_agg(to_jsonb(r)||jsonb_build_object('store_name',s.name,'campus_name',c.name,'university_id',c.university_id) ORDER BY c.name,s.name NULLS LAST),'[]') INTO result
 FROM by_store r LEFT JOIN stores s ON s.id=r.store_id LEFT JOIN campuses c ON c.id=r.campus_id;
 RETURN jsonb_build_object('start',p_start,'end',p_end,'rows',result,'date_basis','order_created_at','refund_basis','current_completed_refunds');
END $$;
REVOKE ALL ON FUNCTION public.hg_store_analytics(uuid,uuid,uuid,timestamptz,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_store_analytics(uuid,uuid,uuid,timestamptz,timestamptz) TO service_role;

CREATE FUNCTION hg_internal.guard_order_store_attribution() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE s public.stores;plan jsonb;enabled boolean;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF NEW.store_id IS DISTINCT FROM OLD.store_id OR NEW.fulfilment_store_snapshot IS DISTINCT FROM OLD.fulfilment_store_snapshot THEN RAISE EXCEPTION 'HG_STORE_ORDER_IMMUTABLE' USING ERRCODE='23514';END IF;
  IF NEW.store_id IS NOT NULL AND NEW.campus_id IS DISTINCT FROM OLD.campus_id THEN RAISE EXCEPTION 'HG_STORE_ORDER_IMMUTABLE' USING ERRCODE='23514';END IF;
  RETURN NEW;
 END IF;
 SELECT coalesce((SELECT is_active FROM feature_flags WHERE feature_name='multi_store_ordering' AND campus_id=NEW.campus_id),
   (SELECT is_active FROM feature_flags WHERE feature_name='multi_store_ordering' AND campus_id IS NULL),false) INTO enabled;
 plan:=NEW.delivery_address_snapshot->'_fulfilment_store';
 IF plan IS NOT NULL THEN NEW.store_id:=(plan->>'id')::uuid;END IF;
 IF NOT enabled THEN
  IF NEW.store_id IS NOT NULL OR plan IS NOT NULL THEN RAISE EXCEPTION 'HG_STORE_ORDERING_DISABLED' USING ERRCODE='23514';END IF;
  RETURN NEW;
 END IF;
 SELECT * INTO s FROM stores WHERE id=NEW.store_id AND campus_id=NEW.campus_id AND is_active FOR SHARE;
 IF NOT FOUND OR (NEW.delivery_type='store_pickup' AND NOT s.pickup_enabled) OR (NEW.delivery_type<>'store_pickup' AND NOT s.delivery_enabled) THEN RAISE EXCEPTION 'HG_STORE_ORDER_UNAVAILABLE' USING ERRCODE='23514';END IF;
 NEW.fulfilment_store_snapshot:=jsonb_build_object('id',s.id,'name',s.name,'address',s.address,'instructions',s.instructions,'lat',s.lat,'lon',s.lon);
 IF plan IS DISTINCT FROM NEW.fulfilment_store_snapshot THEN RAISE EXCEPTION 'HG_STORE_ORDER_CHANGED' USING ERRCODE='23514';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.guard_order_store_attribution() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_order_store_attribution() TO service_role;
CREATE TRIGGER aa_order_store_attribution BEFORE INSERT OR UPDATE ON public.orders FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_order_store_attribution();
NOTIFY pgrst,'reload schema';
