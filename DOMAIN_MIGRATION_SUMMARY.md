# Domain Migration to holygrills.online

## Summary of Changes

This document describes all changes made to migrate the Holy Grills application from the old domains (`holy-grills.vercel.app`, `holygrill.app`, `holygrills.ng`) to the new domain `holygrills.online`.

---

## Files Modified

### 1. Backend Configuration (`holy-grills-backend/app/config.py`)

**FRONTEND_URL Environment Variable:**
- **Before:** `FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://holy-grills.vercel.app")`
- **After:** Production environments now **require** `FRONTEND_URL` to be set explicitly. No default fallback.
- **Change:** Added validation that raises `RuntimeError` if `FRONTEND_URL` is missing in production (detected via `RENDER`, `RAILWAY_ENVIRONMENT`, or `NODE_ENV=production` environment variables).

**CORS Origins:**
- **Before:**
  ```python
  DEFAULT_CORS_ORIGINS = (
      "https://holy-grills.vercel.app",
      "https://holygrill.app",
      "https://www.holygrill.app",
      ...
  )
  ```
- **After:**
  ```python
  DEFAULT_CORS_ORIGINS = (
      "https://holygrills.online",
      "https://www.holygrills.online",
      ...
  )
  ```

**Email Sender:**
- **Before:** `EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")`
- **After:** `EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@holygrills.online")`

---

### 2. Email Utility (`holy-grills-backend/app/utils/email.py`)

**Fallback Email Sender:**
- **Before:** `from_email = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")`
- **After:** `from_email = os.environ.get("EMAIL_FROM", "noreply@holygrills.online")`

---

### 3. Frontend Configuration (`holy-grills-frontend/src/config/app.config.ts`)

**Site Domain:**
- **Before:** `domain: import.meta.env.VITE_SITE_URL || 'https://holy-grills.vercel.app'`
- **After:** `domain: import.meta.env.VITE_SITE_URL || (import.meta.env.DEV ? 'http://localhost:5173' : '')`
- **Change:** Production builds now require `VITE_SITE_URL` to be set. No silent fallback to old domain.

---

### 4. Frontend HTML (`holy-grills-frontend/index.html`)

**All hardcoded domain references updated:**
- `<link rel="canonical" href="https://holygrills.online/" />`
- `<meta property="og:url" content="https://holygrills.online/" />`
- `<meta property="og:image" content="https://holygrills.online/og-cover.jpg" />`
- `<meta name="twitter:image" content="https://holygrills.online/og-cover.jpg" />`
- JSON-LD structured data: `"url": "https://holygrills.online/"`

**PWA Tags (already present, verified):**
- ✅ `<link rel="manifest" href="/manifest.json" />`
- ✅ `<meta name="theme-color" content="#FF4E2D" />`
- ✅ `<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />`
- ✅ `<meta name="apple-mobile-web-app-capable" content="yes" />`
- ✅ `<meta name="apple-mobile-web-app-status-bar-style" content="default" />`

---

### 5. Offline Page (`holy-grills-frontend/public/offline.html`)

**Completely redesigned with brand colors:**
- **Theme color:** `#FF4E2D` (flame orange)
- **Background:** `#FFF5F0` (warm cream)
- **Features:**
  - Animated flame icon with gradient
  - "You're offline" message with flame emoji
  - Connection status card with diagnostic tips
  - "Try again" button with loading spinner
  - Auto-redirect when connection is restored
  - Dark mode support via `prefers-color-scheme`
  - Fully responsive design
  - PWA meta tags included

---

### 6. Environment Examples

**Backend (`.env.example`):**
- `FRONTEND_URL=https://holygrills.online`
- `EMAIL_FROM=noreply@holygrills.online`
- `SWAGGER_CONTACT_EMAIL=dev@holygrills.online`

**Frontend (`.env.example`):**
- `VITE_SITE_URL=https://holygrills.online`

---

### 7. Documentation (`holy-grills-backend/README.md`)

- Updated `EMAIL_FROM` example from `noreply@holygrills.ng` to `noreply@holygrills.online`

---

## Environment Variables to Update

### Render (Backend)

**Required:**
```bash
FRONTEND_URL=https://holygrills.online
```

**Optional (recommended):**
```bash
EMAIL_FROM=noreply@holygrills.online
CORS_ORIGINS=https://holygrills.online,https://www.holygrills.online
```

**Note:** The backend will **fail to start** in production if `FRONTEND_URL` is not set. This is intentional to prevent password reset emails and other links from pointing to the old domain.

---

### Vercel (Frontend)

**Required:**
```bash
VITE_SITE_URL=https://holygrills.online
```

**Note:** The frontend build will use an empty string for the domain if `VITE_SITE_URL` is not set in production. This will break canonical URLs and Open Graph tags.

---

## What Uses FRONTEND_URL / VITE_SITE_URL

### Backend (FRONTEND_URL)

1. **Password reset emails** — `holy-grills-backend/app/services/auth_service.py`
   - Builds reset link: `${FRONTEND_URL}/reset-password?token=...`

2. **Email verification** — `holy-grills-backend/app/services/auth_service.py`
   - Builds verification link: `${FRONTEND_URL}/verify-email?token=...`

3. **Paystack payment callback** — `holy-grills-backend/app/services/order_payments.py`
   - Callback URL: `${FRONTEND_URL}/order-confirmation/${order_id}?payment_return=1`

4. **Newsletter unsubscribe** — `holy-grills-backend/app/services/newsletter_service.py`
   - Unsubscribe link: `${FRONTEND_URL}/unsubscribe?token=...`

