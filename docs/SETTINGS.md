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
| `squad_order_min_items` | env only | settings → env (`squad_order_max_items` read settings with its own query — both now go through the same helper, bounds 1–200) |
| `order_lock_max_reschedules` | env only | settings → env |
| `order_lock_default_discount_pct` | read a **different key** (`order_lock_default_discount`) | reads the frontend's key first, legacy key as fallback, then env |
| `wallet_min_card_topup` | env only | settings → env |

Files touched: `app/utils/settings.py` (the two helpers),
`app/services/order_service.py`, `app/routes/order_locks.py`,
`app/routes/wallet.py`.

## Seeding the table

`holy-grills-backend/migrations/2026-10-04_seed_system_settings.sql` — run it in
the Supabase SQL editor. It is idempotent (a key is inserted only when no global
row exists, so it never overwrites a value an admin has edited) and column-aware
(works whether `value` is jsonb or text, and with a reduced table).

* **Section 1 — live**: 19 keys the backend reads today (squad/order-lock/wallet
  numbers, free-side and spin validity, welcome/signup/review/share HP, transfer
  minimum orders, graduation level, multiplier, monthly cap).
* **Section 2 — frontend-facing**: 21 keys the frontend reads today where the
  backend still resolves the same value from env config; the seeded value is that
  exact default, so nothing moves until someone edits it. Four of these are
  **`is_public = false`** — `low_code_inventory_threshold`, `notification_daily_cap`,
  `paystack_preferred_bank`, `wallet_ref_prefix` — so `GET /storefront/config/public`
  does not serve them and a student's client uses its built-in default for them.
* **Skipped on purpose**: `ordering_window_open_time` / `ordering_window_close_time`
  (opening hours live in `ordering_windows` + per-campus overrides, which is what
  the kitchen and checkout read) and `app_name` (duplicates `platform_name`).
  Candidate list 43 → 40 inserted. The file explains each at the end.
* **Verified against real Postgres** (jsonb, text and a reduced two-column table):
  40 rows on a clean table, exactly the four above private, re-running inserts
  nothing.
* **Not seeded** — the file ends with a NEEDS-A-DECISION list (dead keys,
  tier-driven values, kitchen_settings keys) so nobody seeds a value an edit
  cannot move.

## The database validator — `hg_validate_system_setting`

Applied on test 2 alongside the seed: a `BEFORE INSERT OR UPDATE` trigger on
`system_settings` that range-checks numeric settings. An out-of-range or
non-numeric value is refused with a sentence written for the person editing it,
e.g. `flash_discount_pct must be between 0 and 1 (got 5)`.

**Fractions vs percentages** — the one place the key names lie:

| Kind | Keys | Range |
|---|---|---|
| Fraction | `flash_discount_pct` (0.5 = half price), `hp_unlock_rate_pct` (0.3 = 30% unlocked immediately) | **0–1** |
| Percent | `squad_delivery_discount_pct`, `squad_order_discount_pct`, `squad_hp_bonus_pct`, `order_lock_default_discount_pct`, `order_lock_max_discount_pct` | **0–100** |

Where the code is stricter than the trigger, the row's hint says so (the
order-lock route honours only 1–50 for its default discount). The admin screen
labels every one of these with its unit — on the row and in the editor
(`AdminSystemSettings.tsx` → `UNITS`).

**How the refusal reaches the admin.** Postgres reports a `RAISE` as code
`P0001`, which the app-wide error handler can only turn into a generic 400/500 —
that is why a bad value used to surface as "Something went wrong".
`_validator_refusal` (`app/routes/admin_gifts.py`) recognises the validator's
refusal on both settings write routes (`PATCH /admin/settings/<key>`,
`POST /admin/settings`) and returns its sentence as the response's `error`, which
the screen already toasts verbatim. Everything else — RLS denial, schema drift,
the network — still goes to the global handler, so this is not a path for
arbitrary database text. Covered by `tests/test_setting_validator_surfacing.py`.

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
| `window_capacity`, `referral_hp`, `daily_checkin_hp`, `hp_bundle_price_per_hp`, `hp_bundles`, `paystack_preferred_bank`, `flash_discount_pct` | shown/used by the frontend with defaults that match the backend env defaults today; **not yet** read by the backend from settings. Each needs the same two-line treatment when it matters |
| `event_checkin_hp`, `wallet_topup_hp`, `marketplace_purchase_hp`, `low_code_inventory_threshold` | **wired in this pass** — the seeded row now drives the backend (`setting_or_config`: setting → env), so the admin UI row is real |

| Secrets / infra (`SUPABASE_*`, `PAYSTACK_*`, `CLOUDINARY_*`, `SECRET_KEY`, CORS) | stay in env, by design |
| `LOGIN_STREAK_HP`, `MONTHLY_HP_CAP`, `REFERRAL_HP`, `GRADUATION_HP` | defined in Config but **no reader** — the live paths are `login_streak_rewards` (table), `monthly_pending_cap` (setting), tier perks and `graduation_min_level`. Left out of the seed on purpose |
| `order_lock_default_discount` (legacy key) | still honoured as a fallback behind `order_lock_default_discount_pct` |

## Adding a new tunable (the recipe)

1. Add the row in the admin settings screen (or leave the default in code).
2. Read it in the backend with `setting_or_config(db, "<same key the frontend uses>", <env fallback>, minimum=…, maximum=…)`.
3. Read it in the frontend with `num|str|bool|json('<same key>', <same default>)` — `appConfig.ts`.
4. Never invent a second name for the same value: the `order_lock_default_discount` vs `_pct` split above is exactly the bug that makes an admin's edit do nothing.
