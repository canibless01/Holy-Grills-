-- ============================================================
--  Holy Grills FUTA — Session SQL Changes
--  All database updates made during this development session.
--  Safe to re-run (IF NOT EXISTS / OR REPLACE throughout).
--
--  BLOCKS IN ORDER:
--   1. Squad-order columns on orders
--   2. claim_token column on orders
--   3. hp_bundles table + seed data
--   4. cron_locks table + RPC functions
--   5. checkin_event_atomic RPC (fixed — uses ticket UUID as QR)
--   6. claim_guest_order RPC (links guest order to new account)
--   7. status column on hp_transactions (pending vs active HP)
-- ============================================================


-- ────────────────────────────────────────────────────────────
--  1. Squad-order columns on orders table
--     (identifies group orders that qualify for discounts)
-- ────────────────────────────────────────────────────────────
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS is_squad_order        BOOLEAN       NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS squad_discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS squad_item_count      INTEGER       NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_orders_is_squad_order
  ON orders (is_squad_order)
  WHERE is_squad_order = TRUE;


-- ────────────────────────────────────────────────────────────
--  2. claim_token column on orders table
--     (UUID issued to guest orders so a registered user can
--      later claim them via POST /orders/:id/claim)
-- ────────────────────────────────────────────────────────────
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS claim_token UUID DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_orders_claim_token
  ON orders (claim_token)
  WHERE claim_token IS NOT NULL;


-- ────────────────────────────────────────────────────────────
--  3. hp_bundles table
--     (catalogue of HP packages available for purchase)
-- ────────────────────────────────────────────────────────────
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
  ('Starter Pack',  100,   500,   500,  '100 Holy Points — great for new members',    1),
  ('Value Pack',    300,  1400,  1400,  '300 Holy Points — best value for regulars',  2),
  ('Power Pack',    600,  2600,  2600,  '600 Holy Points — for champions',             3),
  ('Elite Pack',   1000,  4000,  4000,  '1000 Holy Points — maximum loyalty reward',  4)
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────
--  4. cron_locks table + RPC functions
--     (prevents duplicate runs of background Celery jobs)
--
--  NOTE: If you see "cannot change return type" on
--  release_cron_lock, run the two DROP lines first,
--  then paste the rest.
-- ────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS try_acquire_cron_lock(TEXT);
DROP FUNCTION IF EXISTS release_cron_lock(TEXT);

