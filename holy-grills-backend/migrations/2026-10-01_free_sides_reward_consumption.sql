-- ═══════════════════════════════════════════════════════════════════════════
--  test 2 only (zaxdkrmzyibkvlsrgmvq). Never apply to production untested.
--
--  Two atomic operations that Python currently half-does:
--    1. hg_consume_free_sides_atomic  — spend free-side credits at checkout
--    2. hg_claim_reward_redemption_for_order — attach a reward to an order once
--
--  Run in this order:
--      STEP 0  duplicate / shape checks   (read-only, run first — see below)
--      STEP 1  hg_consume_free_sides_atomic
--      STEP 2  hg_claim_reward_redemption_for_order
--      STEP 3  post-checks
--
--  Nothing here touches existing functions. hg_create_order_atomic is left
--  exactly as it is; both helpers are called by Python immediately after it
--  returns (see app/services/order_service.py).
-- ═══════════════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────────────
--  STEP 0 — run these first. Do not create anything until they come back clean.
-- ───────────────────────────────────────────────────────────────────────────
--
-- 0a. does a free-side consumer already exist? (you said no — re-confirm)
--
--     SELECT p.proname, pg_get_function_identity_arguments(p.oid)
--     FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--     WHERE n.nspname = 'public' AND p.proname ILIKE '%free_side%';
--
-- 0b. does a reward-claim function already exist?
--
--     SELECT p.proname, pg_get_function_identity_arguments(p.oid)
--     FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--     WHERE n.nspname = 'public' AND p.proname ILIKE '%redemption%';
--
-- 0c. columns this file depends on must exist with these names
--
--     SELECT table_name, column_name, data_type, is_nullable, column_default
--     FROM information_schema.columns
--     WHERE table_schema = 'public'
--       AND table_name IN ('free_side_credits','cart_free_side_selections',
--                          'free_side_items','order_items','reward_redemptions','orders')
--     ORDER BY table_name, ordinal_position;
--
--     Required to exist:
--       free_side_credits          id, user_id, campus_id, credits_remaining, expires_at, used_at
--       cart_free_side_selections  id, user_id, free_side_item_id, campus_id, created_at
--       free_side_items            id, name, campus_id, is_active
--       order_items                order_id, name_snapshot, quantity, price_snapshot,
--                                  line_total, is_addon
--       reward_redemptions         id, user_id, status, attached_order_id
--       orders                     redemption_id           (used in 0e / 3a)
--
-- 0d. has a reward already been reused? (evidence of the bug you described)
--
--     SELECT redemption_id, count(*) AS orders, array_agg(id) AS order_ids
--     FROM orders WHERE redemption_id IS NOT NULL
--     GROUP BY redemption_id HAVING count(*) > 1;
--
--     SELECT r.id, r.status, r.attached_order_id, o.redemption_id
--     FROM reward_redemptions r
--     LEFT JOIN orders o ON o.redemption_id = r.id
--     WHERE r.attached_order_id IS NOT NULL OR o.id IS NOT NULL
--     ORDER BY r.id;
--
-- 0e. ticket status values — RESOLVED, informational only.
--
--     Confirmed by the project owner: event_tickets.status is plain text with no
--     restrictive CHECK constraint, 'cancelled' is the word already in use, and
--     there is no cancellation_reason column.
--     Expired unpaid tickets are already cancelled by a DATABASE job that runs
--     every 15 minutes and releases the tier seat — this repo therefore ships NO
--     Python equivalent (a second job would race it). Only the registrant-email
--     filter lives in Python.


