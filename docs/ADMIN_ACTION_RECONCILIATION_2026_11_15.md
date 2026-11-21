# Current admin action reconciliation — 15 November 2026

This maps the **38 actual section IDs** in `src/lib/adminSections.ts` to action evidence. It replaces treating the old sidebar inventory as approval. “Recorded” means the linked assertions passed; it does not mean every possible input or a real provider receipt. Historical “next page” wording inside older evidence is superseded by later rows here and the master backlog.

Shared shell: [navigation evidence](ADMIN_NAVIGATION_EVIDENCE_2026_11_14.md) covers all registry entries, compact/mobile layout, direct-link fallback, role/workspace search, selected campus, reload/back/forward and student workspace navigation. Page internals use the evidence below.

| Section ID | Recorded controls / consumer loop | Evidence |
|---|---|---|
| dashboard | Populated counts/charts; delivery pipeline shape; shared Lagos range; refresh/partial/all failure; delayed campus reply; manager denial | [Dashboard](ADMIN_DASHBOARD_CONTRACT_2026_11_15.md) |
| analytics | Date validation/races, headline recovery, CSV failure/formula boundaries, independent brand reads; brand JSON/create/replay/status editor | [Analytics](ADMIN_ANALYTICS_RECOVERY_2026_11_14.md), [brand controls](ADMIN_BRAND_REQUEST_CONTROLS_2026_11_14.md) |
| walletanalytics | Liability/funding projections, dates, history, export, malformed/error/retry, campus scope | [Wallet reports](WALLET_FUNDING_ANALYTICS_2026_11_10.md) |
| deliverycosts | Pool/cost projections and capacity inputs, scope, failed refresh, report/export controls | [Delivery costs](DELIVERY_CUSHION_POOL_2026_11_12.md) |
| economics | Effective campus/date requests, failed-section recovery, retained dates and populated reward/refund arithmetic | [Scope](ADMIN_REPORTING_SCOPE_EVIDENCE_2026_11_05.md), [refund arithmetic](REWARD_COMBINATIONS_AND_REFUND_REPORTING_2026_11_12.md) |
| menu | Admin menu input and customer item/checkout response, availability, add-on quantity, image contract | [Menu/settings](MENU_CRAWL_AND_SETTINGS_CHECK_2026_11_11.md), [storefront inserts](STOREFRONT_INSERT_CONTRACT_EVIDENCE.md) |
| addons | Side dropdown/quantity and order-price/HP consumers; global and item-linked additions | [Menu/settings](MENU_CRAWL_AND_SETTINGS_CHECK_2026_11_11.md), [checkout perks](CHECKOUT_PERKS_AND_GATE_PICKUP_2026_11_13.md) |
| hp | Individual/bulk grant recipients, preview/commit/replay, expiry/balance and effective campus | [Grants](ADMIN_USER_GRANT_CONTROLS_2026_11_05.md), [expiry](ADMIN_HP_EXPIRY_EVIDENCE_2026_11_05.md), [recipient search](ADMIN_HP_RECIPIENT_SEARCH_2026_11_07.md) |
| rewards | Redemption, immutable earned promise, delivery selection, order attachment, restoration/refund | [Restoration](REWARD_RESTORATION_AND_AUDIT_STATUS_2026_11_11.md), [legacy closure](LEGACY_GIFT_RECOVERY_CLOSURE_2026_11_13.md) |
| freecredits | Credit grant/selection/admission/cancellation and current legacy recovery | [Instant redemption](INSTANT_REDEMPTION_EVIDENCE.md), [legacy closure](LEGACY_GIFT_RECOVERY_CLOSURE_2026_11_13.md) |
| exclusivespin | Atomic spin/reward/multiplier consumption and earned benefit restoration | [Reward release](REWARD_RELEASE_CHALLENGE_EVIDENCE.md), [restoration](REWARD_RESTORATION_AND_AUDIT_STATUS_2026_11_11.md), [prize editor retry/version](ADMIN_SPIN_POOL_RECOVERY_2026_11_16.md) |
| challenges | Challenge/milestone creation/eligibility/progression/recovery and promotion consumers | [Challenges](CHALLENGE_MILESTONE_PROMO_VERIFICATION_2026_11_13.md), [membership recovery](MEMBERSHIP_REWARD_RECOVERY_2026_11_13.md) |
| orders | Payment/receipt recovery, scoped status/batches, refund amount/confirmation/conservation, kitchen/rider loop | [Checkout/handoff](CHECKOUT_AND_RIDER_HANDOFF_2026_11_10.md), [refunds](REWARD_COMBINATIONS_AND_REFUND_REPORTING_2026_11_12.md) |
| wallet | Read-only ledger filters/details/pages, late replies, inline Retry, empty later-page return | [Ledger controls](ADMIN_READ_PAGINATION_2026_11_15.md); financial write boundaries retain [funding evidence](WALLET_FUNDING_SQL_CHECK_2026_11_12.md) |
| events | Creation/edit/review, owner settlement, ticket registration/payment/check-in, cancellation/reschedule, resend and private guest/account QR | [Event operations](EVENT_OPERATIONS_2026_11_10.md), [resend](EVENT_TICKET_RESEND_2026_11_13.md), [guest HP](EVENT_GUEST_HP_RECOVERY_2026_11_13.md), [admission](EVENT_ADMISSION_WINDOW_2026_11_13.md) |
| catering | Named eligible staff, zero/invalid quote, notes/status/version/replay, cancellation, request search/filter/pagination, isolated event tab | [Catering](ADMIN_CATERING_CONTROLS_2026_11_15.md) |
| marketplace | Existing gated listing/payment/stock cases; expansion remains owner-deferred | [Original B matrix](WORKSTREAM_B_EVIDENCE_MATRIX.md); not upgraded to complete native approval |
| promos | Editor and checkout gift/discount stacking, immutable benefit claims and refund restoration | [Multi-gift](MULTI_GIFT_CAMPAIGNS_EVIDENCE_2026_10_28.md), [combinations](REWARD_COMBINATIONS_AND_REFUND_REPORTING_2026_11_12.md) |
| abandoned | All/pending/recovered reads, search/contact actions, reminder pending/rejection/retry, six history pages | [Lock/cart controls](ADMIN_LOCK_CART_CONTROLS_2026_11_15.md), [pagination](ADMIN_READ_PAGINATION_2026_11_15.md) |
| reviews | Search/filter/read detail and user/item rating reflection; current page is read-only | [Reviews/arithmetic](ADMIN_REVIEWS_AND_REPORT_ARITHMETIC_2026_11_05.md), [follow-up](ADMIN_REVIEW_FOLLOWUP_EVIDENCE_2026_11_05.md) |
| users | Search/history/grants; role/campus expected-state and write races; deactivate/reactivate; manager hierarchy | [Identity controls](ADMIN_IDENTITY_CONCURRENCY_2026_11_15.md), [grants](ADMIN_USER_GRANT_CONTROLS_2026_11_05.md) |
| delivery | Zones/gates/hostels, delivery area, assignment/reassignment/split and physical handoff/map consumers | [Locations](ADMIN_DELIVERY_LOCATIONS_EVIDENCE_2026_10_29.md), [area](ADMIN_DELIVERY_AREA_EVIDENCE_2026_10_29.md), [handoff](CHECKOUT_AND_RIDER_HANDOFF_2026_11_10.md) |
| orderlocks | All supported status/date filters, combined changes, reverse-order replies, HP/discount/contact/order values, read Retry | [Lock/cart controls](ADMIN_LOCK_CART_CONTROLS_2026_11_15.md) |
| store | Create/adjust/history, ingredient edit/archive/restore, reconciliation/export and stock handover | [Stock lifecycle](ADMIN_STOCK_LIFECYCLE_EVIDENCE_2026_11_05.md), [handover](STOCK_HANDOVER_SETTINGS_LOOP_2026_11_12.md) |
| notifications | Composer, segmentation, preview/test/sync, queue/history/cancel/retry and scoped access | [Campaigns](ADMIN_CAMPAIGNS_PAGE_2026_11_13.md) |
| leaderboard | Pending/history/Hall-of-Fame read failures, handover notes, successful write followed by failed refresh/recovery | [Prize recovery](ADMIN_PRIZE_READ_RECOVERY_2026_11_14.md), [Hall-of-Fame transitions](ADMIN_CAMPUS_PRIZE_CONTROLS_2026_11_15.md) |
| ambassadors | Roster/search/tag, milestone fields/activation/edit/atomic replay and hierarchy | [Ambassador actions](ADMIN_AMBASSADOR_PAGES_2026_11_14.md) |
| ambassadorpromo | Recipient scope, share/status recovery and distribution controls | [Ambassador actions](ADMIN_AMBASSADOR_PAGES_2026_11_14.md), [manager sharing](COMMUNITY_MANAGER_SHARING_2026_11_21.md) |
| ambassadorreviews | Monthly review recipients/recommendations and replay-safe grants | [Ambassador actions](ADMIN_AMBASSADOR_PAGES_2026_11_14.md) |
| campuses | Strict fields/create replay/version/default-campus safeguards; native create/edit/active/read-only/denial/recovery | [Campus native controls](ADMIN_CAMPUS_PRIZE_CONTROLS_2026_11_15.md) |
| departments | Department/level fields, search, create/edit/hide/restore, faculty propagation, scope and duplicate handling | [Academic actions](ADMIN_ACADEMIC_PAGE_EVIDENCE_2026_10_29.md) |
| storefront | Per-section fields/placements, sort, failed drafts/version/reload, newsletter; owner-confirmed Cloudinary uploads | [CMS recovery](CMS_EDIT_RECOVERY_2026_11_14.md), [newsletter](ADMIN_NEWSLETTER_PAGE_2026_11_13.md), [popup cases](PUBLIC_CONTACT_PREFERENCES_POPUPS_2026_11_15.md) |
| onboarding | Configured gift selection, multi-gift earning/checkout/refund and graduation eligibility consumers | [Multi-gift](MULTI_GIFT_CAMPAIGNS_EVIDENCE_2026_10_28.md), [legacy recovery](LEGACY_GIFT_RECOVERY_CLOSURE_2026_11_13.md) |
| flags | Global toggles/create/read recovery, selected campus visibility and disabled consumer checks | [Global flags](ADMIN_FEATURE_FLAGS_SCOPE_EVIDENCE_2026_10_29.md); A4 owner retains final consumer checklist |
| settings | Typed drafts, invalid JSON, versioned writes, failed refresh/reload and scope | [Latest settings](SETTINGS_SYSTEM_RECOVERY_2026_11_15.md); A4 owner retains final consumer checklist |
| academiccalendar | All six types, fields, scoped create/edit/retire/restore and dated graduation consumer | [Calendar](ADMIN_CALENDAR_PAGE_EVIDENCE_2026_10_29.md) |
| webhooks | Filter/detail/retry, scoped authorization and event/webhook recovery | [Webhook controls](ADMIN_WEBHOOK_CONTROLS_2026_11_07.md), [event reliability](EVENT_RELIABILITY_2026_11_09.md) |
| system | Cron diagnostics/error/Retry/pending Run guard, nested health, audit paging and recovery | [Latest system](SETTINGS_SYSTEM_RECOVERY_2026_11_15.md); actual periodic execution remains operational acceptance |

