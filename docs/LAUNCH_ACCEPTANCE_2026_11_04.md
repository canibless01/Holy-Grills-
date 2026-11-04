# Launch acceptance follow-through — 4 November 2026

All times use Africa/Lagos. This report records executed work against the owner's eight-area checklist. It is not a whole-site certification.

## Celery after the reductions

No essential job or reward amount was removed or reduced. All 18 scheduled tasks remain registered. Earlier changes reduced newsletter and scheduled-order scans to every 15 minutes, and abandoned-cart/post-delivery scans to hourly. Payment handling, paid-order confirmation and live kitchen operations do not wait for these scans. Weekly/monthly schedules are unchanged. The startup-memory change omits HTTP blueprints/Swagger from background contexts, with isolated Flask context per task.

The live audit log was inspected on 4 November: 13 job names had successful executions in the preceding two days. Recent campaign, scheduled-blast and scheduled-order executions occurred once per 15-minute interval; recovery scans occurred hourly. Daily birthday, tier grace, decay, rolling earnings, squad, membership and order-lock jobs also had successful records. This is actual worker activity, not just registered schedule definitions. No evidence of duplicate executions was seen in the inspected recent intervals; the number of running beat replicas still requires Railway service access. Ordinary weekly/monthly execution is not claimed before its scheduled date.

API `/health` returned `ok` with Supabase database, Auth and Redis connected. Added the Railway commit revision to health responses and commit/worker identity to private cron audit receipts, so future API/worker revision mismatches can be checked directly. These fields do not expose credentials.

## Executed database acceptance

**20 rollback verification scripts passed** against the real database, with no provider charge or synthetic data committed. The [machine-readable checklist](evidence/launch_acceptance_sql_2026_11_04.json) names each script. Covered:

- Campaign multi-benefit grant, eligibility, validity, checkout and cancellation/refund restoration.
- Late payment, partial/full/refund replay and conservation.
- Immutable earned reward promises after configuration changes.
- Delivery HP, squad-member financial recovery, FIFO pending unlock, welcome-once and ordering streak interruption/replay.
- Physical reward checkout, kitchen preparation, staging/assignment, rider isolation/pickup/delivery, attempted/unclaimed delivery, partial/full/replayed refund and early claim release.
- Ambassador grant, attribution, checkout/refund/retry and authenticated student/admin/super-admin/inactive boundaries.
- Rider settlement/earnings records, exclusion of incomplete/unpriced batches, mark-paid replay and undo. These are settlement records, not a real bank transfer.
- Kitchen stock permission/isolation, academic/calendar configuration, delivery zones/area, global feature flag scope, private financial helper privileges, kitchen handoff, service-date batch isolation, capacity refusal/overflow and paid move-up without a second debit.
- New event admission, active HP, milestone rewards, monthly counters, durable replay/zero outcomes, historical-ledger linking and interruption rollback.

Older scripts expected historical audit identities that the owner has since removed. This pass supplied six fresh isolated actors **inside each transaction** with `tests/sql/acceptance_fixture_prelude.sql`; the enclosing script rolled them back. The capacity fixture's delivery end was already past at this evening run: it correctly refused move-up. The fixture now keeps its own delivery window open until end-of-day. No production ordering/delivery hours were extended. That case passed after the fixture correction.

## Enabled events: corrected defect

Previously admission was inserted separately from HP. A crash could strand an admitted attendee without HP; a retry could return “already checked in” before reaching recovery, or recompute a reward from changed settings. Event milestones also had a separate completion/HP boundary.

Migration `20261104203927_atomic_event_admission_receipts.sql` is applied. The new service-only, security-invoker transaction:

- Revalidates event publication/end, release flag, ticket/payment/expiry, actor/owner/campus and door proof; locks the attendee and ticket.
- Saves admission, a durable reward receipt, ledger linkage, monthly earnings and event milestone awards together. One failure rolls back that whole boundary.
- Returns the saved result on retry; a zero reward stays zero when settings change. A historical existing ledger wins over new configuration, without another credit/counter increment. Ambiguous historical monthly counters are not blindly added again.
- Gives unlinked guests no account HP; contact email cannot establish ownership.
- Prevents direct anonymous/authenticated table writes from forging the server-owned receipt. Existing customer reads remain available; admissions use the validated API. Public execution of both new helpers is denied.

Real database rollback tests passed before and after applying the migration. Security advisors have the same five pre-existing findings; no new finding was introduced. No live check-ins existed before this change. UI copy now distinguishes a replay and removes the contradictory statement that **active** event HP must wait for another order to unlock.

Concurrent safety is implemented with profile/ticket locks and the existing unique keys. The tests executed rollback, repeated requests and response-loss replay; **independent simultaneous database sessions were not exercised**. This does not close every paid-ticket/refund variant or the general milestone/notification recovery audit. In particular, callbacks outside the event transaction retain separate recovery boundaries.

## Password-reset email

Requested a reset for the owner's account through the deployed API. A direct Supabase recovery request was also accepted with HTTP 200 and the intended `https://holygrills.online/reset-password` redirect. Supabase records `recovery_sent_at` at **21:40:15 WAT**. Use the most recent message. No password was changed and no recovery token was printed or stored in the report.