-- ───────────────────────────────────────────────────────────────────────────
--  STEP 1 — free sides: one credit out, one ₦0 order line in, selection gone.
--  Idempotent by construction: the selection row is deleted as it is consumed,
--  so a retry cannot double-spend.
-- ───────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.hg_consume_free_sides_atomic(
    p_user_id   uuid,
    p_order_id  uuid,
    p_campus_id uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_sel       record;
    v_credit_id uuid;
    v_item_name text;
    v_item_id   uuid;
    v_consumed  int  := 0;
    v_item_ids  uuid[] := '{}';
BEGIN
    IF p_user_id IS NULL OR p_order_id IS NULL THEN
        RETURN jsonb_build_object('consumed', 0, 'reason', 'missing user or order id');
    END IF;

    FOR v_sel IN
        SELECT id, free_side_item_id
        FROM cart_free_side_selections
        WHERE user_id = p_user_id
        ORDER BY created_at
    LOOP
        -- oldest-expiring usable credit first; SKIP LOCKED keeps two concurrent
        -- checkouts from fighting over the same credit row
        SELECT c.id INTO v_credit_id
        FROM free_side_credits c
        WHERE c.user_id = p_user_id
          AND c.credits_remaining > 0
          AND (c.expires_at IS NULL OR c.expires_at >= now())
          AND (p_campus_id IS NULL OR c.campus_id IS NULL OR c.campus_id = p_campus_id)
        ORDER BY c.expires_at NULLS LAST
        FOR UPDATE SKIP LOCKED
        LIMIT 1;

        IF v_credit_id IS NULL THEN
            CONTINUE;                     -- out of credits mid-checkout: leave the selection alone
        END IF;

        UPDATE free_side_credits
           SET credits_remaining = credits_remaining - 1,
               used_at = now()
         WHERE id = v_credit_id;

        SELECT name INTO v_item_name FROM free_side_items WHERE id = v_sel.free_side_item_id;

        INSERT INTO order_items (order_id, name_snapshot, quantity, price_snapshot, line_total, is_addon)
        VALUES (p_order_id, COALESCE(v_item_name, 'Free side'), 1, 0, 0, false)
        RETURNING id INTO v_item_id;

        DELETE FROM cart_free_side_selections WHERE id = v_sel.id;

        v_consumed := v_consumed + 1;
        v_item_ids := array_append(v_item_ids, v_item_id);
    END LOOP;

    RETURN jsonb_build_object('consumed', v_consumed, 'order_item_ids', to_jsonb(v_item_ids));
END;
$$;

REVOKE ALL ON FUNCTION public.hg_consume_free_sides_atomic(uuid, uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_consume_free_sides_atomic(uuid, uuid, uuid) TO service_role;


-- ───────────────────────────────────────────────────────────────────────────
--  STEP 2 — reward redemption: claim it for exactly one order.
--  First writer wins; every later call returns claimed = false.
-- ───────────────────────────────────────────────────────────────────────────
ALTER TABLE public.reward_redemptions
    ADD COLUMN IF NOT EXISTS used_at timestamptz;

CREATE INDEX IF NOT EXISTS ix_reward_redemptions_attached_order
    ON public.reward_redemptions (attached_order_id)
    WHERE attached_order_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.hg_claim_reward_redemption_for_order(
    p_redemption_id uuid,
    p_user_id       uuid,
    p_order_id      uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id uuid;
BEGIN
    IF p_redemption_id IS NULL OR p_user_id IS NULL OR p_order_id IS NULL THEN
        RETURN jsonb_build_object('claimed', false, 'reason', 'missing argument');
    END IF;

    UPDATE reward_redemptions
       SET attached_order_id = p_order_id,
           used_at = now()
     WHERE id = p_redemption_id
       AND user_id = p_user_id
       AND attached_order_id IS NULL          -- the guard: an attached reward is spent
       AND status = 'fulfilled'               -- only a fulfilled reward may ride an order
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        -- say *why*, without leaking another user's row
        RETURN jsonb_build_object(
            'claimed', false,
            'reason', (
                SELECT CASE
                    WHEN r.id IS NULL            THEN 'not_found_or_not_owner'
                    WHEN r.status <> 'fulfilled' THEN 'not_fulfilled'
                    WHEN r.attached_order_id IS NOT NULL THEN 'already_used'
                    ELSE 'not_claimable'
                END
                FROM reward_redemptions r
                WHERE r.id = p_redemption_id AND r.user_id = p_user_id
            )
        );
    END IF;

    RETURN jsonb_build_object('claimed', true, 'redemption_id', v_id);
END;
$$;

REVOKE ALL ON FUNCTION public.hg_claim_reward_redemption_for_order(uuid, uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_claim_reward_redemption_for_order(uuid, uuid, uuid) TO service_role;


-- ───────────────────────────────────────────────────────────────────────────
--  STEP 3 — post-checks
-- ───────────────────────────────────────────────────────────────────────────
--
-- 3a. both functions exist and are service-role only
--
--     SELECT p.proname, p.prosecdef, array_to_string(p.proconfig, ','),
--            has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_can_run,
--            has_function_privilege('authenticated', p.oid, 'EXECUTE') AS auth_can_run
--     FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--     WHERE n.nspname = 'public'
--       AND p.proname IN ('hg_consume_free_sides_atomic','hg_claim_reward_redemption_for_order');
--
--     Expect: prosecdef = true, proconfig = 'search_path=public, pg_temp',
--             anon_can_run = false, auth_can_run = false
--
-- 3b. after the next E2E order, a consumed free side looks like this
--
--     SELECT s.* FROM cart_free_side_selections s WHERE s.user_id = <user>;
--     SELECT c.credits_remaining, c.used_at FROM free_side_credits c WHERE c.user_id = <user>;
--     SELECT i.* FROM order_items i WHERE i.order_id = <order> AND i.price_snapshot = 0;
--
-- 3c. a reused reward is now impossible — this must return no rows
--
--     SELECT r.id, count(o.id)
--     FROM reward_redemptions r JOIN orders o ON o.redemption_id = r.id
--     GROUP BY r.id HAVING count(o.id) > 1;
