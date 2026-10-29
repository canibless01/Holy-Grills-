> **29 October update:** this is a historical coverage map, not completed page approval. Current [launch priorities](LAUNCH_PRIORITY_STATUS_2026_10_29.md), [provider results](FRESH_ENV_PROVIDER_PWA_RESULTS_2026_10_28.md), [delivery financial recovery](DELIVERY_REWARD_FINANCIAL_RECOVERY_2026_10_28.md), [ordering-streak recovery](ORDER_STREAK_RECOVERY_2026_10_29.md) and [FUTA signup](FUTA_SIGNUP_REFERENCE_DATA_2026_10_29.md) supersede older provider/upload/funding gaps below. **The complete admin action matrix remains open.**

# Admin audit coverage and ownership

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
