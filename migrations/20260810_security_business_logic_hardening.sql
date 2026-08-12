-- ── HOLY GRILLS SECURITY & BUSINESS LOGIC HARDENING MIGRATION ──────────────────
-- Version: 20260810_security_business_logic_hardening
-- Purpose: Hardens authentication, authorization, payments, and race conditions.

-- ── 1. System Settings Seed additions (idempotent) ───────────────────────────
-- NOTE: system_settings.value is JSONB in this database.
-- If the live table uses TEXT, please remove the ::jsonb casts.
INSERT INTO public.system_settings (key, value, description)
VALUES
(
    'order_lock_default_discount',
    '10'::jsonb,
    'Fixed discount percentage for order locks'
),
(
    'order_lock_default_hp',
    '100'::jsonb,
    'Fixed HP reward for order locks'
),
(
    'order_lock_max_hp',
    '1000'::jsonb,
    'Maximum allowed HP reward for order locks'
)
ON CONFLICT (key) DO UPDATE
SET
    value = EXCLUDED.value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- ── 2. Add payment reference idempotency to hp_bundle_purchases ─────────────
ALTER TABLE public.hp_bundle_purchases
ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'paystack',
ADD COLUMN IF NOT EXISTS provider_reference TEXT;

-- Safely add the UNIQUE constraint on (provider, provider_reference)
-- In PostgreSQL, UNIQUE constraints allow multiple NULLs, so this is safe for historic rows without a reference.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'hp_bundle_purchases_provider_ref_key'
    ) THEN
        ALTER TABLE public.hp_bundle_purchases
        ADD CONSTRAINT hp_bundle_purchases_provider_ref_key UNIQUE (provider, provider_reference);
    END IF;
END $$;

-- ── 3. Add unique business reference constraint to hp_transactions ───────────
-- This prevents duplicate awards (referrals, check-ins, reviews, spins, etc.) on DB level.
CREATE UNIQUE INDEX IF NOT EXISTS hp_transactions_unique_business_key_idx
ON public.hp_transactions (reference_type, reference_id)
WHERE reference_type IS NOT NULL AND reference_type <> ''
  AND reference_id IS NOT NULL AND reference_id <> '';

-- ── 4. Verify/Ensure record_hp_transaction_atomic RPC structure ──────────────
-- VERIFY IN SUPABASE BEFORE APPLYING
-- This RPC performs atomic mutations on profiles.hp_balance and inserts hp_transactions atomically.
-- If the RPC is already present and correct, do not overwrite it.
CREATE OR REPLACE FUNCTION public.record_hp_transaction_atomic(
    p_user_id UUID,
    p_amount INTEGER,
    p_type TEXT,
    p_status TEXT,
    p_source TEXT,
    p_reference_type TEXT,
    p_reference_id TEXT,
    p_issued_by_admin_id UUID DEFAULT NULL,
    p_notes TEXT DEFAULT NULL
) RETURNS JSON AS $$
DECLARE
    v_new_balance INTEGER;
    v_transaction_id UUID;
BEGIN
    -- Update profile hp_balance
    UPDATE public.profiles
    SET hp_balance = hp_balance + p_amount,
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING hp_balance INTO v_new_balance;

    IF NOT FOUND THEN
        RETURN json_build_object('error', 'User profile not found');
    END IF;

    -- Insert the hp_transaction
    INSERT INTO public.hp_transactions (
        user_id, amount, type, status, source, reference_type, reference_id, issued_by_admin_id, notes, created_at
    ) VALUES (
        p_user_id, p_amount, p_type, p_status, p_source, p_reference_type, p_reference_id, p_issued_by_admin_id, p_notes, NOW()
    ) RETURNING id INTO v_transaction_id;

    RETURN json_build_object(
        'success', true,
        'new_balance', v_new_balance,
        'transaction_id', v_transaction_id
    );
EXCEPTION WHEN UNIQUE_VIOLATION THEN
    -- If duplicate key on (reference_type, reference_id) occurs, abort and return error
    RETURN json_build_object('error', 'Duplicate transaction reference');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
