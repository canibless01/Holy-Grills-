# Holy Grills Backend API

**Holy Grills** is a student-focused food ordering and loyalty-points platform built for FUTA. This repository contains the Flask REST API that powers the mobile app — handling orders, payments, HP (Holy Points) economy, user tiers, events, marketplace, wallet, and admin operations.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Quick Start](#quick-start)
3. [Environment Variables](#environment-variables)
4. [Running the App](#running-the-app)
5. [API Documentation](#api-documentation)
6. [Project Structure](#project-structure)
7. [Key Concepts](#key-concepts)
8. [Testing](#testing)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Flask 3.x |
| Database | Supabase (PostgreSQL via REST API) |
| Auth | Supabase Auth + custom JWT middleware |
| Payments | Paystack (card + virtual accounts) |
| Notifications | OneSignal (push + email) |
| Background Jobs | Celery + Redis |
| API Docs | Flasgger (Swagger UI) |

---

## Quick Start

```bash
git clone <repo-url>
cd holy-grills-backend
make setup      # create .venv, install dependencies, create .env if missing
make check      # connect to Supabase (validates keys, project ref, signatures)
make smoke      # read-only end-to-end run against the live project
make e2e        # full end-to-end run (creates its own test user, deletes it after)
make server     # start the API on :5000
```

`make` on its own lists every target. Requires Python 3.9+.

**No `make`** (plain Windows, some CI images)? Do the same by hand:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
cp .env.example .env                          # then fill in the Supabase values
.venv/bin/python scripts/check_supabase.py
.venv/bin/python scripts/live_test.py --read-only
.venv/bin/python run.py
```

**Already have a virtualenv elsewhere?** Point `make` at it:
`make check VENV=../.venv`

Celery worker and beat, when you need background jobs:

```bash
celery -A app.tasks.celery_app worker --loglevel=info
celery -A app.tasks.celery_app beat --loglevel=info
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in every **REQUIRED** value before starting the server.

### Required

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session secret (any long random string) |
| `JWT_SECRET` | Secret used to sign/verify JWT tokens |
| `SUPABASE_URL` | Your Supabase project URL (`https://xxx.supabase.co`) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key (server-side only — never expose to clients) |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `PAYSTACK_SECRET_KEY` | Paystack secret key (`sk_live_...` or `sk_test_...`) |
| `PAYSTACK_PUBLIC_KEY` | Paystack public key |
| `PAYSTACK_WEBHOOK_SECRET` | HMAC secret for verifying Paystack webhook signatures |
| `ONESIGNAL_APP_ID` | OneSignal App ID (for push + email notifications) |
| `ONESIGNAL_API_KEY` | OneSignal API key |
| `REDIS_URL` | Redis connection URL (for Celery) |

### Optional (with defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `Holy Grills` | App name shown in emails and responses |
| `APP_TAGLINE` | `Holy Grills FUTA` | Tagline used in email footers |
| `FLASK_ENV` | `development` | `development` or `production` |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode |
| `FRONTEND_URL` | `http://localhost:3000` | Frontend URL: password-reset links, and added to `Config.CORS_ORIGINS` |
| `CORS_ORIGINS` | *(unset)* | Comma-separated allowed CORS origins. **Not enforced yet** — `app/__init__.py` registers `CORS(app, origins="*")`; set this and switch that call before deploying |
| `JWT_ACCESS_TOKEN_EXPIRES` | `3600` | Access token TTL in seconds (1 hour) |
| `JWT_REFRESH_TOKEN_EXPIRES` | `2592000` | Refresh token TTL in seconds (30 days) |
| `JWT_REFRESH_WINDOW_MINUTES` | `5` | Silent-rotation window — token is refreshed when fewer than this many minutes remain before expiry |
| `PAYSTACK_PREFERRED_BANK` | `wema-bank` | Bank for dedicated virtual accounts |
| `EMAIL_FROM` | `noreply@holygrills.ng` | Sender email address |
| `EMAIL_FROM_NAME` | `Holy Grills` | Sender display name |
| `HP_PER_NAIRA_FOOD` | `0.1` | HP earned per ₦1 spent on food (1 HP / ₦10) |
| `HP_LIABILITY_VALUE` | `0.185` | ₦ value of 1 HP (used for HP-discount maths) |
| `WELCOME_BONUS_HP` | `50` | HP awarded on a user's first order |
| `BIRTHDAY_HP` | `150` | HP awarded on a user's birthday |
| `REFERRAL_HP` | `75` | HP awarded to referrer when referee places first order |
| `SQUAD_ORDER_ENABLED` | `true` | Enable squad order discounts |
| `SQUAD_ORDER_MIN_ITEMS` | `3` | Minimum item count for squad discount |
| `HP_EXPIRY_INACTIVITY_DAYS` | `90` | Days of inactivity before HP expires |

See `.env.example` for the full list including all HP economy and squad-order tuning variables.

---

## Connecting to Supabase

All database access goes through Supabase's REST API (PostgREST) and all
authentication through Supabase Auth (GoTrue) — there is no direct Postgres
connection, so the only thing the app needs is the project URL plus its keys.

### 1. Collect the four values

Supabase Dashboard → **Project Settings → API**:

| Value | Env var |
|-------|---------|
| Project URL | `SUPABASE_URL` |
| `service_role` secret key | `SUPABASE_SERVICE_ROLE_KEY` |
| `anon` public key | `SUPABASE_ANON_KEY` |
| JWT secret | `SUPABASE_JWT_SECRET` (or `JWT_SECRET`) |

Put them in `.env` (that file is git-ignored — keep it that way, the
service-role key is a full-access database credential).

### 2. Verify the connection

```bash
python scripts/check_supabase.py             # full preflight
python scripts/check_supabase.py --offline   # config only, no network
python scripts/check_supabase.py --json      # machine-readable (CI)
```

The checker validates the URL, the key roles, the JWT signatures and the
`ref` claim (catching keys from *another* project), then performs live
Auth + PostgREST round-trips and confirms every table the code queries via
`db.table("…")` actually exists. Exit code is `0` when healthy, `1` on
failure — drop it into a deploy step to fail fast instead of at first request.

### 3. Prove the code↔database contract

```bash
python scripts/contract_check.py
```

`check_supabase.py` proves you can *reach* Supabase; this proves every request
the code makes matches what the database *has*. It parses the source (no
execution) for every `.table(...)`, `.select(...)`, `.insert({...})`, filter
column and `.rpc(...)` call, then probes the live project read-only:

* tables that don't exist
* columns the code selects/filters/writes that don't exist
  (a 400 is re-probed column-by-column so the report names the exact offender)
* RPCs and RPC parameter names the database doesn't expose
  (RPCs are resolved from the OpenAPI spec — never executed)

```
  FAIL  missing columns orders.legacy_price   [app/services/order_service.py:412]
```

### 4. Run the live end-to-end suite

```bash
python scripts/live_test.py                # full run: writes + automatic cleanup
python scripts/live_test.py --read-only    # GET-only smoke test
python scripts/live_test.py --login-email you@example.com --login-password '…'
python scripts/live_test.py --login-email you@example.com --login-password '…' --write-existing
python scripts/live_test.py --keep-data --verbose   # debug a failure
```

Playwright-style: each step drives the API for real and then reads the row back
out of Postgres through the service-role key, so a green run means the whole
chain works — endpoint, service, REST call, SQL, and response.

| Phase | What it exercises |
|-------|-------------------|
| preflight | `/api/health` reports Supabase + Supabase Auth connected |
| public | menu, campuses, departments, levels, calendar, leaderboard, challenges, rewards, delivery windows/zones, hostels/gates, storefront |
| auth | register → duplicate register → login → wrong password 401 → `/me` → refresh → streak → profile patch → device token |
| addresses | create → list → update → delete (each verified in `user_addresses`) |
| cart & saved | add → read → update quantity → save for later → back to cart |
| orders | wallet top-up via `credit_wallet_atomic` → place → read → history → list → active → cancel (+ refund ledger). Ordering is gated by the **signed-in account's own campus** (`g.campus_id`), so after login the suite re-pins itself to that campus and re-fetches the delivery point before provisioning an ordering window. It also provisions a free-side credit and selection and then asserts the order consumed it, removed the selection and carried a ₦0 line, and cancels an UNPAID card order to prove nothing is refunded for money that was never collected |
| economy | HP balance/transactions/tiers, wallet + ledger, rewards, referrals |
| notifications | list, preferences round-trip, read-all |
| admin | optional (`--admin-token`): settings, users, orders, audit log, dashboard, economics |

A throwaway account (`e2e.<timestamp>.<rand>@e2e.holygrills.test`) is created
for the run and hard-deleted afterwards, together with every row the run
touched. `--read-only` never writes. `--login-email` reuses an existing account and turns
writing off — with it, the cart, address, order and economy write steps skip and
everything downstream of them cascades to "depends on … → skipped". Add
`--write-existing` (or `make e2e … WRITE_EXISTING=1`) to run them: the suite then
deletes the rows *it* created — tracked ids, order children, and its temporary
ordering window — while the account and everything already on it is never touched. Exit code is `0`
when every executed step passed (`SKIP` is not a failure), `1` on any failure —
so it can gate a deploy.

### 5. Audit the database (RLS, grants, RPC behaviour, duplicates)

```bash
make audit                                        # inventory + deep pass (needs SUPABASE_DB_URL)
make audit ARGS="--search credit"                 # does something for this already exist?
make audit ARGS="--out docs/audit-report.md"      # write a report
```

Requires `SUPABASE_DB_URL` in `.env` for the deep pass — PostgREST cannot expose
RLS policies, grants or function bodies. Use the **pooler** URI (port 6543): the
direct host `db.<ref>.supabase.co` is IPv6-only and will not connect from Replit
or most CI runners. Copy the format from [`.env.example`](.env.example). Full write-up: [`docs/DATABASE_AUDIT.md`](docs/DATABASE_AUDIT.md).

### 6. Start the app and confirm

```bash
python run.py
curl -s http://localhost:5000/api/health
```

```json
{
  "status": "ok",
  "checks": {
    "supabase": "connected",
    "supabase_auth": "connected",
    "redis": "not_configured"
  }
}
```

`status` is `degraded` if a dependency is unreachable — the endpoint always
returns HTTP 200, so callers must read the `status` field.

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `make: .venv/bin/python: No such file or directory` | `make setup` has not been run yet (or your venv lives elsewhere) | `make setup`, or point at yours: `make check VENV=../.venv` |
| `missing: SUPABASE_URL, …` from the checker | No `.env` (the file is git-ignored, so a fresh clone has none) | `make env` then fill in the Supabase block |
| `unreachable: … Max retries exceeded` / `SSLError` | No network route to `*.supabase.co` (offline, firewall, egress allow-list, sandbox) | Run where the internet is open, or allow `*.supabase.co:443` |
| `error:401` / `Invalid API key` | Key rotated, revoked, or copied with a trailing newline | Re-copy from Project Settings → API |
| Checker: `key belongs to project 'x' but SUPABASE_URL is 'y'` | Keys and URL from different projects | Use one project's URL + keys together |
| Checker: `NOT signed by the configured JWT secret` | `SUPABASE_JWT_SECRET` is stale (rotated) | Re-copy the JWT secret; auth still works without it, refresh optimisation does not |
| `error:404` + `PGRST205` on a table | Schema/migration not applied | Run the SQL in the Supabase SQL editor |
| `error:403` / `RESOURCE_ACCESS_DENIED` | RLS policy or wrong key role | Check the table's policies; server calls use the service-role key |
| Production boot: `SECRET_KEY is unset or still the public default` | Flask session secret missing | Set a long random `SECRET_KEY` (see line above) |
| Suite skips the order steps: `ordering unavailable … "Orders can only be placed during operating hours"` | With `--login-email`, the suite's picked campus differed from the account's own campus, which is the one `POST /api/orders` uses; or the run happened outside 08:00–16:00 WAT with no window for that campus | Fixed in the suite: `auth.campus` re-pins to the account's campus. If it still skips, the message now names the campus it used — check `ordering_windows` for a closed/full row on it |
| Suite leaves a window behind after a `--login-email` run | Older builds only deleted scaffolding for accounts they created | Fixed: `ctx.track_infra()` deletes it either way. Existing leftovers: `ordering_windows` rows with `opens_at 00:00`, `closes_at 23:59`, `capacity 50` |
| Audit: "N tables answer the anon key" | Expected Supabase posture — PostgREST exposes the schema, RLS decides the rows | Only `exposed` (200 **with a row**) is a finding. See [`docs/DATABASE_AUDIT.md`](docs/DATABASE_AUDIT.md#reading-the-anon-result-important) |
| Audit: "deep SQL checks skipped — SUPABASE_DB_URL is not set" | The REST API cannot read RLS policies, grants or function bodies | Add the **pooler** URI to `.env` (direct `db.<ref>.supabase.co` is IPv6-only) — see [`.env.example`](.env.example) |

---

## Running the App

```bash
# Development
python run.py

# Production (Gunicorn)
gunicorn run:app --bind 0.0.0.0:5000 --workers 4

# Celery worker (background tasks — birthday HP, leaderboard reset, etc.)
celery -A app.tasks.celery_app worker --loglevel=info --queues=default

# Celery beat (task scheduler)
celery -A app.tasks.celery_app beat --loglevel=info
```

---

## API Documentation

Swagger UI is available at **`/api/docs/`** when the server is running.

Every endpoint is documented in its route file using Flasgger YAML docstrings.

### Base URL

```
http://localhost:5000/api
```

### Authentication

Most endpoints require a Bearer JWT token:

```
Authorization: Bearer <access_token>
```

Obtain tokens via `POST /api/auth/login` or `POST /api/auth/register`.

### Health Check

```
GET /api/health
```

Returns connectivity status for Supabase (PostgREST), Supabase Auth (GoTrue) and Redis.
No auth required. `status` is `ok` or `degraded`; the endpoint always returns HTTP 200.

---

## Project Structure

```
holy-grills-backend/
├── run.py                   # Entry point — creates and runs the Flask app
├── app/
│   ├── __init__.py          # App factory: blueprints, CORS, Swagger, error handlers
│   ├── config.py            # All config from environment variables
│   ├── db.py                # Supabase REST client wrapper (SupabaseClient)
│   ├── messages.py          # ★ Central string registry — all user-facing copy
│   ├── routes/              # One blueprint per feature domain
│   │   ├── health.py        # GET /api/health
│   │   ├── auth.py          # /api/auth/*
│   │   ├── orders.py        # /api/orders/*
│   │   ├── menu.py          # /api/menu/*
│   │   ├── hp.py            # /api/hp/*
│   │   ├── wallet.py        # /api/wallet/*
│   │   ├── rewards.py       # /api/rewards/*
│   │   ├── marketplace.py   # /api/marketplace/*
│   │   ├── events.py        # /api/events/*
│   │   ├── referrals.py     # /api/referrals/*
│   │   ├── notifications.py # /api/notifications/*
│   │   ├── admin.py         # /api/admin/*
│   │   ├── kitchen.py       # /api/kitchen/*
│   │   ├── riders.py        # /api/riders/*
│   │   ├── leaderboard.py   # /api/leaderboard/*
│   │   ├── challenges.py    # /api/challenges/*
│   │   ├── webhooks.py      # /api/webhooks/*  (Paystack, Flutterwave)
│   │   ├── storefront.py    # /api/storefront/*
│   │   └── analytics.py     # /api/analytics/*
│   ├── services/            # Business logic (no HTTP concerns)
│   │   ├── auth_service.py
│   │   ├── hp_service.py
│   │   ├── notification_service.py
│   │   ├── order_service.py
│   │   ├── payment_service.py
│   │   └── wallet_service.py
│   ├── middleware/
│   │   ├── auth.py          # @require_auth, @require_role decorators
│   │   └── rate_limit.py    # @rate_limit decorator (IP-based, in-memory)
│   ├── tasks/
│   │   ├── celery_app.py    # Celery instance configuration
│   │   └── scheduled.py     # All periodic background tasks
│   └── utils/
│       ├── email.py         # OneSignal email dispatch + TEMPLATES
│       ├── logger.py        # ★ Structured logging — use get_logger(__name__)
│       ├── retry.py         # ★ @with_retry decorator for external API calls
│       └── validators.py    # Input validation helpers
├── scripts/
│   ├── check_supabase.py    # Connection preflight (config + live probes)
│   ├── contract_check.py    # Code ↔ database contract check (tables/columns/RPCs)
│   └── live_test.py         # Playwright-style live end-to-end suite
├── Makefile                 # make setup / check / contract / audit / smoke / e2e / server
├── docs/
│   └── DATABASE_AUDIT.md    # RLS/grants/RPC audit + the four open questions
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
├── Procfile                 # Gunicorn start command for deployment
└── DEVELOPER_GUIDE.md       # Deep-dive developer reference
```

> **Note:** `DEVELOPER_GUIDE.md` also references `migrations/schema.sql` and
> `scripts/seed.py`. Those are not part of this repository checkout — the live
> database is managed directly in the Supabase SQL editor — so the `scripts/`
> folder here is the entry point for verifying a connection
> (`check_supabase.py`), the schema contract (`contract_check.py`) and behaviour
> (`live_test.py`).

---

## Key Concepts

### HP (Holy Points) Economy

HP is the loyalty currency. Users earn it by ordering food, referring friends, attending events, and celebrating birthdays. HP is split into **active** (spendable) and **pending** (unlocks as you spend). See `app/services/hp_service.py` and `app/config.py` for rates.

### Order State Machine

Orders flow through a fixed set of statuses:
```
received → preparing → ready → assigned → out_for_delivery → delivered
                                                            → delivery_attempted → unclaimed
Any pre-delivery state → cancelled | refunded
```
Transitions are enforced in `app/services/order_service.py:VALID_TRANSITIONS`.

### Database (Supabase via REST)

The app uses a custom `SupabaseClient` in `app/db.py` that talks to Supabase's PostgREST REST API. This means there is **no direct PostgreSQL connection** — all queries go through HTTP. Use `db.table("table_name").select(...).execute()` everywhere.

---

## Testing

```bash
# Full end-to-end suite (requires live server + all env vars set)
python test_comprehensive.py

# Smoke tests only (fastest)
python test_smoke.py

# Squad-order specific flow
python test_squad_order.py

# New-API coverage
python test_new_apis.py
```

> **Prerequisites:** run `python run.py` in a separate terminal before executing any test script. All test scripts make HTTP requests against `http://localhost:5000/api`.

### Seed the database first

```bash
# Python seed (uses Supabase REST API — works anywhere)
python scripts/seed.py

# SQL seed (run in Supabase SQL Editor or via psql)
psql "$DATABASE_URL" -f scripts/seed.sql
```
