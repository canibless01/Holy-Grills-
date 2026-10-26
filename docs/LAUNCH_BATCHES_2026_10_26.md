# Small launch batches — 26 October 2026

User confirms actual storefront Cloudinary uploads now work, including story/menu/icon content. Upload transport is no longer an open defect on that evidence. Remaining storefront work concerns content routing/presentation, not replacing the image provider. Events and marketplace are deferred for launch; prioritize existing order, reward, promo and notification flows. Cleanup remains paused.

## Batch 1 — installation recovery

The root installation component now imports the shared prompt store eagerly. All install buttons consume one browser prompt, with synchronous claiming to prevent double use. A legacy permanent dismissal no longer hides installation forever; new dismissals expire after seven days. Profile has a permanent manual install action that overrides banner dismissal and opens browser-specific instructions if no native event is available. Successful installation clears stale prompts and closes the UI; prompt rejection has a usable fallback.

Checks: TypeScript, changed-file ESLint and complete production build passed. Shared install-store tests pass for early capture, concurrent consumers, errors, new events and installed invalidation. Five controlled native browser cases pass for legacy dismissal, one native prompt, Profile instructions, manual recovery after dismissal and appinstalled closure. Existing OneSignal v16 tests pass. These browser tests use controlled events/API and perform no external writes.

Run from frontend: `node scripts/test-install-prompt.mjs`; `python scripts/test-install-browser.py` (Python Playwright + Chromium).

## Batch 2 — ordering streak visibility

The dashboard incorrectly read login `consecutive_weeks` as order consistency, while `/auth/streak` returned no order summary. The response now includes a separate `order_streak` built from the existing owned record and effective campus/global reward definitions. A missed week resets the visible count; the previous week stays alive while the current week is open. Read failure is shown as unavailable with Retry, not invented zero. No GET awards points.

Dashboard links to the combined streak page, which shows both login and ordering progress, this week's qualification, configured HP rewards and the existing repeat-after-final-milestone rule. Rewards are read from Supabase (currently global weeks 3/6/12 with 100/200/350 HP), not fixed in frontend copy. Login calendar no longer infers every intervening day was checked in. Fee-only reward delivery cannot start a paid-food ordering streak. Delivery passes the order's campus to the reward selector; replayed HP does not emit another reward notification, and messages use the actual awarded multiplier amount.

Checks: 37 focused backend regressions pass; four controlled routed browser cases pass for dashboard source, combined page, actual reward-shaped content and unavailable/Retry. Read-only actual backend/Supabase execution read two owned audit streak records and all configured milestones, with zero writes. TypeScript, changed-file lint and complete build pass. No migration or customer-data changes. This batch closes the reported counter/read/display defects; broader interrupted delivery/reward recovery remains in the existing launch queue.

## Batch 3 — account menu closes after navigation

User clarified two separate issues: Chrome's native browser menu lacks an installation entry; the website account sidebar remains over the destination page. No install button was added to the website sidebar. The Profile install action from batch 1 is separate from Chrome-menu eligibility.

Reproduced the desktop Profile & Settings menu remaining visible after navigation. Immediate unmount now removes the blocking account panel without depending on its exit animation completing through a lazy route transition. Route changes, same-page selection, browser history, Escape and resize clear open state; desktop also gets the existing close control. Four native browser assertions run at both desktop and mobile sizes pass for destination navigation, same-page selection, Escape and close. TypeScript, changed-file lint and full production build pass.

## Batch 4 — PWA artwork and update delivery

Regenerated launcher/favicons from the user's supplied complete gold S on brand red. No replacement artwork was invented. The old generator used the wrong fallback/compositing path; maskable artwork is now visibly complete and contained inside the central 80%-diameter safe circle. PNG dimensions/opacity/safe-zone tests pass. SVG embeds the same supplied artwork.

Manifest has a stable root identity. Canonical hosting configuration serves manifest/worker with explicit types and revalidation, and icons revalidate. The worker cache version is advanced so existing sessions replace the old cached icons/manifest. Header changes live in the routes generator as well as generated vercel.json, keeping the build guard authoritative.

Latest production build in a normal persistent Chromium profile: secure context, parsed manifest/icons returning 200 at their declared dimensions, active controlling root worker, no Chrome installability errors. Native beforeinstallprompt was not observed in that headless diagnostic; the controlled event tests are separately labelled. This does not reproduce or explain the user's missing install entry in Chrome's own menu. Device-specific follow-up is pending; do not call the website Profile action a fix for Chrome's menu.

