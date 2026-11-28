# Track B — SSR / pre-rendering plan (B0)

## 1. Stack facts that constrain the decision

| Fact | Value | Consequence |
|---|---|---|
| Routing | `react-router-dom` v6, one `Routes` tree in `src/App.tsx` (40 route entries) | Any tool with its **own** router convention means rewriting the app's routing |
| Auth | **localStorage / sessionStorage tokens** (`hg_access_token`, `hg_refresh_token`), JWT in an `Authorization` header | The server cannot know who the user is → authed routes must stay CSR-only. Switching to cookies is a **stop condition** (auth-model change) |
| Data | every screen fetches from the Flask API in `useEffect` | `renderToString` does not run effects → a server render produces the **static shell + static copy**, never live data (no risk of stale/fake prices in HTML) |
| Deploy | Vercel, static output `dist/`, SPA catch-all rewrite in `vercel.json` | A **static pre-render** needs no new process and no infra change: Vercel serves a real file when one exists and falls back to the SPA rewrite otherwise |
| Backend | Flask JSON API on its own origin (absolute base URL) | Nothing to proxy; no CORS change is required because the pre-render makes **zero** API calls |

## 2. Route inventory (40 entries) and recommended mode

Classes: **A** = public + SEO-critical · **B** = public non-SEO · **C** = authed app.

| Route | Component | Class | Recommended mode | Why |
|---|---|---|---|---|
| `/` | Home | A | **Pre-render** | Landing page; static hero/copy renders without data |
| `/faq` | FAQ | A | **Pre-render** | Fully static content, no data needed |
| `/our-story` | OurStory | A | **Pre-render** | Marketing copy, static |
| `/terms` | TermsPrivacy | A | **Pre-render** | Legal text, static |
| `/menu` | Menu | A (blocked) | **CSR for now** | Inside `CampusScope`: a guest with no campus gets a skeleton/gate, so pre-rendering would bake a skeleton into the HTML. Needs a product decision (see §6) |
| `/menu/:id` | ItemDetail | A (blocked) | CSR | Same gate + data-driven per item |
| `/events` | Events | A (blocked) | CSR | Same gate |
| `/events/:id` | EventDetail | A (blocked) | CSR | Same gate + data-driven |
| `/events/tiers/:tierId` | TierDetail | A (blocked) | CSR | Same |
| `/marketplace` | Marketplace | A (blocked) | CSR | Same gate |
| `/marketplace/:id` | MarketplaceDetail | A (blocked) | CSR | Same |
| `/leaderboard` | Leaderboard | A (blocked) | CSR | Same gate + live ranking data |
| `/login` | Login | B | CSR | Interactive form, no SEO value |
| `/register` | Register | B | CSR | Interactive form |
| `/forgot-password` | ForgotPassword | B | CSR | Interactive form |
| `/reset-password` | ResetPassword | B | CSR | Token in URL, must not be cached/pre-rendered |
| `/mcp-consent` | OAuthConsent | B | CSR | Opaque client handle; endpoints have no Flask route (logged separately) |
| `/cart` | Cart | B/C | CSR | Per-user state (guest cart in localStorage) |
| `/checkout` | Checkout | C | CSR | Auth + payment |
| `/order-confirmation/:id` | OrderConfirmation | C | CSR | Per-order |
| `/orders` | Orders | C | CSR | Per-user |
| `/orders/:id` | OrderDetail | C | CSR | Per-user |
| `/track-orders` | TrackOrders | C | CSR | Per-user |
| `/dashboard` | Dashboard | C | CSR | Per-user |
| `/hp-education` | HpEducation | C | CSR | Per-user balance |
| `/rewards` | Rewards | C | CSR | Per-user |
| `/wallet` | Wallet | C | CSR | Per-user money data |
| `/profile` | Profile | C | CSR | Per-user |
| `/addresses` | Addresses | C | CSR | Per-user |
| `/notification-preferences` | NotificationPreferences | C | CSR | Per-user |
| `/notifications` | Notifications | C | CSR | Per-user |
| `/referrals` | Referrals | C | CSR | Per-user |
| `/order-locks` | OrderLocks | C | CSR | Per-user |
| `/squads` | Squads | C | CSR | Per-user |
| `/streak` | Streak | C | CSR | Per-user |
| `/hall-of-fame` | HallOfFame | C | CSR | Per-user view of public data (CSR keeps it simple) |
| `/admin` | Admin | C | CSR | Role-gated |
| `/kitchen` | Kitchen | C | CSR | Role-gated |
| `/rider` | Rider | C | CSR | Role-gated |
| `*` | PageNotFound | B | CSR | 404 handling stays client-side (see §6) |

