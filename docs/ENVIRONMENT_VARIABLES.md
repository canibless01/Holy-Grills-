# Environment variables — what to set, and why

Derived from the **code** (`app/config.py`, `app/**/*.py`, `src/**/*.ts(x)`), not from the
docs — several of those are stale. Last verified 2026-10-05.

---

## 0. If the backend ever boots to nothing

> **Correction (2026-10-05):** this section was written on the assumption that no
> environment variables were set. The backend is in fact up and running, so the
> Supabase variables **are** present. The real cause of the empty API list turned out
> to be a malformed Swagger docstring, not a missing variable (see §0b). The startup
> check described below is still worth having — it turns a bare `KeyError` into a
> message that names every missing variable — but it was not the cause.

`app/config.py` read the Supabase keys like this, **inside the `Config` class body**:

```python
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
```

A class body runs at **import time**. `run.py` imports `app.config`, so with any of those
unset the whole process dies before Flask ever exists:

```
KeyError: 'SUPABASE_URL'
```

Render's *build* step is just `pip install`, which succeeds — so the deploy looks fine, the
start command `gunicorn run:app` then crashes, and you get an empty API list / 502.

Reproduced locally:

```
$ python -c "import app.config"          # with nothing set
KeyError: 'SUPABASE_URL'
```

**Fixed:** `app/config.py` now validates them up front and names everything missing:

```
RuntimeError: Missing required environment variable(s): SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY. The backend cannot start without
them — set them on the host (Render → your service → Environment) and restart.
```

## 0b. What actually broke the API list: one malformed docstring

`GET /api/docs/apispec.json` returned **500**, so Swagger UI had nothing to render and
showed only `Fetch error undefined /api/docs/apispec.json`.

Flasgger builds the spec by YAML-parsing **every** view docstring, so a single malformed
one takes the whole document down — and the error names no endpoint. Here the culprit was
`app/routes/messages.py::list_messages`, which had a `400:` response block orphaned
between `security: []` and `parameters:`:

```yaml
tags: [Meta]
security: []
  400:            # <- belongs under `responses:`, not here
    description: Malformed prefix
parameters:
```

Fixed by moving it under `responses:`. The spec now returns 200 with 262 paths, and
`tests/test_apispec_docstrings.py` fails the build if any docstring ever stops parsing, or
if the spec endpoint stops returning 200.

**This is unrelated to login.** The spec is only fetched by `/api/docs/`; nothing in the
app calls it.

---

Two more things to set while you're in there:

- **`FLASK_ENV=production`** — `run.py` does `os.environ.get("FLASK_ENV", "development")`,
  and `config_map["default"]` is `DevelopmentConfig`, which sets `DEBUG = True`. On Render
  with nothing set, you are running the API in debug mode.
- **The Procfile declares three processes** — `web`, `worker` (celery) and `beat`. The two
  celery processes need `REDIS_URL`. Without a Redis instance they will crash-loop, which
  is noisy but does not stop the API. Provision Redis, or disable `worker`/`beat` for now.

---

## 1. Backend — REQUIRED, the app will not start

