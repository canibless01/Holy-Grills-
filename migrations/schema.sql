-- ============================================================
--  Holy Grills FUTA — Canonical Database Schema (Third Migration)
--  Run in Supabase SQL Editor AFTER schema_1.sql and schema_2.sql.
--  Every statement is idempotent (IF NOT EXISTS / OR REPLACE).
--
--  Last updated: 2026-07-16
--
--  EXECUTION ORDER:
--   Phase 1 — CREATE TABLE (all new tables, in dependency order)
--   Phase 2 — ALTER TABLE  (add columns to prior-schema tables)
--   Phase 3 — ALTER TABLE  (constraint fixes on new tables)
--   Phase 4 — UPDATE       (back-fill data)
--   Phase 5 — CREATE INDEX (all indexes — tables guaranteed to exist)
--   Phase 6 — RLS ENABLE + POLICY
--   Phase 7 — CREATE OR REPLACE FUNCTION
--   Phase 8 — COMMENT ON
--   Phase 9 — INSERT seed data
-- ============================================================


-- ============================================================
-- PHASE 1 — CREATE TABLE (all new tables, dependency order)
-- ============================================================

-- ── 1.01 gates (off-campus delivery fee reference) ────────────────────────────
--  Must be created before hostels (FK: hostels.gate_id → gates.id).
CREATE TABLE IF NOT EXISTS public.gates (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  lat           DOUBLE PRECISION,
  lon           DOUBLE PRECISION,
  base_fee      NUMERIC(10,2) NOT NULL DEFAULT 0,
  rate_per_km   NUMERIC(10,2) NOT NULL DEFAULT 0,
  min_fee       NUMERIC(10,2) NOT NULL DEFAULT 0,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 1.02 hostels (on-campus fixed delivery fee) ───────────────────────────────
CREATE TABLE IF NOT EXISTS public.hostels (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  gate_id       UUID REFERENCES public.gates(id) ON DELETE SET NULL,
  delivery_fee  NUMERIC(10,2) NOT NULL DEFAULT 0,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 1.03 hp_bundles (HP packages available for purchase) ─────────────────────
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

-- ── 1.04 cron_locks (prevents duplicate background job runs) ─────────────────
CREATE TABLE IF NOT EXISTS cron_locks (
  job_name   TEXT        PRIMARY KEY,
  locked_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 1.05 rider_profiles ───────────────────────────────────────────────────────
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

-- ── 1.06 device_tokens ────────────────────────────────────────────────────────
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

-- ── 1.07 notification_preferences ────────────────────────────────────────────
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

-- ── 1.08 wallet_withdrawals ───────────────────────────────────────────────────
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

-- ── 1.09 menu_addon_groups (must come before order_addon_selections) ──────────
CREATE TABLE IF NOT EXISTS public.menu_addon_groups (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    menu_item_id UUID NOT NULL REFERENCES public.menu_items(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    is_required  BOOLEAN NOT NULL DEFAULT FALSE,
    min_select   INTEGER NOT NULL DEFAULT 0,
    max_select   INTEGER NOT NULL DEFAULT 1,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (min_select >= 0 AND max_select >= min_select)
);

-- ── 1.10 order_addon_selections ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.order_addon_selections (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_item_id  UUID NOT NULL REFERENCES public.order_items(id) ON DELETE CASCADE,
    addon_id       UUID NOT NULL REFERENCES public.menu_addons(id),
    group_id       UUID REFERENCES public.menu_addon_groups(id),
    name_snapshot  TEXT NOT NULL,
    price_delta_snapshot NUMERIC(10,2) NOT NULL DEFAULT 0,
    quantity       INTEGER NOT NULL DEFAULT 1,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 1.11 saved_for_later ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.saved_for_later (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    menu_item_id UUID NOT NULL REFERENCES public.menu_items(id) ON DELETE CASCADE,
    quantity     INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 1),
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, menu_item_id)
);

-- ── 1.12 first_order_gifts ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.first_order_gifts (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_id   UUID REFERENCES public.orders(id) ON DELETE SET NULL,
    status     TEXT NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending', 'fulfilled', 'cancelled')),
    claimed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

-- ── 1.13 order_locks ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.order_locks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    locked_date       DATE NOT NULL,
    discount_pct      NUMERIC(5,2) NOT NULL DEFAULT 10 CHECK (discount_pct BETWEEN 0 AND 50),
    reward_type       TEXT NOT NULL DEFAULT 'discount' CHECK (reward_type IN ('discount', 'hp')),
    reward_hp_amount  INTEGER,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'used', 'expired', 'cancelled')),
    reminder_sent_at  TIMESTAMPTZ,
    reschedule_count  INTEGER NOT NULL DEFAULT 0 CHECK (reschedule_count >= 0),
    order_id          UUID REFERENCES public.orders(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 1.14 login_streaks ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.login_streaks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    streak_count        INTEGER NOT NULL DEFAULT 1 CHECK (streak_count >= 0),
    last_login_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    last_updated        TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_week_start  DATE,
    week_state          JSONB,
    cycle_week_number   INTEGER NOT NULL DEFAULT 1,
    consecutive_weeks   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id)
);

-- ── 1.15 monthly_hp_tracker ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.monthly_hp_tracker (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    month        TEXT NOT NULL,          -- format: 'YYYY-MM'
    total_earned INTEGER NOT NULL DEFAULT 0 CHECK (total_earned >= 0),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT monthly_hp_tracker_user_month_key UNIQUE (user_id, month)
);

-- ── 1.16 squad_members ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.squad_members (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    user_id             UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    email               TEXT NOT NULL,
    hp_share            INTEGER NOT NULL DEFAULT 0 CHECK (hp_share >= 0),
    invite_sent         BOOLEAN NOT NULL DEFAULT FALSE,
    is_registered       BOOLEAN NOT NULL DEFAULT FALSE,
    referral_attributed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 1.17 device_fingerprints ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.device_fingerprints (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    platform    TEXT NOT NULL DEFAULT 'unknown',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fingerprint)
);

-- ── 1.18 system_settings ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.system_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  UUID REFERENCES public.profiles(id) ON DELETE SET NULL
);

