# Capacity rollover, delivery notifications and add-ons — 27 October 2026

## Preserved behavior and corrected gaps

The batch-date correction did not remove next-slot checkout or capacity move-up. These are separate operations: admission chooses a delivery date; paid ready orders later join a rider batch for that date.

When the selected day is full, checkout retains its existing confirmation of the next bookable slot. Accepting it schedules the order rather than exceeding today's limit. Slot search spans the existing 14-day horizon. Window and campus daily capacity now use the delivery business date, including advance bookings made on earlier days; tomorrow's booking does not consume today's capacity. Daily fullness now produces the same structured next-slot response as window fullness.

Increasing an ordering-window capacity fills its dated/recurring occurrences. Increasing the campus `daily_order_capacity` also fills effective windows in chronological date order, rather than filling a later weekday before an earlier available day. Both ceilings still apply: raising the daily limit cannot override a smaller window limit, and vice versa. A past/closed window is not reopened by increasing capacity.

The prior move-up loop counted orders from different dates, operated only on dated windows, did not serialize admissions, did not replace the delivery-window reference and attempted notifications only for registered users. A new service-only atomic helper now locks the same campus/day key used by order admission, counts that day's reservations, moves oldest eligible paid waiting orders, and updates ordering window, delivery window and scheduled instant together. Unpaid, already assigned/preparing, deliberately future or nondeferred orders remain. Effective overrides are checked by the route; the RPC also guards dated-window overrides and closed windows.

New deliberately scheduled orders are no longer tagged as capacity-deferred merely because the client accepted scheduling. Existing historical flags are preserved: the old representation cannot conclusively distinguish a deliberate future selection from a capacity fallback after the fact. No speculative historical rewrite or cleanup was performed.

Registered customers receive order-specific in-app/push/email dispatch requests; guests receive an updated-date email request. Move-up and capacity-deferred notices are transactional types, avoiding the marketing same-type throttle. Actual provider delivery and durable retry after an interrupted notification remain in the messaging audit queue. A failed notification does not undo a saved move.

## Delivery confirmation

Payment-confirmation notifications previously passed only the order ID into a template requiring delivery hours, producing dashes even when the receipt could resolve the window. Confirmation now reads the saved delivery-window reference and uses the actual scheduled/created business date. Timestamp-based legacy windows convert to Lagos time. If the saved configuration cannot be read, the message directs the user to tracking rather than inventing hours or displaying dashes.

## Add-on quantity counters

Menu item add-ons now have minus/count/plus controls. Price includes every selected unit, and both Add to Cart and Checkout send one `{addon_id, quantity}` entry per add-on. Required/minimum and combined group maximum limits remain enforced, alongside the backend's 50-unit per-add-on bound. To permit three coleslaws, configure that group's maximum to allow three units; this change does not bypass admin limits.

## Verification

- Applied `20261027094713_deferred_capacity_move_up_atomic` once, with one function signature and service-only execute rights; no new tables/columns or duplicate grants/triggers.
- Actual Test Two assertions passed for oldest-first/date-scoped capacity, repeating-window occurrences, independent daily ceiling, replay, updated delivery reference/hours, recurring move-up, dated closure, and exclusion of unpaid/deliberate future orders. All fixtures rolled back. Reusable SQL: `holy-grills-backend/tests/sql/deferred_capacity_move_up.sql`.
- Backend regression suite passed 573 tests before the additional daily-settings integration test; that added test and seven focused rollover/notification tests pass.
- Native mobile add-on browser test passed counters, combined maximum, decrement and deduplicated quantity payload. No real cart/order writes.
- Frontend typecheck, component lint (two existing warnings), message-key resolution and full production build passed. No actual payment/email/push was sent by these tests.

The broader multi-benefit gift campaign editor and immutable earned-reward promise/physical handover work remain open in the launch checkpoint.