| Variable | Where to get it | Notes |
|---|---|---|
| `SUPABASE_URL` | Supabase → Project Settings → API → Project URL | `https://xxxx.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase → Project Settings → API → `anon` `public` | Used for the user-scoped client |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API → `service_role` | **Secret.** Bypasses RLS — never expose it |

---

## 2. Backend — security (has an insecure default, set these)

| Variable | Default if unset | Why it matters |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Flask session signing |
| `JWT_SECRET` (or `SUPABASE_JWT_SECRET`) | falls back to `SECRET_KEY`, then `change-me-in-production` | Local token operations. Set it to the value in Supabase → Settings → API → **JWT Secret** |
| `FLASK_ENV` | `development` → **DEBUG=True** | Set to `production` |
| `FLASK_DEBUG` | `false` | Leave false |

---

## 3. Backend — needed for each feature

Everything below is optional in the sense that the app boots without it, but the feature
silently degrades. This is the part that produces "it doesn't work but nothing errors"
reports.

| Variable | Feature that needs it | What happens when unset |
|---|---|---|
| `FRONTEND_URL` | CORS **and every outbound link** | Now defaults to `https://holy-grills.vercel.app` (was `http://localhost:3000`, which made **password-reset emails link to localhost**). Add it to CORS automatically |
| `CLOUDINARY_API_KEY` | Image uploads | `POST /api/upload/signature` → 503 naming these. **This is the upload failure from the audit** |
| `CLOUDINARY_API_SECRET` | Image uploads | same as above |
| `CLOUDINARY_CLOUD_NAME` | Image uploads | Has a hardcoded fallback (`risvlfhx`); set it anyway so it is not implicit |
| `PAYSTACK_SECRET_KEY` | Payments | Paystack calls fail |
| `PAYSTACK_PUBLIC_KEY` | Payments | — |
| `PAYSTACK_WEBHOOK_SECRET` | Webhook verification | Falls back to `PAYSTACK_SECRET_KEY` |
| `RESEND_API_KEY` | Transactional email | Email is fire-and-forget and fails quietly; one route answers `502 "Failed to send email — check RESEND_API_KEY"` |
| `EMAIL_FROM` | Email | Defaults `noreply@holygrills.ng` — must be a domain verified in Resend |
| `EMAIL_FROM_NAME` | Email | Defaults `Holy Grills` |
| `ONESIGNAL_APP_ID` | Web push | Push disabled while empty |
| `ONESIGNAL_API_KEY` | Web push | Server-side push sends |
| `REDIS_URL` | Celery `worker` + `beat` (abandoned carts, scheduled jobs, newsletter batches) | Must include a scheme. Also the fallback broker when `CELERY_BROKER_URL` is unset **or empty**. Defaults to `redis://localhost:6379/0` |
| `WHATSAPP_SUPPORT_NUMBER` | Support button **fallback only** | Only used when the campus has no `system_settings` row. Per-campus rows in `system_settings.whatsapp_support_number` are the real source |
| `WHATSAPP_SUPPORT_MESSAGE` | Prefilled chat text, fallback only | same |

### CORS

`CORS_ORIGINS` / `ALLOWED_ORIGINS` (comma-separated) only **add** to a built-in list that
already contains `https://holy-grills.vercel.app`, `https://holygrill.app`,
`https://www.holygrill.app` and the localhost dev ports. A `*` is deliberately ignored.

**Branch previews now work.** Every push gets a fresh random host
(`holy-grills-<hash>.vercel.app`, `holy-grills-git-<branch>-<scope>.vercel.app`), which a
fixed list can never keep up with — that is why previews were blocked and login failed with
"Failed to fetch". `Config.CORS_ORIGIN_PATTERNS` adds the anchored pattern
`^https://holy-grills[a-z0-9-]*\.vercel\.app$`, so:

| Origin | Allowed |
|---|---|
| `https://holy-grills.vercel.app` | yes |
| `https://holy-grills-git-my-branch-owner.vercel.app` | yes |
| `https://holy-grills-abc123.vercel.app` | yes |
| `https://evil.vercel.app` | no |
| `https://holy-grills.vercel.app.evil.com` | no |

Disable it once you no longer need previews: `ALLOW_VERCEL_PREVIEWS=false`.

---

## 4. Backend — optional tuning (all have defaults)

Set only if you want to override. Every one of these is read with a default in
`app/config.py`, so an empty environment behaves like the shipped defaults:

