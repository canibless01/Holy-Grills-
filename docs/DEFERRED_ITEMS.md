# DEFERRED ITEMS — observed during the TS migration (Phases 4–5)

Logged, **not fixed**. Nothing here blocks the migration; every item is either a
pre-existing frontend/backend mismatch, a cosmetic drift, or tooling that needs a
decision the migration is not allowed to make on its own (no new UI, contract
frozen, no new security work).

## A. Cosmetic drift (needs a decision before touching)

| # | Where | What | Options |
|---|---|---|---|
| D1 | `Pill` with `tone="blue"` — 8 call sites (verified) | `PILL_TONES` keys are `cocoa, flame, green, amber, red, outline` — no `blue`, so those pills silently render as cocoa at runtime. The prop is typed `string`, so tsc cannot see it. | (a) alias `blue` → an existing tone, or (b) add a real blue tone. Any choice changes appearance, so it waits for you. |

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

## D. Migration-era `any`s carrying a `// TODO(ts):` marker

Each was introduced because the source value is genuinely untyped today
(untyped `liveApi` returns, index-signature `unknown` from shared contract types,
or dynamic request-body bags). They are the follow-up list for tightening types
in Phase 6, not silent escapes:

- `lib/liveApi.ts` — `unwrap(res: any, …)` (returns the envelope or a bare array)
- `components/TierIcon.tsx` — `tier?: Record<string, any>` (tier payload untyped in liveApi)
- `components/KitchenStatusBox.tsx` — `onStatus?: (status: any) => void`
- `components/SquadMembersPanel.tsx` — `initialMembers?: any[]`
- `pages/Checkout.tsx` — fee-calc `body` and submit `payload` (`Record<string, any>`)
- `pages/Rewards.tsx` — `ChallengesEnvelope` rows (`badges/challenges_*: any[]`)
