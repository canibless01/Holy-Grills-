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
