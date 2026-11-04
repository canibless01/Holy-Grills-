# Pre-launch completion and verification — 4 November 2026

All dates and operational hours below use Africa/Lagos (WAT).

## Live configuration and cleanup

- Deactivated the erroneous **FUTACOOPS** hostel. The separate, gate-linked FUTASCOOPS Hostel was preserved.
- Recurring Sunday ordering and delivery windows are explicitly closed. The operating-hours table already had Sunday closed; the windows now agree with it. Closed rows remain active so no fallback can accidentally reopen Sunday.
- Saved dated closures for 4–8 November using the existing ordering/delivery window configuration. They expire naturally after their dates; no code toggle needs reversing.
- The production calendar returned **9 November 2026** as the next available date, with delivery **19:30–20:30**. Monday's existing 60-order capacity and 00:00–16:00 intake remain in force. If Monday fills, the normal capacity rules apply; no capacity was fabricated.
- Following the owner's explicit cleanup instruction, removed the seven orders created before the pre-launch configuration at 12:40:01 UTC. A fixed list of IDs protected any newer preorder from concurrent deletion. Related order records followed their existing foreign keys; order-specific inbox notices were removed.
- Verified **zero orders and seven accounts** afterwards. Wallet balances, wallet ledgers, payment receipts, user accounts and non-order activity were preserved. No provider refund or charge was made. A restricted local backup was retained outside version control.

## Complete ordering verification checklist

| Stage | Result and evidence |
|---|---|
| Public menu and campus selection | Live production menu API returned 13 available items. Customer requests use the browsing campus. |
| Menu → item → menu navigation | Browser used the real public catalogue through a read-only proxy. One menu-items request served the round trip, completed in 3.2 seconds, with no uncaught browser errors. This is a functional check, not a general latency benchmark. |
| Modifiers and stock/prices | Existing checkout/modifier regression suite passed. New cart test verifies campus price overrides and disabled stock still apply with one bulk availability read. |
| Guest pending card order | Real database admission created a pending guest order; preparation was refused before payment. |
| Card confirmation/replay | Real payment-record RPC confirmed the synthetic receipt, and replay was safe. No request was sent to Paystack. |
| Signed-in wallet order | Real order RPC debited a synthetic wallet exactly once. |
| Kitchen received → preparing → ready | Actual authenticated kitchen RLS allowed both paid fixture orders through these states. |
| Automatic rider grouping | An on-campus hostel and an off-campus gate order automatically joined the same gate/window/date batch. |
| Kitchen assigns rider | Actual service-only batch transaction accepted the restricted kitchen actor. |
| Rider access and pickup | Assigned rider saw both orders and picked them up. An unrelated rider could not update them. |
| Delivery and completion | Both orders reached delivered and the batch reached completed through the real database rules. |
| Pre-launch dates | Real FUTA admission rejected a closed pre-launch date and Sunday, accepted a Monday preorder/payment, and refused early preparation. |
| Test isolation | Every synthetic actor, wallet, menu item, payment receipt, order, batch and reward in these database tests was rolled back. |

Database evidence scripts are in `holy-grills-backend/tests/sql/`:

- `launch_order_to_rider_rollback.sql`
- `monthly_rollover_atomic_rollback.sql`
- `prelaunch_monday_admission_rollback.sql` — date-specific evidence for this pre-launch period, not a timeless CI test.

The live kitchen should be empty now. New preorders for Monday belong to Monday's preparation date; they should not appear as food to prepare today.

## Weekly and monthly jobs

- Weekly archives now label the week that actually ended. Both weekly and monthly rankings use active students from the correct campus, omit HP transfers, retain valid earnings with null references, paginate beyond the Data API response limit, and break ties consistently.
- Snapshot uniqueness is now campus + period + ranking type. The old global uniqueness rules would have blocked a second campus from archiving the same period.
- Monthly snapshot, leaderboard sides/spins, top-four tracking, third-finish Hall of Fame induction and monthly Hall of Fame side now commit in **one service-only transaction**. A failure rolls everything back; a replay returns an idempotent receipt without duplicating rewards. Existing prize quantities were preserved.
- Real rolled-back database tests exercised all those grants, replay safety, campus/type isolation and denial of public execution. No live user's monthly rewards were replayed.
- Monthly tier grants use the configured credit-validity setting and deterministic HP references. Failures retry instead of being reported as success. The tracker-reset test verifies the current month is retained.
- Weekly/monthly grants use bounded retry backoff. All 18 scheduled tasks remain registered with WAT schedules.
- First ordinary post-change weekly execution is Monday, 9 November at 00:01 WAT; next monthly archive is 1 December at 00:01 WAT. Their absence from the current execution history is distinct from the controlled tests above; no historical live rewards were backfilled.

