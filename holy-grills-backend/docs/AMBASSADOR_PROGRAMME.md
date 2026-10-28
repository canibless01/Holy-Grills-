# Campus Ambassador Programme — Implementation & Deployment Guide

Status: code-complete, gated by 657 backend tests (61 ambassador-specific plus 5 email sign-off) and the
full frontend build. **The four SQL migrations have not been executed** — they are
shipped as reviewable files and must be applied manually by a platform operator in
the order given below.

---

## 1. What was built

A Campus Ambassador Programme that reuses the existing student accounts,
`profiles.referral_code` links, HP / free-side / order services and admin shell —
no separate accounts, wallets, referral engine or dashboards were introduced.

| Capability | Where it lives |
|---|---|
| Restricted `community_manager` role + "Campus Ambassador" tag on student profiles | `constants.py`, `ambassadors` table, admin Ambassadors screen |
| Separate ambassador attribution (visits, signups, existing-customer clicks, delivered orders, milestones) with a **7-day rolling last-click window** | `ambassador_link_clicks`, `ambassador_attributions`, `ambassador_order_attributions` + tracking RPCs |
| Promo distribution: one graphic, one `{{link}}` caption, per-ambassador personalized links and Share | Admin → Ambassador Promos (`AdminAmbassadorPromo.tsx`) |
| Manual Pending / Seen / Shared activity, completion rate vs 4 shares/week | `ambassador_promo_assignments`, monthly review metrics |
| Configurable milestones with reached → approved → issued → redeemed → expired lifecycle and dedupe; **auto-issue** milestones grant immediately via `AMBASSADOR_SYSTEM_ACTOR_ID`, manual ones wait for an admin decision | `ambassador_milestones`, `ambassador_milestone_claims` |
| Rewards: existing HP and free-side grants **plus new meal-discount rewards** (100% off one eligible meal up to a cap, N uses, expiry, single-use checkout redemption) | `ambassador_grants`, `ambassador_meal_discounts` + reward RPCs, checkout integration |
| Monthly reviews with manager recommendation and admin-only decision | `ambassador_monthly_reviews`, Admin → Ambassador Reviews |
| Student dashboard widget (own data only) | `AmbassadorProgrammeCard.tsx` on the student dashboard |
| Audit trail for every staff action | existing `admin_audit_logs` (`entity_type = 'ambassador_programme'`) |

### Hard rules enforced by the implementation

- The programme **never** writes `profiles.referred_by`, never inserts/updates
  `public.referrals`, and never alters the existing 75 HP referral logic. A test
  (`test_attribution_flows_never_write_referral_tables`) asserts this.
- No wallet/naira credit buckets are involved. Meal benefits are meal discounts
  applied to food lines only; the delivery fee is always still payable and a
  discount can never drive the total below zero.
- `community_manager` can manage ambassadors, promos, activity tracking and
  recommendations, but **cannot** tag/untag, configure milestones, record reward
  decisions or issue grants. Financial endpoints are gated twice: the
  `@require_role("admin")` decorator **and** an in-handler
  `_require_financial_admin()` check, backed by RLS/RPC grants in SQL.
- WhatsApp is never automated and no read receipts are fabricated. Sharing uses
  the Web Share API where the browser supports file sharing, otherwise an honest
  download-graphic + copy-caption fallback. Pending/Seen/Shared are recorded by staff.

---

## 2. Role model

| Role | Read programme data | Promos & activity statuses | Recommendation | Tag/untag, milestones, decision, grants |
|---|---|---|---|---|
| `community_manager` | ✅ (own campus) | ✅ (own campus) | ✅ | ❌ 403 |
| `admin` | ✅ (own campus) | ✅ | ✅ | ✅ |
| `super_admin` | ✅ (all campuses) | ✅ | ✅ | ✅ |
| tagged student | own `/me` + own meal discounts only | — | — | — |
| any visitor | `POST /track-click` (optional auth) | — | — | — |

`VALID_ROLES` in `app/constants.py` now includes `community_manager`. The frontend
admin sidebar derives its three ambassador sections from the same role constants,
so the manager sees only those sections; the server independently rejects any
forbidden write (hiding a button is not the security control).

---

## 3. Database migrations — run order (operator action)

