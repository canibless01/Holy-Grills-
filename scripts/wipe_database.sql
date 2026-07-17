-- ============================================================
--  Holy Grills FUTA — Full Database Wipe
--
--  Deletes EVERY row from EVERY table — including seed data.
--  After running this, execute scripts/seed.sql (or seed.py)
--  to restore the baseline seed data.
--
--  Run in Supabase SQL Editor.
--
--  Order: child tables first, then parents, then seed tables.
--  Auth users must be deleted separately via the Supabase
--  Auth dashboard or the admin API (they live outside PostgREST).
-- ============================================================

-- ── Order item children ───────────────────────────────────────────────────────
DELETE FROM public.order_addon_selections   WHERE TRUE;
DELETE FROM public.order_items              WHERE TRUE;
DELETE FROM public.order_status_logs        WHERE TRUE;
DELETE FROM public.order_reviews            WHERE TRUE;
DELETE FROM public.order_share_events       WHERE TRUE;
DELETE FROM public.squad_members            WHERE TRUE;

-- ── Orders ────────────────────────────────────────────────────────────────────
DELETE FROM public.orders                   WHERE TRUE;

-- ── HP & Wallet ───────────────────────────────────────────────────────────────
DELETE FROM public.hp_transactions          WHERE TRUE;
DELETE FROM public.wallet_transactions      WHERE TRUE;
DELETE FROM public.wallet_withdrawals       WHERE TRUE;
DELETE FROM public.wallets                  WHERE TRUE;
DELETE FROM public.monthly_hp_tracker       WHERE TRUE;
DELETE FROM public.hp_bundle_purchases      WHERE TRUE;

-- ── Notifications ─────────────────────────────────────────────────────────────
DELETE FROM public.notifications            WHERE TRUE;
DELETE FROM public.push_subscriptions       WHERE TRUE;
DELETE FROM public.notification_blasts      WHERE TRUE;
DELETE FROM public.notification_preferences WHERE TRUE;

-- ── Deliveries & Batches ──────────────────────────────────────────────────────
DELETE FROM public.delivery_batches         WHERE TRUE;

-- ── Cart & Saved ──────────────────────────────────────────────────────────────
DELETE FROM public.cart_items               WHERE TRUE;
DELETE FROM public.saved_for_later          WHERE TRUE;

-- ── Events & Marketplace ─────────────────────────────────────────────────────
DELETE FROM public.event_checkins           WHERE TRUE;
DELETE FROM public.event_tickets            WHERE TRUE;
DELETE FROM public.marketplace_purchases    WHERE TRUE;
DELETE FROM public.promo_code_uses          WHERE TRUE;

-- ── Feature Tables ────────────────────────────────────────────────────────────
DELETE FROM public.order_locks              WHERE TRUE;
DELETE FROM public.login_streaks            WHERE TRUE;
DELETE FROM public.reward_redemptions       WHERE TRUE;
DELETE FROM public.first_order_gifts        WHERE TRUE;
DELETE FROM public.referrals                WHERE TRUE;
DELETE FROM public.device_fingerprints      WHERE TRUE;
DELETE FROM public.device_tokens            WHERE TRUE;
DELETE FROM public.rider_profiles           WHERE TRUE;
DELETE FROM public.flash_redemptions        WHERE TRUE;
DELETE FROM public.webhook_events           WHERE TRUE;
DELETE FROM public.cron_locks               WHERE TRUE;

-- ── Profiles (must come after all FK children above) ─────────────────────────
DELETE FROM public.profiles                 WHERE TRUE;

-- ── Seed / Config tables ──────────────────────────────────────────────────────
DELETE FROM public.hostels                  WHERE TRUE;
DELETE FROM public.gates                    WHERE TRUE;
DELETE FROM public.promo_codes              WHERE TRUE;
DELETE FROM public.delivery_windows         WHERE TRUE;
DELETE FROM public.storefront_sections      WHERE TRUE;
DELETE FROM public.operating_hours          WHERE TRUE;
DELETE FROM public.menu_addon_groups        WHERE TRUE;
DELETE FROM public.menu_addons              WHERE TRUE;
DELETE FROM public.menu_items               WHERE TRUE;
DELETE FROM public.menu_categories          WHERE TRUE;
DELETE FROM public.kitchen_settings         WHERE TRUE;
DELETE FROM public.system_settings         WHERE TRUE;
DELETE FROM public.hp_bundles               WHERE TRUE;
DELETE FROM public.hp_tiers                 WHERE TRUE;

-- ── Marketplace listings/requests (if they exist) ────────────────────────────
DELETE FROM public.marketplace_requests     WHERE TRUE;
DELETE FROM public.marketplace_listings     WHERE TRUE;

-- ── Rewards & Challenges ──────────────────────────────────────────────────────
DELETE FROM public.challenges               WHERE TRUE;
DELETE FROM public.rewards                  WHERE TRUE;
DELETE FROM public.events                   WHERE TRUE;

-- ============================================================
-- After running this file, restore seed data with:
--   Supabase SQL Editor → run scripts/seed.sql
-- OR:
--   python scripts/seed.py
--
-- Auth users must be deleted separately:
--   Supabase Dashboard → Authentication → Users → delete all
-- OR via the Supabase admin API (see scripts/wipe_test_data.py).
-- ============================================================
