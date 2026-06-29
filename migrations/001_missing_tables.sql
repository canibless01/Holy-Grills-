-- ============================================================
-- Holy Grills — Missing Tables Migration
-- Run this once in the Supabase SQL editor (Dashboard → SQL)
-- These tables are referenced by the API but not yet in prod.
-- ============================================================

-- 1. rider_profiles
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
