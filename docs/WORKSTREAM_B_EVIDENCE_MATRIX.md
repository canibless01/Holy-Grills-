# Workstream B evidence and integration handoff

Audit date: 14 October 2026 (Africa/Lagos). Project: Test Two, `zaxdkrmzyibkvlsrgmvq`. Started at `8e44508`; fetched main again at `723825e`. This is a draft integration checkpoint, **not complete Workstream B or A–Z sign-off**. The remaining rows below require continued work.

## Evidence matrix

| Domain / controls | Status | Evidence and limits |
|---|---|---|
| Native events: create, tier pricing/description/capacity, free registration | Verified for exercised loop | Real admin browser save → API → database → student registration → ticket reload. Zero HP and tier capacity/description retained. Tier editor canonical field mapping fixed. |
| Event admission rollback, capacity, retry | Verified | Invalid promo previously incremented sold_count without a ticket; now rolls back. Six concurrent guest admissions against capacity one yield one ticket and five capacity errors; replay returns the original ticket. Both live functions reject omitted tiers when tiers exist, with ticket count unchanged. |
| Event QR, scanner, duplicate admission | Verified for zero-HP tickets | Canonical door payload accepted; unpaid/cancelled/expired/wrong-event/foreign-campus boundaries covered by tests. Live admission succeeds once, duplicate rejected, owner check-in receipt survives reload. Nonzero HP and reward failure recovery remain open. |
| Door token privacy | Verified | Public event metadata no longer exposes the door token. Anonymous/student/admin direct reads of protected table denied; authorized campus staff generate through backend. Legacy staff writes are stripped and moved by triggers. Deploy backend reader with migration. |
| Event reports, deletion | Partially verified | Registrants handler authentication corrected; CSV field mismatch and formula injection corrected server-side. Deletion with tickets returns conflict. Attendance counts read authoritative tickets/check-ins for visible parents. Large-result pagination, browser exports, cancellations/refunds and provider-paid admission still open. |
| Catering customer → admin → kitchen → customer | Verified | Real browser request, admin quote/assignment, assigned kitchen start/complete, customer receipt and reload. Quote zero/null handling, native status names and assignment permissions fixed. API retry reuses exact request UUID; no second row. |
| Catering negative/role cases | Verified API/tests | Invalid email/phone/date/budget/guest count rejected. Foreign admin denied; kitchen restricted to own assigned requests and allowed transitions. Customer responses omit notes/assignment; email no longer includes internal notes. Last response-redaction/email change regression-verified; provider receipt unverified. |
| Catering notifications | Partial / shared dependency | First owned admin in-app receipt persisted. Subsequent independent requests can be suppressed by shared type throttling. External emails intentionally suppressed in audit server; transport fix/receipt testing belongs to A. |
| Marketplace listing and subscription codes | Partial | Real scoped admin subscription listing saved, duplicate uploaded codes deduplicated. API input and code-upload campus restrictions fixed. Initial customer purchase denied by global release gate. Subsequent isolated-campus overrides verified four retries produce one purchase/code, competing buyers produce one winner for the last code, and two purchases create two bonus transactions. Sold-out retry fixed and live-verified; cross-listing intent reuse returns 409. Paid purchases, expiry/refunds/fulfilment and full customer browser loop remain open. Global gates unchanged. |
| Marketplace trades | Unused/degraded candidate | No complete peer-trade consumer established. Do not infer safe schema removal from this absence. |
| Identity/profile/preferences | Verified for exercised loops | Eight fresh Auth actors: student/student2/kitchen/rider/admin/foreign-admin/foreign-student/super-admin. User-editable Auth metadata cannot grant role/campus. Deactivation blocks API; reactivation requires renewed login. Real profile UI saves nickname/phone/department/custom level and preserves after reload. Preference UI partial update retains unrelated opt-outs across reload. |
| Signup, verification, reset, onboarding gifts/badges | Still open / provider blocked | Synthetic accounts were created through Auth admin API; this does not prove customer signup, OTP, verification or reset delivery. Avatar upload/delete, graduation and complete onboarding loops not signed off. |
| Staff/user administration | Partial | Cross-campus mutation and campus-admin promotion denied; synthetic student role changed to rider and restored; deactivate/reactivate exercised. Every admin form/button and concurrent role changes still require browser coverage. |
| Campus/department/levels/hostel/gates | Partial | Department and custom level persisted; signed foreign-campus query remains own-campus; custom level consumed by profile UI. Hostel requires active same-campus gate; invalid fee rejected; valid fixture consumed by student list. Campus/calendar full UI/job loops remain open. |
| Stock store adjustments | Verified API/concurrency | Unit conversion purchase 5→10, usage 2→8; zero/negative/foreign-campus failures do not write ledger. Six matching request UUID retries add four units once with one ledger entry; conflicting payload returns conflict. Create validation fixed. Full browser edit/archive and larger ledger reporting remain open. |
| Dashboards/analytics/remaining admin reads | Partial | 36 real calls across 28 reporting/admin APIs; selected student access denials and invalid date errors verified. Empty owned campus order counts match database. Error/retry interfaces fixed. This does not establish every filter, button, export, arithmetic or pagination loop. |
| System settings | Partial / unused fixture | Owned campus object setting persisted; string is_public rejected, global/cross-campus admin mutations denied. Synthetic arbitrary key has no consumer and is unused audit data. Existing setting keys inventoried without publishing values; all consumer semantics not verified. |
| Blast preview/schedule/cancel/retry | Verified API | Owned campus student preview count two; create/replay produces one row; foreign cancel denied; cancel/replay persisted cancelled. Segment campus override blocked in backend and restrictive database policy. Browser worker/provider delivery remains unverified. |
| Notification preferences failure/retry | Verified live persistence; synthetic failure UI | Real PATCH/reload preserves unrelated opt-outs. Intercepted browser read failure shows retry and failed PATCH rolls back toggle. Shared transport currently reads different preference fields; actual enforcement needs A. |
| Historical RLS/grants/definer inventory | Partial | Public table/view and definer signatures, grants, search paths, SQL dependency counts and source references inventoried. Event tier comparison switched to invoker and unpublished tier leak closed. No historical object proved unused or removed. Remaining advisories listed below. |