`APP_NAME`, `APP_TAGLINE`, `HP_CURRENCY_NAME`, `SWAGGER_CONTACT_EMAIL`, `JWT_ALGORITHM`,
`JWT_ACCESS_TOKEN_EXPIRES`, `JWT_REFRESH_TOKEN_EXPIRES`, `JWT_REFRESH_WINDOW_MINUTES`,
`AUTH_RESET_REDIRECT_PATH`, `AUTH_VERIFY_REDIRECT_PATH`, `MAX_CONTENT_LENGTH_MB`,
`PAYSTACK_PREFERRED_BANK`, `FLUTTERWAVE_SECRET_KEY`, `FLUTTERWAVE_WEBHOOK_SECRET`,
`HP_PER_NAIRA_FOOD`, `HP_UNLOCK_RATE_PCT`, `HP_DECAY_ONSET_DAYS`, `HP_DECAY_RATE_MONTHLY`,
`MONTHLY_HP_CAP`, `WELCOME_BONUS_HP`, `BIRTHDAY_HP`, `SUBSCRIPTION_HP`, `MARKETPLACE_PURCHASE_HP`,
`WALLET_TOPUP_HP`, `WALLET_TOPUP_MIN`, `WALLET_MIN_CARD_TOPUP`, `WALLET_REF_PREFIX`,
`HP_TRANSFER_MIN_AMOUNT`, `HP_TRANSFER_MIN_ORDERS`, `LOGIN_STREAK_HP`,
`LOGIN_STREAK_WEEK1_HP`…`WEEK4_HP`, `STREAK_MAX_MISSED_DAYS`, `STREAK_RECLAIM_MIN_TOPUP`,
`EVENT_CHECKIN_HP`, `GRADUATION_HP`, `MEMBERSHIP_REWARDS`, `TIER_GRACE_PERIOD_DAYS`,
`TIER_PERKS`, `HP_BUNDLES`, `HP_BUNDLE_PRICE_PER_HP`, `HP_BUNDLE_MIN_PURCHASE`,
`FLASH_DISCOUNT_PCT`, `FLASH_MAX_QTY`, `FREE_SIDE_OPTIONS`, `FREE_SIDE_CREDITS_VALIDITY_DAYS`,
`SQUAD_ORDER_ENABLED`, `SQUAD_MAX_MEMBERS`, `SQUAD_ORDER_MIN_ITEMS`, `SQUAD_ORDER_MAX_ITEMS`,
`SQUAD_ORDER_DISCOUNT_ENABLED`, `SQUAD_ORDER_DISCOUNT_PCT`, `SQUAD_DELIVERY_DISCOUNT_ENABLED`,
`SQUAD_DELIVERY_DISCOUNT_PCT`, `SQUAD_HP_SPLIT_ENABLED`, `SQUAD_REFERRAL_WINDOW_DAYS`,
`FIRST_ORDER_GIFT_ENABLED`, `MINIMUM_AGE`, `LOW_CODE_INVENTORY_THRESHOLD`,
`LEADERBOARD_DEFAULT_LIMIT`, `LEADERBOARD_MAX_LIMIT`, `ABANDONED_CART_MINUTES`,
`CALLBACK_WINDOW_MINUTES`, `NEWSLETTER_BATCH_SIZE`, `WINBACK_DAY1/2/3`,
`ORDERING_WINDOW_OPEN_TIME`, `ORDERING_WINDOW_CLOSE_TIME`, `EXCLUSIVE_SPIN_VALIDITY_DAYS`,
`EXCLUSIVE_SPIN_TEMPLATE_ITEMS`, `MARKETPLACE_DEFAULT_VENDOR_NAME`,
`PAYSTACK_SANDBOX_MOCK_NUBAN`, `API_PUBLIC_URL`, `API_DOCS_ENABLED`,
`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

---

## 5. Frontend (Vercel) — every one is optional

Confirmed in code: each `import.meta.env.VITE_*` read has an in-code fallback, so an empty
Vercel environment behaves like the current deployment.

| Variable | Fallback in code | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `https://holygrills-production.up.railway.app/api` | API origin (Railway) |
| `VITE_SITE_URL` | `https://holygrill.app` | Canonical URLs, `og:url`, JSON-LD |
| `VITE_ASSET_CDN_URL` | `https://media.base44.com/images/public` | Mascots / logos |
| `VITE_ONESIGNAL_APP_ID` | *(empty → push disabled)* | Web push |
| `VITE_DEV_PROXY_TARGET` | *(empty → no proxy)* | Dev only |

