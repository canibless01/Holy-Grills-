-- Step 2: derived bookkeeping only. Never update orders, prices or wallets.
CREATE TABLE hg_internal.delivery_subsidy_ledger (
 order_id uuid PRIMARY KEY REFERENCES public.orders(id),
 campus_id uuid NOT NULL REFERENCES public.campuses(id),
 gate_id uuid REFERENCES public.gates(id),
 delivery_date date NOT NULL,
 cushion_original numeric(14,2) NOT NULL DEFAULT 0,
 delivery_fee_original numeric(14,2) NOT NULL DEFAULT 0,
 paid_total_original numeric(14,2) NOT NULL DEFAULT 0,
 cushion_total numeric(14,2) NOT NULL DEFAULT 0,
 delivery_fee_collected numeric(14,2) NOT NULL DEFAULT 0,
 rider_cost numeric(14,2) CHECK(rider_cost>=0 AND rider_cost::text NOT IN ('NaN','Infinity','-Infinity')),
 rider_cost_date date,
 status text NOT NULL,
 payment_status text NOT NULL,
 net_effect numeric(14,2) GENERATED ALWAYS AS
  (CASE WHEN status='excluded' THEN 0 WHEN rider_cost IS NOT NULL THEN cushion_total+delivery_fee_collected-rider_cost ELSE NULL END) STORED,
 entered_by uuid REFERENCES public.profiles(id),
 entered_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX delivery_subsidy_campus_date ON hg_internal.delivery_subsidy_ledger(campus_id,delivery_date,order_id);
CREATE INDEX delivery_subsidy_gate ON hg_internal.delivery_subsidy_ledger(gate_id);
CREATE INDEX delivery_subsidy_actor ON hg_internal.delivery_subsidy_ledger(entered_by);
ALTER TABLE hg_internal.delivery_subsidy_ledger ENABLE ROW LEVEL SECURITY;
CREATE POLICY delivery_subsidy_service ON hg_internal.delivery_subsidy_ledger FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.delivery_subsidy_ledger FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.delivery_subsidy_ledger TO service_role;

CREATE TABLE hg_internal.delivery_subsidy_movements (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 order_id uuid NOT NULL REFERENCES public.orders(id),
 campus_id uuid NOT NULL REFERENCES public.campuses(id),
 gate_id uuid REFERENCES public.gates(id),
 delta numeric(14,2) NOT NULL,
 before_values jsonb,
 after_values jsonb NOT NULL,
 actor_id uuid REFERENCES public.profiles(id),
 occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX delivery_subsidy_movement_order ON hg_internal.delivery_subsidy_movements(order_id,id);
CREATE INDEX delivery_subsidy_movement_campus ON hg_internal.delivery_subsidy_movements(campus_id,occurred_at,id);
CREATE INDEX delivery_subsidy_movement_gate ON hg_internal.delivery_subsidy_movements(gate_id);
CREATE INDEX delivery_subsidy_movement_actor ON hg_internal.delivery_subsidy_movements(actor_id);
ALTER TABLE hg_internal.delivery_subsidy_movements ENABLE ROW LEVEL SECURITY;
CREATE POLICY delivery_subsidy_movements_service ON hg_internal.delivery_subsidy_movements FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.delivery_subsidy_movements FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON hg_internal.delivery_subsidy_movements TO service_role;
GRANT USAGE,SELECT ON SEQUENCE hg_internal.delivery_subsidy_movements_id_seq TO service_role;

CREATE FUNCTION hg_internal.log_delivery_subsidy_movement() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE previous jsonb;current_values jsonb;old_net numeric:=0;actor uuid;
BEGIN
 IF TG_OP='UPDATE' THEN
  previous:=jsonb_build_object('cushion_total',OLD.cushion_total,'delivery_fee_collected',OLD.delivery_fee_collected,'rider_cost',OLD.rider_cost,'net_effect',OLD.net_effect,'status',OLD.status,'gate_id',OLD.gate_id);
  old_net:=coalesce(OLD.net_effect,0);
  IF (OLD.cushion_total,OLD.delivery_fee_collected,OLD.rider_cost,OLD.gate_id,OLD.net_effect) IS NOT DISTINCT FROM
     (NEW.cushion_total,NEW.delivery_fee_collected,NEW.rider_cost,NEW.gate_id,NEW.net_effect) THEN RETURN NULL;END IF;
  IF OLD.rider_cost IS DISTINCT FROM NEW.rider_cost THEN actor:=NEW.entered_by;END IF;
 END IF;
 current_values:=jsonb_build_object('cushion_total',NEW.cushion_total,'delivery_fee_collected',NEW.delivery_fee_collected,'rider_cost',NEW.rider_cost,'net_effect',NEW.net_effect,'status',NEW.status,'gate_id',NEW.gate_id);
 INSERT INTO hg_internal.delivery_subsidy_movements(order_id,campus_id,gate_id,delta,before_values,after_values,actor_id)
 VALUES(NEW.order_id,NEW.campus_id,NEW.gate_id,coalesce(NEW.net_effect,0)-old_net,previous,current_values,actor);
 RETURN NULL;
END $$;
CREATE TRIGGER delivery_subsidy_movement AFTER INSERT OR UPDATE ON hg_internal.delivery_subsidy_ledger
 FOR EACH ROW EXECUTE FUNCTION hg_internal.log_delivery_subsidy_movement();

CREATE FUNCTION hg_internal.refresh_delivery_subsidy(p_order uuid) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE o public.orders%rowtype;l hg_internal.delivery_subsidy_ledger%rowtype;
 gate uuid;day date;gross numeric;raw_cushion numeric;food numeric;ratio numeric;eligible boolean;
BEGIN
 SELECT * INTO o FROM public.orders WHERE id=p_order FOR UPDATE;
 IF NOT FOUND OR o.campus_id IS NULL THEN RETURN;END IF;
 SELECT * INTO l FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o.id FOR UPDATE;
 IF NOT FOUND THEN
  IF o.is_test OR o.payment_status::text NOT IN ('paid','partially_refunded','refunded') THEN RETURN;END IF;
  SELECT coalesce(sum(i.line_total),0),coalesce(sum(i.cushion_snapshot*i.quantity),0) INTO gross,raw_cushion FROM public.order_items i WHERE i.order_id=o.id;
  raw_cushion:=raw_cushion+coalesce((SELECT sum(a.cushion_snapshot*a.quantity*i.quantity) FROM public.order_addon_selections a JOIN public.order_items i ON i.id=a.order_item_id WHERE i.order_id=o.id),0);
  food:=greatest(0,coalesce(o.total_amount,0)-coalesce(o.delivery_fee,0));
  raw_cushion:=CASE WHEN gross>0 THEN round(least(greatest(0,raw_cushion),gross)*least(1,food/gross),2) ELSE 0 END;
  INSERT INTO hg_internal.delivery_subsidy_ledger(order_id,campus_id,delivery_date,cushion_original,delivery_fee_original,paid_total_original,status,payment_status)
   VALUES(o.id,o.campus_id,(coalesce(o.scheduled_for,o.created_at) AT TIME ZONE 'Africa/Lagos')::date,raw_cushion,greatest(0,coalesce(o.delivery_fee,0)),greatest(0,coalesce(o.total_amount,0)),o.status::text,o.payment_status::text)
   ON CONFLICT(order_id) DO NOTHING;
  SELECT * INTO l FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o.id FOR UPDATE;
 END IF;
 SELECT coalesce(
  (SELECT b.gate_id FROM public.delivery_batches b WHERE b.id=o.batch_id AND b.campus_id=o.campus_id),
  (SELECT g.id FROM public.gates g WHERE g.id=o.delivery_location_id AND (g.campus_id IS NULL OR g.campus_id=o.campus_id)),
  (SELECT h.gate_id FROM public.hostels h WHERE h.id=o.delivery_location_id AND (h.campus_id IS NULL OR h.campus_id=o.campus_id))) INTO gate;
 IF l.status IN ('delivered','cancelled','refunded','excluded') AND l.gate_id IS NOT NULL THEN gate:=l.gate_id;END IF;
 day:=(coalesce(o.delivered_at,o.delivery_attempted_at,o.unclaimed_at,o.scheduled_for,o.created_at) AT TIME ZONE 'Africa/Lagos')::date;
 eligible:=NOT o.is_test AND o.status::text='delivered' AND o.payment_status::text IN ('paid','partially_refunded');
 ratio:=CASE WHEN l.paid_total_original>0 THEN greatest(0,least(1,(l.paid_total_original-coalesce(o.wallet_refund_total,0)-coalesce(o.card_refund_total,0))/l.paid_total_original)) ELSE 0 END;
 UPDATE hg_internal.delivery_subsidy_ledger SET gate_id=coalesce(gate,l.gate_id),delivery_date=day,
  cushion_total=CASE WHEN eligible THEN round(l.cushion_original*ratio,2) ELSE 0 END,
  delivery_fee_collected=CASE WHEN eligible THEN round(l.delivery_fee_original*ratio,2) ELSE 0 END,
  status=CASE WHEN o.is_test THEN 'excluded' ELSE o.status::text END,payment_status=o.payment_status::text,updated_at=now()
 WHERE order_id=o.id;
END $$;

-- Private trigger-only definer is required: kitchen/rider JWTs may transition
-- authorized orders but must never read/write the private accounting tables.
CREATE FUNCTION hg_internal.sync_delivery_subsidy() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'orders' THEN RAISE EXCEPTION 'Invalid accounting trigger';END IF;
 IF TG_OP='UPDATE' AND (NEW.status,NEW.payment_status,NEW.wallet_refund_total,NEW.card_refund_total,NEW.batch_id,NEW.delivered_at,NEW.delivery_attempted_at,NEW.unclaimed_at,NEW.is_test,NEW.delivery_location_id,NEW.scheduled_for)
  IS NOT DISTINCT FROM (OLD.status,OLD.payment_status,OLD.wallet_refund_total,OLD.card_refund_total,OLD.batch_id,OLD.delivered_at,OLD.delivery_attempted_at,OLD.unclaimed_at,OLD.is_test,OLD.delivery_location_id,OLD.scheduled_for) THEN RETURN NULL;END IF;
 PERFORM hg_internal.refresh_delivery_subsidy(NEW.id);
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER sync_delivery_subsidy AFTER INSERT OR UPDATE ON public.orders
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION hg_internal.sync_delivery_subsidy();
REVOKE ALL ON FUNCTION hg_internal.refresh_delivery_subsidy(uuid),hg_internal.sync_delivery_subsidy(),hg_internal.log_delivery_subsidy_movement() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.refresh_delivery_subsidy(uuid),hg_internal.sync_delivery_subsidy(),hg_internal.log_delivery_subsidy_movement() TO service_role;

-- Initialize derived ledger rows for real paid history so the first daily cost
-- screen is useful. Old snapshots stay zero; no historical cushion is inferred
-- from today's catalogue. Rider costs remain unknown until an admin records them.
DO $$DECLARE existing record;BEGIN
 FOR existing IN SELECT id FROM public.orders WHERE NOT is_test AND campus_id IS NOT NULL AND payment_status::text IN ('paid','partially_refunded','refunded') ORDER BY id LOOP
  PERFORM hg_internal.refresh_delivery_subsidy(existing.id);
 END LOOP;
END $$;
