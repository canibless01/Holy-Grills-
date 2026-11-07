# Event management controls — 7 November 2026

This batch closes concrete operational controls around the existing atomic ticket/admission/refund work. It is not an all-feature ticketing-platform sign-off.

- Admin events are scoped explicitly and paginated with stable date/ID order. Publication uses the displayed event's desired state rather than searching only the first event page. New events default to draft in the native editor, with an explicit published toggle.
- Editing converts persisted instants to WAT input values. Host-funded input now matches the database's host_prepaid value, retaining compatibility with the old host_funded spelling.
- Venue QR generation renders a downloadable PNG locally; the private token never goes to an external QR service. The admin confirms rotation because old venue codes stop working.
- Registrant/tier/sales reads distinguish loading/failure/empty results, offer Retry and discard superseded/closed/scope-changed requests. Registrants support name/email/phone/ticket search. Staff can admit an eligible registrant or scan a ticket with the existing camera/manual fallback. Replayed admission does not claim another HP award. Mobile rows wrap without hiding attendee identity.
- CSV exports use formula-safe cells, and an empty export no longer leaves its action busy. Registrant queries use pagination-capable reads rather than silently stopping at the first API page.
- Admins can stop/resume tier sales without deleting its history. Tier body/name/boolean validation is explicit.
- A new scoped sales endpoint counts confirmed tickets and their recorded wallet/card/HP amounts. Unpaid holds and cancelled/refunded tickets do not become cash revenue through current-price multiplication. Its displayed cash metric is specifically cash on confirmed tickets, not a bank settlement report.
- Current/upcoming event browsing includes events still in progress.

Applied `20261107201745_guard_issued_event_history.sql` once: direct admin deletion of an event/tier with issued tickets is denied at the database, closing the API-bypass cascade. Unpublish/stop-sales and empty record deletion remain available. The trigger helper is not executable by browser roles.

Executed verification:

- 20 targeted backend event/admission/release/ownership tests passed; complete backend suite **1,277 passed**.
- Fresh Supabase BEGIN/ROLLBACK fixtures proved issued-history guards, retained tickets, empty deletion, unpublish, tier deactivation and private trigger access. No real event/ticket was altered.
- Native Chromium at 393px and 1280px passed paging/publication, WAT/funding editing, decoded QR display/download, read recovery, attendee search, committed-response-loss admission retry, formula-safe CSV, tier deactivation and recorded cash rendering. Existing mobile/desktop refund/review forms passed again.
- TypeScript and targeted ESLint passed. Complete client/SSR build and seven-route prerender passed.

## Remaining full-loop work

The owner has now requested an organizer workspace: event_organizer role; own-event drafts/submission; admin review/finalized prices and HP; separate fixed organizer entitlement per tier and ticket snapshots; own-event attendee/check-in/stats; separate payout requests/admin-recorded settlements. It is not implemented by this batch.

Other remaining operational features include event-wide cancellation/rescheduling with durable attendee notices and explicit refund policy, ticket receipt/resend/recovery exceptions and more extensive large-event/concurrent-management cases. A deliberately killed worker and independently simultaneous database sessions are not claimed by these controlled checks. Real-device camera and real bank/refund acceptance remain separate from local browser/SQL proofs.

The direct-RPC review additionally found two report functions lacking an active-account check. Applied `20261107203106_restrict_inactive_admin_reports.sql` once, preserving their bodies/signatures/grants and adding that check. `tests/sql/inactive_admin_report_access.sql` passed active own-campus reads and denied both reports after deactivation using the same claims.
