# Current audit checkpoint — 13 November 2026

## This request's completed scope

- Scheduled-order customer reminders: starting 10:00 WAT on the paid order's delivery date, existing scan/recovery jobs, member preferred email/push/inbox and guest transactional email/private tracking. Repeated, unpaid, test, cancelled, delivered and rescheduled-away orders are guarded.
- Tier/grace: actual-campus active definitions, rolling earned HP, valid atomic history, saved notices, grace start/recovery/expiry, retry/concurrency and stale-warning suppression. Existing daily jobs use bounded DB batches, not per-user REST ledger reads.
- Challenges/milestones: verified active/pending awards, period/cap/role/campus boundaries, immutable retry and legacy adoption; closed the completion/notification interruption gap. Native referral progression and weekly challenge retention pass.
- Promotions: fresh stacked campaign/side/delivery/HP/promo/lock/squad/earned-physical reward refund/restoration matrices pass. Native campaign editing, changed-settings history, stale-write Reload and interrupted refresh preserve the grant. These bounded cases do not claim every theoretical combination was run.
- Checkout: Free sides plus one Rewards box, delivery-saving versus food-HP explanations, no empty delivery-zones info dropdown, editable stale-reward selection, existing gate-pickup/pin distinction and contact flow preserved.

## Still separate from whole-site sign-off

1. Historical database RPC/RLS/grant dependency review. Existing advisor findings remain; the other chat has already reduced unnecessary trigger-helper grants. Avoid disabling shared predicates/aggregates without proving their dependencies.
2. Remaining native administration/exception coverage: newsletter/preferences, ambassador measurement/report/share exceptions and CMS/presentation variants beyond the completed cases. This is unverified breadth, not a list of reproduced defects.
3. **Legacy recovery closed for the current launch configuration:** live inspection found no pending legacy gift/multiplier/cap/unsnapshotted records, and fresh legacy admission/refund/replay and earned-snapshot matrices pass. See `LEGACY_GIFT_RECOVERY_CLOSURE_2026_11_13.md`. The obsolete disabled hot-dog promotion is deferred feature work if reintroduced; it is not a current customer-recovery backlog.
4. Operational observations: actual inbox/device receipt of the new scheduled reminder, subsequent nightly job receipts and any bank/provider settlement. SQL rollbacks and provider acceptance are not customer inbox confirmation.

Previously owner-confirmed installation, GPS, push receipt and ordinary customer ordering are not reopened. Event implementation/acceptance remains with the other chat and its latest evidence. Deferred marketplace/subscription, group ticket buying and official ticket transfer are not silently enabled. No new periodic service/job, existing-price edit or retained production test fixture was introduced by this request.
