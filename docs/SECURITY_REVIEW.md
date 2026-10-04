# Phase 7 — frontend security review

Scope: the React/Vite frontend that the TypeScript migration and Track B
(pre-rendering) produced, plus the parts of the frontend↔backend contract that
touch credentials, money or authorisation. The Flask backend was reviewed only
where the frontend depends on it; its internals are out of scope.

Method: source sweep of `holy-grills-frontend/src` for the usual sinks
(`dangerouslySetInnerHTML`, `innerHTML`, `eval`, `document.write`,
`javascript:`), credential and storage inventory, dependency audit
(`npm audit --omit=dev`) cross-checked against what actually ships in
`dist/`, a scan of the built bundles for secret-shaped strings, and a
review of the redirect/URL-assignment sites. Every finding below cites the
file and line it came from.

## Summary

| # | Severity | Finding | Status |
|---|---|---|---|
| S1 | Medium | Payment redirect targets (`authorization_url`) were assigned to `window.location.href` unvalidated — 3 sites | **applied** |
| S2 | Medium | Password-reset token stays in the URL after use (history, referrer, shoulder-surfing) | **applied** (+ confirmation screen) |
| S3 | Medium | Access/refresh tokens live in `localStorage`/`sessionStorage` — XSS-reachable by design | accepted (frozen), mitigate via S4 |
| S4 | Medium | No CSP and no security headers anywhere (`vercel.json` had no `headers` key) | **applied** — report-only, see below |
| S5 | Low–Med | `npm audit`: 16 findings, now **11** after S6; the rest are build-chain or the react-router moderates | reduced |
| S6 | Low | 15 declared runtime dependencies were never imported | **applied** — removed, build unchanged |
| S7 | Low | Server-provided `call_link` was assigned to `window.location.href` unvalidated — 2 sites | **applied** |
| S8 | Low | CMS link fields were handled inconsistently | **applied** (one shared rule) |
| S9 | Low | Google Fonts loaded from a third-party origin on every page (privacy/supply chain) | proposed (later) |
| S10 | Info | Guest `claim_token` and a `hg_admin_*` selector in storage; sidebar cookie has no flags; one GPS `console.log` | documented |

> **Applied (2026-10-04):** S1, S2, S4, S6, S7, S8. Still open: S9 (self-hosted
> fonts, deliberately deferred) and the react-router decision (see the last
> section). Everything below is the finding as written plus what shipped.

**Verified clean** (evidence in the last section): no `eval`/`innerHTML`/
`javascript:` sinks in app code, **no secrets in the shipped bundles**, no token
logging, all `target="_blank"` links carry `noopener noreferrer`, the service
worker never caches API responses, the Cloudinary upload signature is minted by a
role-guarded backend route, and the backend enforces roles on admin routes.

---

## S1 — Payment redirects are not validated (medium) — **applied**

```
src/components/events/RegisterModal.tsx:73       window.location.href = res.authorization_url;
src/components/marketplace/PurchaseModal.tsx:61  window.location.href = res.authorization_url;
src/components/wallet/WalletFundModal.tsx:58     window.location.href = result.authorization_url;
```

Each value comes from the backend's Paystack handoff. `window.location.href`
accepts `javascript:` URIs and executes them, and `//host/` is protocol-relative,
so a malformed or attacker-influenced response is a script-execution primitive in
the payment flow.

Applied: `src/lib/safeNavigation.ts` exports `isAllowedPaymentUrl()` — https on
`paystack.com` or a subdomain (`checkout.paystack.com` is where Paystack's
initialize call points, and it is the only provider this app uses). All three
sites check before assigning. A refusal is loud, never silent: the two modals
throw into their existing error toast, and `WalletFundModal` — whose `handleFund`
is a bare `onClick` and whose catch rethrows — shows its own destructive toast
instead of failing invisibly. Payments fail *closed*: a URL that does not match is
not followed.

## S2 — Reset token persists in the URL (medium)

```
src/pages/ResetPassword.tsx:9   const resetToken = searchParams.get("token");
src/pages/ResetPassword.tsx:42  await liveApi.auth.confirmReset({ access_token: resetToken, ... });
```

The token is read from `?token=…` and left in place for the life of the page: it
lands in browser history, in any "copy link" the user performs, and in the
`Referer` of any cross-origin request the page makes (modern browsers trim the
path by default, but that is a browser default, not a guarantee).

**Applied fix:** the token is captured once into state, then
`history.replaceState(null, '', window.location.pathname)` drops it from the
address bar. It is still sent to the backend in the POST body — never in a URL.
Two details worth knowing:

