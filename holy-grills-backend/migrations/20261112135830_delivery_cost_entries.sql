-- Stage 3: private bookkeeping. No order, retail price or payout changes.
CREATE TABLE hg_internal.delivery_cost_entries (
 id uuid PRIMARY KEY, campus_id uuid NOT NULL REFERENCES public.campuses(id),
 gate_id uuid REFERENCES public.gates(id), cost_date date NOT NULL,
 kind text NOT NULL CHECK(kind IN ('order','trip')),
 total_cost numeric(14,2) NOT NULL CHECK(total_cost>=0 AND total_cost::text NOT IN ('NaN','Infinity','-Infinity')),
 note text NOT NULL DEFAULT '' CHECK(length(note)<=500), version integer NOT NULL DEFAULT 1,
 entered_by uuid NOT NULL REFERENCES public.profiles(id), entered_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX delivery_cost_entry_campus ON hg_internal.delivery_cost_entries(campus_id,cost_date);
CREATE INDEX delivery_cost_entry_gate ON hg_internal.delivery_cost_entries(gate_id);
CREATE INDEX delivery_cost_entry_actor ON hg_internal.delivery_cost_entries(entered_by);
CREATE TABLE hg_internal.delivery_cost_allocations (
 order_id uuid PRIMARY KEY REFERENCES hg_internal.delivery_subsidy_ledger(order_id),
 entry_id uuid NOT NULL REFERENCES hg_internal.delivery_cost_entries(id), amount numeric(14,2) NOT NULL CHECK(amount>=0)
);
CREATE INDEX delivery_cost_allocation_entry ON hg_internal.delivery_cost_allocations(entry_id);
CREATE TABLE hg_internal.delivery_cost_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 entry_id uuid NOT NULL REFERENCES hg_internal.delivery_cost_entries(id),
 actor_id uuid NOT NULL REFERENCES public.profiles(id), occurred_at timestamptz NOT NULL DEFAULT now(),
 before_values jsonb, after_values jsonb NOT NULL
);
CREATE INDEX delivery_cost_audit_entry ON hg_internal.delivery_cost_audit(entry_id,id);
CREATE INDEX delivery_cost_audit_actor ON hg_internal.delivery_cost_audit(actor_id);
CREATE TABLE hg_internal.delivery_cost_receipts (
 request_id uuid PRIMARY KEY, actor_id uuid NOT NULL REFERENCES public.profiles(id),
 campus_id uuid NOT NULL REFERENCES public.campuses(id), payload jsonb NOT NULL, result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX delivery_cost_receipt_actor ON hg_internal.delivery_cost_receipts(actor_id);
CREATE INDEX delivery_cost_receipt_campus ON hg_internal.delivery_cost_receipts(campus_id);
DO $$DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['delivery_cost_entries','delivery_cost_allocations','delivery_cost_audit','delivery_cost_receipts'] LOOP
  EXECUTE format('ALTER TABLE hg_internal.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY service_access ON hg_internal.%I FOR ALL TO service_role USING(true) WITH CHECK(true)',t);
  EXECUTE format('REVOKE ALL ON hg_internal.%I FROM PUBLIC,anon,authenticated',t);
 END LOOP;
END$$;
GRANT SELECT,INSERT,UPDATE ON hg_internal.delivery_cost_entries TO service_role;
GRANT SELECT,INSERT,DELETE ON hg_internal.delivery_cost_allocations TO service_role;
GRANT SELECT,INSERT ON hg_internal.delivery_cost_audit,hg_internal.delivery_cost_receipts TO service_role;
GRANT USAGE,SELECT ON SEQUENCE hg_internal.delivery_cost_audit_id_seq TO service_role;

CREATE FUNCTION hg_internal.delivery_cost_actor(p_actor uuid,p_campus uuid) RETURNS void
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE a public.profiles%rowtype;
BEGIN
 SELECT * INTO a FROM public.profiles WHERE id=p_actor;
 IF NOT FOUND OR NOT a.is_active OR a.role::text NOT IN ('admin','super_admin') OR
  (a.role::text<>'super_admin' AND (p_campus IS NULL OR a.campus_id IS DISTINCT FROM p_campus)) THEN
  RAISE EXCEPTION 'Delivery cost access denied' USING ERRCODE='42501';
 END IF;
END$$;

CREATE FUNCTION public.hg_delivery_costs(p_actor uuid,p_campus uuid,p_action text,p_data jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
#variable_conflict use_variable
DECLARE day date;ids uuid[];old_ids uuid[];all_ids uuid[];rid uuid;entry_id uuid;e hg_internal.delivery_cost_entries%rowtype;
 receipt hg_internal.delivery_cost_receipts%rowtype;before_data jsonb;after_data jsonb;result jsonb;canonical jsonb;
 total numeric;kobo bigint;n integer;gate uuid;item record;expected integer;note text;kind text;cost numeric;
BEGIN
 PERFORM hg_internal.delivery_cost_actor(p_actor,p_campus);
 IF p_action='list' THEN
  day:=(p_data->>'date')::date;
  IF day IS NULL THEN RAISE EXCEPTION 'Choose a date' USING ERRCODE='22023';END IF;
  IF (SELECT count(*) FROM hg_internal.delivery_subsidy_ledger l WHERE (p_campus IS NULL OR l.campus_id=p_campus) AND l.status<>'excluded' AND (l.delivery_date=day OR l.rider_cost_date=day))>2000 THEN
   RAISE EXCEPTION 'Too many orders for one day; choose a campus' USING ERRCODE='22023';END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY q.campus_name,q.gate_name,q.order_id),'[]'::jsonb) INTO result FROM (
   SELECT l.*,c.name campus_name,coalesce(g.name,'Unassigned gate') gate_name,o.total_amount order_total,
    o.delivery_fee customer_delivery_fee,coalesce(o.delivery_address_snapshot->>'line1',o.delivery_address_snapshot->>'location_name','') address,
    a.entry_id,e.version entry_version,e.total_cost entry_total,e.note entry_note,e.kind entry_kind,e.cost_date entry_date,
    coalesce((SELECT jsonb_agg(x.order_id ORDER BY x.order_id) FROM hg_internal.delivery_cost_allocations x WHERE x.entry_id=a.entry_id),'[]'::jsonb) entry_orders,
    (l.status IN ('delivered','delivery_attempted','unclaimed') OR (l.status IN ('cancelled','refunded') AND (o.out_for_delivery_at IS NOT NULL OR o.delivery_attempted_at IS NOT NULL OR o.delivered_at IS NOT NULL))) cost_eligible
   FROM hg_internal.delivery_subsidy_ledger l JOIN public.orders o ON o.id=l.order_id JOIN public.campuses c ON c.id=l.campus_id
   LEFT JOIN public.gates g ON g.id=l.gate_id LEFT JOIN hg_internal.delivery_cost_allocations a ON a.order_id=l.order_id
   LEFT JOIN hg_internal.delivery_cost_entries e ON e.id=a.entry_id
   WHERE (p_campus IS NULL OR l.campus_id=p_campus) AND l.status<>'excluded' AND (l.delivery_date=day OR l.rider_cost_date=day)
  )q;
  RETURN jsonb_build_object('orders',result);
 ELSIF p_action='history' THEN
  entry_id:=(p_data->>'entry_id')::uuid;
  SELECT * INTO e FROM hg_internal.delivery_cost_entries WHERE id=entry_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Cost entry not found' USING ERRCODE='22023';END IF;
  PERFORM hg_internal.delivery_cost_actor(p_actor,e.campus_id);
  IF p_campus IS NOT NULL AND p_campus<>e.campus_id THEN RAISE EXCEPTION 'Delivery cost access denied' USING ERRCODE='42501';END IF;
  RETURN coalesce((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id DESC) FROM hg_internal.delivery_cost_audit a WHERE a.entry_id=entry_id),'[]'::jsonb);
 ELSIF p_action<>'save' THEN RAISE EXCEPTION 'Invalid delivery cost action' USING ERRCODE='22023';END IF;
 IF p_campus IS NULL THEN RAISE EXCEPTION 'Select a campus before recording costs' USING ERRCODE='22023';END IF;
 rid:=(p_data->>'request_id')::uuid;entry_id:=(p_data->>'entry_id')::uuid;expected:=(p_data->>'version')::integer;
 day:=(p_data->>'date')::date;total:=(p_data->>'total_cost')::numeric;note:=coalesce(p_data->>'note','');kind:=p_data->>'kind';
 IF rid IS NULL OR entry_id IS NULL OR expected IS NULL OR expected<0 OR day IS NULL OR day>(now() AT TIME ZONE 'Africa/Lagos')::date OR total IS NULL OR total<0 OR total>999999999999.99 OR total<>round(total,2) OR total::text IN ('NaN','Infinity','-Infinity') OR length(note)>500 OR kind IS NULL OR kind NOT IN ('order','trip') OR jsonb_typeof(p_data->'order_ids') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'Invalid cost details' USING ERRCODE='22023';END IF;
 SELECT array_agg(v::uuid ORDER BY v::uuid) INTO ids FROM jsonb_array_elements_text(p_data->'order_ids') v;
 n:=coalesce(array_length(ids,1),0);
 IF n<1 OR n>200 OR (kind='order' AND n<>1) OR (SELECT count(DISTINCT x) FROM unnest(ids)x)<>n OR array_position(ids,NULL) IS NOT NULL THEN RAISE EXCEPTION 'Select 1 to 200 different orders' USING ERRCODE='22023';END IF;
 canonical:=jsonb_build_object('entry',entry_id,'version',expected,'date',day,'total',total,'kind',kind,'note',note,'orders',to_jsonb(ids));
 PERFORM pg_advisory_xact_lock(hashtextextended('delivery-cost-request:'||rid::text,0));
 SELECT * INTO receipt FROM hg_internal.delivery_cost_receipts WHERE request_id=rid;
 IF FOUND THEN
  IF receipt.actor_id<>p_actor OR receipt.campus_id<>p_campus OR receipt.payload<>canonical THEN RAISE EXCEPTION 'Request already used with different details' USING ERRCODE='40001';END IF;
  RETURN receipt.result;
 END IF;
 -- Serializes edits of an entry even before its first INSERT.
 PERFORM pg_advisory_xact_lock(hashtextextended('delivery-cost-entry:'||entry_id::text,0));
 SELECT * INTO e FROM hg_internal.delivery_cost_entries WHERE id=entry_id FOR UPDATE;
 IF FOUND THEN
  IF e.campus_id<>p_campus THEN RAISE EXCEPTION 'Delivery cost access denied' USING ERRCODE='42501';END IF;
  IF e.version<>expected THEN RAISE EXCEPTION 'Cost changed; reload before editing' USING ERRCODE='40001';END IF;
  SELECT array_agg(order_id ORDER BY order_id) INTO old_ids FROM hg_internal.delivery_cost_allocations WHERE delivery_cost_allocations.entry_id=e.id;
  before_data:=jsonb_build_object('entry',to_jsonb(e),'allocations',(SELECT jsonb_agg(to_jsonb(a) ORDER BY a.order_id) FROM hg_internal.delivery_cost_allocations a WHERE a.entry_id=e.id));
 ELSIF expected<>0 THEN RAISE EXCEPTION 'Cost changed; reload before editing' USING ERRCODE='40001';END IF;
 SELECT array_agg(x ORDER BY x) INTO all_ids FROM (SELECT DISTINCT unnest(ids||coalesce(old_ids,'{}'::uuid[])) x)u;
 -- Same order -> ledger lock order as automatic status accounting.
 PERFORM o.id FROM public.orders o WHERE o.id=ANY(all_ids) ORDER BY o.id FOR UPDATE;
 PERFORM l.order_id FROM hg_internal.delivery_subsidy_ledger l WHERE l.order_id=ANY(all_ids) ORDER BY l.order_id FOR UPDATE;
 IF (SELECT count(*) FROM hg_internal.delivery_subsidy_ledger WHERE order_id=ANY(ids) AND campus_id=p_campus AND status<>'excluded')<>n THEN RAISE EXCEPTION 'Selected orders are unavailable in this campus' USING ERRCODE='42501';END IF;
 SELECT l.gate_id INTO gate FROM hg_internal.delivery_subsidy_ledger l WHERE l.order_id=ids[1];
 IF EXISTS(SELECT 1 FROM hg_internal.delivery_subsidy_ledger l WHERE l.order_id=ANY(ids) AND l.gate_id IS DISTINCT FROM gate) THEN RAISE EXCEPTION 'A trip must contain orders for one gate' USING ERRCODE='22023';END IF;
 IF EXISTS(SELECT 1 FROM hg_internal.delivery_cost_allocations a WHERE a.order_id=ANY(ids) AND a.entry_id<>entry_id) THEN RAISE EXCEPTION 'An order already has a cost; edit its existing trip instead' USING ERRCODE='40001';END IF;
 IF EXISTS(SELECT 1 FROM hg_internal.delivery_subsidy_ledger l JOIN public.orders o ON o.id=l.order_id WHERE l.order_id=ANY(ids) AND NOT (l.status IN ('delivered','delivery_attempted','unclaimed') OR (l.status IN ('cancelled','refunded') AND (o.out_for_delivery_at IS NOT NULL OR o.delivery_attempted_at IS NOT NULL OR o.delivered_at IS NOT NULL)))) THEN RAISE EXCEPTION 'Costs require a delivered or attempted delivery' USING ERRCODE='22023';END IF;
 IF EXISTS(SELECT 1 FROM hg_internal.delivery_subsidy_ledger l WHERE l.order_id=ANY(ids) AND l.rider_cost IS NOT NULL AND NOT EXISTS(SELECT 1 FROM hg_internal.delivery_cost_allocations a WHERE a.order_id=l.order_id AND a.entry_id=entry_id)) THEN RAISE EXCEPTION 'Order already has a recorded cost' USING ERRCODE='40001';END IF;
 INSERT INTO hg_internal.delivery_cost_entries(id,campus_id,gate_id,cost_date,kind,total_cost,note,entered_by)
 VALUES(entry_id,p_campus,gate,day,kind,total,note,p_actor)
 ON CONFLICT(id) DO UPDATE SET gate_id=EXCLUDED.gate_id,cost_date=EXCLUDED.cost_date,kind=EXCLUDED.kind,total_cost=EXCLUDED.total_cost,note=EXCLUDED.note,entered_by=p_actor,entered_at=now(),version=delivery_cost_entries.version+1;
 DELETE FROM hg_internal.delivery_cost_allocations a WHERE a.entry_id=entry_id;
 UPDATE hg_internal.delivery_subsidy_ledger SET rider_cost=NULL,rider_cost_date=NULL,entered_by=p_actor,entered_at=now(),updated_at=now() WHERE order_id=ANY(coalesce(old_ids,'{}'::uuid[])) AND NOT order_id=ANY(ids);
 kobo:=(total*100)::bigint;
 FOR item IN SELECT x, row_number() OVER(ORDER BY x) rn FROM unnest(ids)x LOOP
  cost:=((kobo/n)+CASE WHEN item.rn<=kobo%n THEN 1 ELSE 0 END)::numeric/100;
  INSERT INTO hg_internal.delivery_cost_allocations(order_id,entry_id,amount) VALUES(item.x,entry_id,cost);
  UPDATE hg_internal.delivery_subsidy_ledger SET rider_cost=cost,rider_cost_date=day,entered_by=p_actor,entered_at=now(),updated_at=now() WHERE order_id=item.x;
 END LOOP;
 SELECT jsonb_build_object('entry',to_jsonb(c),'allocations',(SELECT jsonb_agg(to_jsonb(a) ORDER BY a.order_id) FROM hg_internal.delivery_cost_allocations a WHERE a.entry_id=c.id)) INTO after_data FROM hg_internal.delivery_cost_entries c WHERE c.id=entry_id;
 INSERT INTO hg_internal.delivery_cost_audit(entry_id,actor_id,before_values,after_values) VALUES(entry_id,p_actor,before_data,after_data);
 result:=jsonb_build_object('entry_id',entry_id,'version',(after_data->'entry'->>'version')::integer,'total_cost',total,'orders',n);
 INSERT INTO hg_internal.delivery_cost_receipts(request_id,actor_id,campus_id,payload,result) VALUES(rid,p_actor,p_campus,canonical,result);
 RETURN result;
END$$;
REVOKE ALL ON FUNCTION hg_internal.delivery_cost_actor(uuid,uuid), public.hg_delivery_costs(uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.delivery_cost_actor(uuid,uuid),public.hg_delivery_costs(uuid,uuid,text,jsonb) TO service_role;
