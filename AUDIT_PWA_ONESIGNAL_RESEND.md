# PWA, OneSignal, Resend & Hard-coded URLs Audit

**Audit Date:** 2026-01-XX  
**Scope:** Read-only audit of PWA, OneSignal, Resend setup and hard-coded URLs

---

## 1. PWA (Progressive Web App)

### ✅ What Exists

#### Manifest (`holy-grills-frontend/public/manifest.json`)
- **name:** "Holy Grill — FUTA's Only Flame Grill"
- **short_name:** "HolyGrill"
- **start_url:** "/"
- **scope:** "/"
- **display:** "standalone"
- **orientation:** "portrait"
- **background_color:** "#FFF5F0"
- **theme_color:** "#FF4E2D"
- **icons:** 5 icons configured
  - `/icons/icon-192.png` (192x192, any)
  - `/icons/icon-512.png` (512x512, any)
  - `/icons/maskable-192.png` (192x192, maskable)
  - `/icons/maskable-512.png` (512x512, maskable)
  - `/icons/icon.svg` (any size, any)
- **shortcuts:** 3 shortcuts configured (Order Food, My Holy Points, Events)
- **share_target:** Configured for `/share` route

#### Icons (`holy-grills-frontend/public/icons/`)
- ✅ `icon-16.png` (16x16)
- ✅ `icon-32.png` (32x32)
- ✅ `icon-192.png` (192x192)
- ✅ `icon-512.png` (512x512)
- ✅ `icon.svg` (vector)
- ✅ `maskable-192.png` (192x192, maskable)
- ✅ `maskable-512.png` (512x512, maskable)
- ✅ `maskable.svg` (vector, maskable)
- ✅ `apple-touch-icon.png` (iOS home screen)

#### Service Worker (`holy-grills-frontend/public/service-worker.js`)
- ✅ **Comprehensive caching strategy:**
  - Navigation: network-first with offline fallback
  - App shell + icons: cache-first, version-busted
  - Images & fonts: stale-while-revalidate
  - Source modules/JS/CSS/API: NEVER cached (prevents stale bundle issues)
- ✅ **OneSignal integration:** `importScripts('https://cdn.onesignal.com/sdks/OneSignalSDKWorker.js')`
- ✅ **Version-busting:** `CACHE_VERSION = 'hg-v2'`
- ✅ **Offline fallback:** `/offline.html`
- ✅ **Update flow:** Listens for `SKIP_WAITING` message
- ✅ **Smart exclusions:** Never caches dev server modules, Vite internals, source files

#### Service Worker Registration (`holy-grills-frontend/src/main.tsx`)
- ✅ Registered in production mode only
- ✅ Development mode: unregisters all workers and clears caches
- ✅ Update detection: listens for `updatefound` and `controllerchange`
- ✅ Auto-reload: reloads page when new service worker takes control

### ❌ What's Missing

1. **`offline.html` page** — Service worker references it but file doesn't exist
   - Impact: Offline fallback will fail silently
   - Fix: Create `/public/offline.html` with a user-friendly offline message

2. **Apple-specific meta tags** — Not checked in HTML files
   - Need to verify: `<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">`
   - Need to verify: `<meta name="apple-mobile-web-app-capable" content="yes">`
   - Need to verify: `<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">`

3. **Theme color meta tag** — Not checked in HTML files
   - Need to verify: `<meta name="theme-color" content="#FF4E2D">`

4. **Manifest link in HTML** — Not checked
   - Need to verify: `<link rel="manifest" href="/manifest.json">`

---

## 2. OneSignal (Push Notifications)

### ✅ What Exists

#### Frontend SDK Init (`holy-grills-frontend/src/lib/onesignal.ts`)
- ✅ **App ID env var:** `VITE_ONESIGNAL_APP_ID` (read from `app.config.ts`)
- ✅ **SDK loading:** Dynamically loads `https://cdn.onesignal.com/sdks/OneSignalSDK.js`
- ✅ **Initialization:** `OneSignal.init()` with config:
  - `appId` from env
  - `notifyButton: { enable: false }` (custom UI)
  - `serviceWorkerParam: { path: '/service-worker.js', scope: '/' }`
  - `serviceWorkerPath: 'service-worker.js'`
