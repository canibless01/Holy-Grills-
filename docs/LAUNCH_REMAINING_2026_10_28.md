# Launch checkpoint — 28 October 2026

The eight rows below are remaining cases within implemented features, not eight unbuilt features. No entire A–Z category is yet signed off. Passing the listed automated/database cases does not guarantee there are no undiscovered defects.

## Completed in this checkpoint

Side groups on menu-item details now use native compact dropdowns. Each required side slot remains independent; optional clearing, unavailable-option refusal, price adjustments and the existing cart payload are retained. Current Supabase catalogue confirms 13 groups named “Choose your side”, all single-choice, which match the changed renderer. Other modifier layouts retain their existing behavior.

Controlled mobile browser: four side dropdowns, required-selection blocking, unavailable options disabled, all four IDs present in the cart, and correct 1030 total for 1000 food + 30 selected-option charges. TypeScript, changed-page lint and production build pass.

Real Supabase admission scenario (tests/sql/capacity_two_order_admission.sql): kitchen/window capacity two; two orders created through the actual atomic checkout function and wallet debits; third same-day admission refused with no debit/order; overflow admitted for tomorrow; increasing window capacity alone respects the independent daily ceiling; increasing daily capacity moves the overflow to today, changes its linked delivery window and emits complete notification time metadata; wallet remains charged once; move-up replay is a no-op. All fixtures roll back. Service tests separately verify the automatic next-slot search chooses tomorrow when two orders fill today and that admin capacity updates invoke the move-up/notification path. This is real database financial/admission evidence plus application integration tests, not a completed live gateway/browser ordering exercise.

Multi-gift campaigns are implemented and tested: scoped editor, four gift types, eligibility/timing, immutable once-per-user terms, checkout choice/reservation, cancellation/restoration and expiry refusal. They are no longer an unfinished feature on the launch list.

Ambassador coverage includes tagging/untagging, student/community-manager/admin boundaries, promo targeting/personalization, rules/progress, grants, attribution, discount checkout and early/post-preparation refunds. Actual authenticated RLS and real rolled-back financial cases pass. WhatsApp sharing uses the native share sheet where supported, with explicit copy/download fallback. Seen/shared measurements are manually recorded by staff; they are not WhatsApp delivery/read telemetry. Actual device sharing remains an acceptance check.

Signup's local-import crash, missing-field messages, academic-list retry and optional marketing-consent persistence are repaired and covered by route/browser/database tests. A fresh live signup through delivered verification email has not been executed in this checkpoint.

## Remaining launch work

| Area | Remaining executed evidence/work |
| --- | --- |
| Payments | Provider chat now verifies PAY-01–07 (card/split/guest/funding/returns/webhooks and controlled interruption with real recovery). Remaining: wider ambiguous timeout/late-payment/refund variants and guest provider-refund operations; see fresh-provider results |
| Promos/refunds | Wider combinations of HP, squad, locks, campaign and earned rewards. Promo/meal quota, scope, partial/full refund and reuse corrections now pass |
| Physical rewards | Menu-linked/special reward variants and legacy missing-snapshot handling. Generic reward checkout → kitchen → rider → delivered/unclaimed → partial/full refund is now verified |
| Delivery | Wider delivery exceptions and nonfinancial reward-hook outages; ambiguous legacy financial recovery requires review. Financial HP/unlock/welcome/squad recovery and admin re-drive now pass. Rider settlement and generic attempted/unclaimed/refund cases pass; provider chat verifies map/search/save, with native rider-map opening still a device check |
| Messaging | Durable quota counters/dispatch/retries; actual OneSignal device delivery/click; deployed worker execution/recovery. Literal notification destinations, safe browser navigation, push retry deduplication and Beat registration now pass |
| Storefront/sessions | Final content/device presentation matrix and deployed returning-user performance. Provider chat now verifies real Cloudinary persistence/replacement, tier containment and share-card composition; resume recovery is fixed |
| Admin/roles | Remaining per-action campus/global/role and error/concurrency matrix beyond the targeted verified paths; real ambassador share handoff; fresh live signup/email confirmation |
| Chrome installation | Actual-device native Chrome entry remains unresolved. Provider chat verifies deployed technical prerequisites and returning metadata; first-install reload/header fixes are preserved. See fresh-provider results and [PWA evidence](PWA_CRITERIA_EVIDENCE_2026_10_28.md) |

Current physical-reward handover, refund review, promo conservation and capacity-hours evidence: [28 October follow-up](PHYSICAL_REWARDS_REFUNDS_CAPACITY_EVIDENCE_2026_10_28.md). Rider settlement recording is also verified in [settlement evidence](RIDER_SETTLEMENT_EVIDENCE_2026_10_28.md). Next related cases: remaining reward/stacking variants and messaging/payment checks. Provider/device checks remain explicitly distinguished from controlled transport tests. Database cleanup remains paused.

Notification destinations, OS push URL/idempotency, worker registration and the deployment evidence gap: [messaging follow-up](NOTIFICATION_LINK_WORKER_EVIDENCE_2026_10_28.md). Current backend suite: 707 passed.

Community-manager workspace/navigation, explicit admin batch entry, rider batch collection and earnings reflection, global hero, helper privilege hardening and the precise Auth/application-email split: [latest checkpoint](COMMUNITY_WORKSPACE_BATCH_LAUNCH_CHECKPOINT_2026_10_28.md). Backend suite now 708 passed. Delivery auxiliary-reward hook outage recovery remains open; do not infer it from normal delivery evidence.

Current primary-chat checkpoint: [financial delivery reward recovery](DELIVERY_REWARD_FINANCIAL_RECOVERY_2026_10_28.md), backend suite 725 passed. This supersedes the earlier financial-auxiliary recovery gap; tier/streak/milestone/gift hook outage recovery remains open. Provider/device status is maintained in [the other chat’s results](FRESH_ENV_PROVIDER_PWA_RESULTS_2026_10_28.md).

29 October continuation: [ordering-streak recovery](ORDER_STREAK_RECOVERY_2026_10_29.md) is now atomic and re-driven for already-credited deliveries. Backend **728 passed** and real database failure/retry/year-boundary cases passed. Remaining auxiliary hooks are tier/milestone/login-reclamation/legacy gift recovery; do not infer their completion from the streak fix.

Current 29 October [launch-blocking versus later-work classification](LAUNCH_PRIORITY_STATUS_2026_10_29.md), [FUTA catalogue/signup evidence](FUTA_SIGNUP_REFERENCE_DATA_2026_10_29.md) and [cleanup preparation](PRE_LAUNCH_CLEANUP_PLAN_2026_10_29.md) are now available. The broader admin audit remains incomplete. No cleanup was executed.
