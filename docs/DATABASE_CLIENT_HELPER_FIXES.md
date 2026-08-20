# Database Client Helper Fixes Report

## Overview
This document details the audit and fixes applied to resolve database client helper misuse across the backend application routes.

The application uses two primary database access helpers in `app/db.py`:
1. `get_user_client()`: Uses the logged-in user's JWT token (`g.jwt_token`) to wrap the database REST client. This enforces Row Level Security (RLS) policies and campus scoping automatically based on the user's login identity.
2. `get_db()`: Obtains a service-role database client with full admin bypass powers. This helper is intended strictly for unauthenticated contexts (e.g. initial registration, guest checkout, payment webhooks, background Celery cron jobs).

## Audit Findings & Fixes
Every route across `app/routes/*.py` was systematically audited to ensure that authenticated requests (`@require_auth` or `@require_role`) use `get_user_client()` rather than full service-role `get_db()`.

### Summary of Route Fixes Applied:

1. **`app/routes/analytics.py`**
   - **Endpoint**: `GET /analytics/hp` (`hp_analytics`)
   - **Decorator**: `@require_role("admin")`
   - **Fix**: Replaced `db = get_db()` with `db = get_user_client()`.
   - **Line Number**: Line 89.

2. **`app/routes/hp.py`**
   - **Endpoint**: `POST /hp/admin/grant` (`admin_grant`)
   - **Decorator**: `@require_role("admin")`
   - **Fix**: Replaced `db = get_db()` with `db = get_user_client()`.
   - **Line Number**: Line 114.
   - **Endpoint**: `POST /hp/admin/expire` (`admin_expire`)
   - **Decorator**: `@require_role("admin")`
   - **Fix**: Replaced `db = get_db()` with `db = get_user_client()`.
   - **Line Number**: Line 161.

3. **`app/routes/kitchen.py`**
   - **Endpoint**: `GET /kitchen/settings` (`get_kitchen_settings`)
   - **Decorator**: `@require_role("kitchen", "admin")`
   - **Fix**: Replaced `db = get_db()` with `db = get_user_client()`.
   - **Line Number**: Line 23.
   - **Endpoint**: `GET /kitchen/settings/<key>` (`get_kitchen_setting`)
   - **Decorator**: `@require_role("kitchen", "admin")`
   - **Fix**: Replaced `db = get_db()` with `db = get_user_client()`.
   - **Line Number**: Line 54.
   - **Endpoint**: `GET /kitchen/batch-summary/<window_id>` (`batch_summary`)
   - **Decorator**: `@require_role("kitchen", "admin")`
   - **Fix**: Restored missing route header decorator `@kitchen_bp.route("/batch-summary/<window_id>")` and verified `db = get_user_client()`.
   - **Line Number**: Line 305.

### Valid Service-Role `get_db()` Contexts (Retained):
The following contexts legitimately retain service-role `get_db()`:
- **`app/routes/auth.py`**: Session revocation helper `_revoke_all_sessions` and unauthenticated `register()` user account bootstrap.
- **`app/routes/webhooks.py`**: Unauthenticated incoming payment gateway webhooks (`/paystack`, `/flutterwave`).
- **`app/routes/daily_checkin.py`**: Public streak configuration lookup `_get_checkin_hp()`.
- **`app/routes/free_sides.py`**: Public side options lookup `_get_free_side_options()`.
- **`app/routes/menu.py`**: Public unauthenticated single item detail lookup `GET /items/<item_id>` fallback, and internal background notification/audit log helpers (`_notify_sellout`, `_log_menu_admin_action`).
- **`app/routes/exclusive_spin.py` & `app/routes/free_sides.py`**: Targeted write database client (`write_db = get_db()`) inside optimistic concurrency control (OCC) balance mutations to bypass standard RLS UPDATE blocks on credit balances after user authentication.

## Database Query Execution (`.execute()`) Audit
All 681 `.execute()` query calls across the application codebase were inspected and confirmed to be properly formatted method invocations with empty or parameter parens. No dangling `.execute` property references were found.

## Test Verification
The full automated test suite was executed:
- **Command**: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_ANON_KEY=dummy SUPABASE_SERVICE_ROLE_KEY=dummy JWT_SECRET=dummy PYTHONPATH=. pytest tests/`
- **Result**: 230 passed, 1 skipped (0 failures, 0 errors).
