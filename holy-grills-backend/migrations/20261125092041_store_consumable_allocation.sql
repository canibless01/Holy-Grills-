-- Ingredients remain central. Opt-in consumables/prepared stock can be allocated
-- to stores using the existing stock ledger, with no duplicate balance table.
ALTER TABLE public.stock_items ADD COLUMN store_distributable boolean NOT NULL DEFAULT false;
ALTER TABLE public.stock_ledger ADD COLUMN store_id uuid;
ALTER TABLE public.stock_ledger ADD COLUMN store_transfer_id uuid;
ALTER TABLE public.stock_ledger ADD COLUMN store_movement jsonb;
ALTER TABLE public.stock_ledger ADD CONSTRAINT stock_ledger_store_campus_fk
 FOREIGN KEY(campus_id,store_id) REFERENCES public.stores(campus_id,id);
CREATE INDEX stock_ledger_store_item ON public.stock_ledger(stock_item_id,store_id,created_at,id);
CREATE INDEX stock_ledger_transfer ON public.stock_ledger(store_transfer_id) WHERE store_transfer_id IS NOT NULL;
CREATE POLICY stock_ledger_store_read ON public.stock_ledger AS RESTRICTIVE FOR SELECT TO authenticated
 USING(store_id IS NULL OR hg_internal.current_user_has_store(store_id));

