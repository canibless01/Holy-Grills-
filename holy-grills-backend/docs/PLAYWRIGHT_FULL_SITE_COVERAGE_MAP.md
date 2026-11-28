# Playwright Full Site Coverage Map — Holy Grills

> Builder's test plan, not an implemented suite. Frontend is not in this checkout. This doc is a map for any builder who can run Playwright directly to cover full site functionality.

## Purpose
This map enumerates every user-visible flow, API contract, and background job that must be exercised to claim full-site coverage. Each section lists:
- **Route / UI entry**
- **Auth / role**
- **Preconditions / seed**
- **Steps**
- **Expected assertions**
- **Cleanup**

Use `WRITE_EXISTING=1` only when exercising E2E against an existing account; clean only rows created by that run and never delete/reset the account.

---

## 0. Global Config & Safety
- Supabase test project only: `zaxdkrmzyibkvlsrgmvq`; never touch production.
- No live checks with dummy config. If `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` unavailable, report live checks as blocked.
- Do not deploy A3 before B-6. B-6 (event check-in service-client insert) must be deployed first.
- `docs/PLAYWRIGHT_FULL_SITE_COVERAGE_MAP.md` itself is not executed; it drives the builder.
- Order-lock policy: **same-day disallowed**, allowed window **WAT tomorrow through day+7 inclusive** for create & reschedule, one reschedule default, unused locks expire after scheduled date.

---

## 1. Auth & Onboarding
### 1.1 Register
- `POST /api/auth/register` with email, password, full_name, campus_id, referral_code optional, `?ref` & `email` from URL.
- Verify: profile created, referral_code generated, referral row if `ref` present, signup bonus HP if enabled.
- Verify: squad pending claim — `pending_squad_hp` rows for this email become `claimed` and award `squad_split_claimed`.
- UI: `/register?ref=CODE&email=invited@example.com` reads ref & email, sends `referred_by_code`.

### 1.2 Login / Refresh / Logout / Me
- Login, get tokens, `/auth/me`, refresh, logout.
- Rate limiting: register, login, refresh endpoints.

### 1.3 Email Verification / Password Reset
- Resend verification, verify, reset request, reset confirm.

---

## 2. Reference Data
- `GET /campuses`, `GET /departments?campus_id=`, `GET /academic-levels`, `GET /academic-calendar`.
- Campus scoping: admin sees own campus, super_admin sees all via `?campus_id=`.

---

## 3. Menu & Storefront
- `GET /menu/categories`, `GET /menu/items`, `GET /menu/items/:id`, search, filters.
- Admin: create/update/delete category, item, addon, variation, stock, operating hours.
- Operating hour overrides wiring: `operating_hour_overrides` table affects ordering gate.
- Unused routes decision: `POST /storefront/promo-codes/validate` deprecated duplicate of `/orders/validate-promo`, `GET /storefront/config/public`, `POST /storefront/sections/:id/image` — keep or remove, mark deprecated.

---

## 4. Cart & Saved For Later
- Add to cart, update qty, variations, addons, list, clear.
- Saved for later: save, list, move to cart, delete.
- Abandoned cart: cron `scan_abandoned_carts` creates row, nudge notification.

---

## 5. Order Locks (Policy Critical)
### 5.1 Create Lock
- `POST /api/order-locks` with `locked_date` (YYYY-MM-DD), `reward_type` discount/hp.
- **Policy checks:**
  - Same-day (today WAT) → 400 `ORDER_LOCK_DATE_FUTURE`
  - Yesterday or past → 400
  - Tomorrow → 201 allowed
  - Day+7 → 201 allowed
  - Day+8 → 400 `OUT_OF_RANGE`
  - Multiple active locks per user → 400 `ALREADY_ACTIVE`
- Uses service client for insert (customers cannot INSERT directly after DB change).
- Discount/hp values read from settings, user_id from verified token.