5. **Order tracking links** — `holy-grills-backend/app/routes/orders.py`
   - Order details link: `${FRONTEND_URL}/orders/${order_id}`

6. **Referral links** — `holy-grills-backend/app/routes/referrals.py`
   - Referral share link: `${FRONTEND_URL}/referrals?ref=${user_id}`

7. **OneSignal notification action URLs** — `holy-grills-backend/app/services/notification_service.py`
   - Push notification tap target: `/orders/${order_id}`, `/rewards`, etc. (relative paths, resolved by frontend)

### Frontend (VITE_SITE_URL)

1. **Canonical URLs** — `holy-grills-frontend/src/hooks/useSEO.ts`
   - `<link rel="canonical" href="${VITE_SITE_URL}${path}" />`

2. **Open Graph tags** — `holy-grills-frontend/src/hooks/useSEO.ts`
   - `<meta property="og:url" content="${VITE_SITE_URL}${path}" />`

3. **JSON-LD structured data** — `holy-grills-frontend/src/lib/seoJsonLd.ts`
   - Restaurant schema: `"url": "${VITE_SITE_URL}"`

4. **App config domain** — `holy-grills-frontend/src/config/app.config.ts`
   - `APP_CONFIG.domain` used throughout the app

---

## What Does NOT Need Changing

### OneSignal Push Notifications

OneSignal notification action URLs are **relative paths** (e.g., `/orders/123`, `/rewards`). These are resolved by the browser relative to the current origin, so they work correctly regardless of the domain.

**Code:** `holy-grills-backend/app/services/notification_service.py`
```python
payload["url"] = action_url  # action_url is a relative path like "/orders/123"
```

No changes needed.

---

### Resend Email Sending

The Resend API sends emails from the backend. The `EMAIL_FROM` address determines the sender, which has been updated to `noreply@holygrills.online`.

**Important:** You must verify `noreply@holygrills.online` as a sender domain in your Resend dashboard, or emails will be rejected.

---

### Paystack Webhooks

Paystack webhooks are sent to the backend (Render), not the frontend. The webhook URL is configured in the Paystack dashboard and should point to:
```
https://your-render-url.onrender.com/api/webhooks/paystack
```

No changes needed to the webhook URL itself.

---

### CORS Configuration

The backend now allows:
- `https://holygrills.online`
- `https://www.holygrills.online`
- All localhost dev ports (5173, 4173, 4174)
- Vercel preview deployments (pattern: `^https://holy-grills[a-z0-9-]*\.vercel\.app$`)

Additional origins can be added via the `CORS_ORIGINS` environment variable.

---

## Verification Checklist

After deploying, verify the following:

### Backend (Render)

- [ ] Set `FRONTEND_URL=https://holygrills.online` in Render environment variables
- [ ] Restart the backend service
- [ ] Verify the backend starts without errors
- [ ] Test password reset email → link should point to `https://holygrills.online/reset-password`
- [ ] Test Paystack payment → callback should redirect to `https://holygrills.online/order-confirmation/...`
- [ ] Test newsletter unsubscribe → link should point to `https://holygrills.online/unsubscribe`

### Frontend (Vercel)

- [ ] Set `VITE_SITE_URL=https://holygrills.online` in Vercel environment variables
- [ ] Redeploy the frontend
- [ ] View page source → canonical URL should be `https://holygrills.online/`
- [ ] View page source → og:url should be `https://holygrills.online/`
- [ ] View page source → JSON-LD should have `"url": "https://holygrills.online/"`
- [ ] Test offline mode → should see branded offline page with flame icon

### Email (Resend)

- [ ] Verify `holygrills.online` domain in Resend dashboard
- [ ] Verify `noreply@holygrills.online` as a sender address
- [ ] Send a test email → should come from `noreply@holygrills.online`

### PWA

- [ ] Install the PWA on mobile → should use `holygrills.online` domain
- [ ] Go offline → should see branded offline page
- [ ] Go back online → should auto-redirect to home

---

## Rollback Plan

If issues arise, you can temporarily revert by:

1. **Backend:** Set `FRONTEND_URL=https://holy-grills.vercel.app` (or the working domain)
2. **Frontend:** Set `VITE_SITE_URL=https://holy-grills.vercel.app`
3. Redeploy both services

However, this is not recommended long-term. The old domains should be considered deprecated.

---

## Migration Date

**Completed:** 2026-01-XX

**Old Domains (deprecated):**
- `holy-grills.vercel.app`
- `holygrill.app`
- `www.holygrill.app`
- `holygrills.ng`

**New Domain:**
- `holygrills.online` ✅
- `www.holygrills.online` ✅ (redirects to apex domain)

---

## Notes

- The backend will **fail fast** if `FRONTEND_URL` is not set in production. This is intentional to prevent broken links in emails.
- The frontend will build with an empty domain if `VITE_SITE_URL` is not set, which will break SEO tags.
- All PWA manifest references already use relative paths (`/manifest.json`, `/icons/...`), so they work correctly regardless of domain.
- The service worker caches are version-busted (`hg-v2`), so users will get fresh content after the update.
- OneSignal push notifications use relative action URLs, so they work on any domain.

---

## Support

If you encounter issues after migration:

1. Check Render logs for `FRONTEND_URL` errors
2. Check Vercel build logs for missing `VITE_SITE_URL`
3. Verify Resend domain is verified
4. Clear browser cache and service worker (Ctrl+Shift+R / Cmd+Shift+R)
5. Check CORS errors in browser console → may need to add origin to `CORS_ORIGINS`

---

**End of Migration Summary**
