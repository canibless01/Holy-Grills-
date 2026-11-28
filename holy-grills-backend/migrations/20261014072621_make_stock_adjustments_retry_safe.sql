-- Reuse stock_ledger.id as the receipt business key; no table/column/index added.
-- The old eight-argument entry point has no dependent schema object.
DROP FUNCTION public.hg_adjust_stock_balance(uuid,text,numeric,numeric,uuid,numeric,text,uuid);
CREATE FUNCTION public.hg_adjust_stock_balance(
 p_stock_item_id uuid,p_type text,p_quantity_entered numeric,p_delta_usage_units numeric,
 p_unit_id uuid,p_cost numeric,p_notes text,p_logged_by uuid,p_request_id uuid DEFAULT NULL
) RETURNS TABLE(new_balance numeric,is_low_stock boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE v_item public.stock_items%ROWTYPE;v_receipt public.stock_ledger%ROWTYPE;v_balance numeric;
BEGIN
 SELECT * INTO v_item FROM public.stock_items WHERE id=p_stock_item_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Stock item not found' USING ERRCODE='P0002'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_logged_by AND is_active AND
  (role='super_admin' OR (role='admin' AND campus_id=v_item.campus_id))) THEN
  RAISE EXCEPTION 'Stock campus permission denied' USING ERRCODE='42501';
 END IF;
 IF p_request_id IS NOT NULL THEN
  SELECT * INTO v_receipt FROM public.stock_ledger WHERE id=p_request_id;
  IF FOUND THEN
   IF v_receipt.stock_item_id IS DISTINCT FROM p_stock_item_id OR v_receipt.type IS DISTINCT FROM p_type
    OR v_receipt.quantity_entered IS DISTINCT FROM p_quantity_entered OR v_receipt.quantity_in_usage_units IS DISTINCT FROM p_delta_usage_units
    OR v_receipt.unit_id IS DISTINCT FROM p_unit_id OR v_receipt.cost IS DISTINCT FROM p_cost
    OR v_receipt.notes IS DISTINCT FROM p_notes OR v_receipt.logged_by IS DISTINCT FROM p_logged_by THEN
    RAISE EXCEPTION 'Stock request conflicts with an existing receipt' USING ERRCODE='23505';
   END IF;
   RETURN QUERY SELECT v_item.current_balance,(v_item.current_balance<v_item.low_stock_threshold);RETURN;
  END IF;
 END IF;
 IF p_type NOT IN ('purchase','usage','waste','correction') OR p_quantity_entered IS NULL
  OR p_quantity_entered::text IN ('NaN','Infinity','-Infinity') OR p_delta_usage_units IS NULL
  OR p_delta_usage_units::text IN ('NaN','Infinity','-Infinity') OR
  (p_type<>'correction' AND p_quantity_entered<=0) OR (p_cost IS NOT NULL AND (p_cost<0 OR p_cost::text IN ('NaN','Infinity','-Infinity'))) THEN
  RAISE EXCEPTION 'Invalid stock quantity or cost' USING ERRCODE='23514';
 END IF;
 IF (p_type='purchase' AND (p_delta_usage_units IS DISTINCT FROM p_quantity_entered*v_item.conversion_factor OR p_unit_id IS DISTINCT FROM v_item.purchase_unit_id))
  OR (p_type<>'purchase' AND (p_delta_usage_units IS DISTINCT FROM -p_quantity_entered OR p_unit_id IS DISTINCT FROM v_item.usage_unit_id)) THEN
  RAISE EXCEPTION 'Invalid stock unit conversion' USING ERRCODE='23514';
 END IF;
 v_balance=v_item.current_balance+p_delta_usage_units;
 IF v_balance<0 THEN RAISE EXCEPTION 'Insufficient stock for this adjustment' USING ERRCODE='23514'; END IF;
 UPDATE public.stock_items SET current_balance=v_balance,updated_at=now() WHERE id=p_stock_item_id;
 INSERT INTO public.stock_ledger(id,stock_item_id,campus_id,type,quantity_entered,unit_id,quantity_in_usage_units,cost,logged_by,notes)
 VALUES(COALESCE(p_request_id,gen_random_uuid()),p_stock_item_id,v_item.campus_id,p_type,p_quantity_entered,p_unit_id,p_delta_usage_units,p_cost,p_logged_by,p_notes);
 RETURN QUERY SELECT v_balance,(v_balance<v_item.low_stock_threshold);
END;$$;
REVOKE ALL ON FUNCTION public.hg_adjust_stock_balance(uuid,text,numeric,numeric,uuid,numeric,text,uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_adjust_stock_balance(uuid,text,numeric,numeric,uuid,numeric,text,uuid,uuid) TO service_role;
