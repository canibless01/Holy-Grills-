# Holy Grills — Set 5 & Set 6 Audit Fixes Report

This document details all fixes implemented across Set 5 and Set 6 Python route blueprints in Holy Grills backend.

---

## SUMMARY OF AUDIT FIXES

### SET 5 Blueprints

#### 1. `app/routes/hp.py`
- **PY-P2 (Medium)**: Changed soft fallback filtering to unconditional `q.eq("campus_id", campus_id)` in `transactions()` and `unlock_history()` endpoints to enforce strict campus multi-tenancy.
- **PY-P3 (High)**: Refactored `_log_admin_action()` helper:
  - Added `campus_id` parameter (defaults to `g.campus_id`).
  - Read `actor_role` dynamically from `g.user_role` (correctly identifying `super_admin` vs `admin`).
  - Removed silent `try/except: pass` wrapper so database insertion occurs properly.
- **PY-P4 (Medium)**: Added target profile `campus_id` validation in `admin_grant()` and `admin_expire()` to block non-super_admin campus admins from granting or expiring HP for users belonging to other campuses.
- **PY-P5 (High)**: Updated `transfer_hp()` to wrap recipient credit leg in a `try/except` block with compensating refund logic back to sender if the credit step fails.

#### 2. `app/routes/kitchen.py`
- **PY-K1 (Critical)**: Scoped `kitchen_settings` queries (`get_kitchen_settings`, `get_kitchen_setting`) by `g.campus_id`. Updated `update_kitchen_settings()` upsert payload to include `campus_id` and use composite `on_conflict="key,campus_id"`.
- **PY-K2 (Critical)**: Added `campus_id` filtering to `delivery_windows()` and count queries for orders per window.
- **PY-K3 (High)**: Explicitly filtered orders by `g.campus_id` in `batch_summary()` and `batch_advance()`.

#### 3. `app/routes/leaderboard.py`
- **PY-L1 (Medium)**: Added `campus_id` filtering (resolving query parameter or `g.campus_id`) across `hall_of_fame()`, `hall_of_fame_inductees()`, and `inductee_share_card()` endpoints.

---

### SET 6 Blueprints

#### 1. `app/routes/marketplace.py`
- **B0 (Critical)**: Appended missing `.execute()` calls to database write queries in `admin_delete_listing()`.
- **B1.1 (Critical)**: Refactored `purchase()`:
  - Eliminated duplicate Python-side code reservation, wallet debits, and HP spending.
  - Routed purchase execution exclusively through `hg_purchase_marketplace_item` RPC with correct parameters (`p_user_id`, `p_listing_id`, `p_quantity`, `p_pay_with_hp`, `p_wallet_amount`, `p_payment_reference`).
- **B1.2 (High)**: Updated `LISTING_STATUSES` tuple to `("pending", "active", "paused", "rejected", "archived", "draft")` matching database CHECK constraints.
- **B1.3 (High)**: Updated `admin_update_purchase()` refund/cancel logic to release assigned access codes back to `available` and restore `is_out_of_stock = False` on the listing.
- **B1.4 (Low)**: Updated Swagger documentation for valid listing types.

#### 2. `app/routes/menu.py`
- **B0 (Critical)**: Appended missing `.execute()` calls across all 24 write operations:
  - `_log_menu_admin_action()`
  - `create_category()`, `update_category()`, `delete_category()`
  - `create_addon_group()`, `update_addon_group()`, `delete_addon_group()`
  - `create_item()`, `update_menu_item_image()`, `update_item()`, `bulk_update_availability()`, `archive_item()`
  - `create_variation_group()`, `update_variation_group()`, `delete_variation_group()`
  - `create_variation_option()`, `update_variation_option()`, `delete_variation_option()`
  - `create_addon()`, `update_addon()`, `archive_addon()`
  - `set_kitchen_capacity()` (both set and clear branches)
- **B2.1 (Medium)**: Added `campus_id = getattr(g, "campus_id", None)` to records inserted by `create_addon_group()`, `create_variation_group()`, and `create_variation_option()`.
- **B2.2 & B2.3 (Low)**: Removed obsolete fields (`sku`, `dietary_tags`) from docstrings and simplified `get_item()` error handling.

#### 3. `app/routes/notifications.py`
- **B0 (Critical)**: Appended missing `.execute()` calls to `push_subscribe()`, `push_unsubscribe()`, `mark_all_read()`, `update_preferences()`, and `create_blast()`.
- **B3.1 (Low)**: Updated `create_blast()` to set `status = "scheduled"` when `scheduled_at` is present, and `"pending"` when sending immediately.
- **B3.2 (Medium)**: Handled unique index conflict on `push_subscribe()` with update fallback.

#### 4. `app/routes/order_locks.py`
- **B0 (Critical)**: Appended missing `.execute()` calls on `create_lock()`, `reschedule_lock()`, and `cancel_lock()`.
- **B4.1 (High)**: Added try/except handling for `uq_order_locks_one_active_per_user` unique constraint violation during lock creation for race condition safety.

---

## VERIFICATION
All 225 unit and integration tests in `tests/` pass cleanly without errors.
