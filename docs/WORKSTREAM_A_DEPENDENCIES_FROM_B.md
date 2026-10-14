# Requests from Workstream B to Workstream A

Integration branch: `audit/platform-ecosystem-b-20261013`, draft PR [66](https://github.com/canibless01/Holy-Grills-/pull/66). B continues the domain interfaces; A owns shared financial, HP, role/task and notification infrastructure. Use Test Two, `zaxdkrmzyibkvlsrgmvq`.

| A action | Acceptance evidence needed | B action after A returns |
|---|---|---|
| Coordinate backend deployment with live private-door migration | Updated event reader uses protected event_door_tokens; scans work after deployment. Six B migrations already applied once; do not replay. | Verify deployed event QR/customer/staff flows. |
| Provide idempotent recoverable positive event check-in HP contract | Durable ticket/check-in idempotency key; failure between scan and award recovers on retry; no duplicate grant under concurrent scans; documented pending/expiry/multiplier semantics. | Wire event handler and test positive HP and failure/retry. |
| Enforce notification_preferences in shared transport | Category/channel opt-outs suppress actual delivery; existing profile preference reconciliation; unrelated preferences preserved. | Verify preference UI → persisted values → recipient outcome. |
| Replace operational type throttling with request-aware deduplication | Separate catering/marketplace requests notify intended campus staff; replay of same request does not duplicate. | Exercise requests and staff inbox reload. |
| Recover interrupted blast work and consume deep links | Durable recipient processing/delivery outcomes; failed/sending recovery; cancellation races; action URL/reference honored; isolated actual email/push receipts. | Verify blast targeting/preview/schedule/cancel UI against worker outcomes. |
| Review public_campus challenge consumers | Signed non-super actors cannot override own campus; guest/public semantics retained. | Keep local department/level protection and rerun shared scope regressions. |
| Return existing payment/refund contracts | Wallet/HP/card conservation, mixed payments, webhook replay, provider failure and durable recovery; exact RPC/service signatures and migration names. Include marketplace bonus recovery when a purchase commits before bonus failure. | Implement domain event cancellation/refunds and paid marketplace transitions using these primitives. |

Return your commit/PR, callable signatures, task entry points, live migration names, failure/retry/concurrency evidence and unresolved provider blockers. Fetch current main, merge normally, and preserve both message registries, B routes, catering Kitchen tab, inventory-only kitchen edits and hostel/gate-only delivery edits. Do not modify B's owned fixture campus or its domain migrations without coordination.

B now verified free subscription allocation and competing buyers using campus-only release overrides, leaving global gates untouched. Paid purchase/provider/refund and bonus-failure recovery remain separate open loops. Newsletter transport and current storefront/media completion stay with A. Historical security closure remains B's review, with shared-helper changes coordinated with A.
