# Durable balance-change notices — 14 November 2026

Confirmed the missing referral reward notification: the atomic referral payout updated the ledger but never created a notice. Delivery HP notifications depended on a daemon thread after the payout; process loss could leave credited HP without a notice. Both now have a saved financial-boundary notification.

Applied `20261114201427_durable_balance_activity_notices.sql`: deferred triggers observe the final actual active HP/wallet balance and capture one net change per account/asset/DB transaction in the existing inbox and push outbox. A transaction-local marker suppresses intermediate/reversed/zero-net updates. Pending HP receives a separate clearly labelled pending notice; it is not described as spendable. Known specialised atomic reward notices and the existing recoverable wallet-transfer receipt avoid generic duplicates. HP/channel opt-outs are respected. No old customer activity is backfilled and no financial amount/rule is changed.

Delivery's daemon callback now only wakes saved balance receipts; it does not reconstruct another earned/unlocked notice after payout. HP/referral/wallet-credit paths also wake existing saved work. Losing that wake remains recoverable through the existing periodic outbox scan; no new recurring job/service was introduced.

Fresh production rollback proof passed before and after migration: net 75 HP, net wallet 50, pending 40, zero-net/interrupted work, explicit HP opt-out, one durable push, private helper permissions and fixture rollback. Delivery and financial recovery regressions pass with the updated wake-only contract. Actual push arrival is still device/provider-dependent; an inbox record or provider acceptance is not claimed as receipt.