**Pre-render set for B1–B2: `/`, `/faq`, `/our-story`, `/terms`.** Everything else keeps today's behaviour byte-for-byte.

## 3. Tool choice — custom `entry-server` + `entry-client` + a prerender script

Chosen: **hand-rolled SSG on Vite's built-in SSR build** (`vite build --ssr`), using `react-dom/server.renderToString` + `react-router-dom`'s `StaticRouter`, then a small Node script that writes one real HTML file per route.

| Option | Verdict |
|---|---|
| **Vike** | Rejected. Vike brings its own filesystem router; adopting it replaces the `react-router-dom` tree, every `<Link>`, and the route-guard layout structure — a full-app restructure against "preserve file names and structure", with the auth flow (the thing that must not break) sitting inside the blast radius |
| **vite-plugin-ssg / vite-react-ssg** | Rejected for the same reason: they own route declaration and expect the route table in their config; our guard chain (`Layout → CampusScope → RequireAuth`) and 40 `element={}` routes would have to be re-expressed |
| **Next.js** | Explicitly out of scope ("only if you say so") |
| **Custom entry points** | **Chosen.** Adds **zero** runtime dependencies (`react-dom/server` and `react-router-dom/server` are already installed), keeps `App.tsx`'s route tree as the single source of truth, and produces plain static files that today's Vercel config already serves |

Implementation shape:

```
src/entry-server.tsx     render(url) -> renderToString(<StaticRouter><Providers><AppRoutes/></Providers>)
src/main.tsx             hydrateRoot when the container has server HTML, else createRoot (dev/CSR)
src/seo/routeMeta.ts     per-route head metadata (title/description/canonical/OG + JSON-LD), shared
scripts/prerender.mjs    imports the SSR bundle, writes dist/<route>/index.html with head injected
```

`npm run build` becomes: client build → SSR build → prerender (the existing `vite build` result is still the fallback SPA shell).

## 4. Flask's role — Option 3: static pre-render, no runtime change

- No Node SSR server in production, no reverse proxy, no Flask HTML route.
- Flask remains exactly what it is today: a JSON API. **No route, request shape or response shape changes.**
- Because the pre-render executes no effects, it makes **no API calls** — so there is nothing to CORS-enable for the build, and no server-side data to cache.
- Vercel serves `dist/faq/index.html` when a static file matches and falls back to `dist/index.html` (the SPA) for everything else — i.e. the current `rewrites` entry keeps working untouched.

## 5. Auth note (frozen)

