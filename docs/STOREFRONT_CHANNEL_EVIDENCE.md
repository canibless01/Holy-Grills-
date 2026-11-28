# Storefront channel evidence — 2026-10-20

Scope: preserve the current main UI and finish the storefront channel contract. No database migration or remote data write is required.

## Changes

- Popup artwork preserves the uploaded aspect ratio, PNG transparency and full content. Its image button has no background, crop or corner radius. Text overlays are removed; optional CTA copy sits below the artwork.
- Popup display placement is selected independently from its CTA destination using exactly Home, Menu, Dashboard, Orders and Rewards. Layout owns a single popup instance; route/campus changes cancel pending fetches/timers and the selected section is shown once per visit/login session.
- Image-only popup and slider sections may be created without a title. Artwork is still required for image-only sections; ordinary text sections still require their title.
- What's Inside uses compact icon/image-and-text cards, supports independent full artwork cards and auto advances. Pause, hover/focus pause and reduced-motion behavior are supported. Mixed artwork cards no longer stretch compact cards vertically.
- How It's Made retains independent multiple CMS rows, per-row copy and safe CTA routing. Menu cards show their descriptions on mobile.

## Verification

- `/workspace/.venvs/holy-grills/bin/python -m unittest tests.test_storefront_artwork_sections tests.test_storefront_publication_and_media -q`: **64 passed**. In-memory database fixtures exercise production route functions for artwork creation, missing-image rejection, all five placement values, image/CTA/display-mode retention after edit, and independent process-card copy/destinations. The count includes inherited contract tests.
- `npm run typecheck`: passed.
- Owned-path `git diff --check`: passed.
- Root-executed Chromium/Playwright controlled HTTP fixtures: **all assertions passed**. At mobile width 390 px, the 960 × 360 PNG renders at 351 × 132 px with `object-fit: contain`, transparent parent and 0 px corner radius. Compact text-card height is 134 px. Reduced-motion stability, full-artwork containment, process-card `/faq` navigation, native CMS five-page dropdown/save/reload retention, page-scoped popup display, separate CTA navigation and once-per-session behavior passed. Native consent was dismissed with the actual Essential only control.
- Verified source batch SHA-256 (sorted relative paths + NUL + complete source bytes + NUL; excludes this evidence file): `62d00be040e67fee456a54d9603fb8872ff938f71a2cf78be5b76aebe84d65db`.
- Root also reports the combined backend audit suite passed (328 tests).

Private browser script and results: `/workspace/work/ecosystem-audit/storefront-20261020/browser.py` and `browser-results.json`. Browser fixtures intercept API/media requests locally and do not change customer data. The native CMS save/reload check uses controlled HTTP fixtures; backend persistence semantics are verified separately by the production-route unit tests. This is not a production database write test.

## Limits

No production CMS publication, live customer-data edit, database migration, deployment or push is performed in this channel. Native authenticated Dashboard/Orders/Rewards popup behavior follows the same exact-path mapping but requires the broader authenticated fixture matrix to verify each route visually.

Root visual review further reduces the compact card minimum to 88 px and uses a 3:1 full-artwork canvas. Recommended compact artwork: **960 × 320 px** (or 1200 × 400), PNG for transparency. Full artwork still uses contain, so other ratios are preserved with spare space rather than cropped. The earlier 134 px measurement is the pre-refinement proof. A final rerun of the complete browser harness passed with **90 px** compact-card height; popup containment/transparency, both homepage channels, reduced motion, native CMS save/reload and page-scoped routing also passed.
