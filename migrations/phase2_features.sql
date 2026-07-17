-- ============================================================
--  Holy Grills — Phase 2 Feature Migration
--  Run in Supabase SQL Editor.
--  All statements are idempotent (IF NOT EXISTS / OR REPLACE).
--  Run this AFTER the existing schema.sql is applied.
--
--  SECTIONS:
--   1.  milestones table (unified challenges + badges engine)
--   2.  user_milestones table (completion tracking)
--   3.  referral_milestones table (DB-driven, admin-editable)
--   4.  membership_rewards table (anniversary HP, admin-editable)
--   5.  order_streaks table (separate order streak counter)
--   6.  order_streak_rewards table (admin-configurable rewards)
--   7.  login_streak_rewards table (admin-configurable weekly HP)
--   8.  login_streaks new columns (week-based cycle tracking)
--   9.  notification_log table (throttling)
--   10. scheduled_notifications table
--   11. hall_of_fame_inductees table
--   12. profiles new columns (graduation_claimed, top4_finish_count)
--   13. order_locks new columns (reward_type, reward_hp_amount)
--   14. orders new column (squad_name)
--   15. events new columns (paid events, funding_source, etc.)
--   16. marketplace_listings new columns (cash_price, total_value)
--   17. system_settings seed additions
-- ============================================================


-- ────────────────────────────────────────────────────────────
--  1. milestones table
--     Unified engine for both badges (time_window IS NULL)
--     and challenges (time_window IN ('weekly','monthly')).
--     trigger_type drives verification logic in the app.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.milestones (
    id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    title         TEXT    NOT NULL,
    description   TEXT,
    trigger_type  TEXT    NOT NULL,
    -- Lifetime badges: first_order, first_review, first_referral, first_event,
    --   first_squad, first_hp_gift_sent, graduation, birthday, social_follow,
    --   membership_months, hp_earned_total
    -- Recurring challenges: referral_count, order_count, review_count,
    --   event_checkins, squad_orders, order_streak_weeks, login_streak_cycles
    -- Admin-only: department_leader, faculty_leader
    trigger_value INTEGER NOT NULL DEFAULT 1,   -- target count/amount needed
    hp_awarded    INTEGER NOT NULL DEFAULT 0,
    time_window   TEXT    CHECK (time_window IN ('weekly', 'monthly')),  -- NULL = lifetime badge
    icon_won      TEXT,   -- URL/key; badge won't be awarded without this
    icon_locked   TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_by    UUID    REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_milestones_trigger_type
    ON public.milestones (trigger_type, is_active);

ALTER TABLE public.milestones ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view active milestones" ON public.milestones;
CREATE POLICY "Anyone can view active milestones"
    ON public.milestones FOR SELECT USING (is_active = TRUE);

DROP POLICY IF EXISTS "Admins manage milestones" ON public.milestones;
CREATE POLICY "Admins manage milestones"
    ON public.milestones FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

COMMENT ON TABLE public.milestones IS 'Unified table for badges (time_window IS NULL) and challenges (time_window set). trigger_type drives verification logic.';


-- ────────────────────────────────────────────────────────────
--  1b. milestones: social_link column
--      social_follow milestones carry a URL so clients can
--      navigate the user to the social page without hardcoding
--      the URL in the frontend.
-- ────────────────────────────────────────────────────────────
ALTER TABLE public.milestones
    ADD COLUMN IF NOT EXISTS social_link TEXT DEFAULT NULL;

COMMENT ON COLUMN public.milestones.social_link IS 'Optional URL for social_follow milestones — the social page the user should follow. Returned by the API so clients need not hardcode it.';


-- ────────────────────────────────────────────────────────────
--  2. user_milestones table
--     Tracks which milestones each user has completed/earned.
--     period_key used for recurring: 'YYYY-WW' or 'YYYY-MM'.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_milestones (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    milestone_id UUID        NOT NULL REFERENCES public.milestones(id) ON DELETE CASCADE,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    hp_awarded   INTEGER     NOT NULL DEFAULT 0,
    period_key   TEXT        DEFAULT NULL   -- NULL for lifetime badges
);

-- For lifetime badges: one completion per user per milestone (period_key IS NULL).
-- For recurring: one per user per milestone per period.
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_milestones_lifetime
    ON public.user_milestones (user_id, milestone_id)
    WHERE period_key IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_milestones_recurring
    ON public.user_milestones (user_id, milestone_id, period_key)
    WHERE period_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_milestones_user
    ON public.user_milestones (user_id, completed_at DESC);

ALTER TABLE public.user_milestones ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users view own milestones" ON public.user_milestones;
CREATE POLICY "Users view own milestones"
    ON public.user_milestones FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins manage user_milestones" ON public.user_milestones;
CREATE POLICY "Admins manage user_milestones"
    ON public.user_milestones FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));


