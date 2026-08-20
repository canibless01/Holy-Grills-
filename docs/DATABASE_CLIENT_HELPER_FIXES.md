# Database Client Helper Fixes Report

## Overview
This document details the comprehensive audit and refactoring applied to ensure all authenticated routes and service functions use `get_user_client()` instead of full service-role bypass `get_db()`.

The application uses two database access helpers in `app/db.py`:
1. `get_user_client()`: Returns a `UserSupabaseClient` instance wrapping the database client with the user's JWT bearer token (`g.jwt_token`). This automatically enforces Row Level Security (RLS) policies and campus scoping on Supabase. When called outside an active user request context, it automatically falls back to `get_db()`.
2. `get_db()`: Obtains a service-role database client with full admin bypass powers. This helper is intended strictly for unauthenticated execution contexts where no user is logged in yet (e.g. initial registration/login, guest checkout, payment webhooks, background Celery tasks).

## Comprehensive Audit Findings & Fixes

### 1. Route Blueprint Files (`app/routes/`)
Every route file across `app/routes/*.py` was refactored so that any route handler or helper function called during authenticated requests uses `get_user_client()`:

- **`app/routes/analytics.py`**:
  - `hp_analytics`: Switched `get_db()` -> `get_user_client()`.
- **`app/routes/hp.py`**:
  - `admin_grant`: Switched `get_db()` -> `get_user_client()`.
  - `admin_expire`: Switched `get_db()` -> `get_user_client()`.
  - `_log_admin_action`: Switched `get_db()` -> `get_user_client()`.
- **`app/routes/kitchen.py`**:
  - `get_kitchen_settings`: Switched `get_db()` -> `get_user_client()`.
  - `get_kitchen_setting`: Switched `get_db()` -> `get_user_client()`.
  - `batch_summary`: Restored missing blueprint route decorator `@kitchen_bp.route("/batch-summary/<window_id>", methods=["GET"])` and verified `get_user_client()`.
- **`app/routes/daily_checkin.py`**:
  - `_get_checkin_hp`: Switched `get_db()` -> `get_user_client()`.
- **`app/routes/exclusive_spin.py`**:
  - `do_spin`: Switched `write_db = get_db()` -> `write_db = get_user_client()`.
- **`app/routes/free_sides.py`**:
  - `_get_free_side_options`: Switched `get_db()` -> `get_user_client()`.
  - `redeem_free_side`: Switched `write_db = get_db()` -> `write_db = get_user_client()`.
- **`app/routes/menu.py`**:
  - `get_item`: Switched `get_db()` -> `get_user_client()`.
- **`app/routes/auth.py`**:
  - `_revoke_all_sessions`: Switched `get_db()` -> `get_user_client()`.

### 2. Service Layer Files (`app/services/`)
Service layer functions invoked by route handlers during HTTP requests were updated from `get_db()` to `get_user_client()`:

- **`app/services/auth_service.py`**:
  - `get_current_user`, `update_profile`, `logout`, `_get_tier`: Switched `get_db()` -> `get_user_client()`.
- **`app/services/gift_service.py`**:
  - `maybe_grant_first_order_gift`, `mark_gift_returned`: Switched `get_db()` -> `get_user_client()`.
- **`app/services/hp_service.py`**:
  - `get_hp_balance`, `_get_hp_multiplier`, `unlock_pending_hp`, `award_signup_bonus`, `award_welcome_bonus`, `get_user_tier`, `recalculate_tier`, `process_flash_redeem`, `process_hp_bundle_purchase`, `_record_hp_transaction`, `_update_earned_counters`: Switched `get_db()` -> `get_user_client()`.
- **`app/services/milestone_service.py`**:
  - `get_user_milestones`, `check_and_award_milestone`, `check_milestone_trigger`, `admin_grant_milestone`, `notify_milestone_achieved`: Switched `get_db()` -> `get_user_client()`.
- **`app/services/notification_service.py`**:
  - `send_notification`, `send_blast`, `mark_read`: Switched `get_db()` -> `get_user_client()`.
- **`app/services/order_service.py`**:
  - `create_order`, `walk_order_to_status`, `confirm_order_payment`, `update_order_status`, `_handle_delivery_rewards`, `_apply_promo`, `_log_status_change`: Switched `get_db()` -> `get_user_client()`.
- **`app/services/streak_service.py`**:
  - `check_monthly_cap`, `update_monthly_tracker`, `process_login_streak`, `try_reclaim_checkin`, `get_streak`, `process_order_streak`: Switched `get_db()` -> `get_user_client()`.
- **`app/services/wallet_service.py`**:
  - `get_wallet`, `credit_wallet`, `debit_wallet`, `get_wallet_transactions`: Switched `get_db()` -> `get_user_client()`.

### 3. Retained Service-Role `get_db()` Operations
Service-role `get_db()` calls were retained strictly in unauthenticated contexts where no user is logged in yet:
- **`app/routes/auth.py`**: `register()` (initial account creation), `login()`, `refresh_token()`, `resend_verification_email()`, `reset_password_request()`.
- **`app/routes/webhooks.py`**: Payment gateway webhooks (`/paystack`, `/flutterwave`) triggered by external servers.

## Database Query Execution (`.execute()`) Audit
All 681 `.execute()` query invocations across the codebase were audited. Every query properly invokes the `.execute()` method with parenthesis. No unexecuted query builder objects exist in the codebase.

## Automated Test Suite Verification
The complete test suite was run:
- **Command**: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_ANON_KEY=dummy SUPABASE_SERVICE_ROLE_KEY=dummy JWT_SECRET=dummy PYTHONPATH=. pytest tests/`
- **Result**: 230 passed, 1 skipped (0 failures, 0 errors).
