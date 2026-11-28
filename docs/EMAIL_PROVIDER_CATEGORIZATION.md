# Email categorization for review — 22 October 2026

Proposal only: no provider routing or quota was changed. User will consolidate the final split. Provider limits below are the user's stated limits, not independently verified plan terms. Inbox/Promotions placement is decided by receiving mail systems; neither vendor guarantees it.

| Recommended provider | Category | Messages |
|---|---|---|
| Resend | Account access/security | Verification, reset, password change, account deletion/deactivation/reactivation |
| Resend | Money/receipts | Wallet funding, refunds, cancellations, marketplace purchase receipts |
| Resend | Essential order access | Guest confirmation with tracking code/link; order confirmation and delivery; guest status updates; guest-account linking receipt |
| Resend | Tickets/fulfillment | Event registration/QR tickets, fulfilled reward confirmation |
| OneSignal | Rewards/engagement | HP gifts/transfers, expiry warning/applied, tier changes/grace/downgrade, birthday/graduation, inactivity reminders, squad invitations |
| OneSignal | Campaigns | Newsletters, promotional blasts, optional announcements |
| Resend or email-disabled | Staff operations | Monthly birthday report and requested event attendee exports; decide whether these need email at all |

Resend's stated 100/day should be reserved for access, money and essential guest tracking. OneSignal's stated 1,000/month also needs a budget and frequency limits; moving all engagement messages there does not make them unlimited. On vendor failure, do not blindly resend through the other vendor after an uncertain response: duplicates must be reconciled by a durable send identity. No quota fallback or automatic cross-provider retry is implemented by this proposal.

## Current notification email allowlist

The following 32 keys currently request email through get_notification_channels (subject to user preferences and provider readiness). This is configured channel behavior, not a claim every corresponding feature emits correctly or every provider delivery succeeded.

- `account_deactivated`
- `account_deleted`
- `account_reactivated`
- `birthday_bonus`
- `email_verification`
- `event_registered`
- `graduation_declared`
- `guest_order_claimed`
- `hp_decay_applied`
- `hp_decay_warning`
- `hp_gift_received`
- `hp_transfer_recipient`
- `marketplace_purchase`
- `order_cancelled`
- `order_cancelled_admin`
- `order_cancelled_user`
- `order_confirmed`
- `order_delivered`
- `order_refunded`
- `password_changed`
- `password_reset`
- `reward_fulfilled`
- `scheduled_order_cancelled`
- `squad_member_invite`
- `tier_downgrade`
- `tier_grace_period`
- `tier_upgrade`
- `wallet_funded_bank`
- `wallet_funded_card`
- `winback_118`
- `winback_70`
- `winback_95`

## Separate direct email paths

- Guest order confirmation/tracking credentials: order_service → send_email with guest_order_confirmed template.
- Guest delivery status emails: preparing, out-for-delivery and delivered according to the guest status mapping; raw Resend sender.
- Squad invitation emails, including order/squad helper routes.
- Event QR-ticket emails on ticket issuance/reissue and requested attendee export emails.
- Newsletter test/campaign delivery; campaign-provider override path exists.
- Scheduled monthly birthday report to campus staff.
- Supabase Auth signup confirmation, resend-verification and password-recovery emails are a separate Auth mail/SMTP configuration. App notification-provider defaults alone do not route them.

The notification sender currently resolves one transactional default or explicit override. Blasts have a separate default/per-blast override. Some raw email paths always call Resend. Routing the agreed categories consistently therefore needs changes at these boundaries, not just two environment keys.

Templates such as abandoned_cart, hp_earned, referral_completed and reward_redeemed exist in email.py. Template existence alone does not make a message an active email channel. The allowlist above also contains historical naming mismatches (for example graduation_declared versus graduation_hp); audit actual producers before counting those against a launch budget.

Source: app/services/notification_service.py, app/utils/email.py, app/services/order_service.py, app/services/newsletter_service.py, app/routes/orders.py, app/routes/events.py, app/tasks/scheduled.py and Supabase Auth calls in auth_service.py.
