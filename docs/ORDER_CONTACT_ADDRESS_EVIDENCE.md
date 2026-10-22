# Order contact and saved delivery address — 22 October 2026

Checkout asks guests and signed-in customers to confirm a phone they can answer for offline calls. They may provide a different number for this delivery without changing their account. The confirmation is retained when the same attempt continues through scheduling, and the existing checkout intent/payment recovery remains authoritative. Phone confirmation is self-attestation with Nigerian mobile syntax validation, not OTP ownership verification or proof that the phone is reachable.

The normalized number is stored in the existing `orders.delivery_address_snapshot.contact_phone` JSON field. Rider secure-call reads that order snapshot first and preserves historical profile/guest fallbacks for older orders. An optional profile-read outage cannot block a rider from using a valid saved contact snapshot. No telephone call is made by the audit.

Off-campus final submission requires a human-readable street/junction/address, even when coordinates exist. Quotes still work before those details are complete. Checkout can save the address name, city, readable address, landmark, hostel/gate and coordinates through the existing address API. Selecting a saved address restores its gate ID, text and landmark even when it has no coordinates. The routed browser exposed an existing gate-ref-only restore bug that made saving that address fail; the actual selection state is now restored too. Editing the saved selection clears its binding; the server re-reads an owned saved address's canonical details and clears stale incoming coordinates when none were saved.

## Verification

- 48 focused backend executions passed, including the real checkout calculator's canonical address/contact RPC snapshot, readable-address refusal before an RPC, mobile-number validation, quote behavior and secure-call snapshot precedence. The quote fixture now includes a valid signup-required profile phone.
- TypeScript validation, owned Checkout ESLint and whitespace checks passed.
- Four actual backend/Supabase cases passed using the owned audit campus/student and native-kitchen actors: complete saved-address read-back; one real wallet-paid order with the alternate snapshot and unchanged profile; same-intent replay with one order/debit; assigned-rider GET secure-call returning the order's number. The journal retained the order, address and isolated scheduling fixtures. No cleanup or real customer edits occurred.
- Actual routed checkout browser proof is recorded separately in the private `order-contact-20261022` directory. Its API/payment responses are controlled fixtures; those UI results do not prove external Paystack settlement or a phone call.

No table, column, migration, provider or account-profile change is required. Real provider settlement and broader scheduled/split concurrency combinations remain separate verification.
