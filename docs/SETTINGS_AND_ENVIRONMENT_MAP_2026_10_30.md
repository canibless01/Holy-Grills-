# Configuration map — active database figures and environment fallbacks

The signup gift is **system_settings.signup_bonus_hp = 50**, editable in Admin → System Settings. `SIGNUP_BONUS_HP` on Render is only its fallback if the database key is absent/unreadable. An existing database value (including 0) wins over the environment. The one-side welcome rule is `signup_free_side_config = {"enabled":true,"credits":1,"validity_days":60}`. Both apply to every eligible new signup, not only the two repaired accounts.

`welcome_bonus_hp` is a separate **first delivered order** gift; it is not the signup setting. Do not change it expecting signup HP to change. Signup gifts are active HP and are not event-multiplied.

## Edit in the application

- Admin → System Settings: signup/first-delivery/review/referral rewards, food earn/unlock settings, multipliers, limits and switches listed below. Numeric values are read from the live table. Some legacy settings have no runtime reader; see the caveats after the table.
- Ordering hours/windows: daily opens/cutoff and date exceptions; FUTA is 00:00–16:00 Africa/Lagos for all seven weekdays.
- Delivery times: FUTA 19:30–20:30, linked separately to ordering windows.
- Kitchen capacity: `kitchen_settings.daily_order_capacity`, currently 60 for FUTA.
- Delivery setup: gate/hostel fees, distance pricing and delivery radius, in their delivery/kitchen configuration panels.
- Loyalty tiers: tier thresholds, earning multipliers and tier perks; side credits and exclusive-spin allowances are separate from the signup rule.
- Menu/rewards: prices, add-ons, variations, reward costs and availability in their own admin sections.

### Stored numeric/boolean system settings

| Key | Current stored value | Scope |
| --- | --- | --- |
| `ambassador_attribution_window_days` | `7` | Global |
| `ambassador_expected_weekly_shares` | `4` | Global |
| `ambassador_meal_discount_default_max` | `3000` | Global |
| `ambassador_meal_discount_default_validity` | `14` | Global |
| `birthday_hp` | `150` | Global |
| `daily_checkin_hp` | `5` | Global |
| `decay_onset_days` | `120` | Global |
| `decay_rate_monthly` | `0.1` | Global |
| `event_checkin_hp` | `40` | Global |
| `event_max_discount_pct` | `0.25` | Global |
| `exclusive_spin_free_delivery_cap` | `1500` | Global |
| `exclusive_spin_validity_days` | `30` | Global |
| `first_order_gift_enabled` | `false` | Global |
| `flash_discount_pct` | `0.5` | Global |
| `flash_max_qty` | `5` | Global |
| `free_delivery_threshold` | `3000` | Global |
| `free_side_credits_validity_days` | `60` | Global |
| `graduation_min_level` | `400` | Global |
| `hof_induction_threshold` | `4` | Global |
| `hp_bundle_min_purchase` | `100` | Global |
| `hp_bundle_price_per_hp` | `5` | Global |
| `hp_liability_value` | `0.185` | Global |
| `hp_multiplier` | `1` | Global |
| `hp_per_naira_food` | `0.1` | Global |
| `hp_redeem_rate` | `100` | Global |
| `hp_rounding` | `50` | Global |
| `hp_transfer_min_amount` | `10` | Global |
| `hp_transfer_min_orders` | `3` | Global |
| `hp_unlock_ceiling_pct` | `0.35` | Global |
| `hp_unlock_rate_pct` | `0.3` | Global |
| `leaderboard_prize_rank1_sides` | `3` | Global |
| `leaderboard_prize_rank2_sides` | `2` | Global |
| `leaderboard_prize_rank3_sides` | `1` | Global |
| `login_streak_hp` | `2` | Global |
| `low_code_inventory_threshold` | `5` | Global |
| `marketplace_purchase_hp` | `50` | Global |
| `menu_hp_multiplier` | `1` | Global |
| `min_hp_redeem` | `100` | Global |
| `min_topup_amount` | `500` | Global |
| `min_withdrawal_amount` | `1000` | Global |
| `monthly_hp_cap` | `1000` | Global |
| `monthly_pending_cap` | `900` | Global |
| `notification_daily_cap` | `20` | Global |
| `notification_gap_minutes` | `30` | Global |
| `order_lock_default_discount_pct` | `10` | Global |
| `order_lock_max_discount` | `50` | Global |
| `order_lock_max_reschedules` | `1` | Global |
| `programme_cost_target_pct` | `0.025` | Global |
| `push_subscribe_hp` | `25` | Global |
| `pwa_install_hp` | `50` | Global |
| `pwa_push_bonus_hp` | `75` | Global |
| `referral_hp` | `75` | Global |
| `review_hp` | `20` | Global |
| `reward_margin_share_food` | `0.4` | Global |
| `reward_margin_share_merch` | `0.5` | Global |
| `share_prompt_hp` | `25` | Global |
| `signup_bonus_hp` | `50` | Global |
| `social_share_hp` | `25` | Global |
| `squad_delivery_discount_enabled` | `true` | Global |
| `squad_delivery_discount_pct` | `100` | Global |
| `squad_hp_bonus_pct` | `30` | Global |
| `squad_order_discount_enabled` | `false` | Global |
| `squad_order_discount_pct` | `10` | Global |
| `squad_order_max_items` | `6` | Global |
| `squad_order_min_items` | `3` | Global |
| `wallet_min_card_topup` | `100` | Global |
| `wallet_topup_hp` | `50` | Global |
| `wallet_topup_min` | `3000` | Global |
| `welcome_bonus_hp` | `50` | Global |
| `whatsapp_support_enabled` | `true` | FUTA campus override |

