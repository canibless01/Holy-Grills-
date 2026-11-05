# Admin reporting scope and date controls — 5 November 2026

## Fixed and verified

Economics now sends the effective campus to all three report endpoints. Super admins can view All Campuses or a selected campus; ordinary admins use their profile campus even if a stale super-admin selector remains in storage. Campus changes remount the report workspace, while an in-flight generation guard prevents late replies from replacing newer data.

Previously a failure in just one report endpoint could display an incomplete report with misleading zero values. Any failed section now produces a central-registry error and Retry control. Date controls remain visible, allowing a bad range to be corrected rather than trapping the user in repeated failed retries. Default dates now follow the WAT business day, including the hour after Lagos midnight while UTC is still on the previous day.

Analytics and Economics reject reversed dates and date-conversion overflows as invalid input. Both retain inclusive WAT calendar days converted to a half-open UTC range. Analytics export validates its limit before fetching any table. The existing campus filter, bounded CSV output and spreadsheet formula protection are covered by handler tests.

## Evidence

- **1,049 backend tests passed** after integrating the launch chat's weekly-reward recovery commit `5ccb912`. Ten new reporting contract cases exercise actual date helpers and handlers: invalid/reversed/extreme dates, same-day WAT boundaries, campus-admin/super-admin/global Economics scope, early invalid-limit rejection, scoped/date-bounded CSV output, row limits and formula escaping.
- **Native Chromium/Playwright passed** with controlled HTTP and no live writes: all-campus and selected-campus reports, regular-admin profile scope, all three scoped/date requests, ignored delayed replies, partial-failure behavior, retained date inputs, retry recovery, and WAT midnight defaults using a fixed browser clock.
- TypeScript, ESLint and the complete production build passed, including client/SSR builds and seven-route prerender.
- A read-only aggregate reconciliation query on live Supabase returned **0 ingredients, 0 balance mismatches, 0 ledger-campus mismatches**. Since there are no live ingredient rows, this does **not** establish populated reporting correctness. Prior fresh synthetic transaction rollback stock evidence remains applicable. No database schema or real customer data was changed in this batch.

## Remaining

No existing stock summary/reconciliation/export screen was found. A native implementation and populated reconciliation/export cases remain separate work. This batch does not establish full programme-economics arithmetic, every Analytics chart/export, reporting under concurrent database writes, or the whole admin page-by-page audit. Existing hardcoded copy elsewhere in Economics also remains in the broader message-registry cleanup; new error/date-control copy uses the registry.

Next general-site verification: wider Analytics/Economics arithmetic, filters and exports, then review moderation and rating reflection, followed by the remaining role/action pages in the general-site inventory. Launch acceptance remains with the other chat.