### 5.2 List / Get / Reschedule / Cancel
- List own locks, filter by status.
- Reschedule: `PATCH /:id/reschedule` with new date within tomorrow..+7, only once (default max 1). Uses user client (allowed).
- Cancel: `DELETE /:id` uses user client.
- Admin: `GET /admin/all` with campus scoping, filters.

### 5.3 Expiry Job
- `check_order_locks` cron: active locks with `locked_date < today_wat()` → `expired`, reminder at 10,7,3,1 days.
- Live-test lifecycle: create → reschedule → place order with lock → cancel → lock active again.

### 5.4 Order Integration
- `POST /orders` with `order_lock_id`: discount applied or HP reward, lock → `used`, `order_id` set.
- Cancel order restores lock: `status active`, `order_id null` — must use `get_db()` for select & update + `.execute()`.

---

## 6. Orders & Payments
### 6.1 Create Order
- Website, whatsapp, etc. `order_source` validated against 6 values, else `other`.
- Squad order: `is_squad_order`, `squad_id`, `excluded_member_ids`, `extra_members`, snapshot via service client.
- Three follow-up updates after RPC must use service client: `squad_member_snapshot`, `order_source`, `delivery_fee`.
- Delivery fee: hostel fee or off-campus calc, squad discount, monthly free delivery perk.

### 6.2 Status Walk
- Kitchen: `received → preparing → ready → assigned → out_for_delivery → delivered` (or skip to delivered).
- Rider: assignment, pickup, delivery.
- Concurrency: reschedule race uses `reschedule_count` optimistic lock.

### 6.3 Cancel Flows
- `cancel_scheduled_order` and `cancel_order`: wallet refund, card refund, promo rollback, lock restore (service client).
- Reviews: only after delivered.

### 6.4 Guest Orders
- Guest checkout with email, claim token, later claim via register.

---

## 7. Squad — True Split + Bonus (B-7, B-8, Part D)
### 7.1 Add Members
- `POST /orders/:id/squad-members` with emails / user_ids.
- **B-7 fix:** profile lookup by email uses service client, only `id` & `campus_id`, accept only if same campus as order. No other profile details returned (privacy).
- **B-8:** refuse if order already `delivered` → 409.
- Dedupe by email lowercased, owner own row not counted twice.
- Roster: `squad_roster` insert, duplicate ignored.
- Invite email: only for truly unregistered after fix; includes `invite_link = {frontend_url}/register?ref={owner_code}&email={email}`.
- Template fix: `squad_invite` body must contain `Sign up here to join and earn HP: {invite_link}`.
- Notify registered user via `squad_order`.

### 7.2 List / Remove / Resend
- List members, remove (order-scoped, roster untouched, blocked after delivered → 400).
- Resend invite: force resend, only for unregistered.

### 7.3 Delivery Rewards — True Split
- Shared helper `squad_share_plan(order_id, hp_amount, owner_id)` reads `squad_members` via service client, fixes wrongly stored rows (B-7 robustness), returns `total_shares = 1 + distinct members`, `share = hp // total`, `owner_share = hp - share*(total-1)`.
- `_handle_delivery_rewards`: compute plan before credit; if squad members exist, call `hg_credit_delivery_hp_atomic` with `owner_share` not full amount. `orders.hp_earned` stays TOTAL order HP. Notification uses `owner_share`.

### 7.4 Distribute Squad HP
- Registered (not owner): `award_active_hp(share, source_type="squad_split", reference_type="squad_split", reference_id=order_id, apply_multiplier=False)`.
- Unregistered: `pending_squad_hp` row for share, skip if (order,email) already exists.
- Sign-up claim: `squad_split_claimed` (renamed from `squad_bonus_claimed`).
- Owner bonus: if `pct>0` and at least one other registered member, `award_active_hp(floor(hp*pct/100), source_type="squad_bonus", reference_type="squad_bonus", reference_id=order_id, apply_multiplier=False)`. Setting `squad_hp_bonus_pct` from settings, default 30, 0=split only, validated 0-100.
- hp_share update per member.
- Replay safety: `orders.squad_hp_distributed`, unique reference index, pending-row check. Old guard keyed on owner's bonus row removed.

