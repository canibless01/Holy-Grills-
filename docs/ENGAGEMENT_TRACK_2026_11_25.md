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

1. Completed in batch 2 below: weekly reports, verified ambassador metrics and roster performance.
2. Daily active users, page visits, funnels and streak analytics, included in existing daily reports. HP source reconciliation completed in batch 2; its daily-report inclusion follows with the engagement summary.
3. Guest/new-account push enrolment verification and fixes.
4. Editable repeating fourteen-day morning/15:00 push sequence: nickname personalization, operating-day/cutoff awareness, deep links, durable occurrence receipts and interruption/duplicate-send checks. Reuse the existing notification outbox and scheduler; do not add a second beat service or send customer-wide tests.

Before each source batch, fetch main and preserve the other track's changes. Report code, automated verification and actual provider/device verification separately.


## Batch 2 — verified weekly reports, roster reads and HP source reconciliation

Implemented:
- One set-based actor/campus-scoped RPC for ambassador roster metrics, replacing per-ambassador scans. Student dashboard metrics use the same verified source, limited to their own identity.
- Signup attribution chooses the first qualifying pre-signup click once, respecting campus ownership. Orders are checked against the live reporting order record: delivered, paid/not fully refunded, with net completed refunds; test and super-admin activity is excluded. Periods use delivery time in Lagos.
- Shareable weekly summaries with native date selection, copy and WhatsApp link; phone/email details are omitted from the share payload. Sharing counts remain explicitly manual confirmations, not claims about WhatsApp activity. Weekly target configuration remains campus-editable.
- HP period earnings now exclude pending/revoked awards. Current circulation is based on account balances, independently of the chosen report period, and tier membership is counted from one scoped owner read rather than one query per tier.
- A source reconciliation view separates current account HP, unspent ledger HP, pending awards, by-source allocations and any difference. It reports mismatches; it does not repair balances or rewrite financial records.

Database: `20261125091139_ambassador_verified_reports.sql` applied successfully to Test Two; guarded reporting RPCs are service-role only. Live read-back succeeds and current account/ledger/source totals reconcile. Exact business totals stay outside this public source document.

Automated verification: 97 ambassador tests, 8 new report tests, 16 existing report-contract/separation tests; local PostgreSQL rollback tests cover first-click uniqueness, refunded/test orders, scoped reads, self-only reads, configured share targets and HP reconciliation. Native weekly copy/share and HP source-table browser flows pass at 393px and 1280px. TypeScript, ESLint and full frontend production build pass.

Actual verification limits: live database aggregate/read boundaries are verified; real recipient WhatsApp sharing and deployed staff-device acceptance are not claimed. No external report or campaign was sent.