## Batch 5 — events launch gate

Added the global `events` feature flag and saved it disabled on Test Two (one global row, no new table/migration). Customer list/detail/tier routes show Coming Soon without loading the feature. Backend browse, tier, registration and check-in paths enforce the gate, so direct calls cannot bypass it. Staff can prepare/read content while admissions remain closed. Existing ticket history/downloads and catering remain separate. Super-admin flag controls expose the release guidance.

Three native controlled browser cases pass for disabled list, disabled direct detail, and enabled restoration. Backend tests exercise actual disabled HTTP routes before event reads/reservations, enabled delegation and staff-preview/admission separation. The complete backend suite passes **528 tests**; existing event-domain test fixtures now explicitly enable their feature and the email recorder supplies a real-shaped message ID. TypeScript, lint and complete production build pass. The previously discussed Chrome native-menu issue remains distinct from this release gate.

## Batch 6 — focused streak design and progressive challenges

Streak is now a dedicated login/order consistency page: paired tonal cards on desktop, readable stacked cards on mobile, an ordering progress bar with configured HP milestones, authoritative weekly check-ins and a persistent reclaim section. Detailed rules are expandable. The ordering card uses the existing dark brand gradient and warm gold accents instead of a large white text block. Login HP preview uses its cycle week rather than deriving a reward week from the raw day count.

Removed challenge lists and installation bonuses from Streak; Rewards remains their home, with a working `?tab=challenges` link. Retired the now-unused StreakMilestones component and its obsolete permission-only claim flow. Related challenge ladders show their next unclaimed target, advancing after the server confirms a claim. Independent activity types, recurrence periods, campuses and social destinations remain separate. Completed history is collapsed below active steps. This is presentation sequencing; it does not replace server eligibility/HP verification or invent new reward definitions.

Checks: progression unit cases pass; four native controlled Rewards cases prove first-step visibility, claim advancement, unrelated challenge retention and collapsed completion history. Streak browser checks prove independent counts, configured milestones, absence of challenge/install panels, reclaim visibility and unavailable/Retry. Mobile/desktop screenshots inspected. TypeScript, changed-file ESLint and complete production build pass. No financial/database migration or content mutation.

## Batch 7 — final release checks and current domain

The complete backend suite passes 528 tests. Full frontend lint found two pre-existing unused imports in rich-editor controls; removed without behavior changes. Built-site smoke found a retired domain hardcoded in the checker and relative production metadata when no public origin was configured. Added a tracked public-only `.env.production` with `VITE_SITE_URL=https://holygrills.online`; host environment overrides remain possible. No secrets belong in that file. Smoke reads the same production environment rather than assuming an old Vercel hostname. TypeScript, complete production build, full lint and built-site smoke pass.

GitHub's Vercel statuses confirm completed deployments for the sidebar, PWA artwork and streak/progression batches. Render health is 200; the actual deployed events API returns the expected 403 release-closed response, confirming backend activation of the new gate. These observations are separate from verifying the custom domain's current browser install menu. User confirms that missing entry affects both Android and desktop Chrome. The live-domain request still hits this environment's outbound proxy restriction; no repeated allowlist request was made.

## Batch 8a — authoritative reward pricing backend

Found additional concrete launch bugs: the editor offered legacy types rejected by the database, guessed HP prices with a different formula, treated a percentage as the backend's fractional value, and cost PATCHes did not recalculate HP at all. Database inspection confirms only timestamp/delete triggers on rewards, so there was no hidden recalculation to rely on.

Added an admin-only read-only economics preview using the existing backend functions, with positive-price validation and monetary liability. Cost edits merge the saved basis and recalculate outputs; unrelated edits preserve the saved price despite later global-setting changes. Explicit clearing is respected. Existing updated_at supports an editor precondition and compare-and-set write, refusing stale/concurrent repricing with 409. No table, migration, bulk repricing, existing redemption or customer ledger change.

Fourteen focused backend cases pass for preview/create/update agreement, food/merch basis, percentages, partial/cleared fields, invalid values, configuration outages, unchanged edits, authentication and stale/concurrent edits. The complete backend suite passes **542 tests**. Actual backend preview code read Test Two's configured economics successfully for synthetic food and merchandise inputs; zero writes. Backend is published before the dependent admin editor update.