-- ── 1.19 order_share_events ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.order_share_events (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_id   UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    platform   TEXT NOT NULL DEFAULT 'whatsapp',
    hp_awarded INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 1.20 marketplace_requests ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.marketplace_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_name     TEXT NOT NULL,
    vendor_email    TEXT NOT NULL,
    vendor_phone    TEXT,
    service_title   TEXT NOT NULL,
    category        TEXT NOT NULL,
    description     TEXT NOT NULL,
    proposed_price  NUMERIC NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
    admin_notes     TEXT,
    reviewed_by     UUID REFERENCES public.profiles(id),
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 1.21 webhook_events ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.webhook_events (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type     TEXT NOT NULL,
  provider       TEXT,                        -- 'paystack' | 'flutterwave'
  reference      TEXT NOT NULL DEFAULT '',
  payload        JSONB,
  status         TEXT NOT NULL DEFAULT 'processed', -- 'processed' | 'failed'
  error          TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at   TIMESTAMPTZ
);

-- ── 1.22 flash_redemptions ────────────────────────────────────────────────────
--  NOTE: references public.rewards — must exist in a prior schema.
CREATE TABLE IF NOT EXISTS public.flash_redemptions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reward_id        UUID NOT NULL REFERENCES public.rewards(id) ON DELETE CASCADE,
  window_starts_at TIMESTAMPTZ NOT NULL,
  window_ends_at   TIMESTAMPTZ NOT NULL,
  quantity_limit   INTEGER NOT NULL DEFAULT 5,
  discount_pct     NUMERIC(5,2) NOT NULL DEFAULT 0.50,
  is_active        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 1.23 hp_bundle_purchases ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.hp_bundle_purchases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_host_id   UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  hp_amount       INTEGER NOT NULL,
  naira_paid      NUMERIC(12,2) NOT NULL,
  price_per_hp    NUMERIC(10,4) NOT NULL DEFAULT 5.0,
  status          TEXT NOT NULL DEFAULT 'completed',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 1.24 banners (storefront homepage carousel) ───────────────────────────────
CREATE TABLE IF NOT EXISTS public.banners (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       TEXT NOT NULL,
  subtitle    TEXT,
  image_url   TEXT NOT NULL,
  images      JSONB,
  cta_text    TEXT,
  cta_url     TEXT,
  placement   TEXT NOT NULL DEFAULT 'homepage',
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- PHASE 2 — ALTER TABLE (add columns to prior-schema tables)
-- ============================================================

-- ── 2.01 orders: squad-order columns ─────────────────────────────────────────
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS is_squad_order        BOOLEAN       NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS squad_discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS squad_item_count      INTEGER       NOT NULL DEFAULT 0;

-- ── 2.02 orders: guest-order claim token ─────────────────────────────────────
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS claim_token UUID DEFAULT NULL;

-- ── 2.03 hp_transactions: status column ──────────────────────────────────────
ALTER TABLE hp_transactions
  ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'
  CHECK (status IN ('active', 'pending', 'expired', 'cancelled'));

-- ── 2.04 orders: scheduled-order flag ────────────────────────────────────────
ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS is_scheduled BOOLEAN NOT NULL DEFAULT FALSE;

-- ── 2.05 order_reviews: per-role ratings ─────────────────────────────────────
ALTER TABLE public.order_reviews
  ADD COLUMN IF NOT EXISTS kitchen_rating SMALLINT CHECK (kitchen_rating BETWEEN 1 AND 5),
  ADD COLUMN IF NOT EXISTS rider_rating   SMALLINT CHECK (rider_rating   BETWEEN 1 AND 5);

-- ── 2.06 profiles: JWT version counter ───────────────────────────────────────
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS jwt_version INTEGER NOT NULL DEFAULT 0;

-- ── 2.07 cart_items: abandoned-cart timestamp ─────────────────────────────────
ALTER TABLE public.cart_items
    ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ── 2.08 orders: first-order gift flag ───────────────────────────────────────
ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS gift_included BOOLEAN NOT NULL DEFAULT FALSE;

-- ── 2.09 profiles: last activity for decay-onset ─────────────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ;

-- ── 2.10 profiles: rolling 120-day HP counter ────────────────────────────────
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS hp_earned_120day INTEGER NOT NULL DEFAULT 0;

-- ── 2.11 menu_addons: group_id FK → menu_addon_groups ────────────────────────
ALTER TABLE public.menu_addons
  ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES public.menu_addon_groups(id) ON DELETE CASCADE;

-- ── 2.12 orders: delivery location columns ───────────────────────────────────
ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS delivery_type          TEXT CHECK (delivery_type IN ('on_campus','off_campus')),
  ADD COLUMN IF NOT EXISTS delivery_location_id   UUID,
  ADD COLUMN IF NOT EXISTS delivery_location_lat  DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS delivery_location_lon  DOUBLE PRECISION;


-- ============================================================
-- PHASE 3 — ALTER TABLE (constraint fixes on new tables)
-- ============================================================

-- ── 3.01 monthly_hp_tracker: unique constraint idempotent fix ─────────────────
--  PostgreSQL does NOT support ADD CONSTRAINT IF NOT EXISTS.
--  Use DROP + ADD to make this idempotent.
ALTER TABLE public.monthly_hp_tracker
  DROP CONSTRAINT IF EXISTS monthly_hp_tracker_user_month_key,
  ADD CONSTRAINT monthly_hp_tracker_user_month_key UNIQUE (user_id, month);

-- ── 3.02 order_locks: remove hardwired reschedule cap ────────────────────────
--  Remove CHECK (reschedule_count <= 1) so the app config controls the cap.
ALTER TABLE public.order_locks
  DROP CONSTRAINT IF EXISTS order_locks_reschedule_count_check;

ALTER TABLE public.order_locks
  ADD CONSTRAINT order_locks_reschedule_count_check
  CHECK (reschedule_count >= 0);


-- ============================================================
-- PHASE 4 — UPDATE (back-fill data)
-- ============================================================

-- Back-fill hp_transactions: pre-migration rows are treated as active.
UPDATE hp_transactions SET status = 'active' WHERE status IS NULL OR status = '';


-- ============================================================
-- PHASE 5 — CREATE INDEX (all tables guaranteed to exist now)
-- ============================================================

-- orders (prior schema)
CREATE INDEX IF NOT EXISTS idx_orders_is_squad_order
  ON orders (is_squad_order)
  WHERE is_squad_order = TRUE;

CREATE INDEX IF NOT EXISTS idx_orders_claim_token
  ON orders (claim_token)
  WHERE claim_token IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_orders_is_scheduled
  ON public.orders (is_scheduled)
  WHERE is_scheduled = TRUE;

-- hp_transactions (prior schema)
CREATE INDEX IF NOT EXISTS idx_hp_transactions_user_status
  ON hp_transactions (user_id, status);

-- profiles (prior schema)
CREATE INDEX IF NOT EXISTS idx_profiles_jwt_version
  ON public.profiles (id, jwt_version);

-- order_reviews (prior schema)
CREATE INDEX IF NOT EXISTS idx_order_reviews_kitchen_rating
  ON public.order_reviews (kitchen_rating)
  WHERE kitchen_rating IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_order_reviews_rider_rating
  ON public.order_reviews (rider_rating)
  WHERE rider_rating IS NOT NULL;

-- menu_addons (prior schema)
CREATE INDEX IF NOT EXISTS idx_menu_addons_group_id
  ON public.menu_addons (group_id);

-- hp_bundles (new)
CREATE INDEX IF NOT EXISTS idx_hp_bundles_active
  ON hp_bundles (is_active)
  WHERE is_active = TRUE;

-- menu_addon_groups (new)
CREATE INDEX IF NOT EXISTS idx_menu_addon_groups_item
  ON public.menu_addon_groups (menu_item_id);

-- order_addon_selections (new)
CREATE INDEX IF NOT EXISTS idx_order_addon_selections_order_item
  ON public.order_addon_selections (order_item_id);

-- saved_for_later (new)
CREATE INDEX IF NOT EXISTS idx_saved_for_later_user
    ON public.saved_for_later (user_id);

-- first_order_gifts (new)
CREATE INDEX IF NOT EXISTS idx_first_order_gifts_status
    ON public.first_order_gifts (status)
    WHERE status = 'pending';

-- order_locks (new)
CREATE INDEX IF NOT EXISTS idx_order_locks_user_status
    ON public.order_locks (user_id, status);
CREATE INDEX IF NOT EXISTS idx_order_locks_locked_date
    ON public.order_locks (locked_date)
    WHERE status = 'active';

-- login_streaks (new)
CREATE INDEX IF NOT EXISTS idx_login_streaks_user
    ON public.login_streaks (user_id);

-- monthly_hp_tracker (new)
CREATE INDEX IF NOT EXISTS idx_monthly_hp_tracker_user_month
    ON public.monthly_hp_tracker (user_id, month);

-- squad_members (new)
CREATE INDEX IF NOT EXISTS idx_squad_members_order
    ON public.squad_members (order_id);
CREATE INDEX IF NOT EXISTS idx_squad_members_email
    ON public.squad_members (email);

-- device_fingerprints (new)
CREATE INDEX IF NOT EXISTS idx_device_fingerprints_fingerprint
    ON public.device_fingerprints (fingerprint);
CREATE INDEX IF NOT EXISTS idx_device_fingerprints_user
    ON public.device_fingerprints (user_id);

-- order_share_events (new)
CREATE INDEX IF NOT EXISTS idx_order_share_events_user
    ON public.order_share_events (user_id, created_at DESC);

-- marketplace_requests (new)
CREATE INDEX IF NOT EXISTS idx_marketplace_requests_status
    ON public.marketplace_requests (status, created_at DESC);

-- webhook_events (new)
CREATE INDEX IF NOT EXISTS webhook_events_event_type_idx ON public.webhook_events (event_type);
CREATE INDEX IF NOT EXISTS webhook_events_reference_idx   ON public.webhook_events (reference);
CREATE INDEX IF NOT EXISTS webhook_events_created_at_idx  ON public.webhook_events (created_at DESC);

-- flash_redemptions (new)
CREATE INDEX IF NOT EXISTS flash_redemptions_reward_id_idx ON public.flash_redemptions (reward_id);
CREATE INDEX IF NOT EXISTS flash_redemptions_is_active_idx ON public.flash_redemptions (is_active)
  WHERE is_active = TRUE;

-- hp_bundle_purchases (new)
CREATE INDEX IF NOT EXISTS hp_bundle_purchases_event_host_id_idx ON public.hp_bundle_purchases (event_host_id);

-- banners (new)
CREATE INDEX IF NOT EXISTS idx_banners_active_placement
  ON public.banners (placement, sort_order)
  WHERE is_active = TRUE;

-- event_tickets unique index (must be in prior schema)
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_tickets_event_user
  ON event_tickets (event_id, user_id);


-- ============================================================
-- PHASE 6 — ENABLE RLS + POLICIES
-- ============================================================

-- gates
ALTER TABLE public.gates   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hostels ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all_gates"   ON public.gates;
DROP POLICY IF EXISTS "service_role_all_hostels" ON public.hostels;
CREATE POLICY "service_role_all_gates"   ON public.gates   FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "service_role_all_hostels" ON public.hostels FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "anon_read_gates"   ON public.gates;
DROP POLICY IF EXISTS "anon_read_hostels" ON public.hostels;
CREATE POLICY "anon_read_gates"   ON public.gates   FOR SELECT TO anon, authenticated USING (is_active = TRUE);
CREATE POLICY "anon_read_hostels" ON public.hostels FOR SELECT TO anon, authenticated USING (is_active = TRUE);

-- rider_profiles
ALTER TABLE public.rider_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Riders manage own profile" ON public.rider_profiles;
CREATE POLICY "Riders manage own profile"
    ON public.rider_profiles FOR ALL
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins manage all rider profiles" ON public.rider_profiles;
CREATE POLICY "Admins manage all rider profiles"
    ON public.rider_profiles FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- device_tokens
ALTER TABLE public.device_tokens ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users manage own device tokens" ON public.device_tokens;
CREATE POLICY "Users manage own device tokens"
    ON public.device_tokens FOR ALL
    USING (auth.uid() = user_id);

-- notification_preferences
ALTER TABLE public.notification_preferences ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users manage own notification preferences" ON public.notification_preferences;
CREATE POLICY "Users manage own notification preferences"
    ON public.notification_preferences FOR ALL
    USING (auth.uid() = user_id);

-- wallet_withdrawals
ALTER TABLE public.wallet_withdrawals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users view own withdrawals" ON public.wallet_withdrawals;
CREATE POLICY "Users view own withdrawals"
    ON public.wallet_withdrawals FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins manage all withdrawals" ON public.wallet_withdrawals;
CREATE POLICY "Admins manage all withdrawals"
    ON public.wallet_withdrawals FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- menu_addon_groups
ALTER TABLE public.menu_addon_groups ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view addon groups" ON public.menu_addon_groups;
CREATE POLICY "Anyone can view addon groups"
    ON public.menu_addon_groups FOR SELECT
    USING (true);

DROP POLICY IF EXISTS "Admins manage addon groups" ON public.menu_addon_groups;
CREATE POLICY "Admins manage addon groups"
    ON public.menu_addon_groups FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- order_addon_selections
ALTER TABLE public.order_addon_selections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins/kitchen manage addon selections" ON public.order_addon_selections;
CREATE POLICY "Admins/kitchen manage addon selections"
    ON public.order_addon_selections FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('admin', 'kitchen'))
    );