CREATE FUNCTION public.hg_store_stock(p_actor uuid,p_campus uuid,p_store uuid,p_action text,p_data jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,extensions AS $$
DECLARE actor public.profiles%rowtype;item public.stock_items%rowtype;entry public.stock_ledger%rowtype;
 target public.stores%rowtype;source public.stores%rowtype;rid uuid;other uuid;item_id uuid;
 qty numeric;delta numeric;allocated numeric;balance numeric;result jsonb;fingerprint jsonb;notes text;
BEGIN
 SELECT * INTO actor FROM public.profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=p_campus)
  OR (actor.role::text='super_admin' OR (actor.campus_id=p_campus AND actor.role::text IN ('admin','kitchen'))) IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'store_stock_denied' USING ERRCODE='42501';END IF;
 IF p_store IS NOT NULL THEN
  SELECT * INTO source FROM public.stores WHERE id=p_store AND campus_id=p_campus;
  IF NOT FOUND OR (actor.role::text='kitchen' AND NOT hg_internal.actor_has_store(p_actor,p_store)) THEN
   RAISE EXCEPTION 'store_stock_denied' USING ERRCODE='42501';END IF;
 ELSIF actor.role::text='kitchen' THEN RAISE EXCEPTION 'store_stock_denied' USING ERRCODE='42501';END IF;
 IF p_action='snapshot' THEN
  WITH totals AS(SELECT stock_item_id,sum(quantity_in_usage_units) FILTER(WHERE store_id IS NOT NULL) allocated,
   sum(quantity_in_usage_units) FILTER(WHERE store_id=p_store) selected
   FROM public.stock_ledger WHERE campus_id=p_campus GROUP BY stock_item_id)
  SELECT coalesce(jsonb_agg(to_jsonb(s)||jsonb_build_object('central_balance',s.current_balance-coalesce(t.allocated,0),
   'allocated_balance',coalesce(t.allocated,0),'store_balance',coalesce(t.selected,0),
   'purchase_unit',pu.name,'usage_unit',uu.name) ORDER BY s.name,s.id),'[]'::jsonb)
  INTO result FROM public.stock_items s LEFT JOIN totals t ON t.stock_item_id=s.id
   LEFT JOIN public.measurement_units pu ON pu.id=s.purchase_unit_id LEFT JOIN public.measurement_units uu ON uu.id=s.usage_unit_id
   WHERE s.campus_id=p_campus AND (p_store IS NULL OR s.store_distributable);
  IF actor.role::text='kitchen' THEN
   SELECT coalesce(jsonb_agg(x-'current_balance'-'central_balance'-'allocated_balance'),'[]') INTO result FROM jsonb_array_elements(result)x;
  END IF;
  RETURN jsonb_build_object('items',result,'store_id',p_store,'as_of',now());
 ELSIF p_action='history' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.id),'[]') INTO result
  FROM(SELECT l.*,s.name AS item_name,u.name AS unit_name,st.name AS store_name FROM public.stock_ledger l
   JOIN public.stock_items s ON s.id=l.stock_item_id LEFT JOIN public.measurement_units u ON u.id=l.unit_id
   LEFT JOIN public.stores st ON st.id=l.store_id
   WHERE l.campus_id=p_campus AND (p_store IS NULL OR l.store_id=p_store)
    AND (p_data->>'item_id' IS NULL OR l.stock_item_id=(p_data->>'item_id')::uuid)
   ORDER BY l.created_at DESC,l.id LIMIT 100)x;
  RETURN jsonb_build_object('entries',result,'limit',100);
 END IF;
 IF jsonb_typeof(p_data)<>'object' THEN RAISE EXCEPTION 'store_stock_invalid' USING ERRCODE='23514';END IF;
 item_id:=(p_data->>'item_id')::uuid;
 SELECT * INTO item FROM public.stock_items WHERE id=item_id AND campus_id=p_campus FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'store_stock_not_found' USING ERRCODE='P0002';END IF;
 IF p_action='classify' THEN
  IF actor.role::text NOT IN ('admin','super_admin') OR jsonb_typeof(p_data->'distributable')<>'boolean' THEN
   RAISE EXCEPTION 'store_stock_denied' USING ERRCODE='42501';END IF;
  IF NOT(p_data->>'distributable')::boolean AND EXISTS(SELECT 1 FROM public.stock_ledger WHERE stock_item_id=item.id
    AND store_id IS NOT NULL GROUP BY store_id HAVING sum(quantity_in_usage_units)<>0) THEN
   RAISE EXCEPTION 'store_stock_allocated' USING ERRCODE='55000';END IF;
  UPDATE public.stock_items SET store_distributable=(p_data->>'distributable')::boolean,updated_at=now() WHERE id=item.id;
  RETURN jsonb_build_object('saved',true);
 END IF;
 IF p_action NOT IN ('transfer','usage','waste','correction') OR NOT item.store_distributable THEN
  RAISE EXCEPTION 'store_stock_central_only' USING ERRCODE='23514';END IF;
 IF actor.role::text='kitchen' AND p_action NOT IN ('usage','waste') THEN RAISE EXCEPTION 'store_stock_denied' USING ERRCODE='42501';END IF;
 rid:=(p_data->>'request_id')::uuid;qty:=(p_data->>'quantity')::numeric;notes:=btrim(p_data->>'notes');
 other:=(p_data->>'destination_store_id')::uuid;
 IF rid IS NULL OR qty IS NULL OR qty::text IN ('NaN','Infinity','-Infinity') OR qty=0
  OR (p_action<>'correction' AND qty<0) OR notes IS NULL OR length(notes) NOT BETWEEN 1 AND 1000
  OR (p_action<>'transfer' AND (p_store IS NULL OR other IS NOT NULL)) OR (p_action='transfer' AND other IS NOT DISTINCT FROM p_store)
 THEN RAISE EXCEPTION 'store_stock_invalid' USING ERRCODE='23514';END IF;
 fingerprint:=jsonb_build_object('action',p_action,'store_id',p_store,'destination_store_id',other,'quantity',qty,'notes',notes);
 SELECT * INTO entry FROM public.stock_ledger WHERE id=rid;
 IF FOUND THEN
  IF entry.logged_by IS DISTINCT FROM p_actor OR entry.stock_item_id<>item.id OR entry.store_movement IS DISTINCT FROM fingerprint THEN
   RAISE EXCEPTION 'store_stock_conflict' USING ERRCODE='23505';END IF;
  RETURN jsonb_build_object('saved',true,'replayed',true,'receipt_id',rid);
 END IF;
 IF item.archived_at IS NOT NULL THEN RAISE EXCEPTION 'store_stock_archived' USING ERRCODE='55000';END IF;
 IF other IS NOT NULL THEN
  SELECT * INTO target FROM public.stores WHERE id=other AND campus_id=p_campus AND is_active;
  IF NOT FOUND THEN RAISE EXCEPTION 'store_stock_denied' USING ERRCODE='42501';END IF;
 END IF;
 SELECT coalesce(sum(quantity_in_usage_units),0) INTO allocated FROM public.stock_ledger WHERE stock_item_id=item.id AND store_id IS NOT NULL;
 IF p_store IS NULL THEN balance:=item.current_balance-allocated;
 ELSE SELECT coalesce(sum(quantity_in_usage_units),0) INTO balance FROM public.stock_ledger WHERE stock_item_id=item.id AND store_id=p_store;END IF;
 delta:=CASE WHEN p_action='correction' THEN qty ELSE -qty END;
 IF balance+delta<0 THEN RAISE EXCEPTION 'store_stock_insufficient' USING ERRCODE='23514';END IF;
 INSERT INTO public.stock_ledger(id,stock_item_id,campus_id,type,quantity_entered,unit_id,quantity_in_usage_units,logged_by,notes,store_id,store_transfer_id,store_movement)
 VALUES(rid,item.id,p_campus,CASE WHEN p_action='transfer' THEN 'correction' ELSE p_action END,-delta,item.usage_unit_id,delta,p_actor,notes,p_store,
  CASE WHEN p_action='transfer' THEN rid END,fingerprint);
 IF p_action='transfer' THEN
  INSERT INTO public.stock_ledger(id,stock_item_id,campus_id,type,quantity_entered,unit_id,quantity_in_usage_units,logged_by,notes,store_id,store_transfer_id,store_movement)
  VALUES(md5(rid::text||':store-stock-destination')::uuid,item.id,p_campus,'correction',-qty,item.usage_unit_id,qty,p_actor,notes,other,rid,fingerprint);
 ELSE UPDATE public.stock_items SET current_balance=current_balance+delta,updated_at=now() WHERE id=item.id;END IF;
 RETURN jsonb_build_object('saved',true,'receipt_id',rid,'balance',balance+delta);
