# Event check-in HP recovery — implementation checkpoint

Status: **investigated, not implemented or verified**. Saved against main `cbdb1ca` on 15 October 2026 so the next session can continue without treating this area as complete. No event migration was applied, no event source changed, and no event fixtures or balances were modified by this investigation.

## Confirmed failure path

`holy-grills-backend/app/routes/events.py:checkin` inserts `event_checkins`, then separately calls `earn_pending_hp`. Any failure between those operations leaves an admission without its HP award. A retry finds the existing check-in and returns `TICKET_ALREADY_CHECKED_IN`, preventing recovery. Concurrent duplicate inserts are also returned as an error rather than an existing successful receipt.

`earn_pending_hp(source_type="event")` credits **active HP**, bypassing the monthly pending cap. It returns `added_to_pending: 0`; the route passes that zero to EventDetail, which displays “HP added to pending pool.” Both the success display and event reward description need to use the real active award. Do not change event HP into pending HP to match this incorrect copy.

The route currently resolves guest tickets by matching a profile email after admission. That lookup must not become a privileged email-only account-linking mechanism during this fix. Guest admission already requires the opaque ticket and protected door proof. Preserve those protections and explicitly design authenticated guest-ticket ownership before expanding linking.

## Existing schema and helpers to reuse

- Existing `event_checkins.hp_transaction_id` can link a successful award. Ticket metadata can hold an immutable admission/award snapshot, including completion for zero-HP or unlinked guest admission. No new table is justified yet.
- Existing `record_hp_transaction_atomic` locks the profile, records HP, updates active balance, and deduplicates the business key `(user_id, reference_type, reference_id)`. The current legacy event reference is `reference_type='event'`, `reference_id=event_id`.
- The helper returns `transaction_id` and `replayed`. Current `earn_pending_hp` discards that receipt and calls `increment_monthly_hp_tracker` even on a replay; a retry-only route patch could therefore inflate counters despite preserving the balance.
- `increment_monthly_hp_tracker` is an additive upsert. It must execute only once inside the admission transaction for a new award.
- Tier recalculation is currently a separate best-effort Python call. `hg_set_profile_tier_from_balance` exists and may be usable inside the new atomic boundary after verifying its triggers/locking.
- Existing event multiplier semantics apply only when multiplier > 1.0. Preserve the configured campus/global lookup and rounding deliberately; a reduction below 1 currently has no effect. Persist the effective amount so later configuration changes cannot alter a replay.
- The old event award does not explicitly assign expiry. Do not accidentally introduce the 12-month food/spin policy here without checking existing HP expiry/bucket triggers.

Private scratch baseline `/workspace/work/ecosystem-audit/event-hp-baseline.json` contains the inspected definitions of `record_hp_transaction_atomic`, `hg_add_hp_transaction`, and `increment_monthly_hp_tracker`. Re-read live definitions before migration; scratch files are not committed evidence or deployable migrations.

## Concrete next implementation

1. Inspect live columns, constraints and triggers for event tickets/check-ins, HP transactions, monthly counters and profile tiers. Especially read default remaining-amount, bucket-consumption, pending-ceiling and balance-reconciliation triggers before inserting HP rows. Inspect grants and all relevant RPC overloads.
2. Add one private service-role RPC wrapping admission, immutable reward snapshot, ledger receipt, monthly tracker and tier update in one transaction. Lock the ticket and attendee/profile in a consistent order. Revalidate event/ticket relationship, publication, event end, ticket expiry/status/payment, attendee campus and actor/staff scope inside the boundary. Preserve current guest door/ticket proof checks; do not accept client-supplied award amounts or an arbitrary target user.
3. Return a durable receipt: check-in ID, award transaction ID when present, actual active HP amount, completion state and replay flag. A lost response/repeated scan returns that receipt with no second admission, credit, tracker increment or milestone increment. Zero reward and an unlinked guest also need an explicit completed marker.
4. For historical check-ins missing a transaction link, first find the **existing legacy event ledger row** for the same attendee/event and link it without crediting again. Do not calculate a new amount from changed settings and assume a different-amount conflict is a missing grant. Historical tracker reconciliation is ambiguous if the old separate counter already ran: do not blindly add the counter again; document or individually reconcile this case.
5. Wire the route to the atomic contract. An existing check-in must reach recovery rather than the early duplicate rejection. Preserve unrelated ticket/door security and B's six already-applied migrations. Surface transaction failures honestly; do not return admission success with an uncertain award.
6. Wire EventDetail to explicit active-award receipt fields and central `messages.py` copy. Display replay/recovered results truthfully. Coordinate shared message generation with the checkout worker; do not overwrite concurrent registry changes.
7. Keep milestone side effects idempotent/recoverable separately. Calling `event_checkins += 1` on every replay would manufacture progress; simply skipping it on a replay could strand an interrupted trigger. Inspect milestone semantics and record a durable outcome before choosing a strategy.

Suggested RPC name/signature is intentionally not frozen until schema/trigger inspection. Deploy only after a complete SQL definition, grants and failure proof exist. Revoke execution from PUBLIC/anon/authenticated and grant only service_role; verify no alternate overload exposes the capability. Check migration history before applying and never replay the migration after an ambiguous tool response.

## Required evidence before marking complete

Use separate labelled fixtures, not existing A/B customer balances, and journal cleanup. Browser ports must differ from checkout's 5001/5174.

- Positive reward: native attendee scan → active HP, exact ledger link, one monthly counter increment, correct UI wording.
- Repeated scan, concurrent scans and committed-response loss/retry: one admission, one ledger award, one counter/milestone outcome, same durable receipt.
- Injected failure after admission/ledger work: all transactional changes roll back; retry succeeds once.
- Historical admitted/no-ledger case recovers; historical admitted/existing legacy ledger links without duplicate money/counter; changed reward amount does not overwrite history.
- Zero reward is completed and stays zero after configuration changes. Guest remains non-credited without legitimate account linking.
- Invalid/expired door token, wrong ticket/event, foreign owner/campus, unpublished/ended event, cancelled/unpaid/expired ticket, and non-staff calls cannot grant admission or HP. Authorized staff credits the attendee rather than staff.
- Correct active/pending/bucket/expiry/tier behavior and grants verified directly in Supabase Test Two (`zaxdkrmzyibkvlsrgmvq`). No duplicate tables/functions/migrations; clean up only owned fixtures and reconcile their balances from transaction evidence.
- Focused backend tests plus relevant existing platform-boundary regressions; frontend typecheck/build and native receipt display proof. Record actual evidence separately from planned cases.

Related contract request: [WORKSTREAM_A_DEPENDENCIES_FROM_B.md](WORKSTREAM_A_DEPENDENCIES_FROM_B.md). This checkpoint fulfills persistence of the investigation, **not** that acceptance request.
