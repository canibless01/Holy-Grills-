# Membership milestone rewards — 13 November 2026

The existing daily membership-anniversary job now uses a backend-only atomic reward function. It locks the actual active student profile and validates its active campus, WAT membership date and configured active reward. One deterministic account/milestone reference commits the HP grant, monthly tracker and inbox/push dispatch receipts together. Changed reward settings cannot change a completed award. A retry after a lost response does not credit or notify twice. Existing daily execution also catches up a due milestone later in its current anniversary month, including month-end date clamping. It does not invent missed milestones from prior months.

A single matching legacy NULL-reference award is adopted without another HP or monthly increment. Existing random-ID notice channels are retained; missing channels get deterministic recoverable receipts. Ambiguous or inconsistent old records require review. No historical balance or reward configuration is rewritten. HP/push preferences remain respected. Tier refresh retains the previous best-effort behavior after commit; tier history/grace atomicity remains separate.

The job skips inactive configurations and nonmilestone/future-day profiles before calling the financial function. It reuses the existing daily schedule, cron lock and notification recovery. Failed recipients do not prevent attempts for others, and incomplete runs request bounded automatic retries. No new recurring job, service, environment variable or frontend fetch is added.

Migration: `20261113082222_atomic_membership_anniversary_rewards.sql`. The live table currently has a globally unique `months` index; this batch preserves that schema and the existing campus-versus-global fallback rather than silently changing reward configuration semantics.

Verification:

- Full merged backend suite: **1,665 passed**. Final focused recovery rerun after tier-refresh preservation: **24 passed**.
- Fresh production BEGIN/ROLLBACK: grant/monthly/notice interruption, original/replayed award, changed settings, exact legacy grant adoption, old inbox-channel preservation, missing-channel recovery, active-student exclusion, month-end arithmetic and backend-only grants.
- Disposable local independent sessions: **24 concurrent claims** and changed-setting replay produce one original 70 HP grant, one monthly increment and one inbox/push pair. Local fixtures cleaned.
- Production fixture users across the squad, check-in and membership prefixes: **0**. No provider/customer sends or real payment/refund actions.
- Security advisor counts remain the preceding 2/1/13/22/1 baseline; the new reward function uses invoker security, a fixed search path and service-role-only execution.

Earlier squad and check-in batches were pushed separately. Broader tier/grace history, milestone/legacy-gift interruption coverage and remaining administration/presentation variants remain separate, not whole-site sign-off.