## Concrete remaining reconciliation

- Campus editor and Hall-of-Fame transition modal controls are closed for the cases in [their current evidence](ADMIN_CAMPUS_PRIZE_CONTROLS_2026_11_15.md).
- Reporting current/historical attribution, populated actual chart responses, shared date-aware requests and all four CSV controls are reconciled in [21 November reporting](ADMIN_REPORT_CONTRACTS_2026_11_21.md). Independent read APIs do not claim one atomic reporting snapshot; historical tier-at-purchase reconstruction is not an existing feature.
- Menu/addon/reward/challenge/free-credit/onboarding native field and recovery follow-ups are recorded in [final editor reconciliation](ADMIN_FINAL_EDITORS_2026_11_21.md); spin retains its existing replay/version/session evidence. Consumer tests are linked separately from editor assertions.
- A4/A7 and O4/O5 recorded review is complete in [the current closeout](AUDIT_CLOSEOUT_2026_11_21.md). Retain its latest pushed changes. Operational O1–O3 observations remain explicit.
- Catering DB-update-to-email capture is now closed by the other chat in [settings/catering recovery](SETTINGS_CONSUMERS_CATERING_RECOVERY_2026_11_15.md); real inbox/device/scheduled-worker/provider observations remain O1–O3.
- Marketplace expansion, group tickets, official transfer, delegated door staff, broad visual redesign and optional schema/data deletion remain deferred as in the master.

Public/profile extras closed in this run: [profile/account recovery](PROFILE_ACCOUNT_RECOVERY_2026_11_15.md) and [preferences/contact/popups](PUBLIC_CONTACT_PREFERENCES_POPUPS_2026_11_15.md). No customer cleanup or production broadcasts are part of this matrix.

21 November continuation: [editor recovery](ADMIN_EDITOR_RECOVERY_2026_11_21.md) adds native menu failure/Retry, add-on reversed-item/draft/pending-save and reward duplicate-save recovery at phone/desktop widths. Remaining editor reconciliation is listed there.

Final continuation index: [21 November closeout and precise operational remainder](AUDIT_CLOSEOUT_2026_11_21.md).
