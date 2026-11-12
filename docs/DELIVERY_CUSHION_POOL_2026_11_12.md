# Delivery cushion pool — implementation record, 12 November 2026

## Price rule confirmed with the owner

The cushion is **included in the selling price**. A ₦3,500 menu price and ₦500 cushion charges the student ₦3,500, internally allocating ₦3,000 to the meal and ₦500 to delivery support. Setting the cushion does not increase a price. The cushion cannot exceed its item's selling price. The same rule covers checkout extras/add-ons and priced combo choices.

No existing selling price, order amount, wallet balance or automatic-funding plan is updated by this work. Automatic-funding SQL was separately checked; the owner reconfirmed customer-paid Paystack fees. See [that verification](WALLET_FUNDING_SQL_CHECK_2026_11_12.md).

## Stage 1 — applied and verified

The compatibility API was deployed first as `e3bdab7`, with **1,586 backend tests passing**, before changing database column access. It expands browser-scoped wildcard reads and write receipts into their existing public columns, including nested relationships. Service-role accounting reads remain unchanged. Non-admin API responses strip internal cushion fields recursively.

Migration `20261112132141_delivery_cushion_snapshots.sql` adds zero-default internal amounts to menu items, add-ons and priced variation options, plus immutable order-item/add-on snapshots. There is no separate food checkout-bundle table: bundle-style checkout extras use menu_addons; HP bundles are unrelated and unchanged. SQL triggers derive snapshots from the server catalogue, not submitted client amounts. Positive priced combo-choice cushions join the main line; selected add-ons keep separate per-unit snapshots. Grouped add-on quantities multiply by their parent meal quantity. A zero-price physical reward does not generate cushion income.

Existing snapshots remain zero. Later catalogue edits do not rewrite them. Browser roles retain their old public column privileges while the new fields are denied, including through direct Supabase REST, not merely hidden in the UI. Role/campus RLS remains in place.

The migration/diff was shown before applying and is saved under its actual production history version. Both local and production rollback matrices pass inclusive-price preservation, trusted snapshots, combo/bundle/add-on quantities, reward-zero handling, snapshot immutability and private-column permissions. The production fixture was corrected to supply the required guest identity before its final successful run; no fixture data remained. Actual anonymous REST checks returned 200 for ordinary item names/prices and denied private-column/wildcard reads; the public menu API still returned 200 with 15 items and no cushion fields.

## Next stages

2. Derived ledger and reversal/movement history; existing paid order data may be copied into separate bookkeeping rows with historical cushion zero and unknown rider cost. Original orders remain untouched.
3. Admin-only cost/trip entry and menu cushion controls, with scoped authorization, precise split arithmetic, editing history and retry safety.
4. Pool totals, per-gate breakdown, balance trend and CSV.
5. A private configurable per-campus floor and an admin warning. Negative pool balances are permitted.

This record is updated as each stage is verified. Stage 1 alone is not a completed pool dashboard or cost-entry workflow.
