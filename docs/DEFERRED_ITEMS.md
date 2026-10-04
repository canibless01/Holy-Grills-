# DEFERRED ITEMS — observed during the TS migration (Phases 4–5)

Logged, **not fixed**. Nothing here blocks the migration; every item is either a
pre-existing frontend/backend mismatch, a cosmetic drift, or tooling that needs a
decision the migration is not allowed to make on its own (no new UI, contract
frozen, no new security work).

## 0. Resolved (Track B session) — kept here for the audit trail

| # | Was | Now |
|---|---|---|
| D3 | `seo.business.logo: '/logo.png'` — no such file in `public/`, so the JSON-LD logo 404'd | points at the real `/icons/icon.svg`; the `seoJsonLd` special-case that papered over it is gone. Social image stays the new 1200×630 `og-cover.jpg` |
| D4 | Relative `/api/*` callers could not be exercised locally (no dev proxy) | `vite.config.ts` proxies `/api` when `VITE_DEV_PROXY_TARGET` is set. Unset = previous behaviour, and dev-only |
| D5 | `eslint.config.js` globs matched **no** files, so `npm run lint` linted nothing | globs are TS/TSX and the parser is `typescript-eslint`. Same rule set as before the migration — coverage restored, no new policy. It immediately found two unused imports in `main.tsx` |
| D6 | `jsconfig.json` pointed at `.js`/`.jsx` globs that no longer exist | deleted; `tsconfig.json` (which has the same `@/*` paths) is the single source of truth |
| D7 | Comments referenced `App.jsx`, `Admin.jsx`, `AdminShared.jsx`, `toast.jsx`, `ImageUploader.jsx` | the seven references now name the real files |
| D1 | *Original note:* "8 call sites of `Pill tone="blue"` silently render cocoa" | **the note was wrong and is corrected below** — see §A |
| E1 | Four components with no static import, possibly reachable through the dynamic storefront registry | confirmed against the renderer (`how_its_made` is rendered by `StorefrontSlider`) and deleted: `storefront/EarlySupporters.tsx`, `storefront/HowItsMade.tsx`, `MenuListCard.tsx`, `Sparkline.tsx` (recoverable from git) |
| E2 | `MarketplacePurchasesPanel` computed `STATUS_TONE` and then ignored it, hardcoding `text-success`/`text-blue-600`/`text-destructive` inline — so `pending` and `refunded` lost their colours | the row renders the computed tone; the map is typed, so a status without a tone fails the build |
| E3 | `Cart.tsx` carried promo/squad state whose setters no longer existed, so both discounts were always 0 and `total === subtotal` | remnant and the dead Checkout-side seeding removed; the navigation contract that still matters (`subtotal`) is kept and documented |
| F6 | `liveApi.challenges.get(id)` called `GET /challenges/<id>`, a route the backend does not serve, with no caller | deleted |
| F7 | "We do not have SSR" | pre-rendering shipped for `/`, `/faq`, `/our-story`, `/terms` — see `docs/TRACK_B_SSR_PLAN.md` |

Second pass (same session, after your answers):

| # | Was | Now |
|---|---|---|
| D1 | two `Pill` components, two tone maps (brand tokens vs Tailwind 100/700), both untyped | **one** `Pill` on brand tokens; `AdminShared` re-exports it so the ~25 admin files are unchanged. Typed against its own keys — `tone="mauve"` is a compile error |
| F1 | `/mcp-consent` called two endpoints no backend route serves (`GET /apps/:id/mcp/consent-info`, `POST /apps/:id/mcp/authorize-grant`) and read the Base44-only `appParams` | **page, route and `lib/app-params.ts` deleted** — the flow could never complete, and the last `VITE_BASE44_*` consumers are gone with it. `vercel.json` regenerated (33 route families). Recoverable from git if you want an MCP consent flow later |
| F2 | `media.base44.com` artwork (flame mark, mascots, offline mascot) | **kept** (your call: artwork is fine where it is; new images go to Cloudinary). The host is now config: `VITE_ASSET_CDN_URL` in `lib/mascots.ts`, so the Cloudinary switch is an env change, not a code change |
| F3 | hardcoded CORS origin list in `app/config.py`, including the retired base44.app | **removed** — origins now come from `CORS_ORIGINS`/`FRONTEND_URL` only. Note `app/__init__.py` sets `origins="*"`, so the list was dead config; pin it before deploy |
| F5 | 8 frontend calls with no Flask route | audited against the backend by hand — see §G. Two were genuinely dead and are deleted; **six are gaps with real UI callers and are reported, not deleted** |
| — | hardcoded environment values in the frontend | moved to env with production fallbacks: `VITE_API_BASE_URL`, `VITE_SITE_URL`, `VITE_ASSET_CDN_URL`, `VITE_ONESIGNAL_APP_ID`; `.env.example` documents all of them plus `VITE_DEV_PROXY_TARGET` |

