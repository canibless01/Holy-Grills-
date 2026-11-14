Current executed continuation: [Newsletter controls](ADMIN_NEWSLETTER_PAGE_2026_11_13.md) and [delivery worker](ADMIN_NEWSLETTER_WORKER_2026_11_13.md), 13 November 2026. Earlier dated open items below are historical; later closure evidence takes precedence. The whole admin audit remains open.

General-site continuation: [4 November ownership and progress](GENERAL_SITE_AUDIT_PROGRESS_2026_11_04.md).

Current remaining work: [30 October launch and full audit list](REMAINING_LAUNCH_AND_AUDIT_2026_10_30.md).

# Admin audit coverage and ownership

**Current executed page batches — 29 October 2026.** Each pass covers the actions/cases in its evidence; the whole admin A–Z audit is still open.

| Page | Current result |
| --- | --- |
| Departments & Academic Levels | [Native fields/edit/hide/restore/search, role/scope/duplicate and linked-profile checks](ADMIN_ACADEMIC_PAGE_EVIDENCE_2026_10_29.md) pass |
| Academic Calendar | [All six types, modal fields, scope/edit/retire/restore and graduation consumer](ADMIN_CALENDAR_PAGE_EVIDENCE_2026_10_29.md) pass |
| Delivery → Zones & Fees | [Gate/hostel fields, pricing, lifecycle, actual scope/link/duplicate integrity](ADMIN_DELIVERY_LOCATIONS_EVIDENCE_2026_10_29.md) pass |
| Delivery → Delivery area | [Centre/radius target, failed/stale reads, save/clear/force, permissions and checkout distance](ADMIN_DELIVERY_AREA_EVIDENCE_2026_10_29.md) pass |
| Kitchen workspace / read-only settings | [Explicit super-admin campus, handoff scope, authoritative availability, failed-read recovery](KITCHEN_WORKSPACE_SCOPE_EVIDENCE_2026_10_29.md) pass; ineffective legacy switch removed in favor of existing ordering-window controls |
| Feature Flags — global controls | [Native toggle/create/retry, override visibility, actual global-row/RLS checks](ADMIN_FEATURE_FLAGS_SCOPE_EVIDENCE_2026_10_29.md) pass; complete consumer/worker matrix remains open |
| Kitchen prep/stock actions | [Window races/Retry, single batch submission, correct persisted campus stock endpoint](KITCHEN_ACTIONS_EVIDENCE_2026_10_30.md) pass for listed cases |
| Store / ingredient stock — current controls | [Native create/adjust/history, scopes/retries, paging and actual direct-write protection](ADMIN_STOCK_CONTROLS_EVIDENCE_2026_11_04.md) pass for listed cases; edit/archive/restore and broader inventory reports remain open |
| Remaining admin pages / actions | Still open; targeted earlier successes below do not establish whole-page approval |

The domain ownership/history below remains context rather than a current whole-page pass list. Latest integrated backend suite in the general-site continuation: **993 passed**.


**Inventoried means mapped, not approved safe.** Opening a sidebar page, listing fields or finding an existing test does not establish that every button, role and customer outcome works. A passed loop applies only to its recorded assertions. This chat cannot certify work performed in another chat without its evidence/PR.

Coverage is completed as each domain is audited: admin input/action → API → stored rows → customer/kitchen/rider result → reload, plus invalid values, failed/repeated requests, concurrency, campus/global permissions and cleanup. Source inspection and inserted task fixtures are distinguished from executed UI or workers.

