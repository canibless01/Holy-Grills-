# Ecosystem audit status

Updated 21 October 2026. This is the short status index. The longer [progress report](ECOSYSTEM_AUDIT_PROGRESS.md) records changes and evidence chronologically; an inventory or proposed test there is not a completed audit.

## Fixed and verified in published batches

- Wallet checkout intent replay, selected free-side claim and eligible cancellation: unit, transaction and owned browser evidence in the progress report.
- Explicit HP/delivery reward selection, save-for-later, reservation links, lost committed response followed by hard reload/recovery, cancellation and competing claims: [seven browser/API cases](CHECKOUT_REWARD_BROWSER_EVIDENCE.json). Native rider-delivery payout is not included in that evidence.
- Notification preference/channel reconciliation and operational request receipt deduplication: transaction/service and controlled browser evidence. Real provider delivery and durable dispatch recovery remain open.
- Workstream B's released platform subset: [evidence matrix](WORKSTREAM_B_EVIDENCE_MATRIX.md). Its remaining cases are not implied complete by that release.

## Current fixes and remaining verification — not a full release sign-off

| Area | Current work | Evidence still required |
|---|---|---|
| Checkout payment | Open card/split gateway directly after saving; retain honest unpaid recovery on setup failure | Native scheduled card/split and missing-provider fallback passed; actual Paystack test transaction remains open |
| Food HP | Include global add-ons; use discounted food spend excluding delivery; freeze new-order earning snapshot | Focused regressions and live admission/receipt passed; native delivered payout and stacking combinations remain |
| Delivery summary | Normalize persisted hostel/gate/address and actual delivery-window relation | Native on-campus/gate-only passed; nearest-gate/override/radius API passed; full native pin-address map remains |
| Reward redemption | Remove approval wait; deliver-now versus next-order attachment with one atomic claim | Automatic readiness, private grants, live replay/race/cancel and native fee-only checkout passed; native next-paid-order/rider handover, immutable snapshots and verified legacy pending rows remain |
| Delivery batches | Atomic assignment/reassignment/splitting and matching admin controls | Owned multi-order kitchen/admin/rider loops and concurrent operations |
| Storefront | Full unclipped flyer artwork; five display-page placements; compact What's Inside cards; section-specific inputs | Controlled section routing, multiple-item rendering, admin save/read-back and native layout passed; live CMS publication and each authenticated flyer route remain |
| Rewards interaction | Remove visual badges and stacked credit banner; install/push/claim actions; recipient suggestions; podium/spin readability | Seven controlled browser assertions and SDK outcomes passed; live challenge creation/claim, transfer/grant and real PWA/push remain |
| Graduation/promotions | Delivered-order/time/level eligibility; replace rigid hot-dog offer with configured benefits and signup free-side credit | Server enforcement, campus/global scope, atomic once-only awards, banner/toggle and calendar tests |

Checkout evidence for the current batch: [native/API results and provider limits](CHECKOUT_PAYMENT_DELIVERY_EVIDENCE.json).

Reward evidence for the current batch: [live transactions and native delivery-choice checkout](INSTANT_REDEMPTION_EVIDENCE.md).

## Still open across the full audit

- Full reward, discount, HP multiplier and refund/reversal combinations, including later preparation/partial refunds and physical reward fulfilment.
- Guest tracking/account linking and unresolved checkout during guest-to-account transitions; complete page/role action coverage.
- Fully atomic event admission plus HP/counter/snapshot recovery. The [event checkpoint](EVENT_HP_RECOVERY_CHECKPOINT.md) is investigation, not implementation.
- Remaining worker/retention, scheduled campaign, blast restart/cancel and notification deep-link/recovery cases.
- Actual Cloudinary, Paystack, email and push delivery checks: [provider gates](PROVIDER_VERIFICATION_BLOCKERS.md). Controlled recorders do not prove external provider success.
- Backend activation/health verification separately from GitHub/Vercel deployment; B's latest release recorded a Redis URL configuration error.
- Historical security-advisor findings outside each verified migration's explicit grants and scope.

## Evidence rules

“Fixed and verified” identifies the actual layer tested: unit, SQL transaction, native UI, or provider. A simulated provider stays labelled simulated. A migration must have one recorded application, expected function signatures and accurate grants. Only isolated, journaled audit fixtures may be changed or removed; the customer's current menu, rewards and reviews are not test fixtures.
