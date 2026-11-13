# Check-in recovery notices — 13 November 2026

Recovered attendance and its inbox/push dispatch receipt now commit together in the existing `hg_reclaim_login_checkin` transaction. An API/worker exit cannot commit attendance while losing the notice. The Python caller wakes saved work only; existing periodic notification recovery handles interruption. No extra scheduled task or service is introduced.

The deterministic IDs match the preceding Python path, so retrying an existing reclaim does not duplicate an old notice. A normal login still does not become a reclaim. Preferences suppress notices without denying attendance. The message identifies a wallet top-up versus an order and the activity's saved WAT date, rather than incorrectly always saying an order recovered today's check-in or guaranteeing a successful week. The destination is the existing `/streak` page.

Migration `20261113081739_durable_checkin_reclaim_notices.sql` adds a private invoker helper and hooks the two successful existing reclaim branches. No historical activity or customer notice is replayed by the migration.

The expanded production `checkin_reclamation_rollback.sql` passes original receipt ownership/amount/source/payment/food/old-week guards, attendance merging, interruption rollback and no HP creation, plus atomic notice/outbox capture, same-reference replay and HP preference opt-out. Fixtures roll back. Targeted recovery/outbox tests: 81 passed. Full merged backend regression is recorded in the progress entry.

Separate remaining findings: membership-anniversary awards still use a read-before-award check with no reference ID; tier history/grace transitions and some milestone/legacy-gift notices still need their own interruption/concurrency proof. These are not certified by this attendance-notice fix.