**One caveat:** if you ever point `VITE_API_BASE_URL` at a different origin, add it to the
CSP `connect-src` in `scripts/routes.mjs` and re-run `npm run routes:sync` — the CSP is now
**enforced**, so a mismatched origin will be blocked.

---

## 6. Minimum viable set to paste into Render

```
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SECRET_KEY=<long random string>
JWT_SECRET=<Supabase JWT secret>
FLASK_ENV=production
FLASK_DEBUG=false
FRONTEND_URL=https://holygrill.app
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
CLOUDINARY_CLOUD_NAME=risvlfhx
RESEND_API_KEY=re_...
EMAIL_FROM=noreply@holygrills.ng
PAYSTACK_SECRET_KEY=sk_live_...
PAYSTACK_PUBLIC_KEY=pk_live_...
REDIS_URL=<Railway Redis internal URL>
```

## 7. Verify

```
GET https://holygrills-production.up.railway.app/api/health          # the deployment is up
GET https://holygrills-production.up.railway.app/api/docs/           # 404 in production unless API_DOCS_ENABLED=true
```

Then, on the site: log in, place a small order, upload an image in Admin → Storefront, and
trigger a password reset (to confirm the email links to `holygrill.app`, not localhost).

## Broker URL resolution (Celery worker)

`app/tasks/celery_app.py` resolves the broker as
`CELERY_BROKER_URL` → `REDIS_URL` → `redis://localhost:6379/0`, ignoring blank or
whitespace-only values, and the result backend as
`CELERY_RESULT_BACKEND` → the same URL as the broker.

Blank values are skipped deliberately. `os.environ.get("CELERY_BROKER_URL", default)`
only uses the default when the variable is *absent*, so a variable created but left
empty — which is what a platform reference like `${{Redis.REDIS_URL}}` resolves to when
the service name or variable name does not match — evaluates to `""`. Celery then treats
the broker as unset and falls back to `amqp://guest@localhost:5672`, and the worker
fails with `Cannot connect to amqp://guest:**@127.0.0.1:5672//: [Errno 111] Connection
refused` even though Redis is running. If that error ever reappears, check the worker
service's own variables: they must be non-empty **on the worker**, not just on the web
service.

## 8. Backend-host values after the Render → Railway move

The frontend origin (`https://holygrills.online`) did not change; only the API moved.
Anything that names the **backend** must use the Railway origin:

| Where | Value |
|---|---|
| Vercel `VITE_API_BASE_URL` | `https://holygrills-production.up.railway.app/api` |
| Backend `API_PUBLIC_URL` | `https://holygrills-production.up.railway.app/api` |
| Paystack webhook URL | `https://holygrills-production.up.railway.app/api/webhooks/paystack` |
| Backend `FRONTEND_URL` | `https://holygrills.online` (unchanged — links point at the site) |
| Supabase Auth Site URL / redirects | `https://holygrills.online` (unchanged — auth is frontend) |
| OneSignal site origin, Google Maps referrer | `https://holygrills.online` (unchanged) |

`API_PUBLIC_URL` is what email open-tracking pixels, click-tracking redirects and the
newsletter one-click unsubscribe header are built from. Its in-code default is the Railway
URL; set it explicitly so a future host move cannot quietly break tracking.

### API docs are closed in production

`/api/docs/` (Flasgger) publishes every route, admin path and payload example on one page.
`create_app` now registers it only when `DEBUG`/`TESTING` is on or `API_DOCS_ENABLED` is
`true`; otherwise `/api/docs/`, `/api/docs/apispec.json` and `/api/docs/static/*` all 404.
Set `API_DOCS_ENABLED=true` temporarily on a staging service if you need to browse them.

### Redis URL formats accepted

`REDIS_URL` is passed through `normalize_redis_url()` (`app/utils/redis_url.py`) before
anything uses it, because dashboard pastes are not always connection strings:

| You paste | It becomes |
|---|---|
| `redis://host:6379/0`, `rediss://…`, `unix://…` | unchanged |
| `host:6379` (Railway Connect tab, public proxy) | `redis://host:6379` |
| `http://host:6379` / `https://host:6379` | `redis://…` / `rediss://…` |
| `amqp://…` or any other scheme | rejected for Redis, passed through for Celery |
| empty / whitespace / `""` | treated as not configured |

