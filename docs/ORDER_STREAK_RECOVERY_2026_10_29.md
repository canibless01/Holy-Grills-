# Ordering-streak delivery recovery

The previous handler wrote the week's streak before awarding HP. A failed award could therefore leave a counted week with no reward, and recovery used today's week rather than the delivery's week.

`hg_process_order_streak_atomic` now commits the HP ledger, monthly tracker and streak summary together. It snapshots weekly terms in an existing private order-status log before the financial subtransaction. Recovery uses the saved delivery timestamp in Nigeria time, the existing Python-compatible weekly UUID and saved reward terms. A second delivered order in that week adopts the same terms and cannot pay the weekly grant again. Older recovery preserves the latest delivery-week summary. Zero-food orders and missing delivery dates are refused. Only service_role may execute; browser roles cannot read the receipt.

Both already-credited recovery branches now run the streak path; its failure remains pending through the existing admin recovery action. Primary order HP and payment are unchanged. No new table or column was created. The previous unused Python-only streak payout path was removed.

Executed evidence:
- Full backend suite: **728 passed**.
- Real Supabase rollback script `tests/sql/order_streak_atomic_recovery.sql`: ISO-year/WAT boundary, delayed and out-of-order delivery, second order in the same week, intentional financial conflict with rollback, retry after configuration changes, repeated recovery, missed-week reset, zero-food refusal, private receipts and service-only grant checks.
- No audit fixture persisted, and no provider email/push/payment was sent.
- New function did not introduce a security-advisor finding. Existing unrelated findings remain.

Still open: durable tier/milestone/login-reclamation/legacy gift outage recovery and durable notifications; this does not certify every delivery hook. Missing historical delivery dates require review rather than guessing a reward period. This real SQL test controls global reward configuration only inside its rolled-back transaction: the existing `uq_order_streak_rewards_weeks` unique index currently prevents separate reward rows for the same week in multiple campuses. Campus-specific reward configuration requires a separate coordinated admin/schema change.