## Live migrations

Each named migration applied once on Test Two; do not apply again simply because the branch is merged. Four timestamped files were created using the CLI. The two event changes use canonical SQL documents; the later CLI bootstrap failed in this environment, so no invented timestamped filename was added.

1. `make_event_admission_failures_rollback_and_tier_reads_scoped` — [SQL](WORKSTREAM_B_EVENT_ADMISSION_FIX.sql).
2. `make_stock_adjustments_retry_safe` — backend migration `20261014072355`.
3. `validate_checkin_admission_and_allow_owned_receipt_reads` — backend migration `20261014072356`.
4. `enforce_blast_segment_campus_scope` — backend migration `20261014073756`.
5. `keep_event_door_tokens_private` — backend migration `20261014075026`.
6. `require_event_tiers_when_tiers_exist` — [SQL](WORKSTREAM_B_EVENT_TIER_REQUIREMENT.sql); preserves current function definitions and adds a guard under existing locks.

No shared wallet, HP ledger, task or role helper was replaced. Stock RPC changes from eight arguments to nine with a default request UUID: existing named-argument calls remain valid. Dependency inventory found no SQL consumers of the old stock signature. New protected door-token table was justified by the public token leak; it has RLS, service-only grants and two compatibility triggers. Existing storage remains Cloudinary only.

## Workstream A integration dependencies

- Deploy event backend with the private-door migration: old backend metadata reads cannot validate new private tokens.
- Positive-HP event scans still need atomic/recoverable check-in reward handling using A's HP semantics. Successful zero-HP scans do not prove reward recovery.
- Shared notification transport must enforce notification_preferences, prevent throttling separate catering/marketplace operational requests, and verify actual provider receipts.
- Shared blast worker needs durable failed/sending recovery and delivery counts; action_url/reference/deep-link consumption still needs coordination. Interface copy now says processed rather than delivered.
- Shared public-campus helper still permits override in some A challenge consumers; B department/level endpoints bind signed users locally.
- Resolve shared message registry/router and Kitchen tab changes during integration; kitchen.py edits concern inventory only, delivery.py edits concern hostel/gate setup only. CateringCard now uses the canonical request modal.
- Marketplace purchase/provider/payment recovery and event refunds must reuse shared transaction infrastructure. Global release flags were not flipped for this audit.

