-- ═══════════════════════════════════════════════════════════════════════════
--  SEED system_settings — the business values the app reads (2026-10-04)
--
--  HOW TO RUN
--    Supabase dashboard → SQL Editor → paste this whole file → Run.
--    Safe by design:
--      • idempotent — a key is inserted only when it has no global row yet, so
--        running it twice changes nothing;
--      • non-destructive — an existing row (the admin's live value) is skipped,
--        never overwritten;
--      • column-aware — it reads the real column list/types of system_settings
--        and writes only what exists (value as jsonb or text, whichever this
--        project uses) instead of assuming a schema.
--    It ends with a NOTICE listing what it inserted and what it skipped, plus a
--    verify query in the comments. Values in the table below are written as JSON
--    literals (100, true, [..], "08:00") so the same file is correct whether the
--    project stores system_settings.value as jsonb or as text.
--
--  WHAT IT SEEDS
--    Global rows only (campus_id IS NULL) — per-campus overrides are the admin
--    UI's job, and the backend reads campus row → global row → env.
--
--    SECTION 1 — the backend reads this exact key today. Seeding is a no-op
--                until an admin edits the value; after that, the edit takes
--                effect with no deploy on both sides.
--    SECTION 2 — the frontend reads the key today; the backend still resolves
--                the same value from env config, and the value seeded here is
--                that exact default. Nothing moves today; the row exists so the
--                admin screen and the frontend already agree, and so wiring the
--                backend (docs/SETTINGS.md) is a one-liner later.
--
--  WHAT IT DOES NOT SEED (and why)
--    ✘ secrets — Supabase keys, Paystack/Cloudinary/Resend/OneSignal secrets,
--      SECRET_KEY: env only, never in a readable table.
--    ✘ infrastructure / boot-time — CORS origins, port, log level, database URL,
--      APP_ENV: read before a request (and sometimes before a DB) exists.
--    ✘ everything in the NEEDS-A-DECISION list at the bottom of this file.
--
--  is_public = true on every row here: each of these values already ships inside
--  the frontend JS bundle, so publishing them from the table discloses nothing
--  that a visitor cannot read in the bundle today.
-- ═══════════════════════════════════════════════════════════════════════════

DO $$
DECLARE
  r            record;
  v_type       text;          -- data type of system_settings.value
  v_as_json    boolean;
  v_cols       text;          -- insert column list, built to match the table
  v_vals       text;          -- ...and the values, in that same order
  v_seeded     text[] := '{}';
  v_skipped    text[] := '{}';
  v_existing   boolean;
  has_desc     boolean;
  has_campus   boolean;
  has_public   boolean;
  has_upd_at   boolean;
  has_upd_by   boolean;
BEGIN
  IF to_regclass('public.system_settings') IS NULL THEN
    RAISE EXCEPTION 'public.system_settings does not exist — nothing seeded';
  END IF;

  SELECT data_type INTO v_type
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'system_settings' AND column_name = 'value';
  IF v_type IS NULL THEN
    RAISE EXCEPTION 'system_settings.value column not found — nothing seeded';
  END IF;
  v_as_json := v_type IN ('json', 'jsonb');

  -- Write only the columns this project's table actually has. The column list
  -- and the value list are built together, in the same order, on purpose.
  SELECT count(*) FILTER (WHERE column_name = 'description') > 0,
         count(*) FILTER (WHERE column_name = 'campus_id')   > 0,
         count(*) FILTER (WHERE column_name = 'is_public')   > 0,
         count(*) FILTER (WHERE column_name = 'updated_at')  > 0,
         count(*) FILTER (WHERE column_name = 'updated_by')  > 0
    INTO has_desc, has_campus, has_public, has_upd_at, has_upd_by
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'system_settings';

  v_cols := 'key, value';
  IF has_desc    THEN v_cols := v_cols || ', description'; END IF;
  IF has_campus  THEN v_cols := v_cols || ', campus_id';   END IF;
  IF has_public  THEN v_cols := v_cols || ', is_public';   END IF;
  IF has_upd_at  THEN v_cols := v_cols || ', updated_at';  END IF;
  IF has_upd_by  THEN v_cols := v_cols || ', updated_by';  END IF;

  -- The existence check is the only other place that names a column, so it
  -- follows the same has-column flags.
  FOR r IN
    SELECT * FROM (VALUES
      -- ── SECTION 1 — backend reads this key today ───────────────────────────
      -- (key, value, description; comments name the backend reader)
      ('1', 'squad_order_min_items',        '3',      'Distinct item lines that make one order a squad order — order_service (settings → SQUAD_ORDER_MIN_ITEMS)'),
      ('1', 'squad_order_max_items',        '6',      'Maximum item lines the cart lets one squad order carry — order_service (settings → SQUAD_ORDER_MAX_ITEMS)'),
      ('1', 'squad_delivery_discount_enabled', 'true', 'Waive part of the delivery fee on squad orders — order_service (settings → SQUAD_DELIVERY_DISCOUNT_ENABLED)'),
      ('1', 'squad_delivery_discount_pct',  '100',    'Percentage of the delivery fee waived on squad orders (0-100) — order_service'),
      ('1', 'squad_order_discount_enabled', 'false',  'Percentage discount on the squad-order subtotal — order_service (settings → SQUAD_ORDER_DISCOUNT_ENABLED)'),
      ('1', 'squad_order_discount_pct',     '10',     'Subtotal discount percentage when the squad subtotal discount is on (0-100) — order_service'),
      ('1', 'order_lock_max_reschedules',   '1',      'How many times a customer may reschedule a locked order (0-10) — order_locks'),
      ('1', 'order_lock_default_discount_pct', '10',  'Default goodwill discount applied on an order lock (0-50) — order_locks'),
      ('1', 'wallet_min_card_topup',        '100',    'Smallest naira amount accepted for a card wallet top-up — wallet'),
      ('1', 'free_side_credits_validity_days', '60',   'Days a free-side credit stays usable before it expires — free_sides, tasks/scheduled'),
      ('1', 'exclusive_spin_validity_days', '30',     'Days an exclusive spin prize stays claimable — admin, tasks/scheduled'),
      ('1', 'hp_multiplier',                '1.0',    'Global event multiplier on HP earned (1.0 = no event) — hp_service; admin UI broadcasts on change'),
      ('1', 'monthly_pending_cap',          '1000',   'Monthly cap on pending (activity-earned) HP per user — streak_service'),
      ('1', 'welcome_bonus_hp',             '50',     'HP granted once on first login/registration — hp_service'),
      ('1', 'signup_bonus_hp',              '0',      'HP granted at account creation; 0 = off — hp_service'),
      ('1', 'review_hp',                    '20',     'HP for leaving a verified order review — orders'),
      ('1', 'share_prompt_hp',              '25',     'HP for sharing an order from the confirmation screen — orders'),
      ('1', 'hp_transfer_min_orders',       '3',      'Orders a user must have completed before sending HP — hp'),
      ('1', 'graduation_min_level',         '500',    'Level a student must reach to be graduation-eligible — graduation'),

      -- ── SECTION 2 — frontend reads the key today. Where the backend resolves the
      --    same value from env config, the value below is that env default, so
      --    nothing moves yet. FOUR of these are already read back through
      --    setting_or_config, so editing them takes effect without a deploy:
      --      event_checkin_hp · wallet_topup_hp · marketplace_purchase_hp ·
      --      low_code_inventory_threshold
      --    The rest are the frontend's copy of an env value until they are wired
      --    the same way (see SETTINGS.md → leftovers).
      ('2', 'hp_per_naira_food',            '0.1',    'HP earned per ₦1 of food spend — HP_PER_NAIRA_FOOD'),
      ('2', 'hp_unlock_rate_pct',           '0.3',    'Share of earned HP unlocked immediately vs pending (0-1) — HP_UNLOCK_RATE_PCT'),
      ('2', 'referral_hp',                  '75',     'HP awarded when a referred friend completes their first order — REFERRAL_HP'),
      ('2', 'event_checkin_hp',             '40',     'HP for checking in at a campus event — EVENT_CHECKIN_HP'),
      ('2', 'wallet_topup_hp',              '50',     'HP awarded on a qualifying wallet top-up — WALLET_TOPUP_HP'),
      ('2', 'wallet_topup_min',             '3000',   'Minimum wallet top-up that earns HP — WALLET_TOPUP_MIN'),
      ('2', 'hp_transfer_min_amount',       '10',     'Smallest HP amount a user may transfer — HP_TRANSFER_MIN_AMOUNT'),
      ('2', 'marketplace_purchase_hp',      '50',     'HP cost of a standard marketplace redemption — MARKETPLACE_PURCHASE_HP'),
      ('2', 'low_code_inventory_threshold', '5',      'Remaining stock at which the kitchen sees a low-inventory warning — LOW_CODE_INVENTORY_THRESHOLD'),
      ('2', 'flash_discount_pct',           '0.5',    'Discount applied to flash redemptions (0-1) — FLASH_DISCOUNT_PCT'),
      ('2', 'flash_max_qty',                '5',      'Maximum quantity per flash redemption — FLASH_MAX_QTY'),
      ('2', 'hp_bundle_price_per_hp',       '5',      'Naira price of one HP when an event host buys a bundle — HP_BUNDLE_PRICE_PER_HP'),
      ('2', 'hp_bundle_min_purchase',       '100',    'Smallest HP amount an event host may buy — HP_BUNDLE_MIN_PURCHASE'),
      ('2', 'hp_bundles',                   '[{"hp":100,"label":"Starter"},{"hp":250,"label":"Basic"},{"hp":500,"label":"Standard"},{"hp":1000,"label":"Premium"},{"hp":2500,"label":"Elite"}]', 'Bundle tiers offered to event hosts — HP_BUNDLES'),
      ('2', 'notification_gap_minutes',     '30',     'Minimum minutes between two notifications of the same type — NOTIFICATION_GAP_MINUTES'),
      ('2', 'notification_daily_cap',       '20',     'Maximum notifications one user receives per day — NOTIFICATION_DAILY_CAP'),
      ('2', 'ordering_window_open_time',    '"08:00"',  'Time orders open (campus local time, HH:MM) — ORDERING_WINDOW_OPEN_TIME'),
      ('2', 'ordering_window_close_time',   '"16:00"',  'Time orders close (campus local time, HH:MM) — ORDERING_WINDOW_CLOSE_TIME'),
      ('2', 'free_side_options',            '["Fries","Coleslaw","Plantain","Gizzard"]', 'Free-side choices offered when a credit is redeemed — FREE_SIDE_OPTIONS'),
      ('2', 'login_streak_rewards',         '{"1":25,"2":40,"3":60,"4+":80}', 'HP per completed streak week — LOGIN_STREAK_WEEK1..4_HP / login_streak_rewards table'),
      ('2', 'paystack_preferred_bank',      '"wema-bank"', 'Virtual-account bank code shown at top-up — PAYSTACK_PREFERRED_BANK'),
      ('2', 'app_name',                     '"Holy Grills"', 'Product name used in copy and receipts — APP_NAME'),
      ('2', 'hp_currency_name',             '"HP"',     'What the loyalty currency is called in copy — HP_CURRENCY_NAME'),
      ('2', 'wallet_ref_prefix',            '"HG-WALLET-"', 'Prefix on generated wallet transaction references — WALLET_REF_PREFIX')
    ) AS t(section, key, value, description)
  LOOP
    IF has_campus THEN
      EXECUTE format('SELECT EXISTS (SELECT 1 FROM public.system_settings s WHERE s.key = %L AND s.campus_id IS NULL)', r.key)
        INTO v_existing;
    ELSE
      EXECUTE format('SELECT EXISTS (SELECT 1 FROM public.system_settings s WHERE s.key = %L)', r.key)
        INTO v_existing;
    END IF;

    IF v_existing THEN
      v_skipped := v_skipped || r.key;
      CONTINUE;
    END IF;

    -- Values above are JSON literals. A jsonb/json value column takes them
    -- verbatim (so 100 is a number, true is a boolean, [...] is an array); a
    -- text column gets the JSON quotes stripped off plain strings, so it stores
    -- '08:00', not '"08:00"'. (No seeded value contains a double quote — that is
    -- the one assumption this text fallback makes.)
    v_vals := format('%L, %s', r.key,
                     CASE WHEN v_as_json THEN format('%L::jsonb', r.value)
                          ELSE format('%L', CASE WHEN r.value ~ '^".*"$'
                                                 THEN btrim(r.value, '"')
                                                 ELSE r.value END) END);

    IF has_desc   THEN v_vals := v_vals || format(', %L', r.description); END IF;
    IF has_campus THEN v_vals := v_vals || ', NULL';   END IF;
    IF has_public THEN v_vals := v_vals || ', TRUE';   END IF;
    IF has_upd_at THEN v_vals := v_vals || ', now()';  END IF;
    IF has_upd_by THEN v_vals := v_vals || ', NULL';   END IF;

    EXECUTE format('INSERT INTO public.system_settings (%s) VALUES (%s)', v_cols, v_vals);
    v_seeded := v_seeded || r.key;
  END LOOP;

  RAISE NOTICE 'seed_system_settings: inserted % row(s): %',
               coalesce(array_length(v_seeded, 1), 0), coalesce(array_to_string(v_seeded, ', '), '(none)');
  RAISE NOTICE 'seed_system_settings: skipped % key(s) that already had a global row: %',
               coalesce(array_length(v_skipped, 1), 0), coalesce(array_to_string(v_skipped, ', '), '(none)');
END $$;


-- ───────────────────────────────────────────────────────────────────────────
--  Verify (run after the block above)
--
--    SELECT key, value, is_public, updated_at
--      FROM public.system_settings
--     WHERE campus_id IS NULL
--     ORDER BY key;
--
--  A per-campus override, for when a campus runs a different number
--  (only this campus's admin or a super admin may write it — same rule as the
--  admin screen; the backend reads campus row → global row → env):
--
--    INSERT INTO public.system_settings (key, value, campus_id, is_public, updated_at)
--    VALUES ('squad_order_min_items', '4', '<CAMPUS_ID>', TRUE, now());
--
--  Rollback for the rows this file inserted (only if you want the env defaults
--  back — per-campus rows and other keys are untouched):
--
--    DELETE FROM public.system_settings
--     WHERE campus_id IS NULL
--       AND key IN ( 'squad_order_min_items', 'squad_order_max_items',
--         'squad_delivery_discount_enabled', 'squad_delivery_discount_pct',
--         'squad_order_discount_enabled', 'squad_order_discount_pct',
--         'order_lock_max_reschedules', 'order_lock_default_discount_pct',
--         'wallet_min_card_topup', 'free_side_credits_validity_days',
--         'exclusive_spin_validity_days', 'hp_multiplier', 'monthly_pending_cap',
--         'welcome_bonus_hp', 'signup_bonus_hp', 'review_hp', 'share_prompt_hp',
--         'hp_transfer_min_orders', 'graduation_min_level' );
--
--
-- ───────────────────────────────────────────────────────────────────────────
--  NEEDS A DECISION — deliberately NOT seeded, one line each.
--  (These are frontend-visible keys with no backend reader, or readers that
--   disagree. Seeding them would create a value an edit cannot move.)
--
--   birthday_hp (frontend 150)            the grant comes from the tier perks
--                                         (tiers table, 100-250 by tier); a
--                                         settings row would be a third source.
--   graduation_hp (frontend 1000)         the backend grant is not read from
--                                         settings; graduation_min_level (seeded
--                                         above) is the real gate.
--   daily_checkin_hp (frontend 5)         LOGIN_STREAK_HP exists in config but
--                                         nothing reads it; the streak award is
--                                         login_streak_rewards.
--   streak_cycle_days (frontend 7)        the 7-day streak cycle is in code.
--   signup_bonus_enabled (frontend false) implied by signup_bonus_hp > 0 (seeded);
--                                         a second switch is a second source.
--   wallet_min_withdrawal (frontend 1000) no withdrawal endpoint exists — nothing
--                                         to align yet.
--   order_lock_max_discount_pct (50)      dead on both sides: the real bound is
--                                         the 1-50 validation in order_locks.py.
--   multiplier_expires_at                 written by the admin HP-multiplier
--                                         screen, not a seeded constant.
--   daily_order_capacity / window_capacity live in kitchen_settings (per campus),
--                                         not system_settings — the admin capacity
--                                         screen writes them there.
--   first_order_gift_enabled / _item_name / launch_window_end_date
--                                         the gift service defaults to FALSE when
--                                         no row exists while FIRST_ORDER_GIFT_ENABLED
--                                         defaults to true — a real conflict to
--                                         settle before enabling the gift.
--
--  Feature flags (leaderboard_prizes, free_side_credits, hp_transfer, ...) are
--  NOT system_settings rows — they live in the feature_flags table and are
--  toggled from the admin Feature Flags screen. Seed that table separately if it
--  is ever empty.
-- ───────────────────────────────────────────────────────────────────────────
