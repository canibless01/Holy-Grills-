# Eight launch areas — 27 October 2026

These categories contain completed implementation and tested cases as well as open cases. None is signed off as an entire A–Z category. An open provider/device check does not mean its implementation is missing.

| Area | Completed implementation and evidence | Remaining |
| --- | --- | --- |
| Payment returns, funding, split, retries, reconciliation | Guest ownership/session isolation; callback recovery; pending cart preservation; gateway-before-confirmation; exact split remainder; provider verification guards; webhook recovery; late cancelled-order payment recovery and refund conservation below | Actual Paystack test-mode card/bank/funding runs; wider interruption and reconciliation matrix; guest manual provider refunds |
| Promos/discounts/rewards, cancellations/refunds | Promo editing and Lagos timing; reward economics; checkout benefit claims/release guards; partial-then-full refund/retry conservation; normal and flash reward promise retention; multi-gift timed campaigns and atomic grant/checkout/cancel loop ([evidence](MULTI_GIFT_CAMPAIGNS_EVIDENCE_2026_10_28.md)) | Full stacking/restoration matrix; delivery-stage reward/refund variants |
| Physical reward fulfillment | Instant entitlement; instant/next-order choice; earned snapshots; normal/flash redemption to zero-value order attachment | Final kitchen/rider handover, failed delivery and refund recovery variants; legacy missing snapshots |
| Address/batches/delivery exceptions | Saved address/gate/radius checks; standard kitchen to two riders/delivery/HP loop; automatic staging; manual assignment/reassign/split/cancel; actual delivery-date isolation; capacity rollover/move-up | Kitchen Handoff, preparation-day/date-preview and saved-pin navigation repairs are now verified in [handoff evidence](KITCHEN_HANDOFF_MAP_EVIDENCE_2026_10_27.md). Remaining: real map/device behavior, attempted/unclaimed/cancellation combinations and payout settlement |
| Email/push/links/workers | Explicit-quota email fallback; provider outcome checks; push registration wiring; corrected delivery-time and capacity-change notices | Durable quota counters/dispatcher/retries; actual push delivery; full deep-link matrix; running Celery/Redis schedules/recovery |
| Storefront/returning sessions | User confirms actual uploads; section-specific controls, multiple slides/copy/actions and prior session recovery fixes | Final presentation matrix and deployed returning-user loading/performance |
| Admin/role boundaries | Specific repaired paths tested; latest user campus/global changes preserved; service-only financial helpers and migration/grant checks | Ambassador programme financial and RLS cases are verified in the 28 October evidence. Remaining: wider per-action role/campus/global, error/retry/concurrency and consumer-reflection matrix |
| Chrome native installation | Local normal-profile installability, manifest/icons/service worker checks | Reported missing native Chrome menu entry on Android and desktop remains unresolved |

## This continuation: late payment and refund reconciliation

Previously, `confirm_order_payment` rejected a provider-confirmed payment after cancellation. A late bank transfer could remain in the failed webhook queue without a payment receipt or an automatic wallet return.

The server still validates provider status, currency, reference, owner, campus and exact card remainder first. It now routes closed orders to a service-only atomic reconciliation helper. The order remains cancelled/refunded; registered customers receive at most the unreturned card amount in their wallet. The payment receipt, refund ledger, counters and order log commit together. An existing paid receipt or full refund ledger prevents crediting the original payment again. Cancellation winning the lock after the initial payment read is re-read once and reaches the same recovery path.

Guests have no wallet. Their paid receipt is durably saved with `late_payment_resolution=manual_refund_required` and `reconciliation_required=true`; the order remains cancelled. The webhook stays in the existing failed/admin-review queue with an explicit manual-provider-refund reason. This records the obligation; it does not claim an automatic guest provider refund has been completed.

Notifications send only after a new wallet recovery, not replay. Ledger/notification copy is supplied from `messages.py`. Notification dispatch failure does not undo reconciliation; durable notification retries remain open.

Applied three ordered migrations: `20261027101108_reconcile_verified_late_order_payments`, `20261027101148_cap_late_payment_recovery_by_remaining_balance` and `20261027101550_centralize_late_payment_ledger_copy`. They introduce and refine one helper, not three overloads. Existing payment/refund tables and policies remain; no table/column is added. Inspected privileges show one signature with service-only execution. Security advisors report no finding for this helper.

Actual Test Two rolled-back SQL checks cover pending split cancellation (500 wallet/1800 card), late remainder recovery, exact replay, wrong amount refusal, partial then remaining refund, duplicate original payment after refund, historical missing payment receipt, partial legacy card-refund overlap and durable guest manual-review replay. No gateway charges, provider refunds or emails were made. Reusable SQL: `holy-grills-backend/tests/sql/late_payment_and_refund_conservation.sql`.

Backend suite: **587 passed**; new focused tests cover provider-proof refusal, closed-order recovery, notification replay, guest review, recovery failure and cancellation winning after the first read.

Cleanup remains paused. The earlier checkpoint and dated evidence files contain details; this table supersedes stale descriptions of already completed cases.

28 October continuation: ambassador programme migrations, financial/role repairs, signup consent and capacity-aware date selection are documented in [current evidence](AMBASSADOR_SIGNUP_SCHEDULING_EVIDENCE_2026_10_28.md). Returning-browser content recovery and push subscription/timing are active next checks.

Returning-browser read recovery and the push device-token contract are implemented and browser-tested in [follow-up evidence](RETURNING_BROWSER_PUSH_EVIDENCE_2026_10_28.md). Real OneSignal delivery remains separate from these registration checks.
