# Environment variables — what to set, and why

Derived from the **code** (`app/config.py`, `app/**/*.py`, `src/**/*.ts(x)`), not from the
docs — several of those are stale. Last verified 2026-10-05.

---

## 0. Why the backend loads nothing on Render right now

This is the answer to "the build passes but my API list doesn't load".

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
| `FRONTEND_URL` | CORS **and every outbound link** | Defaults to `http://localhost:3000`, so **password-reset and verification emails link to localhost**. Add it to CORS automatically. Set `https://holygrill.app` |
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
| `REDIS_URL` | Celery `worker` + `beat` (abandoned carts, scheduled jobs, newsletter batches) | Defaults to `redis://localhost:6379/0` — no broker on Render, so those background jobs never run |
| `WHATSAPP_SUPPORT_NUMBER` | Support button **fallback only** | Only used when the campus has no `system_settings` row. Per-campus rows in `system_settings.whatsapp_support_number` are the real source |
| `WHATSAPP_SUPPORT_MESSAGE` | Prefilled chat text, fallback only | same |

### CORS

`CORS_ORIGINS` / `ALLOWED_ORIGINS` (comma-separated) only **add** to a built-in list that
already contains `https://holygrill.app`, `https://www.holygrill.app` and the localhost dev
ports. A `*` is deliberately ignored. Vercel **preview** URLs
(`holy-grills-<hash>.vercel.app`) are **not** in the list — add them via `CORS_ORIGINS` if
you test on a preview.

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
`PAYSTACK_SANDBOX_MOCK_NUBAN`, `API_PUBLIC_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

---

## 5. Frontend (Vercel) — every one is optional

Confirmed in code: each `import.meta.env.VITE_*` read has an in-code fallback, so an empty
Vercel environment behaves like the current deployment.

| Variable | Fallback in code | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `https://holy-grills-backend.onrender.com/api` | API origin |
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
REDIS_URL=<Render Redis internal URL>
```

## 7. Verify

```
GET https://holy-grills-backend.onrender.com/api/health     # or any documented route
GET https://holy-grills-backend.onrender.com/apidocs        # the API list
```

Then, on the site: log in, place a small order, upload an image in Admin → Storefront, and
trigger a password reset (to confirm the email links to `holygrill.app`, not localhost).
