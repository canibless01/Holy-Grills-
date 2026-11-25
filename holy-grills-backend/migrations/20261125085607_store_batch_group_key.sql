-- Disjoint uniqueness rules preserve legacy NULL-store groups and allow one
-- open group per actual store for the same shared campus/window/gate/date.
DROP INDEX public.delivery_batches_open_window_gate_uidx;
CREATE UNIQUE INDEX delivery_batches_open_window_gate_uidx ON public.delivery_batches(campus_id,delivery_window_id,gate_id,delivery_date)
 WHERE status='open' AND store_id IS NULL;
CREATE UNIQUE INDEX delivery_batches_open_store_window_gate_uidx ON public.delivery_batches(campus_id,store_id,delivery_window_id,gate_id,delivery_date)
 WHERE status='open' AND store_id IS NOT NULL;