Without the scheme, redis-py raises `Redis URL must specify one of the following schemes
(redis://, rediss://, unix:/` and `/api/health` reported that as `error:…`. It now
reports `error:invalid_url_missing_redis_scheme` when a value is set but unusable, and
`not_configured` when it is absent. Inside Railway, prefer the private URL
(`redis://…@redis.railway.internal:6379`) so traffic never leaves the project.

## 9. Launch hardening defaults

| Behaviour | Before | Now |
|---|---|---|
| API docs `/api/docs/` | always public | 404 unless `DEBUG`/`TESTING` or `API_DOCS_ENABLED=true` |
| `ALLOW_VERCEL_PREVIEWS` | default **true** — any `holy-grills*.vercel.app` origin allowed | default **true** (previews are the test surface); set `false` to close the pattern |
| Rate limits | in-process counters — multiplied by worker count, reset on deploy | Redis counters when `REDIS_URL` is set; in-process only as a fallback |
| `/api/health` detail | raw driver text (`host:port`, credentials in URLs) | failure class only (`unreachable:connection_refused`, `error:timeout`, …); full text in DEBUG |
| API response headers | none | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, plus HSTS over TLS |

Rate limits now key on `hg:rl:<endpoint>:<ip-or-user>:<window slot>` in Redis with a TTL
slightly longer than the window, so every worker and every service share one count. If
Redis is unreachable the limiter logs once and counts in-process for up to 60 seconds
before retrying, so an outage degrades accuracy instead of failing open or blocking logins.

### Closing the API docs (Flasgger) on the live API

The switch is **`API_DOCS_ENABLED`**, read by `create_app` in `app/__init__.py`:

| `API_DOCS_ENABLED` | Where | Result |
|---|---|---|
| absent, empty, `false` | Railway web service | `/api/docs/`, `/api/docs/apispec.json`, `/api/docs/static/*` all **404** |
| `true` / `1` / `yes` / `on` | Railway web service | docs served (temporary viewing only) |

`DEBUG`/`TESTING` also opens them, which is why local runs and the test suite still have
Swagger. To close them on Railway: open the **web** service → Variables → delete
`API_DOCS_ENABLED` (or set it to `false`) → redeploy. Setting it on worker/beat has no
effect; they serve no HTTP.

Verify with `GET https://holygrills-production.up.railway.app/api/docs/` → expect 404, and
`GET /api/health` → expect 200. Reopen only by temporarily setting the variable again.

### Vercel previews and CORS

`ALLOW_VERCEL_PREVIEWS` defaults to **true** so preview deployments (where the app is
tested) can call the API. The pattern is `^https://holy-grills[a-z0-9-]*\.vercel\.app$`,
which covers every branch and hash preview of this repo — and, by design, any fork using
the same project name. Set `ALLOW_VERCEL_PREVIEWS=false` on Railway once testing stops
using previews.

### Railway background-work launch profile (4 November 2026)

All values are optional; these defaults now apply in code. Put overrides in shared
Railway variables used by API/worker/beat so job monitoring shows the same cadence.

| Variable | Default | Purpose |
|---|---|---|
| `CELERY_WORKER_CONCURRENCY` | `1` | Worker processes; an explicit CLI `--concurrency` overrides it. |
| `CELERY_CAMPAIGN_SCAN_MINUTES` | `15` | Newsletter queue scan interval. |
| `CELERY_SCHEDULED_ORDER_SCAN_MINUTES` | `15` | Scheduled-order staff-notice scan; live kitchen visibility remains immediate. |
| `CELERY_RECOVERY_SCAN_MINUTES` | `60` | Abandoned-cart and post-delivery nudge scans. |

Scan intervals must divide a whole hour: 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30 or
60. Payment confirmation, checkout, customer order notifications and live queue
updates do not wait for these schedules. Do not start a second beat scheduler.
