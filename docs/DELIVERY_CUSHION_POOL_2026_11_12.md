# Delivery cushion pool — implementation record, 12 November 2026

## Price rule confirmed with the owner

The cushion is **included in the selling price**. A ₦3,500 menu price and ₦500 cushion charges the student ₦3,500, internally allocating ₦3,000 to the meal and ₦500 to delivery support. Setting the cushion does not increase a price. The cushion cannot exceed its item's selling price. The same rule covers checkout extras/add-ons and priced combo choices.

No existing selling price, order amount, wallet balance or automatic-funding plan is updated by this work. Automatic-funding SQL was separately checked; the owner reconfirmed customer-paid Paystack fees. See [that verification](WALLET_FUNDING_SQL_CHECK_2026_11_12.md).

## Stage 1 — applied and verified

The compatibility API was deployed first as `e3bdab7`, with **1,586 backend tests passing**, before changing database column access. It expands browser-scoped wildcard reads and write receipts into their existing public columns, including nested relationships. Service-role accounting reads remain unchanged. Non-admin API responses strip internal cushion fields recursively.

Migration `20261112132141_delivery_cushion_snapshots.sql` adds zero-default internal amounts to menu items, add-ons and priced variation options, plus immutable order-item/add-on snapshots. There is no separate food checkout-bundle table: bundle-style checkout extras use menu_addons; HP bundles are unrelated and unchanged. SQL triggers derive snapshots from the server catalogue, not submitted client amounts. Positive priced combo-choice cushions join the main line; selected add-ons keep separate per-unit snapshots. Grouped add-on quantities multiply by their parent meal quantity. A zero-price physical reward does not generate cushion income.

Existing snapshots remain zero. Later catalogue edits do not rewrite them. Browser roles retain their old public column privileges while the new fields are denied, including through direct Supabase REST, not merely hidden in the UI. Role/campus RLS remains in place.

The migration/diff was shown before applying and is saved under its actual production history version. Both local and production rollback matrices pass inclusive-price preservation, trusted snapshots, combo/bundle/add-on quantities, reward-zero handling, snapshot immutability and private-column permissions. The production fixture was corrected to supply the required guest identity before its final successful run; no fixture data remained. Actual anonymous REST checks returned 200 for ordinary item names/prices and denied private-column/wildcard reads; the public menu API still returned 200 with 15 items and no cushion fields.

## Stage 2 — applied and verified

Migration `20261112133732_delivery_subsidy_ledger.sql` creates the private one-row-per-order ledger and append-only movement history. It creates separate bookkeeping rows for existing real paid orders without updating those orders; historical cushion remains zero and rider cost remains unknown. Test orders are excluded. New wallet-paid checkouts are captured by a deferred trigger after their order lines exist, avoiding an empty snapshot when the order itself is inserted first.

Original contribution/fee amounts freeze at first capture. Discounts reduce cushion proportionately to actual food revenue. Recognized collections require paid/partially-refunded delivered orders. Partial refunds proportionately reduce those collections; full refunds/cancellations reverse them. Actual rider expense remains, including failed/unclaimed deliveries, so the pool may go negative. Unknown rider cost leaves net effect unreconciled rather than assuming the rider was free. Original customer delivery charges remain available separately from the recognized pool components.

Movement history records changes to reconciled net amounts, so a refund or later cost correction produces a delta instead of silently losing its reversal. Current ledger net and accumulated movement deltas conserve the same pool balance. The private trigger-only definer supports legitimate kitchen/rider status transitions without giving those roles access to accounting data.

Local and production BEGIN/ROLLBACK matrices pass deferred capture, authenticated kitchen preparation, valid ready/out-for-delivery/delivered transitions, untouched order totals, unknown-cost distinction, contribution/fee/rider arithmetic, discounted food, partial/full refund reversal, retained failed-delivery expense, hostel gate mapping, private permissions and movement conservation. No test order or actual rider payment was retained.

## Remaining stages completed below

The sections below record the cost-entry workflow, menu controls, dashboard, CSV and private warning-floor implementation.

## Stages 3–5 — applied; application verification and deployment

Stage 3 migration `20261112135830_delivery_cost_entries.sql` adds private cost entries, unique order allocations, idempotent request receipts and append-only edit history. The backend-only RPC validates the active actor's actual database role and campus. It locks orders before their ledger rows, matching automatic status accounting. A trip belongs to one campus and gate; a costed order cannot be assigned to another trip. Costs are non-negative amounts with at most two decimals. Division happens in integer kobo: ₦1,000 across three orders is ₦333.34 + ₦333.33 + ₦333.33, never a rounded ₦999.99. A repeated request returns its saved receipt; changed intent, overlapping trips and stale edits conflict. Costs may be recorded for delivered, failed/unclaimed or previously dispatched cancelled/refunded orders. The record does not issue a rider payment.

