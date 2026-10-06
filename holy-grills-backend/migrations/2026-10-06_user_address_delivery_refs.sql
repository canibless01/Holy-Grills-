-- ═══════════════════════════════════════════════════════════════════════════
--  user_addresses: remember WHAT was saved, not just where
--
--  WHY
--    A saved address is replayed at checkout: tapping it must re-apply the
--    delivery type (on-campus hostel / off-campus pin) and re-run the fee
--    calculation. The table only had latitude/longitude, so an off-campus
--    address could be re-pinned but an on-campus one could not be resolved back
--    to its hostel, and neither carried its type or gate. The address form was
--    already sending these three fields; the API's field allowlist dropped them.
--
--    Nothing here is a new concept — `hostels` and `gates` already exist and
--    `user_addresses` already points at the campus. This adds the two references
--    a saved address needs so it can be replayed.
--
--  HOW TO RUN
--    Supabase dashboard → SQL Editor → paste this whole file → Run.
--    Idempotent (ADD COLUMN IF NOT EXISTS) and non-destructive: no data is
--    rewritten, no column is dropped, and existing rows simply read as
--    delivery_type = NULL → the client falls back to "has coordinates" for
--    off-campus and to the hostel-name match for on-campus.
--
--  RLS is unchanged: `user_addresses: users crud own` already covers new columns
--  (policies are per-table, not per-column), so no policy work is needed.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE public.user_addresses
  ADD COLUMN IF NOT EXISTS delivery_type text
    CHECK (delivery_type IS NULL OR delivery_type IN ('on_campus', 'off_campus'));

-- The gate the rider is met at, and (on-campus) the hostel the order is
-- delivered to. Both are plain references, never owned data — ON DELETE SET NULL
-- so removing a gate/hostel in the admin panel leaves the address intact
-- instead of deleting a student's saved address with it.
ALTER TABLE public.user_addresses
  ADD COLUMN IF NOT EXISTS gate_id     uuid REFERENCES public.gates(id)     ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS location_id uuid REFERENCES public.hostels(id)  ON DELETE SET NULL;

-- Checkout reads the user's default/first address; delivery lookups filter by
-- the referenced location. Both are single-column indexes on an existing
-- per-user table, so they are cheap.
CREATE INDEX IF NOT EXISTS idx_user_addresses_gate     ON public.user_addresses (gate_id)     WHERE gate_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_addresses_location ON public.user_addresses (location_id) WHERE location_id IS NOT NULL;

COMMENT ON COLUMN public.user_addresses.delivery_type IS
  'on_campus | off_campus | NULL. What the student saved, so checkout can re-apply it without guessing.';
COMMENT ON COLUMN public.user_addresses.gate_id IS
  'gates.id — the gate an off-campus delivery is met at (also the nearest gate for a saved pin).';
COMMENT ON COLUMN public.user_addresses.location_id IS
  'hostels.id — the hostel an on-campus delivery goes to.';

-- ── VERIFY ────────────────────────────────────────────────────────────────
--   SELECT column_name, data_type
--     FROM information_schema.columns
--    WHERE table_name = 'user_addresses'
--      AND column_name IN ('delivery_type', 'gate_id', 'location_id');
--   -- expect 3 rows. Then in the app: Addresses → save an on-campus and an
--   -- off-campus address → checkout → tap each one → the hostel / pin and the
--   -- fee are re-applied automatically.
