# Settings & config — where a value lives, and who can change it

**Status:** the bridge is in place. Business numbers are read from
`system_settings` first (per-campus, then global) and fall back to the
environment config, so an admin can change a value without a deploy — and the
frontend, which has always read the settings table, finally agrees with the
backend.

## The rule

| Value | Lives in | Why |
|---|---|---|
| **Business numbers and toggles** (discounts, minimums, caps, bonuses, hours) | `system_settings` table — per campus, falling back to global | they change per campus, per season, or on a whim; a deploy for a discount percentage is waste |
| **Secrets and infrastructure** (Supabase keys, Paystack secret, Cloudinary API secret, JWT secret, mail credentials) | environment only | not copy, not per-campus, and the API must never expose them |
| **Boot-time wiring** (CORS origins, port, log level, database URL) | environment only | read before a request (and sometimes before a DB) exists |
| **Pricing formulas themselves** (how a total is assembled) | code | this is logic, not a number |

Environment config remains the **fallback**, never the only copy, for anything a
campus admin should be able to tune.

## Reading order (what the backend does now)

`app/utils/settings.py` → `setting_or_config(db, key, config_value, minimum=…, maximum=…)`
and `setting_bool(db, key, config_value)`:

1. the **campus row** (`key` + the caller's campus),
2. the **global row** (`key`, `campus_id IS NULL`),
3. the **env value** passed by the caller,

with numeric bounds enforced (`MalformedSettingError`) and a settings-table
failure logged and degraded to the env value — a bad row or a DB hiccup must
never break checkout or a pay-out. This is the same shape `orders.py` already
used for `review_hp`.

## What moved in this pass

| Frontend setting key (`appConfig.ts`) | Backend before | Backend now |
|---|---|---|
| `squad_delivery_discount_enabled` / `_pct` | env only | settings → env |
| `squad_order_discount_enabled` / `_pct` | env only | settings → env |
| `squad_order_min_items` | env only | settings → env (`squad_order_max_items` already read settings — the pair now matches) |
| `order_lock_max_reschedules` | env only | settings → env |
| `order_lock_default_discount_pct` | read a **different key** (`order_lock_default_discount`) | reads the frontend's key first, legacy key as fallback, then env |
| `wallet_min_card_topup` | env only | settings → env |

Files touched: `app/utils/settings.py` (the two helpers),
`app/services/order_service.py`, `app/routes/order_locks.py`,
`app/routes/wallet.py`.

## Permissions (this is why the migration stopped before)

`require_settings_write_permission` (admin_gifts.py) — unchanged, and the rule to
keep when moving anything else:

| Row | Who may write it |
|---|---|
| `campus_id IS NULL` (**global**) | **super_admin only** |
| `campus_id = <C>` (**per-campus**) | that campus's **admin**, or any super_admin |

Reads follow the same shape: per-campus row → global row. A campus admin
therefore tunes their own campus's discounts and minimums, and cannot touch
another campus or the global default. The frontend's settings screen posts
`campus_id` only for super-admins; the backend is the enforcement point either
way.

## Known leftovers (reported, not silently changed)

| Item | State |
|---|---|
| `wallet_min_withdrawal` | frontend constant only — the backend has **no** withdrawal endpoint, so nothing to align yet; it gates nothing today (verified) |
| `order_lock_max_discount_pct` (frontend) / `ORDER_LOCK_MAX_DISCOUNT_PCT` (env) | **unused on both sides** — the real bound is the 1–50 validation inside `order_locks.py`. Dead config; delete or wire deliberately |
| `window_capacity`, `referral_hp`, `daily_checkin_hp`, `event_checkin_hp`, `wallet_topup_hp`, `hp_bundle_price_per_hp`, `hp_bundles`, `paystack_preferred_bank`, `flash_discount_pct` | shown/used by the frontend with defaults that match the backend env defaults today; **not yet** read by the backend from settings. Each needs the same two-line treatment when it matters |
| Secrets / infra (`SUPABASE_*`, `PAYSTACK_*`, `CLOUDINARY_*`, `SECRET_KEY`, CORS) | stay in env, by design |

## Adding a new tunable (the recipe)

1. Add the row in the admin settings screen (or leave the default in code).
2. Read it in the backend with `setting_or_config(db, "<same key the frontend uses>", <env fallback>, minimum=…, maximum=…)`.
3. Read it in the frontend with `num|str|bool|json('<same key>', <same default>)` — `appConfig.ts`.
4. Never invent a second name for the same value: the `order_lock_default_discount` vs `_pct` split above is exactly the bug that makes an admin's edit do nothing.
