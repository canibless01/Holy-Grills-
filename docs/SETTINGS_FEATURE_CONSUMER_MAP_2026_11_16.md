# Current settings and feature consumers — 16 November 2026

Reconciled against the live metadata snapshot and current main. This supersedes the old October stored-value table as a consumer list; **no live amounts, prices, switch states or stored values were changed**.

The complete [101-key CSV](audit/database_2026_11_16/settings_consumers.csv) records type, public/private exposure, campus/global scope and Python/React/SQL reader references. It contains no setting values or recipient addresses. A source getter alone is not a working consumer: confirmed obsolete keys and uncalled frontend getters are explicitly marked **Stored legacy / unused getter**, and the Settings page now shows a warning on those rows. They remain stored rather than being deleted or silently connected to financial rules. The first-order physical-gift implementation is separately marked legacy/gated, not a new welcome reward.

Current money/reward settings resolve through their recorded domain consumer, including transactional SQL. Generic typed editor, scope and version/error behavior is verified in `SETTINGS_SYSTEM_RECOVERY_2026_11_15.md`; the catalog is not a claim that every possible numeric value has separately been exercised. Existing domain conservation/recovery tests remain the semantic proof.

Important distinctions:

- Signup HP/free-side configuration differs from first-delivered-order HP. Ordinary wallet top-up HP/minimum differs from card funding minimum and automatic-funding consent/fee policy.
- Weekly login completion, the order-streak reward catalogue, per-tier/per-milestone perks and issued reward/prize snapshots remain their actual authorities. Obsolete daily HP, old rank-side, generic redeem-rate and old global spin-cap keys do not override them.
- Private transfer business settings are evaluated server-side, even when the student's database role cannot read that setting. The form receives the authoritative minimum from eligibility; the user database client still scopes delivered-order reads. Zero remains a real configured value.
- Currency remains the current NGN implementation; dormant currency-label getters do not create multi-currency support. The app's API/Supabase environment remains the connection authority, not an old stored project URL.
- Notification delivery uses canonical template/category preferences, channel opt-outs and the existing router. Provider defaults are dynamic `email_provider_{scope}_default` readers; those two keys are not falsely classified as unused merely because their names are constructed at runtime.
- No unsupported stored key was repurposed to change current rewards, prices, caps or payment charges. Such a product change needs its own implementation.

## All 18 live flag names

Global and existing campus overrides retain their effective lookup semantics. The admin flag API edits global release rows; campus overrides are visible read-only. Disabled flags remain disabled. The previous 17-flag tracing/disabled-endpoint proof remains valid; `birthday_celebrations` adds the eighteenth SQL consumer.

| Flag | Actual consumer / boundary |
|---|---|
| abandoned_cart_nudge | cart_recovery/guest-cart capture, preference/payment/activity/preparation deadline checks |
| birthday_celebrations | `hg_process_birthday`: same-campus department notices/gift links, separate from birthday HP |
| birthday_hp | birthday service computes reward; annual SQL receipt prevents repeat payment |
| events | event admission/customer routes; existing tickets retain recovery ownership |
| exclusive_spin | spin access and grants; issued physical/automatic benefits retain their own receipts |
| flash_redemptions | reward flash admission; existing redemption snapshots remain authoritative |
| free_side_credits | side-credit access/checkout; signup grant has its own configured rule |
| hall_of_fame | leaderboard rollover/Hall-of-Fame access and private prize fulfilment |
| hp_expiry_warnings | scheduled expiry warning consumer, separate from the underlying decay rules |
| hp_multiplier | existing HP multiplier consumer/expiry bounds; no change to live multiplier state |
| hp_transfer | authenticated eligibility and same-campus atomic HP transfer; completed-intent replay remains readable |
| leaderboard_prizes | rollover reward generation and persisted physical-prize handover |
| marketplace_general | catalogue/purchase access; already-issued purchases keep recovery/ownership rules |
| referral_milestones | optional referral milestones; ordinary first-paid-order referral payout is separate |
| scheduled_orders | future admission/calendar choice; paid admitted orders retain due-day preparation rules |
| squad_orders | squad participation/order admission and existing benefit snapshots |
| subscription_codes | gated code inventory/purchase branch; not automatic wallet funding |
| wallet_transfer | same-campus private transfer RPC, configured limits and owned receipt recovery |

## Where configuration lives

System Settings/domain admin panels provide the business controls referenced in the CSV. Railway API/worker/beat environment provides service credentials, fallback config and schedule-scan tuning. Vercel `VITE_*` values provide browser/build API origin, Maps and OneSignal configuration; they need a frontend rebuild. Supabase Auth owns SMTP/templates/autoconfirm/password controls. The API's optional Google review link/Place ID configuration retains its separate completed evidence. No new environment variable, periodic scan or service was introduced by this review.
