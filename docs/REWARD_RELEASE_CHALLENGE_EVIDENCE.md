# Reward release gates and challenge configuration — 21 October 2026

This bounded change fixes release-off leaks and challenge administration. It does not complete the requested generalized promotion scheduler, reward/refund stacking matrix or interruption-safe challenge awarding.

## Corrected behavior

- Reward detail now runs optional authentication, respects the same saved/selected campus as the list, and uses the same release-gated flash-status lookup. A paused flash feature cannot advertise a live sale on the detail endpoint while the list hides it. Guests without a selected campus see global rewards only; foreign campus detail is not found.
- Flash redemption's route checks the verified caller's campus, matching the atomic RPC's existing campus/global resolution. No financial RPC, table or grant is changed.
- Changing an HP multiplier cannot announce a live event while its release flag is disabled or its effective configuration has expired. Global announcements target active students and skip campus-paused or overridden recipients whose actual effective multiplier differs.
- Challenge create and partial update validate title, trigger type, integer target/HP bounds, actual booleans, weekly/monthly/lifetime period and optional HTTPS social URL before persistence. Optional description/artwork/social fields may remain absent or be cleared; no badge artwork is required.
- Campus administrators create in their own scope and cannot edit global/foreign definitions. Super admins can create global definitions. An existing definition cannot be moved between campuses and strand its completion history. A write returning zero rows is a refusal rather than a successful save; database failures return a central message.
- The admin form includes an Active switch and accurately describes paused creations. Unsupported birthday verification is no longer offered. Read failures expose Retry instead of an empty editable panel. Edit/grant/deactivate icon buttons have accessible labels.
- Recurring challenge progress is calculated from the current period's actual verification data. Previously its response lacked progress, so the frontend showed zero even when a claim was eligible. Automatic callbacks now recheck this period too: lifetime order totals cannot satisfy a weekly target, and a callback carrying just the latest event increment cannot prevent an otherwise reached period target from being checked.

## Verification

Thirty-two focused backend tests passed, including six new release-gate tests and ten challenge configuration/progress/automatic-period tests. Runtime assertions include disabled actions before financial calls, disabled/expired broadcasts before recipient queries, effective campus overrides, invalid create/patch payloads, scoped writes, zero-row persistence, nullable optional fields and current-period progress. TypeScript and owned admin-component ESLint passed.

Parent ran the journaled actual backend/Supabase script `challenge-release-live.py`. It verified existing release-off listing, created one own-campus weekly challenge, read it back through the student challenges/progress endpoints, and confirmed a malformed edit leaves the saved HP unchanged. Its first three claim attempts were correctly refused because the actor had no `delivered_at` inside the current WAT week; old synthetic status-only delivered fixtures do not satisfy a weekly delivery challenge. No completion or HP was awarded by that refusal. After genuine native kitchen/rider deliveries, the guarded continuation found an existing completion from the automatic delivery hook and stopped before attempting another grant. A read-only receipt/counter inspection plus already-completed replay check is prepared; it is not yet marked passed. No global flags changed and no real-user blasts were sent.

The actual routed mobile Playwright script `challenge-browser-latest.py` passed two controlled UI cases: admin load-failure → retry → active weekly creation without badge inputs, and student verified progress → claim → completed state. The API responses were intercepted in that browser proof; it does not establish live HP accounting. The live script and browser proof are deliberately separate.

## Scheduler and transaction limits

Parent's read-only Test Two inspection found global `hp_multiplier=false` and `flash_redemptions=false`, with no corresponding multiplier/flash pg_cron jobs. Source inspection found no Celery task/beat registration implementing automatic random event generation, advance staff reminders or their day-of user blasts. Existing notification templates are not an implemented scheduler. No global release setting was changed; those disabled gates must remain off until deliberate release.

The challenge completion engine currently inserts `user_milestones` and then awards HP/counters in separate requests. An interrupted/failed award can leave a completion receipt without its intended HP, and retries can treat that receipt as already complete. Successful concurrency proof does not establish crash recovery. A future private transaction must commit completion, actual HP, month counter and any immutable snapshot together, with explicit historical reconciliation; this patch does not hide or claim to fix that risk.

Generalized time-based multi-benefit campaigns, full reward/refund combinations, real provider notifications, durable broadcast recovery and native physical fulfillment remain separate open work. No migration, table, column or cleanup was introduced.

## Live challenge result

A journaled campus-only weekly challenge was created through the admin API. Invalid edits were refused and the saved definition remained intact. Early claims correctly failed because the old synthetic delivered rows had no delivered_at in the current week. After the two real native wallet deliveries, the delivery milestone hook automatically created one completion and one 25-HP active ledger receipt. Three explicit claim replays then left the completion, ledger and monthly counter unchanged. A guarded continuation stopped on discovering that automatic completion; it did not award a second time. This proves the normal automatic/replay loop, not transactional recovery from interruption between separate writes. Both controlled admin/student browser cases passed.
