# Operational verification — 26 November 2026

Read-only production queries at 09:38 WAT close the new delivery-pass worker execution item. The first genuine scheduled success was 25 November at 23:00 WAT. There have been 11 successful executions through 26 November at 09:00 WAT, with zero failed executions. The four most recent runs report zero renewals, verifications, notices, issues and retryable errors, consistent with the disabled feature and no pass receipts. Revision 93aec202 includes the implementation. No heartbeat, purchase or due work was manufactured.

The preceding 24 hours show no failed cron execution. Existing jobs continue to run. Optional delivery-pass, multi-store and pickup flags remain false; no business price/store data was invented.

The owner-approved repeating engagement campaign executed its first morning slot at 09:00 WAT. Three push rows were accepted with real provider message references; 17 were marked skipped without a provider message reference. Acceptance is not device-display proof. Skipped recipients must not be counted as successful delivery. Aggregate checks identify provider external-account alias resolution failures for all 17 skipped accounts; their 20 stored device records have subscription UUIDs, not placeholder tokens. The exact device-level cause is not yet established. No extra campaign/test notification was sent.

The hourly delivery-pass frequency is a bounded shared sweep, not one job per customer. Expiry is independently checked during quote/order admission. Hourly limits renewal and unresolved-payment delays to roughly one scheduling interval. A slower interval is possible but also requires changing the current two-hour worker-health/renewal-consent check and updating the tests and operational wording. No interval was changed merely in response to a question about its rationale.

Actual pass-specific gateway execution remains unobserved: the audit runtime still lacks its Paystack test key. Shared Paystack implementation, database conservation, signed webhook routing and recovery checks remain closed for recorded cases. Scheduled reminder receipt/private tracking tap, future ambassador report/monthly executions and physical-device display remain observations to collect when eligible activity occurs.


## Final independent verification and remaining provider check

The v16 SDK registration suite passes: single-flight initialization, verified identity, explicit consent, backend-registration failure, denied permission, guest adoption, logout, bounded SDK timeouts and canonical-origin behavior. A fresh combined run of delivery-pass, shared Paystack transport, actual admin HTTP permissions, engagement campaign, notification-link/worker and durable outbox tests passes **156 tests**. No app code changed in this continuation; the already-passing full build was not repeated for documentation changes.

Two attempted read-only OneSignal subscription-identity lookups were not executed: automatic approval review failed because the account hit its usage limit. This is neither an HTTP provider response nor proof that those subscriptions no longer exist. Do not reinterpret the review errors as device/provider evidence or bypass review with another transport. Individual alias/device verification remains the precise open push diagnostic. No alias was reassigned, subscription deleted or duplicate campaign message sent.

Actual physical-device display/link tap, pass-specific test charge without a configured test key, genuinely due reminder receipt, future ambassador/monthly runs and owner store/price configuration cannot be manufactured by local tests. These remain separately recorded operational checks. The worker-execution and documented implementation checks are closed. Latest published checkpoint before this follow-up: 42e3873.
