# Guest tracking and account claims — 21 October 2026

## Corrected behavior

Guest tracking accepts the displayed order number or full order UUID, plus its private tracking token. A successful lookup can be revisited from this device. The tracking page remains available without selecting a campus. Knowing another order number or an invalid token does not authorize a read.

Signing in does not discard a device-saved token for an order that is still a guest order. A student can view the guest order and explicitly link it. Once linking succeeds, only that guest reference and its URL token are removed; normal authenticated ownership reads replace them. Staff cannot claim customer orders. Pending payments remain token-accessible but cannot change ownership until settled, preserving the identity in existing payment-provider metadata.

`claim_guest_order(uuid,uuid,uuid)` now serializes the owner decision under a row lock, checks the fresh active student and matching campus, and is service-only. Two accounts competing for one guest order cannot overwrite each other. The verified owner's response-loss retry returns the saved success. A subsequent HP/account read failure cannot report a committed ownership change as failed; delivered paid orders can retry the existing idempotent reward-recovery pathway.

Automatic signup reconciliation now requires an actual confirmed Auth email matching the profile email, an active student, the same campus, and settled payment. A self-entered profile email alone cannot take another person's order. The existing signup trigger remains attached only to profile insertion: accounts whose campus is not populated at that instant use explicit tracking proof later. No backfill is performed.

Tracking read outages show a retry action and keep the last known rows instead of fabricating an empty account. Order-detail failures display an error with Retry. Stale requests cannot replace a different order or identity after navigation.

## Verification completed

- Thirteen focused HTTP tests passed: verified identity binding, staff exclusion, malformed JSON/token rejection, conflicts/campus/payment boundaries, own replay, private error handling, committed-claim reward recovery, displayed-number/UUID lookup, and refusal of wildcard or invalid proof.
- Frontend TypeScript and owned-file ESLint passed.
- Seven native browser/API cases passed against the actual frontend, local backend and Supabase Test Two: fresh-device number/code lookup; signed-in device proof; loss of a committed claim response and successful replay; pending-payment UI/API; wrong/postclaim guest-token denial; competing account claims; and denial of direct authenticated privileged RPC execution. [Deidentified results](GUEST_TRACKING_NATIVE_RESULTS.json).
- Native fixtures were three explicitly synthetic order rows and one confirmed audit Auth actor, all journaled privately and retained. They do not prove real payment-provider settlement, public signup email, or a kitchen/rider delivery.

## Migration history and access

The original migration is `20261021204846_serialize_verified_guest_order_claims.sql`. The forward revision `20261021204949_check_guest_claim_proof_before_payment_state.sql` checks the supplied token before reporting payment state. These are revisions of one live claim function, not duplicate overloads. The existing zero-argument signup reconciliation function is replaced. Both deny anonymous and authenticated direct execution and permit service role. No table, column, index, trigger or historical data backfill is introduced.

## Remaining limits

A complete delivered-guest → explicit claim → positive food-HP receipt/month-counter replay proof remains separate from these received-order ownership tests. Native payment-provider settlement and verification-email delivery are still provider checks. The analogous historical event-ticket email-only signup trigger is a separate open finding and is not repaired by this order migration. Broader guest cart/unresolved-checkout conversion combinations remain outside this bounded slice.
