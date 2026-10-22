# SSR / pre-rendering — where the app stands and what it would take

## Short answer

**No — the app is not server-side rendered today.** It is a classic Vite SPA:
`index.html` ships an empty `<div id="root">`, one JS entry chunk, and React
builds the entire DOM in the browser. Every route (`/menu`, `/rewards`, …) is the
same HTML file; the difference comes from client-side routing. A crawler that
does not execute JavaScript sees an empty page plus whatever static tags
`index.html` already carries (title, meta, JSON-LD — those exist and help).

What the phases so far *did* deliver:

| Goal | Status |
|---|---|
| SEO prerequisites that are static | ✅ (meta, OG, Twitter card, Restaurant JSON-LD in `index.html`, `sitemap.xml`, `robots.txt`) |
| Smaller/faster client payload (helps Core Web Vitals, a ranking input) | ✅ entry JS −58% (1,355 kB → 573 kB; gzip 375 → 172 kB) |
| Route-level code splitting (prerequisite for either pre-render strategy) | ✅ 33 of 38 pages lazy |
| Actual server-rendered HTML per route | ❌ not started |

## The two viable routes to real SSR

### Option A — pre-render to static HTML at build time (recommended first step)

Render each public route to HTML during `npm run build` and ship those files, so
crawlers and slow connections get real content immediately, while React
"hydrates" on top.

- Tooling: `vite-plugin-ssr`/`vike`, or `react-snap`/`vite-plugin-prerender` for a
  lighter touch.
- Works with the current router and components **only if** components are
  hydration-safe: every page must render without `window`/`localStorage` access
  at import time. Today several do touch `localStorage` at module scope
  (`lib/app-params.ts`, `lib/apiClient.ts` storage helpers), and `AuthProvider`
  style bootstrap reads storage on mount — those need guards.
- Needs a crawl-free route list (we have one: the 38 routes in `src/App.tsx`).
- Backend stays exactly as it is; data still arrives client-side after hydration
  (so the pre-render carries layout + static text, not live menu prices).
- Cost: ~1–2 focused days, no backend change, no auth risk.

### Option B — render on the Flask server (full SSR/SSR+data)

Serve HTML from Flask with the initial data already inlined, then hydrate.

- Requires either a Node renderer alongside Flask (Next/Remix-style) or a
  Node side-car that Flask calls — the React code cannot run inside Python.
- Every component must be universal-safe, and the app must switch from
  `localStorage` tokens to cookies so the server can render an authenticated view
  (this is the part that touches auth, which the migration froze).
- Gives live SEO content (menu, events, marketplace) and the biggest LCP win.
- Cost: a real project (weeks), and it re-opens the auth model — a decision for
  you, not a migration step.

## Recommended sequence

1. Do **Option A** for the public, indexable routes only: `/`, `/menu`, `/faq`,
   `/our-story`, `/terms`, `/events`, `/marketplace`, `/leaderboard`. Private
   screens (`/dashboard`, `/admin`, …) gain nothing from pre-rendering.
2. Verify with `curl` (HTML must contain the page's text) and Lighthouse SEO.
3. Only if live-data SEO becomes a business requirement, plan **Option B** as its
   own phase, starting with the cookie-based auth decision.

## What is blocked on you

- Whether SEO content needs to include *live* data (menu/prices) or static copy is
  enough — that choice decides A vs B.
- If B: approval to change the token storage model (cookies + CSRF), because the
  frozen rule was "auth must never break".
