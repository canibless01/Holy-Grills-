# Instant reward redemption — 20 October 2026

Normal and flash HP redemption now create `fulfilled` entitlements inside their existing atomic stock/HP RPCs. This status means ready for delivery choice; it does not require an administrator. Existing legacy pending rows are not automatically promoted.

The server builds zero-price reward order lines from the entitlement and its reward definition. Menu rewards require an available campus menu item. Simple physical rewards use a named kitchen line with a nullable menu item. Explicit unavailable claims fail; unavailable automatic next-order rewards stay saved. The plan contains sorted claim UUIDs and is included in checkout quote validation.

The existing 38-argument `hg_create_order_atomic` locks the wallet before sorted entitlement rows, validates owner/campus/state and one zero-price line per claim, and attaches every claim before payment. All writes roll back on failure. Stock is reserved when HP is spent and is not decremented twice. Idempotent order replay resolves before claim checks. Existing `hg_refund_order_atomic` releases every entitlement attached to the cancelled order.

Delivery choice uses `IS NULL` predicates for unclaimed state and permits retries and changes until an order claims the reward. The delivery dialog uses the existing Radix portal, full viewport scrim, focus management, keyboard dismissal, and labelled title/description. Delivery address and pickup selection happen at checkout.

## Migration evidence

Canonical file: `holy-grills-backend/migrations/20261020143226_instant_reward_checkout.sql`.

SHA-256: `a5c7ce7780f06e77a3bc469dd20ffc9f9a062f81fafc7ce213da338000cdd437`.

Parent agent applied the migration to TestTwo (`zaxdkrmzyibkvlsrgmvq`). The first attempt failed compilation because a CASE expression inside a PL/pgSQL IF needed parentheses; its transaction rolled back. The corrected migration succeeded once, recorded as version `20261020143226`. Post-apply checks found one 38-argument order function, executable only by service role (plus owner), and normal/flash redemption executable by authenticated and service roles, never anonymous.

Raw table grants on `reward_redemptions` are broad, but RLS gives ordinary owners SELECT only and campus administrators ALL. No automatic-fulfillment INSERT trigger was added; readiness is written only in HP-debit RPC bodies. Existing function signatures and ACLs are retained.

## Local validation

- Seven new helper/delivery-choice regression tests pass, including foreign/used/pending/cross-campus rejection, nullable simple reward lines, unavailable automatic reward preservation, sorted/deduplicated claims, and lost-response delivery-choice retry.
- Thirty-five combined reward, checkout quote, and atomic refund route tests pass.
- Frontend TypeScript validation passes.

Live isolated harness: `/workspace/work/ecosystem-audit/verify_instant_rewards.py`; it uses only the parent-owned AUDIT campus/user/menu fixtures and newly journaled AUDIT reward rows. Its private journal prevents blind replay after a partial run. This agent's first invocation stopped at authentication because its shell lacked network permission, before any mutation; the parent agent runs it with the existing network grant. Results are recorded separately after completion.

## Scope and remaining semantics

Already redeemed entitlements currently resolve the reward's current definition, so a later administrator edit changes the future fulfillment line. No immutable reward snapshot column was introduced. Existing pending redemptions retain their prior workflow.
