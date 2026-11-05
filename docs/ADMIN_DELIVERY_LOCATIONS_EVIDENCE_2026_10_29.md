# Admin page audit: Delivery → Zones & Fees

Completed the listed gate/hostel controls, separately from delivery batches and the Delivery area radius/centre page.

## Fixes and executed loops

- Gate editor exposes name, target campus, base fee, per-kilometre rate, minimum fee, latitude and longitude. New entries have no example pin. Coordinates can be cleared explicitly as a pair; partial API coordinate edits preserve the other stored coordinate.
- Hostel editor exposes name, fee, target campus and a same-campus active-gate dropdown instead of a raw gate UUID. Changing the new-record campus clears the gate choice. Invalid money, incomplete coordinate pairs and unselected campus are refused. Zero fees remain an explicit supported configuration.
- Failed saves preserve entered fields and show the backend error. An immediate latch plus disabled fields prevents repeated Save requests. Name, scope and numeric values are sent as an explicit payload rather than a whole joined database row.
- Campus-admin controls remain scoped to their campus; super admins can choose any campus for new locations. Operational locations require a real campus. Existing records retain their campus when editing. Global/foreign edit controls are not offered to campus admins.
- Hostel deletion was already soft deactivation but its UI said “deleted” and had no restore path. It now says Hide, marks the row Hidden and offers Restore using the existing PATCH endpoint. Gates and hostels keep their IDs and historical order references when hidden.
- Public/admin location read failures return retryable errors instead of false empty lists. Mutation responses map database errors without exposing raw Postgres details; a duplicate returns an actionable 409. Updates and hide actions validate identifiers and scope before mutation.
- **Pricing fix:** without a pin, the previous shared calculator returned `min_fee` alone. A zero minimum could bypass a positive base fee. It now returns `max(base_fee, min_fee)`; pinned pricing remains base plus distance × rate, floored at the minimum. The actual checkout quote code uses this same function. Saved historical order totals remain unchanged.

## Database integrity

Existing rows/indexes/constraints/policies were inspected first. No duplicate normalized names or inconsistent hostel/gate campus links existed before applying:

1. `20261029102829_prevent_duplicate_delivery_location_names`: exactly one normalized campus/name unique index per existing gates/hostels table. Case and surrounding whitespace cannot create duplicates; the same name in different campuses remains valid. Hidden entries are restored rather than duplicated.
2. `20261029103528_enforce_hostel_gate_campus_links`: one security-invoker trigger helper and two triggers prevent a hostel linking to another campus's gate, and prevent moving a linked gate away from its hostel campus. The hostel trigger locks its gate FOR SHARE against a concurrent campus move. Existing RLS remains in force; no table, column or elevated definer function was added.

Actual introspection: one helper signature; security_definer=false; direct anon/authenticated execute=false, service_role=true; two intended triggers; two intended unique indexes. Authenticated normal trigger writes passed despite the helper not being a browser RPC. No advisor finding mentioned the new helper; unrelated prior advisories remain. Local filenames match the actual applied Supabase migration versions. No existing content, campus fee or coordinate was edited by this batch.

## Evidence and boundaries

- `scripts/test-admin-location-browser.py`: actual native page/modal with controlled HTTP; all fields, blank initial pin, coordinate validation/clear, failed-save retention, repeated Save suppression, gate choice scope, campus-admin/global controls, super-admin campus creation, gate/hostel edit/hide/restore and public list outcome, read failure and Retry. No production writes.
- `tests/test_admin_delivery_locations.py`: ten backend tests, including real shared fee arithmetic and the actual order quote path with controlled rows, clean failures, duplicate response, explicit permission/ID checks and existing restore API.
- Real Supabase `tests/sql/admin_delivery_location_loop.sql`: authenticated writes/fields, case/space duplicate refusal, independent campus names, cross-campus link refusal, linked-gate move refusal, hide/restore, student/foreign restrictions, super-admin superset, and unchanged historical order reference/fee/snapshot. All fixtures roll back; no payment or provider message.
- Full backend **760 passed**; frontend typecheck, changed-file lint and complete production build pass. UI double-click and database unique/locking mechanisms are verified; this is not a claim that every independent multi-connection race was physically reproduced.

**Next page: Delivery area.** Its campus centre/radius settings are separate from gate coordinates and location fees and have not received this native page sign-off. Actual West/South entrance-pin provenance and physical rider navigation remain separate acceptance work. No cleanup, external timer or hosting migration was run.
