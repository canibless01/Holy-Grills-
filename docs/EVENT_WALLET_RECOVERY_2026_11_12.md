# Event payment and closed-loop refund recovery — 12 November 2026

New admin-approved event refunds stay in the app wallet. Members receive their ticket cash and spent HP through the existing atomic refund ledger. Guests get an `awaiting_account` wallet refund, not a bank-refund job. A matching, active, Auth-verified account claims the credit once through the wallet or My Events read; ownership and payment state update in the same transaction. Unverified/different emails cannot claim it. Existing approved provider refunds retain their original recovery path.

A verified card payment arriving after a reservation expired now returns only the newly received card amount to the member wallet, or reserves it for the guest's verified wallet. Expiry's earlier wallet/HP/promo/seat restoration is not repeated. The charge receipt and refund commit together. Duplicate callbacks return the original receipt. Unproven cancellation/expiry states still fail closed rather than reissuing entry.

Customers have no refund-request button. Admins retain the reason/confirmation/checked-in restrictions and see when a guest credit awaits account verification. Customer payment returns show refund status and an account-creation link, without claiming an entry ticket was issued.

Migration `20261112193223_event_wallet_refund_recovery` reuses existing private refund records and adds one state and one service-only invoker helper. It checks source function fingerprints, preserves existing provider obligations, and reasserts execute restrictions on changed financial helpers. It creates no table. A guest claim locks all selected events in stable order before wallet/profile locks.

Verification:

- Isolated real PostgreSQL: late member/guest charges, expired split-wallet restoration, duplicate callbacks, guest verification/credit replay, prior cancellation/refund matrices and legacy provider recovery.
- Supabase fresh BEGIN/ROLLBACK acceptance passed for the new member/guest recovery loop; no existing customer or real provider call was used. Helper grants verified: anon/authenticated denied; service role allowed; changed functions invoker.
- Full backend suite: 1,628 passed.
- Native Chromium mobile/desktop: reason/confirmation, checked-in restriction, response-loss identity, pending-account state, and legacy provider evidence/review forms passed. No production financial write from browser tests.
- TypeScript and targeted ESLint passed before final build.

This closes late-expired-payment and the guest refund policy gap. Guest attendance HP recovery, explicit ticket resend/recovery, configurable admission opening and the broader remaining security/action matrix are the next batch; they are not claimed complete here.