- ✅ **External user ID mapping:** `OneSignal.setExternalUserId(userId)`
- ✅ **Device token storage:** Calls `liveApi.auth.deviceToken()` to store `player_id` in DeviceToken entity
- ✅ **Subscription change listener:** Updates device token on `subscriptionChange`
- ✅ **Permission request:** `requestPushPermission()` with 45s timeout, polling, and slidedown prompt
- ✅ **Graceful degradation:** Silent no-op if App ID not configured

#### Service Worker Integration (`holy-grills-frontend/public/service-worker.js`)
- ✅ **OneSignal SDK import:** `importScripts('https://cdn.onesignal.com/sdks/OneSignalSDKWorker.js')`
- ✅ **Harmless if not configured:** Wrapped in try-catch

#### Backend Send Code (`holy-grills-backend/app/services/notification_service.py`)
- ✅ **Env var names:**
  - `ONESIGNAL_APP_ID` — App ID (public, used in payloads)
  - `ONESIGNAL_API_KEY` — REST API key (secret, server-only)
  - `ONESIGNAL_BASE_URL` — API base (defaults to `https://api.onesignal.com`)
- ✅ **Push dispatch:** `_dispatch_push_async()` function
  - Uses `include_aliases: { external_id: [user_id] }` to target user
  - Sets `target_channel: "push"`
  - Supports `urgency="high"` for priority delivery (Android priority 10, iOS time-sensitive)
  - Fire-and-forget, never raises
- ✅ **Email via OneSignal:** `_dispatch_email_via_onesignal()` function
  - Uses `target_channel: "email"`
  - Fallback when Resend quota exceeded
- ✅ **Provider routing:** `get_email_provider()` resolves `resend` or `onesignal`
  - Reads from `system_settings.email_provider_{scope}_default`
  - Supports per-blast override via `email_provider` column
- ✅ **Quota failover:** `send_email_routed()` tries preferred provider, then alternate on quota rejection

### ❌ What's Missing

1. **No OneSignal dashboard webhook** — Not checked
   - OneSignal can send delivery receipts, but no webhook handler found
   - Optional: Track delivery success/failure rates

2. **No player_id cleanup** — Not checked
   - DeviceToken table may accumulate stale tokens
   - Optional: Periodic cleanup of tokens not seen in 90+ days

---

## 3. Resend (Transactional Email)

### ✅ What Exists

#### Client Code (`holy-grills-backend/app/utils/email.py`)
- ✅ **API base:** `RESEND_BASE = "https://api.resend.com"`
- ✅ **Env var names:**
  - `RESEND_API_KEY` — API key (secret, server-only)
  - `EMAIL_FROM` — Sender email address (defaults to `noreply@holygrills.ng`)
  - `EMAIL_FROM_NAME` — Sender display name (defaults to `Holy Grills`)
- ✅ **Email dispatch:** `send_email_routed()` function
  - Prefers Resend by default
  - Falls back to OneSignal on quota rejection (429, 400, 403 with quota error)
  - Never retries ambiguous outcomes (no double-send risk)
- ✅ **HTML builder:** `_build_html()` wraps plain text in responsive HTML shell
- ✅ **Template system:** 16 hardcoded templates in `TEMPLATES` dict:
  - `order_confirmed`, `hp_earned`, `tier_upgrade`, `wallet_funded`
  - `password_reset`, `birthday_bonus`, `referral_completed`, `abandoned_cart`
  - `reward_redeemed`, `tier_grace_period`, `tier_dropped`, `hp_expired`
  - `monthly_birthday_report`, `event_tickets_export`, `event_ticket_qr`
  - `squad_invite`, `guest_order_confirmed`
- ✅ **Admin-editable templates:** Reads from `email_templates` table, falls back to hardcoded
- ✅ **QR ticket emails:** `send_qr_ticket_email()` generates base64 QR code locally (no third-party leak)

#### Which Emails Are Sent