-- ────────────────────────────────────────────────────────────
--  3. referral_milestones table
--     DB-driven referral milestone rewards. Replaces hardcoded
--     values. Admin can edit HP amounts here without a deploy.
--     is_repeating = TRUE for the open-ended "+25 → 1500" rule.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.referral_milestones (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_count  INTEGER NOT NULL,
    hp_awarded      INTEGER NOT NULL,
    is_repeating    BOOLEAN NOT NULL DEFAULT FALSE,  -- repeats every repeat_interval after this count
    repeat_interval INTEGER DEFAULT NULL,             -- NULL unless is_repeating = TRUE
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_milestones_count
    ON public.referral_milestones (referral_count)
    WHERE NOT is_repeating;

INSERT INTO public.referral_milestones (referral_count, hp_awarded, is_repeating, repeat_interval) VALUES
    (5,  150,  FALSE, NULL),
    (10, 400,  FALSE, NULL),
    (20, 750,  FALSE, NULL),
    (30, 1200, FALSE, NULL),
    (50, 2500, FALSE, NULL),
    (75, 1500, TRUE,  25)   -- every 25 referrals after 50 → 1500 HP
ON CONFLICT DO NOTHING;

ALTER TABLE public.referral_milestones ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage referral_milestones" ON public.referral_milestones;
CREATE POLICY "Admins manage referral_milestones"
    ON public.referral_milestones FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

DROP POLICY IF EXISTS "Anyone reads referral_milestones" ON public.referral_milestones;
CREATE POLICY "Anyone reads referral_milestones"
    ON public.referral_milestones FOR SELECT USING (TRUE);


-- ────────────────────────────────────────────────────────────
--  4. membership_rewards table
--     Admin-editable anniversary HP milestones.
--     trigger_type = 'membership_months' in milestones engine.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.membership_rewards (
    id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    months     INTEGER NOT NULL,
    hp_awarded INTEGER NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_rewards_months
    ON public.membership_rewards (months);

INSERT INTO public.membership_rewards (months, hp_awarded) VALUES
    (3,  100),
    (6,  200),
    (12, 500),
    (24, 750),
    (36, 1000),
    (48, 1250),
    (60, 1500)
ON CONFLICT DO NOTHING;

ALTER TABLE public.membership_rewards ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage membership_rewards" ON public.membership_rewards;
CREATE POLICY "Admins manage membership_rewards"
    ON public.membership_rewards FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

DROP POLICY IF EXISTS "Anyone reads membership_rewards" ON public.membership_rewards;
CREATE POLICY "Anyone reads membership_rewards"
    ON public.membership_rewards FOR SELECT USING (TRUE);


-- ────────────────────────────────────────────────────────────
--  5. order_streaks table
--     Tracks consecutive weekly order streaks per user.
--     Completely independent of login_streaks.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.order_streaks (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID    NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    streak_weeks    INTEGER NOT NULL DEFAULT 0 CHECK (streak_weeks >= 0),
    longest_streak  INTEGER NOT NULL DEFAULT 0,
    last_order_week TEXT    DEFAULT NULL,   -- 'YYYY-WW' format (ISO week)
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_order_streaks_user
    ON public.order_streaks (user_id);

ALTER TABLE public.order_streaks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users view own order streak" ON public.order_streaks;
CREATE POLICY "Users view own order streak"
    ON public.order_streaks FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins manage order_streaks" ON public.order_streaks;
CREATE POLICY "Admins manage order_streaks"
    ON public.order_streaks FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));


-- ────────────────────────────────────────────────────────────
--  6. order_streak_rewards table
--     Admin-configurable HP rewards at streak milestones.
--     Checked after each week count increment.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.order_streak_rewards (
    id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    weeks      INTEGER NOT NULL,
    hp_awarded INTEGER NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_order_streak_rewards_weeks
    ON public.order_streak_rewards (weeks);

INSERT INTO public.order_streak_rewards (weeks, hp_awarded) VALUES
    (1,  10),
    (2,  20),
    (4,  50),
    (8,  100),
    (12, 200),
    (24, 500)
ON CONFLICT DO NOTHING;

ALTER TABLE public.order_streak_rewards ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage order_streak_rewards" ON public.order_streak_rewards;
CREATE POLICY "Admins manage order_streak_rewards"
    ON public.order_streak_rewards FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

DROP POLICY IF EXISTS "Anyone reads order_streak_rewards" ON public.order_streak_rewards;
CREATE POLICY "Anyone reads order_streak_rewards"
    ON public.order_streak_rewards FOR SELECT USING (TRUE);


-- ────────────────────────────────────────────────────────────
--  7. login_streak_rewards table
--     HP awarded on completing each week of the check-in cycle.
--     Week 4+ uses the week_number=4 row (no higher rows needed).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.login_streak_rewards (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    week_number INTEGER NOT NULL,   -- 1=first week, 2=second, 3=third, 4=fourth+
    hp_awarded  INTEGER NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_login_streak_rewards_week
    ON public.login_streak_rewards (week_number);

INSERT INTO public.login_streak_rewards (week_number, hp_awarded) VALUES
    (1, 25),
    (2, 40),
    (3, 60),
    (4, 80)
ON CONFLICT DO NOTHING;

ALTER TABLE public.login_streak_rewards ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage login_streak_rewards" ON public.login_streak_rewards;
CREATE POLICY "Admins manage login_streak_rewards"
    ON public.login_streak_rewards FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

DROP POLICY IF EXISTS "Anyone reads login_streak_rewards" ON public.login_streak_rewards;
CREATE POLICY "Anyone reads login_streak_rewards"
    ON public.login_streak_rewards FOR SELECT USING (TRUE);


-- ────────────────────────────────────────────────────────────
--  8. login_streaks new columns
--     Week-based cycle tracking for the rebuilt check-in streak.
-- ────────────────────────────────────────────────────────────
ALTER TABLE public.login_streaks
    ADD COLUMN IF NOT EXISTS current_week_start    DATE    DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS week_state            JSONB   NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS cycle_week_number     INTEGER NOT NULL DEFAULT 1 CHECK (cycle_week_number >= 1),
    ADD COLUMN IF NOT EXISTS consecutive_weeks     INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_weeks >= 0);

COMMENT ON COLUMN public.login_streaks.current_week_start IS 'Monday of the current check-in week. NULL = no active cycle.';
COMMENT ON COLUMN public.login_streaks.week_state IS 'JSONB map: {"0":"checked","1":"missed","2":"reclaimed"} day offsets from current_week_start.';
COMMENT ON COLUMN public.login_streaks.cycle_week_number IS 'Which week of the streak cycle we are on (resets to 1 on cycle failure).';
COMMENT ON COLUMN public.login_streaks.consecutive_weeks IS 'Consecutive completed weeks in the current cycle run.';


-- ────────────────────────────────────────────────────────────
--  9. notification_log table
--     Per-user, per-type log for throttle enforcement.
--     Enforces: daily cap, 6-hour gap between non-critical.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.notification_log (
    id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    type    TEXT        NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notification_log_user_sent
    ON public.notification_log (user_id, sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_log_user_type
    ON public.notification_log (user_id, type, sent_at DESC);

ALTER TABLE public.notification_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage notification_log" ON public.notification_log;
CREATE POLICY "Admins manage notification_log"
    ON public.notification_log FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));


-- ────────────────────────────────────────────────────────────
--  10. scheduled_notifications table
--      Admin-configured recurring or one-time push campaigns.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.scheduled_notifications (
    id             UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    title          TEXT    NOT NULL,
    body           TEXT    NOT NULL,
    frequency      TEXT    NOT NULL CHECK (frequency IN ('daily', 'weekly', 'once')),
    send_time      TEXT    NOT NULL,   -- 'HH:MM' in WAT (UTC+1)
    target_segment TEXT    NOT NULL DEFAULT 'all',  -- 'all' | tier slug | 'active'
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    last_sent_at   TIMESTAMPTZ DEFAULT NULL,
    next_send_at   TIMESTAMPTZ DEFAULT NULL,
    created_by     UUID    REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.scheduled_notifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins manage scheduled_notifications" ON public.scheduled_notifications;
CREATE POLICY "Admins manage scheduled_notifications"
    ON public.scheduled_notifications FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));


-- ────────────────────────────────────────────────────────────
--  11. hall_of_fame_inductees table
--      Triggered when profiles.top4_finish_count reaches 4.
--      Status only — no HP reward.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.hall_of_fame_inductees (
    id                UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID    NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE UNIQUE,
    inducted_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    full_name         TEXT    NOT NULL,
    photo_url         TEXT    DEFAULT NULL,
    tier_at_induction TEXT    DEFAULT NULL,   -- tier slug at time of induction
    top4_finish_count INTEGER NOT NULL DEFAULT 4,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.hall_of_fame_inductees ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone reads hall_of_fame" ON public.hall_of_fame_inductees;
CREATE POLICY "Anyone reads hall_of_fame"
    ON public.hall_of_fame_inductees FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS "Admins manage hall_of_fame" ON public.hall_of_fame_inductees;
CREATE POLICY "Admins manage hall_of_fame"
    ON public.hall_of_fame_inductees FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

COMMENT ON TABLE public.hall_of_fame_inductees IS 'Users inducted after 4 non-consecutive top-4 leaderboard finishes. Status only, no HP.';


-- ────────────────────────────────────────────────────────────
--  12. profiles new columns
-- ────────────────────────────────────────────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS graduation_claimed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS top4_finish_count  INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS academic_level     TEXT    DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS faculty            TEXT    DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS department         TEXT    DEFAULT NULL;

COMMENT ON COLUMN public.profiles.graduation_claimed  IS 'True once user has self-declared graduation. One-time, cannot re-declare.';
COMMENT ON COLUMN public.profiles.top4_finish_count   IS 'Lifetime count of top-4 leaderboard finishes. Induction at count=4.';
COMMENT ON COLUMN public.profiles.academic_level      IS 'e.g. "400", "500", "postgrad". Used for graduation eligibility gate.';
COMMENT ON COLUMN public.profiles.faculty             IS 'User faculty for birthday blast segmentation.';
COMMENT ON COLUMN public.profiles.department          IS 'User department for birthday blast segmentation.';


-- ────────────────────────────────────────────────────────────
--  13. order_locks new columns
--     reward_type: 'discount' (% off) or 'hp' (HP awarded on use).
--     Both admin-set; user picks type at lock-in.
-- ────────────────────────────────────────────────────────────
ALTER TABLE public.order_locks
    ADD COLUMN IF NOT EXISTS reward_type      TEXT    NOT NULL DEFAULT 'discount'
        CHECK (reward_type IN ('discount', 'hp')),
    ADD COLUMN IF NOT EXISTS reward_hp_amount INTEGER DEFAULT NULL;

COMMENT ON COLUMN public.order_locks.reward_type      IS '"discount" = % off order | "hp" = HP credited on lock-date order placed.';
COMMENT ON COLUMN public.order_locks.reward_hp_amount IS 'HP to award when reward_type=hp and user places order on locked_date.';


-- ────────────────────────────────────────────────────────────
--  14. orders new column: squad_name
--     Entered at squad order creation; used for squad leaderboard
--     ranking instead of the organiser username.
-- ────────────────────────────────────────────────────────────
ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS squad_name TEXT DEFAULT NULL;

COMMENT ON COLUMN public.orders.squad_name IS 'Optional squad name for squad orders, used in squad leaderboard rankings.';


-- ────────────────────────────────────────────────────────────
--  15. events new columns
--     hp_per_attendee  — admin-set HP per check-in (replaces hp_reward for events)
--     funding_source   — host_prepaid | hg_funded (preserves liability boundary)
--     max_attendees    — required when hg_funded (bounds liability)
--     hp_required      — for paid events: HP portion user must hold
--     total_value      — for paid events: full cash price if HP insufficient
--     is_paid          — flag: paid event (has hp_required + total_value)
-- ────────────────────────────────────────────────────────────
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS hp_per_attendee INTEGER        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS funding_source  TEXT           DEFAULT NULL
        CHECK (funding_source IN ('host_prepaid', 'hg_funded', NULL)),
    ADD COLUMN IF NOT EXISTS max_attendees   INTEGER        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS hp_required     INTEGER        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS total_value     NUMERIC(10,2)  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS is_paid         BOOLEAN        NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.events.hp_per_attendee IS 'Admin-set HP awarded per attendee at check-in. Takes priority over the legacy hp_reward column.';
COMMENT ON COLUMN public.events.funding_source  IS 'host_prepaid = event host paid for HP upfront; hg_funded = HG funds the HP (liability exposure).';
COMMENT ON COLUMN public.events.max_attendees   IS 'Hard cap on registrations. Required when funding_source=hg_funded to bound liability.';
COMMENT ON COLUMN public.events.hp_required     IS 'Paid event: HP the user must hold to use the HP+cash payment path.';
COMMENT ON COLUMN public.events.total_value     IS 'Paid event: full cash price when user HP < hp_required.';
COMMENT ON COLUMN public.events.is_paid         IS 'True when event requires payment (hp_required + total_value set by admin).';


-- ────────────────────────────────────────────────────────────
--  16. marketplace_listings new columns
--     cash_price   — cash portion when user HP >= hp_price
--     total_value  — full cash price when user HP < hp_price
-- ────────────────────────────────────────────────────────────
ALTER TABLE public.marketplace_listings
    ADD COLUMN IF NOT EXISTS cash_price  NUMERIC(10,2) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS total_value NUMERIC(10,2) DEFAULT NULL;

COMMENT ON COLUMN public.marketplace_listings.cash_price  IS 'Cash paid when user HP >= hp_price (HP + this cash = full purchase).';
COMMENT ON COLUMN public.marketplace_listings.total_value IS 'Full cash price when user HP < hp_price (no partial HP path).';


-- ────────────────────────────────────────────────────────────
--  17. system_settings seed additions
-- ────────────────────────────────────────────────────────────
INSERT INTO public.system_settings (key, value, description) VALUES
    ('hp_multiplier',              '1',   'Active HP earn multiplier (e.g. "2" = 2x all HP earning). Set to "1" to disable.'),
    ('multiplier_expires_at',      '""',  'ISO 8601 UTC datetime when the hp_multiplier expires. Empty string = no expiry.'),
    ('monthly_pending_cap',        '1000','Max pending HP per user per month from free activities (post/share, review, challenge, check-in streak, social-follow).'),
    ('hp_transfer_min_orders',     '3',   'Minimum completed orders a sender must have before HP gifting is allowed.'),
    ('graduation_min_level',       '400', 'Minimum academic level (numeric string) required to self-declare graduation.'),
    ('notification_gap_minutes',   '30',  'Minimum gap in minutes between same-type promotional notifications to the same user. Admin-editable. Default 30.'),
    ('notification_daily_cap',     '20',  'Maximum non-critical notifications per user per day. Admin-editable. Default 20.')
ON CONFLICT (key) DO NOTHING;

-- Update monthly_hp_cap default to 1000 if still at 800
UPDATE public.system_settings SET value = '"1000"' WHERE key = 'monthly_hp_cap' AND value = '800';
