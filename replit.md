# Holy Grills Backend API

Flask REST API powering the Holy Grills student food-ordering and loyalty-points (HP) platform built for FUTA.

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Flask 3.x |
| Database | Supabase (PostgreSQL via REST API) |
| Auth | Supabase Auth + custom JWT middleware |
| Payments | Paystack + Flutterwave |
| Notifications | OneSignal (push + email) |
| Background Jobs | Celery + Redis |
| API Docs | Flasgger (Swagger UI at `/api/docs/`) |

## Running the app

The workflow `Start application` runs `python run.py`, serving on port 5000.

To also start the Celery worker for background jobs (birthday HP, leaderboard resets, etc.):

```bash
celery -A app.tasks.celery_app worker --loglevel=info
```

## API Documentation

Swagger UI is available at `/api/docs/` once the server is running.

Health check: `GET /api/health`

## Environment variables / secrets

All secrets are configured via Replit Secrets. Key ones:

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` — database + auth
- `JWT_SECRET` / `SUPABASE_JWT_SECRET` — JWT signing
- `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_WEBHOOK_SECRET` — payments
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` — background jobs
- `SECRET_KEY` — Flask session secret

> **Note:** `REDIS_URL` must point to a publicly reachable Redis instance (not a Railway-internal hostname) for Celery background jobs to work on Replit.

## Project structure

```
app/
  __init__.py       # App factory, blueprint registration
  config.py         # All config (loaded from env vars)
  db.py             # SupabaseClient (HTTP REST wrapper)
  routes/           # One blueprint per feature area
  services/         # Business logic
  tasks/            # Celery tasks
  middleware/       # Auth + rate-limit middleware
  utils/            # Logging, helpers
migrations/
  schema.sql        # Full database schema
scripts/
  seed.py           # Seed the database via REST API
run.py              # Entry point
```

## Database migrations

Migrations that require running in the **Supabase SQL Editor** (service-role cannot CREATE TABLE via REST):

| File | What it does |
|------|-------------|
| `migrations/run9_departments.sql` | Creates `departments` table + seeds FUTA departments, adds `department_id` FK to `profiles` |

## Brand name / personalisation
All user-facing strings use `{platform}` as a placeholder instead of hardcoding "Holy Grills". Both `notification_service.send_notification()` and `email.send_email()` resolve `{platform}` → `APP_NAME` env var at send time. Email footers use `APP_TAGLINE`. Set these in Replit Secrets to rebrand without code changes.

## API additions

| Endpoint | Description |
|----------|-------------|
| `GET /api/departments` | Public — list active departments (used in registration dropdown) |
| `GET /api/departments?grouped=true` | Grouped by faculty |
| `GET /api/departments/faculties` | Distinct faculty list |
| `POST /api/admin/departments` | Admin — create department |
| `PATCH /api/admin/departments/<id>` | Admin — update department |
| `DELETE /api/admin/departments/<id>` | Admin — deactivate department |
| `POST /api/admin/departments/<id>/restore` | Admin — reactivate department |

Registration (`POST /api/auth/register`) and profile update (`PATCH /api/auth/profile`) now accept `department` and `academic_level` fields, which map directly to `profiles.department` and `profiles.academic_level` — the columns used by admin blast filters.

## User preferences

- Keep the existing project structure — do not restructure or migrate it.
- Database is truth source — every code change must match live Supabase schema, no assumptions.