Apply these in the **Supabase SQL Editor (or an equivalent service-role
connection), in strict filename order**. Each file is idempotent
(`CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`, guarded seeds) and
contains RLS policies plus `REVOKE ALL ... FROM PUBLIC, anon, authenticated` /
`GRANT EXECUTE ... TO service_role` on every RPC, so the Flask API is the only
caller.

| Order | File | Contents |
|---|---|---|
| 1 | `migrations/20261027120000_ambassador_programme_schema.sql` | 12 tables, indexes, unique constraints (one attribution per order, one claim per milestone/ambassador/month, one non-overridden grant per ambassador/month/category), RLS enablement + policies, helper functions `hg_ambassador_actor`, `hg_is_ambassador_staff`, `hg_is_financial_admin` |
| 2 | `migrations/20261027120100_ambassador_tracking_rpcs.sql` | `hg_ambassador_record_click`, `hg_ambassador_merge_visitor`, `hg_ambassador_attribute_order`, `hg_ambassador_reverse_order` plus the window/for-code resolvers |
| 3 | `migrations/20261027120200_ambassador_reward_rpcs.sql` | `hg_expire_ambassador_discounts`, `hg_grant_ambassador_meal_discount`, `hg_redeem_ambassador_meal_discount`, `hg_restore_ambassador_meal_discount` |
| 4 | `migrations/20261027120300_ambassador_programme_settings.sql` | Four global `system_settings` seeds (existing values are never overwritten) |

### Tables created (migration 1)

`ambassadors`, `ambassador_link_clicks`, `ambassador_attributions`,
`ambassador_order_attributions`, `ambassador_promo_messages`,
`ambassador_promo_assignments`, `ambassador_milestones`,
`ambassador_milestone_claims`, `ambassador_monthly_reviews`,
`ambassador_grants`, `ambassador_meal_discounts`,
`ambassador_meal_discount_redemptions`.

### Post-deploy verification queries

```sql
-- All twelve tables exist.
select table_name from information_schema.tables
where table_schema = 'public' and table_name like 'ambassador%'
order by table_name;

-- RPCs are service-role only (each should return zero grants to anon/authenticated).
select p.proname, r.rolname
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
join lateral aclexplode(p.proacl) a on true
join pg_roles r on r.oid = a.grantee
where n.nspname = 'public' and p.proname like 'hg_%ambassador%'
  and r.rolname in ('anon', 'authenticated');

-- Settings seeds.
select key, value from public.system_settings
where key like 'ambassador_%' order by key;
```

The backend contract checker can also be run after applying the migrations:
`python scripts/contract_check.py` (and `make contract` if using the Makefile).

### Rollback

Migrations are additive and touch only new `ambassador_*` objects plus four new
settings rows. To disable the programme without dropping data, turn every
ambassador row inactive (`update public.ambassadors set status = 'inactive';`) —
the API then returns the `is_ambassador: false` shape everywhere and clicks become
no-ops. A full drop script was deliberately not shipped; if one is needed it must
drop the four migration's objects in reverse order and be reviewed separately.

---

## 4. Configuration

### Environment variables

The tracking link builder reuses the existing mandatory `FRONTEND_URL`
(production deploys already fail fast without it). Supabase service-role
credentials continue to supply the single database connection used by the
SECURITY DEFINER calls. One optional variable supports auto-issuing milestones:

| Variable | Required | Purpose |
|---|---|---|
| `AMBASSADOR_SYSTEM_ACTOR_ID` | optional | Profile id of an `admin`/`super_admin` that authorizes grants created by milestones with **auto-issue** enabled. When blank or invalid, an auto milestone still creates a `pending_approval` claim for a manual admin decision — a reward is never written without a real authorizing profile (the `ambassador_grants.issued_by` foreign key requires one). |

### `system_settings` seeds (migration 4, global rows)

| Key | Default | Read by |
|---|---|---|
| `ambassador_attribution_window_days` | `7` | Postgres `hg_ambassador_window_days()` inside the click/merge/attribute RPCs |
| `ambassador_expected_weekly_shares` | `4` | Documents the expectation surfaced by `assignment_metrics` (weekly target 4; monthly target = weeks × 4) |
| `ambassador_meal_discount_default_max` | `3000` | Reference default for the admin grant form's max eligible meal value (NGN) |
| `ambassador_meal_discount_default_validity` | `14` | `issue_grant` via `setting_or_config(..., 14, minimum=1, maximum=365)` when a grant omits `validity_days` |

