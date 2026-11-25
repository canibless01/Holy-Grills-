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


## Batch 3 — activity/funnel/streak analytics, daily email and guest consent

Implemented:
- Deferred, consent-gated first-party page measurement. Only normalized route buckets are stored; URL queries, order IDs/claim tokens, IPs and contact details are not included. Event UUID receipts make retries duplicate-safe. Guest page events never invent an account, and verified account identity comes from the JWT rather than the event body.
- Private, RLS-protected activity and weekly-streak history. Activity observes the existing login attendance profile write, adding last-seen in that same write; no extra login HTTP call or beat service is added. Existing actual last-seen observations/latest settlement receipts initialize only known facts, not fabricated historical visits.
- Daily observed student counts, opt-in visitors/page visits, page breakdown and ordered menu → checkout → paid linked-account funnel. Unlinked guest payments are explicitly not claimed as tracked conversions. Daily check-ins and saved qualified/failed weekly outcomes are reported separately.
- The existing users analytics endpoint now supplies real observed DAU/MAU keys instead of leaving the UI to default missing keys to zero. One scoped aggregate RPC replaces the old multi-read user report.
- Existing daily/weekly operations emails append engagement, funnel, streak and current active/pending HP source summaries. An unavailable sidecar does not block the core operational email. No additional recipients, test campaign or mail dispatch is introduced.
- Guest push opt-in may be adopted by an account created after that opt-in. The seven-day prompt-dismissal cooldown no longer expires valid adoption consent; older accounts' saved opt-outs are not silently changed.

Database: `20261125092930_engagement_activity_reporting.sql` applied successfully. Live aggregate execution succeeds; public/ordinary authenticated users cannot read the private activity tables or execute report RPCs.

Automated verification: 46 targeted activity/report/streak-recovery/operations-access tests pass. Local rollback proof covers duplicate event IDs, rejected raw URL tokens, guest/verified identity, ignored staff, campus/admin report boundaries, ordered funnel and persisted weekly outcomes. Native consent cases pass for opted-in guest/student, declined guest and super admin. Frontend typecheck, lint, production build, the v16 SDK contract suite and the new guest-consent cases pass.

Actual verification limits: database read boundaries are verified. Actual new-device guest opt-in, native OS permission, device display and real provider delivery for these changes are not claimed. No customer-wide tests or new messages were sent. The new metrics do not reconstruct historical traffic before collection existed.

The repeating campaign is completed in batch 4 below.


## Batch 4 — repeating 14-day campus push campaign

Implemented:
- Admin → Campaigns & Blasts → “14-day community push campaign”. The editor loads its configuration only when opened. A campus must be selected; changing the super-admin campus resets the editor. Campus admins cannot read or edit another campus, and community managers/students cannot manage campaigns.
- One optional campaign per campus, initially paused, with 28 editable steps: morning and afternoon for days 1–14. Defaults are 09:00 and 15:00 WAT. Start date and times are editable. The cycle repeats over calendar days; closed operating days are skipped, rather than shifting the cycle.
- Nickname personalization falls back to the first name, then “friend”. Other supported tokens are name, campus and order_cutoff. Preview renders a selected step without sending. Links are restricted to existing customer routes; images use Cloudinary. Default campaign copy lives in messages.py.
- Reuses the existing 15-minute scheduled-blast task and durable push outbox. No new beat job, scheduler or hosting service. Queueing is paginated and bounded; missed slots older than 30 minutes are skipped, so recovery never bursts historical messages.
- Reuses strict campus ordering schedules and checkout capacity status. Closed days, date overrides, cutoff and full capacity suppress ordering pushes. Actual ordering windows remain configurable; no Sunday or 16:00 cutoff is hardcoded in this feature.
- Recipients must be active students on the campus, with a registered device token and no saved push/promotions opt-out. Anonymous visitors are not silently enrolled in a personalized account campaign. Their separate SDK consent and new-account adoption remain supported.
- Atomic user/date/slot receipts prevent duplicates across concurrent ticks, crashes, edits and re-enabling a campaign. Each config revision has an audit snapshot; competing saves return a reload conflict.
- Dispatch rechecks active config revision, recipient/campus, preferences and operating state. Paused, edited or expired notices are cancelled. Push TTL is bounded by the slot expiry and ordering cutoff. The existing outbox allows only this new type’s TTL to decrease on retry; content, app and provider idempotency key stay fixed, and existing dispatch guards are preserved.

Database: 20261125143354_engagement_cycle_campaigns.sql applied successfully to Test Two. Three private RLS-protected tables and guarded service-role RPCs were added. Live read-back verifies no active campaign, no campaign receipt or due send from rollout, denied public/authenticated access and preserved stock/reminder outbox guards. No test records or cleanup were performed on the production database.

Automated verification: 267 targeted ambassador/engagement/reporting/notification-preference/outbox/blast tests pass. Isolated local PostgreSQL tests cover six simultaneous enqueue calls producing one notification/receipt/outbox, interrupted enqueue rollback, interrupted push recovery with the same provider key, shorter-TTL-only replay, foreign-campus/staff/opt-out exclusions, stale edit conflicts, pause/re-enable duplicate protection, audit history and private grants. Native browser tests at 393px and 1280px cover deferred load, day-14 edit, nickname preview, save, pause, stale conflict and reload with zero sends and no horizontal overflow. TypeScript, ESLint and the full frontend production build pass.

Actual provider/device verification: no real campaign was enabled or sent. A production provider acceptance receipt and physical-device display/deep-link tap for this new campaign remain external acceptance, not automated-test claims. Existing user-confirmed push receipt does not prove this new campaign on a physical device. API, worker and frontend deployments must pick up the main commits before the editor and scheduled path are available.

Assigned implementation status: batches 1–4 complete. This track does not include the other chat’s fulfilment, checkout or shared commerce work. Operator action: review the 28 steps and selected campus, then explicitly enable the campaign when ready for real recipients.