-- saved_for_later
ALTER TABLE public.saved_for_later ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users manage own saved items" ON public.saved_for_later;
CREATE POLICY "Users manage own saved items"
    ON public.saved_for_later FOR ALL
    USING (auth.uid() = user_id);

-- first_order_gifts
ALTER TABLE public.first_order_gifts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage first_order_gifts" ON public.first_order_gifts;
CREATE POLICY "Admins manage first_order_gifts"
    ON public.first_order_gifts FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

DROP POLICY IF EXISTS "Users view own gift" ON public.first_order_gifts;
CREATE POLICY "Users view own gift"
    ON public.first_order_gifts FOR SELECT
    USING (auth.uid() = user_id);

-- order_locks
ALTER TABLE public.order_locks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users manage own locks" ON public.order_locks;
CREATE POLICY "Users manage own locks"
    ON public.order_locks FOR ALL
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins manage all locks" ON public.order_locks;
CREATE POLICY "Admins manage all locks"
    ON public.order_locks FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- login_streaks
ALTER TABLE public.login_streaks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users view own streak" ON public.login_streaks;
CREATE POLICY "Users view own streak"
    ON public.login_streaks FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins manage streaks" ON public.login_streaks;
CREATE POLICY "Admins manage streaks"
    ON public.login_streaks FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- monthly_hp_tracker