Important: `hp_unlock_rate_pct` is a fraction (0.3 means 30%); squad percentage settings use 0–100. `daily_checkin_hp` is legacy attendance configuration: the daily attendance action itself awards zero, while weekly completion has its own reward. `order_lock_max_discount_pct` is documented in the admin UI as having no backend reader; saving an arbitrary new key does not make it executable business logic. Free-side choices now come from the curated free-side-items table, not the legacy free_side_options text.

## Render: numerical fallback defaults

These are defaults declared by the backend configuration. Where a corresponding runtime system-setting reader exists, the database value overrides the default. Do not add/change all of these just to keep the current launch setup.

| Backend environment variable | Code fallback | Database override |
| --- | --- | --- |
| `MINIMUM_AGE` | `16` | No same-name numeric database key currently stored; configure environment if needed |
| `CALLBACK_WINDOW_MINUTES` | `30` | No same-name numeric database key currently stored; configure environment if needed |
| `HP_PER_NAIRA_FOOD` | `0.1` | `hp_per_naira_food` when consumed by its service |
| `HP_UNLOCK_RATE_PCT` | `0.30` | `hp_unlock_rate_pct` when consumed by its service |
| `SIGNUP_BONUS_HP` | `0` | `signup_bonus_hp` when consumed by its service |
| `WELCOME_BONUS_HP` | `50` | `welcome_bonus_hp` when consumed by its service |
| `REVIEW_HP` | `20` | `review_hp` when consumed by its service |
| `REFERRAL_HP` | `75` | `referral_hp` when consumed by its service |
| `EVENT_CHECKIN_HP` | `40` | `event_checkin_hp` when consumed by its service |
| `BIRTHDAY_HP` | `150` | `birthday_hp` when consumed by its service |
| `WALLET_TOPUP_HP` | `50` | `wallet_topup_hp` when consumed by its service |
| `WALLET_TOPUP_MIN` | `3000` | `wallet_topup_min` when consumed by its service |
| `SUBSCRIPTION_HP` | `50` | No same-name numeric database key currently stored; configure environment if needed |
| `SOCIAL_SHARE_HP` | `25` | `social_share_hp` when consumed by its service |
| `FLASH_DISCOUNT_PCT` | `0.50` | `flash_discount_pct` when consumed by its service |
| `FLASH_MAX_QTY` | `5` | `flash_max_qty` when consumed by its service |
| `HP_BUNDLE_PRICE_PER_HP` | `5.0` | `hp_bundle_price_per_hp` when consumed by its service |
| `HP_BUNDLE_MIN_PURCHASE` | `100` | `hp_bundle_min_purchase` when consumed by its service |
| `TIER_GRACE_PERIOD_DAYS` | `7` | No same-name numeric database key currently stored; configure environment if needed |
| `LOW_CODE_INVENTORY_THRESHOLD` | `5` | `low_code_inventory_threshold` when consumed by its service |
| `ABANDONED_CART_MINUTES` | `60` | No same-name numeric database key currently stored; configure environment if needed |
| `MARKETPLACE_PURCHASE_HP` | `50` | `marketplace_purchase_hp` when consumed by its service |
| `SQUAD_ORDER_MIN_ITEMS` | `3` | `squad_order_min_items` when consumed by its service |
| `SQUAD_ORDER_MAX_ITEMS` | `6` | `squad_order_max_items` when consumed by its service |
| `SQUAD_MAX_MEMBERS` | `20` | No same-name numeric database key currently stored; configure environment if needed |
| `SQUAD_DELIVERY_DISCOUNT_PCT` | `100` | `squad_delivery_discount_pct` when consumed by its service |
| `SQUAD_ORDER_DISCOUNT_PCT` | `10` | `squad_order_discount_pct` when consumed by its service |
| `GRADUATION_HP` | `1000` | No same-name numeric database key currently stored; configure environment if needed |
| `HP_TRANSFER_MIN_AMOUNT` | `10` | `hp_transfer_min_amount` when consumed by its service |
| `HP_TRANSFER_MIN_ORDERS` | `3` | `hp_transfer_min_orders` when consumed by its service |
| `WALLET_MIN_CARD_TOPUP` | `100` | `wallet_min_card_topup` when consumed by its service |
| `LOGIN_STREAK_HP` | `2` | `login_streak_hp` when consumed by its service |
| `MONTHLY_HP_CAP` | `800` | `monthly_hp_cap` when consumed by its service |
| `HP_DECAY_ONSET_DAYS` | `120` | No same-name numeric database key currently stored; configure environment if needed |
| `HP_DECAY_RATE_MONTHLY` | `0.10` | No same-name numeric database key currently stored; configure environment if needed |
| `WINBACK_DAY1` | `70` | No same-name numeric database key currently stored; configure environment if needed |
| `WINBACK_DAY2` | `95` | No same-name numeric database key currently stored; configure environment if needed |
| `WINBACK_DAY3` | `118` | No same-name numeric database key currently stored; configure environment if needed |
| `SHARE_PROMPT_HP` | `25` | `share_prompt_hp` when consumed by its service |
| `SQUAD_REFERRAL_WINDOW_DAYS` | `7` | No same-name numeric database key currently stored; configure environment if needed |
| `ORDER_LOCK_MAX_RESCHEDULES` | `1` | `order_lock_max_reschedules` when consumed by its service |
| `ORDER_LOCK_MAX_DISCOUNT_PCT` | `50` | No same-name numeric database key currently stored; configure environment if needed |
| `ORDER_LOCK_DEFAULT_DISCOUNT_PCT` | `10` | `order_lock_default_discount_pct` when consumed by its service |
| `LOGIN_STREAK_WEEK1_HP` | `25` | No same-name numeric database key currently stored; configure environment if needed |
| `LOGIN_STREAK_WEEK2_HP` | `40` | No same-name numeric database key currently stored; configure environment if needed |
| `LOGIN_STREAK_WEEK3_HP` | `60` | No same-name numeric database key currently stored; configure environment if needed |
| `LOGIN_STREAK_WEEK4_HP` | `80` | No same-name numeric database key currently stored; configure environment if needed |
| `STREAK_MAX_MISSED_DAYS` | `2` | No same-name numeric database key currently stored; configure environment if needed |
| `STREAK_RECLAIM_MIN_TOPUP` | `1000` | No same-name numeric database key currently stored; configure environment if needed |
| `NOTIFICATION_GAP_MINUTES` | `30` | `notification_gap_minutes` when consumed by its service |
| `NOTIFICATION_DAILY_CAP` | `20` | `notification_daily_cap` when consumed by its service |
| `LEADERBOARD_DEFAULT_LIMIT` | `10` | No same-name numeric database key currently stored; configure environment if needed |
| `LEADERBOARD_MAX_LIMIT` | `50` | No same-name numeric database key currently stored; configure environment if needed |
| `MAX_CONTENT_LENGTH` | `10` | No same-name numeric database key currently stored; configure environment if needed |
| `REWARD_FULFILMENT_HOURS` | `24` | No same-name numeric database key currently stored; configure environment if needed |
| `FREE_SIDE_CREDITS_VALIDITY_DAYS` | `60` | `free_side_credits_validity_days` when consumed by its service |
| `EXCLUSIVE_SPIN_VALIDITY_DAYS` | `30` | `exclusive_spin_validity_days` when consumed by its service |
| `RATE_LIMIT_REGISTER_REQUESTS` | `10` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_REGISTER_WINDOW` | `3600` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_LOGIN_REQUESTS` | `20` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_LOGIN_WINDOW` | `900` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_ORDERS_REQUESTS` | `10` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_ORDERS_WINDOW` | `300` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_RESET_PW_REQUESTS` | `5` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_RESET_PW_WINDOW` | `3600` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_REFRESH_REQUESTS` | `30` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_REFRESH_WINDOW` | `60` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_VERIFY_EMAIL_REQUESTS` | `3` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_VERIFY_EMAIL_WINDOW` | `3600` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_DEVICE_TOKEN_REQUESTS` | `20` | No same-name numeric database key currently stored; configure environment if needed |
| `RATE_LIMIT_DEVICE_TOKEN_WINDOW` | `3600` | No same-name numeric database key currently stored; configure environment if needed |