### 7.5 Pending Claim & Sweep
- Register flow claims pending via `squad_split_claimed`.
- Daily sweep `sweep_pending_squad_hp` pays any pending row whose email now matches existing account (same logic as register claim).
- Backfill: `select p.* from pending_squad_hp p join profiles u on lower(u.email)=lower(p.email) where p.status='pending';` claim via `award_active_hp` + mark claimed.

### 7.6 Cost Control
- Total issued for squad order = order HP + bonus. Example 100 HP, 2 people, 30% → owner 50+30=80, member 50, total 130. Bonus independent of squad size.

### 7.7 Test Matrix (must be in live test after deploy)
- Setting 30, 100 HP order, owner + 1 registered: owner 50+30=80, member 50 active, `hp_earned` stays 100, total 130; replay pays 0.
- Owner + 1 registered + 1 unregistered, 100 HP: shares 33,33,34 owner remainder; unregistered pending 33; bonus 30.
- Only unregistered: split pending, no bonus.
- Setting 0: split only, no bonus.
- Adding member to delivered order → 409.
- Existing user added by email shows registered immediately.

---

## 8. HP Bundle — Init + Strict Purchase + Webhook Isolation (B-4)
### 8.1 Init
- `POST /hp/bundles/initialize` auth required, body `hp_amount`, validate min purchase & bundle price, generate unique reference, call `initialize_payment` with metadata `{"purpose":"hp_bundle","user_id":..., "hp_amount":...}`, return `authorization_url, reference, hp_amount, naira`.

### 8.2 Purchase
- `POST /hp/bundles/purchase` with `hp_amount, paystack_reference`.
- After `verify_payment`, require `metadata.purpose=="hp_bundle"`, `metadata.user_id==g.user_id`, `metadata.hp_amount==hp_amount`.
- Paid kobo == expected kobo (not <).
- Idempotency on `hp_bundle_purchases`.
- Replay of non-bundle reference must be refused.

### 8.3 Webhook Isolation
- Paystack webhook `charge.success`: if `purpose==hp_bundle` or `type==hp_bundle`, process via `process_hp_bundle_purchase` (idempotent) and return campus, never credit as order or wallet top-up.
- Flutterwave similar guard.
- Test in Paystack test mode.

---

## 9. Events & Catering & Check-in
- Events CRUD, tickets, paid tickets, QR generation (local base64, no external leak).
- Check-in: `POST /events/:id/check-in` with door QR / ticket validation, then **service client** for `event_checkins` insert only (`get_db().table("event_checkins").insert(...)`). Leave other calls as is. Deploy before A3.
- Catering: `POST /catering-requests` public, **rate limited** (10 req/60s per IP), campus_id required, notifies admins.
- List/update catering requests admin only.

---

## 10. Referrals & Squad Invite Link
- `POST /referrals/complete` stays admin repair route (called through API, no UI).
- Squad invite email link: frontend `/register?ref=CODE&email=EMAIL` reads ref & email, sends `referred_by_code`.
- Referral award on first paid order, notification.

---

## 11. Analytics & Economics (B-9)
- Economics `_HP_ISSUED_SOURCES` includes `squad_split, squad_split_claimed, squad_bonus` so HP cost reflects squad orders.
- HP analytics `/analytics/hp`: exclude `hp_transfer_received` from earned, `hp_transfer_sent` from spent, report transfers separately.
- Economics `hp_redeemed` same exclusion.
- Admin `GET /api/admin/hp/pending-squad` calls `get_pending_squad_hp_report` (A9) via authenticated RPC if available, else service client. Campus admin sees own campus, super_admin all. Use `stuck_count` as alert — should be 0 after B-7.