ALTER TABLE public.monthly_hp_tracker ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users view own monthly tracker" ON public.monthly_hp_tracker;
CREATE POLICY "Users view own monthly tracker"
    ON public.monthly_hp_tracker FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins manage monthly trackers" ON public.monthly_hp_tracker;
CREATE POLICY "Admins manage monthly trackers"
    ON public.monthly_hp_tracker FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- squad_members
ALTER TABLE public.squad_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage squad members" ON public.squad_members;
CREATE POLICY "Admins manage squad members"
    ON public.squad_members FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

DROP POLICY IF EXISTS "Users view own squad entries" ON public.squad_members;
CREATE POLICY "Users view own squad entries"
    ON public.squad_members FOR SELECT
    USING (auth.uid() = user_id);

-- device_fingerprints
ALTER TABLE public.device_fingerprints ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage device fingerprints" ON public.device_fingerprints;
CREATE POLICY "Admins manage device fingerprints"
    ON public.device_fingerprints FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- system_settings
ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage system_settings" ON public.system_settings;
CREATE POLICY "Admins manage system_settings"
    ON public.system_settings FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

DROP POLICY IF EXISTS "Anyone can read system_settings" ON public.system_settings;
CREATE POLICY "Anyone can read system_settings"
    ON public.system_settings FOR SELECT
    USING (true);