CREATE TABLE IF NOT EXISTS cron_locks (
  job_name   TEXT        PRIMARY KEY,
  locked_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION try_acquire_cron_lock(p_job_name TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO cron_locks (job_name, locked_at)
  VALUES (p_job_name, now())
  ON CONFLICT (job_name) DO NOTHING;
  RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION release_cron_lock(p_job_name TEXT)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  DELETE FROM cron_locks WHERE job_name = p_job_name;
END;
$$;


-- ────────────────────────────────────────────────────────────
--  5. checkin_event_atomic RPC function
--     (validates QR token = ticket UUID, prevents double
--      check-in, records to event_checkins atomically)
--
--  The QR code embedded in the ticket IS the ticket UUID.
--  Pass the ticket UUID string as p_qr_token on the client.
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION checkin_event_atomic(
  p_event_id UUID,
  p_qr_token TEXT,
  p_user_id  UUID
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_ticket_id  UUID;
  v_checkin_id UUID;
BEGIN
  -- Find user's ticket for this event
  SELECT id INTO v_ticket_id
  FROM   event_tickets
  WHERE  event_id = p_event_id
    AND  user_id  = p_user_id
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('error', 'No ticket found for this event');
  END IF;

  -- QR token must match the ticket UUID
  IF v_ticket_id::TEXT <> p_qr_token THEN
    RETURN jsonb_build_object('error', 'Invalid QR token');
  END IF;

  -- Prevent double check-in
  IF EXISTS (SELECT 1 FROM event_checkins WHERE ticket_id = v_ticket_id) THEN
    RETURN jsonb_build_object('error', 'Already checked in to this event');
  END IF;

  -- Record check-in
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


-- ────────────────────────────────────────────────────────────
--  6. claim_guest_order RPC
--     (called by POST /orders/:id/claim — links a guest order
--      to a newly registered user account using the one-time
--      claim_token issued when the guest order was placed)
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION claim_guest_order(
  p_order_id    UUID,
  p_user_id     UUID,
  p_claim_token UUID
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_order RECORD;
BEGIN
  -- Find the guest order by ID and claim token
  SELECT id, user_id, status, total_amount, claim_token
  INTO   v_order
  FROM   orders
  WHERE  id          = p_order_id
    AND  claim_token = p_claim_token
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('error', 'Order not found or claim token invalid');
  END IF;

  IF v_order.user_id IS NOT NULL THEN
    RETURN jsonb_build_object('error', 'Order is already linked to an account');
  END IF;

  -- Link the order to the registered user and clear the claim token
  UPDATE orders
  SET    user_id     = p_user_id,
         claim_token = NULL
  WHERE  id = p_order_id;

  RETURN jsonb_build_object(
    'success',      TRUE,
    'order_id',     p_order_id,
    'user_id',      p_user_id,
    'status',       v_order.status,
    'total_amount', v_order.total_amount
  );
END;
$$;


-- ────────────────────────────────────────────────────────────
--  7. status column on hp_transactions
--     The code tracks pending HP (referrals, reviews, events,
--     social shares) as separate ledger rows with status='pending'
--     so they never inflate the spendable active balance until
--     manually approved/converted by an admin job.
-- ────────────────────────────────────────────────────────────
ALTER TABLE hp_transactions
  ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'
  CHECK (status IN ('active', 'pending', 'expired', 'cancelled'));

-- Back-fill: all pre-migration rows are treated as active
UPDATE hp_transactions SET status = 'active' WHERE status IS NULL OR status = '';

CREATE INDEX IF NOT EXISTS idx_hp_transactions_user_status
  ON hp_transactions (user_id, status);



--    Tracks each rider's availability and location, keyed by user id.
CREATE TABLE IF NOT EXISTS public.rider_profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    is_available            BOOLEAN NOT NULL DEFAULT FALSE,
    availability_updated_at TIMESTAMPTZ,
    location_lat            DOUBLE PRECISION,
    location_lng            DOUBLE PRECISION,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

ALTER TABLE public.rider_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Riders manage own profile"
    ON public.rider_profiles FOR ALL
    USING (auth.uid() = user_id);
CREATE POLICY "Admins manage all rider profiles"
    ON public.rider_profiles FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );


-- 2. device_tokens
--    Push-notification tokens registered by each user's device.
CREATE TABLE IF NOT EXISTS public.device_tokens (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    token        TEXT NOT NULL,
    platform     TEXT NOT NULL DEFAULT 'unknown',
    device_model TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, token)
);

ALTER TABLE public.device_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own device tokens"
    ON public.device_tokens FOR ALL
    USING (auth.uid() = user_id);


-- 3. notification_preferences
--    Per-user opt-in/opt-out flags for each notification channel.
CREATE TABLE IF NOT EXISTS public.notification_preferences (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    push_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    email_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    order_updates    BOOLEAN NOT NULL DEFAULT TRUE,
    promotions       BOOLEAN NOT NULL DEFAULT TRUE,
    hp_updates       BOOLEAN NOT NULL DEFAULT TRUE,
    delivery_updates BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

ALTER TABLE public.notification_preferences ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own notification preferences"
    ON public.notification_preferences FOR ALL
    USING (auth.uid() = user_id);


-- 4. wallet_withdrawals
--    Pending/processed withdrawal requests from user wallets.
CREATE TABLE IF NOT EXISTS public.wallet_withdrawals (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    amount         NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    bank_code      TEXT NOT NULL,
    account_number TEXT NOT NULL,
    account_name   TEXT NOT NULL,
    narration      TEXT,
    reference      TEXT NOT NULL UNIQUE,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    processed_at   TIMESTAMPTZ,
    failure_reason TEXT,
    metadata       JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.wallet_withdrawals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users view own withdrawals"
    ON public.wallet_withdrawals FOR SELECT
    USING (auth.uid() = user_id);
CREATE POLICY "Admins manage all withdrawals"
    ON public.wallet_withdrawals FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- ============================================================
-- After running this migration, re-test with:
--   python test_new_apis.py
-- The WARN items for missing tables will upgrade to PASS.
-- ============================================================
