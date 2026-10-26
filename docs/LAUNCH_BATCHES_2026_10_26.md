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