Edit them through the existing system-settings admin surface. Re-running
migration 4 will not overwrite tuned values.

---

## 5. Attribution rules

### Click → attribution (7-day rolling last-click)

1. The browser calls `POST /api/ambassadors/track-click` on every `?ref=CODE`
   visit (`AmbassadorClickTracker.tsx`), including for anonymous visitors; the
   response returns a stable `anonymous_id` stored locally.
2. `hg_ambassador_record_click` upserts the visitor's row in
   `ambassador_attributions`: a later click **replaces** the ambassador and slides
   `expires_at` to `last_click_at + window` (default 7 days). Same-ambassador
   clicks still refresh the window and increment `click_count`.
3. On login/signup the client calls `POST /api/ambassadors/merge-visitor`;
   `hg_ambassador_merge_visitor` adopts the anonymous click trail and, again,
   lets the newest click win.
4. When an order becomes `delivered`, the order lifecycle calls
   `hg_ambassador_attribute_order`. It attributes the order only when
   `status = 'delivered'`, `payment_status <> 'refunded'`, a click predates the
   order and `expires_at >= order.created_at`. The primary key on `order_id`
   makes double counting impossible; re-runs converge (re-eligibility after a
   reversed refund flips the row back to `eligible`).
5. Full refund/cancellation calls `hg_ambassador_reverse_order`, which marks the
   row `excluded` (idempotent — only `eligible` rows move). Partial refunds stay
   eligible. Reporting reads (`attributed_orders`) exclude the `excluded` rows by
   default, so refund changes are reflected automatically.

The existing referral tables are not involved at any point.

### Meal-discount checkout lifecycle

- **Quote and order creation** both call `resolve_discount_for_checkout`
  (ownership, status not voided/expired, `uses_remaining > 0`) and
  `compute_discount_amount` (the lesser of the cap, the priciest single meal and
  the remaining food headroom — delivery is not an input to the function).
- Once the order exists, `hg_redeem_ambassador_meal_discount` consumes one use
  atomically (status flips to `redeemed` at the last use) and writes a redemption
  row keyed to the order.
- Cancellation/refund calls `hg_restore_ambassador_meal_discount`, which returns
  the use (`LEAST(uses_total, uses_remaining + 1)`), preventing reuse abuse while
  not exceeding the original total.
- `hg_expire_ambassador_discounts` runs on every discount read
  (`list_my_discounts`, `resolve_discount_for_checkout`) and can additionally be
  placed on the existing scheduler if a hard time-based cutoff is desired.
- Recurring grants (e.g. biweekly) are independent rows: the duplicate guard only
  blocks the same ambassador × month × reward category unless
  `override_duplicate: true` is sent; each grant gets its own
  `idempotency_key`, its own discount row, expiry and redemption counter.

### Milestone auto-issue vs manual approval

- A milestone with `auto_issue = false` (the default) creates a
  `pending_approval` claim when its threshold is first reached; the reward is
  only issued when an admin records an approved decision/grant.
- A milestone with `auto_issue = true` issues its configured reward the moment
  the claim is created, inside the same `evaluate_milestones` call that powers
  the review pages and the student dashboard — no separate cron job is needed.
  The claim is marked `issued` and linked to the grant (`grant_id`,
  `decided_by = AMBASSADOR_SYSTEM_ACTOR_ID`). The write always runs on the
  service-role client (the ambassador tables are SELECT-only under RLS for
  authenticated users), including when it is triggered from a student's own
  `GET /me`; rows remain hard-scoped to that JWT user.
- Guard rails: claim creation is deduped per milestone/ambassador/month, so a
  reward can auto-issue at most once; if a same-month/category grant already
  exists the duplicate guard wins and the claim simply stays
  `pending_approval` (an admin can still grant with the explicit override); any
  failure leaves the pending claim intact and never breaks the dashboard.
- Activity on its own never issues a reward — only a configured auto rule, or
  an admin, can do so.

