# Instant reward redemption — 20 October 2026

Normal and flash HP redemption now create `fulfilled` entitlements inside their existing atomic stock/HP RPCs. This status means ready for delivery choice; it does not require an administrator. Existing legacy pending rows are not automatically promoted.

The server builds zero-price reward order lines from the entitlement and its reward definition. Rewards with an explicit `metadata.menu_item_id` require that available campus menu item. Standalone food and simple physical rewards use their own named kitchen line with a nullable menu item; `fulfillment_type=menu_item` is an economic category, not a required catalogue foreign key. Explicit unavailable claims fail; unavailable automatic next-order rewards stay saved. The plan contains sorted claim UUIDs and is included in checkout quote validation.

The existing 38-argument `hg_create_order_atomic` locks the wallet before sorted entitlement rows, validates owner/campus/state and one zero-price line per claim, and attaches every claim before payment. All writes roll back on failure. Stock is reserved when HP is spent and is not decremented twice. Idempotent order replay resolves before claim checks. Existing `hg_refund_order_atomic` releases every entitlement attached to the cancelled order.

Delivery choice uses `IS NULL` predicates for unclaimed state and permits retries and changes until an order claims the reward. The delivery dialog uses the existing Radix portal, full viewport scrim, focus management, keyboard dismissal, and labelled title/description. Delivery address and pickup selection happen at checkout.

## Migration evidence

Canonical file: `holy-grills-backend/migrations/20261020143226_instant_reward_checkout.sql`.

SHA-256: `a5c7ce7780f06e77a3bc469dd20ffc9f9a062f81fafc7ce213da338000cdd437`.

Parent agent applied the migration to TestTwo (`zaxdkrmzyibkvlsrgmvq`). The first attempt failed compilation because a CASE expression inside a PL/pgSQL IF needed parentheses; its transaction rolled back. The corrected migration succeeded once, recorded as version `20261020143226`. Post-apply checks found one 38-argument order function, executable only by service role (plus owner), and normal/flash redemption executable by authenticated and service roles, never anonymous.

Raw table grants on `reward_redemptions` are broad, but RLS gives ordinary owners SELECT only and campus administrators ALL. No automatic-fulfillment INSERT trigger was added; readiness is written only in HP-debit RPC bodies. Existing function signatures and ACLs are retained.

## Local validation

- Nine helper/delivery-choice regression tests pass, including foreign/used/pending/cross-campus rejection, nullable simple reward lines, unavailable automatic reward preservation, sorted/deduplicated claims, and lost-response delivery-choice retry.
- Thirty-five combined reward, checkout quote, and atomic refund route tests pass.
- Frontend TypeScript validation passes.

Live isolated harness: `/workspace/work/ecosystem-audit/verify_instant_rewards.py`; it uses only the parent-owned AUDIT campus/user/menu fixtures and newly journaled AUDIT reward rows. Its private journal prevents blind replay after a partial run. This agent's first invocation stopped at authentication because its shell lacked network permission, before any mutation; the parent agent runs it with the existing network grant. Results are recorded separately after completion.

## Scope and remaining semantics

Already redeemed entitlements currently resolve the reward's current definition, so a later administrator edit changes the future fulfillment line. No immutable reward snapshot column was introduced. Existing pending redemptions retain their prior workflow.


## Schema correction — 21 October 2026

Live testing found `rewards` has no `menu_item_id` column. Its existing `metadata` JSON supports an optional catalogue link, while standalone rewards have their own reserved stock and fulfillment name. The helper now reads that existing metadata, preserves unlinked food rewards, and rejects malformed explicit links while leaving unavailable automatic links saved. No new column or table is required.

The corrective migration replaces only the existing 38-argument create-order body: its only functional change is validation against `rewards.metadata.menu_item_id` instead of a nonexistent row field. The original applied migration remains unchanged as historical evidence. Parent applied the correction successfully once to TestTwo as `20261020235036_reward_metadata_menu_link` (canonical file uses that same server version). SHA-256: `12030f15b31a59a4e55c629d8ba2630a238cabda31582a49e7f343861ccc8adf`. The live harness results remain pending until its final output is verified.

The harness recovers the exact prior 100 HP audit funding ledger record without issuing another funding intent, checks simple/linked-menu/unlinked-food redemption and concurrent claim conservation, and cancels/refunds only its journaled orders in `finally`. HP funding/spend ledger entries remain intact for the separate identified-test-data cleanup.


## Integrated live and browser verification — 21 October 2026

The parent-run isolated Test Two harness passed six cases: simple physical, linked menu and unlinked food reward redemption each became ready immediately and admitted an order with safe replay; multiple next-order choices survived retry and rejected an invalid line without a debit; cancellation released all attached rewards and refunded once; three distinct competing checkout intents produced one winner, two refusals and one wallet debit. The journal's final refund cleanup restored the isolated wallet to 50,000. The prior 100 HP test grant was recovered from its exact ledger metadata rather than issued again. Audit HP funding/spend records are retained for identified fixture cleanup.

A native local browser used the actual frontend, backend and Supabase to open Redeemed → Choose delivery → Deliver now → checkout, select a hostel and wallet, and place a zero-food-price order with only the 250 delivery fee. Its existing paid cart survived unchanged. The saved order had one zero-price earned reward line. Cancellation released the entitlement and restored the wallet. The fixture ordering window was restored and the newly created cart row removed. This test used no simulated payment transport because payment was entirely from the isolated test wallet.

This flow found and fixed three additional boundaries: the POST route rejected an empty paid cart even with an explicit redemption; inactive catalogue RLS hid the earned reward's name; and the UI read `reward` while the API returned `rewards`. Empty ordinary carts remain rejected. Name hydration uses only public display fields and IDs from the authenticated owner's authorized redemption rows. The UI now labels readiness, links attached orders, and opens delivery choice directly after normal or flash redemption.

Eleven focused helper/history/admission tests and **66** combined checkout/payment/free-side/food-HP regressions passed. Frontend typecheck, message registry, lint, full client/SSR/prerender build and built-site smoke passed. Native add-to-next-paid-order, rider delivery of a physical reward, immutable entitlement snapshots and verified legacy pending-redemption reconciliation remain open.
