# Reporting reconciliation — 21 November 2026

Reconciles the remaining A2 current/historical attribution and populated panel contracts against the actual producing handlers. No database migration, customer write or financial-rule change.

## Corrections

Nine date-aware panels now receive the selected Lagos range: order timing, add-on acceptance, delivery locations, squads, demographics, payment methods, revenue, HP ecosystem and order sources. The headline HP request uses the same range. Existing late-response guards and isolated panel Retry remain.

Several populated responses were being treated as empty or zero because the charts expected speculative field names:

- Timing maps `day_of_week_distribution` and `hourly_distribution` to chart rows and derives peak labels from positive counts.
- Payments maps `counts`, preserving card, wallet, split and HP/free slices.
- Add-ons reads `attachment_rate` and `top_addons.quantity` and the reported top-add-on revenue.
- Delivery locations maps actual `locations` by delivery type to counts and hostel/gate names.
- Squads uses `avg_squad_group_size` and the actual squad/individual counts.
- Demographics maps department/faculty/academic-level names and `order_count`.
- Engagement displays its actual review/referral/check-in totals.
- HP tiers accept the API's `{tier,slug,count}` array and the legacy keyed map. Filtered zero slices retain the correct tier color; configured tier names are preserved.

Metrics not returned by the relevant producer (for example average add-ons, delivery-fee total on the location endpoint, squad revenue percentage and average wallet balance on the payment endpoint) show a dash. No truncated top-N result is used to fabricate an all-order average. Optional HP value/average fields are preserved when supplied and otherwise also show a dash.

## Period and attribution contract

The screen states which panels follow selected dates and which use independent all-time/cohort/academic windows. User CSV is explicitly a current snapshot. Tier economics groups dated activity by **current membership**, not a tier-at-purchase snapshot; guests/untiered accounts are outside those rows. Current active/pending/outstanding balances remain current when changing activity dates. No historical tiers were invented or backfilled.

A regression moves one member between tiers, reruns the same historical period, and confirms the dated activity moves between rows without changing total activity or underlying records. Another confirms an empty activity period does not erase current balances. Historical-at-event tier attribution would require a separate schema/product change and is not represented as an existing report.

## Verification

- `scripts/test-admin-report-contracts-browser.py`: populated actual response shapes across all three tabs, nine date-aware panel requests, all four CSV buttons/download contents, and an isolated payment-chart failure/Retry at **393 and 1280 pixels**. All HTTP is controlled; zero reporting writes.
- `tests/test_admin_reporting_contract.py`, `test_reporting_review_isolation.py`, `test_refund_reporting.py`: **30 passed**. Covers current tier movement, date/current-balance distinction, selected/global scope, user-ID chunking, refunds, all CSV families, formula safety and exact Lagos boundaries.
- Existing economics scope/race/recovery and analytics failure/CSV scripts remain complementary evidence.

Independent API reads/CSV page sweeps do not promise one atomic database snapshot under concurrent writes. This is an explicit consistency boundary, not a claim of untested synchronized totals.