END$$;
REVOKE ALL ON FUNCTION public.hg_store_stock(uuid,uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_store_stock(uuid,uuid,uuid,text,jsonb) TO service_role;

-- The central adjustment path may consume only stock not already allocated.
-- Retain the reviewed helper signature, checks, grants and lock order.
DO $patch$
DECLARE body text;needle text:=$old$IF v_balance<0 THEN RAISE EXCEPTION 'Insufficient stock for this adjustment' USING ERRCODE='23514'; END IF;$old$;
BEGIN
 SELECT pg_get_functiondef('public.hg_adjust_stock_balance(uuid,text,numeric,numeric,uuid,numeric,text,uuid,uuid)'::regprocedure) INTO body;
 IF strpos(body,needle)=0 THEN RAISE EXCEPTION 'Stock adjustment source changed';END IF;
 body:=replace(body,needle,needle||$new$
 IF v_balance<(SELECT coalesce(sum(quantity_in_usage_units),0) FROM public.stock_ledger WHERE stock_item_id=p_stock_item_id AND store_id IS NOT NULL) THEN
  RAISE EXCEPTION 'Central adjustment cannot consume allocated store stock' USING ERRCODE='23514';END IF;
 $new$);
 EXECUTE body;
END$patch$;

CREATE FUNCTION hg_internal.guard_store_stock_classification() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NOT NEW.store_distributable AND OLD.store_distributable AND EXISTS(
  SELECT 1 FROM public.stock_ledger WHERE stock_item_id=NEW.id AND store_id IS NOT NULL
   GROUP BY store_id HAVING sum(quantity_in_usage_units)<>0) THEN
  RAISE EXCEPTION 'store_stock_allocated' USING ERRCODE='55000';END IF;
 RETURN NEW;
END$$;
REVOKE ALL ON FUNCTION hg_internal.guard_store_stock_classification() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_store_stock_classification() TO service_role;
CREATE TRIGGER guard_store_stock_classification BEFORE UPDATE OF store_distributable ON public.stock_items
 FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_store_stock_classification();
