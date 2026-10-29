# Web push origin alignment — 29 October 2026

**Scope:** the `PUSH-ORIGIN FAIL` case in
[provider results](FRESH_ENV_PROVIDER_PWA_RESULTS_2026_10_28.md), the
`OneSignal registration and actual device delivery/click` row in
[launch priorities](LAUNCH_PRIORITY_STATUS_2026_10_29.md), and the
`hg-onesignal-origin-fix.json` attempt that was rejected with HTTP 401.

**Status:** root cause fixed in source and regression-tested locally. The host
level half (one Vercel domain setting) is still to be flipped, and a real
recipient receipt/click is still **NOT EXECUTED** — those remain the only open
steps. No dashboard value was changed by this batch.

---

## 1. What the auditor is told (approved wording)

> The web push origin mismatch has been identified. Our OneSignal app was
> configured with the origin `https://holygrills.online`, while the live site
> serves users on `https://www.holygrills.online`. Because browsers treat these
> as two distinct origins (same-origin policy), the push SDK could not
> initialize on the served pages. We are correcting this so the configured
> origin and the final served origin match exactly, and subscriptions are being
> preserved by standardizing on a single origin.

## 2. The measured mismatch

| Fact | Value | Evidence |
| --- | --- | --- |
| OneSignal web origin (Chrome + Safari) | `https://holygrills.online` | `hg-onesignal-origin-fix.json` (`before`) |
| Existing players / messageable | 341 / 340 | same file |
| JWT-triggered dashboard update to `www` | **HTTP 401** — no usable API key; nothing changed | `hg-onesignal-origin-fix.json` (`provider_errors`) |
| Where the deployed site actually serves | `https://www.holygrills.online` | `hg-live-host-map.json` |
| Apex behaviour | `308` → `https://www.holygrills.online/` (apex is **not** primary today) | `hg-live-host-map.json` |
| SDK init on the served origin | `Error: Can only be used on: https://holygrills.online` | `hg-onesignal-origin.json` |

So the redirect currently runs **the wrong way** for push: traffic is pushed
*off* the origin the push app is registered for.

## 3. Decision — option 1 (redirect to a single origin)

Of the two available resolutions, this batch takes **"Redirect to a single
origin"** and standardises on the apex origin `https://holygrills.online`:

| Option | Effect on the 341 existing players | Chosen |
| --- | --- | --- |
| Redirect `www` traffic to the apex origin (dashboard value untouched) | **Kept** — same origin they opted in on, nobody resubscribes | **Yes** |
| Change the dashboard Site URL to `www` | Orphaned — would require deleting the old subscriptions and asking every subscriber to re-enable | No |

Reasons beyond subscriber preservation:

- The 401 above shows the dashboard value cannot be changed safely from this
  checkout anyway (a partial failure here is worse than a documented no-op).
- `VITE_SITE_URL`, `index.html` canonical/OG/JSON-LD, `FRONTEND_URL` and the
  email templates **already** point at the apex origin, so the apex is the
  origin the rest of the product already believes it is.
- The apex origin keeps the `holygrills.online` cookie/storage scope the
  existing subscribers' `external_id` links were created under.

**Do not switch the OneSignal Site URL to `www`.** If that path is ever taken,
the old web-push subscriptions must be deleted first and users told to
re-enable, otherwise one order can produce two notifications.

## 4. What changed in the code

Nothing here touches a provider setting. Both halves point at the same origin.

| File | Change |
| --- | --- |
| `src/lib/canonicalOrigin.ts` *(new)* | Single source of truth for the served origin: `CANONICAL_ORIGIN = https://holygrills.online`, `isWwwAliasHost()`, pure `canonicalRedirectTarget()` (path + query + hash preserved), `enforceCanonicalOrigin()`. Only the `www` alias is normalised — `localhost` and Vercel preview hosts are untouched so push can still be tested. |
| `src/main.tsx` | `boot()` is skipped entirely when the document is on the alias: no React mount, no service-worker registration on an origin push cannot use. This also covers a `www` service worker that follows the host redirect internally and leaves the document on the `www` origin. |
| `src/lib/onesignal.ts` | `initOneSignal()` refuses to start the SDK on the alias (it redirects instead of logging an origin-mismatch error). New exported **`ensurePushReady(userId, timeoutMs)`**: bounded wait for *both* SDK initialization and the `OneSignal.login(userId)` identity step. Identity work extracted into `identify()` so the login path and the button path share one single-flight implementation. |
| `src/lib/webPush.ts` | `subscribeToWebPush(userId?)` now `await`s `ensurePushReady()` **before** `requestPushPermission()`. This is the fix for the "still loading" complaint: a slow SDK load is waited out instead of being reported as a failure. |
| `src/components/notifications/PushSoftPrompt.tsx`, `src/components/challenges/InstallPushBonuses.tsx` | Pass the signed-in id so the tap can start initialization itself and then wait for it. |
| `holy-grills-backend/app/messages.py` | Three registry keys for the new outcomes: origin-only-on-apex, sign-in-required, and "push couldn't load — retry". |
| `scripts/test-canonical-origin.mjs` *(new)*, `scripts/test-push-registration.mjs` (rewritten), `package.json` | Both suites are now part of `npm run build`. The push suite was previously **not wired into the build and was already failing at `HEAD`** (its fixture had no `liveApi.notifications.updatePreferences`, and it asserted a `player_id` field the endpoint has not accepted since it became `token`); it is now fixed *and* extended. |