## G. Backend gaps reported — a route is missing, not the frontend

Your rule: don't add backend handlers; remove frontend code that has nothing
behind it, and report what is genuinely needed. These six have live UI callers and
**no** backend route (verified by reading the blueprint files, not the matrix):

| Frontend call | Caller | Backend reality | Consequence today |
|---|---|---|---|
| `POST /api/orders/:id/resend-tracking` | `pages/OrderDetail.tsx:94` (guest resend button) | `orders.py` has only `/<order_id>/squad-members/<member_id>/resend` | button 404s |
| `POST /api/admin/reviews/:id/promote` | `components/admin/AdminReviews.tsx:67` | `admin.py` has `GET /reviews` only | promote action 404s |
| `GET /api/items/archived` | `components/admin/AdminMenu.tsx:30` (archived view) | `menu.py` filters `is_archived` but never lists archived items | archived tab empty |
| `GET /api/admin/free-credits` | `components/admin/AdminFreeCredits.tsx:25` | free-sides admin is `/free-sides/admin/items` + `POST /free-sides/admin/credits` (no GET list) | credits list empty |
| `GET /api/admin/exclusive-spin/history` | `components/admin/AdminExclusiveSpin.tsx:36` | admin routes are the prize pool, the grant and the fulfilment list | history table empty |
| `GET /api/settings` (public) | `lib/featureConfig.ts:100` | only `/admin/settings` and `/kitchen/settings`; `src/types/config.ts` already documents this gap | storefront system settings always fall back to defaults |

Deleted instead (no caller **and** no route): `rewards.redeemFreeSide` (+ the legacy
`FreeSideRedemptionModal` and its OrderDetail button — you confirmed Checkout sends
`free_side_credit`/`free_side_choice` in the order payload), and
`challenges.get(id)`. Also resolved: the 42 Flask routes with no frontend caller are
**backend surface** — left untouched per "the backend is the source of truth".

Still open from the original list: §D (the six migration-era `any`s) and F4.

## A. Cosmetic drift (needs a decision before touching)

| # | Where | What | Options |
|---|---|---|---|
| D1 | ~~`Pill` with `tone="blue"` — 8 call sites | `PILL_TONES` keys are `cocoa, flame, green, amber, red, outline` — no `blue`, so those pills silently render as cocoa at runtime.~~ | **Corrected in the Track B session.** All eight call sites import `Pill` from `AdminShared.tsx`, whose `TONES` map *does* include `blue` — so nothing rendered as cocoa; the original note conflated two components. There are in fact **two** `Pill` implementations with two different tone maps (see below), and the real defect was that both typed `tone` as `string` while their key sets differed. Both are now typed against their own keys, `AdminKit` gained the missing `blue`, and `AdminShared` gained the `outline` tone that `AdminExclusiveSpin` was already asking for (an unknown key produced an `undefined` class, i.e. an unstyled pill). Enforced: `tone="mauve"` is now a compile error. **Open decision:** the two maps are still separate — `AdminKit` uses brand tokens, `AdminShared` uses Tailwind 100/700 pairs, so the same tone looks different depending on the import. Unifying them is a visual change across ~25 admin files → your call. |

_Checked and cleared: `components/admin/AdminHp.tsx`'s `amount` state is **not** dead — it feeds the
bulk-grant request body (`:49`) and the bulk-grant input (`:111`). No Phase 6a action needed._

## B. Pre-existing asset / environment gaps (not migration regressions)

