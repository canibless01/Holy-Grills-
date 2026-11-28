# Group event tickets — 23 November 2026

Implemented on the event detail page: **Book for a group**, including a single friend or 2–10 attendees. The purchaser supplies their contact information, each recipient's email and ticket tier, then answers the organizer questions once for the booking and can add quantity/preference notes. Each ticket is sent to its recipient, then reviews one booking. Members can use wallet/card/split; guests use card. Free bookings confirm immediately. Card bookings issue entry credentials only after payment verification. The purchaser receives a private recovery link; every confirmed attendee receives their own ticket email/QR and checks in independently.

## Registration questions

Admin and organizer editors use the existing event question schema. Individual and group registration share the same input renderer. Supported responses: short text, long text, dropdown, radio, multiple choice, checkbox, date, email and number. Required answers and response types are validated in the browser and backend. The current group form collects one shared answer map. Organizer rows and CSV identify it as group answers from the purchaser and preserve the group notes; individual registration still collects individual answers. Older in-flight group requests with separate answers remain recoverable. A changed question schema returns actionable errors and refreshes the form without discarding existing answers. Existing organizer attendance/details/export consume the same ticket answers; no second questionnaire storage was introduced.

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

## Follow-up: simplified purchaser registration

At the owner's request, purchaser name/email/phone are entered once. Each recipient needs only their email and ticket tier. Their email identifies an unclaimed ticket; the system does not invent their name or copy the buyer's name onto a friend's ticket. Purchaser phone remains the booking contact. Organizer questions are answered once for the group, with optional notes such as “2 vegetarian and 3 regular meals.” These notes are recorded, displayed and exported as booking-level information; they do not automatically create meal quantities or individual dietary declarations. Required organizer question types remain validated.

Applied `20261123145439_event_group_shared_registration.sql` once, preserving the existing group helper signature and service-only grants. No extra table or duplicate helper was created. Updated SQL lifecycle including shared scope/notes passed on Test Two in a rollback transaction. Recovery fingerprints bind both shared answers and notes and retain compatibility with previous saved requests.

Follow-up verification: all 2,009 backend tests passed (including 48 targeted backend/question tests); frontend typecheck/lint and both client/server production builds passed. Native Chromium rerun was blocked before launch by the current environment's socket restrictions. The complete build command reached the canonical-origin browser check and stopped with an environment `esbuild EPERM`; the previous complete build/native passes above belong to the initial group implementation, not this follow-up. No actual payment or email was triggered by this work.

Multi-store discovery and the implementation plan are recorded separately in `MULTI_STORE_FULFILMENT_DESIGN_2026_11_23.md`. Multi-store fulfilment has not been deployed.