-- order_share_events
ALTER TABLE public.order_share_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users view own share events" ON public.order_share_events;
CREATE POLICY "Users view own share events"
    ON public.order_share_events FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins manage share events" ON public.order_share_events;
CREATE POLICY "Admins manage share events"
    ON public.order_share_events FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- marketplace_requests
ALTER TABLE public.marketplace_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage marketplace requests" ON public.marketplace_requests;
CREATE POLICY "Admins manage marketplace requests"
    ON public.marketplace_requests FOR ALL
    USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- banners
ALTER TABLE public.banners ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_banners" ON public.banners;
CREATE POLICY "anon_read_banners"
  ON public.banners FOR SELECT TO anon, authenticated USING (is_active = TRUE);

DROP POLICY IF EXISTS "service_role_all_banners" ON public.banners;
CREATE POLICY "service_role_all_banners"
  ON public.banners FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "admins_manage_banners" ON public.banners;
CREATE POLICY "admins_manage_banners"
  ON public.banners FOR ALL
  USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
  );


-- ============================================================
-- PHASE 7 — CREATE OR REPLACE FUNCTION
-- ============================================================

-- ── 7.01 cron_lock helpers ────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS try_acquire_cron_lock(TEXT);
DROP FUNCTION IF EXISTS release_cron_lock(TEXT);

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

