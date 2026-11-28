# Launch database reset completed — 30 October 2026

Executed at the owner's explicit request to remove all current test users/transactions and every non-FUTA campus, including Lagos, while preserving intentional content and operating configuration. This supersedes earlier documents saying cleanup had not run.

## Removed

- All **62 Supabase Auth accounts**, using the supported Admin API with hard deletion; all **54 profiles**. Final direct database checks: Auth users **0**, Auth identities **0**, Auth sessions **0**, profiles **0**. Their emails are no longer reserved by the old Auth accounts. No replacement test signup was created.
- All **112 orders**, **25 payments**, **54 wallets**, their test ledger/reward/cart/address/streak/referral/squad/ambassador activity, delivery assignments/batches and notification/subscription/log records. Every table classified as test activity is verified empty.
- **Nine non-FUTA campuses**, including Lagos. Only `futa-main` remains. Removed those campuses' configuration rows before deleting the campus, preventing `ON DELETE SET NULL` from leaking their test content into global scope.
- Explicit test content, including **two menu items**, **33 storefront records**, **six rewards**, **three spin prizes**, **eight free-side items** and the one audit-only milestone. Dependent catalog test rows followed their test parents.

## Preserved and verified

| Configuration/content | Remaining |
| --- | ---: |
| FUTA campus | 1 |
| Genuine menu items / categories | 18 / 5 |
| Add-on groups / add-ons | 18 / 135 |
| Variation groups / options | 16 / 64 |
| Storefront entries / banner | 33 / 1 |
| Reward definitions / free-side choices / exclusive spin prizes | 30 / 4 / 7 |
| Global release feature flags | 16 |
| System settings / FUTA kitchen settings | 95 / 10 |
| Real milestones | 9 |
| HP tiers | 4 |
| Ordering windows / delivery windows | 7 / 7 |
| FUTA gates / hostels | 3 / 13 |
| Department rows, including the 52 FUTA options and existing global reference rows | 55 |
| Academic levels / active academic calendar | 6 / 1 |

The real milestones include app installation, enabling push notifications, completing both, and referral milestones. No genuine milestone, PWA/install/push configuration or global feature flag was removed or toggled. The three removed flag rows were overrides for deleted audit campuses; the 13 removed system-setting rows were scoped to deleted campuses. Challenge configuration was preserved; the standalone challenges table already had zero records. Configured login/order-streak rewards, measurement units, operating hours/retained overrides and the owner's ambassador caption also remain.

Only proven consumption from two erased test Coleslaw redemptions was restored, bringing that retained reward's stock from 998 back to 1000. Other configured stocks, prices, fees, capacities and settings were preserved. Test-author pointers were detached; content and images were preserved.

## Safeguards and evidence

- Private pre-reset snapshot of all **135 public tables** plus the 62 Admin API user records, under `/workspace/work/prelaunch-reset-2026-10-30/` (directory 0700, data files 0600). These private records are not committed to Git. Auth Admin list initially failed because two old test Auth rows had null token-string fields; normalized those nulls to empty strings, then successfully exported and deleted all accounts through Auth administration. No password or token was printed.
- Dependency-ordered reset rehearsed inside a transaction and rolled back. The final transaction used the same reviewed statements, locked application tables and asserted protected row counts/content hashes before commit. Only actual nullable FK cycles were broken; constraints/triggers were not disabled.
- Independent post-reset REST snapshot of every public table compared against the protected manifest: **all protected records match**, with no mismatched tables and no nonempty test-activity tables.
- Preserving the owner's ambassador caption required migration `20261030093022_preserve_ambassador_copy_when_author_is_deleted.sql`: nullable `created_by` with a single FK using `ON DELETE SET NULL`. The live migration version and nullable/FK state were verified; no new table, function, policy or role grant was added. Security advisors were read; this is not a claim that unrelated historical advisory notices are all resolved.
- Removed test image references from the database. **Physical Cloudinary objects were not deleted.** Twenty-seven Cloudinary URLs appeared only in deleted records; the exact candidate list is private. No broad Cloudinary deletion was attempted without configured media credentials/proven asset ownership.

## After reset

The first genuine owner account must be registered and deliberately promoted to super admin. There is no hidden surviving test administrator. Set backend `AMBASSADOR_SYSTEM_ACTOR_ID` to the real authorized actor UUID when that account exists. Existing clients may need to sign out/reload; the backend refuses requests from erased profiles and the old Auth sessions are gone.

No new persistent test accounts/orders should be created as a casual smoke test. This reset does not close the remaining functional audit, deploy cron/workers or claim device push/PWA installation verification.