Tokens stay in `localStorage`/`sessionStorage`; **no cookie migration** (stop condition #3).
For pre-rendered routes the server render runs with an empty storage shim, so the HTML contains no user data, and the shell's auth-dependent UI is deferred one tick so the hydrate pass matches the server markup exactly (details in the B1 report).

## 6. Items I am *not* deciding for you (would be guessing at intent)

1. **Campus-scoped SEO routes** (`/menu`, `/events`, `/marketplace`, `/leaderboard`): they currently show guests a campus gate/skeleton, so pre-rendering them means pre-rendering a gate. Options: (a) let crawlers see a default campus, (b) render a crawler-friendly campus-picker page with real copy, (c) leave them CSR and accept they are not indexable. Each changes guest behaviour → your call. `robots.txt`/`sitemap.xml` currently advertise some of these, which is what makes it SEO-relevant.
2. **Real 404 status codes** (B5): a static host serving the SPA returns HTTP 200 for unknown paths. Returning a true 404 needs a hosting-level rule (e.g. Vercel `404.html` or a rewrite) rather than an app change → confirm before I touch deploy config.
3. **Live-data SEO** (menu prices, events in HTML): that requires server-side data fetching, which means either a Node SSR runtime or Flask rendering — a bigger project than static pre-render, and it would need the auth/data path re-thought. Flagged, not started.

---

# B1/B2 implementation log

## What actually shipped (differs from §4 in one place)

| Plan line | Reality |
|---|---|
| SPA fallback stays `dist/index.html` | **Changed.** `dist/index.html` is now the pre-rendered home page, so the fallback moved to a new `dist/app-shell.html` (`vercel.json` rewrite updated). Serving home's markup (and home's title/canonical) for `/menu`, `/login`, `/admin`… would have been wrong on every CSR route, and `main.tsx` would have tried to hydrate home's HTML as `/menu`. |
| `renderToString` | **Changed to `renderToPipeableStream` + `onAllReady`.** Every page is `React.lazy`-loaded; `renderToString` cannot wait for Suspense, so it emitted the page's loading fallback (≈2.2 kB) instead of the page. |
| `AppProviders` / `AppShell` split | **Kept, with one correction:** `CampusProvider` calls `useLocation()`, so it belongs *inside* the router. `AppProviders` = ErrorBoundary + QueryClient + (post-hydration) Toaster; `AppShell` = Sound → HolyGrill → Campus → routes, with the two popups behind `ClientOnly`. |

## Hydration safety

`scripts/prerender.mjs` stamps `<div id="root" data-prerendered-route="/faq">`. `src/main.tsx`
hydrates only when that stamp equals the URL being hydrated (`src/lib/hydrationMode.ts`); any
mismatch clears the container and mounts fresh — the pre-pre-render behaviour.

The pre-render runs with an empty storage shim, so its HTML is always the signed-out,
no-campus view. Three storage reads happened during the *first* render and would have
mismatched for a signed-in visitor hydrating a pre-rendered page:

| Where | Before | Now |
|---|---|---|
| `HolyGrillContext` `authed` | `useState(isAuthenticated())` (reads token) | guest default while hydrating; the existing session effect adopts the real token right after mount |
| `campusContext` `guestCampusId` / `adminCampusId` | `useState(getStoredCampusId())` | null while hydrating, adopted in a mount effect (still earlier than the campus-list fetch the gate waits on) |
| `app-params.ts` | `defaultValue: window.location.href` evaluated on import (throws on a server import) | `isNode ? '' : window.location.href` |

Everything else that touches storage on a pre-rendered route does so in an effect
(`PromoFlyerPopup`, `KitchenClosePopup`, `InstallPrompt`/`CookieConsent` via `ClientOnly`).

## Verification (all run)

| Check | Result |
|---|---|
| `tsc --noEmit` | clean |
| `npm run build` | client 11.3s → SSR 2.9s → prerender ~1.7s, **zero React warnings** |
| `curl` per route (static host simulator, `scripts/serve-static.mjs`) | `/` 29 046 B, `/faq` 48 830 B, `/our-story` 30 651 B, `/terms` 33 361 B of real markup inside `#root`; correct `<title>`, canonical, OG and Twitter tags per route; images present in the raw HTML |
| CSR routes (`/menu`, `/login`, `/admin`, `/events`) | empty `app-shell.html` (0 bytes in `#root`), client mounts as before |
| Assets | entry JS 573 546 B, CSS 114 185 B — unchanged from the perf baseline |
| Determinism | two consecutive pre-renders produce byte-identical files (no `Date.now`/random in any render path) |
| SPA `<title>` parity | `headFor()` composes exactly what `useSEO` writes at runtime; `FAQ`/`TermsPrivacy` gained the `<SEO>` call they never had, `OurStory` now reads the same object |
| Service worker | navigations are network-first, so a new deploy is never shadowed by the cached HTML |

