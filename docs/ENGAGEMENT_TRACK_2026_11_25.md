# Ambassador and engagement track — 25 November 2026

Owner scope: ambassador operations, engagement/HP analytics, guest push enrolment and repeating engagement campaigns. Fulfilment, checkout, delivery subscriptions and shared commerce performance belong to the other track.

## Batch 1 — promo lifecycle and separate WhatsApp contacts

Implemented:
- Campus-scoped community managers/admins and super admins can edit a promo's caption/Cloudinary graphic and delete it from the programme. Deletion keeps a tombstone, recipients and an immutable before/after history; it does not erase operational history.
- A revision check rejects stale writes. Edits do not reassign or resend recipients. A deleted message cannot be resurrected through a replayed creation request.
- A durable creation fingerprint prevents identical requests with different UUIDs from creating multiple messages/assignments in the same campus and month. Database locks and a unique receipt index enforce this across processes.
- A separate ambassador WhatsApp override is stored on the ambassador record; changing or clearing it does not change the account phone used for other operations. Sharing uses the override first and the profile phone as fallback.
- Promo recipient reads obtain the contact override through the existing campus-scoped join, without an extra per-ambassador read. Share captions now use `/register?ref=...` directly.
- Customer-facing strings are in `app/messages.py`; images must be Cloudinary uploads.

Database: migration `20261125085748_ambassador_engagement_management.sql` applied successfully to Test Two (`zaxdkrmzyibkvlsrgmvq`). It adds fields, indexes, a service-only audit table and guarded service-only RPCs. No production test fixtures, cleanup or customer notifications were created.

Automated verification:
- 97 ambassador backend tests pass.
- Local PostgreSQL rollback proof covers creation, editing, tombstones, duplicate receipts, optimistic conflicts, contact clearing, inactive staff, role/campus boundaries and RPC permissions.
- Independent local SQL sessions: six concurrent creates produce one message/assignment; competing edits have one winner; four concurrent deletes retain one deletion history and cannot resurrect the create receipt.
- Browser fixtures pass for community manager, admin and super admin at 393px and 1280px: edit → assignment read → WhatsApp override/share link → delete. No external messages are sent.
- Frontend typecheck, ESLint, message registry check and full production build pass.
- Live metadata read-back confirms additive columns, audit RLS and service-only mutation access.

Actual verification limits: source/database permissions are verified; deployed staff UI acceptance and real-device WhatsApp handoff are not claimed. No real WhatsApp or OneSignal campaign was sent.

## Remaining batches in this assigned track

1. Shareable weekly ambassador reports; reconciled referral/delivered-order attribution and ambassador roster performance.
2. Daily active users, page visits, funnels and streak analytics; active/pending HP reconciliation by source, included in existing daily reports.
3. Guest/new-account push enrolment verification and fixes.
4. Editable repeating fourteen-day morning/15:00 push sequence: nickname personalization, operating-day/cutoff awareness, deep links, durable occurrence receipts and interruption/duplicate-send checks. Reuse the existing notification outbox and scheduler; do not add a second beat service or send customer-wide tests.

Before each source batch, fetch main and preserve the other track's changes. Report code, automated verification and actual provider/device verification separately.