### Behaviour table for the Enable button

| Situation | Before | Now |
| --- | --- | --- |
| SDK still downloading when the user taps Enable | `OneSignal is still loading — try again in a moment.` | Waits (up to 20 s), then shows the permission prompt |
| Sign-in identity not yet attached | same generic "still loading" | `Sign in to enable push notifications on this device.` |
| CDN blocked / offline / unsupported browser | same generic "still loading", forever retryable | `Push couldn't load on this connection. Check your network and tap Enable again.` |
| Page on `www.holygrills.online` | SDK init error in console (`Can only be used on: …`) | Moved to `https://holygrills.online` with path/query/hash intact; SDK never initializes on the alias |
| App ID missing | "not configured" | "not configured" (unchanged) |

## 5. What still has to be done by a human (one setting)

**Vercel → project → Settings → Domains:**

1. Make `holygrills.online` the primary/apex domain (currently
   `https://holygrills.online` answers `308 → https://www.holygrills.online/`).
2. Set `www.holygrills.online` → **Redirect to** `holygrills.online`
   (308, path/query preserved).

That is the whole host-side fix, and it needs no OneSignal change: the
dashboard already says `https://holygrills.online`, which becomes the only
origin that ever serves the app.

Do **not** delete subscriptions, and do not touch the OneSignal Site URL. After
the flip the deployment is single-origin and the 341 existing players keep
working.

The in-app guard in §4 is not a substitute for this step — it is a guarantee
that a stray `www` document (old service worker, preview alias, a redirect that
has not propagated) cannot silently re-break push before someone notices.

## 6. Verification

### 6.1 Local regression (executed in this batch, production build)

| Check | Command | Result |
| --- | --- | --- |
| Types | `npx tsc --noEmit` | pass |
| Canonical-origin contract | `npm run test:canonical-origin` | **18/18 ok** — alias normalises to the apex origin, path/query/hash kept, lookalike domain and localhost untouched, no redirect loop |
| Push readiness/registration | `npm run test:push-registration` | **PASS** — no permission prompt during setup, slow-SDK tap waits instead of failing, stalled SDK reports the retryable message, guest gets the sign-in message, `www` alias performs **zero** SDK init/login calls and is redirected with the URL intact |
| Message registry | `npm run messages:check` | pass — every call site resolves, no new drift |
| Full production build (`routes:check` → worker/PWA/messages/banner/… → `build:client` → `build:ssr` → `test:storefront-ssr` → `prerender`) | `npm run build` | exit 0 |
| Generated-host smoke (CSP hash, headers, 404s, assets) | `npm run smoke` | `[smoke] PASS` |
| Guard really shipped | `grep -l "www.holygrills.online" dist/assets/*.js` | present in the entry chunk every pre-rendered route loads |

Machine-readable copy: `docs/evidence/fresh-provider-pwa-2026-10-28/hg-onesignal-origin-alignment-regression.json`.

### 6.2 Live checks after deploying this batch + flipping the domain

1. `https://www.holygrills.online/menu?x=1` → `308` → `https://holygrills.online/menu?x=1`.
2. On `https://holygrills.online`: DevTools console shows **no**
   `Can only be used on: …` error, and
   `window.OneSignalDeferred` resolves with the v16 SDK.
3. Tap **Enable push notifications**: the button shows its spinner while the SDK
   loads and then opens the browser prompt — it must not print "still loading"
   on a throttled ("Slow 3G") connection.
4. Application → Service workers: exactly one registration, scoped to
   `https://holygrills.online/`.
5. One authorised recipient: subscribe, confirm the row in `device_tokens`,
   send one targeted notification, confirm device receipt and tap target.

Steps 1–4 are the `PUSH-ORIGIN` case. Step 5 remains
`PUSH-DEVICE NOT EXECUTED` until it is run against a real device.

## 7. Not claimed

- No live re-probe of OneSignal/Vercel happens in this batch: the host redirect
  is still `apex → www` in `hg-live-host-map.json` until the setting in §5 is
  flipped. `PUSH-ORIGIN` therefore moves from **FAIL** to **FIX SHIPPED,
  LIVE VERIFICATION PENDING**, not to PASS.
- No subscription was created, deleted or migrated; no dashboard or provider
  setting was written; no notification was sent.
- Device receipt/click (`PUSH-DEVICE`) is unchanged and still not executed.