**Transactional (30 types from `EMAIL_TYPES` in notification_service.py):**

**Order (7):**
- `order_confirmed`, `order_delivered`, `order_refunded`
- `order_cancelled`, `order_cancelled_user`, `order_cancelled_admin`, `scheduled_order_cancelled`

**Guest (1):**
- `guest_order_claimed`

**Wallet (2):**
- `wallet_funded_card`, `wallet_funded_bank`

**HP (6):**
- `hp_gift_received`, `hp_transfer_recipient`, `hp_decay_applied`, `hp_decay_warning`
- `winback_70`, `winback_95`, `winback_118`

**Tier (3):**
- `tier_upgrade`, `tier_grace_period`, `tier_downgrade`

**Account (8):**
- `graduation_declared`, `birthday_bonus`, `password_changed`, `password_reset`, `email_verification`
- `account_deleted`, `account_deactivated`, `account_reactivated`

**Events & Marketplace (3):**
- `event_registered`, `marketplace_purchase`, `reward_fulfilled`

**Squad (1):**
- `squad_member_invite`

**Additional (from TEMPLATES dict):**
- `abandoned_cart`, `hp_earned`, `tier_grace_period`, `monthly_birthday_report`
- `event_tickets_export`, `event_ticket_qr`, `guest_order_confirmed`

### ❌ What's Missing

1. **No custom headers support for OneSignal** — OneSignal email doesn't support custom RFC unsubscribe headers
   - Code comment: "Custom RFC unsubscribe headers cannot safely be translated to an undocumented provider field"
   - Workaround: Resend path retained when headers are present

2. **No email analytics** — Not tracking delivery, opens, clicks
   - Resend provides webhooks for this, but not implemented
   - Optional: Track email engagement rates

---

## 4. Hard-coded URLs

### `holy-grills.vercel.app` References

#### Backend (`holy-grills-backend/app/config.py`)
- **Line 43:** `FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://holy-grills.vercel.app")`
  - Default value if env var not set
- **Line 59:** In `DEFAULT_CORS_ORIGINS` tuple
  - Hard-coded as allowed CORS origin

#### Frontend (`holy-grills-frontend/src/config/app.config.ts`)
- **Line 24:** `domain: import.meta.env.VITE_SITE_URL || 'https://holy-grills.vercel.app'`
  - Default domain for canonical URLs, og:url, JSON-LD

#### Documentation
- `docs/ENVIRONMENT_VARIABLES.md` — Multiple references (documentation only)
- `docs/PRE_LAUNCH_QA.md` — Multiple references (documentation only)
- `holy-grills-backend/ENV_CONFIGURATION.md` — Multiple references (documentation only)

### `FRONTEND_URL` Usage

#### Backend Routes & Services
- **`holy-grills-backend/app/routes/orders.py`** (2 occurrences)
  - Builds order confirmation/tracking links
- **`holy-grills-backend/app/routes/referrals.py`** (2 occurrences)
  - Builds referral share links
- **`holy-grills-backend/app/services/auth_service.py`** (2 occurrences)
  - Builds password reset and email verification links
- **`holy-grills-backend/app/services/newsletter_service.py`** (3 occurrences)
  - Builds unsubscribe links
  - Refuses to send if FRONTEND_URL missing/localhost (production guard)
- **`holy-grills-backend/app/services/order_payments.py`** (1 occurrence)
  - Builds Paystack callback URL: `FRONTEND_URL + '/order-confirmation/' + order_id + '?payment_return=1'`

### Impact Analysis

**If you change your domain:**
1. Update `VITE_SITE_URL` on Vercel (frontend)
2. Update `FRONTEND_URL` on Render (backend)
3. Update `CORS_ORIGINS` on Render if different from FRONTEND_URL
4. Code defaults will fallback to `holy-grills.vercel.app` if env vars not set

**CORS is safe:**
- `DEFAULT_CORS_ORIGINS` includes both `holy-grills.vercel.app` and `holygrill.app`
- `FRONTEND_URL` adds to the list, doesn't replace
- Vercel preview deployments auto-allowed via regex pattern

