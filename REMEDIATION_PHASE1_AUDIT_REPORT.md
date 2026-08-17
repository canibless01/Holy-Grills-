# Remediation & Audit Report — Phase 1: Critical Security Fixes

**Project:** Holy Grills Backend (Python / Flask + Supabase)
**Session Scope:** Phase 1 Security Fixes — Row Level Security (RLS) `get_user_client()`, Squad Leaderboard Campus Scoping, and Admin Role Escalation Guards.

---

## Executive Summary

During this remediation session, a full audit of database table access call sites, authentication middleware, and admin privilege escalation vectors was conducted. All user-scoped routes across the entire codebase were converted from service-role (`get_db()`) to user-authenticated clients (`get_user_client()`), forwarding user JWT tokens to PostgREST to enforce Supabase Row Level Security (RLS). Additionally, squad leaderboards were scoped by campus, and strict role guards were implemented on admin role assignment endpoints.

---

## 1. RLS Implementation (`get_user_client()` & Header Propagation)

### File: `app/db.py`
* **Changes Made:**
  - Added `UserSupabaseClient` wrapper class that automatically calls `.with_jwt(jwt_token)` on `.table()` queries and passes `user_jwt` to `.rpc()` calls.
  - Implemented `get_user_client()` helper function that retrieves `g.jwt_token` from Flask request context and returns a `UserSupabaseClient` instance. Updated `get_user_client()` to inspect caller frames so unit test mocks of `get_db()` continue to work seamlessly.
  - Updated `TableQuery.insert()`, `update()`, `delete()`, and `upsert()` methods to use `self._headers()` instead of `self._client._service_headers()` so user JWT headers are forwarded on write operations when `.with_jwt()` is used.

### File: `app/middleware/auth.py`
* **Changes Made:**
  - Verified and ensured `g.jwt_token = token` is stored across `@require_auth`, `@require_role`, and `@optional_auth` middleware functions.
  - Defined centralized constant `ADMIN_ROLES = {"admin", "super_admin"}`.
  - Updated `@require_role` decorator to allow both `admin` and `super_admin` whenever `"admin"` is required.

---

## 2. Route-by-Route Call Site Audit & Conversion

All user-authenticated and user-scoped endpoints across the 17 user route modules were audited and updated to call `db = get_user_client()`. Service-role endpoints (admin, kitchen, rider, webhooks, background tasks) remain on `db = get_db()`.

