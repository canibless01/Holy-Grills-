-- ============================================================================
-- Campus Ambassador Programme — 1/4 — schema, role helpers, RLS
-- ----------------------------------------------------------------------------
-- Safe to review and apply standalone. Creates ONLY new objects (plus one
-- nullable column on public.orders). No existing table, policy, function or
-- reward rule is modified. Run order:
--   1. 20261027120000_ambassador_programme_schema.sql        (this file)
--   2. 20261027120100_ambassador_tracking_rpcs.sql
--   3. 20261027120200_ambassador_reward_rpcs.sql
--   4. 20261027120300_ambassador_programme_settings.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Role helpers. The role itself is an application-level value on
-- profiles.role (there is no DB enum/CHECK to extend). RLS needs to recognise
-- the new community_manager role, which may read programme data for its own
-- campus but can never perform financial mutations (those RPCs are granted to
-- service_role only and the Flask layer additionally rejects the role).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.hg_ambassador_actor()
RETURNS TABLE (user_id uuid, role text, campus_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT p.id, p.role::text, p.campus_id
  FROM public.profiles p
  WHERE p.id = auth.uid() AND p.is_active IS TRUE;
$$;
REVOKE ALL ON FUNCTION public.hg_ambassador_actor() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_actor() TO authenticated, service_role;

-- True for staff allowed to open the ambassador programme sections.
CREATE OR REPLACE FUNCTION public.hg_is_ambassador_staff(v_campus_id uuid DEFAULT NULL)
RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_role text;
  v_campus uuid;
BEGIN
  SELECT role, campus_id INTO v_role, v_campus FROM public.hg_ambassador_actor();
  IF v_role NOT IN ('admin', 'super_admin', 'community_manager') THEN
    RETURN false;
  END IF;
  IF v_role = 'super_admin' THEN
    RETURN true; -- platform-wide access
  END IF;
  -- Campus admins and community managers are pinned to their own campus.
  RETURN v_campus IS NOT NULL AND (v_campus_id IS NULL OR v_campus_id = v_campus);
END; $$;
REVOKE ALL ON FUNCTION public.hg_is_ambassador_staff(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.hg_is_ambassador_staff(uuid) TO authenticated, service_role;

-- True only for roles allowed to approve/issue programme rewards.
CREATE OR REPLACE FUNCTION public.hg_is_financial_admin()
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.hg_ambassador_actor() a WHERE a.role IN ('admin', 'super_admin')
  );
$$;
REVOKE ALL ON FUNCTION public.hg_is_financial_admin() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.hg_is_financial_admin() TO authenticated, service_role;

-- Generic touched-row timestamp, scoped to this programme's tables.
CREATE OR REPLACE FUNCTION public.hg_ambassador_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION public.hg_ambassador_set_updated_at() FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 1. Ambassador tag — a marker on an EXISTING profile. The student keeps their
--    account, role, campus and dashboard; nothing about the profile is rewritten.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassadors (
  profile_id   uuid PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
  campus_id    uuid REFERENCES public.campuses(id),
  status       text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  tagged_by    uuid REFERENCES public.profiles(id),
  tagged_at    timestamptz NOT NULL DEFAULT now(),
  untagged_at  timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_ambassadors_updated ON public.ambassadors;
CREATE TRIGGER trg_ambassadors_updated BEFORE UPDATE ON public.ambassadors
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

-- ---------------------------------------------------------------------------
-- 2. Every link hit (?ref=CODE), including anonymous visitors. visitor_user_id
--    stays NULL until login/merge; anonymous_id carries the pre-login trail.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassador_link_clicks (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ref_code         text NOT NULL,
  ambassador_id    uuid NOT NULL REFERENCES public.ambassadors(profile_id) ON DELETE CASCADE,
  visitor_user_id  uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  anonymous_id     text,
  campus_id        uuid REFERENCES public.campuses(id),
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_amb_clicks_ambassador_time
  ON public.ambassador_link_clicks (ambassador_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_amb_clicks_visitor
  ON public.ambassador_link_clicks (visitor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_amb_clicks_anon
  ON public.ambassador_link_clicks (anonymous_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 3. Current last-click attribution per identified customer. One row per
--    customer; each new qualifying click refreshes ambassador + 7-day window.
--    Completely separate from profiles.referred_by / public.referrals.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassador_attributions (
  customer_user_id uuid PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
  ambassador_id    uuid NOT NULL REFERENCES public.ambassadors(profile_id) ON DELETE CASCADE,
  first_click_at   timestamptz NOT NULL DEFAULT now(),
  last_click_at    timestamptz NOT NULL DEFAULT now(),
  expires_at       timestamptz NOT NULL,
  click_count      integer NOT NULL DEFAULT 1 CHECK (click_count >= 1),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_amb_attributions_ambassador
  ON public.ambassador_attributions (ambassador_id);
CREATE INDEX IF NOT EXISTS idx_amb_attributions_live
  ON public.ambassador_attributions (expires_at);
DROP TRIGGER IF EXISTS trg_amb_attributions_updated ON public.ambassador_attributions;
CREATE TRIGGER trg_amb_attributions_updated BEFORE UPDATE ON public.ambassador_attributions
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

-- ---------------------------------------------------------------------------
-- 4. One row per attributed order. PK on order_id makes double counting
--    physically impossible. 'excluded' keeps refunded/cancelled orders visible
--    in reporting instead of deleting history.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassador_order_attributions (
  order_id          uuid PRIMARY KEY REFERENCES public.orders(id) ON DELETE CASCADE,
  customer_user_id  uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  ambassador_id     uuid NOT NULL REFERENCES public.ambassadors(profile_id) ON DELETE CASCADE,
  campus_id         uuid REFERENCES public.campuses(id),
  order_total       numeric(12,2) NOT NULL DEFAULT 0,
  eligibility       text NOT NULL DEFAULT 'eligible' CHECK (eligibility IN ('eligible', 'excluded')),
  exclusion_reason  text,
  attributed_at     timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_amb_order_attr_amb_time
  ON public.ambassador_order_attributions (ambassador_id, attributed_at DESC);
CREATE INDEX IF NOT EXISTS idx_amb_order_attr_customer
  ON public.ambassador_order_attributions (customer_user_id);
DROP TRIGGER IF EXISTS trg_amb_order_attr_updated ON public.ambassador_order_attributions;
CREATE TRIGGER trg_amb_order_attr_updated BEFORE UPDATE ON public.ambassador_order_attributions
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

-- ---------------------------------------------------------------------------
-- 5. Promotional content + per-ambassador monthly assignments (manual
--    Pending / Seen / Shared tracking — no automated WhatsApp telemetry).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassador_promo_messages (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_by  uuid NOT NULL REFERENCES public.profiles(id),
  campus_id   uuid REFERENCES public.campuses(id),
  image_url   text,
  caption     text NOT NULL CHECK (length(btrim(caption)) > 0),
  target_all  boolean NOT NULL DEFAULT false,
  month       text NOT NULL DEFAULT to_char(now(), 'YYYY-MM'),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_amb_promo_updated ON public.ambassador_promo_messages;
CREATE TRIGGER trg_amb_promo_updated BEFORE UPDATE ON public.ambassador_promo_messages
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

CREATE TABLE IF NOT EXISTS public.ambassador_promo_assignments (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id     uuid NOT NULL REFERENCES public.ambassador_promo_messages(id) ON DELETE CASCADE,
  ambassador_id  uuid NOT NULL REFERENCES public.ambassadors(profile_id) ON DELETE CASCADE,
  month          text NOT NULL,
  status         text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'seen', 'shared')),
  evidence_note  text,
  updated_by     uuid REFERENCES public.profiles(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (message_id, ambassador_id)
);
CREATE INDEX IF NOT EXISTS idx_amb_promo_assign_month
  ON public.ambassador_promo_assignments (ambassador_id, month);
DROP TRIGGER IF EXISTS trg_amb_promo_assign_updated ON public.ambassador_promo_assignments;
CREATE TRIGGER trg_amb_promo_assign_updated BEFORE UPDATE ON public.ambassador_promo_assignments
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

-- ---------------------------------------------------------------------------
-- 6. Configurable performance milestones and their per-ambassador claims.
--    Separate from the existing milestone_service / referral milestones.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassador_milestones (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campus_id       uuid REFERENCES public.campuses(id), -- NULL = applies to every campus
  metric          text NOT NULL CHECK (metric IN ('orders', 'signups', 'shares')),
  threshold       integer NOT NULL CHECK (threshold > 0),
  reward_type     text NOT NULL CHECK (reward_type IN ('hp', 'free_side', 'meal_discount')),
  reward_amount   numeric(12,2) NOT NULL CHECK (reward_amount > 0),
  reward_uses     integer NOT NULL DEFAULT 1 CHECK (reward_uses >= 1),
  validity_days   integer NOT NULL DEFAULT 14 CHECK (validity_days > 0),
  auto_issue      boolean NOT NULL DEFAULT false,
  is_active       boolean NOT NULL DEFAULT true,
  created_by      uuid REFERENCES public.profiles(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_amb_milestones_active
  ON public.ambassador_milestones (is_active, metric);
DROP TRIGGER IF EXISTS trg_amb_milestones_updated ON public.ambassador_milestones;
CREATE TRIGGER trg_amb_milestones_updated BEFORE UPDATE ON public.ambassador_milestones
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

CREATE TABLE IF NOT EXISTS public.ambassador_milestone_claims (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  milestone_id          uuid NOT NULL REFERENCES public.ambassador_milestones(id) ON DELETE CASCADE,
  ambassador_id         uuid NOT NULL REFERENCES public.ambassadors(profile_id) ON DELETE CASCADE,
  period_month          text NOT NULL,
  metric_value_at_claim integer NOT NULL DEFAULT 0,
  status                text NOT NULL DEFAULT 'pending_approval'
                          CHECK (status IN ('reached', 'pending_approval', 'approved', 'rejected', 'issued')),
  decision_note         text,
  decided_by            uuid REFERENCES public.profiles(id),
  decided_at            timestamptz,
  grant_id              uuid, -- FK added in migration 3 once ambassador_grants exists
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (milestone_id, ambassador_id, period_month)
);
DROP TRIGGER IF EXISTS trg_amb_claims_updated ON public.ambassador_milestone_claims;
CREATE TRIGGER trg_amb_claims_updated BEFORE UPDATE ON public.ambassador_milestone_claims
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

-- ---------------------------------------------------------------------------
-- 7. Monthly review: manager recommendation, then Admin decision.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassador_monthly_reviews (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ambassador_id      uuid NOT NULL REFERENCES public.ambassadors(profile_id) ON DELETE CASCADE,
  month              text NOT NULL,
  assigned_count     integer NOT NULL DEFAULT 0,
  seen_count         integer NOT NULL DEFAULT 0,
  shared_count       integer NOT NULL DEFAULT 0,
  completion_rate    numeric(5,2) NOT NULL DEFAULT 0,
  signups_count      integer NOT NULL DEFAULT 0,
  orders_count       integer NOT NULL DEFAULT 0,
  recommendation     text NOT NULL DEFAULT 'none'
                       CHECK (recommendation IN ('none', 'recommend', 'do_not_recommend')),
  recommendation_note text,
  recommended_by     uuid REFERENCES public.profiles(id),
  recommended_at     timestamptz,
  decision           text NOT NULL DEFAULT 'pending'
                       CHECK (decision IN ('pending', 'approved', 'rejected')),
  decided_by         uuid REFERENCES public.profiles(id),
  decided_at         timestamptz,
  decision_note      text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (ambassador_id, month)
);
DROP TRIGGER IF EXISTS trg_amb_reviews_updated ON public.ambassador_monthly_reviews;
CREATE TRIGGER trg_amb_reviews_updated BEFORE UPDATE ON public.ambassador_monthly_reviews
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

-- ---------------------------------------------------------------------------
-- 8. Grant ledger. The partial unique index blocks an accidental second grant
--    of the same category in the same programme month; an intentional extra
--    grant sets duplicate_override = true and is recorded separately.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassador_grants (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ambassador_id        uuid NOT NULL REFERENCES public.ambassadors(profile_id) ON DELETE CASCADE,
  month                text NOT NULL,
  reward_category      text NOT NULL CHECK (reward_category IN ('hp', 'free_side', 'meal_discount')),
  amount               numeric(12,2) NOT NULL CHECK (amount > 0),
  uses_count           integer NOT NULL DEFAULT 1 CHECK (uses_count >= 1),
  validity_days        integer,
  expires_at           timestamptz,
  reason               text NOT NULL CHECK (length(btrim(reason)) > 0),
  source               text NOT NULL DEFAULT 'manual'
                         CHECK (source IN ('manual', 'monthly_review', 'milestone')),
  milestone_claim_id   uuid REFERENCES public.ambassador_milestone_claims(id),
  status               text NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'voided')),
  duplicate_override   boolean NOT NULL DEFAULT false,
  idempotency_key      text NOT NULL UNIQUE,
  hp_transaction_id    uuid,
  free_side_grant_id   uuid,
  meal_discount_id     uuid, -- FK added in migration 3
  issued_by            uuid NOT NULL REFERENCES public.profiles(id),
  issued_at            timestamptz NOT NULL DEFAULT now(),
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_amb_grant_month_category
  ON public.ambassador_grants (ambassador_id, month, reward_category)
  WHERE duplicate_override = false;
CREATE INDEX IF NOT EXISTS idx_amb_grants_ambassador
  ON public.ambassador_grants (ambassador_id, issued_at DESC);
DROP TRIGGER IF EXISTS trg_amb_grants_updated ON public.ambassador_grants;
CREATE TRIGGER trg_amb_grants_updated BEFORE UPDATE ON public.ambassador_grants
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

-- ---------------------------------------------------------------------------
-- 9. Meal-discount rewards (NOT naira wallet credit). Each grant produces one
--    discount bucket with its own expiry and use count; recurring biweekly
--    rewards are simply multiple independent rows.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ambassador_meal_discounts (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ambassador_id  uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  grant_id       uuid REFERENCES public.ambassador_grants(id) ON DELETE SET NULL,
  code           text NOT NULL UNIQUE,
  max_meal_value numeric(12,2) NOT NULL CHECK (max_meal_value > 0),
  uses_total     integer NOT NULL DEFAULT 1 CHECK (uses_total >= 1),
  uses_remaining integer NOT NULL DEFAULT 1 CHECK (uses_remaining >= 0),
  status         text NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'redeemed', 'expired', 'voided')),
  source_note    text,
  expires_at     timestamptz NOT NULL,
  created_by     uuid NOT NULL REFERENCES public.profiles(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_amb_meal_discount_owner
  ON public.ambassador_meal_discounts (ambassador_id, status, expires_at);
DROP TRIGGER IF EXISTS trg_amb_meal_discount_updated ON public.ambassador_meal_discounts;
CREATE TRIGGER trg_amb_meal_discount_updated BEFORE UPDATE ON public.ambassador_meal_discounts
  FOR EACH ROW EXECUTE FUNCTION public.hg_ambassador_set_updated_at();

CREATE TABLE IF NOT EXISTS public.ambassador_meal_discount_redemptions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  discount_id   uuid NOT NULL REFERENCES public.ambassador_meal_discounts(id) ON DELETE CASCADE,
  order_id      uuid NOT NULL UNIQUE REFERENCES public.orders(id) ON DELETE CASCADE,
  ambassador_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  meal_item_id  uuid REFERENCES public.menu_items(id),
  amount        numeric(12,2) NOT NULL CHECK (amount >= 0),
  restored_at   timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_amb_meal_redemptions_owner
  ON public.ambassador_meal_discount_redemptions (ambassador_id);

-- Orders remember which ambassador discount they consumed (the redemption row
-- is the financial record; this column makes checkout/refund lookups trivial).
ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS ambassador_discount_id uuid
  REFERENCES public.ambassador_meal_discounts(id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- RLS. Writes are service-role only — every mutation goes through the SECURITY
-- DEFINER RPCs / Flask routes, which perform their own role checks. Direct
-- authenticated access is limited to self-reads and staff reads.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'ambassadors',
    'ambassador_link_clicks',
    'ambassador_attributions',
    'ambassador_order_attributions',
    'ambassador_promo_messages',
    'ambassador_promo_assignments',
    'ambassador_milestones',
    'ambassador_milestone_claims',
    'ambassador_monthly_reviews',
    'ambassador_grants',
    'ambassador_meal_discounts',
    'ambassador_meal_discount_redemptions'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated;', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO service_role;', t);
  END LOOP;
END $$;

-- Self-read policies (ambassadors viewing their own programme data). For
-- ambassador-keyed tables the staff branch resolves the ambassador's campus via
-- the ambassadors tag table, so a campus community_manager cannot read another
-- campus's rows even through the user-scoped PostgREST client. No recursion:
-- the ambassadors policy does not reference any of these tables.
CREATE POLICY ambassadors_self_read ON public.ambassadors
  FOR SELECT TO authenticated USING (profile_id = auth.uid() OR public.hg_is_ambassador_staff(campus_id));
CREATE POLICY amb_attributions_self_read ON public.ambassador_attributions
  FOR SELECT TO authenticated USING (
    customer_user_id = auth.uid()
    OR public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_attributions.ambassador_id)));
CREATE POLICY amb_order_attr_self_read ON public.ambassador_order_attributions
  FOR SELECT TO authenticated USING (
    customer_user_id = auth.uid()
    OR public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_order_attributions.ambassador_id)));
CREATE POLICY amb_claims_self_read ON public.ambassador_milestone_claims
  FOR SELECT TO authenticated USING (
    ambassador_id = auth.uid()
    OR public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_milestone_claims.ambassador_id)));
CREATE POLICY amb_reviews_self_read ON public.ambassador_monthly_reviews
  FOR SELECT TO authenticated USING (
    ambassador_id = auth.uid()
    OR public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_monthly_reviews.ambassador_id)));
CREATE POLICY amb_grants_self_read ON public.ambassador_grants
  FOR SELECT TO authenticated USING (
    ambassador_id = auth.uid()
    OR public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_grants.ambassador_id)));
