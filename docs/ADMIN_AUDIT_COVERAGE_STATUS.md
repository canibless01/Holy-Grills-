# Admin audit coverage and ownership

**Current executed page batches — 29 October 2026.** Each pass covers the actions/cases in its evidence; the whole admin A–Z audit is still open.

| Page | Current result |
| --- | --- |
| Departments & Academic Levels | [Native fields/edit/hide/restore/search, role/scope/duplicate and linked-profile checks](ADMIN_ACADEMIC_PAGE_EVIDENCE_2026_10_29.md) pass |
| Academic Calendar | [All six types, modal fields, scope/edit/retire/restore and graduation consumer](ADMIN_CALENDAR_PAGE_EVIDENCE_2026_10_29.md) pass |
| Delivery → Zones & Fees | [Gate/hostel fields, pricing, lifecycle, actual scope/link/duplicate integrity](ADMIN_DELIVERY_LOCATIONS_EVIDENCE_2026_10_29.md) pass |
| Delivery → Delivery area | [Centre/radius target, failed/stale reads, save/clear/force, permissions and checkout distance](ADMIN_DELIVERY_AREA_EVIDENCE_2026_10_29.md) pass |
| Remaining admin pages / actions | Still open; targeted earlier successes below do not establish whole-page approval |

The domain ownership/history below remains context rather than a current whole-page pass list. Latest integrated backend suite: **769 passed**.


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