### Grants reuse the existing financial services

- HP → `hp_service.award_active_hp(..., apply_multiplier=False,
  reference_type='ambassador_grant')`, with the resulting transaction id linked
  back onto the grant row.
- Free sides → the existing `hg_grant_free_sides_atomic` RPC with a fresh intent
  key; an RPC error voids the ambassador grant row.
- Meal discounts → the new reward RPC above.
- Every grant writes `admin_audit_logs`; no code path edits balances directly.

---

## 6. HTTP API (20 routes, all under `/api/ambassadors`)

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/track-click` | public (optional auth) | record a `?ref=` visit, returns `anonymous_id` |
| POST | `/merge-visitor` | authenticated | attach an anonymous trail after login |
| GET | `/me` | authenticated | ambassador dashboard payload (`is_ambassador:false` for everyone else) |
| GET | `/meal-discounts` | authenticated | caller's active meal discounts |
| GET | `/staff/ambassadors` | manager/admin | roster with lifetime + month metrics |
| POST | `/staff/ambassadors` | admin only | tag a student (campus-checked) |
| GET | `/staff/ambassadors/<id>` | manager/admin | monthly review detail + grants |
| DELETE | `/staff/ambassadors/<id>` | admin only | untag (soft, reversible) |
| GET/POST | `/staff/promo-messages` | manager/admin | list / create a promo (caption must contain `{{link}}`) |
| GET | `/staff/promo-messages/<id>/assignments` | manager/admin | per-ambassador rows + profiles |
| PATCH | `/staff/assignments/<id>` | manager/admin | set `pending` / `seen` / `shared` |
| GET | `/staff/reviews` | manager/admin | persisted monthly metrics for the campus |
| POST | `/staff/reviews/<id>/recommendation` | manager/admin | recommend / do_not_recommend + note |
| POST | `/staff/reviews/<id>/decision` | admin only | approve / reject |
| GET/POST | `/staff/milestones` | GET manager/admin; POST admin only | list / configure milestones |
| PATCH | `/staff/milestones/<id>` | admin only | edit/deactivate a milestone |
| GET/POST | `/staff/grants` | GET manager/admin (scoped); POST admin only | list / issue rewards (409 `DUPLICATE_MONTHLY_GRANT` until override) |

Duplicate-grant responses carry `code: "DUPLICATE_MONTHLY_GRANT"` so the admin
UI can show the explicit override checkbox.

---

## 7. Frontend surfaces

- **Admin → Ambassadors** (`AdminAmbassadors.tsx`): roster, tag/untag (admin
  roles only), milestone configuration.
- **Admin → Ambassador Promos** (`AdminAmbassadorPromo.tsx`): month-scoped
  messages, graphic upload (existing `ImageUploader`, folder
  `ambassador-promo`), all/selected targeting, per-ambassador Share and the
  manual Pending/Seen/Shared buttons.
- **Admin → Ambassador Reviews** (`AdminAmbassadorReviews.tsx`): month picker,
  eight metric tiles, milestone progress, recommendation (manager) and
  approve/reject + grant modal (admin/super_admin only), 409 override flow.
- **Student dashboard** (`AmbassadorProgrammeCard.tsx`): renders only for tagged
  ambassadors; tracking link copy, lifetime and current-month totals, referral HP
  (read from the existing referrals system), milestones and meal discounts with
  uses/expiry/status.
- **Checkout** (`Checkout.tsx`): active meal discounts appear as a radio choice;
  the quote summary shows the meal-discount line separately from the always-payable
  delivery fee.
- All new copy is registered as `FE_*` keys in `app/messages.py`
  (`messages:check` is part of the build).

### Sharing behaviour (no automation, no fake receipts)

`shareToWhatsApp` fetches the graphic into a `File`; when
`navigator.canShare({ files })` is true it invokes the native Web Share sheet with
the file and the personalized caption. Otherwise (or after a share cancellation /
CORS failure) it copies the caption to the clipboard and downloads the graphic,
with a toast telling the user to attach it manually. `wa.me` is deliberately not
used for images because it can prefill text only. Activity statuses remain
manually recorded. A source-level guard (`npm run test:ambassador-share`) fails
the build if these guarantees are removed.

---

## 8. Test coverage & verification

### Backend — `tests/test_ambassador_programme.py` (61 tests) plus `tests/test_email_signoff.py` (5 tests)

| Mandated scenario | Test(s) |
|---|---|
| Tag add/remove/idempotent re-tag | `TagAndRoleTests` |
| Manager permission denial (decorator + in-handler + cross-campus) | `TagAndRoleTests`, `FinancialAdminGuardTests` |
| Caption personalization | `test_caption_personalization_*`, `test_target_all_*` |
| Share fallback / manual statuses | `test_manual_status_*` + frontend `test:ambassador-share` |
| New + existing customer attribution | `ClickAttributionTests` (guest, logged-in, merge, guest route) |
| A→B last-click + 7-day window | `test_last_click_replacement_and_seven_day_window_are_in_sql` |
| Original referrer unchanged | `test_attribution_flows_never_write_referral_tables`, `test_module_does_not_import_wallet_or_referral_write_services` |
| Delivered once / cancelled-refunded excluded | `test_delivery_and_refund_eligibility_rules_are_in_sql`, wrapper/lifecycle tests |
| Completion rate 7/10 = 70% | `test_completion_rate_seven_of_ten_is_seventy_percent` |
| Milestone dedupe | `MilestoneTests` |
| Auto-issue grant, missing/invalid actor fallback, duplicate degradation, HP auto grant, service-client `/me` scoping | `AutoIssueMilestoneTests`, `DashboardAndReviewTests` |
| Email sign-off replaced on every branded mail (`test_email_signoff.py`) | fixed "Made with more than flame ❤️‍🔥, Holy Grills Team." line, no "With love"/"Holy Grills FUTA" |
| Single/multiple meal grants + duplicate override | `GrantTests` |
| Checkout discount + delivery payable | `MealDiscountCheckoutTests` |
| Independent biweekly grants | `test_recurring_biweekly_grants_keep_independent_keys_and_discounts` |
| Regression of referral/free-side/HP/wallet/orders | full 657-test suite, HP/free-side grant tests, lifecycle hook source tests, RPC `REVOKE` contract tests |

### Gate commands

```bash
# backend (from holy-grills-backend)
.venv/bin/python -m pyflakes app/services/ambassador_service.py \
  app/routes/ambassadors.py tests/test_ambassador_programme.py