The owner acknowledged the requested check; that is not yet confirmation of inbox receipt, rendered branding or successful reset-page navigation. Hosted template management is not exposed by the connected tools. The prepared HTML remains in [Auth templates](SUPABASE_AUTH_EMAIL_TEMPLATES.md); SMTP acceptance does not establish that these templates were pasted into the hosted configuration.

## Checklist status and exact remaining work

| Requested area | Result in this pass | Still needed |
|---|---|---|
| Production acceptance | API dependencies healthy; live worker cadence confirmed; revision reporting added; production calendar retains Monday Nov 9. | Verify post-push API/worker revisions, actual single beat replica in Railway, and one owner-completed payment/return/tracking journey plus webhook receipt. The local configured Paystack key is test-mode; this alone does not prove Railway's intended payment mode. No charge was attempted. |
| Authentication email | Supabase accepted the request and records a recovery-send timestamp. | Owner's inbox/branding/link result and hosted template confirmation. Verification email is only required if confirmation is enabled. |
| Device acceptance | Previous manifest/browser-installability and map checks retained. | Actual handset/desktop install, iPhone Add to Home Screen, GPS and saved-location selection, notification tap destination. Owner acknowledgment is not acceptance evidence. |
| Enabled events | Atomic admission/HP/event milestones and durable replay fixed and rolled-back transaction tests pass; events remain enabled. | Paid-ticket/refund variants, simultaneous-session contention, broader ownership/expiry/changed-configuration matrix and interrupted external milestone notification. |
| Promotion/reward exceptions | Supported cases above reverified with real transaction conservation. | Complete combinatorial coverage of every supported promo/order-lock/squad/campaign/earned reward combination remains unproven. |
| Physical reward/delivery exceptions | Ordinary and attempted/unclaimed physical reward handoff/refund loops pass. | Full special/menu-linked/legacy reward-type matrix and every exceptional interrupted handover variant. |
| Interrupted reward/notification recovery | Event financial/milestone boundary fixed; existing delivery/order-streak recovery reverified. | Non-event tier/milestone/login-reclamation/legacy gift paths and durable external email/push crash recovery. Current external notification dispatch still uses daemon threads; stored receipts and quota counters do not prove crash-safe delivery. |
| Enabled admin controls | Listed database role/field/consumer checks and backend regression suite pass. | Every remaining native input/button, failure/retry/concurrent edit and customer-reflection loop in [admin coverage](ADMIN_AUDIT_COVERAGE_STATUS.md). This pass does not certify every admin page. |

## Validation and data cleanliness

Backend suite: **980 passed**. Frontend TypeScript and full client/SSR/prerender production build passed, including message and QR checks. Twenty database transaction scripts passed. All acceptance/event fixture profiles were checked absent afterward. No test accounts, orders, balances, event tickets, check-ins or rewards were retained; no provider charge, refund or broadcast was made. The only requested outbound action was the owner's password-reset test. Schema/source fixes are permanent; test data is not.


## Post-push deployment recheck and owner response

At 21:46 WAT the newest cron receipt was still 21:15 WAT (31 minutes old). This supersedes any inference that earlier successful runs prove present worker health. GitHub deployment checks reported the `8d51b3e` worker **failed**, although its API and beat succeeded. The newer `1002f59` worker deployment reported success, with API/beat still pending at that observation; fresh job completion is not yet proven. Railway logs are required to identify the worker failure's cause. No Railway management/token or direct Redis credential is connected here.

The checked-in Procfile had an explicit `--concurrency=2`, overriding the configuration's one-process default. Removed that override so `CELERY_WORKER_CONCURRENCY` (default 1) controls the checked-in worker command. An independently configured Railway Start Command can still override it and must be checked.

The owner reports **no reset email received**. Supabase's accepted response/recovery timestamp establishes a send attempt, not inbox receipt. SMTP delivery, filtering and hosted template configuration remain unresolved.


## Confirmed worker startup cause — owner-provided logs

The worker traceback identifies `kombu.exceptions.VersionMismatch`: the installed transport requires redis-py >=6.1, while requirements pin redis-py 5.2.1. Kombu was an unpinned transitive dependency. Added an explicit `kombu==5.6.2` pin, matching the tested environment and compatible with the existing Celery 5.4.0 / Redis 5.2.1 stack. Direct Redis-transport client-selection tests now cover both ordinary and prefixed clients, without network/provider calls; the earlier memory-broker probe could not catch this transport mismatch. `pip check` passed. No job, reward amount or provider routing changed. Railway must rebuild dependencies on the pushed revision; successful deployment status alone does not prove a fresh completed job.

Brevo logs provided by the owner show both reset requests as Sent followed by Error, from `noreply@holygrills.online` to the owner, with zero delivered. This establishes SMTP handoff to Brevo but failed downstream delivery. The detailed Error/SMTP response is still needed; no sender/DNS cause is assumed from the event labels. No additional reset email was sent during this investigation.
