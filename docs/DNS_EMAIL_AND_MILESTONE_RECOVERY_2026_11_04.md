# DNS, reset email, worker recovery and active milestone grants — 4 November 2026

All user-facing times use Africa/Lagos.

## Sender coexistence and reset acceptance

Live DNS now contains both the original OneSignal/Namecheap SPF TXT record and Brevo's separate ownership TXT record at the domain root. The original DMARC record is unchanged. Brevo's two DKIM CNAMEs plus branding, link and image CNAMEs resolve to the values supplied by the owner's Brevo setup. Namecheap is the authoritative DNS provider.

A root TXT ownership record does not replace or expand SPF. Separate ownership TXT records can coexist at `@`; there remains one SPF record and one DMARC record. No OneSignal, Resend or mailbox-forwarding record was changed by this code session.

Provider reads after the DNS additions:

- Resend reports `holygrills.online` **verified**.
- OneSignal reports the domain **active**, its verification records **passed**, and both email and push **enabled**. Provider checks are configuration evidence, not a newly sent test campaign.
- A fresh reset was requested through the live application. The owner explicitly confirmed: **the email arrived and the reset link works**. This closes the previous rejected-sender/password-reset receipt issue. Visual branding of every hosted Auth template was not independently confirmed.

## Celery is executing after the dependency fix

The deployed API, worker, beat and Vercel checks for `e704c5c` all reported success. The public API health response identified that revision and healthy database/Auth/Redis dependencies.

More importantly, the real database has successful receipts from that revision at **22:15 WAT** for scheduled orders, scheduled blasts and newsletter scans. This is fresh task execution after the earlier worker failure, rather than an inference from a successful deployment label. All 18 schedules remain registered. No job, reward amount or weekly/monthly cadence was removed.

The failure was the unpinned Kombu upgrade requiring a newer redis-py than the pinned 5.2.1 client. `kombu==5.6.2` now pins the compatible transport; direct ordinary/prefixed Redis client-selection regression tests pass. The lower process default is retained. The number of actual Railway beat replicas still requires Railway service access; no extra scheduler was deployed here.

## Next recovery gap corrected: active milestones

Self-claimed verified milestones, automatic non-event milestone callbacks and manual administrative grants previously inserted a completion and then issued HP in separate operations. A process failure could preserve completion without HP, and retry would stop at “already completed.”

Migration `20261104213212_atomic_active_milestone_rewards.sql` is applied. The new service-only, security-invoker RPC locks the recipient, validates scope/issuer/period and saves completion, active HP, monthly earnings and a durable receipt together. New grants either commit together or roll back together. Existing API eligibility, PWA/push prerequisites and manual-grant permissions remain in force; manual grants still bypass promotional multiplication. Existing event milestone grants use this same atomic boundary inside their admission transaction.

A replay returns zero newly awarded HP and the saved original amount separately. Zero rewards remain zero after settings change. Period-specific completion IDs distinguish recurring grants. A known historical ledger can be linked without a second credit or speculative monthly-counter increment. An ambiguous old completion without a ledger is reported as requiring review rather than fabricated into a payout. At inspection there were no existing live completion rows; this is not a backfill of real customer rewards.

Milestone notification retries now use completion-specific deterministic IDs, so a retry does not create another notification and a later month's completion has its own notification. Preference categories and opt-outs were not reclassified. This does not establish durable external dispatch across a provider/process crash: the general email/push outbox work remains separate.

Self-declared pending/social rewards retain their existing cap-aware path; their full crash recovery is not certified by this active-grant fix. Missing callbacks before any grant begins, broader tier/login/legacy-gift recovery, independent simultaneous database-session tests and the remaining exceptions in the launch checklist also remain open.

## Verification and cleanliness

- Integrated backend suite: **1011 passed** after including the concurrent stock-control changes. The final twenty-test recovery/contract run also passed, including notification period/retry deduplication and isolation of one failed automatic milestone from other earned grants.
- New real database rollback proof: completion/ledger/counter atomicity, controlled interruption, changed/zero replay, period scope, manual issuer role/campus, conservative legacy reconciliation and service-only mutation.
- Existing real event admission/HP/milestone rollback proof still passes with the shared helper.
- Both SQL scripts passed before and after applying the migration. All synthetic actors and financial rows were rolled back; fixture-profile counts were zero afterward.
- Security advisor findings were unchanged: five pre-existing findings, no new finding.
- No new test customers, retained orders, provider charge, refund or blast. The only outbound test was the owner-authorized reset email.

The [broader launch checklist](LAUNCH_ACCEPTANCE_2026_11_04.md) remains the map of unfinished areas; this report supersedes its earlier reset-email and stale-worker observations.
