# Event reliability, uploads and storefront ordering — 9 November 2026

## Completed

- Organizer submission, review and payout actions now capture in-app notices and durable push-dispatch rows inside the business transaction. Python only wakes saved work. An interrupted backend cannot commit the action while losing its notice. Existing notification tables, preferences, provider leases and scheduler recovery are reused; no new table or scheduler is introduced.
- Review retries with the same outcome/notes retain the same receipt version and notice identity. Payout bank details do not retain the server-only notice-copy envelope. Copy comes from `messages.py`.
- Browser CORS preflights now allow `X-Campus-Scope`, which the frontend sends on super-admin global writes. Its omission blocked global image signatures before Cloudinary was contacted. Approved origins and role checks remain enforced.
- Organizer scanning explicitly accepts attendee ticket QR payloads (including emailed guest tickets) or a pasted ticket UUID. Customer self-check-in continues to use venue QR mode. Repeat admission returns an already-checked-in receipt rather than another HP credit.
- CMS section and banner/carousel arrows now move/rank the complete same-campus, same-surface list in one transaction. Equal initial ranks no longer make moves ineffective. Expected IDs/ranks/timestamps reject stale edits; failure refreshes the displayed list. Stable list tie-breakers use creation time and ID. Slides inside a carousel continue to be published through Save.

## Evidence

Independent local PostgreSQL sessions, using current production function definitions, table shapes, checks/unique indexes and relevant triggers:

- Eight simultaneous scans of one member ticket: one check-in and one 50HP credit; seven replays.
- Eight simultaneous guest scans: one admission, no unowned HP credit.
- Client process exits after admission/HP statements but before commit: neither check-in nor ledger/balance update persists; a new session succeeds once.
- Committed response loss: a new session retrieves the original admission receipt.
- Six admission/refund races: exactly one valid state, with no deadlock or check-in/refund double state.
- Competing payout requests reserve available earnings once; concurrent request, approval and recorded-transfer retries preserve one payout record.
- Process exit during submission rolls back notices and state. Concurrent submissions/reviews capture one notice per channel and durable push, without a Python wake.
- Eight dispatch workers compete for one lease. Expired push work preserves its provider idempotency key; an old worker cannot finish a newer lease. Interrupted email handoff becomes uncertain rather than being blindly resent.

`tests/event_reliability_sessions.py` refuses remote databases and requires an isolated local database named `reliability`. This is concurrency/process-interruption evidence, not a claim that the local copy reproduces all platform RLS, foreign keys or generated authentication columns. Production authorization and schema compatibility were checked separately through fresh synthetic BEGIN/ROLLBACK fixtures; no customer data or real provider messages were used.

`tests/sql/event_reliability_notices_and_sort.sql` passed in Supabase after migration: atomic/replayed notices, durable dispatch, five equal-ranked sections and five equal-ranked hero banners, persisted ordering, stale rejection, global-content protection and service-only helper privileges. All fixtures rolled back.

Native Chromium checks at 393/1280px cover carousel/card ordering, reload persistence and stale-error recovery. Event-management journeys also verify selecting an image, a controlled Cloudinary response, preview and saving the returned URL. Backend checks use real authenticated middleware/signature handlers and browser preflight requests with global scope. This verifies application wiring; it does not substitute for a real Cloudinary/provider acceptance run.

Full backend regression: 1,376 tests passed. TypeScript, targeted ESLint and QR payload tests passed. Organizer and event-management mobile/desktop journeys cover draft/review/settlement, admission retries and navigation. The full client/SSR/prerender production build passed. Final native organizer checks at both widths also passed pasted-ticket scanning and duplicate-admission feedback.

## Migrations / access

- `20261109130634_atomic_organizer_notices`
- `20261109130638_atomic_storefront_reordering`
- `20261109131048_atomic_banner_reordering`

Each is applied once and matches Supabase history. Each new helper has one signature with service-only execution; no duplicate table or browser financial privilege was added. Security advisors retain the same five pre-existing categories, tracked separately.

## Next work / deferred scope

Event-wide cancellation/rescheduling, durable attendee notices and explicit refund policy are next. Exceptional ticket receipt/resend/recovery and configurable check-in opening times remain in that event-exceptions batch. Real camera/device/provider delivery and actual bank-transfer acceptance remain external acceptance checks. Recovery after a lost immediate wake needs the existing recovery worker to be running; this batch does not configure hosting/Cron.

Group purchases, buying tickets for friends, ticket ownership/HP attribution and any squad-style distribution are deferred by the owner. Current admission remains individual-ticket based. Ticket transfer and delegated door staff are also deferred.
