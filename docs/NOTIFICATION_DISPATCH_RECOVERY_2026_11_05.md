# Saved notification dispatch recovery — 5 November 2026

New registered-user notifications now save their external dispatch record in the same database transaction as the notification. A process exit between the insert and its daemon thread no longer strands the message. Migration `20261105115039_durable_notification_dispatch.sql` is applied.

The existing scheduled-blast scan checks up to 50 due records, starting no further attempts after 45 seconds. One in-flight provider call can finish beyond that budget. It adds no service or beat entry; the 18 existing jobs and weekly/monthly schedules remain intact. Immediate dispatch still starts after the save, so ordinary orders do not wait for the scan. Recovery latency follows the existing scheduled-blast interval, normally 15 minutes.

## Delivery boundary

- A database row lock and two-minute claim lease prevent competing workers from beginning the same attempt. Prepared content is saved before the provider call, and a stale token cannot finish a newer claim.
- An interrupted push reuses its saved OneSignal idempotency UUID and identical payload. Automatic attempts stop after six claims or 24 hours. An unconfigured push does not freeze a missing application ID.
- A queued email or expired pre-handoff claim can recover. An email interrupted after handoff is **uncertain**: it is not automatically resent or switched to another provider. A timeout may have happened after provider acceptance.
- Existing quota routing remains authoritative. Only known non-sends such as unconfigured providers/quota exhaustion are automatically retried; ambiguous primary/fallback responses require review. Accepted fallback records the actual sending provider and message ID. Provider acceptance is not a claim of inbox delivery.
- Recipient preferences, a changed recipient email and cancelled campaigns are checked before dispatch. Private snapshots are hidden by restrictive RLS; service-only functions are unavailable to anonymous/authenticated direct callers. Historical untagged notifications are not backfilled or replayed.

## Admin review

Campaigns → **Delivery recovery** loads on demand, with no extra initial page request. Admins see only their campus; super admins can inspect the selected scope. Only failed/uncertain records offer review. Check the provider logs before saving:

- **Provider accepted** requires its message ID and log evidence; it marks the receipt sent without another send.
- **Provider confirms not sent** requires evidence, queues a fresh attempt and creates a new idempotency key. The existing scan sends it. Do not use this option merely because the customer cannot find the email.

Reviews have an immutable request UUID and an audit entry; repeating the same request does not duplicate the action. Uncertain reserved email quota is conservatively retained, including after manual reconciliation: it is not automatically decremented on an unproven delivery result.

## Executed verification

- Backend regression suite before concurrent reporting updates: 1,080 passed. Additional native role/lease-result checks: 37 focused tests passed. Integrated post-rebase suite: 1,093 passed.
- Real database rollback checks passed before and after migration: capture/history isolation, active lease exclusion, expired claims, immutable push replay, email uncertainty, stale token rejection, backoff/budgets, fallback IDs, scoped provider review, conflicting/repeated review and private RLS/RPC access.
- Browser checks of the real admin component with synthetic local API responses: mobile and desktop forms, lazy fetch, required evidence, review payload and refreshed queue all passed without page errors. No live provider request or production write was made.
- Frontend TypeScript and full client/SSR/prerender build passed. Security advisors retain the same five existing categories (39 findings); none introduced by this migration. Audit fixture users retained: zero.

## Scope still open

This closes the dispatch boundary for new records created through `send_notification`. Direct guest/event/QR email utility calls and Supabase Auth SMTP are separate paths; this migration does not make them durable. It does not make saving a business transaction and creating its notification one atomic transaction. Existing reward receipts must still retry notification creation if interrupted before that insert. Independent simultaneous database sessions and a deliberately killed production worker were not exercised; lease exclusion, replay and interruption states were verified with controlled database transitions. Real handset acceptance and a completed production payment/return/webhook journey remain separate owner checks.
