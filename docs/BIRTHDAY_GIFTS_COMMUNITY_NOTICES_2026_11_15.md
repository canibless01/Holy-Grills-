# Birthday outreach, gifts and community notices — 15 November 2026

Implemented and migrated alongside the earlier durable balance notices (`ba25038`). No existing balances, prices or customer history were rewritten. Production SQL acceptance uses fresh BEGIN/ROLLBACK fixtures; no customer blast or real payment was initiated.

## Behavior

- Existing birthday task runs daily at **08:00 WAT**. It queries only birthdays due today, with bounded batches, and records an annual per-person receipt. Birthday HP uses the campus/global system setting plus existing tier perk, and the existing `birthday_hp` flag. The annual receipt adopts an earlier birthday payment without paying again. HP, inbox and permitted provider outbox receipts commit together.
- New `birthday_celebrations` flag controls department announcements. Only active students on the same campus and same department receive them. Faculty alone is never sufficient. Notification preferences apply. Birthday links resolve a same-campus student celebrating today; public lookup does not expose phone or birth year. Birthday peer pushes expire at the end of the birthday in WAT.
- Existing monthly task runs **07:00 WAT on the 1st**. It queues a deduplicated report to that campus’s private operational-email recipients. The list contains name, day/month, faculty, department and registered phone, with a reminder to ask before sharing photos. `Monthly birthday outreach list` can be disabled in Operations email controls. No birth year is emailed. No new periodic job was added and no mid-month retrospective email was sent.
- Birthday wallet links prefill the friend and a birthday message. Cash and HP still follow their existing release/eligibility/minimum/balance/same-campus rules. No funds move without the sender’s explicit submission.
- Named gifts keep phone private by default. The sender may explicitly share their registered number, or send anonymously; these choices are mutually exclusive. The registered phone is snapshotted at sending, not looked up later. Anonymous recipient receipts, ledgers and notices mask sender identity; private service audit records retain accountability. A self-identifying gift message remains visible, as stated in the UI.
- HP gifts now have stable request IDs, atomic paired ledger movement and owned receipts. A lost response/reload reuses the original intent. A completed retry is readable before reapplying changed eligibility rules; changed amount, recipient, note or visibility conflicts instead of charging again. Existing cash transfer recovery keeps the same protections. Super-admin test isolation remains.
- Signed-out gift links retain their query through login/signup. Frontend privacy choices are shown only when the API advertises support, avoiding an anonymity promise from a new frontend paired with an old API.

## Copy review

Reviewed the 165-type central notification registry and 18 email templates. Updated 29 central messages plus source-specific review copy and three email passages. Referrals now welcome someone into the circle and distinguish signup from the actual payout. Corrected review HP being described as food HP, the unsupported birthday “30 days” claim and the preparation “won’t be long” promise. Existing interpolation fields in the 29 replacements were checked unchanged; precise amounts, deadlines and security/status messages remain precise. SQL-created gift/birthday/balance receipts use the same community voice.

## Evidence

- **1,849 backend tests passed after incorporating main**, including 25 new recovery, strict-input, consent, rendering and annual-processing cases.
- Frontend typecheck, lint and full production build passed. Browser checks at **393 px and 1280 px** exercise real gift components with a controlled API: birthday lookup retry/prefill, anonymous/contact choices, lost-response reload recovery with the same request, named/anonymous owned receipts, cash gift review/send and capability gating.
- Disposable local PostgreSQL: **12 simultaneous HP retries and 12 cash retries** create one paired movement each. Competing distinct HP transfers cannot overdraw; balances conserve. This found and fixed the missing-display-name notification failure. Native browser found and fixed the missing receipt-modal open flag.
- Fresh production rollback matrices pass for birthday grant/replay, same-department/campus boundaries, own and peer channels, monthly-report deduplication/contact payload, cash/HP anonymity, immutable contact, changed-intent rejection, ownership and conservation.
- Both migrations applied. Catalog verifies all six new RPCs are invokers executable only by service_role; new private table uses RLS. Security advisor adds no finding for this batch. Previously reviewed helper grants and managed extension/password-protection findings remain tracked in the database review.

## Operational limits

Saved outbox rows are durable; actual email/push receipt still depends on provider acceptance, preferences and device subscriptions. Immediate HP-gift wakes reuse the existing outbox; periodic recovery handles interrupted sends. Monthly report timing requires the deployed single beat scheduler and worker. These tests do not claim a real recipient inbox/device test or a real Paystack charge. The broader historical database/configuration inventory remains separate from this completed feature batch.

## Combined rollout follow-up

After rebasing the latest main, the combined backend suite passed **1,849 tests**; frontend typecheck and full build passed. Removed four unused AdminOrders imports exposed by the combined lint run; lint then passed. Expanded native cash birthday gifting also passes at both widths. `d65bdcf` received successful API, worker, single beat and Vercel deployment statuses; the public health response reports that revision with Redis/Supabase/Auth connected. Later normal scheduled execution remains an operational observation, not inferred from build success.

A small follow-up migration aligns birthday query role predicates with the new partial index. EXPLAIN confirms an indexed birthday lookup is available; fresh post-apply birthday rollback proof passes. Birthday race skips use `skipped_profiles`, so skipping one changed/deactivated profile does not mislabel a partly processed successful job as entirely skipped.

Final application follow-up `b453e5a` also reports successful API/worker/beat/Vercel deployment. Additional native signup regression passes at mobile/desktop widths for faculty/department catalogue search, campus-change clearing and postgraduate registration. Its controlled HTTP fixture now uses the current combined registration-options endpoint; no real Auth write occurred.
