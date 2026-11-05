# Atomic event-ticket email dispatch — 5 November 2026

Free guest/account registration and card-ticket confirmation now save a private email dispatch record in the same transaction as the ticket/payment. A failure before commit leaves neither side committed; a process exit after commit leaves queued work for the existing recovery scan. Applied migration: `20261105121556_durable_event_ticket_emails.sql`.

The event API uses new service-only wrapper RPCs. Pending card reservations do not queue ticket emails. Repeated registration/payment callbacks reuse the existing dispatch row. Historical paid/free registrations made by old code are not backfilled, preventing replay of mail already sent. Old workers cannot claim the new raw ticket rows; updated workers use a new claim RPC which handles both existing notifications and ticket emails.

The same email router, quota reservation and safe fallback rules apply to guests. No extra provider, environment variable, scheduler entry or service is needed. Ticket content, recipient and QR payload are frozen before handoff; QR rendering stays local. Changed email/ownership or cancelled/refunded ticket state prevents a new send. A guest email does not link an account or award HP. Ticket emails remain transactional and do not depend on a marketing subscription.

The API reports `email_queued` and does not claim `email_sent` merely because a thread started. The bounded 15-minute recovery scan can retry a lost pre-handoff claim. A timeout/crash after provider handoff is uncertain and requires the existing provider-log review; it is never automatically resent on another transport. Provider acceptance remains different from customer inbox receipt.

## Executed checks

- New database rollback matrix: free guest/member capture, pending-card exclusion, amount mismatch, controlled payment interruption, commit/replay, historical isolation, frozen event content, old-worker isolation, new-worker claim, uncertain-email handling, admin review and private RPC/RLS access.
- Existing notification rollback matrix also passed through the new claim RPC, retaining its normal lease/replay/CAS behavior.
- Backend suite: **1,120 passed**. Focused notification/event/branding tests: **65 passed** before the full run.
- Guest dispatcher tests cover a real locally generated QR, escaped event title, recipient normalization, changed owner/address, cancellation/refund/payment guards, immutable prepared content, uncertain timeout and immediate-worker wake rules. Provider/database calls are controlled; no test email was sent.
- Security advisor findings remain the same five categories/39 findings. Retained audit users: zero. No real event tickets existed at the inspected baseline; no historical customer data was backfilled.

This closes the event-ticket payment/registration-to-email boundary, including guests. It does not retrofit every direct guest order/catering email call, implement paid-ticket refunds, or prove a killed production process or independent simultaneous database sessions. Those are separate boundaries in the consolidated status.