-- ── 7.02 checkin_event_atomic ─────────────────────────────────────────────────
--  Validates QR token = ticket UUID, prevents double check-in.
--  Requires: event_tickets, event_checkins (from prior schemas).
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
  SELECT id INTO v_ticket_id
  FROM   event_tickets
  WHERE  event_id = p_event_id
    AND  user_id  = p_user_id
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('error', 'No ticket found for this event');
  END IF;

  IF v_ticket_id::TEXT <> p_qr_token THEN
    RETURN jsonb_build_object('error', 'Invalid QR token');
  END IF;

  IF EXISTS (SELECT 1 FROM event_checkins WHERE ticket_id = v_ticket_id) THEN
    RETURN jsonb_build_object('error', 'Already checked in to this event');
  END IF;

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

-- ── 7.03 claim_guest_order ────────────────────────────────────────────────────
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

-- ── 7.04 register_for_event_atomic ────────────────────────────────────────────
--  Race-free event registration with capacity enforcement.
--  Requires: events, event_tickets (from prior schemas).
CREATE OR REPLACE FUNCTION register_for_event_atomic(
  p_event_id UUID,
  p_user_id  UUID
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_capacity  INTEGER;
  v_issued    INTEGER;
  v_ticket_id UUID;
  v_existing  UUID;
  v_status    TEXT;
BEGIN
  SELECT capacity INTO v_capacity
  FROM   events
  WHERE  id = p_event_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('error', 'Event not found');
  END IF;

  SELECT id, status INTO v_existing, v_status
  FROM   event_tickets
  WHERE  event_id = p_event_id
    AND  user_id  = p_user_id
  LIMIT 1;

  IF FOUND THEN
    RETURN jsonb_build_object(
      'ticket_id',          v_existing,
      'status',             v_status,
      'already_registered', TRUE
    );
  END IF;

  IF v_capacity IS NOT NULL THEN
    SELECT COUNT(*) INTO v_issued FROM event_tickets WHERE event_id = p_event_id;
    IF v_issued >= v_capacity THEN
      RETURN jsonb_build_object('error', 'Event is at full capacity');
    END IF;
  END IF;

  INSERT INTO event_tickets (event_id, user_id, status)
  VALUES (p_event_id, p_user_id, 'confirmed')
  RETURNING id INTO v_ticket_id;

  RETURN jsonb_build_object(
    'ticket_id',          v_ticket_id,
    'status',             'confirmed',
    'already_registered', FALSE
  );
END;
$$;


-- ============================================================
-- PHASE 8 — COMMENT ON
-- ============================================================

COMMENT ON TABLE  public.gates           IS 'Off-campus delivery exit gates. Fee = base_fee + (distance_km × rate_per_km), minimum min_fee.';
COMMENT ON TABLE  public.hostels         IS 'On-campus hostels with fixed per-hostel delivery fees.';
COMMENT ON TABLE  public.banners         IS 'Promotional banners shown on the storefront homepage carousel.';
COMMENT ON COLUMN public.banners.images  IS 'Optional JSONB array of image URLs for carousel slides. Falls back to single image_url when null.';
COMMENT ON TABLE  public.system_settings IS 'Global editable configuration key-value store. Edit values here to tune behaviour without a code deploy.';
COMMENT ON TABLE  public.monthly_hp_tracker IS 'Tracks monthly free-activity pending HP per user. Cap read from system_settings key monthly_pending_cap. Does NOT apply to food orders, referrals, or admin grants.';
COMMENT ON TABLE  public.order_locks     IS 'Users can lock-in a future order date to reserve a discount (up to 50%) or HP reward. One reschedule allowed. Auto-expires if missed.';
COMMENT ON TABLE  public.login_streaks   IS 'Per-user consecutive daily login streak. Incremented on new-day login; reset to 1 if more than 2 days missed in a week.';
COMMENT ON TABLE  public.squad_members   IS 'Participants in a squad order. hp_share = their portion of order HP (split evenly among registered accounts only).';
COMMENT ON TABLE  public.device_fingerprints IS 'Device/phone fingerprint hashes stored at signup to prevent duplicate account creation.';
COMMENT ON TABLE  public.order_share_events IS 'Records every order-confirmation social share to enforce the 1 HP reward per day guardrail.';
COMMENT ON TABLE  public.marketplace_requests IS 'Vendor listing requests submitted for admin review before becoming marketplace_listings.';
COMMENT ON TABLE  public.menu_addon_groups IS 'Add-on groups scoped to a single menu item (e.g. "Sides", "Sauces"). Addons with group_id = NULL remain global/flat add-ons.';
COMMENT ON COLUMN public.menu_addons.group_id IS 'FK to menu_addon_groups. NULL = legacy global add-on (not tied to a specific item/group).';
COMMENT ON TABLE  public.order_addon_selections IS 'Records which add-ons were selected for a specific order_item at checkout time.';
COMMENT ON COLUMN public.orders.is_squad_order         IS 'True when the cart qualified for a squad-order discount.';
COMMENT ON COLUMN public.orders.squad_discount_amount   IS 'Naira value discounted from the subtotal due to squad-order promotion (0 when not a squad order).';
COMMENT ON COLUMN public.orders.squad_item_count        IS 'Total non-addon item quantity used to determine squad eligibility.';
COMMENT ON COLUMN public.orders.claim_token             IS 'UUID token set on guest orders; used by POST /orders/:id/claim to link a guest order to a newly registered account.';
COMMENT ON COLUMN public.orders.is_scheduled            IS 'True when the customer scheduled this order for a future delivery window instead of ASAP delivery.';
COMMENT ON COLUMN public.orders.gift_included           IS 'TRUE when a launch-window hot dog gift was issued with this order.';
COMMENT ON COLUMN public.order_reviews.kitchen_rating   IS 'Optional 1-5 star rating for food quality and preparation speed.';
COMMENT ON COLUMN public.order_reviews.rider_rating     IS 'Optional 1-5 star rating for rider delivery speed and professionalism.';
COMMENT ON COLUMN public.profiles.jwt_version           IS 'Monotonically incrementing token-invalidation counter. Increment to revoke all existing JWTs for this user.';
COMMENT ON COLUMN public.profiles.last_activity_at      IS 'UTC timestamp of last qualifying activity. Used by decay-onset and win-back notification tasks.';
COMMENT ON COLUMN public.cart_items.added_at            IS 'When this item was first added to the cart. Used by the abandoned-cart notification task.';
COMMENT ON TABLE  public.first_order_gifts              IS 'Records users who earned the launch-window hot dog gift on their first completed order.';
COMMENT ON TABLE  public.saved_for_later                IS 'Items saved by a user for later — distinct from the active cart. Users can move items between saved and cart.';


-- ============================================================
-- PHASE 9 — INSERT seed data
-- ============================================================

-- hp_bundles default catalogue
INSERT INTO hp_bundles (name, hp_amount, price_naira, total_price, description, sort_order)
VALUES
  ('Starter Pack',  100,   500,   500,  '100 Holy Points — great for new members',    1),
  ('Value Pack',    300,  1400,  1400,  '300 Holy Points — best value for regulars',  2),
  ('Power Pack',    600,  2600,  2600,  '600 Holy Points — for champions',             3),
  ('Elite Pack',   1000,  4000,  4000,  '1000 Holy Points — maximum loyalty reward',  4)
ON CONFLICT DO NOTHING;

-- NOTE: Seed data for system_settings is in scripts/seed.sql (section 8).
-- Run scripts/seed.sql (or python scripts/seed.py) after this migration
-- to insert the default values for all configurable keys.