Not verifiable in this sandbox: the browser console (no headless browser here). The hydration
gate, the storage deferrals and the single shared tree make a mismatch structurally
impossible on these four routes, but the empirical pass is yours — the preview on 4174 is the
closest thing to production.

## Open items for later phases

1. **`og:image` is relative and SVG** (`/icons/icon.svg`): crawlers need an absolute URL and most
   social platforms do not render SVG. Needs a 1200×630 raster in `public/` (B5).
2. **Unknown paths answer 200** with the app shell (soft 404) — B5, and §6 item 2 stays open.
3. **`/our-story` title is 78 chars** because the SPA appends `| Holy Grills` to the page title.
   Shortening it changes live copy → your call (B5).
4. **Pre-rendering a menu-derived route** additionally needs `liveApi`'s raw `localStorage` reads
   (`downloadTicketPdf`, `auth.refresh`) behind the storage shim. They only run on user action
   today, which is why these four routes are safe.
5. §6 items 1 and 3 (campus-gated SEO routes, live-data SEO) are unchanged and still yours.

---

# B5–B7 implementation log

## B5 — SEO hardening

| Item | Before | After |
|---|---|---|
| `og:image` / `twitter:image` | `/icons/icon.svg` — **relative**, and social platforms do not render SVG | `https://holygrill.app/og-cover.jpg` — new 1200×630 JPEG (140 kB) generated for this purpose into `public/`, wired through `APP_CONFIG.seo.defaultImage` so `useSEO` and the pre-render agree |
| JSON-LD `logo` / `image` | `/logo.png` (a file that does not exist in `public/`) and an SVG | the same real cover, absolute |
| `<title>` / description / canonical / OG / Twitter | template defaults on every route | per-route values on all four pre-rendered routes, identical to what `useSEO` writes after hydration (`FAQ` and `TermsPrivacy` had **no** `<SEO>` call at all before this) |
| `robots.txt` | 9 disallowed prefixes, sitemap advertised | unchanged — still correct (all four now-indexable routes are `Allow`) |
| **Unknown paths** | **HTTP 200** with a soft-404 body | **HTTP 404** with `noindex`, verified locally and mirrored 1:1 in `vercel.json` |
| `html lang` / charset / viewport | already correct | unchanged |