- The token is captured in a **state initialiser** (`useState(() => searchParams.get('token'))`).
  Reading it straight from `searchParams` would break the moment the URL is
  scrubbed: the parameter would disappear and the page would flip to its
  "invalid link" state mid-flow.
- **A refresh before submitting now needs a new email link**, because the token
  only exists in that page's memory. Submitting works exactly as before.

**Success screen.** The flow used to bounce straight to `/login` on success. It now
shows a confirmation — "Password changed … every other session on your account has
been signed out" (which the backend really does: `_revoke_supabase_sessions` in
`app/routes/auth.py`) — with a "Continue to login" link. Auto-login was
deliberately *not* added: it would mean silently authenticating with the new
password on a screen reached from an emailed link.

## S3 — Tokens in web storage (medium, accepted)

```
src/lib/apiClient.ts:8    const TOKEN_KEY = 'hg_access_token';
src/lib/apiClient.ts:9    const REFRESH_KEY = 'hg_refresh_token';
src/lib/apiClient.ts:15   const storage = () => isRemember() ? localStore : sessionStore;
```

Any XSS that runs on the origin can read the session; that is inherent to the
frozen "token in localStorage" decision, and moving to httpOnly cookies would
change the auth contract (out of scope). Two mitigations are cheap and already
mostly in place: short access-token TTL (backend `JWT_ACCESS_TOKEN_EXPIRES`,
default 1 h) and the refresh-on-401 path. The third, a CSP, is S4.

## S4 — No CSP, no security headers (medium) — **applied, report-only**

`vercel.json` contained only `installCommand`, `buildCommand`,
`outputDirectory`, `routes` — no `headers` block — and no page carried a
`Content-Security-Policy` meta tag. For a token-in-localStorage app, CSP is the
main structural defence against XSS and the one thing S1/S3 lean on.

What shipped (2026-10-04): `scripts/routes.mjs` now emits a `headers` block for
every path in the generated `vercel.json`, `scripts/serve-static.mjs` applies those
rules locally so they are testable, and `scripts/smoke.mjs` asserts them.

- **`Content-Security-Policy-Report-Only`** — nothing is blocked. The string is
  built from the origins the source actually uses (script/style/font/image/
  connect/frame/worker), with the API origin read from `VITE_API_BASE_URL` so a
  staging backend does not need a policy edit. Every third-party origin named
  above was checked to be present in the generated header.
- **Enforcing** alongside it: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY` (clickjacking — `frame-ancestors` is ignored in
  report-only mode, so this is the real defence), `Referrer-Policy:
  strict-origin-when-cross-origin` (also covers S2), HSTS, and a
  `Permissions-Policy` that keeps geolocation to self while turning camera and
  microphone off.

**Next step (needs a browser):** load `/`, `/menu`, a paid checkout and the rider
map, watch the console for `[Report Only]` violations, and once the policy is
clean change the header name from `Content-Security-Policy-Report-Only` to
`Content-Security-Policy` — one word in `scripts/routes.mjs`, then
`npm run routes:sync`. One known complication: `index.html:78` has an inline
`<script>` (the dev-only service-worker cleanup), which a strict `script-src`
blocks; it is static text, so a SHA-256 hash belongs in the policy or the snippet
should move into the bundled entry.

## S5 — `npm audit` findings (low–medium)

`npm audit --omit=dev`: **16 vulnerabilities — 8 high, 7 moderate, 1 low.** What
matters is which of those can reach a user:

| Package | Via | Ships to the browser? | Assessment |
|---|---|---|---|
| `dompurify` (mod), `fflate` (mod) | `jspdf` | ❌ not in `dist/` | `jspdf` is never imported (S6) |
| `quill` (mod) | `react-quill` | ❌ not in `dist/` | `react-quill` is never imported (S6) |
| `moment` (mod) | direct | ❌ not in `dist/` (the `moment` hits in the bundle are the English word) | never imported (S6) |
| `react-router`, `react-router-dom` (3 mod) | direct, 6.30.4 | ✅ | see applicability below |
| `postcss`, `postcss-selector-parser`, `nanoid`, `braces`, `micromatch`, `chokidar`, `fast-glob`, `tailwindcss` | build chain | ❌ build-time only | not reachable from a browser |

**react-router applicability.** The advisories are an open redirect via backslash
in `<Link>`/`useNavigate`, and constructor injection via `deserializeErrors()` in
SSR hydration. Neither is reachable here: every in-app navigation target is a
literal path or an id interpolated into a fixed path, `Notifications.tsx:23`
already restricts deep links to `target.startsWith('/')`, and the app uses no
data router, no `deserializeErrors()` and no Remix-style hydration errors — our
pre-render hydrates a plain `StaticRouter` tree. The remaining "fix" is
react-router **7.18+** (a major upgrade: `react-router-dom/server` moves, breaking
API surface), so it belongs in a planned upgrade, not in this round.

## S6 — Dependencies declared but never imported (low) — **applied**

Scan of every import/require/dynamic-import/`@import` in `src/`, `index.html` and
the build configs, cross-checked against the built bundles. These were in
`package.json` and neither imported nor present in `dist/`:

```
@hello-pangea/dnd   @hookform/resolvers   @radix-ui/react-toast
@stripe/react-stripe-js   @stripe/stripe-js   date-fns   html2canvas
jspdf   lodash   moment   react-hot-toast   react-markdown
react-quill   three   zod
```

Removed on 2026-10-04 and verified in this order: `npm run typecheck` ✅,
`npm run lint` ✅, `npm run build` ✅ (33 route families, 7 pre-renders),
`npm run smoke` ✅ PASS — and the entry chunk kept its content hash
(`index-CrnT1mY2.js`), which proves no byte of shipped output depended on them.
`npm audit --omit=dev` went **16 → 11** findings (`dompurify`, `fflate`, `quill`
and `moment` left with their parents). `lodash` stays installed transitively via
`recharts`; `three` is gone entirely; `tailwindcss-animate` was *not* removed — it
is used from `tailwind.config.js`.

## S7 — `tel:` link from the server not validated (low)

```
src/pages/OrderDetail.tsx:163   if (callLink) { window.location.href = callLink; return; }
src/hooks/useRiderData.ts:135   window.location.href = (link && (link.call_link || link.call_url)) || '';
```

The comment at `OrderDetail.tsx:160` says the link is fetched from
`GET /orders/<id>/call-rider` rather than trusted from the order object — good
instinct, but the fetched value is still assigned unchecked. A `javascript:`
value here would run in the origin. Applied: both sites run the value through `safeCallHref()`
(`tel:` payload reduced to digits and a leading `+`; `https://` allowed for
click-to-chat; anything else returns null → the existing "no number available"
message). The scheme test is done on the raw string, **not** after resolving
against the current origin — a relative-resolution first draft turned junk like
`"not a url"` into a valid same-origin https URL and would have navigated away
instead of reporting no number. The test suite below covers that case.

