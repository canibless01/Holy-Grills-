# Rider settlement records — 28 October 2026

Payment is external. The site records a completed batch's agreed amount and whether staff have paid it; it does not send a bank transfer. Admin copy and buttons now say this explicitly.

Fixed the admin's wrong earnings field (the RPC returns total_earned), completed-batch count, hidden fractional naira, blank price being accepted as zero, and a request failure leaving the roster loading indefinitely. Paid batches cannot open a price editor. Incomplete batches no longer show a payment-recording action.

Paid-state writes compare the amount observed by the admin route, so a concurrent price change is skipped for review rather than marking the changed amount paid. Undo compares the observed payment timestamp and cannot erase a newer payment. Pricing refuses cancellation that wins after the initial read. A skipped undo no longer reports success. These remain individual conditional writes under existing campus RLS; bulk requests may return updated/skipped/not_found per item.

Real Test Two SQL: rider and admin earnings agree; unpriced completed batches are counted separately; incomplete batches do not inflate earned amounts; marking paid updates paid/outstanding; replay cannot mark again; undo restores outstanding; rider cannot settle own work; another campus admin cannot read or settle it. Fixtures roll back, and no transfers occur. See tests/sql/rider_settlement_records.sql.

Controlled React browser proves displayed earnings/counts, external-payment explanation, blank price refusal, saved price/payment reflection and disabled paid-price edits. Five route tests cover duplicate IDs, replay, concurrent price/payment changes, stale undo, incomplete/unpriced batches and cancellation races. Backend suite: 702 passed. Typecheck, build and changed-component lint pass.

This closes the settlement-recording cases. Actual payment of riders is still an operational action outside the site. Wider delivery exception combinations and map/device acceptance remain in the launch checkpoint. No schema migration was needed.
