# Pending social milestone recovery — 5 November 2026

Applied `20261105122035_atomic_social_milestone_rewards.sql`. Social-follow milestone completion, pending-HP ledger and monthly tracker now commit together. Previously the completion was written first; a failed credit could leave a permanently completed milestone with no HP, because an already-completed retry exited before recovery.

The service-only transaction locks the recipient and saved completion, checks the milestone's campus/trigger/period, applies the existing global monthly pending cap and saves the actual credited amount in a receipt. Python retains the current multiplier behavior. It preserves the existing UTC month key for pending accounting and WAT milestone period keys. The pending-pool ceiling remains enforced: failure rolls back completion and tracker so the claim remains retryable. No reward amount, cap or environment variable changes.

A response replay uses the saved receipt and completion ID, preventing another credit, tracker increment or distinct notification. Zero/capped promises stay zero after settings change. A legacy completion with a known `challenge` ledger links it without a second credit or ambiguous tracker increment; one without a ledger requires review rather than an invented payout. The notification uses its actual saved HP and deterministic completion reference, and the external push follows the existing durable dispatch path.

## Evidence

Native rollback checks passed: completion/HP/tracker interruption rollback; normal pending destination with active HP unchanged; changed-amount replay; partial/full monthly caps; zero reward; pending-pool failure without consuming the completion; campus/period guards; conservative legacy reconciliation; service-only execution. Eight focused service tests passed, including an already-completed social claim re-entering receipt recovery and refusing success notices for uncredited rewards.

The combined regression suite passed **1,149 tests** after the concurrent admin user-grant changes. All **35 SQL rollback scripts** passed together on the current schema, including those concurrent admin grants. No audit users were retained. These tests do not claim independent simultaneous sessions or a killed production process. Tier transition history/notification recovery and other unrelated direct-email boundaries remain separate checks.
