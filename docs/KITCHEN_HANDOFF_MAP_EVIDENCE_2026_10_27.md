# Kitchen handoff, preparation days and rider navigation — 27 October 2026

## Operational flow

Previously, kitchen marked orders ready, admin assigned/reassigned batches, and the assigned rider confirmed pickup and delivery. Pickup did not need another admin confirmation, but assignment still depended on admin access.

Kitchen now has a **Handoff** tab for its own campus. Paid, ready batches appear with customer names, item/customization quantities and rider selection. Kitchen can assign a whole staged batch or change its rider while it is still waiting. After physical handover the assigned rider presses Pickup in the rider screen. The order goes out for delivery; the rider then confirms delivery or an attempt. There is no extra admin approval or separate kitchen handover confirmation step. Admin retains split/cancel/payout management.

The new kitchen route accepts only `rider_id`, returns no payout fields and uses the existing service-only atomic batch function. The database independently verifies active kitchen role, campus, allowed fields, waiting status, due day, rider role/campus and locked membership. Kitchen cannot use this permission to create/split/cancel batches, change status/money, or administer another campus. Direct customer execution remains revoked.

## Preparation visibility

The old live queue used the precise `scheduled_for` clock, delaying an evening delivery order until evening. The separate Scheduled tab showed future/unpaid received orders and offered preparation. The consolidated prep list also lacked the due-day/payment filters.

The live queue and consolidated prep list now include only paid/partially-refunded active orders that are immediately ordered or scheduled before the end of the current Lagos day. Today's scheduled orders can be prepared before their delivery clock; overdue active work is retained. Future orders stay out of active preparation.

Scheduled defaults to today, with a preparation-date picker. A deliberately selected future date is a planning-only preview with preparation disabled. Backend and database guards independently refuse moving future/unknown-day scheduled orders into preparation/ready/dispatch states. Admin can still inspect future orders in the admin order list; the preparation guard is not an instruction to delete or cancel them.

Window counts now use each occurrence's delivery business date rather than accumulating every week sharing its UUID. Kitchen metrics use fulfillment-day membership and prefer actual preparation-start time for prep-duration measurements. Customer ordering capacity behavior is unchanged by these visibility fixes.

## Maps and delivery address

The rider endpoint fetched coordinates but omitted them from its response. Its browser normalizer dropped off-campus street/landmark details, and Navigate appended a hardcoded FUTA/Akure suffix. Coordinates and full saved address are now retained. Navigate opens directions to the exact valid saved pin; without a usable pin it uses the written address without inventing a campus/city. Missing destinations disable navigation. Calls retain their existing assigned-rider-only phone-link route.

The checkout map now measures container resizes/visibility changes and follows a campus center that arrives after initial rendering. Failed or stalled tiles show a reload action and gate/address/search/GPS alternatives. Stale place-search requests are aborted and cannot overwrite newer results. Actual external tile/geocoder availability and physical-device GPS accuracy remain distinct from controlled browser tests.

## Verification

- Actual Test Two rolled-back SQL: today's scheduled orders prepared before their delivery clock, future preparation refused, two same-day orders grouped, kitchen assigned their entire batch, and cancellation/status-field/cross-campus escalation refused. No fixture or role changes persisted. Reusable test: `holy-grills-backend/tests/sql/kitchen_handoff_and_due_day.sql`.
- Native mobile controlled-HTTP browser: future schedule preview cannot prepare; kitchen assigns rider through the new tab; rider Navigate opens the exact synthetic pin; blocked map tiles offer retry and GPS selection still works.
- Eight destination helper cases cover pin precedence, valid zero coordinates, string coordinates, invalid coordinates, address escaping and missing destinations.
- Backend regressions, frontend TypeScript, affected-component lint, message registry and production build pass. Existing lint warnings are not evidence of runtime failures.
- Applied `20261027102933_kitchen_handoff_and_preparation_day_guards` once. It replaces two existing functions, adds no table/column/trigger/overload, and preserves service-only execute grants. Advisors report no finding for the affected helpers.

This closes the described staffing/visibility/navigation gaps. Wider delivery exceptions, payout settlement, real map transport/device behavior and the remaining physical reward handover/refund matrix stay in the launch queue.