## S8 — CMS link fields handled inconsistently (low)

```
src/components/storefront/PromoFlyerPopup.tsx:58  if (/^https?:\/\//.test(dest)) window.open(dest, '_blank', 'noopener,noreferrer'); else navigate(dest);
src/components/HeroCarousel.tsx:120               else navigate(dest);                    // no guard
src/components/storefront/StorefrontSlider.tsx:98 navigate(dest);                        // no guard
```

react-router normalises absolute URLs to a path rather than leaving the origin,
so this was not an open redirect to another site; the risk was a hostile/broken
CMS value producing odd navigation.

Applied: `openCmsDestination(dest, navigate)` in `src/lib/safeNavigation.ts` is now
the single rule — absolute `http(s)` opens in a new tab with `noopener,noreferrer`,
anything else goes through `navigate()`. `HeroCarousel`, `StorefrontSlider` and
`PromoFlyerPopup` all call it, so a CMS link behaves the same wherever it appears.

## Covered by `npm run test:safe-navigation`

`scripts/test-safe-navigation.mjs` transpiles the real module with esbuild and
asserts the policy: payment URLs are refused for `http:`, `javascript:`, other
hosts and look-alikes such as `evil-paystack.com`; call links are refused for
`javascript:`, `http:`, too-short `tel:` values and plain junk, and normalised for
`tel:+234 801 234 5678`; CMS links open externally with `noopener,noreferrer` and
internally through the router. It runs in CI between lint and build (that is how
the relative-resolution bug above was caught).

## S9 — Third-party font CSS (low, deferred)

`index.html:45–47` preconnects to and loads `fonts.googleapis.com` on every page,
including pre-rendered ones. That is a privacy leak (IP + referrer to Google on
every visit) and a third-party CSS execution surface. Self-hosting the two
families removes both and is a perf win; it is a build-output change, so it is
noted here and left for a later round.

## S10 — Informational

- `hg_guest_orders` stores up to 10 guest orders with their `claim_token`
  (`Checkout.tsx:284`). That token is a capability for the guest order view; it is
  required for guest tracking and scoped to the guest's own browser, but it is
  readable by any XSS. Same mitigation as S3/S4.
- `ui/sidebar.tsx:84` writes `document.cookie` with no `Secure`/`SameSite`
  attributes (UI state only, no security value).
- `ErrorBoundary.componentDidCatch` (`:23`) logs the error object to the console;
  errors are not sent anywhere, so nothing leaves the browser.
