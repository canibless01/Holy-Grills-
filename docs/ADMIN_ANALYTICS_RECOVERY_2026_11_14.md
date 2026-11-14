# Analytics controls and report recovery — 14 November 2026

A2 follow-up found that failed headline report calls were converted into zero/null/empty figures with no retry, while overlapping date reads could replace newer results with an older range. The loading return also removed date inputs, making a slow/invalid range difficult to correct. UTC/browser-local presets disagreed with the API's Lagos business dates around midnight.

## Changes

- Date/preset controls remain visible through loading, invalid-range and report-failure states. Missing/reversed dates are rejected before report requests; date labels are accessible.
- Required headline feeds must complete successfully before their figures/actions are shown. Failure displays centralized explanatory copy and Retry; it does not invent zero revenue, users, orders or item counts. AOV uses a dash until a valid snapshot is available.
- Request generations discard stale date replies and unmounted reads. Shared child-dashboard reads now also guard stale/unmounted responses and expose an error even if a thrown error has no message.
- Presets/defaults/CSV filenames use the existing Lagos calendar helper. A note explains which reports follow these dates; other panels retain their own reporting periods.
- Brand requests load independently of date changes, have their own failure/Retry state and are not shown as an empty queue after failure. Mutation refresh uses the same guarded read.
- CSV failures/empty results use centralized messages; simultaneous export submissions are suppressed and all export buttons stay disabled while an export is pending.

## Verification

`holy-grills-frontend/scripts/test-admin-analytics-recovery-browser.py` passes at 393px and 1280px with controlled transport: one headline feed fails, no false KPI view, working Retry, visible date inputs during held reads, newer 90-day response survives a late 7-day response, reversed dates issue no new report reads, brand feed is not refetched for date changes, independent brand read/Retry, failed export recovery and downloaded CSV content/range/filename. At 23:30 UTC the dates and filename use the next Lagos calendar day. No production data or brand request was written.

Reporting regression: **28 passed** (`test_admin_reporting_contract.py`, `test_reporting_review_isolation.py`, `test_analytics_separation.py`, `test_refund_reporting.py`). No backend arithmetic/schema/permission changes. TypeScript and edited-component ESLint pass. The earlier full backend checkpoint remains 1,797; it was not newly repeated for this frontend read-control change.

Remaining A2: brand-request field/create/status/retry exceptions; further populated chart/export/historical-attribution cases beyond existing report evidence. This batch does not sign off every chart's arithmetic or all reports during concurrent database writes.

Full production build passed, including message/route contracts, client, SSR and prerender. Native test fixtures made no production writes; no migration was required.
