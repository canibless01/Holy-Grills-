# Physical-store pickup — 22 November 2026

Pickup is implemented but remains **disabled**. Configure the campus address under **Admin → Delivery → Store pickup**, then enable the `store_pickup` feature flag when ready. No real collection address was invented. The production global flag is false and no campus pickup settings were created.

Paid pickup follows received → preparing → ready → collected. The persisted terminal status is the existing `delivered` status, retaining the existing completion/HP/reward recovery path; customer tracking labels it Collected. Kitchen staff or a campus admin confirm collection; no rider or delivery batch is involved. Existing on/off-campus delivery transitions and scheduling/capacity rules remain intact. Preparing is intentionally retained as serving/packing, including prepared food.

The server sets the zero delivery charge and authoritative campus collection address. Client delivery coordinates, saved delivery address, location ID and fee cannot replace it. A configured name/address and enabled campus/global release flag are required independently in both API admission and the database. Disabling admission does not strand an existing paid pickup. Mode switching, delivery fees, rider assignments and delivery batches are rejected by database guards. Future-day and unpaid orders cannot enter preparation. Delivery rewards with zero savings remain unspent.

## Evidence

- Native Chromium at 393/1280: release hidden, member wallet checkout, guest card gateway handoff, configured address/maps link, retained failed-save draft and identical retry, kitchen prepare/ready/cancel-confirm/collect controls, customer Collected tracking without rider stages; no body overflow. Controlled HTTP; no actual gateway charge or customer send.
- Targeted backend pickup tests: configuration validation, fail-closed release, authoritative campus fee, conserved quote/credit, committed checkout replay, unpaid/role/campus restrictions, collection replay and preparation-preserving admin walk.
- Real PostgreSQL: `tests/sql/store_pickup_rollback.sql` passed locally and on Test Two inside a complete rollback. Checks actual wallet admission/debit, repeated intent returning one order, retained delivery credit, future/unpaid preparation denial, kitchen collection while release is disabled, one collection state log, forbidden fee/mode/assignment, and unchanged ordinary delivery path.
- `tests/store_pickup_sessions.py`: disposable loopback PostgreSQL, two simultaneous collection requests, one compare-and-set transition and one HP credit; reward recovery replay adds no second credit. Fixtures deleted from the disposable database afterward.
- Migration `20261122153343_store_pickup_disabled.sql` is applied once in Test Two. Verified: one private trigger function, two distinct guards, no anon/authenticated execute, service-role execute, global flag false, zero pickup configuration rows. No new public data table or RPC overload.
- Frontend typecheck, component lint (zero errors; existing warnings), client/SSR/prerender build and central-message/brand checks passed. Backend suite and final revision are recorded in the completion update.

## Intentional content change

FUTA now has an active **Hot Dog** free-side option alongside Chips, added on 21 November by an idempotent existing-table insert. It reuses the existing Hot Dog Bun Cloudinary image. This is requested launch content, not disposable audit data. No menu/storefront content or customer data was removed.

## Separate follow-up

Automatic preparation when an ordering window closes is separate from pickup admission and must retain paid-only, due-day and campus checks. Existing hourly ordering/delivery windows remain usable; this change does not rewrite them or introduce another cron provider.