The 404 work is the one that needs care: a static host answers 200 for every path, and the
modern `rewrites` dialect **cannot** set a status code (confirmed: Vercel community discussion
#9567; only the legacy `routes` dialect supports `status`). So:

- `scripts/routes.mjs` is the single definition of "a route family the SPA owns", derived from
  `src/App.tsx` (40 `<Route path>` entries → 34 families covering every nested path: `/events`
  also covers `/events/:id` and `/events/tiers/:tierId`).
- `scripts/sync-routes.mjs --write` regenerates `vercel.json`; `--check` (run first in
  `npm run build`) **fails the build** if App.tsx has a route the config does not know, so a new
  page can never silently 404 in production.
- `vercel.json` route order: `handle: filesystem` → one rewrite per route family →
  `{"src": "/(.*)", "status": 404, "dest": "/404.html"}`.
- `scripts/serve-static.mjs` now runs that same config, so local checks and the host cannot drift.

## B6 — build & deploy pipeline

```
npm run build
  routes:check      vercel.json matches App.tsx
  build:client      vite build                       -> dist/
  build:ssr         vite build --ssr src/entry-server -> dist-ssr/
  prerender         dist/{index.html,faq,our-story,terms,app-shell.html,404.html}
```

- `.github/workflows/frontend.yml` runs typecheck → lint → build → serve → smoke on every push
  to `main` and every PR touching the frontend.
- `npm run smoke` (`scripts/smoke.mjs`) asserts, per route: HTTP 200, >5 kB of rendered markup,
  a route-specific `<title>`, the exact canonical, an absolute `og:image`, parseable JSON-LD with
  the right `@type`; then that all 39 declared app routes answer 200, that 3 unknown paths answer
  **404 + noindex**, that `app-shell.html` has an empty `#root` and no pre-render stamp, and that
  every asset the HTML references resolves.
- Backend: untouched. `git diff --name-only` over the entire Track B range shows **0 backend files**.
- Smoke tests need the built output and a server, so they run after the build (they cannot be a
  `postbuild` hook that also runs in a bare `npm ci`).

## B7 — runtime verification (what I can prove here vs. what needs your browser)

| Check | Result |
|---|---|
| View-source real HTML | ✅ 29 051 / 15 664 / 15 371 / 15 423 / 48 832 / 30 657 / 33 363 bytes of markup in `#root` for the seven pre-rendered routes (the three campus pickers included) |
| No user data for unauth requests | ✅ all 39 non-pre-rendered routes (incl. `/admin`, `/dashboard`, `/checkout`, `/kitchen`, `/rider`) serve an **empty** shell; zero token/email/`Bearer` strings in any served HTML |
| Images in raw HTML and after hydration | ✅ images present in the prerendered markup (lazy-loaded ones hydrate client-side) |
| CSS/JS load post-hydration | ✅ entry JS `573 981 B` raw / `172 326 B` gzip, CSS `114 185 B` / `18 587 B` gzip |
| Bundle size before/after | perf baseline 572.95 kB → **573.98 kB raw (+1.03 kB, +0.18%)**; gzip 172.24 → 172.33 kB. CSS unchanged. Zero new runtime dependencies. |
| Route coverage | ✅ 39/39 routes 200, 0 accidental 404s; 3/3 unknown paths 404 |
| Determinism | ✅ two consecutive builds byte-identical |
| Hydration mismatches | ✅ **verified 2026-10-04 with a jsdom harness** — the shipped pre-renders hydrate with zero React mismatch warnings on all 7 routes, signed out and with a seeded signed-in session. A real-browser console pass is still recommended (see below) |
| Lighthouse Performance/SEO before-after | ⏳ needs a real browser (deferred to B7 completion on your side) |

### Deferred — needs your browser, or your call

1. **Hydration console pass** — partially covered on 2026-10-04. No browser exists in this
   sandbox (no Chromium or its shared libraries, no apt, and the Playwright/Chrome-for-Testing
   CDNs are blocked), so the check was reproduced with **jsdom**: each *shipped* pre-render is
   loaded, jsdom installed as the DOM, the real app bundle hydrated into `#root`, and React's
   console output read. Result: **14/14 clean** — 7 routes × signed-out and signed-in
   (`hg_access_token`, `hg_campus_id`, `hg_user`, `hg_remember` seeded before hydration), no
   "Hydration failed" / "did not match" messages, no wiped container. That is the empirical
   proof that the storage-deferral design (`isHydratingPrerender()`) holds even when a session
   is present at first paint, which is exactly the case the pre-render cannot see.
   **Still worth a real browser:** jsdom cannot prove anything about paint, layout, real
   network timing, or engine-specific behaviour — and it needed stubs for `matchMedia`,
   `Element.scrollTo`, canvas and the observers. Re-run this in a browser when one is
   available; the harness is a supplement, not a replacement.

   *Harness (kept out of the repo so no test dependency is added): it transpiles an entry that
   calls `hydrateRoot` and runs it in jsdom with the built `dist/` HTML. Reproduce with the
   commands in the session log; ask and I will bring it into `scripts/` behind a devDependency.*
2. **Lighthouse before/after** on `/` and `/faq` (Performance + SEO).
3. **Images have no `width`/`height`** in the server HTML (7 on `/`): a CLS risk independent of
   this workstream. Fixing it means touching hero/mascot markup, so I left it alone.

### Already open (unchanged)

§6 items 1 (campus-gated SEO routes), 2 (now implemented — but see below) and 3 (live-data SEO),
plus the `/our-story` 78-char title and the `liveApi` raw-storage reads that any future
menu-derived pre-render would need. **§6 item 2 is done**: I implemented the 404 outside the app
(next static file + host rule), not as an in-app change, which is what the item asked to confirm.
If you would rather not switch `vercel.json` to the legacy `routes` dialect, say so and I will
revert to the previous `rewrites` (and lose real 404 statuses).

---

# Question: do admin-CMS image changes affect the pre-render?

Short answer: **no, and they never reach the raw HTML — by design.**

`Home` renders images from three places, and all three are runtime fetches:

| Source | Where | What the pre-render emits |
|---|---|---|
| `HeroCarousel.tsx` | `DEFAULT_SLIDES` (3 hardcoded Unsplash URLs) as `useState` initial value, replaced by `liveApi.storefront.getBanners({ placement: 'hero' })` / `getSections('hero')` in an effect | the `DEFAULT_SLIDES` URLs |
| `getStorefrontSections(...)` consumers (`StorefrontSlider`, `EarlySupportersSlider`, testimonial slider, catering card) | `liveApi.storefront.getSections` in effects | nothing (no data) or the component's own fallback |
| `FeaturedItems` / menu-derived cards | `liveApi` in effects | nothing |

The build runs **zero** API calls (`docs/TRACK_B_SSR_PLAN.md` §4), so a CMS change
cannot alter the pre-rendered markup, cannot fail the build, and cannot leak
CMS draft content into a static file. Consequences worth knowing:

1. **Crawlers see the fallback art**, not the published hero. This is a
   pre-existing property of a client-rendered SPA; pre-rendering does not change it.
2. **A visitor may briefly see the fallback** and then the CMS image, because the
   pre-rendered fallback paints before hydration and the fetch resolves after. Before
   pre-rendering, the same swap happened one paint later — the pre-render makes the
   fallback visible *earlier*, which is a small improvement, not a regression.
3. **No hydration mismatch**, because the first client render uses the same three
   defaults the server used; the CMS data arrives as a normal state update afterwards.

### If you want CMS images *in* the HTML

Two options, neither of which is free:

- **Build-time fetch** (smallest change): `scripts/prerender.mjs` fetches the public
  `storefront/banners?placement=hero` endpoint and injects those URLs into the
  `HeroCarousel` server render, with the known caveat that the build then depends on
  the live backend and needs a rerun (or a publish webhook) after every CMS change.
  Requires an env flag and a hard fallback to `DEFAULT_SLIDES` when the API is down.
- **A real SSR runtime** (bigger): render per request so CMS content, prices and
  availability are always current. That is the "live-data SEO" item in §6 and it needs
  a Node process — the static pre-render was chosen specifically to avoid one.

Say which and I will scope it; nothing is implemented for either today.


---

# Post-B6 round — campus picker pre-rendered (§6 item 1), plus an encoder repair

## §6 item 1 is implemented for `/menu`, `/events`, `/marketplace`

The decision was "pre-render a campus picker page: real copy + campus list in the
HTML for crawlers; the app still shows its gate to visitors". What shipped:

| Piece | File | What it does |
|---|---|---|
| Picker view | `src/components/CampusPickerLanding.tsx` (new) | eyebrow, `<h1>`, intro, campus list, "What's waiting" bullets. Reads `useCampus()` and falls back to `APP_CONFIG.university` (`FUTA`), so it renders **identically** at build time and on the first client paint |
| Copy + wiring | `src/components/CampusScope.tsx` | `LANDING_BY_PATH` holds the copy for `/menu`, `/events`, `/marketplace`, `/leaderboard`; the landing renders whenever there is no campus *and* the campus list has not resolved |
| Head data | `src/seo/routeMeta.ts` | `/menu`, `/events`, `/marketplace` added to `ROUTE_META` / `PRERENDER_ROUTES`; the set went from 4 to **7** routes |
| Runtime head | `src/pages/Events.tsx`, `src/pages/Marketplace.tsx` | `<SEO>` added (they had none) so the client-rendered head matches the pre-rendered head |

### The ordering question the build had to answer

`CampusScope` returns `<Outlet />` (the real page) when the campus list resolves
*empty* — the deliberate single-campus pass-through. If that branch also fired at
build time, the pre-render would have written the real page shell and the whole
change would have been for nothing. It does not: `campusContext` starts with
`campusesLoading = true` and effects never run during a render, so the build-time
state is "still loading" → the picker branch wins. Confirmed in the emitted HTML,
not just in the source:

```
/menu        h1 "Today's menu at FUTA"        + campus row + 3 bullets
/events      h1 "Campus events at FUTA"       + campus row + 3 bullets
/marketplace h1 "The campus marketplace"      + campus row + 3 bullets
```

The same state (`campusesLoading = true`) is the client's first render, so
hydration sees identical markup; the campus list then resolves, the gate opens
**on top of** the picker (unchanged behaviour), and a campus-less visitor still
falls through to the real page exactly as before.

`/leaderboard` gets the picker at runtime but is **not** pre-rendered — it is not
in `sitemap.xml`, so there was nothing to fix there.

Pre-rendered byte sizes after this round: `/` 29 051 · `/menu` 15 664 ·
`/events` 15 371 · `/marketplace` 15 423 · `/faq` 48 832 · `/our-story` 30 657 ·
`/terms` 33 363, plus app-shell and 404.

## React 18.3.1 bug found and repaired: NUL bytes in streamed HTML

While checking the new `/menu` output I found **two `0x00` bytes** where the
homepage strapline's ❤️‍🔥 should be (`Made With More Than Flame\0\0🔥`). It is
not our code — it is React 18.3.1's stream encoder:

```js
// react-dom/cjs/react-dom-server.node.development.js, writeStringChunk()
const { read, written } = textEncoder.encodeInto(stringChunk, target);
writtenBytes += written;
if (read < stringChunk.length) {
  writeToDestination(destination, currentView);   // ← the WHOLE 2 KB view
  currentView = new Uint8Array(VIEW_SIZE);
  ...
}
```

When a multi-byte character does not fit in what is left of the 2 048-byte view,
`encodeInto` stops before it — and React writes the entire view anyway instead of
`subarray(0, writtenBytes)`, so the unused tail goes out as zero padding (the
character itself lands in the next view). It reproduces in isolation: a 500-block
stress render loses 4 of 500 emoji to NUL bytes. Which routes are hit depends on
where the boundaries fall, so this was **latent for the original four pre-renders
too** — `/` and `/faq` happened to be unaffected.

Fix, in `src/entry-server.tsx`: the sink buffers chunks and trims trailing NUL
bytes (verified against the stress render that the padding is always a *suffix*,
never interior), then asserts the finished document contains no `U+0000` at all,
so a future regression fails the build instead of shipping. `scripts/smoke.mjs`
now asserts "no NUL bytes" on every pre-rendered route, and asserts the picker
copy is really in the three campus-gated responses.

`/menu` went 15 666 → 15 664 bytes (exactly the two trimmed bytes) and the emoji
is intact in both the file and the served response.

## Verification for this round

| Check | Result |
|---|---|
| `npm run typecheck` / `npm run lint` | ✅ clean |
| `npm run build` | ✅ route families in sync (33), **7** pre-renders + app-shell + 404 |
| `npm run smoke -- http://localhost:4173` | ✅ PASS, including the new NUL and picker assertions |
| NUL scan | ✅ 10/10 emitted HTML files contain no `0x00` |
| Picker copy in the served HTML | ✅ `/menu`, `/events`, `/marketplace` — h1, campus name and all three bullets |

Still open in §6: item 1 for live data (prices/availability in the HTML, which
needs a Node SSR runtime) and item 3. The browser-only B7 checks (hydration
console pass, Lighthouse) are unchanged.
