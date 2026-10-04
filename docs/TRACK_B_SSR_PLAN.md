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
