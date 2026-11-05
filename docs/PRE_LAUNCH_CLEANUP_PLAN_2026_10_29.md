**Reset update — 30 October:** the authorized database cleanup is now completed and independently verified. See [completed reset and preserved configuration](PRE_LAUNCH_RESET_COMPLETED_2026_10_30.md). Earlier “not executed” notes below are historical. Real owner/admin setup and final release smoke remain.

# Pre-launch reset preparation — 29 October 2026

The user has identified the current accounts and transactions as test data and requested a clean production start, while preserving deliberately entered FUTA menu/storefront/reviews/rewards and other real configuration. This checkpoint prepares the reset; **no account, order, payment, content or Cloudinary asset has been deleted**.

## Read-only inventory

Current snapshot: 62 Supabase Auth accounts, 54 application profiles, 111 orders (13 guest), 25 payments, 20 menu items, 66 storefront sections, one newsletter subscription and three stock-ledger entries. Counts include mixed campus/global/test content; they are not permission to delete all menu or storefront rows. There are eight Auth accounts without a profile. The read-only query is [cleanup inventory](data/prelaunch-cleanup-inventory.sql).

A profile-only reset does not free every email. The corresponding `auth.users` identity must also be removed through supported Auth administration. Supabase identities/sessions then cascade. An existing test account can currently log in or reset its password, but its email cannot represent a second distinct signup until its Auth identity is removed. Guest checkout email records are separate from Auth accounts.

## Preserve and compare before/after

- Preserve FUTA Main Campus and all intentionally entered menu categories/items/variations/add-ons, recipes, prices, images, stock settings, storefront sections/banners/reviews, tiers, reward definitions, challenge definitions, operational configuration, promo/campaign definitions and public contact/social configuration.
- Preserve all 51 newly supplied FUTA departments and their ten school mappings, academic levels, intended gates/hostels/calendar, hours/capacity/fees and feature flags.
- Preserve global content/configuration unless an exact audit-owned record is identified. Preserve unlabelled non-FUTA configuration pending review: `Lagos Campus` is active and is not explicitly labelled audit.
- Record exact protected row IDs, counts and content fingerprints in a private backup/manifest before mutations. Exclude mutable author pointers and compare the actual content, not only total counts. Keep credentials, Auth exports and private customer fields out of Git and chat.
- Do not delete Cloudinary files broadly. The user's uploaded media is intentional; any old audit asset needs exact ownership/provenance before deletion.

## Reset execution order to implement and rehearse

1. Pause public signup/order submission and dispatch during the reset; finish or stop audit provider activity first. Take a recoverable backup and exact protected-content manifest.
2. Build an explicit dependency-ordered transaction reset for orders/items/logs, payments/webhook receipts, batches/assignments, wallet/HP ledgers and top-ups, carts, addresses, reward claims/credits/spins, streaks/milestones/challenge completions, referral/squad/ambassador activity, test ticket/marketplace/catering activity and notification/subscription/queue records. Include guest orders and newsletter contact records; deleting profiles alone leaves orders/payments as anonymous historical rows.
3. Handle restrictive profile foreign keys before Auth deletion: `stock_ledger.logged_by`, exclusive-spin fulfilments, cart free-side selections, marketplace reviews and ambassador creator/reviewer/grant references currently have NO ACTION references. Clearing transaction history is different from deleting programme definitions. Preserved rules/milestones/promo messages that reference a test author need a deliberate replacement/nullable-author strategy; do not delete legitimate rules to satisfy a foreign key.
4. Revoke test sessions and remove the intended Auth accounts using supported admin operations, so those emails can be reused. Never TRUNCATE public/auth schemas or use uncontrolled CASCADE. Existing JWTs need server-side profile/session checks until expiry; account deletion alone is not a universal access-token invalidation guarantee.
5. Reconcile preserved definitions' usage/stock/capacity counters from the actual remaining history and intended launch settings. Do not blindly set remaining stock to zero or reset a legitimate configured quota. Test purchases/grants can affect these counters even after activity rows are removed.
6. Bootstrap the real owner account and promote it to super admin using the trusted backend/SQL procedure. All old accounts are test according to the user; retain no hidden test admin. Update `AMBASSADOR_SYSTEM_ACTOR_ID` in the backend runtime to the new real super-admin UUID if configured. Re-tag real staff under the intended campuses.
7. Verify protected IDs/content, zero remaining test identities/transactions, reusable test email, and one bounded real-owner signup/login/admin-access smoke. Confirm old guest tracking proofs and old test callbacks cannot revive an erased order or issue a credit. Check OneSignal subscriber identity association separately from database rows.
8. Remove/deactivate only explicitly identified audit campuses/content, then reopen signup/orders. Avoid creating persistent replacement test fixtures after the final reset.

## Information needed for production reference configuration

- Owner confirmed no 600 level. Postgraduate school/department and PG level are now added for FUTA alongside 100–500.
- Owner confirmed West Gate, South Gate and North Gate. All have stored coordinates; North was aligned to a published study/map reference. West/South still need reliable entrance-pin verification; confirm fees as well.
- Confirm the 13 hostel names and coverage/fees. Current names include both `FUTACOOPS` and `FUTASCOOPS Hostel`; keep both until the owner confirms whether they are distinct.
- Owner confirmed session began Monday, 26 October 2026; the existing semester start is corrected. Its stored 31 December end date still needs confirmation; no new end date was invented.
- Confirm whether Lagos Campus is intended for launch or retained configuration. Audit-labelled campuses are separately identifiable.

This is an execution plan and inventory, not a completed cleanup or a new automatic deletion job. The user asked to prepare the reset alongside finishing launch fixes; none of the destructive steps has run at this checkpoint.

Delivery-location integrity follow-up: audit-only hostel/gate/campus cleanup must respect the new cross-campus-link guard. Unlink/remove exactly owned audit hostel children before moving/deleting their gate/campus; do not disable the guard or alter protected FUTA relationships. These rules do not authorize broad content deletion.
