# Page-load report — before / after

All numbers below are **measured in this workspace** (`npm run build`, Vite 6.4.3,
Node 20), so they are directly comparable. Lighthouse/LCP/TTI numbers are *not*
here: the sandbox's egress is allowlisted to the npm registry, so it cannot reach
either the preview URL or the backend — §"Still to measure" covers those and the
harness to capture them.

## Initial payload (the number that drives first paint)

| Stage | Entry JS | gzip | Entry CSS | gzip | Chunks emitted |
|---|---|---|---|---|---|
| Phase 4 baseline (all-TS, pre-cleanup) | 1,354.96 kB | 374.54 kB | ~129 kB | ~25.4 kB | 8 |
| After 6a dead-code removal | 1,353.81 kB | 373.98 kB | 129.47 kB | 25.37 kB | 9 |
| **After Base44 removal** | **1,222.40 kB** | **330.11 kB** | 129.47 kB | 25.37 kB | 9 |
| **After route splitting + fonts + deps** | **572.95 kB** | **172.24 kB** | **114.19 kB** | **18.68 kB** | **83** |

**Net: 1,354.96 kB → 572.95 kB (−58% raw, 374.54 → 172.24 kB gzip, −54%).**

## What produced each win

| # | Change | Effect | Why it works |
|---|---|---|---|
| 1 | **Deleted the Base44 SDK scaffolding** (`AuthContext`, `ProtectedRoute`, `analytics.ts`, the client, the Vite plugin) | −131 kB raw / −44 kB gzip | Those modules pulled the SDK's HTTP/auth/entity layer into the entry chunk; none of them were reachable (details in `docs/VERIFICATION_REPORT.md` §1) |
| 2 | **Route-level `React.lazy` for 33 of 38 pages** | −649 kB raw / −158 kB gzip | Before, every page — including `/admin`, checkout, marketplace, the map — was imported by `App.tsx`, so the browser downloaded all of them before rendering the landing page. Now the entry chunk is the shell + Home/Login/Register, and each page arrives on first visit. Leaflet (155 kB) only ships when a pin-drop map is shown. |
| 3 | **Fonts: CSS `@import` → `<link rel=stylesheet>`** | Removes a serialised waterfall (HTML → app CSS → Google CSS → font files) | The `@import` inside `src/index.css` could not start until the app CSS had parsed. The `<link>` starts in parallel with it, next to the existing `preconnect`s |
| 4 | **Removed 12 unused dependencies** | Installs ~23 packages lighter; no runtime bytes (they were never imported) | jspdf, html2canvas, react-quill, lodash, three, @stripe/*, moment, date-fns, react-hot-toast, react-markdown, @hello-pangea/dnd |
| 5 | **`loading="lazy" decoding="async"` on list/table/thumbnails** | Fewer bytes+decodes before first paint; hero/LCP images deliberately stay eager | Admin tables, uploader preview, rewards thumbs, order-review images |

## Duplicate / wasted work removed (not bundle size, but time-to-data)

- **Menu** fired `GET /orders/delivery-windows/status` and `GET /menu/kitchen-capacity` on every mount; neither result was ever read. Removed.
- **Cart** fired `GET /rewards/free-side-credits` (and loaded the squad list) for UI that no longer exists. Removed.
- Both removals shorten the on-mount request fan-out, which is what a skeleton is actually waiting on.

## Still to measure (needs your browser — see `docs/PERF_SKELETONS.md`)

| Metric | Tool | Where to record |
|---|---|---|
| LCP / TTI / CLS per route | Lighthouse (mobile + desktop) | paste into this table for before/after |
| Flask p50/p95 per endpoint | `holy-grills-frontend/tools/measure-api-latency.js` | drives the skeleton removal decisions |
| Cold-start penalty | same harness, first call after idle | Render spin-up is 10–30 s; it must not be confused with endpoint cost |

## Suspected remaining bottlenecks (fix only after the measurements above)

1. **Admin chunk is 880 kB** (215 kB gzip) and is now its own lazy chunk — good, but it
   still carries every admin domain in one file. Splitting per admin section would
   cut the first `/admin` visit further; it is deferred until we see how the
   entry/route numbers land in a real browser.
2. **`recharts`** is imported by 6 modules (dashboard/analytics charts) and lands in
   the pages that use it; if a chart-heavy page is slow, the fix is an
   intersection-observer-gated dynamic import of the chart component.
3. **Duplicate on-mount fetches on Home** (kitchen status + storefront sections +
   featured items) — worth deduplicating into one parallel batch if p50 is high.
