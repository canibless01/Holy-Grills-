# Explicit ticket email recovery — 13 November 2026

Completed: the confirmed ticket card, admin registrants and organizer attendee workspace now offer “Resend ticket email”. Guests can use recipient-bound signed email ticket access, or their original ticket/email proof. Signed-in owners, campus admins within their campus, super admins and the assigned event organizer are authorized. The recipient is always read from the current ticket owner/original guest record, never a submitted destination.

Each click intent creates its own durable notification delivery using the existing outbox. Double clicks are suppressed; a response-loss retry keeps its original UUID and recognizes the saved receipt without requeueing an accepted/uncertain message. A database-enforced two-minute cooldown limits different requests for the same ticket across workers. Unpaid, refunded, expired or canceled-event tickets cannot be resent. The immediate worker wake is best effort; the durable row remains available to existing recovery workers. UI says “requested”, not “delivered”. Existing old messages are never reset.

Migration `20261113083508_event_ticket_resend_intents.sql` is applied to Test Two. One service-only invoker and one nonduplicate partial outbox lookup index; no tables. Signed proof is validated by the backend before the service-only function receives it. Browser-supplied actor/signed flags are ignored.

Verification:
- Full backend suite: 1,688 passed.
- Live synthetic BEGIN/ROLLBACK: wrong guest/unrelated user denied, actual service-role execution, canonical destination, accepted request replay, cooldown, organizer ownership, changed-actor request conflict, linked-account guest proof denial, unpaid rejection and direct-execution grants.
- Four local competing requests: one queue row, three cooldown responses.
- Native Chromium at 393px/1280px for guest/owner/admin: duplicate clicks, response loss, identical UUID retry, requested confirmation, no overflow/console errors.
- TypeScript, edited-component ESLint and production build passed before push.

No real emails were sent during automated tests. Real recipient inbox acceptance and device scanning remain operational evidence, separate from these authorization/transaction/browser checks.

Next: configurable admission windows, then the remaining database/security and admin action matrix.
