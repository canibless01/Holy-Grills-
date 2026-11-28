# Provider checks still required before launch

These are **unverified external actions**, not passed tests. Use a fresh environment with the actual provider bindings and outbound access. Never commit credentials or substitute a local fixture for provider evidence. Current application, role and database checks are recorded separately in [progress](ECOSYSTEM_AUDIT_PROGRESS.md).

The local audit runtime currently has no Paystack secret-key binding. Its enforced custom outbound hosts remain Render and Supabase; Paystack and Cloudinary are absent. A different environment can have different readiness. Check that environment rather than repeatedly editing this runtime's policy snapshot.

## Paystack sandbox

Configure `PAYSTACK_SECRET_KEY` with the test secret in the **backend**, allow `api.paystack.co`, and set `FRONTEND_URL` to the frontend being tested. Configure the Paystack test webhook URL as `<backend>/api/webhooks/paystack`. Paystack signs with the account secret key; remove a stale conflicting `PAYSTACK_WEBHOOK_SECRET` override or ensure it matches. Browser access must also permit the Paystack checkout destination. No frontend secret key is needed for hosted checkout.

| ID | Single action to perform | Required result | Current evidence |
| --- | --- | --- | --- |
| PAY-01 | Place one full-card order and complete a Paystack test-card payment | Hosted Paystack checkout opens for the quoted total; return verifies on the backend; one paid `payments` row and one order; order remains received until kitchen action | Native UI, server verification contract and real SQL passed using an explicitly controlled local gateway fixture; real Paystack unverified |
| PAY-02 | Return without paying, reload the saved order, then use its Pay button | Honest payment-required UI; no paid status before success; the same provider reference/link resumes without creating another order | Native fixture loop passed; real cancellation/session-resume behavior unverified |
| PAY-03 | Pay a split order with a known wallet contribution | Wallet deducted once; Paystack charges **only the card remainder**; receipt total equals wallet plus card; one paid ledger record | Native fixture and rollback SQL passed; actual gateway charge unverified |
| PAY-04 | Complete a guest card payment and reload its confirmation/tracking link | Guest token grants access; payment completes without account login; a wrong token or unrelated account cannot initialize/verify it | API guest admission plus native guest payment/reload passed with fixture; real provider round trip unverified |
| PAY-05 | Deliver the real signed `charge.success` webhook while returning from checkout, then resend that event | Signature accepted, callback/webhook agree, one paid receipt, no repeated wallet debit; order does not auto-start preparation | Signed local HTTP fixture, failed-event retry and concurrent callback/webhook plus six replays passed; real delivery/signing unverified |
| PAY-06 | Temporarily interrupt gateway access while initializing or verifying an order, restore it and retry | Order stays saved; no false paid status; recoverable error; retry recovers the same reference/receipt | Missing-key native recovery and application contracts passed; real provider/network ambiguity unverified |
| PAY-07 | Initialize wallet card funding, complete the sandbox charge and reload Wallet | The intended audit account gets one top-up for one reference, including webhook redelivery | Wallet transaction regressions exist; complete provider loop remains open |

Use isolated audit actors and a fresh audit checkout intent. Capture the order ID, reference, gateway test outcome, quote, wallet deltas and payment row count. Do not infer payment from a callback query string, an HTTP 201 order response, the provider API's outer `status`, or a success toast. The backend must verify the transaction's successful status, NGN amount, order/user/campus metadata and reference. See [Paystack verification documentation](https://paystack.com/docs/payments/verify-payments/) and [Transactions API](https://paystack.com/docs/api/transaction/).

## Cloudinary

Configure backend Cloudinary credentials and permit `api.cloudinary.com` and `res.cloudinary.com`. Images remain on Cloudinary only.

| ID | Single action to perform | Required result | Current evidence |
| --- | --- | --- | --- |
| IMG-01 | Upload an actual image from the admin storefront editor | Signed Cloudinary upload succeeds; save uses its URL; bytes decode after reload | Signer/configuration and URL persistence tested; upload/decoded bytes blocked |
| IMG-02 | Upload desktop/mobile images for two carousel slides with different copy and CTAs | Each image, crop, eyebrow, text and CTA changes together on its public placement | Three-slide configuration and native navigation tested; real media bytes blocked |
| IMG-03 | Replace and remove an owned audit upload using the supported editor/provider path | Saved references update correctly; exact owned asset cleanup is confirmed; unrelated images remain | Provider replacement/deletion unverified |
| IMG-04 | Export an order/referral share card with a Cloudinary template | Downloaded image includes the selected template and actual order/referral data | Resolver/captions and failed-download Retry tested; successful rendered-image export blocked |

## Email and workers

| ID | Single action to perform | Required result | Current evidence |
| --- | --- | --- | --- |
| MAIL-01 | Send one newsletter preview to an owned test mailbox | Provider accepts and mailbox receives the intended subject/body and unsubscribe headers | Preview failure now returns recoverable 503; real delivery unverified |
| MAIL-02 | Run one queued audit newsletter campaign through the real worker | Intended subscribed audit recipient receives once; unsubscribed/foreign recipients excluded; delivery records reflect the run | Subscription/queue/view/cancel/unsubscribe tested; actual worker/provider execution unverified |
| MAIL-03 | Place a guest test order and inspect its tracking email | Correct guest order/token link arrives and opens the intended order | Email provider delivery remains open; a saved template or URL alone is not proof |

## Keep functional gaps separate from credential blockers

The wider audit is unfinished. Free-side atomic fulfilment, overlapping multiplier awards, physical reward delivery choices, auxiliary reward/job recovery and other assigned families remain in Workstream A. Guest refunds currently require manual handling. A provider success arriving after cancellation needs a defined reconciliation/refund path. A process dying while a webhook remains `processing` needs operational recovery; in-flight retries now return 503 rather than falsely acknowledging completion, and explicitly failed events can retry. These are **open implementation/audit items**, not actions that become verified merely by adding a key. Neither this document nor a fixture pass approves the complete ecosystem for launch.
