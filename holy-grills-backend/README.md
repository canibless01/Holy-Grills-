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
# 1. Clone the repo
git clone <repo-url>
cd holy-grills-backend

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy env template and fill in values
cp .env.example .env
# Edit .env with your credentials

# 4. Start the API
python run.py

# 5. (Optional) Start Celery worker for background jobs
celery -A app.tasks.celery_app worker --loglevel=info
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
| `FRONTEND_URL` | `http://localhost:3000` | Frontend URL for CORS and password-reset links |
| `CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins |
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

Returns connectivity status for Supabase and Redis. No auth required.

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
├── migrations/
│   └── schema.sql           # Idempotent SQL for tables not in Supabase migrations
├── scripts/
│   └── seed.py              # Dev seed data
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
├── Procfile                 # Gunicorn start command for deployment
└── DEVELOPER_GUIDE.md       # Deep-dive developer reference
```

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