Stage 4 migration `20261112140516_delivery_pool_reporting.sql` supplies scoped current balances, WAT daily/weekly/monthly net changes, per-gate totals, a running balance chart and bounded CSV data. Customer delivery fees are shown independently of recognized pool collections. A missing rider cost remains unknown. The **reconciled balance** includes only orders with recorded costs; unreconciled order counts and collections are displayed separately, so unknown costs are never presented as free delivery. CSV exports use a chosen delivery-date range; chart changes use the date a movement was recorded, with an opening balance before the range. Later refunds/corrections remain visible in history. Exports above 10,000 rows fail explicitly rather than truncate silently.

Stage 5 migration `20261112140517_delivery_pool_budget.sql` adds a private per-campus in-app warning floor, default ₦0 until deliberately changed. It is not a new environment variable or scheduled task. Edits use version checks; all-campus super-admin warnings are evaluated per campus, so a positive campus cannot hide another campus's shortfall.

### Where to use it

- **Admin → Delivery Costs:** `/admin?section=deliverycosts`. Select the campus and date. Each order shows total paid/charged, the final customer delivery fee, its checkout cushion, recognized collections, actual rider cost and pool effect. Select uncosted orders within one gate for a trip, or use Record cost for one order. Edit trip cost edits its complete allocation; the history button retains earlier totals/notes/allocations and actor/time. Recorded expenses are separate from actual rider payout execution.
- **Admin → Menu Items:** create/edit now includes **Delivery cushion included (₦)** beside the selling price. Changing the cushion alone does not increase the selling price. Existing menu values are not populated automatically.
- **Admin → Addons & Variations / embedded modifier editor:** flat extras/bundle-style add-ons and individual priced combo choices have the same inclusive cushion controls. Existing option identities and cushion values are retained when other modifier fields are edited.
- **Admin → Orders:** the customer delivery fee is visible separately from the total.
- **Delivery Costs → Pool warning floor:** select a campus, enter the threshold and save. No deployment is needed to change this setting.

### The accounting loop

1. Enter a selling price of ₦3,500 and included cushion of ₦200. The customer still pays ₦3,500 for the meal.
2. If checkout charges ₦500 delivery, the paid order saves that fee and its immutable ₦200 cushion snapshot.
3. Once delivered, record the actual rider expense. A ₦600 expense leaves **₦200 + ₦500 − ₦600 = +₦100** for the pool. A ₦900 expense leaves **−₦200**.
4. Each reconciled order's result accumulates into the pool. **The pool balance can be negative; the rider expense is never a negative cost.** A negative pool is the delivery shortfall borne by Holy Grills. The warning floor does not block checkout or cost recording.
5. Cancelled/full-refunded orders reverse recognized collections but retain expenses already incurred. Partial refunds reduce recognized collections proportionately. Historical orders do not acquire invented cushions from today's menu.

### Verification

Local and production BEGIN/ROLLBACK matrices verify snapshots, unchanged selling/order prices, paid capture, exact trip splitting, retries, optimistic edit conflicts, duplicate-cost prevention, admin/campus permissions, append-only history, refunds, failed-delivery expense, negative balances, gate/period/chart conservation, CSV source amounts and floor editing. Production test fixtures are rolled back. No real provider charge, rider payment or customer notification is generated by these checks.

Native built-app browser cases cover mobile trip entry, desktop trip edit/history, uncertain-save replay with the exact same request, CSV formula protection/negative numeric values, floor editing, menu retail/cushion preservation, global add-on cushion editing and embedded combo cushion editing. The lazy admin section adds no new student-page initial fetch or runtime dependency.

Final application checks: **1,618 backend tests passed**, frontend typecheck and full client/SSR/prerender build passed, and all seven native browser cases passed against the final build. The production SQL matrix also passed with the first real cost save executed as `service_role` (not just the migration owner). Anonymous/authenticated callers cannot execute the report/budget/cost RPCs. Security advisors remain at the existing baseline (2 RLS-policy notices, 1 extension notice, 13 anonymous and 22 authenticated definer notices, 1 Auth configuration notice); none name the delivery feature. The counted audit cost accounts remaining after rollback: **0**.