## Historical security notices and removal limits

Latest security advisor: newsletter_deliveries has RLS with no policies; pg_net remains in public; 13 anonymous and 24 authenticated executable SECURITY DEFINER notices; leaked-password protection remains disabled. Some are intentional policy helpers or trigger functions. Their existence alone does not justify revoking shared role helpers. See [inventory](WORKSTREAM_B_SCHEMA_INVENTORY.json); unproven-unused-candidate means review needed, not unused.

Final dependency check: pg_net reports `extrelocatable=false` and 28 catalogue dependents, so a simple ALTER EXTENSION SET SCHEMA is unsuitable; coordinated extension replacement requires more investigation. All current public views report security_invoker=true. Final catalogue checks confirm service-only execute on admission/stock/door functions, invoker tier comparison, exactly one of each added policy and both door triggers. Door table grants are limited to postgres/service_role; public event metadata has zero door-token keys.

Remediation references: [RLS policies](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy), [extension schema](https://supabase.com/docs/guides/database/database-linter?lint=0014_extension_in_public), [anonymous definer grants](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable), [authenticated definer grants](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable).

## Validation and fixture handling

Initial B regression: 186 backend tests pass; frontend typecheck and complete build pass, including message/route checks and eight QR parser assertions. Final integrated counts and cleanup results are recorded below after execution. Browser runs used the real local frontend/backend against Test Two with isolated synthetic recipients. Email/push provider sends were suppressed; in-app writes were restricted to owned actors. No real recipients, external payment funding, global release setting changes or Supabase Storage fallback were used. Credentials, tokens and raw fixture manifests remain excluded from Git.

Final integrated backend: **209 passed**. Main merge preserved both sides of the messages.py conflict. Frontend typecheck and complete production build passed after integration. The last profile change preserves deactivated/unresolved reference values on unrelated edits; this edge case is fixed but awaits a live browser rerun.

Cleanup completed and verified by exact key reads: two owned campuses; eight profiles/Auth users and their empty wallets/referral codes; one event/tier, two tickets/check-ins and protected door token; three catering requests; one department/level, gate/hostel, listing/access code, stock item and three ledger entries, cancelled blast/preferences/owned setting; six each owned audit logs, notifications and notification logs. The first pass stopped at system_settings' missing primary key; resumed using the recorded exact key+campus tuple. No broad production or other-chat deletion. Owned profiles were deactivated and logout requested before deletion, and missing fresh profiles deny residual JWT authorization. No temporary global settings needed restoration. [Selected evidence and cleanup counts](WORKSTREAM_B_TEST_EVIDENCE.json).


## Continuation checkpoint — 14 October 2026

Workstream A's concrete requests and acceptance criteria are in [A dependencies](WORKSTREAM_A_DEPENDENCIES_FROM_B.md). No additional database migration was applied in this continuation.

- **Verified:** isolated academic calendar creation → student current-period consumption despite foreign query → analytics row with zero owned orders; object description rejected; foreign update denied. Real calendar browser edit/save/reload passes. Intercepted 503 produces Retry, which then uses the real backend successfully.
- **Verified:** free subscription allocation under four matching retries creates one purchase and assigns one code; two competing buyers for the last code produce one winner, with two total purchases and two bonus HP rows across both purchases. Live sold-out retry now returns the saved receipt with no new purchase; same key against another listing returns 409. This is not paid-provider/refund or bonus-outage recovery evidence.
- **Fixed, unit-verified, awaiting full browser coverage:** 13 analytics panels now render read failure/Retry instead of zero/empty results. Explicit calendar global selection overrides super-admin's campus header; campus admins remain bound to own campus. This global edge has a role regression test, not a live global production write.
- **Verified parser:** browser catering CSV export escapes formulas (including leading whitespace/BOM), quotes and zero values. Ten focused assertions are part of the production build; a downloaded real browser CSV remains unverified.
- **Cleanup verified:** a second distinct fixture prefix/campus pair and eight Auth accounts removed; exact owned calendar, two campus-only release flags, listing, two codes/purchases/bonus transactions/monthly trackers, owned notification/log/audit rows, wallets/profiles/referral codes removed. Global gates/settings unchanged.

Final continuation verification: **212 backend tests pass**, including 17 platform regressions; frontend typecheck and complete production build pass, including CSV formula assertions and route/message checks. Existing open rows remain open; B is not complete.


Review administration continuation (14 October): fetched main; it remains `723825e`, so no A dependency was newly resolved. Added 25-row pagination with backend total, filter resets, stale-response protection and error/retry. Search explicitly applies to this page. Intercepted Playwright responses verify outage/retry, pages 1–3, final-page disable and rating-filter reset. This is client-only evidence, not new live review creation/moderation/database sign-off. No accounts, live fixtures, settings or migrations changed. Final typecheck and complete production build pass, including message/route/CSV/QR checks.

## Completion pass in progress — 14 October 2026

PR #66 merged as `0635b21`. The continuation branch is `audit/platform-ecosystem-b-completion-20261014`; it normally merged main through `5015267`. This checkpoint is not whole-domain completion.

| Area | Evidence / change | Current status / remaining work |
|---|---|---|
| Positive event HP | Real committed scan with injected award outage; retry creates one active grant; subsequent scan denied with unchanged balance. Uses existing idempotent award primitive. | Verified targeted recovery; event expiry/config-change and broader concurrent cases remain open. |
| Event card setup | Stable per-ticket provider reference and pending-registration resume; focused unit regressions. | Fixed, live provider journey unverified; cancellations/refunds under review. |
| Catering | Previous real customer → admin quote/assignment → kitchen start/complete → customer reload. Two independent operational requests and replay receipts verified; A canonical transport now retained. | Downloaded registrant CSV, host provider receipt and remaining reporting/error/race controls still open. |
| Identity | Recovery fragment parser, correct own-session logout endpoint, truthful revoke result, login profile-read fail closed, campus-dependent reference loads and stable graduation reference. Four backend regressions and six parser cases. | Browser verification in progress; actual Auth email/recovery, signup partial-write and graduation claim-before-award gaps remain open. |
| Profile photos | Actual signed Cloudinary upload, decoded image, save/reload, removal/save/reload. Header accepts profile photo field. Exact provider asset deleted. | Targeted path verified; no Storage fallback. |
| User roles | Real super-admin promotion and demotion with required campus selection; reload reflects original student role. | Verified targeted UI/API/persistence/reload; full role matrix still required. |
| Campus setup | Super-admin create/edit/retire → public discovery/hide → reload; student/campus-admin/guest writes denied; authenticated direct insert denied by existing RLS. Stale timestamp update409 preserves current values. | Targeted live paths verified; default-campus guard has no live production mutation. |
| Inventory | New stock opens at zero; opening units require existing ledger adjustment. Mixed-unit summary counts stocked ingredients instead of summing unlike units. | Unit-verified; broader native UI/retry/ledger reconciliation remains open. |
| Onboarding settings | Intercepted read503/retry; enabled toggle saves intended value; sequential field saves; reload. | Client verified only; no global settings changed. |
| Blasts | Owned real API interruption after first recipient; failed retry completes; repeat adds no receipt; foreign retry denied; active lease409 and stale lease recovery; deep link persisted. Controlled campus-only Celery task processes due campaign and leaves future schedule unchanged. | Targeted verified before latest main integration; integrated live rerun pending. Actual scheduler cadence and external provider delivery remain unverified. |
| Notification preferences | Main's canonical category/channel policy and atomic legacy reconciliation retained; B duplicate policy removed. | Integrated backend suite251 passes; real email/push provider receipts blocked by missing configured keys. |
| Historical security / unused schema | Dependency inventory and advisor follow-up delegated to read-only review. | Open; no object is declared unused or removed merely because source search found no caller. |

No additional B migration has been applied in this completion pass. Third isolated fixture batch remains active for verification; cleanup has not yet completed. Work scripts and credentials are excluded from Git. No new continuation PR or merge-to-main is claimed at this checkpoint.
