# Remaining ecosystem work — 21 October 2026

This is the outstanding checklist, including explicit user requests and the broader A–Z audit. An inventoried page or a “safe to test” designation is not a completed interaction test. Each closure needs its actual layer of evidence: service, transaction, browser or external provider. The chronological progress log also records completed fixes; it is not a list of unresolved defects.

## Current priority: storefront and returning sessions

- Render every persisted storefront channel: multiple independent How It's Made and What's Inside cards; story, catering, promotions, reviews, share templates, flyers and tier icons. Confirm section-specific inputs, ordering/visibility, image-only/text modes, independent copy/destinations and mobile layout.
- Finish image-only 4:1 menu banners and admin design guidance. Loading must not add a secondary headline or overlay. Same-title cards must coexist and response-loss retries must not create duplicates.
- Global social-link form/footer/Contact Us: implemented and controlled browser checks passed; links hide when blank. Keep global socials distinct from campus WhatsApp.
- Returning session: refresh races, profile outage/retry and deferred welcome recovery passed; finish header loading, restored-user login redirect and campus-gate browser cases. Measure deployed signed-in versus guest loading separately.
- Real Cloudinary upload/served artwork remains provider-gated here. Trusted URL persistence does not prove an asset exists. All images remain Cloudinary-owned.

## Delivery, checkout and money

- Automatic campus/gate/window ready-order groups: finish multi-campus bulk/concurrency and assignment-race proof. Manual create/reassign/split/cancel transaction and admin UI cases already pass.
- Complete native kitchen preparation → ready group → assignment → rider pickup → delivery, including partial batch splits, attempted delivery/unclaimed resolution and assigned-rider-only ticket access.
- Prove final food/add-on HP payout, physical rewards and delivery summaries at handover. Synthetic paid-order history is not payment/delivery evidence.
- Native off-campus map/pin, nearest-gate, gate-only fallback, unknown-location/radius and address/window receipt combinations for guests and accounts.
- Real Paystack card/split/funding transactions, cancellation/redirect/reload/webhook response loss and reconciliation. Saved unpaid orders must remain unfulfillable.
- Discount/promo/order-lock/free-side/reward stacking; refunds after preparation, partial refunds, benefit restoration and fulfillment boundaries. Check wallet/HP conservation under competing actions.

## Rewards and promotions

- Native automatic redemption → deliver now with fee checkout or attach to next paid order → kitchen/rider handover. Explicit selection and fee-only checkout have evidence; full physical fulfillment remains.
- Immutable earned reward snapshots after admin edits; individually verified legacy pending redemptions and historical multiplier reconciliation.
- Signup credit grant/scope/replay/concurrency pass. Native selection/consumption on a paid order remains.
- General time-based multi-benefit campaigns and corresponding homepage promotion artwork. This is separate from signup welcome credits; exclusive spins stay exclusive.
- Live challenge creation/display/completion/claim, milestones and badge-free rewards/streak pages. Complete recipient suggestions, transfer eligibility and admin-grant loops.
- Real-device install → push permission → bonus claim progression, permission denial and exact-once bonus.
- HP multiplier/flash release flags, scheduler generation, advance staff notices, user blasts and disabled-at-launch behavior. Wiring alone does not prove workers run.
- Graduation eligibility/atomic claim/browser races pass; wider calendar operational scheduling and actual notification delivery remain.

## Events, guests and accounts

- Atomic event admission plus active HP/month counter/tier/snapshot recovery: repeated/concurrent scans, lost response, zero reward and historical receipts. The existing checkpoint is investigation until implementation/proofs are recorded.
- Preserve door/ticket/owner/campus/payment guards. Guest account linking must not use arbitrary email matching.
- Guest direct-route campus enforcement, tracking/QR ownership, guest-to-account conversion with cart/unresolved checkout and staff-role exclusions.
- Real public verification/recovery email, inactive account/session revocation and full role/browser lifecycle matrix. Auth-admin fixtures bypass email verification.

## Administrative and operational A–Z coverage

- Complete inventoried admin, super-admin, kitchen and rider pages button by button: empty/read failures, every relevant input, save/reload/customer reflection, delete/cancel, global creation, campus isolation and competing edits.
- Remaining reporting, CSV, analytics, subscriptions, marketplace and event cases from Workstream B's evidence matrix. Published subsets do not close the whole workstream.
- Notification deep links/cart nudges, blast restart/cancel, durable dispatch, worker outages, retention/scheduled tasks and actual provider delivery.
- Historical Supabase advisor findings outside each verified migration's grants; overloads, duplicate triggers/policies, RLS and financial writes. Reuse existing tables.
- Deployed backend activation/health, Redis/worker and provider configuration. GitHub push does not prove backend deployment health.

## Deferred by the user

Database cleanup is paused. Preserve real menu, rewards, reviews and storefront content. Private fixture inventories do not justify deleting uncertain data. The uploaded UI skills folder remains deferred.

See [short status](AUDIT_STATUS.md), [provider gates](PROVIDER_VERIFICATION_BLOCKERS.md) and [B matrix](WORKSTREAM_B_EVIDENCE_MATRIX.md) for completed work and exact limits.
