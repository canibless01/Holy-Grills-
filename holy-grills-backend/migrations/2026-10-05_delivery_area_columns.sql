-- Delivery area: the columns the radius feature reads and writes.
-- =====================================================================================
-- WHY THIS FILE EXISTS
--
-- The delivery radius is two values in two tables:
--   • campuses.lat / campuses.lon          — the centre point the radius is measured from
--   • kitchen_settings.max_delivery_radius_km (per campus) — the radius
--
-- Both are read and written by live code today:
--   app/routes/admin.py       get_campus_location / set_campus_location
--                             SELECT id,name,lat,lon ... UPDATE {lat, lon, updated_at}
--   app/routes/kitchen.py     get/update_kitchen_settings
--                             .eq("campus_id", campus_id) and
--                             .upsert(payload, on_conflict="key,campus_id")
--   app/routes/storefront.py  get_public_config (service client, D17-B09)
--   app/routes/delivery.py    is_within_delivery_area
--
-- However BACKEND_SOURCE_OF_TRUTH.md currently documents
--   public.campuses          → id, name, slug, is_active, created_at, updated_at
--   public.kitchen_settings  → key, value, updated_at, updated_by
-- with NO lat/lon and NO campus_id. Either that document is stale (most likely:
-- the code comments describe observed live behaviour, e.g. "the anon client
-- always read 0 rows here and every guest silently got the 15 km default"),
-- or the columns are genuinely absent and those endpoints have been failing.
--
-- This migration is fully idempotent and safe either way: every statement is
-- guarded, so running it against a database that already has the columns
-- changes nothing. Run the VERIFY query at the bottom first to find out which
-- case you are in.
-- =====================================================================================

-- ───────────────────────────── VERIFY FIRST ─────────────────────────────
-- Paste into the Supabase SQL editor and run it. If both rows return true,
-- you do NOT need the rest of this file.
--
--   SELECT
--     EXISTS (SELECT 1 FROM information_schema.columns
--             WHERE table_name='campuses' AND column_name='lat')          AS campuses_has_lat,
--     EXISTS (SELECT 1 FROM information_schema.columns
--             WHERE table_name='campuses' AND column_name='lon')          AS campuses_has_lon,
--     EXISTS (SELECT 1 FROM information_schema.columns
--             WHERE table_schema='public' AND table_name='kitchen_settings'
--               AND column_name='campus_id')                              AS kitchen_settings_has_campus_id;

-- ───────────────────────────── campuses.lat / .lon ──────────────────────
-- The single origin point per campus. Nullable: a campus with no centre yet
-- must still be listable, and set_campus_location accepts nulls to clear it.
ALTER TABLE public.campuses ADD COLUMN IF NOT EXISTS lat double precision;
ALTER TABLE public.campuses ADD COLUMN IF NOT EXISTS lon double precision;

-- Sanity constraint: latitude/longitude ranges. Guards against a typo in a
-- pasted "lat, lon" pair landing in the table. The API validates this too
-- (_parse_coord + the Nigeria bounds check); this is the backstop.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'campuses_lat_lon_range') THEN
    ALTER TABLE public.campuses
      ADD CONSTRAINT campuses_lat_lon_range
      CHECK (lat IS NULL OR (lat BETWEEN -90 AND 90))
      NOT VALID;   -- NOT VALID so existing rows are not scanned on a busy table
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'campuses_lon_range') THEN
    ALTER TABLE public.campuses
      ADD CONSTRAINT campuses_lon_range
      CHECK (lon IS NULL OR (lon BETWEEN -180 AND 180))
      NOT VALID;
  END IF;
END $$;

-- ───────────────────────────── kitchen_settings.campus_id ───────────────
-- Makes kitchen settings per-campus. NULL = the global default row.
ALTER TABLE public.kitchen_settings
  ADD COLUMN IF NOT EXISTS campus_id uuid REFERENCES public.campuses(id) ON DELETE CASCADE;

-- The upsert in kitchen.py uses on_conflict="key,campus_id", and PostgREST
-- can only do that against a real unique index. Without it the write fails
-- with "there is no unique or exclusion constraint matching the ON CONFLICT
-- specification" — which is the single most likely reason saving the radius
-- would 500.
CREATE UNIQUE INDEX IF NOT EXISTS kitchen_settings_key_campus_id_key
  ON public.kitchen_settings (key, campus_id);

-- The upsert payload has no id column, so the column needs a default or the
-- insert half of the upsert fails on a NOT NULL id.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='kitchen_settings'
      AND column_name='id' AND is_nullable='NO'
  ) THEN
    ALTER TABLE public.kitchen_settings ALTER COLUMN id SET DEFAULT gen_random_uuid();
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_kitchen_settings_campus_id
  ON public.kitchen_settings (campus_id);

-- ───────────────────────────── seed (optional) ──────────────────────────
-- One row per campus so the admin screen shows a value instead of blank.
-- Safe to re-run: it only inserts rows that are not already there.
INSERT INTO public.kitchen_settings (key, value, campus_id, updated_at)
SELECT 'max_delivery_radius_km', '15', c.id, now()
FROM public.campuses c
WHERE NOT EXISTS (
  SELECT 1 FROM public.kitchen_settings ks
  WHERE ks.key = 'max_delivery_radius_km' AND ks.campus_id = c.id
);

-- ───────────────────────────── VERIFY AFTER ─────────────────────────────
--   SELECT c.name, c.lat, c.lon,
--          (SELECT value FROM public.kitchen_settings ks
--            WHERE ks.key='max_delivery_radius_km' AND ks.campus_id=c.id) AS radius_km
--   FROM public.campuses c ORDER BY c.name;
--
-- Then: Admin → Delivery → Delivery area, save a centre point and a radius,
-- and confirm GET /api/storefront/config/public returns campus_lat,
-- campus_lon and max_delivery_radius_km for that campus.
