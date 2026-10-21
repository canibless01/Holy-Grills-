# Reward release gates and challenge configuration — 21 October 2026

This bounded change fixes release-off leaks and challenge administration. It does not complete the requested generalized promotion scheduler, reward/refund stacking matrix or interruption-safe challenge awarding.

## Corrected behavior

- Reward detail now runs optional authentication, respects the same saved/selected campus as the list, and uses the same release-gated flash-status lookup. A paused flash feature cannot advertise a live sale on the detail endpoint while the list hides it. Guests without a selected campus see global rewards only; foreign campus detail is not found.
- Flash redemption's route checks the verified caller's campus, matching the atomic RPC's existing campus/global resolution. No financial RPC, table or grant is changed.
- Changing an HP multiplier cannot announce a live event while its release flag is disabled or its effective configuration has expired. Global announcements target active students and skip campus-paused or overridden recipients whose actual effective multiplier differs.
- Challenge create and partial update validate title, trigger type, integer target/HP bounds, actual booleans, weekly/monthly/lifetime period and optional HTTPS social URL before persistence. Optional description/artwork/social fields may remain absent or be cleared; no badge artwork is required.
- Campus administrators create in their own scope and cannot edit global/foreign definitions. Super admins can create global definitions. An existing definition cannot be moved between campuses and strand its completion history. A write returning zero rows is a refusal rather than a successful save; database failures return a central message.
- The admin form includes an Active switch and accurately describes paused creations. Unsupported birthday verification is no longer offered. Read failures expose Retry instead of an empty editable panel. Edit/grant/deactivate icon buttons have accessible labels.
- Recurring challenge progress is calculated from the current period's actual verification data. Previously its response lacked progress, so the frontend showed zero even when a claim was eligible.

## Verification

Thirty focused backend tests passed, including six new release-gate tests and eight challenge configuration/progress tests. Runtime assertions include disabled actions before financial calls, disabled/expired broadcasts before recipient queries, effective campus overrides, invalid create/patch payloads, scoped writes, zero-row persistence, nullable optional fields and current-period progress. TypeScript and owned admin-component ESLint passed.

Parent live verification is pending for the prepared journaled script `challenge-release-live.py`; it uses only the owned audit campus/student, creates one weekly challenge, and tests invalid edits, visibility and three competing successful claims. It does not modify global flags or send real-user blasts. The native routed browser script `challenge-browser-latest.py` uses controlled API fixtures and is separately pending.

## Scheduler and transaction limits

Parent's read-only Test Two inspection found global `hp_multiplier=false` and `flash_redemptions=false`, with no corresponding multiplier/flash pg_cron jobs. Source inspection found no Celery task/beat registration implementing automatic random event generation, advance staff reminders or their day-of user blasts. Existing notification templates are not an implemented scheduler. No global release setting was changed; those disabled gates must remain off until deliberate release.

The challenge completion engine currently inserts `user_milestones` and then awards HP/counters in separate requests. An interrupted/failed award can leave a completion receipt without its intended HP, and retries can treat that receipt as already complete. Successful concurrency proof does not establish crash recovery. A future private transaction must commit completion, actual HP, month counter and any immutable snapshot together, with explicit historical reconciliation; this patch does not hide or claim to fix that risk.

Generalized time-based multi-benefit campaigns, full reward/refund combinations, real provider notifications, durable broadcast recovery and native physical fulfillment remain separate open work. No migration, table, column or cleanup was introduced.
