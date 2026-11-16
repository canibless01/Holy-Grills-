-- Step 1: internal allocations inside the existing retail price. No price,
-- order, item history or wallet update/backfill occurs in this migration.
ALTER TABLE public.menu_items ADD COLUMN cushion_amount numeric(14,2) NOT NULL DEFAULT 0
 CHECK(cushion_amount>=0 AND cushion_amount<=greatest(price,0) AND cushion_amount::text NOT IN ('NaN','Infinity','-Infinity'));
ALTER TABLE public.menu_addons ADD COLUMN cushion_amount numeric(14,2) NOT NULL DEFAULT 0
 CHECK(cushion_amount>=0 AND cushion_amount<=greatest(price,0) AND cushion_amount::text NOT IN ('NaN','Infinity','-Infinity'));
-- Positive-price combo choices are represented by variation options, while
-- checkout bundle-style extras already live in menu_addons. HP bundles are not food.
ALTER TABLE public.menu_item_variation_options ADD COLUMN cushion_amount numeric(14,2) NOT NULL DEFAULT 0
 CHECK(cushion_amount>=0 AND cushion_amount<=greatest(price_delta,0) AND cushion_amount::text NOT IN ('NaN','Infinity','-Infinity'));
ALTER TABLE public.order_items ADD COLUMN cushion_snapshot numeric(14,2) NOT NULL DEFAULT 0
 CHECK(cushion_snapshot>=0 AND cushion_snapshot::text NOT IN ('NaN','Infinity','-Infinity'));
ALTER TABLE public.order_addon_selections ADD COLUMN cushion_snapshot numeric(14,2) NOT NULL DEFAULT 0
 CHECK(cushion_snapshot>=0 AND cushion_snapshot::text NOT IN ('NaN','Infinity','-Infinity'));

CREATE FUNCTION hg_internal.capture_delivery_cushion_snapshot() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE amount numeric:=0;extra numeric:=0;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF NEW.cushion_snapshot IS DISTINCT FROM OLD.cushion_snapshot THEN
   RAISE EXCEPTION 'Delivery cushion snapshots are immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 END IF;
 -- All supported checkout admissions use the existing service-only atomic RPC.
 -- A direct browser insert cannot select or set an internal allocation.
 NEW.cushion_snapshot:=0;
 IF coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'role','')<>'service_role' THEN RETURN NEW;END IF;
 IF TG_TABLE_NAME='order_items' THEN
  IF coalesce(NEW.price_snapshot,0)<=0 THEN RETURN NEW;END IF;
  IF coalesce(NEW.is_addon,false) THEN
   SELECT cushion_amount INTO amount FROM menu_addons WHERE id=NEW.addon_id AND (campus_id IS NULL OR campus_id=NEW.campus_id);
  ELSE
   SELECT cushion_amount INTO amount FROM menu_items WHERE id=NEW.menu_item_id AND (campus_id IS NULL OR campus_id=NEW.campus_id);
   SELECT coalesce(sum(o.cushion_amount),0) INTO extra FROM menu_item_variation_options o
    JOIN menu_item_variation_groups g ON g.id=o.variation_group_id
    WHERE g.menu_item_id=NEW.menu_item_id AND (o.campus_id IS NULL OR o.campus_id=NEW.campus_id)
     AND o.id::text IN(SELECT selection->>'option_id' FROM jsonb_array_elements(coalesce(NEW.selected_variations,'[]')) selection);
  END IF;
  NEW.cushion_snapshot:=least(NEW.price_snapshot,greatest(0,coalesce(amount,0)+extra));
 ELSE
  IF coalesce(NEW.price_delta_snapshot,0)<=0 THEN RETURN NEW;END IF;
  SELECT cushion_amount INTO amount FROM menu_addons WHERE id=NEW.addon_id AND (campus_id IS NULL OR campus_id=NEW.campus_id);
  NEW.cushion_snapshot:=least(NEW.price_delta_snapshot,greatest(0,coalesce(amount,0)));
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.capture_delivery_cushion_snapshot() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.capture_delivery_cushion_snapshot() TO service_role;
CREATE TRIGGER capture_delivery_cushion BEFORE INSERT OR UPDATE ON public.order_items
 FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_delivery_cushion_snapshot();
CREATE TRIGGER capture_delivery_cushion BEFORE INSERT OR UPDATE ON public.order_addon_selections
 FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_delivery_cushion_snapshot();

-- Preserve each browser role's previous effective column access, excluding the
-- new internal values. RLS still controls rows. Backend projection compatibility
-- must be deployed first, so existing SELECT * reads and write receipts work.
DO $$
DECLARE t text;r text;op text;columns text;rights jsonb;
BEGIN
 FOREACH t IN ARRAY ARRAY['menu_items','menu_addons','menu_item_variation_options','order_items','order_addon_selections'] LOOP
  SELECT string_agg(quote_ident(attname),',' ORDER BY attnum) INTO columns FROM pg_attribute
   WHERE attrelid=('public.'||t)::regclass AND attnum>0 AND NOT attisdropped AND attname NOT IN ('cushion_amount','cushion_snapshot');
  SELECT jsonb_object_agg(role_name,jsonb_build_object('SELECT',has_table_privilege(role_name,('public.'||t)::regclass,'SELECT'),
   'INSERT',has_table_privilege(role_name,('public.'||t)::regclass,'INSERT'),'UPDATE',has_table_privilege(role_name,('public.'||t)::regclass,'UPDATE')))
   INTO rights FROM unnest(ARRAY['anon','authenticated']) role_name;
  EXECUTE format('REVOKE SELECT,INSERT,UPDATE ON public.%I FROM PUBLIC,anon,authenticated',t);
  FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
   FOREACH op IN ARRAY ARRAY['SELECT','INSERT','UPDATE'] LOOP
    IF (rights->r->>op)::boolean THEN EXECUTE format('GRANT %s (%s) ON public.%I TO %I',op,columns,t,r);END IF;
   END LOOP;
  END LOOP;
 END LOOP;
END $$;