CREATE POLICY amb_meal_self_read ON public.ambassador_meal_discounts
  FOR SELECT TO authenticated USING (
    ambassador_id = auth.uid()
    OR public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_meal_discounts.ambassador_id)));
CREATE POLICY amb_meal_redemptions_self_read ON public.ambassador_meal_discount_redemptions
  FOR SELECT TO authenticated USING (
    ambassador_id = auth.uid()
    OR public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_meal_discount_redemptions.ambassador_id)));

-- Staff-only tables (other people's identities, promo ops, click trail, config).
CREATE POLICY amb_staff_ambassadors ON public.ambassadors
  FOR SELECT TO authenticated USING (public.hg_is_ambassador_staff(campus_id));
CREATE POLICY amb_staff_clicks ON public.ambassador_link_clicks
  FOR SELECT TO authenticated USING (
    public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_link_clicks.ambassador_id)));
CREATE POLICY amb_staff_promo_messages ON public.ambassador_promo_messages
  FOR SELECT TO authenticated USING (public.hg_is_ambassador_staff(campus_id));
CREATE POLICY amb_staff_promo_assignments ON public.ambassador_promo_assignments
  FOR SELECT TO authenticated USING (
    public.hg_is_ambassador_staff((SELECT a.campus_id FROM public.ambassadors a WHERE a.profile_id = ambassador_promo_assignments.ambassador_id)));
CREATE POLICY amb_staff_milestones ON public.ambassador_milestones
  FOR SELECT TO authenticated USING (public.hg_is_ambassador_staff(campus_id));
