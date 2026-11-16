# Event cancellation, rescheduling and customer ticket QR — 10 November 2026

## Behavior and use

Open Admin → Events → Open event workspace → Schedule and cancellation. Campus admins act on their own campus; super admins retain global authority. Organizers can see updates and attendance data but cannot approve their own financial cancellation or schedule change.

Rescheduling validates future WAT start/end times, venue and a 10–500 character reason. It is available before check-in begins. Existing tickets and agreed organizer earnings remain unchanged; any configured ticket QR expiry follows the revised date. Member notices and guest emails are captured with the schedule transaction. Superseded unsent notices are skipped, and newly prepared receipt emails use the current event details.

Cancellation records a private approved operation and stops new tickets and admission. Unused paid tickets receive the ticket amount paid back: account purchases return to the Holy Grills wallet, with spent HP restored; guest card refunds use the existing durable provider-refund queue. Separately charged payment-provider fees and checked-in tickets are excluded. Free unused tickets are cancelled and their seats released. Refund/cancellation status is visible in existing event administration/refund controls. A completed bank transfer to an organizer is never silently reversed: the existing overpayment/adjustment display remains authoritative.

Pending payments are not labelled paid or refunded before confirmation. If a charge is confirmed after cancellation, the payment and refund receipt commit together. If reservation expiry already returned wallet/HP and released capacity, only the newly received card amount is refunded. Retried callbacks do not return wallet/HP or release capacity twice. The recorded cancellation approval remains effective if the original approving account is later deactivated or changes role/campus.

Requests retain a UUID and displayed event version. Identical retries return the original receipt. A competing edit is rejected rather than overwriting another session; the frontend refreshes stale details. A database trigger prevents silent date/venue changes to booked events and direct manipulation of lifecycle metadata outside the checked operation.

The customer ticket page now displays a real locally generated PNG QR, using the same `hg-event:<event UUID>:<ticket UUID>` payload as emailed/PDF tickets. The QR endpoint requires account ownership or the original guest email plus ticket UUID. Ineligible tickets receive no QR. Responses use `private, no-store`; private ticket credentials never go to an external QR-image service or public media storage. Guest venue self-check-in includes the opaque ticket ID and does not promise account HP. Pending reservations no longer appear as confirmed tickets, paid events are not labelled free merely because they use tier prices, and refund returns do not announce a ready entry ticket.

## Verification

- Full backend regression before the final private-QR addition: 1,430 passed. The QR/operations/outbox contract run passed 89 tests; final integrated regression/build results are added in the completion entry.
- Native Chromium at 393/1280px passed WAT fields, double-click suppression, lost-response replay with the same request/version, stale refresh, cancellation confirmation and policy, customer cancellation presentation, and organizer restrictions.
- Native customer checks passed a real decoded PNG, owner/guest request identity, QR-read failure/Retry, unpaid reservation presentation and cancellation refund returns. A final guest door-check-in case verifies the ticket ID accompanies venue proof.
- Independent PostgreSQL sessions on an isolated local schema/function copy passed six identical concurrent reschedules, competing date edits with one winner, cancel/payment and cancel/admission races, callback replay, and client process exit before commit. No partial operation, refund or notice survived interruption. This is not a claim that the local copy reproduces all platform RLS or foreign keys.
- Fresh Supabase BEGIN/ROLLBACK matrices passed the operations loop, atomic admission, paid refunds and organizer settlement after migration. Cases include preserved financial snapshots, member/guest notices, stale/direct-write denial, late/expired payments, changed approving-account role/campus, financial-error rollback and service-only grants. All synthetic fixtures rolled back. No genuine event was cancelled/rescheduled, no real notification was sent and no bank/provider refund was initiated by the audit.
- TypeScript, targeted ESLint, central-message resolution, client/SSR build and seven-route prerender passed before the final QR addition; these are repeated for the completed source.

## Schema and remaining scope

Applied once as `20261109211224_event_operational_changes`; the repository filename matches Supabase history. Existing private review, ticket refund, notification and dispatch records are reused. The private review row gains only the lifecycle receipt history and approving cancellation actor needed for replay and late-payment recovery. New helpers use invoker security and service-only execution. The same five pre-existing security-advisor categories remain tracked separately.

Worker/Cron hosting is unchanged. Durable queues require the existing recovery worker for a lost immediate wake; real provider delivery/refund settlement and handset-camera acceptance remain operational checks. Exceptional ticket resend/self-service recovery and configurable admission-opening times remain separate follow-ups. Group purchases, ticket transfers and delegated door-staff roles remain deferred.

## Final integrated verification

After preserving main's ambassador-notice and wallet-recipient changes: **1,474 backend tests passed**. TypeScript, targeted ESLint and the complete client/SSR/seven-route production build passed. Both 393/1280px native suites passed the event-operation controls and the real customer QR, including guest door proof carrying the ticket UUID, unpaid-state presentation and refund return handling. Every new helper/trigger has one definition and no anon/authenticated execution privilege.

Non-cancellation payments arriving after an expired reservation remain flagged for manual refund/reissue; automating that separate recovery case is still open. This batch does not silently reactivate those tickets or claim their recovery is complete.

The final rebase also preserves main's wallet analytics work. TypeScript and 119 targeted event/QR/notification/wallet-analytics contracts passed after that integration.
