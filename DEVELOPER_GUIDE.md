# Holy Grills Backend — Developer Guide

This guide is the single reference for any developer picking up this codebase. Read it top to bottom once, then use it as a reference.

---

## Contents

1. [Architecture Overview](#1-architecture-overview)
2. [App Startup Flow](#2-app-startup-flow)
3. [Database Layer](#3-database-layer)
4. [Authentication & Middleware](#4-authentication--middleware)
5. [How to Add a New Endpoint](#5-how-to-add-a-new-endpoint)
6. [How to Add a New Background Task](#6-how-to-add-a-new-background-task)
7. [HP Economy Internals](#7-hp-economy-internals)
8. [Order State Machine](#8-order-state-machine)
9. [Notifications](#9-notifications)
10. [Payments (Paystack)](#10-payments-paystack)
11. [Messages & Copy](#11-messages--copy)
12. [Logging](#12-logging)
13. [Retry Logic](#13-retry-logic)
14. [Error Handling](#14-error-handling)
15. [Configuration Reference](#15-configuration-reference)
16. [Common Pitfalls](#16-common-pitfalls)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────┐
│  Mobile App (React Native / Flutter)            │
└────────────────────┬────────────────────────────┘
                     │  HTTPS + JWT
                     ▼
┌─────────────────────────────────────────────────┐
│  Flask API  (this repo)                         │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ Routes   │  │ Services  │  │ Middleware   │ │
│  │ (HTTP)   │→ │ (logic)   │  │ (auth/rl)   │ │
│  └──────────┘  └─────┬─────┘  └──────────────┘ │
└────────────────────── │ ────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   Supabase         Paystack        OneSignal
 (PostgreSQL        (payments)      (push/email)
  via REST)
        │
        ▼
     Celery + Redis
   (background jobs)
```

**Key design decisions:**

- **No direct PostgreSQL connection.** All DB queries use the Supabase REST API through a custom HTTP client (`app/db.py`). This avoids the need for a persistent connection pool and works in environments where TCP 5432 is blocked.
- **Fire-and-forget notifications.** Every call to `send_notification()` that triggers an email or push runs in a daemon thread, so the HTTP response is never delayed by notification I/O.
- **Webhook-driven payment confirmation.** The API never trusts client-side payment success. Only Paystack/Flutterwave webhooks confirm payments (`app/routes/webhooks.py`).

---

## 2. App Startup Flow

```
run.py
  └── create_app(config_class)          ← app/__init__.py
        ├── Flask()
        ├── CORS(app, ...)
        ├── Swagger(app, ...)
        ├── register all blueprints
        └── register global error handlers
```

`run.py` selects the config class based on `FLASK_ENV` (`development` → `DevelopmentConfig`, `production` → `ProductionConfig`), then calls `create_app()`.

All blueprints are registered in `app/__init__.py`. To add a new route module, create the blueprint file and add two lines there (import + register).

---

## 3. Database Layer

**File:** `app/db.py`

The `SupabaseClient` class wraps the Supabase PostgREST REST API. It provides a chainable query builder that mimics the Supabase JS client:

```python
from app.db import get_db

db = get_db()

# SELECT
rows = db.table("orders").select("id,status").eq("user_id", uid).execute()

# INSERT (returns list of inserted rows)
result = db.table("orders").insert({"user_id": uid, "status": "received"})

# UPDATE
db.table("orders").eq("id", order_id).update({"status": "preparing"})

# DELETE
db.table("orders").eq("id", order_id).delete()

# Single row (raises if multiple)
row = db.table("profiles").select("*").eq("id", uid).single().execute()

# RPC (Postgres function)
db.rpc("try_acquire_cron_lock", {"p_job_name": "reset_monthly_leaderboard"})
```

`get_db()` returns a cached singleton — safe to call multiple times per request.

**Important:** Because this is a REST client, not a real SQL ORM, there is **no JOIN support**. Fetch related records in separate calls or use Supabase's nested select syntax where supported (`orders(*,order_items(*))` returns nested JSON from PostgREST).

---

## 3b. JWT Silent Rotation (`POST /api/auth/refresh`)

The refresh endpoint is designed so the mobile app can call it on every app-foreground event without hammering Supabase.

**How it works:**

1. Client sends `{ refresh_token, access_token? }`.
2. Server decodes the `access_token` **without signature verification** to read the `exp` claim.
   - Security note: signature verification is intentionally skipped here because we only need the expiry timestamp, not identity assurance. All real security enforcement happens inside Supabase's `auth_refresh` call in step 4. This also avoids a silent failure where a mismatch between `JWT_SECRET` and Supabase's actual signing key caused the TTL optimisation to never fire.
3. If more than `JWT_REFRESH_WINDOW_MINUTES` remain → returns `{ rotated: false, access_token: <same> }`. No Supabase call is made.
4. If fewer than `JWT_REFRESH_WINDOW_MINUTES` remain, or the token is already expired, or `access_token` is omitted → calls Supabase, returns fresh tokens with `{ rotated: true, access_token, refresh_token }`.

**Window size is configurable** via `JWT_REFRESH_WINDOW_MINUTES` (default 5 minutes). Set it in `.env` or environment secrets.

**Rate limit:** 30 requests per minute per IP (`RATE_LIMIT_REFRESH_REQUESTS` / `RATE_LIMIT_REFRESH_WINDOW`).

**Mobile app pattern:**

```dart
// Call on every app foreground — only hits Supabase when necessary
final resp = await api.post('/auth/refresh', {
  'refresh_token': storedRefreshToken,
  'access_token':  storedAccessToken,   // optional but prevents unnecessary rotation
});
if (resp['rotated']) {
  // Store the new tokens
  storedAccessToken  = resp['access_token'];
  storedRefreshToken = resp['refresh_token'];
}
// Always use resp['access_token'] for subsequent requests
```

---

## 3c. Email Verification Resend (`POST /api/auth/verify-email`)

For users who registered but never confirmed their email (or whose confirmation link expired):

```json
POST /api/auth/verify-email
{ "email": "student@futa.edu.ng" }

→ 200 { "message": "If your email is not yet confirmed, a new verification link has been sent. Check your inbox." }
```

**Security design:**
- Always returns the same 200 response regardless of whether the email exists or is already confirmed (prevents email enumeration).
- Supabase returns HTTP 422 when the address is already confirmed; the server silently swallows it.
- Rate-limited to **3 requests per hour** per IP (`RATE_LIMIT_VERIFY_EMAIL_REQUESTS` / `RATE_LIMIT_VERIFY_EMAIL_WINDOW`).
- No authentication required — this is a pre-login flow.

**Mobile app flow:**
1. User taps "Resend verification email" on the "Check your inbox" screen.
2. POST `{ email }` to this endpoint.
3. Show the same confirmation message regardless of the response body.

---

## 3d. Device Token Registration (`POST /api/auth/device-token`)

Register a push-notification device token immediately after the user grants push permission in the app. The token is a OneSignal `subscription_id` (v5+ SDK) or `player_id` (legacy SDK).

```json
POST /api/auth/device-token
Authorization: Bearer <access_token>
{
  "token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "platform": "ios",
  "device_model": "iPhone 15 Pro"
}
→ 201 { "message": "Device token registered", "token": "..." }
→ 200 { "message": "Device token updated",     "token": "..." }
→ 400 { "error": "'token' is required" }
```

**SDK pairing (required for push to work):** The mobile SDK must also call `OneSignal.login(userId)` so the subscription is linked to the user's `external_id`. The server fans out push notifications using `external_id` targeting — without this call, push delivery to that device will fail silently.

---

## 4. Authentication & Middleware

**Files:** `app/middleware/auth.py`, `app/middleware/rate_limit.py`

### Protecting an endpoint

```python
from app.middleware.auth import require_auth, require_role

@bp.route("/my-endpoint", methods=["GET"])
@require_auth          # sets g.user_id, g.user, g.user_role, g.jwt_token
def my_endpoint():
    user_id = g.user_id   # UUID string
    ...

@bp.route("/admin-only", methods=["POST"])
@require_role("admin")   # implies require_auth; 403 if role != admin
def admin_only():
    ...
```

### How auth works

1. Client sends `Authorization: Bearer <access_token>`.
2. `require_auth` calls **Supabase's `/auth/v1/user` endpoint** with the token (live validation — not local JWT decode). This is the only security check; no local JWT verification is performed.
3. On success, `g.user_id`, `g.jwt_payload`, and `g.jwt_token` are set.
4. A second query loads the user's profile from the `profiles` table and sets `g.user` and `g.user_role`.
5. If the profile has `is_active = false`, a 403 is returned.

> **Note:** `JWT_SECRET` / `SUPABASE_JWT_SECRET` are **not** used by `require_auth` or `require_role`. Those decorators always validate live against Supabase. `JWT_SECRET` is only referenced in the refresh endpoint's TTL optimisation (and there it is used without signature verification, so it doesn't need to match Supabase's signing key).

### Rate limiting

```python
from app.middleware.rate_limit import rate_limit

@bp.route("/login", methods=["POST"])
@rate_limit("RATE_LIMIT_LOGIN_REQUESTS", "RATE_LIMIT_LOGIN_WINDOW")
def login():
    ...
```

Both arguments can be an `int` (hard-coded) or a `str` config key (env-backed). Limits are IP-based and use in-memory storage — they reset on server restart. In production with multiple workers, swap for a Redis-backed limiter.

**Configured rate limits:**

| Endpoint | Env var prefix | Default |
|---|---|---|
| `POST /auth/register` | `RATE_LIMIT_REGISTER_*` | 10 req / 1 hr |
| `POST /auth/login` | `RATE_LIMIT_LOGIN_*` | 20 req / 15 min |
| `POST /auth/refresh` | `RATE_LIMIT_REFRESH_*` | 30 req / 1 min |
| `POST /auth/verify-email` | `RATE_LIMIT_VERIFY_EMAIL_*` | 3 req / 1 hr |
| `POST /auth/reset-password` | `RATE_LIMIT_RESET_PW_*` | 5 req / 1 hr |

---

## 5. How to Add a New Endpoint

**Example:** Adding `GET /api/specials` to list today's specials.

### Step 1 — Create the route file (if new domain)

```python
# app/routes/specials.py
from flask import Blueprint, jsonify, g
from app.middleware.auth import require_auth
from app.db import get_db

specials_bp = Blueprint("specials", __name__)

@specials_bp.route("", methods=["GET"])
@require_auth
def list_specials():
    """
    List today's specials.
    ---
    tags: [Specials]
    responses:
      200:
        description: List of specials
    """
    db = get_db()
    rows = db.table("specials").select("*").eq("is_active", "true").execute()
    return jsonify(rows), 200
```

### Step 2 — Register the blueprint in `app/__init__.py`

```python
# add import
from app.routes.specials import specials_bp

# add inside create_app():
app.register_blueprint(specials_bp, url_prefix="/api/specials")
```

### Step 3 — Handle errors consistently

```python
try:
    result = some_service_call()
    return jsonify(result), 200
except ValueError as e:
    return jsonify({"error": str(e)}), 400
except Exception as e:
    logger.error("specials error: %s", e)
    return jsonify({"error": "An unexpected error occurred"}), 500
```

That's it. The Swagger docs at `/api/docs/` will automatically pick up the new endpoint.

---

## 6. How to Add a New Background Task

**File:** `app/tasks/scheduled.py`

```python
from app.tasks.celery_app import celery_app
from app.db import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)

@celery_app.task(name="app.tasks.scheduled.my_new_task", bind=True, max_retries=3)
def my_new_task(self):
    """Describe what this task does and when it runs."""
    db = get_db()
    try:
        # Acquire idempotency lock (prevents duplicate runs)
        lock = db.rpc("try_acquire_cron_lock", {"p_job_name": "my_new_task"})
        if not lock:
            return {"skipped": "Lock not acquired"}
    except Exception:
        pass  # proceed if lock table doesn't exist

    try:
        # ... your task logic here ...
        return {"processed": 0}
    except Exception as e:
        logger.error("my_new_task failed: %s", e)
        raise self.retry(exc=e, countdown=60)
    finally:
        try:
            db.rpc("release_cron_lock", {"p_job_name": "my_new_task"})
        except Exception:
            pass
```

Register it in your Celery beat schedule (celery_app.py or via `CELERYBEAT_SCHEDULE`).

---

## 7. HP Economy Internals

**File:** `app/services/hp_service.py`

HP is tracked in the `hp_transactions` table with statuses `active` or `pending`. Key operations:

| Function | What it does |
|----------|-------------|
| `award_active_hp(user_id, amount, ...)` | Credit HP directly to active balance |
| `award_pending_hp(user_id, amount, ...)` | Credit HP to pending pool |
| `spend_hp(user_id, amount, ...)` | Debit active HP (raises ValueError if insufficient) |
| `expire_hp(user_id, amount, notes)` | Mark HP as expired |
| `get_hp_balance(user_id)` | Return `{active, pending, lifetime}` |
| `get_user_tier(user_id)` | Return current tier row from `hp_tiers` |
| `recalculate_tier(user_id)` | Re-evaluate tier based on 120-day HP; returns `{changed, tier}` |
| `award_food_order_hp(...)` | Full food-order HP flow: base earn + tier bonus + unlock pending |
| `award_welcome_bonus(user_id, order_id)` | 50 HP (configurable) on first-ever order, idempotent |

### Earn rates (from config)

- **Food orders:** `HP_PER_NAIRA_FOOD` HP per ₦ (default 0.1 = 1 HP / ₦10)
- **Tier bonus:** Multiplier applied on top of base earn (e.g. 1.25× for Champion tier)
- **Pending unlock:** 100 HP unlocked per ₦1,000 food spend (`HP_UNLOCK_RATE`)
- **Welcome bonus:** `WELCOME_BONUS_HP` (default 50)
- **Birthday:** `BIRTHDAY_HP` (default 150)
- **Referral:** `REFERRAL_HP` (default 75)

---

## 8. Order State Machine

**File:** `app/services/order_service.py`

```
received ──► preparing ──► ready ──► assigned ──► out_for_delivery ──► delivered
    │             │           │          │                │
    └─────────────┴───────────┴──────────┴────────────────┴──► cancelled
                                                                  │
                                                               refunded

out_for_delivery ──► delivery_attempted ──► unclaimed ──► cancelled
```

Use `walk_order_to_status(order_id, target_status)` to jump across multiple states in one call (BFS finds the shortest valid path). Use `update_order_status(order_id, new_status)` for a single hop.

HP is awarded automatically when an order reaches `delivered`.

---

## 9. Notifications

**File:** `app/services/notification_service.py`, `app/utils/email.py`

```python
from app.services.notification_service import send_notification

send_notification(
    user_id=user_id,
    notif_type="order_confirmed",          # used for filtering in the app
    title="Order Confirmed!",
    body="Your order is heading to the kitchen.",
    reference_id=order_id,
    reference_type="order",
    channels=["in_app", "email", "push"],  # default: ["in_app"]
)
```

- **`in_app`** — inserts a row into the `notifications` table (the mobile app polls this).
- **`email`** — dispatches via OneSignal email API in a daemon thread.
- **`push`** — dispatches via OneSignal push API in a daemon thread; requires the user to have registered a push subscription with their `user_id` as `external_id` (see §3d above).

Email bodies use the `TEMPLATES` dict in `app/utils/email.py`. To add a new email template, add an entry there and call `send_email(to_email, to_name, "template_key", data)`.

### Push-notification types used by the server

| `notif_type` | When sent | Channels |
|---|---|---|
| `hp_expiry_warning_14` | User inactive 76–87 days (once per 14-day window) | in_app, email |
| `hp_expiry_warning_3`  | User inactive 87–90 days (once per 7-day window)  | in_app, push  |
| `hp_expired`           | User inactive 90+ days — HP breakage applied      | in_app, email |
| `abandoned_cart`       | Cart inactive ≥ `ABANDONED_CART_MINUTES` (once/24h per user) | in_app, push |
| `wallet_funded`        | Paystack charge.success or bank transfer confirmed | in_app, email |

---

## 10. Payments (Paystack)

**File:** `app/services/payment_service.py`

| Function | Description |
|----------|-------------|
| `initialize_payment(email, amount_naira, reference, ...)` | Start a card payment; returns `authorization_url` |
| `verify_payment(reference)` | Verify a transaction by reference |
| `create_virtual_account(user_id, email, full_name, phone)` | Provision a Dedicated NUBAN |
| `verify_webhook_signature(payload_bytes, signature)` | HMAC-SHA512 validation for Paystack webhooks |

**Never confirm a payment from the client.** The flow is always:
1. Client calls `POST /api/wallet/fund/card` → gets `authorization_url`
2. User pays on Paystack
3. Paystack sends webhook to `POST /api/webhooks/paystack`
4. Server verifies HMAC, then updates order/wallet

### Webhook idempotency

Paystack retries failed webhooks (any 5xx response triggers a retry). The server guards against double-processing for `charge.success` and `transfer.success` by checking `payment_transactions` for an existing record with the same `payment_reference` before executing any business logic. If a record already exists, the handler returns `200 Already processed` immediately.

`dedicatedaccount.assign.success` events are naturally idempotent (updating the same virtual-account row twice is a no-op) and do not need this guard.

---

## 11. Messages & Copy

**File:** `app/messages.py`

All user-facing strings are defined in the `MSG` class. This is the **only** place you should change copy.

```python
from app.messages import MSG

# In a route
return jsonify({"message": MSG.PASSWORD_CHANGED}), 200

# In a service
send_notification(title=MSG.ORDER_CONFIRMED_TITLE, body=MSG.ORDER_CONFIRMED_BODY.format(...))

# Email subjects
"subject": MSG.EMAIL_ORDER_CONFIRMED
```

To change wording, edit `app/messages.py`. No other file needs to change.

---

## 12. Logging

**File:** `app/utils/logger.py`

```python
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Info
logger.info("Order created | order_id=%s user_id=%s total=%s", order_id, user_id, total)

# Warning
logger.warning("Payment retry | attempt=%d ref=%s", attempt, ref)

# Error
logger.error("Supabase insert failed | table=%s error=%s", table, exc)
```

Log format:
```
[INFO]  2025-01-15 12:34:56 | app.services.order_service | Order created | order_id=abc user_id=xyz
[ERROR] 2025-01-15 12:34:57 | app.services.payment_service | Paystack call failed | error=...
```

Never use `print()` — it bypasses the log level system and can't be filtered.

---

## 13. Retry Logic

**File:** `app/utils/retry.py`

External API calls (Paystack, OneSignal) are wrapped with `@with_retry` to handle transient network failures:

```python
from app.utils.retry import with_retry

@with_retry(max_attempts=3, backoff=0.5)
def call_paystack_api():
    return requests.post(...)
```

The decorator retries on `ConnectionError`, `TimeoutError`, and HTTP 429/5xx responses, with exponential backoff. All retry activity is logged automatically.

---

## 14. Error Handling

Global HTTP error handlers live in `app/__init__.py`. They return consistent JSON for every status code — including 405 (Method Not Allowed), which Flask would otherwise return as HTML:

```json
{ "error": "Not found", "message": "...", "request_id": "abc123" }
```

Handled codes: `400`, `401`, `403`, `404`, `405`, `500`, plus a catch-all `Exception` handler.

In routes, raise Python errors to the appropriate handler:

```python
# 400 — bad input
return jsonify({"error": "amount is required"}), 400

# 404 — resource missing
return jsonify({"error": "Order not found"}), 404

# 405 — wrong method (handled automatically by Flask + the global handler)

# 500 — unexpected (always log these)
logger.error("Failed to process order: %s", exc)
return jsonify({"error": MSG.ERR_SERVER}), 500
```

---

## 15. Configuration Reference

All configuration comes from environment variables via `app/config.py`. You can add new config values there and access them anywhere with:

```python
from flask import current_app
value = current_app.config["MY_VAR"]
```

Or at import time (outside Flask context):

```python
import os
value = os.environ.get("MY_VAR", "default")
```

---

## 16a. Seeding the Database

Two seed options — both are fully idempotent (safe to run multiple times):

| Method | Command | When to use |
|--------|---------|-------------|
| **Python** (Supabase REST) | `python scripts/seed.py` | Works anywhere — no direct DB access needed |
| **SQL** (psql / SQL Editor) | `psql "$DATABASE_URL" -f scripts/seed.sql` | Supabase SQL Editor or CI pipelines with direct DB access |

Both seed the same 8 tables in FK-dependency order. After seeding, all API endpoints that depend on menu data, operating hours, promo codes, and delivery windows will work.

---

## 16. Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| Calling `current_app` outside app context | Use `with app.app_context():` or pass the value as an argument |
| Forgetting `.execute()` at the end of a query chain | Every query must end with `.execute()` — without it nothing runs |
| `single()` on a query that returns 0 rows | Returns `None`, not an exception — always check for `None` |
| Sending notifications synchronously in a hot path | Wrap in a daemon thread or use `channels=["in_app"]` only |
| Hardcoding strings | Add to `app/messages.py` and import `MSG` |
| Using `print()` for errors | Use `logger = get_logger(__name__)` and `logger.error(...)` |
| Trusting client-side payment confirmation | Always wait for the Paystack webhook before marking payment as paid |
| Not handling `is_squad_order` column absence | The insert in `order_service.py` falls back gracefully — keep that pattern for any new optional columns |
| `SupabaseError` vs `ValueError` in route handlers | `db.*` methods raise `SupabaseError`, not `ValueError`. Catch both when you need to distinguish user errors from system errors. For auth endpoints, only map `SupabaseError` with `status_code in (400, 401)` to user-facing 401 — re-raise or return 500 for all others. |
| Over-broad `except Exception` on DB fallbacks | When falling back after a migration-gated column, catch only `SupabaseError` and verify the message contains `"column"` + `"does not exist"` before retrying. Re-raise anything else. |

---

## 17. Live Test Suite

`scripts/live_test.py` — full end-to-end suite against live Supabase. Creates a real test user, exercises 43 endpoints, then hard-deletes all test records (Supabase Auth user + profile + newsletter row).

```bash
python scripts/live_test.py
```

**Last result (2026-07-04):** 44 PASS · 0 FAIL · 1 WARN (cart skipped — empty DB, not a bug)

### Endpoints added / strengthened in this session
| Endpoint | Change |
|----------|--------|
| `POST /api/auth/login` | Fixed: wrong password now returns 401 (was 500). `SupabaseError` mapped by status code — 5xx auth errors still surface as 500. |
| `POST /api/auth/addresses` | Fixed: `state` defaults to `""` when omitted, satisfying DB NOT NULL constraint. |
| `DELETE /api/menu/items/<id>/addon-groups/<gid>` | **New** (admin only). Verifies ownership then hard-deletes; cascades to linked `menu_addons` rows via FK. |
| `POST /api/orders/<id>/review` | **Strengthened.** Now accepts optional `kitchen_rating` and `rider_rating` (1–5 integers) for kitchen/rider performance tracking. Falls back gracefully if migration 16 has not yet been applied. |

All public endpoints, auth flow (including wrong-password 401), address CRUD, token refresh, order lifecycle, HP balance/transactions, wallet, notifications, referrals, challenges, storefront, delivery windows/zones confirmed working against live Supabase.

### Background tasks added (app/tasks/scheduled.py + celery_app.py)
| Task | Schedule | Purpose |
|------|----------|---------|
| `process_scheduled_orders` | Every 5 min | Finds scheduled orders whose `scheduled_for` time has passed and notifies kitchen/admin staff via in-app notification. Dedupes within a 10-minute window so repeated runs don't spam staff. |

### Pending migrations (run in Supabase SQL Editor)
The following additions are in `migrations/schema.sql` and must be applied before the new columns are live:

| Section | What it adds |
|---------|-------------|
| 16 | `kitchen_rating` and `rider_rating` SMALLINT (nullable, CHECK 1–5) on `order_reviews` |
| 17 | `jwt_version` INTEGER NOT NULL DEFAULT 0 on `profiles` (for future token-invalidation support) |

The review endpoint works without these — it falls back to the old schema automatically until the migration runs.
