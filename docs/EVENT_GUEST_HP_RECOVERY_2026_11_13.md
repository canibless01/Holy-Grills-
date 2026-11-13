# Guest attendance HP recovery — 13 November 2026

Completed: checked-in guests can create and verify an account with their original ticket email and collect the reward earned at admission. New admissions save the earned amount and multiplier in the existing check-in receipt; changing event rewards or ending the event does not change that promise. Recovery runs when opening HP balance or My Events. Ownership, ledger credit, monthly tracking, milestones and receipt commit together. Retries and concurrent requests cannot award twice.

Older guest admissions without a saved amount are linked but marked for support review. Campus admins can review only their campus; super admins can review any campus. The admin registrant and event workspace attendee screens expose an amount/reason form. Organizers and students cannot grant HP. A completed review cannot be changed into a second grant. Zero-HP events do not invent an event award. Ticket displays use the earned receipt rather than the current event configuration.

No new tables. Migration `20261113082341_event_attendance_claims_and_ticket_recovery.sql` is applied to Test Two. New helpers are service-only invokers; anon/authenticated direct execution is denied. The filename reserves ticket recovery follow-up wording, but this migration implements guest attendance claims only.

Verification:
- Full backend suite: 1,665 passed.
- Live synthetic SQL transaction rolled back: verified/unverified ownership, earned snapshot after event changes, actual service-role execution, legacy review and replay, changed-amount rejection, zero-HP, function grants.
- Disposable local PostgreSQL: four competing sessions produce one claim; killing an uncommitted claim leaves no ownership/ledger changes and recovery succeeds.
- Native Chromium at 393px and 1280px: amount/reason validation, double-click suppression, committed-response-loss retry, earned amount and legacy review display, no overflow or console errors.
- TypeScript, edited-component ESLint and production build checked before push.

Still separate: explicit ticket email resend/recovery controls, configurable admission windows, remaining database/action matrix. Real recipient email delivery and handset scanning remain operational checks; no real provider charge or broadcast was sent during these tests.