## Hosting work reduced

| Frequent job | Previous interval | New default |
|---|---|---|
| Newsletter campaigns | 5 minutes | 15 minutes |
| Scheduled-order staff notices | 5 minutes | 15 minutes |
| Abandoned-cart recovery | 30 minutes | 60 minutes |
| Post-delivery nudges | 30 minutes | 60 minutes |
| Scheduled blasts | 15 minutes | 15 minutes |

These scans total **336 rather than 768 invocations/day**, a **56.25% reduction**. Transactional order/payment notifications and the live kitchen queue do not wait for these scans. Newsletter/staff-notice scans may wait up to 15 minutes; recovery/survey scans up to an hour.

- Default Celery worker concurrency is one; the existing per-process Flask application reuse remains. An existing command-line concurrency override takes precedence.
- Cron monitoring now reads all jobs through one indexed database request instead of 18 REST requests. Monitoring derives the four adjustable cadence labels from the actual Celery configuration.
- New optional Railway variables: `CELERY_CAMPAIGN_SCAN_MINUTES=15`, `CELERY_SCHEDULED_ORDER_SCAN_MINUTES=15`, `CELERY_RECOVERY_SCAN_MINUTES=60`, `CELERY_WORKER_CONCURRENCY=1`. Defaults apply when absent. Share schedule overrides between the scheduler, worker and API so monitoring agrees.
- No Railway billing percentage is claimed. Fixed memory/service charges and actual resource limits still determine the bill. No Railway platform service was removed or resized from this session.

## Page loading improvements

- Available-menu and customer item/addon metadata can reuse a scoped 15-second catalogue read; categories and tier definitions use up to 60 seconds. Account, campus, token and request parameters isolate entries.
- Writes invalidate the cache before and after completion. Late responses cannot repopulate a cache invalidated by a write; failed reads are not cached; callers receive separate copies.
- Wallet balances, HP balances, order status/tracking, payment verification and checkout totals are never put in this cache. Checkout still validates current price/stock/capacity server-side.
- Item details and addons load in parallel; customer detail reads use the browsing campus. Dashboard no longer repeats the provider's initial streak request.
- Cart availability is fetched once for the whole cart rather than once per line. Existing hidden-tab kitchen polling reductions remain.

## Verification and full remaining list

- **969 backend tests passed**, including new rollover, cadence, monitor, stock/price and null-reference rank cases.
- TypeScript, complete production build/prerender, request-sharing, catalogue-cache and paid-cart checks passed.
- Three real database rollback scripts passed. Both migrations were applied, privileges checked, and the new functions do not add security-advisor findings.
- Public production checks confirmed the calendar, available menu and the previous Railway code rollout. This report's new commit still needs the normal Railway/Vercel rollout after push.

Remaining operational confirmation:

1. Confirm the new Railway API, worker and beat deployments are all on the pushed commit. If an explicit worker `--concurrency` override exists, use one process for the intended launch profile. Keep a single beat scheduler.
2. Check Railway resource/billing graphs after rollout. This session has no Railway management connection or billing metrics, so actual monetary savings and platform sizing cannot be verified here.
3. Observe the first ordinary weekly/monthly production executions on their scheduled dates. Controlled task/database verification is complete; manually replaying real-user rewards is unnecessary.

External launch checks not re-tested in this pass: Google Business Profile/review Place ID and Search Console ownership, physical-device GPS/native PWA eligibility, and a new real outbound email/push or card charge. Existing OneSignal work was left intact, as the owner reported it resolved. These are not represented as newly proven by the database/browser tests above.
