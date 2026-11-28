# Ladies Hangout configuration and wallet check — 11 November 2026

## Live event updated

Existing event: `f55033e0-ca1b-46c4-9197-30c53758e359`.
Share: https://holygrills.online/events/ladies-hangout-2026-9841e

- Published; free admission; 300 total event places.
- Added active tiers: Free admission (₦0), Support — ₦500, Support — ₦1,000, Support — ₦5,000.
- Each support tier includes admission; support is optional. These are fixed prices, not an arbitrary-amount donation input.
- Recorded organizer settlement terms equal to each tier's full price, as explicitly requested. No automatic bank payout was made. The event is still owned by the existing super-admin creator account; no external organizer account was assigned or impersonated.
- Replaced the description with the supplied ARISE copy, paragraph spacing and WhatsApp community URL. Existing image, date/time, campus, owner, capacity and 100 HP check-in reward were preserved.
- The existing booking was preserved. No extra registration questions were supplied, so the default name/email/phone form remains.
- A Supabase BEGIN/ROLLBACK test registered a fresh synthetic guest against each actual tier: free admission required no payment; support reserved exactly ₦500/₦1,000/₦5,000 awaiting payment; organizer earning snapshots matched the full tier price. No Paystack request or real attendee email was made. Test tickets rolled back.

## Guest ownership and HP

Guests receive a ticket and account-creation prompt. A verified matching Auth email can link an unowned guest ticket before attendance. HP is awarded once at check-in to the linked account; this is not a cash credit to its wallet. Retroactive rewards for a guest who already checked in without an account remain excluded from automatic linking.

## Wallet verification

- 48 backend wallet-transfer tests passed, including complete email normalization and request identity.
- Real Supabase rollback acceptance passed: exact case-insensitive email and referral-code lookup; same-campus boundaries; paired balances/ledger conservation; response-loss replay; amount/limit/insufficient-funds/paused cases; receipts/private outbox and actual service-role access. All accounts and transactions were synthetic and rolled back.
- Native Chromium passed normal mobile/desktop transfers, uncertain retry/reload, denial, paused-feature receipt, email lookup, phone lookup and ambiguous phone cases, with controlled API responses.
- TypeScript and targeted ESLint passed (one existing unused eslint-disable warning).
- The current database intentionally isolates super-admin test wallets from ordinary-member wallets. Both parties must be on the same campus and active. Lookup accepts the complete email, phone or referral code, rather than partial-name suggestions.
- Added a visible super-admin notice to explain this isolation. The user's specific failed recipient has not been identified; the account-role clarification remains pending. No genuine wallet funds were moved.
