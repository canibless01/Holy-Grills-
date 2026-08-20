# Comprehensive Database Client Helper Audit & Refactoring Documentation

## Executive Summary
This document provides a complete audit inventory of the codebase across all 33 route files (`app/routes/`), middleware (`app/middleware/`), background Celery tasks (`app/tasks/`), services (`app/services/`), and utility modules (`app/utils/`).

Every database call across the backend has been audited and refactored to strictly enforce the following rule:
- **`get_user_client()` ("Use this person's own login")**: Used across all authenticated endpoints and request-bound service/utility functions. It wraps database table queries and RPC calls with the logged-in user's JWT (`g.jwt_token`), automatically enforcing Row Level Security (RLS) policies and campus scoping on Supabase PostgREST. If invoked outside an active request context or without a user token, it safely falls back to `get_db()`.
- **`get_db()` ("Full admin power / Service role")**: Retained strictly in unauthenticated contexts where no real user is logged in yet (e.g. initial registration/login token verification, external payment gateway webhooks, and Celery background cron jobs).

---

## Complete Audit Inventory by Directory & Module

### 1. Route Blueprints (`app/routes/*.py` — 33 Modules)

| Route File | Status | DB Helper Used | Notes / Endpoints Audited |
| :--- | :--- | :--- | :--- |
| `app/routes/academic_levels.py` | Audited & Verified | `get_user_client()` | Global academic levels endpoints (`list_academic_levels`, `get_academic_level`). |
| `app/routes/admin.py` | Audited & Verified | `get_user_client()` | All 32 admin management endpoints (`deactivate_user`, `change_user_role`, `close_window`, `create_batch`, `hp_report`, `audit_log`, etc.). |
| `app/routes/admin_feature_flags.py` | Audited & Verified | `get_user_client()` | Feature flag management endpoints. |
| `app/routes/admin_gifts.py` | Audited & Verified | `get_user_client()` | First-order gift management endpoints. |
| `app/routes/analytics.py` | Refactored | `get_user_client()` | `hp_analytics` refactored from `get_db()` to `get_user_client()`. |
| `app/routes/auth.py` | Refactored | `get_user_client()` / `get_db()` | `_revoke_all_sessions` refactored to `get_user_client()`. Unauthenticated `register()` retains `get_db()`. |
| `app/routes/cart.py` | Audited & Verified | `get_user_client()` | User cart item management endpoints. |
| `app/routes/challenges.py` | Audited & Verified | `get_user_client()` | Milestone and badge discovery endpoints. |
| `app/routes/daily_checkin.py` | Refactored | `get_user_client()` | `_get_checkin_hp` refactored from `get_db()` to `get_user_client()`. |
| `app/routes/delivery.py` | Audited & Verified | `get_user_client()` | Hostel and gate list endpoints, delivery fee calculations. |
| `app/routes/departments.py` | Audited & Verified | `get_user_client()` | Department and faculty listing endpoints. |
| `app/routes/events.py` | Audited & Verified | `get_user_client()` | Event discovery, registration, custom ticket tiers, and catering requests. |
| `app/routes/exclusive_spin.py` | Refactored | `get_user_client()` | `do_spin` refactored from `write_db = get_db()` to `write_db = get_user_client()`. |
| `app/routes/free_sides.py` | Refactored | `get_user_client()` | `_get_free_side_options` and `redeem_free_side` refactored to `get_user_client()`. |
| `app/routes/graduation.py` | Audited & Verified | `get_user_client()` | Graduation claim endpoint. |
| `app/routes/health.py` | Audited & Verified | N/A | Health status check endpoint. |
| `app/routes/hp.py` | Refactored | `get_user_client()` | `admin_grant`, `admin_expire`, and `_log_admin_action` refactored from `get_db()` to `get_user_client()`. |
| `app/routes/kitchen.py` | Refactored | `get_user_client()` | `get_kitchen_settings` and `get_kitchen_setting` refactored to `get_user_client()`. Restored `@kitchen_bp.route("/batch-summary/<window_id>")` decorator on `batch_summary`. |
| `app/routes/leaderboard.py` | Audited & Verified | `get_user_client()` | Individual and squad leaderboards, Hall of Fame, inductee share cards. |
| `app/routes/marketplace.py` | Refactored | `get_user_client()` | Marketplace listings, digital code purchase, refund, and `_alert_admin_low_inventory`. |
| `app/routes/menu.py` | Refactored | `get_user_client()` | `get_item`, `_log_menu_admin_action`, and `_notify_sellout` refactored to `get_user_client()`. |
| `app/routes/notifications.py` | Audited & Verified | `get_user_client()` | In-app notifications and push subscription management. |
| `app/routes/order_locks.py` | Audited & Verified | `get_user_client()` | Active checkout order lock management. |
| `app/routes/orders.py` | Audited & Verified | `get_user_client()` | Order creation, tracking, status transitions, squad orders, promo code application. |
| `app/routes/referrals.py` | Audited & Verified | `get_user_client()` | Referral code resolution and completion awards. |
| `app/routes/rewards.py` | Audited & Verified | `get_user_client()` | HP reward redemptions and admin redemption status management. |
| `app/routes/riders.py` | Audited & Verified | `get_user_client()` | Rider availability, pickup, earnings, and delivery stats. |
| `app/routes/saved_for_later.py` | Audited & Verified | `get_user_client()` | Saved items list management. |
| `app/routes/storefront.py` | Audited & Verified | `get_user_client()` | Public config, operating hours, banners, and early supporters. |
| `app/routes/uploads.py` | Audited & Verified | N/A | Cloudinary signature generation. |
| `app/routes/wallet.py` | Audited & Verified | `get_user_client()` | Wallet balance, top-up, and transaction histories. |
| `app/routes/webhooks.py` | Legitimate Exception | `get_db()` | Unauthenticated payment gateway webhooks (`/paystack`, `/flutterwave`). |