- `OffCampusMap.tsx:140` logs GPS coordinates to the console (dev convenience,
  visible to the user only).

## Verified clean

| Check | Evidence |
|---|---|
| No XSS sinks in app code | only `ui/chart.tsx:84` (developer-defined theme strings rendered into a `<style>` tag) and `main.tsx:20` (`container.innerHTML = ''`, a clear) |
| No secrets in the shipped bundle | `dist/assets/*.js` contain no `service_role`, `SUPABASE_SERVICE`, `sk_live`/`sk_test`, `PAYSTACK_SECRET`, `JWT_SECRET`; no `VITE_*` placeholder survives inlining |
| Secrets are env-only | `VITE_API_BASE_URL`, `VITE_SITE_URL`, `VITE_ONESIGNAL_APP_ID`, `VITE_ASSET_CDN_URL` are all public-safe values |
| No token logging | one `console.log` in the whole of `src/`, and it is GPS coordinates |
| `target="_blank"` | all four sites carry `rel="noopener noreferrer"` |
| Service worker | API responses are never cached (`public/service-worker.js:8,119`); only images/fonts get a runtime cache |
| Cloudinary uploads | signature minted server-side by `POST /upload/signature` (`app/routes/uploads.py:18–21`), `@require_auth` + folder scoping in the handler — admins may target any folder, everyone else only their own profile-photo folder. **Note:** the frontend comment (`admin/ImageUploader.tsx:30`) claims `@require_role("admin")`, which overstates the guard; the comment should be corrected to match the route |
| Server-side authorisation | 239 `@require_role` guards across `app/routes/`; client-side role gates are UX only |
| Pre-rendered HTML | contains no user data (B7 verification) — no authed content is baked into any pre-rendered file |
| Deep-link guard | `Notifications.tsx:23` only navigates relative paths from a notification payload |
| Auth transport | Bearer tokens in headers, no cookies and no `credentials: 'include'`, so CSRF does not apply; refresh token is sent in a POST body, never in a URL |

## Proposed order of work

1. **S6** dependency removal (mechanical, verifiable by build + smoke, halves the audit noise).
2. **S1 + S7** URL-scheme helper (small, localised, removes the script-execution primitives).
3. **S2** reset-token URL scrub (one line, no UX change).
4. **S8** shared CMS-link helper.
5. **S4** CSP + security headers through the `vercel.json` generator, shipped report-only first.
6. **S9** self-hosted fonts — later, with the next perf round.
7. **react-router 7** — planned upgrade on its own branch, not folded into this work.

Nothing in this document has been applied yet; each item is a proposal.

---

## react-router 7 — cost and benefit (decision: skipped for now)

We are on `react-router-dom@6.30.4`; the latest 6.x is `6.30.6`, and all 6.x
versions carry the three moderate advisories. The fix line is **7.18+**.

**What the advisories actually need**

1. *Open redirect via backslash in `<Link>`/`useNavigate>`* — an attacker-controlled
   target string. Every navigation target in this app is a literal (`/admin`,
   `/kitchen`, …) or an id interpolated into a fixed path; the one place a payload
   could influence a destination is notifications, and that already requires
   `target.startsWith('/')`.
2. *Constructor injection via `deserializeErrors()` in SSR hydration* — a
   Remix/data-router code path. This app has no data router: the pre-render is a
   plain `StaticRouter` tree, and the browser entry is `BrowserRouter`.

So neither is reachable today. `npm audit` will keep listing them, which is the
real cost of staying — noise, not exposure.

**What the upgrade costs**

- `react-router-dom/server` no longer exists as such; `StaticRouter` moves to the
  `react-router` package, so `src/entry-server.tsx` changes.
- v7 requires React 18+ (we are on 18.3.1, fine) but renames/moves several APIs;
  `json`/`defer` and the `future` flags of 6.x are gone, so every `useNavigate`,
  `Link`, `useSearchParams` and route definition needs a type-level pass.
- `scripts/routes.mjs` parses `<Route path="...">` out of `App.tsx` for the
  `vercel.json` route families — it must still find 39 routes after the migration,
  which is a good automatic check on the upgrade.
- Verification cost is one full cycle: typecheck, lint, build (7 pre-renders),
  smoke, plus the browser hydration check that is already outstanding.

**Options if it is revisited:** (a) upgrade on its own branch with nothing else in
flight — the honest way; (b) stay on 6.x and keep the advisories documented as
not-applicable — what we are doing now; (c) upgrade only if a React 19 migration is
planned, since the two would otherwise be done twice.

**Recommendation:** leave it. There is no exposure to remove today, and the upgrade
is a behaviour-adjacent change that deserves its own round with the browser
hydration check available.
