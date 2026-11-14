# Store / ingredient stock controls — 4 November 2026

This is the first general-site audit batch after the owner assigned launch acceptance to another chat. Existing stock conversion/replay tests were reused; this batch covers the currently implemented native create/purchase/usage/ledger controls. It is not complete Store/Stock lifecycle or whole-admin sign-off.

## Findings fixed

- Stock data did not reload with the super-admin campus selector. The page now requires an explicit campus for a super-admin and remounts its workspace on campus changes; ordinary admins use their profile campus. Reads and creates carry that target. A late read for a previous campus cannot replace the new workspace, and modals cannot keep an old campus's item selected.
- Creation had no response-loss replay contract. The native form now reuses its request UUID as the new ingredient's existing primary key. Matching retries return the existing item/current balance; changed details with the same intent return conflict. A normalized unique campus/name index prevents a second ingredient with a case/whitespace variant. No idempotency table was added.
- The UI incorrectly rejected negative corrections, although the existing adjustment RPC supports them. Correction now accepts finite nonzero signed quantities; positive removes and negative adds usage units, with explanatory copy. Purchase/usage/waste remain positive. Cost, conversion, threshold, names and notes are validated. A blank optional purchase cost is retained as unknown, rather than inventing a free purchase. Decimal conversion uses exact decimal arithmetic for the numeric RPC; overflow is refused before transport. Same-tick writes are guarded and committed-response loss retains the original adjustment intent for retry.
- Opening the add form unnecessarily fetched measurement units again and could disguise failed reads as an empty configuration. It now uses the successfully loaded unit list from the page.
- A failed ledger read looked like empty history. It now exposes Retry. The native ledger uses bounded 50-row pages, stable created-at/id ordering and visible Previous/Next controls. Older unpaged API clients retain their response shape.
- Ledger quantities used a nonexistent `quantity` field and labelled every entry with the usage unit. The page now shows `quantity_entered` with that entry's actual unit, signed usage-unit balance change, purchase cost, human operator name and notes. Unneeded operator email is no longer selected by the endpoint.
- Raw authenticated stock-table permissions permitted balance or ledger mutation outside the private adjustment RPC. Ordinary clients can now create only zero-balance ingredients; table-level balance updates/deletion and all ledger writes are revoked. Authorized name/threshold metadata permissions remain under campus RLS. The existing actor-checked service-only adjustment RPC remains unchanged and functional.
- Stock adjustment endpoints now reject non-object JSON and invalid notes explicitly. Touched labels, validation and feedback use the central messages registry.

## Executed verification

- `scripts/test-admin-stock-browser.py`: real native React page in Chromium with controlled HTTP. Covers explicit super-admin campus, ordinary-admin own scope despite a stale foreign selector, delayed wrong-campus response, all create fields, invalid name/conversion/cost, immediate repeated clicks, omitted-cost handling, committed create and purchase response loss/retry, signed correction/waste/usage, correct unit/cost/change display, ledger Retry/pagination and failed stock-read Retry.
- `tests/test_admin_stock_controls.py`: **13** backend cases for create replay/conflict/concurrent winner, scoped creation, explicit foreign-campus denial, exact decimal conversion/overflow, validation, malformed adjustment input and bounded stable ledger pages.
- Complete integrated backend suite: **993 passed**. Frontend typecheck, lint, message-registry and full production build/prerender passed. The registry reports existing unrelated fallback-copy drift; all new keys resolve.
- Real Supabase `tests/sql/admin_ingredient_stock_controls.sql`: fresh Auth actors/campuses/items in a single rolled-back transaction. Checks normalized duplicate refusal, same name allowed in another campus, zero-balance creation, direct balance/ledger/delete refusal, name/threshold permissions, service-only adjustment grants, 5 purchase units → 10 usage units and exact 0.1 × 3 → 0.3, replay without duplicate ledger, signed correction/waste/usage conservation, overdraw refusal, foreign-campus refusal, student/kitchen/rider isolation and super-admin reads. Actual PostgREST also accepted the numeric-string transport in a deliberately NULL-item request refused before any write. No genuine profile, order or stock row was changed; no fixture persisted and no provider message was sent.

## Applied schema/access changes

- `20261104203445_prevent_duplicate_scoped_stock_item_names.sql`: one normalized-name unique index on the existing stock table. Existing duplicates were zero. Exactly one such index is verified.
- `20261104204059_protect_ingredient_balances_and_ledger_writes.sql`: column/table privilege restrictions and one restrictive zero-opening-balance INSERT policy. Verified one policy; authenticated balance UPDATE and ledger INSERT are false; authorized name UPDATE remains true. Existing adjustment RPC still has exactly one overload, anon/authenticated execution denied and service-role execution allowed.

No new table, function, application queue, role or background task was introduced. Security advisors were read after applying; this batch does not claim to resolve every historical advisor category.

## Remaining inventory work

The current page does not implement ingredient metadata editing or archive/restore; those remain explicit lifecycle gaps, rather than tested buttons. Unit/conversion edits must preserve existing ledger meaning. Complete larger inventory reporting/export/reconciliation and the remaining settings/role matrix in a later coherent batch. These additions are separate from the now-tested current create/adjust/history controls.