---

## 12. Settings & Admin
- `PATCH /admin/settings/<key>` already works for any existing key. Add validation for `squad_hp_bonus_pct`: integer 0-100 else 400 (same pattern as hp_multiplier).
- Row already exists (Part A).
- Admin audit logs for cron.

---

## 13. Webhooks
- Paystack: signature check (secret key fallback), idempotency via `webhook_events`, routing to order, ticket, marketplace, wallet, virtual account deposit, hp_bundle.
- Flutterwave: similar.
- Failure alerts to admins.

---

## 14. Scheduled Jobs
- `reset_weekly_leaderboard`, `reset_monthly_leaderboard`, `recalculate_120day_hp`, `tier_grace_period_check`, `birthday_hp_awards`, `monthly_birthday_report`, `process_scheduled_orders`, `win_back_notifications`, `hp_decay_check`, `check_order_locks`, `reset_monthly_hp_tracker`, `membership_anniversary_awards`, `send_scheduled_blasts`, `send_scheduled_notifications`, `scan_abandoned_carts`, `check_post_delivery_nudges`, `grant_monthly_tier_perks`, `send_newsletter_campaigns`, `sweep_pending_squad_hp`.
- All idempotent, cron lock via RPC.

---

## 15. Playwright E2E Full Flows (UI-level, when frontend available)
- **Happy path:** register → browse menu → add to cart → apply promo → lock date (tomorrow) → checkout wallet/card → kitchen prepares → rider delivers → HP earned → tier upgrade → free side credit → redeem reward → review.
- **Squad flow:** create squad roster → create squad order → add members (registered same campus, unregistered) → deliver → verify splits & bonus → unregistered registers via invite link → pending claimed → referral HP.
- **Order lock lifecycle:** create lock (tomorrow) → reschedule (within +7) → place order with lock → cancel order → lock active again → expiry after date passes.
- **HP bundle:** init bundle → Paystack test checkout → purchase → verify exact amount & metadata → replay non-bundle ref → 400.
- **Event:** create event → buy ticket → check-in (door QR) → HP pending → admin export.
- **Catering:** submit request (rate limit) → admin list → accept/reject → email notification.
- **Analytics:** admin views sales, payment methods, squad orders, hp ecosystem (transfers separated), economics overview (squad sources), pending squad report (stuck_count alert).
- **Edge:** delivered-order squad-add 409, same-day lock 400, day+8 lock 400, reschedule limit 400, same-campus violation treated as unregistered.

---

## 16. Contract / Smoke / E2E Suites (Backend)
- `make contract`: route self-check 168 declared vs 407 app routes.
- `make smoke`: basic health, auth, menu, order create, HP balance.
- `make e2e`: full lifecycle with `.env` (SUPABASE_URL, SERVICE_ROLE_KEY), test account, `WRITE_EXISTING=1` when using existing account, cleanup only rows created by run.
- Offline: `python -m unittest discover -s tests -v` — 21+ tests, no DB required, covers order-lock date validation, squad share plan, HP bundle metadata, rate limiting, etc.
- Live-test blockers: when env unavailable, report as blocked, do not fabricate.

---

## 17. Cleanup Rules
- E2E creates: orders, squad_members, pending_squad_hp, hp_transactions, order_locks, catering_requests, event_tickets, etc. Delete only those with `test_run_id` or created within run window.
- Never delete/reset existing account.
- Expired locks: cron marks expired, not deleted.

---

## 18. Residual Risks (Accepted)
- User with real second account can farm bonus; percentage caps worth.
- Squad invite link is guessable if ref code leaked; mitigated by campus check.

---

## 19. References
- Backend source of truth: `BACKEND_SOURCE_OF_TRUTH.md`
- API field reference: `API_FIELD_REFERENCE.md`
- Security audit: `docs/SECURITY_AUDIT.md`
- Database audit: `docs/DATABASE_AUDIT.md`
