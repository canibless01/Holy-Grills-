# Group event tickets — 23 November 2026

Implemented on the event detail page: **Book for a group**, including a single friend or 2–10 attendees. The purchaser supplies their contact information, each attendee's contact details, ticket tier and required answers, then reviews one booking. Members can use wallet/card/split; guests use card. Free bookings confirm immediately. Card bookings issue entry credentials only after payment verification. The purchaser receives a private recovery link; every confirmed attendee receives their own ticket email/QR and checks in independently.

## Registration questions

Admin and organizer editors use the existing event question schema. Individual and group registration share the same input renderer. Supported responses: short text, long text, dropdown, radio, multiple choice, checkbox, date, email and number. Required answers and response types are validated in the browser and backend. Group answers are independent per attendee, including radio-button selection. A changed question schema returns actionable errors and refreshes the form without discarding existing answers. Existing organizer attendance/details/export consume the same ticket answers; no second questionnaire storage was introduced.

## Money, identity and recovery

- One atomic booking/payment with individual ticket records and capacity reservations. Failure rolls back the whole group; network retry reuses its original request key and fingerprint. The saved recovery attempt survives a reload in the same tab.
- Full cash ticket pricing; eligible promo is applied through the existing reservation path. HP spending/discounts remain an individual-registration feature. Each verified attendee earns their own check-in HP, once. The purchaser does not collect others' attendance HP. Shared HP pooling/spending remains deferred.
- One wallet debit for the group; each child records its allocated wallet/card share. Card receipts use individual positive amounts, with no duplicate aggregate receipt and no zero-value card receipt. The provider reference is owned by the group; a metadata-less bank-payment webhook cannot turn it into wallet funding.
- Guest tickets continue to link only through verified attendee identity. Guest purchaser access/refund ownership is separate. A ticket identifier or email address alone does not authorize purchaser access. Purchaser links are signed and private.
- Admin/support refunds retain the existing wallet-only policy. Money returns to the purchaser, including when another attendee owns/checks in with the ticket. A guest purchaser must verify/link their own account before claiming a wallet refund; an attendee cannot claim the purchaser's money. There is no customer ticket-refund action.
- Expiry restores wallet allocations once. Late card settlement refunds the newly received money once without reviving expired entry rights. Existing tier settlement amounts and organizer reporting remain per ticket.
- Individual and purchaser emails use the existing durable transactional outbox, retry/uncertain-send boundary and provider quota/fallback handling. No new scheduler or provider was added.

## Database

Applied once to Supabase Test Two: `20261123025332_event_group_bookings.sql`. One private parent table, one ticket association column and required indexes; existing individual ticket/question/refund tables reused. New functions are invoker functions, executable by service role only. Parent table RLS enabled; anonymous/authenticated direct access denied. Guarded replacements preserve existing financial-helper signatures/grants. Migration inventory contains one entry; test groups remaining after live verification: zero.

## Verification

- **2,006 backend tests passed**; frontend typecheck, lint and complete production build passed.
- **14 native Chromium cases passed** at 393px and 1280px: member wallet, guest card, split, timeout/reload recovery, settlement race, a free ticket for one friend, and changed registration questions. All nine response types were exercised per attendee; no horizontal overflow or browser errors in the controlled cases.
- Existing individual guest registration and admin question editor native regressions passed at both sizes.
- Actual SQL lifecycle passed on Test Two in a full rollback transaction: wallet/card/split, capacity/duplicate/price rollback, private recipients, financial allocations, individual check-in/HP, organizer settlement, guest account linking/refund ownership, expiry and late-payment conservation. Temporary outbox rows were never committed or exposed to workers.
- Disposable PostgreSQL concurrency: eight identical requests yielded one group/two tickets/one debit; eight confirmations yielded allocated receipts and exactly one purchaser receipt plus two attendee emails; competing two-person groups at capacity three admitted only one complete group. Local baseline was refreshed with reviewed live financial/auth/admission definitions; this is deliberately not described as a full production clone.
- Fresh migration application from original reviewed financial functions and absent group schema passed before applying live. Live grants/RLS/signatures checked after application.

Browser API/payment responses were controlled; no real gateway charge or customer email was sent. A real group payment and receipt-inbox observation remain operational acceptance, using the deployed code and configured providers. Passing these tests does not certify every provider/network condition.
