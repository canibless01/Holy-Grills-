# Delivery reward financial recovery — 28 October 2026

Synced the provider/PWA chat through d82fb04 before final integration checks. Its wallet, deployment-header, worker-lifecycle and map changes are preserved. Its real PAY-01–07 results are evidence for those cases, not substitutes for the wider refund/exception matrix.

## Defects corrected

- An already credited main food-HP award previously ended retries, leaving an unfinished pending-HP unlock, welcome grant or squad share unrecoverable through delivery re-drive.
- Finding any prior squad share skipped every remaining recipient. Per-recipient failures were logged but the order could still be marked distributed.
- A partial pending-HP unlock reused the food award's order reference and could collide with the existing unique business key. Whole-row unlocks lacked an order receipt and could be repeated against later pending HP.
- A failed squad-member read could fall back to paying all HP to the organiser. It now fails closed. Duplicate resolved profile IDs no longer dilute the organiser's share under different email rows.

The primary food award still uses its existing seven-argument atomic helper. It now commits a recovery marker in the existing order-status-log table with the owner's actual share and total squad award. No new table or column was introduced.

One service-only helper completes financial side effects under the order lock: FIFO unlock, at-most-once welcome bonus, registered squad shares, unregistered pending shares, organiser bonus, monthly counters and the distributed marker. The attempted terms are saved before the financial subtransaction. If one step fails, all financial changes from that attempt roll back; the main award remains committed, and the saved plan remains available for retry. Existing consistent recipient awards are treated as replays while missing recipients still receive their share. Retry cannot re-price a saved plan or consume a newly granted food multiplier.

The FIFO helper now records a durable per-order receipt and uses a separate reference for a partially unlocked transaction. Whole pending rows become active; partial rows retain the remainder. No duplicate summary earning is inserted for already activated whole rows. Retrying the same order cannot unlock pending HP acquired later. Expired pending rows are excluded.

Clients cannot execute the recovery helper. Recovery/unlock receipts are hidden from anon/authenticated reads and writes by a restrictive policy on the existing log table; normal order access and ordinary timeline entries remain available. Status-log enrichment excludes internal reward receipts and admission bonus plans so an override cannot overwrite those receipts.

Admin Orders → expand a delivered registered order → Recover delivery rewards re-drives the existing authorized status endpoint. Pending failures stay visibly pending; success and failure do not change delivery status or debit the wallet. Ambassador attribution failures on first delivery or re-drive are also reported as pending rather than turning a committed recovery into an unqualified success/500.

## Executed evidence

Real Test Two rollback SQL (`tests/sql/delivery_reward_financial_recovery.sql`): organiser share 26 of total 101; two registered shares 25 each; one unregistered pending share 25; 70-HP FIFO unlock across a whole 50 row plus a partial 20; bonus; injected inactive recipient; complete auxiliary rollback; recovery with an already credited recipient; immutable welcome terms; one welcome grant across two orders; completion and unlock replays; later pending HP not consumed; legacy ambiguity refusal; owner cannot read internal receipts. No provider or customer notification is called by this SQL.

Unit/integration contracts cover saved-plan reuse, first-plan food spend excluding delivery, changed-owner-share refusal, missing legacy receipts, financial refusal, early recovery of an already credited order, failed member lookup, duplicate resolved recipients and receipt-preserving log updates. The full backend suite passes 725 tests. Controlled React browser checks execute pending then successful admin recovery and retain the explicit partial/full delivered-refund, capacity, role and hours regressions. Frontend typecheck/build and changed-component lint pass.

Applied `20261028203718_recover_delivery_reward_financial_steps_atomically` and `20261028204752_keep_delivery_reward_receipts_server_private`. Final function inspection shows one primary seven-argument helper, one existing four-argument unlock helper and one new three-argument completion helper, all service-only. Advisors show no new finding for these helpers. Historic database advisories remain; this is not an all-database security sign-off. See https://supabase.com/docs/guides/database/database-linter .

## Migration history alignment

Compared local migration names with actual Test Two history. Renamed 22 existing matching-name migration files to their recorded applied versions, plus named the new privacy migration by its actual applied version. SQL contents were not reapplied by these renames, no remote history entry was edited, and no duplicate table/function was created. Updated ambassador migration path contracts and documentation. This prevents later migration tooling treating those same changes as new versions. The CLI-generation limitation documented earlier remains; the connected migration tool supplies the recorded versions. Unmatched historical files/history are not silently declared reconciled.

## Deliberate remaining boundaries

Older orders without the new primary receipt can have unidentifiable whole-row unlock history. Automatic recovery refuses these instead of guessing and awarding again; they need an explicit ledger review. No historical customer data was silently repaired or erased.

This closes financial delivery reward recovery for the tested paths. Tier/streak/milestone/first-order-gift auxiliary-hook outage recovery, wider promo/reward stacking and refund variants, durable notification dispatch and deployed worker execution remain separate work. Financial receipts do not make notification delivery durable. No external cron was deployed, no provider keys changed and database cleanup remains paused.