| Admin area | Responsible workstream | Evidence available in this chat / remaining scope |
| --- | --- | --- |
| Menu Items; Addons & Variations | A for menu/order consumers; B coordinates reference-data controls | Native creation/edit and selected student menu/cart loops exist; this is not every possible stock/role variant or real image-upload sign-off |
| Orders; kitchen/rider order and batch actions | A — this chat | Atomic admission/refund and selected delivery loops verified; card recovery now has UI/SQL/provider-contract proof; broader bulk/guest/assignment variants remain open |
| Wallet and financial controls | A | Atomic ledger/concurrency checks exist; real funding/provider loops and extended reconciliation remain open |
| Promo Codes; order locks; abandoned carts | A | Selected price/lock/replay boundaries verified; complete promotion, scheduler and notification loops remain open |
| Rewards; Free Credits; Exclusive Spin; Challenges; HP & Multipliers | A | Spin grant/award, delivery-credit use/restoration and primary delivery HP verified for documented cases; free-side grant/selection/admission/cancellation now has native and SQL proof; queued multiplier consumption now has SQL/handler proof and native grant/history/quote proof; physical fulfilment, full stacking and auxiliary jobs remain open |
| Storefront | A | Documented fields, independent carousels and public placements tested; Cloudinary bytes/export and newsletter provider/worker remain unverified; residual write/sort cases remain open |
| Feature Flags | A for global controls and reward gates; B for its domain consumers | Super-admin mutation, campus-admin restriction and selected live consumers verified; each additional feature consumer still needs its own proof |
| Events and ticket administration | B — new chat | Await B's domain evidence and PR; this chat does not claim full event/ticket/check-in coverage |
| Catering | B | Await B's evidence |
| Marketplace; subscriptions and codes | B | Await B's evidence; shared wallet/payment infrastructure must be coordinated with A |
| Users; onboarding; staff/identity controls | B | Audit actors and selected authorization checks exist; complete native identity/user-management coverage belongs to B |
| Campus; Departments; Academic Calendar; hostel/gate configuration | B | A owns checkout's consumption, fee arithmetic and kitchen opening/closing behavior; B owns configuration inputs and broader setup |
| Store / Stock; inventory operations | B | Mapping is not verification; await every stock-control/report loop from B; A verifies admission/stock contention against orders |
| Analytics; dashboards; leaderboard administration; review moderation | B for interfaces; A for financial/reward producers | Existing tests cover selected boundaries; report/export/filter/pagination and every producer-consumer loop require B's evidence |
| Notifications blasts/preferences | B for admin interfaces; A for shared transport and transactional jobs | End-to-end delivery is not inferred from a stored notification or working deep link |
| Settings; System; Webhook Events | B for remaining controls/diagnostics; A for payment/reward behavior | Each setting must be traced to an actual consumer. New payment replay rules are A's shared contract; historical security/dead settings remain under B |

See the complete [two-workstream assignment](REMAINING_ECOSYSTEM_AUDIT_SPLIT.md), [tested/fixed progress](ECOSYSTEM_AUDIT_PROGRESS.md), [database access verification](MIGRATION_ACCESS_VERIFICATION.md), and [external-provider checklist](PROVIDER_VERIFICATION_BLOCKERS.md). The historical Playwright coverage map is a test plan, not a completed test run. No whole-page or whole-ecosystem approval is implied by inventory status.

29 October next completed page batch: [Academic Calendar](ADMIN_CALENDAR_PAGE_EVIDENCE_2026_10_29.md) now has native field/type/edit/retire/restore/error/scope checks and real RLS/date/duplicate/graduation-consumer proof. Gates/Hostels and Delivery area are next. This does not close the entire Campus configuration domain.

29 October Delivery → Zones & Fees batch: [gate/hostel evidence](ADMIN_DELIVERY_LOCATIONS_EVIDENCE_2026_10_29.md) covers native inputs/edit/hide/restore, actual same-campus constraints/roles, duplicate protection, fee preview/checkout base-floor correction and historical order preservation. Delivery area is a separate next page. Backend **760 passed**; whole-admin approval remains open.

### Store lifecycle follow-up — 5 November 2026

Native ingredient metadata editing and archive/restore have targeted backend, Chromium and rolled-back Supabase evidence. The lifecycle helper is service-only, preserves accounting, and rejects stale transitions; archived ingredients reject new adjustments while retaining receipt replay and ledger access. See [recorded cases and remaining scope](ADMIN_STOCK_LIFECYCLE_EVIDENCE_2026_11_05.md). Reporting/export and wider stock-notification behavior remain open; the entire Store page and whole admin inventory are not marked complete.

### Reporting controls — 5 November 2026

