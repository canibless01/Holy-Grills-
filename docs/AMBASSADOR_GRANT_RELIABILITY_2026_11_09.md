# Ambassador grant reliability — 9 November 2026

The next reward-audit batch follows the student/admin performance and same-campus wallet release. It closes the recorded ambassador grant/notification interruption and meal-entitlement concurrency cases; it does not certify all promotion, reward, reporting or admin exceptions.

## Reproduced and fixed

A rollback-only Supabase fixture linked two grants to the same milestone claim: the second request changed its amount and used the explicit additional-grant override. The claim then pointed at the second grant, and the student had received 75 HP instead of the first 50. Neither grant saved a notification inside the financial transaction; Python attempted that only after the grant committed.

The grant RPC now locks and validates a linked claim before awarding. A new grant cannot reuse an issued claim, grant against a rejected claim, or link another ambassador/month. An identical original request still returns its existing receipt before this check. Authorised additional **manual** grants remain available without reusing a milestone claim. Claim refusals have an actionable HTTP 409 response.

The same RPC saves the existing in-app and push notification channels with the completed financial action. The notification trigger saves durable external dispatch in that transaction. A failed capture rolls back the grant and benefit; a committed grant retains recoverable work if the Python process stops before waking it. No new table, recurring task or scheduler was introduced. Email channels were not added.

The notice uses the same UUIDv5 identity as the existing notification service, adopts historical random-ID notices, respects HP/push opt-outs and opens `/rewards`. Python only wakes saved owned push work after commit. Existing dispatch leases and the 15-minute recovery job handle missed wakes. At dispatch, missing, voided or reassigned grants are cancelled instead of announcing an invalid reward. Ambiguous provider outcomes retain the existing transport rules.

## Evidence

`tests/sql/ambassador_grant_atomic_notices.sql` passes in isolated PostgreSQL and Supabase using BEGIN/ROLLBACK. It covers all three grant types, stable identities, one in-app/one queued push, receipt replay, claim/period/rejected-state boundaries, supported extra manual grants, capture-failure rollback, opt-outs, historical notice adoption, voided replay and service-only helper execution. No fixture users, grants, benefits or notifications persist.

The existing `tests/sql/ambassador_meal_rewards_recovery.sql` also passes on the changed production schema. Its recorded checkout/refund cases retain the ₦4,500 meal − ₦3,000 discount + ₦500 delivery = ₦2,000 payable flow, stacking, wallet debits, early restoration, partial/post-preparation refunds and historical attribution. All fixtures roll back; there is no real order or provider payment.

`tests/ambassador_reliability_sessions.py` refuses remote databases. Independent sessions against an isolated copy of current table shapes, checks, unique indexes and application functions prove:

- Eight identical grant requests create one award, one grant receipt, two channel notices and one queued push.
- Eight competing monthly grants admit one award and return seven duplicate refusals.
- Eight changed-amount/override requests sharing one milestone claim issue exactly one grant.
- A separate client exits after grant and notification statements but before COMMIT: neither award nor notices persist. A committed response lost to the caller replays the original receipt without awarding again, and its saved push is due without a Python wake.
- Eight dispatch workers obtain one lease for the saved reward push.
- Eight requests competing for the last meal-discount use obtain one reservation. Eight restorations return one use once.
- Six restoration-versus-new-use races conserve one entitlement without a deadlock or negative remaining uses.

This local copy does not reproduce all Supabase platform authentication, RLS, foreign keys or unrelated triggers. Production schema/privilege compatibility is covered separately by the rollback matrices. No real process was killed in production, and no OneSignal/email send or customer balance mutation was used for verification.

Migration: `20261109210307_atomic_ambassador_reward_notices`. The security-advisor category counts are unchanged; the new private invoker helper is service-only. Existing notification preferences, recovery schedules, campus/role checks, meal caps, food prices and wallet/payment behaviour remain in place.

## Remaining scope

Wider promo/campaign/order-lock/squad and physical-reward refund/delivery combinations remain separate. So do report/export arithmetic, remaining staff action checks, the complete feature-flag consumer matrix and the other audit groups in `GENERAL_SITE_AUDIT_PROGRESS_2026_11_04.md`. This batch does not claim end-to-end acceptance of every feature.

Final release checks: **1,413 backend tests passed**; TypeScript and the full client/SSR/prerender build passed. Native browser checks passed all five student-benefit, checkout, manager-promo, manager-review and admin-grant scenarios. Production fixture-user/campus counts after rollback were zero; the migration created no historical notification broadcast or real grant.
