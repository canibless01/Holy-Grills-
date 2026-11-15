# Settings consumers and catering mail recovery — 15 November 2026

Reconciled against main `c05c46d`. Existing dashboard, staff lifecycle, shared contact/preferences, catering UI, lock/cart and earlier Settings/System fixes were retained. This batch fixes separate consumer/dispatch boundaries; it does not repeat those UI audits.

## Corrected consumers

HP transfer minimum amount previously came only from `HP_TRANSFER_MIN_AMOUNT`, while its admin/public setting could show another number. Minimum delivered orders read only the global row and treated a configured zero as missing. Both now resolve campus → global → environment through the validated settings reader, preserve zero, reject malformed/fractional/non-finite values and return 503 rather than authorize a transfer on a failed setting read. Eligibility returns the authoritative minimum amount, which the gift form uses. Completed request-ID receipts still replay before today's rules are reapplied. No live setting or balance changed.

Monthly birthday capture defaulted its optional switch to enabled, but final outbox handoff defaulted an absent switch to disabled. The shared dispatcher now uses the same default at both boundaries and still honors an explicit false.

## Catering status email

Applied `20261115211109_durable_catering_status_and_birthday_dispatch.sql`. Status edits now save a customer-email intent in the existing private operational outbox within the same database transaction. The API only wakes that saved request; losing the wake or crashing during preparation leaves leased work for existing scheduled recovery. No new table, periodic task, provider or environment variable is added.

The dispatcher checks the current campus, recipient email, status and superseding status receipts immediately before handoff. Internal-note edits do not silently cancel a still-current status message; outdated statuses and changed contacts are suppressed. Messages contain the public status/current quote (including zero), not private admin notes. The existing counted transactional router, provider policy, claim leases, uncertainty holds and opt-out rules for operator reports are retained. A lost response after sending is not blindly retried.

Rolling API deployments use an internal `catering-status-v1` write-protocol header: new API edits capture and wake the outbox, while old API edits keep their legacy send without also queuing a duplicate. The header grants no authority; the same authenticated update and campus RLS apply. Unrelated queries have no marker. Direct SQL edits without that marker do not request a customer email.

The historical public INSERT grant also let guests/members bypass the API's validation and rate limiter. Repository consumers use the rate-limited service API for submission; browser clients have no direct catering insert dependency. Removed direct INSERT privileges from PUBLIC/anon/authenticated, retaining service submission and the existing scoped admin/kitchen UPDATE permissions. No genuine request/history was modified.

## Evidence

- **1,924 full backend tests pass**, including 76 focused settings, catering, operator-mail, birthday and gift recovery cases.
- Full frontend typecheck, lint and client/SSR/prerender build pass. Native birthday cash/HP/retry/privacy checks pass at 393/1280 px, including authoritative minimum changes.
- Fresh production rollback proof passes before and after migration: legacy/new rolling-deploy behavior, atomic status intent, no-op deduplication, crashed preparation lease recovery, stale lease denial, superseded status cancellation, current customer destination independent of operator recipients, uncertain-send hold, default birthday enablement/explicit opt-out, service-only insertion and private-helper grants. No provider send or retained fixture.

Actual guest inbox delivery after a future genuine edit remains provider acceptance/recipient-device observation. This batch closes the identified post-update daemon-only loss window; it does not claim every historical catering communication was delivered.
