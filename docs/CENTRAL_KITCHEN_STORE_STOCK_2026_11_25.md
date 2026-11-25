# Central kitchen and store supplies — 25 November 2026

The owner clarified the operating model: one central preparation kitchen per campus, with food sent to store counters. Ingredient inventory stays central. Store quantities are for consumables (containers, serviettes, cutlery, toothpicks and similar supplies) and prepared items explicitly marked for distribution. This supersedes the earlier suggestion of independent ingredient inventories or recipes at every store.

## Implemented

Reuse `stock_items` and `stock_ledger`. No second ingredient catalogue, inventory ledger or balance table was created. `stock_items.current_balance` remains the campus total. Store balances are the sum of that item's ledger entries for each store. Central available balance is campus total minus allocated store quantities, including quantities held by inactive stores. Existing historical balances remain central; nothing is allocated by guessing.

Admin → Store / Stock Tracking → Central kitchen & store supplies opens the allocation workspace. Receive purchases using the existing Ingredient Stock screen, mark only suitable items “Allocate this item to stores”, then transfer quantities from central to a store. The same controls support store-to-store transfers and returns to central. Each transfer has two linked ledger entries, preserves campus totals and does not record a second purchase or expense. Quantities use the item's existing usage unit.

Usage/waste subtract from both that store and the campus total. Admin signed corrections record a reason; kitchen staff may record usage/waste only at assigned stores. Kitchen staff cannot adjust central ingredients, transfer stock, change classification or view another store's balance. Admins retain campus oversight; super admins retain global access through a concrete campus selection.

All movement writes use a retained UUID replay key. A saved operation with a lost response is recovered by retrying the same intent. A changed payload cannot reuse it. The stock-item lock serializes both central and store mutations. Store underflow and central consumption of allocated stock are rejected. Classification cannot revert to central-only while any store has a nonzero balance, including through direct metadata updates. Archived records preserve their history and require restoration before new movements.

Migration applied once to Test Two: `20261125092041_store_consumable_allocation.sql`. The single public RPC is service-only; new columns retain existing RLS, with a restrictive store-read policy on ledger rows. No browser grants were opened. Review found no new store-related security-advisor warning.

## Verification

- 2,061 backend tests passed; new route tests reject invalid quantities/booleans, client actor spoofing and changed intents.
- Local PostgreSQL and actual Test Two rollback fixture `tests/sql/store_stock_allocation_rollback.sql` passed: two stores, central ingredient refusal, receipt conversion, transfer and usage replay, cross-store/campus denial, campus-less admin denial, underflow, source protection, corrections, returns, conservation and grants.
- Native Chromium: mobile and desktop admin allocation, controlled lost-response recovery, store usage, and assigned-kitchen controls passed. No live customer data was written by these browser tests.
- Native multi-store checkout: member mobile and guest desktop pickup, failed store-options recovery, changing between two stores, selected-store quote/order payload, wallet confirmation and controlled gateway handoff passed. These tests use controlled payment responses; they do not prove a real provider charge.
- Frontend typecheck/lint/message validation and client/server production builds passed. No new dependencies were installed.

## Scope decisions and related feature verification

| Area | Correct scope for this model |
| --- | --- |
| Ingredient catalogue, units, purchasing, preparation | Central campus kitchen; unchanged |
| Consumables/prepared-item allocations and usage | Per store; campus totals reconcile |
| Menus, prices, promotions | Campus-wide; unchanged |
| Opening hours, ordering/delivery windows, admission capacity | Campus-wide; one central production capacity |
| Order fulfilment address, pickup, rider origin, batches | Per store; immutable paid-order snapshots |
| Orders, refunds and sales reporting | Per store, campus aggregate, super-admin overview |
| Kitchen staff | Assign central staff to the stores they serve; All assigned stores combines their queue/prep view |
| Riders | Store membership plus actual delivery assignment; individual delivery confirmation |
| Store configuration, active state and pickup/delivery capabilities | Per store |
| Payment, wallet, HP identity and customer history | Account-owned; never duplicate by store |

This is physical quantity record keeping, not an automatic recipe-consumption engine. The original system records ingredient usage manually and has no order-to-ingredient recipe map. Orders do not automatically consume packaging or prepared-stock allocations, and the allocation ledger does not claim to provide checkout reservations or store-specific menu availability. Making those automatic would be separate work; the owner requested a limited extension, not an inventory overhaul. Purchase costs remain central; this report does not invent per-store cost-of-goods or profitability.

Multi-store ordering remains off until actual store locations and teams are configured and operational deployment acceptance is complete. The wider customer ordering-campus switch independent of academic identity is still separate from this within-campus implementation.
