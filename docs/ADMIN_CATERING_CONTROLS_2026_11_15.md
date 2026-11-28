# Catering administration — 15 November 2026

Completed the current request-editor/list exception batch under A5, preserving existing customer→admin→assigned-kitchen controls.

- Staff assignment now uses named active staff choices from scoped role-filtered directory reads. Unavailable/inactive/foreign staff are not silently selected; failed staff reads expose Retry and block saving. Existing assignments are retained while loading.
- Quote, status and internal-note inputs retain drafts on failed saves; pending fields, close/backdrop and repeat submissions are locked. Zero quotes are distinct from no quote/budget. Negative, boolean, non-finite and oversized quotes are rejected explicitly.
- Edits carry the saved timestamp. The handler validates it and conditions UPDATE on the saved timestamp/status, rejects stale/conflicting edits and recovers an already-committed identical edit without another transition notice. An invalid request UUID is a clean 404. Existing kitchen assignment/transition restrictions remain.
- Lists previously fetched the first 50 rows and only searched/filtered those rows in-browser. They now have 25-row server pagination, search across organizer/event/email, server status filtering, stable created-at/ID ordering, selected-campus scope and honest current-page counts. Search/status reset pagination. Loading/error retain filters; Retry preserves the requested page.
- Event-catering reads start only on that tab. Event API failure does not block ordinary requests; its own error/Retry is shown. No provider email or genuine catering request is used in the browser tests.

Verification:
- **40 focused catering/platform tests pass**, including numeric/assignee validation, timestamp/replay/race and kitchen guards; server list scope/page/order/search sanitization and invalid-status handling.
- Native 393px/1280px request controls pass: staff failure/Retry/filtering, named assignment, negative/zero quotes, private notes, duplicate/close suppression, failed-save draft retention, identical retry payload, stale edit and close→refresh→reopen→cancel recovery.
- Native 393px/1280px pagination passes with 60 synthetic requests: page 1→2→3, search beyond the first 50, filter/reset, zero quote display, failed page read/Retry and isolated event-tab failure. No production writes.
- Independent actual-handler local PostgreSQL sessions: eight identical edits replay safely with a zero quote; competing different notes admit one winner and one 409. Exact disposable fixture cleanup; no external notification. This is persistence-contract proof using local access, not new live RLS/provider acceptance.
- Full backend checkpoint **1,843 passed** before integrating the other chat's subsequent community-gift additions. The final identical-edit re-read adjustment also passes the focused suite and local concurrency harness. TypeScript, edited-component lint and full client/SSR/prerender build pass. No migration required.

Remaining explicit limits: event registrant export/host-email retains its earlier evidence; actual host/customer email receipt and worker/provider interruption acceptance are separate. Existing status email code starts a send thread after the database update, so process-loss durability across that boundary needs review with the shared worker/settings owner; it is not proven by these UI/handler tests. Broader A5 and other owners' remaining items stay in the master list. No whole-Catering provider-delivery certification is implied.

Merged-main verification after community-gift integration: **1,868 backend tests passed**, and the complete production build passed again. The final identical-edit re-read path is additionally exercised by the focused and independent-session tests.
