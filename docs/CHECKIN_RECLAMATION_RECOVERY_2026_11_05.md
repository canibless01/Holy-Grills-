# Check-in reclamation recovery — 5 November 2026

All activity dates use Africa/Lagos (WAT).

## Corrected behavior

A wallet callback previously called reclamation without its transaction ID, and the service marked whichever day the callback happened to run. A delayed or replayed top-up could therefore reclaim a different day from the actual payment. Delivery callbacks had the same date ambiguity; the already-credited order recovery branch skipped reclamation entirely. Same-week login and reclamation also wrote whole Python JSON snapshots, allowing one action to overwrite another action's attendance.

The new service-only, security-invoker RPC reads the persisted qualifying receipt, verifies its owner and activity type, and merges only the appropriate day into the saved week under a row lock:

- Wallet credit: actual positive top-up/bank-transfer transaction at the configured reclamation threshold. A refund, small credit, foreign receipt or old-week replay cannot manufacture today's attendance.
- Food delivery: paid/partially-refunded delivered order with a positive non-addon food line. Unpaid, undelivered, addon-only or foreign orders cannot reclaim attendance.
- The receipt's actual WAT date determines the day. A delayed callback can repair that date while its week is still saved; it never shifts the activity onto the callback's date. An already archived week is not reconstructed from unknown attendance.
- Normal same-week login updates merge their own day under the same locking order. A checked or reclaimed day is not overwritten, and repeat processing does not increment the streak count again.
- Paid-order financial recovery now retries attendance too, including orders whose primary HP was already credited. This does not replay their wallet/HP award.
- A deterministic per-user/activity-day reference deduplicates reclamation notifications. A retry can recreate a missing notification; a saved external receipt is not proof of crash-safe provider delivery.

The existing configured `STREAK_RECLAIM_MIN_TOPUP` still decides the threshold. No HP reward amount, monthly cap, weekly completion rule, ordering cutoff or scheduled-job cadence changed. These RPCs do not award HP. Fraud-flagged/inactive profiles are excluded consistently with login attendance.

Migration `20261105025015_atomic_checkin_reclamation.sql` is applied. No new table or public write capability was introduced; both helpers deny anonymous/authenticated execution.

## Evidence

- **1,022 backend tests passed**, including ten new reclamation/integration checks.
- The real database rollback script `tests/sql/checkin_reclamation_rollback.sql` passed before and after migration: receipt owner/type/threshold, WAT boundary, prior-week replay refusal, both login/reclamation operation orders, duplicate processing, a controlled interruption and refusal of unpaid/addon-only orders. No attendance operation created an HP transaction.
- The test's first unpaid-delivered fixture was rejected by the existing database fulfillment guard. The fixture now uses a pending received order; no production guard was relaxed.
- All synthetic accounts, wallet receipts, orders and attendance were rolled back. Fixture counts were zero afterward.
- Security advisors stayed at the same five pre-existing findings, with no new finding.
- Deployment checks for the preceding `ee13437` release passed for API, worker, beat and Vercel. Fresh worker receipts identify that release through 03:45 WAT on 5 November. Successful runs and lock-skipped runs were distinguished; inspected locks were clear and no same-minute duplicates were found in the preceding two hours. This is not proof of the number of Railway beat replicas.

## Remaining scope

This closes receipt/date recovery and same-week attendance merging. The broader weekly login payout still saves pending HP and week advancement separately; its full atomic payout/cap/retry proof remains open. New-week rollover races, all legacy-gift/tier recovery, durable external email/push dispatch, independent simultaneous-session proof and the remaining launch checklist are not certified by this change.

The existing five database maintenance jobs were inventoried without changes: promo deactivation, tier maintenance, abandoned-cart maintenance, HP expiry and unpaid event-ticket expiry. No live job was manually replayed, disabled or removed.


5 November update: [weekly pending-HP payout/tracker/week advancement and notice recovery](WEEKLY_LOGIN_PAYOUT_RECOVERY_2026_11_05.md) now have atomic transaction and replay proof. General external dispatch durability remains separate.
