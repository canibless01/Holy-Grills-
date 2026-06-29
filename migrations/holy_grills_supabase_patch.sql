-- ============================================================
--  Holy Grills FUTA — Supabase SQL Patch (corrected)
--
--  Paste the 3 blocks below ONE AT A TIME in Supabase SQL Editor.
--  Each block is self-contained and safe to re-run.
-- ============================================================


-- ════════════════════════════════════════════════════════════
--  BLOCK 1 — hp_bundles table + seed data
--  (Paste this first, Run, confirm green ✓, then do Block 2)
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS hp_bundles (
  id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT          NOT NULL,
  hp_amount   INTEGER       NOT NULL,
  price_naira NUMERIC(10,2) NOT NULL,
  total_price NUMERIC(10,2) NOT NULL,
  description TEXT,
  is_active   BOOLEAN       NOT NULL DEFAULT TRUE,
  sort_order  INTEGER       NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hp_bundles_active
  ON hp_bundles (is_active)
  WHERE is_active = TRUE;

INSERT INTO hp_bundles (name, hp_amount, price_naira, total_price, description, sort_order)
VALUES
  ('Starter Pack',  100,   500,   500,  '100 Holy Points',            1),
  ('Value Pack',    300,  1400,  1400,  '300 Holy Points — best value', 2),
  ('Power Pack',    600,  2600,  2600,  '600 Holy Points',             3),
  ('Elite Pack',   1000,  4000,  4000,  '1000 Holy Points',            4)
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════
--  BLOCK 2 — Cron lock table + RPC functions
--  (Paste after Block 1 succeeds)
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS cron_locks (
  job_name   TEXT        PRIMARY KEY,
  locked_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION try_acquire_cron_lock(p_job_name TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  INSERT INTO cron_locks (job_name, locked_at)
  VALUES (p_job_name, now())
  ON CONFLICT (job_name) DO NOTHING;
  RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION release_cron_lock(p_job_name TEXT)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  DELETE FROM cron_locks WHERE job_name = p_job_name;
END;
$$;


-- ════════════════════════════════════════════════════════════
--  BLOCK 3 — checkin_event_atomic RPC
--  (Paste after Block 2 succeeds)
-- ════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION checkin_event_atomic(
  p_event_id UUID,
  p_qr_token TEXT,
  p_user_id  UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_ticket_id  UUID;
  v_ticket_code TEXT;
  v_checkin_id  UUID;
BEGIN
  -- Find user's ticket for this event
  SELECT id, ticket_code
  INTO   v_ticket_id, v_ticket_code
  FROM   event_tickets
  WHERE  event_id = p_event_id
    AND  user_id  = p_user_id
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('error', 'No ticket found for this event');
  END IF;

  -- Validate QR token
  IF v_ticket_code IS DISTINCT FROM p_qr_token THEN
    RETURN jsonb_build_object('error', 'Invalid QR token');
  END IF;

  -- Prevent double check-in
  IF EXISTS (SELECT 1 FROM event_checkins WHERE ticket_id = v_ticket_id) THEN
    RETURN jsonb_build_object('error', 'Already checked in to this event');
  END IF;

  -- Record check-in (uses checked_in_at per schema)
  INSERT INTO event_checkins (ticket_id, checked_in_at)
  VALUES (v_ticket_id, now())
  RETURNING id INTO v_checkin_id;

  RETURN jsonb_build_object(
    'success',    TRUE,
    'checkin_id', v_checkin_id,
    'ticket_id',  v_ticket_id
  );
END;
$$;
