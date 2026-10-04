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
| S1 | Medium | Payment redirect targets (`authorization_url`) are assigned to `window.location.href` with no scheme/host validation — 3 sites | proposed |
| S2 | Medium | Password-reset token stays in the URL after use (history, referrer, shoulder-surfing) | proposed |
| S3 | Medium | Access/refresh tokens live in `localStorage`/`sessionStorage` — XSS-reachable by design | accepted (frozen), mitigate via S4 |
| S4 | Medium | No CSP and no security headers anywhere (`vercel.json` has no `headers` key; `index.html` has no meta policy) | proposed |
| S5 | Low–Med | 16 `npm audit` findings; 4 of the flagged packages are pulled in by dependencies the source never imports | proposed (S6 fixes half) |
| S6 | Low | 13 declared runtime dependencies are never imported — dead weight and extra supply-chain surface | proposed |
| S7 | Low | Server-provided `call_link` assigned to `window.location.href` without validating the `tel:` scheme — 2 sites | proposed |
| S8 | Low | CMS link fields are handled inconsistently: one site guards external URLs, two `navigate()` any string | proposed |
| S9 | Low | Google Fonts loaded from a third-party origin on every page (privacy/supply chain) | proposed (later) |
| S10 | Info | Guest `claim_token` and a `hg_admin_*` selector in storage; sidebar cookie has no flags; one GPS `console.log` | documented |

**Verified clean** (evidence in the last section): no `eval`/`innerHTML`/
`javascript:` sinks in app code, **no secrets in the shipped bundles**, no token
logging, all `target="_blank"` links carry `noopener noreferrer`, the service
worker never caches API responses, the Cloudinary upload signature is minted by a
role-guarded backend route, and the backend enforces roles on admin routes.

---

## S1 — Payment redirects are not validated (medium)

```
src/components/events/RegisterModal.tsx:73       window.location.href = res.authorization_url;
src/components/marketplace/PurchaseModal.tsx:61  window.location.href = res.authorization_url;
src/components/wallet/WalletFundModal.tsx:58     window.location.href = result.authorization_url;
```

Each value comes from the backend's Paystack handoff. `window.location.href`
accepts `javascript:` URIs and executes them, and `//host/` is protocol-relative,
so a malformed or attacker-influenced response is a script-execution primitive in
the payment flow — the worst place to have one. The backend is trusted here, which
is why this is medium and not high, but the client should not be the place where
that trust is unbounded.

**Proposed fix:** one helper that only allows `https:` and (for this flow) hosts
under an allow-list (`checkout.paystack.com`, plus the configured API origin), and
falls back to an error toast. Apply at the three sites.

## S2 — Reset token persists in the URL (medium)

```
src/pages/ResetPassword.tsx:9   const resetToken = searchParams.get("token");
src/pages/ResetPassword.tsx:42  await liveApi.auth.confirmReset({ access_token: resetToken, ... });
```

The token is read from `?token=…` and left in place for the life of the page: it
lands in browser history, in any "copy link" the user performs, and in the
`Referer` of any cross-origin request the page makes (modern browsers trim the
path by default, but that is a browser default, not a guarantee).

**Proposed fix:** after reading it, `history.replaceState(null, '', '/reset-password')`
so the token exists only in memory; keep sending it in the POST body (already the
case — it is never sent in a URL).

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

## S4 — No CSP, no security headers (medium)

`vercel.json` contains only `installCommand`, `buildCommand`,
`outputDirectory`, `routes` — no `headers` block — and no page carries a
`Content-Security-Policy` meta tag. For a token-in-localStorage app, CSP is the
main structural defence against XSS and the one thing all of S1/S3 lean on.

**Proposed fix:** add a `headers` entry to the `vercel.json` **generator**
(`scripts/sync-routes.mjs`), not to the generated file, so `npm run build`'s
`--check` keeps passing. A workable starting policy given the app's actual
dependencies:

```
Content-Security-Policy: default-src 'self';
  script-src 'self' https://cdn.onesignal.com;
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;   /* React style attrs */
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data: https://res.cloudinary.com https://media.base44.com https://*.tile.openstreetmap.org;
  connect-src 'self' https://holy-grills-backend.onrender.com https://api.cloudinary.com https://*.onesignal.com;
  frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```

plus `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`
(also helps S2), `Strict-Transport-Security`, and
`X-Frame-Options: DENY` for older browsers. One obstacle: `index.html:78` carries an
inline `<script>` (the dev-only service-worker cleanup snippet), which a strict
`script-src` blocks — it is static text, so a SHA-256 hash is enough, or it can move
into the bundled entry. For that reason the policy should ship as
`Content-Security-Policy-Report-Only` first, be checked in the browser console, then
flipped — a deploy-config change, so it waits for your go-ahead.

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

## S6 — Dependencies declared but never imported (low)

Scan of every import/require/dynamic-import/`@import` in `src/`, `index.html` and
the build configs, cross-checked against the built bundles. These are in
`package.json` and neither imported nor present in `dist/`:

```
@hello-pangea/dnd   @hookform/resolvers   @radix-ui/react-toast
@stripe/react-stripe-js   @stripe/stripe-js   date-fns   html2canvas
jspdf   moment   react-hot-toast   react-markdown   react-quill   zod
```

(`lodash`, `three` also have no direct import; the bundle strings are
`__lodash_hash_undefined__` coming from a transitive dependency and the English
word "three". `tailwindcss-animate` is used from `tailwind.config.js`, so it is
*not* unused.)

Removing these cuts install size, removes `jspdf`→`dompurify`+`fflate`,
`react-quill`→`quill` and `moment` from the audit output entirely, and shrinks the
supply-chain surface. Removal is a lockfile change; `npm run typecheck`,
`npm run build` and `npm run smoke` are the checks that prove nothing depended on
them (the F5 lesson: never trust a grep alone — the build is the authority).

## S7 — `tel:` link from the server not validated (low)

```
src/pages/OrderDetail.tsx:163   if (callLink) { window.location.href = callLink; return; }
src/hooks/useRiderData.ts:135   window.location.href = (link && (link.call_link || link.call_url)) || '';
```

The comment at `OrderDetail.tsx:160` says the link is fetched from
`GET /orders/<id>/call-rider` rather than trusted from the order object — good
instinct, but the fetched value is still assigned unchecked. A `javascript:`
value here would run in the origin. Same proposed fix as S1: allow `tel:` and
`https:` only.

## S8 — CMS link fields handled inconsistently (low)

```
src/components/storefront/PromoFlyerPopup.tsx:58  if (/^https?:\/\//.test(dest)) window.open(dest, '_blank', 'noopener,noreferrer'); else navigate(dest);
src/components/HeroCarousel.tsx:120               else navigate(dest);                    // no guard
src/components/storefront/StorefrontSlider.tsx:98 navigate(dest);                        // no guard
```

react-router normalises absolute URLs to a path rather than leaving the origin,
so this is not an open redirect to another site; the risk is a hostile/broken
CMS value producing odd navigation. The popup's pattern is the right one — make
it the shared helper so all three behave the same.

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