.venv/bin/python -m pytest -q          # 657 passed

# frontend (from holy-grills-frontend)
npm run typecheck                     # tsc --noEmit
npm run lint
npm run messages:check
npm run routes:check
npm run test:ambassador-share
npm run build                         # full chain incl. client, SSR and prerender
```

### Post-deploy smoke (after migrations + deploy)

1. As an admin, tag a test student → the student's dashboard shows the widget and
   their `?ref=` link.
2. Open the link in a private window (guest click), then log in as that visitor →
   `ambassador_link_clicks` carries the adopted trail and
   `ambassador_attributions` shows the ambassador with a ~7-day `expires_at`.
3. Place and deliver an order inside the window → one
   `ambassador_order_attributions` row (`eligible`); refund it fully →
   `excluded`; confirm the review metrics update.
4. Create a promo with a graphic, confirm the personalized link per ambassador,
   exercise both share paths (a desktop browser without file share shows the
   download/copy fallback), and set Seen/Shared → completion rate reads correctly.
5. Issue one of each reward type; confirm HP appears in the normal HP ledger, the
   free-side credit in the existing free-side surface, and the meal discount on
   checkout with delivery still charged. Attempt a second same-month grant → 409;
   override → succeeds as a separate discount.
6. As a `community_manager`, confirm the grant/decision/milestone controls are
   absent and that replaying the same calls against the API directly returns 403.

---

## 9. Deployment sequence

1. Merge code; no behaviour activates before the migrations because every new
   endpoint reads only the new tables and the click route no-ops on unknown codes.
2. Apply migrations 1 → 2 → 3 → 4 in the Supabase SQL editor; run the verification
   queries in §3.
3. Deploy the backend (no new env vars; confirm `FRONTEND_URL`).
4. Deploy the frontend; smoke-test with the §8 checklist.
5. Tag the first ambassadors, configure milestones and seed the first promo.
