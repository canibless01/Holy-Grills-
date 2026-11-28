# University, campus and store fulfilment — 23 November 2026

This is the reviewed implementation design, **not a claim that multi-store routing is ready to activate**. Updated to preserve the owner’s campus-wide menu, price, stock, capacity and schedule rules. See `MULTI_STORE_IMPLEMENTATION_2026_11_23.md` for the current implementation and verification state. Current source and Test Two schema were inspected. Existing store pickup and automatic preparation are implemented behind their existing flags; neither is enabled by this design.

## Initial findings before implementation

- `campuses` has identity, active/default flags and coordinates, but no university parent.
- Profiles, menus, delivery zones, ordering windows, kitchen capacity and batches are campus-scoped. No `store_id` exists on the reviewed order/window/batch records.
- `app/services/store_pickup.py` reads one validated `store_pickup_location` object from campus settings. Its database guard snapshots and checks that one campus pickup address. Adding more addresses to that setting alone cannot route independent stores.
- `automatic_preparation.py` scans paid, due-day orders after their campus ordering-window cutoff, using the existing status transition path.
- The authorization middleware deliberately pins ordinary users and campus staff to their assigned campus. Globally replacing that rule with a browser-selected campus would also affect administrative/community/event permissions.

## Recommended hierarchy

University → physical campus → store. A university can have several distant campuses; a campus can have several stores. Each store belongs to exactly one campus. All stores in a campus share its menu, prices, promotions, stock, capacity and ordering/delivery windows. A campus admin sees all stores in their campus, with an All stores filter. Kitchen staff see their assigned stores. Riders see authorized store work and their assigned deliveries; a store picker alone does not grant access to other orders.

Keep the customer's academic/home campus on their profile. Store the current ordering campus/store preference separately. At checkout, show and confirm the fulfilment campus and store; visiting a different campus must not require changing the person's department, university identity, leaderboard membership or staff permissions.

## Customer flow

1. Registration selects university and academic campus, then the existing school/department fields. Existing FUTA accounts keep their current campus and academic data.
2. The menu shows the current ordering campus. Customers can change it before building an order. A single campus/store defaults automatically; multiple choices are presented only when needed.
3. For pickup, choose an open store and show its address, directions and collection instructions. For delivery, validate that the selected address belongs to the operating campus/service area and route to a serving store. Proximity is considered only among eligible stores, rather than selecting an unsupported store because it is geographically closest.
4. The existing campus menu, prices/promos, capacity and available date/window remain authoritative. The existing hostel/gate delivery tariff is retained; store choice determines fulfilment origin and routing, not a second price list. Context changes revalidate the cart and require the customer to accept changes; they cannot silently move a paid order.
5. Persist the store ID and fulfilment/address/configuration snapshots on the order. The receipt, tracking, kitchen, pickup desk, rider and notifications all read that same order context.
6. Retain the current received → preparing → ready flow. Pickup completes with staff-confirmed collection, without a rider. Delivery continues through assignment and delivery. Existing auto-preparation runs after the shared **campus** cutoff and only for paid orders due that day.

## Smallest coherent data changes

Check existing objects again immediately before migration. Reuse existing ordering/delivery/menu tables rather than duplicating the ecosystem.

- University parent reference and a parent link on existing campuses.
- A stores table with campus, name, active state, address, validated coordinates, pickup/delivery capability and instructions. Reuse the existing campus pickup object to backfill one default store, only where it is configured.
- Store staff memberships, with server-checked role and same-campus boundaries. Do not use the customer's selected store as staff authorization.
- Store associations on orders and delivery batches. Reuse the existing campus schedules, capacity, settings and rollover resolution without store overrides.
- Retain the campus menu/availability and inventory model. Do not create store-specific menus, stock ledgers or separate configuration for the shared campus schedule.

Orders and batches must enforce store/campus consistency in the database. New financial/assignment helpers remain backend-only; browser access follows existing role/RLS policy. No extra wallet or loyalty ledger is required. Academic recognition stays tied to the member identity; order earnings and eligible promotions use the explicit fulfilment scope according to existing earning rules.

## Operations and scheduling

- Batch identity includes store + service date + window + zone/gate. Two stores must not accidentally share a kitchen or rider batch. Their admitted orders consume the same campus capacity, as explicitly requested.
- Capacity exhaustion searches the campus’s next eligible window while retaining the chosen store. Moving an order to another store requires explicit consent or an authorized, audited reassignment that rechecks availability, fee, capacity and customer communication.
- Campus admins can filter orders, capacity and performance by store or inspect the campus aggregate. Kitchen bulk actions cannot cross unauthorized stores. Rider assignment checks store eligibility, and reassignment/splitting preserves each order's store and fee snapshots.
- Keep one shared hourly auto-preparation scan. Iterate the shared campus windows; do not create a separate scheduler per store. Hourly scanning can begin preparation up to approximately an hour after a non-hourly cutoff; the UI must not promise instantaneous preparation at cutoff.
- Historic paid orders must preserve their original fulfilment address and ownership. Avoid inventing a historic store where there is insufficient evidence.

## Delivery sequence and acceptance

Implement as a gated vertical slice with an initially disabled multi-store flag, preserving current single-store checkout until enabled:

1. Migration/backfill + store configuration/role membership + database guards.
2. Explicit customer fulfilment context + menu/cart/fee/capacity quote + atomic order snapshot/admission.
3. Admin/kitchen/rider store views, pickup confirmation and store-aware schedules/batches/notifications.
4. End-to-end tests before enabling: two stores in one campus and one in another; cross-store/campus role denial; shared campus stock/capacity and independent store batches; closure/rollover; payment timeout/replay; pickup/delivery/refund/HP; window auto-preparation; saved-address/cart context changes; existing single-store regression.

A store-list CRUD screen alone does not complete this capability. The routing, financial, capacity and authorization loop must ship together behind the flag. The initial discovery changed no data. Subsequent configuration/attribution migrations are recorded in the implementation status document; operational release remains disabled.