| # | Where | What | Impact |
|---|---|---|---|
| D3 | `config/app.config.ts` → `seo.business.logo: '/logo.png'` | `public/` contains only `icons/`, `manifest.json`, `offline.html`, `robots.txt`, `service-worker.js`, `sitemap.xml` — there is no `logo.png`, so the Restaurant JSON-LD image 404s (Vite's SPA fallback serves HTML). | Structured-data image only; on-page images all come from backend `image_url` fields and are unaffected. Fix in Phase 6c/6d or by adding the asset. |
| D4 | Relative `/api/*` calls (`lib/webPush.ts`, `pages/OAuthConsent.tsx` MCP consent, base44 analytics) | The dev server has no `/api` proxy: the `@base44/vite-plugin` prints *"No Base44 backend configured — VITE_BASE44_APP_BASE_URL is not set"*. | `liveApi` uses the absolute production URL, so app data flow is fine; only these relative-URL calls cannot be exercised locally. Set `VITE_BASE44_APP_BASE_URL` (or a `server.proxy` entry) when local dev against the real backend is needed. |

## C. Tooling left deliberately untouched

| # | Where | What |
|---|---|---|
| D5 | `eslint.config.js` (files: `src/**/*.{js,mjs,cjs,jsx}`) | After the conversion, those globs match **no** files, so `npm run lint` now lints nothing. Widening them to `ts,tsx` requires a TypeScript parser (`typescript-eslint`) and rule decisions — a dependency + policy change, not part of the rename. |
| D6 | `jsconfig.json` (`include: src/components/**/*.js, src/pages/**/*.jsx, src/Layout.jsx`) | Same staleness; `tsconfig.json` is now the source of truth for the language service. Either delete `jsconfig.json` or repoint its include globs. |
| D7 | Comment references to old filenames (`App.jsx`, `Admin.jsx`, `toast.jsx`, `ImageUploader.jsx`, `AdminShared.jsx`) | Comments were preserved verbatim per the migration rules; the paths they name are now `.tsx`/`.ts`. |

## D. Migration-era `any`s carrying a `// TODO(ts):` marker — **CLOSED 2026-10-04**

All six were retyped against what the code actually reads, which is how the
`/challenges/my` envelope bug and the untyped payment method were found (see
`docs/WIRING_AUDIT.md` §3.4). The section is kept for the audit trail; the
original list was:

- `lib/liveApi.ts` — `unwrap(res: any, …)` (returns the envelope or a bare array)
- `components/TierIcon.tsx` — `tier?: Record<string, any>` (tier payload untyped in liveApi)
- `components/KitchenStatusBox.tsx` — `onStatus?: (status: any) => void`
- `components/SquadMembersPanel.tsx` — `initialMembers?: any[]`
- `pages/Checkout.tsx` — fee-calc `body` and submit `payload` (`Record<string, any>`)
- `pages/Rewards.tsx` — `ChallengesEnvelope` rows (`badges/challenges_*: any[]`)

## E. Phase 6a — dead code found but deliberately NOT deleted

Everything below was verified unreferenced by `tsc --noUnusedLocals --noUnusedParameters`, but is
left in place because removing it is a product decision or needs a cross-page contract check.

| # | Where | Finding | Why it was left |
|---|---|---|---|
| E1 | `components/storefront/EarlySupporters.tsx`, `components/storefront/HowItsMade.tsx`, `components/MenuListCard.tsx`, `components/Sparkline.tsx` | No static import anywhere in `src/`. | The storefront renders sections from a dynamic `section_type` registry (`how_its_made` is a real admin section id — `AdminStorefront.tsx:57`), so "no static import" is not proof of deadness. Confirm against the section renderer before deleting. |
| E2 | `components/marketplace/MarketplacePurchasesPanel.tsx:47` | `const tone = STATUS_TONE[p.status]` is computed but never applied to the row — status colors are lost. | Looked like a real (pre-existing) bug rather than dead code. Kept the line so the intent stays visible; fix belongs to Phase 6b (it is a UI change). |
| E3 | `pages/Cart.tsx` | Inert promo/squad remnant: `promoResult` and `squadEnabled` can no longer be set (their setters died with the removed handlers), so `promoDiscount`/`squadDiscount` are always 0 and `total === subtotal`. `checkoutState` still forwards `promoResult`/`squadEnabled`/`squadId` to Checkout. | Promo handling now lives in Checkout (`Checkout.tsx:187`, `:235`, `:565`), so this is leftover wiring — but it is also the Cart→Checkout navigation contract. Delete it together with a Checkout-side check, not piecemeal. |
| E4 | `pages/Home.tsx:41`, `components/ui/use-toast.tsx:40`, `lib/liveApi.ts:955-956` | Write-only `loading` state (setter used, value never read); `_clearFromRemoveQueue` (canonical shadcn toast internals, underscore-prefixed on purpose); `eventId` params kept in the ticket-tier signatures with an explicit comment that the URL omits them. | Intentional/idiomatic or signature-level, not dead code. |

Unused *parameters* reported by the probe (`ShareSheet` platform builders, `TestimonialSlider`,
`toast.tsx`, `AdminLeaderboard.fulfillReward`) were left alone: they are function signatures, and the
project does not enable `noUnusedParameters`.

## F. Stop-and-ask — decisions needed from you (found by the coverage matrix)

| # | Item | Why it needs a decision |
|---|---|---|
| F1 | **MCP consent endpoints have no Flask route**: `pages/OAuthConsent.tsx` calls `GET /api/apps/:appId/mcp/consent-info` and `POST /api/apps/:appId/mcp/authorize-grant`, and reads `appParams.appId`, `appParams.token`, `appParams.appBaseUrl`. In the Base44 build these were served by the Base44 platform. | Port the two endpoints into Flask (new backend work — needs your go-ahead), or retire the `/mcp-consent` route and page. Until then the page cannot complete a consent flow. |
| F2 | **`media.base44.com` asset CDN** — `components/FlameMark.tsx` (the flame mark), `lib/mascots.ts` (mascot art), `public/offline.html` (offline mascot), `App.tsx` SEO default image path. | These render today and were left alone; if you want Base44 gone from the stack entirely, the images must be re-hosted (repo `public/` or your own CDN) before the URLs are removed. |
| F3 | **Backend CORS origin** `https://holy-grill-copy-copy-copy-cop-f435c07e.base44.app` in `app/config.py:33`. | Backend-side and possibly still in use by a deployed origin; removing it may break a live client. Your call. |
| F4 | **34 Flask routes with no frontend caller** — fresh join against the booted app's `url_map`; full list in `docs/WIRING_AUDIT.md` (appendix). | Not deleted: they may serve webhooks, the mobile client or admin tooling. Biggest clusters: free-sides admin (7, unused by the web app), newsletter campaigns (5), departments/faculty (3). Confirm which are dead before any removal. |
| F5 | **6 frontend calls with no Flask route** — enumerated with impact in `docs/WIRING_AUDIT.md` §1 (each already carries an in-code `// F5 GAP:` note and degrades to an empty state). | Implement the backend route, or remove the frontend call — with one exception that can be fixed frontend-side today: `GET /settings` should be `GET /api/storefront/config/public` (audit §3.2: students currently read built-in defaults for admin-configured public settings). |
| F6 | **`GET /challenges/:id` in `liveApi`** — no caller anywhere in the frontend; the backend never served it. | **Resolved:** the method was deleted during the type pass; `liveApi.ts:1325` records the reason. |
| F7 | **SSR** — you asked whether we already have server-side rendering. | We do **not**: the app is still a client-rendered SPA (empty `<div id="root">` + a JS bundle per route). Pre-rendering is a separate project — see `docs/SSR_EXPLAINER.md` for what it would take and the two viable routes. |

Third pass (post-B6 decisions) — plus the production wiring audit:

| # | Item | Why it needs a decision |
|---|---|---|
| F10 | **Free-side credits were never applied** — the modal promised a ₦0 side, but Checkout sent `free_side_credit`/`free_side_choice`, which **no backend code reads**; consumption requires a `cart_free_side_selections` row written by `POST /free-sides/select`, which the frontend never called. Evidence: `docs/WIRING_AUDIT.md` §3.1. | **Resolved:** the modal now lists the backend's curated `available_sides` by id and Checkout selects/deselects through the documented endpoints; the two unread body fields are removed. Fails loudly instead of promising a side that is not delivered. |
| F11 | **`GET /settings` (P2)** — `featureConfig.ts` read public settings from a route that does not exist, fell back to an admin-only route and then to built-in defaults, so **students never saw admin-configured public settings**. | **Resolved:** reads `GET /api/storefront/config/public` (flat key→value map); the dead `config.getPublic()` method is removed and `types/config.ts` updated. |


> **Phase 7 security review is in `docs/SECURITY_REVIEW.md`** (authorised this
> session): 10 findings, none applied yet — payment-redirect validation, the
> reset-token URL, CSP/security headers, 13 unused runtime dependencies, and the
> react-router 7 upgrade decision. Every finding carries file:line evidence and a
> proposed patch.

| # | Was | Now |
|---|---|---|
| F8 | `Config.CORS_ORIGINS` was composed from env **plus a hardcoded origin list** that still named the retired `base44.app` host. It was dead config either way: `app/__init__.py` registers `CORS(app, origins="*")` | hardcoded list removed — origins are env-only now (`CORS_ORIGINS` / `ALLOWED_ORIGINS` / `FRONTEND_URL`), with a comment saying the list is not enforced until the app stops passing `origins="*"`. `holy-grills-backend/ENV_CONFIGURATION.md` and `README.md` updated to match: CORS stays `*` until deployment, then set the two variables **and** switch `CORS(...)` to the configured list |
| F9 | React 18.3.1's stream encoder writes a full 2 KB view (zero padding included) whenever a multi-byte character does not fit the remaining space, so `/menu`'s pre-render contained two NUL bytes in place of ❤️‍🔥 | repaired in `src/entry-server.tsx` (trailing-NUL trim + a build-time assertion), guarded by a per-route "no NUL bytes" smoke check |
| F10 | §6 item 1: `/menu`, `/events`, `/marketplace` were in `sitemap.xml` but pre-rendered nothing indexable | the campus picker (real `<h1>`, intro, campus list, bullets) is now pre-rendered for those three routes; `PRERENDER_ROUTES` is 7. See `docs/TRACK_B_SSR_PLAN.md`, post-B6 round |