---

## 5. Environment Variables Required

### Vercel (Frontend)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `VITE_API_BASE_URL` | ✅ Yes | Backend API base URL | `https://holy-grills-backend.onrender.com/api` |
| `VITE_SITE_URL` | ⚠️ Recommended | Production domain (canonical URLs, OG tags) | `https://holygrill.app` |
| `VITE_ONESIGNAL_APP_ID` | ⚠️ Optional | OneSignal App ID (enables push notifications) | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |

### Render (Backend)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| **Supabase (Required)** |
| `SUPABASE_URL` | ✅ Yes | Supabase project URL | `https://xxxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ Yes | Supabase service role key (secret) | `eyJhbGc...` |
| `SUPABASE_ANON_KEY` | ✅ Yes | Supabase anon key | `eyJhbGc...` |
| `SUPABASE_JWT_SECRET` | ✅ Yes | JWT secret for verifying Supabase tokens | `your-jwt-secret` |
| **Frontend URL (Required)** |
| `FRONTEND_URL` | ✅ Yes | Production frontend URL (for email links, CORS) | `https://holygrill.app` |
| **CORS (Optional)** |
| `CORS_ORIGINS` | ⚠️ Optional | Comma-separated allowed origins (adds to defaults) | `https://holygrill.app,https://www.holygrill.app` |
| `ALLOW_VERCEL_PREVIEWS` | ⚠️ Optional | Allow Vercel preview deployments (default: true) | `true` |
| **Email (Required for emails)** |
| `RESEND_API_KEY` | ✅ Yes | Resend API key (transactional emails) | `re_xxxxxxxx` |
| `EMAIL_FROM` | ⚠️ Recommended | Sender email address | `noreply@holygrill.app` |
| `EMAIL_FROM_NAME` | ⚠️ Recommended | Sender display name | `Holy Grills` |
| **Push Notifications (Optional)** |
| `ONESIGNAL_APP_ID` | ⚠️ Optional | OneSignal App ID (must match frontend) | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `ONESIGNAL_API_KEY` | ⚠️ Optional | OneSignal REST API key (server-only, secret) | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| **Payments (Required for payments)** |
| `PAYSTACK_SECRET_KEY` | ✅ Yes | Paystack secret key (webhooks, refunds) | `sk_live_xxxxxxxx` |
| `PAYSTACK_PUBLIC_KEY` | ✅ Yes | Paystack public key (frontend) | `pk_live_xxxxxxxx` |
| `PAYSTACK_WEBHOOK_SECRET` | ⚠️ Optional | Paystack webhook secret (falls back to SECRET_KEY) | `your-webhook-secret` |
| **App Config (Optional)** |
| `APP_NAME` | ⚠️ Optional | App name (default: Holy Grills) | `Holy Grills` |
| `APP_TAGLINE` | ⚠️ Optional | App tagline (default: Holy Grills FUTA) | `Made With More Than Flame` |
| `HP_CURRENCY_NAME` | ⚠️ Optional | HP currency name (default: HP) | `HP` |

---

## 6. Summary

### ✅ Strengths
- **PWA:** Comprehensive manifest, icons, service worker with smart caching
- **OneSignal:** Full integration with SDK init, device token storage, provider routing
- **Resend:** Robust email dispatch with quota failover, 16+ templates, admin-editable
- **Security:** No hard-coded secrets, env-driven config, CORS properly configured

### ⚠️ Gaps
1. **Missing `offline.html`** — Service worker references it but file doesn't exist
2. **Missing Apple meta tags** — Not verified in HTML files
3. **No email analytics** — Delivery/opens/clicks not tracked
4. **No player_id cleanup** — DeviceToken table may accumulate stale tokens

### 🔧 Recommendations
1. Create `/public/offline.html` with user-friendly offline message
2. Verify Apple meta tags in `index.html`
3. Set all required env vars on Vercel and Render before going live
4. Consider email analytics webhook from Resend
5. Consider periodic DeviceToken cleanup job

---

## 7. Files Modified

**No files were modified** — this is a read-only audit.

---

**End of Audit**
