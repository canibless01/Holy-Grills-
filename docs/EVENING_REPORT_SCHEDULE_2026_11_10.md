# Evening reports and verified cart alerts

Owner-requested update, 10 November 2026:

- FUTA daily reports use **21:00 Africa/Lagos**, covering the 24 hours ending at that cutoff. The existing ten-minute scheduler captures the due report at 21:00–21:10; a missed slot catches up once. Late-night activity belongs to the following report, without a three-hour gap. Weekly Monday reports retain their previous Monday–Sunday calendar window.
- `daily_report_time` is an editable private campus setting, validated as HH:MM. No hosting environment change or additional recurring service is required. Daily period/recipient deduplication and the existing durable transport remain in place.
- Staff abandoned-cart alerts wait at least **30 minutes**. The send-time gate rechecks current cart contents, pending/paid checkout state, ownership, and recent member activity. Changed/cleared/recovered carts are cancelled; temporarily active or too-recent carts are deferred with `available_at` and checked afresh later. Previously queued early alerts cannot bypass this check.
- The checkout-confirmation warning and super-admin exclusion note were removed from operational mail. Actual test-activity filtering is preserved. Customer reminder frequency is unchanged.

Verification: 22 targeted backend cases, five native mobile/desktop settings/cart cases, TypeScript and complete client/SSR/prerender build pass. Local and production rollback matrices verify before/after report cutoff, 24-hour coverage and exact funding boundaries, report dedupe, twenty-minute deferral, recent-activity extension, eligible inactive carts, payment-before-send cancellation and configuration validation. The earlier operations rollback matrix still passes. All production audit fixtures roll back; tests do not send synthetic messages to customers.

Migration: `20261110202213_evening_reports_and_verified_cart_alerts.sql`, matching production history. Tonight's already-passed 21:00 report is eligible for catch-up after deployment; provider acceptance is verified separately from inbox delivery.
