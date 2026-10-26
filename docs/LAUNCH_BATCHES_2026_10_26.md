# Small launch batches — 26 October 2026

User confirms actual storefront Cloudinary uploads now work, including story/menu/icon content. Upload transport is no longer an open defect on that evidence. Remaining storefront work concerns content routing/presentation, not replacing the image provider. Events and marketplace are deferred for launch; prioritize existing order, reward, promo and notification flows. Cleanup remains paused.

## Batch 1 — installation recovery

The root installation component now imports the shared prompt store eagerly. All install buttons consume one browser prompt, with synchronous claiming to prevent double use. A legacy permanent dismissal no longer hides installation forever; new dismissals expire after seven days. Profile has a permanent manual install action that overrides banner dismissal and opens browser-specific instructions if no native event is available. Successful installation clears stale prompts and closes the UI; prompt rejection has a usable fallback.

Checks: TypeScript, changed-file ESLint and complete production build passed. Shared install-store tests pass for early capture, concurrent consumers, errors, new events and installed invalidation. Five controlled native browser cases pass for legacy dismissal, one native prompt, Profile instructions, manual recovery after dismissal and appinstalled closure. Existing OneSignal v16 tests pass. These browser tests use controlled events/API and perform no external writes.

Run from frontend: `node scripts/test-install-prompt.mjs`; `python scripts/test-install-browser.py` (Python Playwright + Chromium).
