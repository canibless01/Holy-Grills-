# Launch audit checkpoint — 27 October 2026

User changes through `499d374` were merged first, preserving the admin selector/global-write fixes and the separate student checkout campus rule. Database cleanup and uploaded UI skills remain deferred.

## Completed this continuation

1. **Delivery batching:** fixed the reproduced cross-date grouping defect. Scheduled orders a week apart no longer share a run merely because the weekly delivery-window UUID matches. Added the actual delivery date to the existing batch record and corrected the unique index. Closed-window fulfillment, immediate orders without ordering-window associations, date boundaries, replay and manual refusal checks pass in actual Supabase transactions with all fixtures rolled back. Five native admin assignment/reassignment/split/cancel regressions pass. Details: [batch evidence](BATCH_DELIVERY_DATE_EVIDENCE_2026_10_27.md). Published as `fe523dc`.
2. **Promotion editing:** the editor previously sent immutable `code` in every PATCH, so backend validation rejected edits. Existing codes are now read-only and omitted from edits. Untouched campaign timestamps retain exact stored values; editable campaign times use Africa/Lagos rather than the browser timezone or midnight truncation. Admin campus changes reload the list and close stale editors; old responses are discarded, and read failures offer Retry. A native controlled-HTTP browser test covers successful edits, timestamp preservation and creation from a browser in New York. It does not create a real campaign or prove checkout discount consumption.

Backend suite after user merge: **566 passed**. Affected frontend TypeScript/lint and message-registry resolution pass; the registry still reports three existing fallback wording differences elsewhere.

## Remaining launch work, grouped by complete loops

- **Payments and ordering:** expand card/bank/split/funding return, retry, duplicate webhook, reconciliation, cart preservation and refund cases. Guest claim/tracking repairs already exist; this is final combination and interruption coverage, not an assertion that the flow is unbuilt.
- **Benefits and promotions:** complete the multi-gift/time-based campaign editor and grant path using implemented benefits, excluding exclusive spins. Signup onboarding currently exposes free-side credits only. Verify promo, discount, reward, HP and delivery-benefit stacking, eligibility, cancellation/release and refund accounting.
- **Earned physical rewards:** freeze each earned promise against later catalogue edits, then prove choose-now/next-order through kitchen/rider handover and failure/refund recovery. Existing instant entitlement and checkout claim paths are implemented; immutable reward-definition snapshots are not yet implemented.
- **Delivery operations:** expand outside-window/scheduled/inside-window lifecycle combinations, off-campus saved addresses/gates, exceptions, partial runs, completion and rider payout conservation. Date isolation and existing assignment/split/reassign/cancel tests above close only those cases. Historical mixed-date batches are preserved for explicit review.
- **Messaging and workers:** durable shared email quota/retry state, real push delivery and deep links, scheduled-task recovery, deploy/worker health and provider-specific proof. Existing provider fallback is implemented; durable dispatcher draft is not applied.
- **Storefront and accounts:** remaining rendering/returning-session measurements, role-scoped reads and writes, and the reported Chrome native install-menu absence on Android and desktop. User confirms actual Cloudinary uploads work; do not reopen that transport as broken.
- **Administrative coverage:** remaining input/save/reload/customer reflection, empty/error/race and campus-isolation cases tied to the above launch loops. Inventoried pages are not automatically signed off.

Events/marketplace, broader inventory/reporting/Part B cases and historical security-advisor findings remain in the broader ecosystem queue. Events are launch-gated. Real-device browser chrome, live-domain browser behavior and provider delivery must remain distinguishable from local/native controlled-response tests. No percentage is assigned without a stable denominator of executed cases.