Targeted Economics campus/date/error/retry and Analytics date/CSV controls are now verified through real handlers and a native controlled browser run. See [reporting evidence and explicit remaining scope](ADMIN_REPORTING_SCOPE_EVIDENCE_2026_11_05.md). This does not close every chart, programme arithmetic, concurrent export behavior or whole-page reporting coverage.

### Reviews and tier arithmetic — 5 November 2026

[Targeted evidence](ADMIN_REVIEWS_AND_REPORT_ARITHMETIC_2026_11_05.md) covers the native Reviews read/filter/detail/page/search/retry controls and campus switching, stable backend page order, selected-campus tier activity isolation, controlled report arithmetic, and rating-fallback duplicate handling. No review promotion/manual moderation write workflow is claimed. Full reporting/moderation and whole-admin coverage remain open.

### Review follow-up controls — 5 November 2026

[Native mutation and real SQL evidence](ADMIN_REVIEW_FOLLOWUP_EVIDENCE_2026_11_05.md) now covers setting/clearing follow-up flags, repeated/failed/stale writes, campus boundaries and unchanged score/HP. Real public rating aggregation with duplicate item lines is verified in rolled-back fixtures. No review deletion, score censorship or promotion workflow is implied.

### User directory and HP grants — 5 November 2026

[Targeted directory/grant loops](ADMIN_USER_GRANT_CONTROLS_2026_11_05.md) cover campus switches, history failures, role/activation reflection, single/bulk retry identity, explicit recipient safety and partial bulk recovery. Expiry, broader identity/role exceptions and complete programme-page coverage remain open.

### Manual HP expiry — 5 November 2026

[Preview, confirmation and receipt evidence](ADMIN_HP_EXPIRY_EVIDENCE_2026_11_05.md) covers native partial/all-mode deductions, failures/retries/stale previews, private grants and role/campus guards with real rolled-back ledger tests. Scheduled expiry and broader programme/identity cases remain separate.

### Community-manager account control — 7 November 2026

[Owner-confirmed hierarchy](COMMUNITY_MANAGER_ACCOUNT_HIERARCHY_2026_11_07.md) is verified through the API, native directory and fresh Supabase rollback cases. Own-campus manager activation/deactivation belongs to campus admins; global admin-account control remains with super admins. No database restriction was added.

### Current continuation — 13 November 2026

The historical tables above are not a current backlog: later closure records in `GENERAL_SITE_AUDIT_PROGRESS_2026_11_04.md` supersede earlier open stock/event/settings/reward entries. The page-by-page continuation is now active. Storefront → Newsletter controls have [new native/API/live transaction/concurrency evidence](ADMIN_NEWSLETTER_PAGE_2026_11_13.md): fields, preview, queue/replay, list/detail/paging, cancel/replay, subscriber removal and role/campus guards. Its worker send-boundary/interruption/counter cases are now closed in `ADMIN_NEWSLETTER_WORKER_2026_11_13.md`. Next are Campaigns & Blasts and remaining ambassador/CMS exception cases. No whole-admin sign-off is claimed from page inventory alone.

### Campaigns & Blasts — 13 November 2026

[Recorded page evidence](ADMIN_CAMPAIGNS_PAGE_2026_11_13.md) closes the native composer/history/analytics/test/sync/recovery batch. Fixed cross-campus analytics and subscriber-sync access, dropped tracking settings, WAT scheduling, stale reads and duplicate submissions; verified role/RLS/provider-review boundaries. Full backend 1,771, native mobile/desktop, typecheck/lint/build and live rollback matrices pass. Ambassador roster/milestone, distribution and review exceptions are next; existing completed pages are not reopened merely because older inventory rows predate their evidence.

### Ambassador controls — 14 November 2026

[Native, API and live SQL evidence](ADMIN_AMBASSADOR_PAGES_2026_11_14.md) closes roster/search/tag recovery, milestone edit/activation/replay and review/grant controls for the recorded cases. Added one service-only helper reusing the audit ledger; campus selection and inactive-recipient boundaries corrected. Full backend 1,787 and independent-session concurrency tests pass. Native share/distribution exception checks also pass on mobile and desktop (failed reads/Retry, personalized links, clipboard denial, explicit manual statuses and selected recipients). CMS/presentation variants and historical database dependency review remain follow-up work; this does not claim whole-admin completion.