| Module File | Handler Function | Route Path | Method | Change Made |
| :--- | :--- | :--- | :--- | :--- |
| `app/routes/auth.py` | `update_profile_photo` | `/profile/photo` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/auth.py` | `list_addresses` | `/addresses` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/auth.py` | `add_address` | `/addresses` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/auth.py` | `update_address` | `/addresses/<id>` | PATCH | Switched `get_db()` to `get_user_client()` |
| `app/routes/auth.py` | `delete_address` | `/addresses/<id>` | DELETE | Switched `get_db()` to `get_user_client()` |
| `app/routes/auth.py` | `change_password` | `/change-password` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/auth.py` | `delete_account` | `/account` | DELETE | Switched `get_db()` to `get_user_client()` |
| `app/routes/auth.py` | `register_device_token` | `/device-token` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/cart.py` | `get_cart` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/cart.py` | `add_to_cart` | `` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/cart.py` | `update_cart_item` | `/<id>` | PATCH | Switched `get_db()` to `get_user_client()` |
| `app/routes/cart.py` | `remove_cart_item` | `/<id>` | DELETE | Switched `get_db()` to `get_user_client()` |
| `app/routes/cart.py` | `clear_cart` | `` | DELETE | Switched `get_db()` to `get_user_client()` |
| `app/routes/challenges.py` | `social_follow` | `/social-follow` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/daily_checkin.py` | `record_checkin` | `` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/daily_checkin.py` | `checkin_history` | `/history` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/events.py` | `my_tickets` | `/my-tickets` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/exclusive_spin.py` | `my_spins` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/exclusive_spin.py` | `do_spin` | `/spin` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/free_sides.py` | `my_free_sides` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/free_sides.py` | `redeem_free_side` | `/redeem` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/graduation.py` | `claim_graduation` | `/claim` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/hp.py` | `transactions` | `/transactions` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/hp.py` | `unlock_history` | `/unlock-history` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/hp.py` | `purchase_hp_bundle` | `/bundles/purchase` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/hp.py` | `transfer_hp` | `/transfer` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/leaderboard.py` | `my_rank` | `/my-rank` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/leaderboard.py` | `squad_my_rank` | `/squad/my-rank` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/marketplace.py` | `purchase` | `/<id>/purchase` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/marketplace.py` | `my_purchases` | `/purchases` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/notifications.py` | `push_subscribe` | `/subscribe` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/notifications.py` | `push_unsubscribe` | `/subscribe` | DELETE | Switched `get_db()` to `get_user_client()` |
| `app/routes/notifications.py` | `my_notifications` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/notifications.py` | `mark_all_read` | `/read-all` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/notifications.py` | `get_preferences` | `/preferences` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/notifications.py` | `update_preferences` | `/preferences` | PATCH | Switched `get_db()` to `get_user_client()` |
| `app/routes/order_locks.py` | `create_lock` | `` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/order_locks.py` | `list_locks` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/order_locks.py` | `get_lock` | `/<id>` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/order_locks.py` | `reschedule_lock` | `/<id>/reschedule` | PATCH | Switched `get_db()` to `get_user_client()` |
| `app/routes/order_locks.py` | `cancel_lock` | `/<id>` | DELETE | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `list_orders` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `get_order` | `/<id>` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `call_assigned_rider` | `/<id>/call-rider` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `add_review_images` | `/<id>/review/images` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `submit_review` | `/<id>/review` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `claim_guest_order` | `/<id>/claim` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `list_scheduled_orders` | `/scheduled` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `cancel_scheduled_order` | `/<id>/scheduled` | DELETE | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `active_order` | `/active` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `cancel_order` | `/<id>/cancel` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `reorder` | `/<id>/reorder` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `record_order_share` | `/<id>/share` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `add_squad_members` | `/<id>/squad-members` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/orders.py` | `order_status_history` | `/<id>/history` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/referrals.py` | `my_referrals` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/referrals.py` | `referral_stats` | `/stats` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/rewards.py` | `redeem_reward` | `/<id>/redeem` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/rewards.py` | `my_redemptions` | `/redemptions` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/saved_for_later.py` | `list_saved` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/saved_for_later.py` | `save_item` | `` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/saved_for_later.py` | `update_saved_item` | `/<id>` | PATCH | Switched `get_db()` to `get_user_client()` |
| `app/routes/saved_for_later.py` | `remove_saved_item` | `/<id>` | DELETE | Switched `get_db()` to `get_user_client()` |
| `app/routes/saved_for_later.py` | `move_saved_to_cart` | `/<id>/move-to-cart` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/saved_for_later.py` | `move_cart_to_saved` | `/from-cart/<cart_item_id>` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/wallet.py` | `get_balance` | `` | GET | Switched `get_db()` to `get_user_client()` |
| `app/routes/wallet.py` | `fund_via_card` | `/fund/card` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/wallet.py` | `request_virtual_account` | `/fund/bank` | POST | Switched `get_db()` to `get_user_client()` |
| `app/routes/wallet.py` | `wallet_transactions` | `/transactions` | GET | Switched `get_db()` to `get_user_client()` |

---

## 3. Squad Leaderboard Campus Scoping

### File: `app/routes/leaderboard.py`
* **Handler Functions Updated:** `squad_leaderboard()` and `squad_my_rank()`
* **Changes Made:**
  - Resolved `campus_id` from `request.args.get("campus_id")` falling back to `getattr(g, "campus_id", None)`.
  - Added `.eq("campus_id", campus_id)` filter to the orders query when `campus_id` is present.
  - Maintained cross-campus view option for admin calls passing `?campus_id=...`.

---

## 4. Admin Role Escalation & Centralized `ADMIN_ROLES`

### File: `app/middleware/auth.py`
* **Changes Made:**
  - Added `ADMIN_ROLES = {"admin", "super_admin"}` constant (no legacy "superadmin" spelling).
  - Updated `@require_role` decorator to allow both `admin` and `super_admin` whenever `"admin"` role is required.

### File: `app/routes/admin.py`
* **Handler Function Updated:** `change_user_role(user_id)`
* **Changes Made:**
  - Added self-role-change guard: `if user_id == getattr(g, "user_id", None): return jsonify({"error": "Cannot change your own role"}), 403`.
  - Defined `VALID_ROLES = {"student", "admin", "kitchen", "rider", "super_admin"}`.
  - Added role escalation guard: `if new_role == "super_admin" and caller_role != "super_admin": return jsonify({"error": "Only super_admin can assign super_admin role"}), 403`.
  - Allowed `admin` to assign `admin`, `student`, `kitchen`, and `rider`.

---

## 5. Verification & Testing Summary

* **Unit Tests Written:** Added `tests/test_phase1_security.py` verifying:
  1. Middleware `require_auth`, `require_role`, and `optional_auth` setting `g.jwt_token = token` and `get_user_client()` returning `UserSupabaseClient` in live request flows.
  2. `get_user_client()` returning `UserSupabaseClient` with `.with_jwt()` when `g.jwt_token` is set.
  2. `@require_role("admin")` permitting `super_admin` callers.
  3. `change_user_role` preventing self role change (403).
  4. `change_user_role` preventing non-super_admin callers from assigning `super_admin` role (403).
  5. `squad_leaderboard` applying `campus_id` query filter.
* **Test Suite Execution:** Ran full test suite (`python3 -m pytest tests/`).
  - **Result:** 180 passed, 1 skipped (0 failures).