Additional fallback hours: `ORDERING_WINDOW_OPEN_TIME` and `ORDERING_WINDOW_CLOSE_TIME`. FUTA’s saved ordering/operating-hour rows override these; changing the Render fallback does not replace FUTA’s database schedule.

## Render: service configuration and secrets

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`/configured Supabase key, `SUPABASE_ANON_KEY`, the configured JWT/auth secrets, `SECRET_KEY`, `FRONTEND_URL`, `CORS_ORIGINS`, `API_PUBLIC_URL`, Paystack keys, OneSignal app/API credentials, Resend key/from identity, Cloudinary credentials, and Redis/Celery configuration if workers are deployed. Preserve secrets when migrating; do not put service-role/API secrets in browser variables. No Brevo fallback environment variables were added because that integration is not implemented.

## Vercel: browser/build variables

`VITE_API_BASE_URL` points to the backend `/api` URL. `VITE_GOOGLE_MAPS_API_KEY` enables Maps; `VITE_GOOGLE_BUSINESS_PLACE_ID` is the actual Place ID for Google reviews; `VITE_ONESIGNAL_APP_ID` is the public push app ID. Redeploy after changes because Vite embeds these during the build.

## Supabase dashboard

SMTP host/port/login/key/from address and Auth email templates belong in Supabase Authentication settings. They are not Render app-email fallback settings. Email autoconfirm remains enabled (confirmation emails are not required for signup). Password resets still use the configured Auth SMTP.

## Calendar loading correction

The 14-day selector previously repeated configuration reads for every date under a generic 12-second client deadline. It now takes request-local snapshots of schedule configuration, keeps order counts as live reads, and gives the calendar a bounded 30-second read deadline. A real database read-only route check returned 14 selectable-date records in 2.2 seconds, with zero writes. Configuration snapshots expire at the end of each HTTP request, so admin edits are visible on the next request.

During this audit, `wallet_topup_min` was also found to be stored in the app while the award threshold read only the environment fallback. The wallet service now honours the system setting; a regression proves changing the threshold changes bonus eligibility. Current stored threshold remains ₦3,000 and top-up reward remains 50 active HP.