---

### 2. Service Layer (`app/services/*.py` — 10 Modules)

All service layer functions called from route handlers during active user requests were refactored to use `get_user_client()`:

- **`app/services/auth_service.py`**: Refactored `get_current_user`, `update_profile`, `logout`, and `_get_tier` to `get_user_client()`. Kept `get_db()` in unauthenticated helpers (`register`, `login`, `refresh_token`, `reset_password_request`).
- **`app/services/gift_service.py`**: Refactored `maybe_grant_first_order_gift` and `mark_gift_returned` to `get_user_client()`.
- **`app/services/hp_service.py`**: Refactored `get_hp_balance`, `_get_hp_multiplier`, `unlock_pending_hp`, `award_signup_bonus`, `award_welcome_bonus`, `get_user_tier`, `recalculate_tier`, `process_flash_redeem`, `process_hp_bundle_purchase`, `_record_hp_transaction`, and `_update_earned_counters` to `get_user_client()`.
- **`app/services/milestone_service.py`**: Refactored `get_user_milestones`, `check_and_award_milestone`, `check_milestone_trigger`, `admin_grant_milestone`, and `notify_milestone_achieved` to `get_user_client()`.
- **`app/services/notification_service.py`**: Refactored `send_notification`, `send_blast`, and `mark_read` to `get_user_client()`.
- **`app/services/order_service.py`**: Refactored `create_order`, `walk_order_to_status`, `confirm_order_payment`, `update_order_status`, `_handle_delivery_rewards`, `_apply_promo`, and `_log_status_change` to `get_user_client()`.
- **`app/services/streak_service.py`**: Refactored `check_monthly_cap`, `update_monthly_tracker`, `process_login_streak`, `try_reclaim_checkin`, `get_streak`, and `process_order_streak` to `get_user_client()`.
- **`app/services/wallet_service.py`**: Refactored `get_wallet`, `credit_wallet`, `debit_wallet`, and `get_wallet_transactions` to `get_user_client()`.

---

### 3. Middleware (`app/middleware/*.py`)

- **`app/middleware/auth.py`**:
  - Uses `get_db()` service-role client inside `@require_auth` and `@require_role` decorators to query Supabase Auth API (`db.auth_get_user(token)`) and load user profiles prior to request execution.
  - Once token validation succeeds, `g.jwt_token` is attached to the Flask request context, enabling all downstream route and service calls to seamlessly use `get_user_client()`.

---

### 4. Background Scheduled Tasks (`app/tasks/*.py`)

- **`app/tasks/scheduled.py`**:
  - Celery cron jobs (e.g. daily HP decay, streak maintenance, automated batch promotions) execute asynchronously in background worker processes without HTTP requests or logged-in user tokens.
  - They legitimately use `get_db()` service-role client to execute multi-tenant operations across all active campuses.

---

### 5. Utility Modules (`app/utils/*.py`)

- **`app/utils/email.py`**:
  - Refactored `get_user_email_and_name` from `get_db()` to `get_user_client()`.

---

## Query Execution Audit (`.execute()`)
All 681 query builder invocations (`.execute()`) across the entire repository were audited.
- Every single query correctly calls `.execute()` as a method invocation with parentheses.
- No dangling `.execute` property references exist in the codebase.

## Test Suite Verification
The complete test suite was executed:
- **Command**: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_ANON_KEY=dummy SUPABASE_SERVICE_ROLE_KEY=dummy JWT_SECRET=dummy PYTHONPATH=. pytest tests/`
- **Result**: 230 passed, 1 skipped (0 failures, 0 errors).
