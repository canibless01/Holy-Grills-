# RECENT HOLY GRILLS BACKEND FIXES AND FEATURES

This document details exclusively the new features, route additions, bug fixes, security enhancements, and policy refactorings implemented across the Holy Grills backend codebase.

---

## 1. Challenges Blueprint Registration (`/api/challenges`)

- **Location**: `app/__init__.py` & `app/routes/challenges.py`
- **Change**: Registered the `challenges_bp` blueprint on the Flask application under the URL prefix `/api/challenges`.
- **Endpoints Registered**:
  - `GET /api/challenges` — List active challenges (scoped to caller's campus or global).
  - `GET /api/challenges/<id>` — Get single challenge detail and user progress.
  - `POST /api/challenges/<id>/join` — Join a challenge.
  - `POST /api/challenges/<id>/claim` — Claim challenge completion reward HP.
  - `GET /api/challenges/admin/all` — Admin list all challenges (including drafts/inactive).
  - `POST /api/challenges/admin` — Admin create challenge.
  - `PATCH /api/challenges/admin/<id>` — Admin update challenge.
  - `DELETE /api/challenges/admin/<id>` — Admin soft-delete challenge.

---

## 2. Marketplace Card Payments & Webhook Fulfillment

- **Location**: `app/routes/marketplace.py` & `app/routes/webhooks.py`
- **Card Payment Initialization**:
  - `POST /api/marketplace/<listing_id>/purchase` with `payment_method="card"` or `payment_method="split"` initializes Paystack card transactions (`initialize_payment`) and returns `{ "payment_required": true, "authorization_url": "..." }`.
- **Shared Completion Helpers**:
  - Extracted `_complete_marketplace_purchase()` and `fulfill_marketplace_purchase()` to process wallet/HP-only purchases synchronously, and card-paid purchases asynchronously via Paystack and Flutterwave `charge.success` webhooks.
- **Admin Listing Deletion Foreign-Key Guard**:
  - `DELETE /api/admin/marketplace/listings/<listing_id>` verifies `marketplace_purchases` before deletion, returning HTTP `400 Bad Request` if historical purchases exist instead of raising raw database foreign-key exceptions.
- **Low Inventory Admin Alerts**:
  - `_alert_admin_low_inventory` uses service-role `get_db()` client to query admin profiles across RLS boundaries, filtered by `campus_id`.

---

## 3. Guest Campus Scoping Resolution (`_get_campus_id()`)

- **Location**: `app/routes/orders.py`, `app/routes/menu.py`, `app/routes/marketplace.py`
- **Resolution Mechanism**:
  - Replaced direct `getattr(g, 'campus_id', None)` checks with `_get_campus_id()` (imported from `app.routes.events`).
  - Evaluates campus scoping sequentially: `request.args.get("campus_id")` → `request.headers.get("X-Campus-Id")` → `session.get("campus_id")` → `None`.
- **Endpoints Scoped**:
  - `GET /api/orders/delivery-zones`
  - `GET /api/orders/delivery-windows`
  - `GET /api/menu/categories`
  - `GET /api/menu/items`
  - `GET /api/menu/addons`
  - `GET /api/menu/kitchen-capacity` (`_kitchen_stats` and `_daily_item_counts`)
  - `GET /api/menu/items/<item_id>`
  - `GET /api/marketplace` (`list_listings`)
  - `GET /api/marketplace/<listing_id>` (`get_listing`)

---

## 4. Closed-Loop Wallet-Only Refund Policy

- **Location**: `app/routes/orders.py` & `app/routes/marketplace.py`
- **Platform Policy**: 100% of order and marketplace refunds credit the customer's closed-loop wallet balance (`credit_wallet()`). No funds ever leave the platform or trigger Paystack card refunds (`refund_paystack_charge` calls removed from refund handlers).
- **Order Refunds (`POST /api/orders/<order_id>/refund`)**:
  - Calculates `total_wallet_credit = wallet_refund_allocation + card_refund_allocation` and issues a single `credit_wallet()` call.
  - Audit trail in `orders.notes` logs `[CARD_PORTION_TO_WALLET: x]`.
  - Removed `refund_to_wallet` parameter from docstrings and body expectations since all refunds are wallet-based by policy.
- **Marketplace Refunds (`PATCH /api/admin/marketplace/purchases/<purchase_id>`)**:
  - When status is updated to `refunded` or `cancelled`, both `wallet_amount` and `card_amount` portions credit `credit_wallet()`.

---

## 5. Exclusive Spin Prize Pool Database Integration & Admin CRUD

- **Location**: `app/routes/exclusive_spin.py` & `app/routes/admin.py`
- **Dynamic Prize Pool Lookup (`_spin_prizes`)**:
  - Queries `exclusive_spin_prizes` table from the database (scoped to caller's campus, falling back to global `campus_id IS NULL` rows).
  - If table is empty or unreachable, defaults to the full 8-item template list (`EXCLUSIVE_SPIN_TEMPLATE_ITEMS`).
- **Admin Prize-Pool CRUD Endpoints**:
  - `GET /api/admin/exclusive-spin-pool` — List all exclusive spin prize-pool entries with weights and active status.
  - `POST /api/admin/exclusive-spin-pool` — Create a new spin pool entry.
  - `PATCH /api/admin/exclusive-spin-pool/<prize_id>` — Update a spin pool entry (`name`, `weight`, `is_active`).
  - `DELETE /api/admin/exclusive-spin-pool/<prize_id>` — Soft-delete (deactivate) a spin pool entry.

---

## 6. Conditional Fulfillment Timestamp Stamping

- **Location**: `app/routes/admin_feature_flags.py`
- **Endpoints Updated**:
  - `PATCH /api/admin/leaderboard-prizes/<record_id>` (`fulfil_leaderboard_prize`)
  - `PATCH /api/admin/hall-of-fame-rewards/<record_id>` (`fulfil_hof_reward`)
  - `PATCH /api/admin/exclusive-spin-prizes/<record_id>` (`fulfil_exclusive_spin_prize`)
- **Behavior Fix**:
  - Only sets `fulfilled_by = g.user_id` and `fulfilled_at = now()` when `"status"` is explicitly present in the request JSON payload.
  - Notes-only PATCH updates preserve existing fulfillment timestamps and actor IDs.

---

## 7. Service Role (`get_db()`) Context & RLS Security Fixes

- **Location**: `app/services/gift_service.py`, `app/services/streak_service.py`, `app/services/hp_service.py`, `app/services/milestone_service.py`, `app/services/order_service.py`, `app/services/wallet_service.py`
- **Privilege Context Corrections**:
  - Switched from `get_user_client()` to service-role `get_db()` client in background jobs, system settings reads, delivery rewards, milestone evaluation, and streak check-in reclaims where Row Level Security (RLS) policies previously blocked operations under end-user JWT context.
- **Milestone Campus Filter Fix**:
  - Milestone queries evaluate global milestones alongside campus-specific milestones using `.or_(f"campus_id.eq.{campus_id},campus_id.is.null")`.

---

## 8. Profile Validation & Auth Hardening

- **Location**: `app/services/auth_service.py`
- **Phone Number Format Validation**: `update_profile` enforces Nigerian international format regex `^\+234\d{10}$`.
- **Minimum Age Validation**: Enforces minimum age limit (`MINIMUM_AGE` config, default 16) based on `date_of_birth`.
- **Department/Faculty Derivation**: Automatically derives and links `department` and `faculty` names when `department_id` is updated.

---

## 9. Order Processing, Squad HP & Streak Reclaim Fixes

- **Location**: `app/routes/orders.py`, `app/services/order_service.py`, `app/services/wallet_service.py`
- **Squad HP Distribution**: Fixed `NameError` in `_distribute_squad_hp` by importing `award_active_hp`.
- **Monthly Tracker Sync**: `record_order_share` invokes `update_monthly_tracker` to track social share HP against monthly caps.
- **Streak Reclaim Trigger**: `credit_wallet` triggers `try_reclaim_checkin(user_id)` when top-up meets `STREAK_RECLAIM_MIN_TOPUP` threshold.
- **Delivery Window Scoping**: Automatic delivery window assignment filters by campus ID.
- **Walk Status Authorization**: `walk_order_to_status` enforces kitchen and admin campus isolation rules matching `update_order_status`.

---

## 10. Ingredient & Stock Tracking (General Store Model)

- **Location**: `app/routes/kitchen.py` & `app/__init__.py`
- **Blueprint Registration**:
  - `units_bp` registered under `/api/measurement-units`.
  - `stock_bp` registered under `/api/admin/stock-items`.
- **Endpoints Implemented**:
  - `GET /api/measurement-units` — Return full list of measurement units (`spoon`, `sachet`, `bag`, etc.).
  - `POST /api/admin/stock-items` — Create new ingredient with buying unit, usage unit, conversion factor, low stock threshold, and campus scoping.
  - `GET /api/admin/stock-items` — List stock items with live `current_balance` and `is_low_stock` flag (`current_balance < low_stock_threshold`).
  - `POST /api/admin/stock-items/<id>/purchase` — Log incoming stock in purchase units, convert to usage units (`quantity * conversion_factor`), update balance, and record a `purchase` ledger entry.
  - `POST /api/admin/stock-items/<id>/usage` — Log stock consumption (`usage`, `waste`, `correction`) in usage units, update balance, record ledger entry, and trigger `low_stock_ingredient` notification if balance is below threshold.
  - `GET /api/admin/stock-items/<id>/ledger` — Return complete append-only ledger history for an ingredient.

---

## 11. Scheduled Marketing Engine (System 1 Consolidation)

- **Location**: `app/tasks/scheduled.py` & `app/tasks/celery_app.py`
- **Background Task (`send_scheduled_blasts`)**:
  - Scheduled Celery task running every 15 minutes (`minute="*/15"`).
  - Uses distributed cron locking (`try_acquire_cron_lock`).
  - Queries `notification_blasts` where `status = "scheduled"` and `scheduled_at <= now()`.
  - Calls `send_blast(blast_id)` for each, executing recipient resolution and updating status to `"sent"`.
  - Flagged legacy `send_scheduled_notifications` (System 2) as unused.

---

## 12. Analytics & Data Infrastructure

- **Location**: `app/routes/analytics.py` & `app/services/order_service.py`
- **Order Source Tracking**: `create_order` populates `orders.order_source` when supplied in request payload.
- **Unified 4-Branch Payment Mix**: Centralized `_derive_payment_method()` across sales, payment method, and dashboard analytics (`split`, `wallet`, `card`, `hp_or_free`).
- **Endpoints Implemented / Updated**:
  - `GET /api/analytics/order-timing` (A1) — Hourly (0-23) and weekday distributions.
  - `GET /api/analytics/addon-acceptance` (A2) — Parse `_addon_selections` JSON in `order_items` for attachment rates and top add-ons.
  - `GET /api/analytics/delivery-locations` (A3) — Order volume and revenue grouped by hostel and gate names.
  - `GET /api/analytics/squad-orders` (A4) — Squad order volume, percentage, and size distributions.
  - `GET /api/analytics/demographics` (A5) — Revenue/orders by department, faculty, level with fallback join on `departments.faculty`.
  - `GET /api/analytics/engagement` (A6) — Reviews, referrals, and event check-in engagement.
  - `GET /api/analytics/payment-methods` (A7) — Exact 4-branch payment classification.
  - `GET /api/analytics/retention-ltv` (A8) — Cohort repeat order rates and customer LTV.
  - `GET /api/analytics/referral-network` (A9) — Top referrers list and conversion stats.
  - `GET /api/analytics/hp-ecosystem` (A10) — HP circulation and distribution across all 4 tiers (Ember, Flame, Blaze/Inferno, Holy).
  - `GET /api/analytics/items-menu` (A11) — Sales quantity and revenue per dish.
  - `GET /api/analytics/revenue` (A12) — Total revenue and 4-branch payment method revenue split.
  - `GET /api/analytics/academic-calendar` (B1) — Order volume/revenue trends during active academic calendar periods.
  - `GET /api/analytics/order-sources` (B2) — Order volume by channel (`order_source`).
  - `GET /api/analytics/order-motivations` (B3) — Customer motivation breakdown from `order_motivations`.
  - `GET /api/admin/brand-partnerships` (B4) — Super-admin brand partnership requests list and status updates.

---

## 13. Part A Features & Fixes

- **Location**: `app/services/hp_service.py`, `app/routes/riders.py`, `app/routes/admin.py`, `app/routes/storefront.py`, `app/routes/rewards.py`, `app/services/streak_service.py`, `app/routes/events.py`
- **A1 — Tier Grace Fields in HP Balance**: `get_hp_balance()` returns `tier_grace_ends_at` and `tier_grace_started_at`.
- **A2 — Continuous Rider Location Ping**: `POST /api/riders/location-update` accepts `{ location_lat, location_lng }` and updates `rider_profiles`.
- **A3 — Admin Webhook Events Listing**: `GET /api/admin/webhook-events` queries `webhook_events` using service-role `get_db()` client with provider, status, date range filters and pagination.
- **A4 — Pre-Checkout Delivery Radius Config**: `GET /api/storefront/config/public` includes `max_delivery_radius_km`, `campus_lat`, and `campus_lon`.
- **A5 — Reward Redemption Fulfillment Fix**: `PATCH /api/rewards/admin/redemptions/<id>` sets `fulfilled_by = g.user_id` and server-side `fulfilled_at = now()`.
- **A6 — Order Streak HP Reward Plateau**: `_award_order_streak_hp` caps streak lookup at 12 (`min(streak_weeks, 12)`), ensuring week 13+ plateaus at 350 HP instead of matching nothing and awarding 0 HP.
- **A7 — Catering Request Status Email**: `update_catering_request` dispatches async email notifications to requesters on status transitions (`quoted`, `completed`, `cancelled`).

---

## 14. Consumer Message Centralization

- **Location**: `app/messages.py`, `app/middleware/auth.py`, and consumer route modules (`cart`, `delivery`, `events`, `exclusive_spin`, `free_sides`, `graduation`, `hp`, `marketplace`, `menu`, `order_locks`, `orders`, `saved_for_later`, `uploads`, `wallet`)
- **Central Registry (`MSG`)**: Added 32 consumer-facing error message constants.
- **Route Refactoring**: Replaced hardcoded inline error strings across consumer endpoints with centralized `MSG` references.
