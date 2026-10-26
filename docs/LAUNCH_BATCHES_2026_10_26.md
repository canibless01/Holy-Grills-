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
