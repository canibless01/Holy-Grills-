# Menu performance, crawlability and settings checks — 11 November 2026

## Changes

Menu category selection no longer starts another full catalogue read. Categories already filter the in-memory campus catalogue immediately; the effect mistakenly also depended on the selected category. The existing 15-second API cache concealed this extra network request in the previous immediate-click browser check. Advancing the cache clock beyond 15 seconds reproduced the redundant request before the fix. Campus changes, explicit Retry and real browser resume/reconnection retain their existing refresh behavior. Search still debounces remote discovery and displays known local matches while that request is pending.

Menu now uses its existing shared route metadata for runtime SEO as well as prerendering. Previously the prerendered title was “Grilled Chicken, Wings & Sides at FUTA, Akure | Holy Grills” but hydration replaced it with “Today's Menu | Holy Grills”. The heading and page layout are unchanged.

This eliminates a specific redundant request; it does not establish a whole-site percentage speedup or remove the first catalogue API request.

## Verification

- Targeted event tests: **114 passed**, covering save recovery, operations, payment recovery, guest ownership, private ticket QR, atomic admission and paid refunds. At the owner's direction, event implementation stays with the other chat; these are automated contract checks, not new live provider/bank settlement proof.
- Feature-flag mutation/release-gate tests: **18 passed**. Settings validation: **3 passed**.
- Native admin feature-flag browser suite passed global toggle and immediate frontend gate refresh, failed-write preservation, creation, legacy campus-override visibility, campus-admin read-only controls and failed-read Retry. HTTP fixtures isolate writes; no live release switches changed.
- TypeScript and the full client/SSR/prerender build passed, including existing build contract checks and all seven public routes.
- The updated native page-performance suite verifies category filtering after cache expiry without a new catalogue request, consistent hydrated menu title, immediate local search with remote secret-item discovery, responsive menu images, and a retained reconnect refresh. Its existing dashboard, CMS, settings, campus-admin settings and rewards cases also run against the built output.

Read-only production HTTP checks returned 200 for all seven sitemap pages: `/`, `/menu`, `/events`, `/marketplace`, `/our-story`, `/faq`, `/terms`. Every response includes its prerendered route root and content headings, a matching canonical and Open Graph URL, nonempty description/social image and no meta noindex. Embedded JSON-LD parses as JSON. `/robots.txt` and `/sitemap.xml` both return 200, and robots declares the sitemap. Dynamic hero slides and actual campus catalogue data still load through JavaScript; the checks do not imply that every menu item is embedded in static HTML.

Google can fetch these public pages without waiting for client execution to see their static content and metadata. This evidence does not establish Google indexing, rankings, autocomplete suggestions or a refreshed AI Overview; those are controlled by Google.

## Remaining scope

Event follow-ups are delegated to the other chat per the owner. This batch verifies existing settings/flag controls; it does not close the entire flag-to-consumer matrix or all historical staff permissions. Remaining general-site priorities are wider settings/consumer and role boundaries, additional reward/interruption variants, and reporting/export/stock reconciliation cases listed in [the consolidated audit record](REWARD_RESTORATION_AND_AUDIT_STATUS_2026_11_11.md). The ordinary event contract checks above should not become a duplicate event implementation project here.
