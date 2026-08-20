# Phase 3 Backend Remediation & Explicit Follow-ups Summary

This document provides a comprehensive, line-by-line summary of all fixes, enhancements, and remediation applied across the Holy Grills Python backend codebase for Phase 3 (including Part 1 explicit follow-ups, Part 2 Medium/Low findings, and Part B/C findings).

---

## PART 1 — Explicit Follow-ups Flagged in `03_SUPABASE_FIXES_APPLIED-1.md`

### 1. `app/services/order_service.py`
- **Function:** `create_order()`, `create_order_apply_rpc_total()`
- **Fix:** Added `create_order_apply_rpc_total(rpc_result, locally_computed_total)` helper and invoked it immediately following the `hg_create_order_atomic` RPC call in `create_order()`. Updates `order["total_amount"]` and `order["order_lock_discount_applied"]` using the authoritative post-discount values returned by the RPC instead of relying on pre-discount local Python calculations.

### 2. `app/routes/admin_gifts.py` & Global Settings Readers
- **Functions:** `require_super_admin_for_settings_write()`, `read_global_setting()`, `read_percampus_setting()`
- **Fix:**
  - Added `require_super_admin_for_settings_write(g, jsonify)` helper to enforce `g.user_role == "super_admin"` on `update_setting()` (PATCH `/settings/<key>`) and `create_setting()` (POST `/settings`).
  - Added `read_global_setting()` and `read_percampus_setting()` helpers.
  - Updated global settings reads across `app/utils/settings.py`, `app/services/hp_service.py`, `app/services/streak_service.py`, `app/services/gift_service.py`, `app/routes/daily_checkin.py`, `app/routes/free_sides.py`, `app/routes/graduation.py`, `app/routes/hp.py`, `app/routes/order_locks.py`, and `app/tasks/scheduled.py` to filter global keys with `.is_("campus_id", "null")`.

---

## PART 2 & PART B — MEDIUM / LOW Remediation Findings

### 3. `app/middleware/auth.py` & `app/routes/auth.py`
- **Functions:** `require_auth()`, `require_role()`, `optional_auth()`, `register()`
- **Fix (B1, B4):** Fixed the campus fallback query across all auth middleware functions and user registration. Replaced queries filtering by the non-existent `is_default` column with `.eq("is_active", True).order("created_at").limit(1)`.

### 4. `app/tasks/scheduled.py`
- **Functions:** `_log_cron_execution()`, `with_cron_logging()`
- **Fix (B2):**
  - Updated `_log_cron_execution()` to set `actor_id: None` (fixing UUID type validation errors) and `entity_type: "cron_jobs"`.
  - Created `@with_cron_logging(job_name)` decorator and applied it to all 14 background Celery tasks (`reset_monthly_leaderboard`, `recalculate_120day_hp`, `tier_grace_period_check`, `birthday_hp_awards`, `monthly_birthday_report`, `process_scheduled_orders`, `win_back_notifications`, `hp_decay_check`, `check_order_locks`, `reset_monthly_hp_tracker`, `membership_anniversary_awards`, `send_scheduled_notifications`, `scan_abandoned_carts`, and `check_post_delivery_nudges`). Logs success, skipped, and failure states to `admin_audit_logs`.

### 5. `app/routes/admin.py`
- **Function:** `run_cron_job()`
- **Fix (B3):** Added missing `check-post-delivery-nudges` task to the OpenAPI Swagger `enum:` list in the endpoint docstring.

### 6. `app/db.py` & `app/routes/analytics.py`
- **Functions:** `TableQuery.select()`, `execute()`, `hp_analytics()`
- **Fix (B6):**
  - Updated `TableQuery.select(columns="*", count=None)` in `app/db.py` to support `count="exact"`. Adds `Prefer: count=exact` header and parses `Content-Range` header total.
  - Bounded `hp_analytics()` in `app/routes/analytics.py` with `from_date` / `to_date` date-range filters on `hp_transactions`.
  - Updated `tier_distribution` aggregation in `hp_analytics()` to use count-only queries (`select("id", count="exact")`) instead of fetching all profile rows.

### 7. `app/routes/auth.py`
- **Function:** `delete_account()`
- **Fix (B5):** Replaced hand-rolled partial profile update with atomic `hg_anonymize_user` RPC call. Returns error if RPC indicates failure; revokes sessions and signs out on success.

### 8. `app/routes/challenges.py`
- **Functions:** `admin_create_milestone()`, `admin_update_milestone()`, `list_challenges()`, `list_badges()`, `social_follow()`
- **Fix (B7, B8, B12):**
  - Added `"campus_id"` to `MILESTONE_ALLOWED_FIELDS` whitelist and set `safe.setdefault("campus_id", getattr(g, "campus_id", None))` in `admin_create_milestone()`.
  - Added `@optional_auth` to `list_challenges()` and `list_badges()` to ensure `g.campus_id` is populated for authenticated requests.
  - Replaced `.single().execute()` with `.limit(1).execute()` on `milestones` lookup in `social_follow()`.

### 9. `app/routes/daily_checkin.py`
- **Functions:** `record_checkin()`, `checkin_history()`
- **Fix (B10, B11):**
  - Updated `checkin_history()` to use `count_q = db.table("daily_checkins").select("id", count="exact")` to count total check-ins without fetching all rows into memory.
  - Replaced catch-all exception handler in `record_checkin()` that returned a false "already checked in" 200 message with an explicit 500 error response.

### 10. `app/routes/graduation.py`
- **Function:** `claim_graduation()`
- **Fix (B18):** Wrapped `award_active_hp()` in a try/except block that rolls back `graduation_claimed` on `profiles` back to `False` if HP awarding fails, allowing safe retry.

### 11. `app/routes/events.py`
- **Functions:** `create_event()`, `my_tickets()`, `register_for_event()`
- **Fix (B14, B15, B19):**
  - Added `"campus_id"` to `EVENT_COLUMNS` and enforced campus resolution (returning 400 if unresolved) in `create_event()`.
  - Removed dead `or t.get("qr_token")` fallback in `my_tickets()`, returning `t.get("qr_code") or t["id"]`.
  - Refactored `register_for_event()` error handling for `register_for_event_atomic` RPC calls.

### 12. `app/routes/marketplace.py` & `app/routes/menu.py`
- **Functions:** `admin_create_listing()`, `create_item()`, `update_item()`
- **Fix (B1.4, B2.2):**
  - Updated `admin_create_listing()` Swagger `enum:` list in `marketplace.py` to `[code, manual, subscription, digital_code, voucher]`.
  - Removed unbacked `sku` and `dietary_tags` parameters from `create_item()` / `update_item()` Swagger docstrings in `menu.py`.

### 13. `app/routes/notifications.py`
- **Function:** `push_subscribe()`
- **Fix (B3.2):** Wrapped `push_subscriptions` insertion in try/except to catch unique constraint duplicate errors (`uq_push_subscriptions_user_endpoint`) and fall back to updating the existing subscription record.

### 14. `app/routes/order_locks.py`
- **Function:** `admin_list_locks()`
- **Fix (B4.3):** Added optional `campus_id` query parameter filtering to `admin_list_locks()`.

### 15. `app/routes/hp.py`
- **Functions:** `_log_admin_action()`, `transactions()`, `unlock_history()`, `admin_grant()`, `admin_expire()`
- **Fix (PY-P2, PY-P3, PY-P4):**
  - Updated `_log_admin_action()` to record `g.campus_id` and `g.user_role` and raise errors instead of silently swallowing them.
  - Enforced `g.campus_id` on `transactions()` and `unlock_history()`.
  - Added target user campus check in `admin_grant()` and `admin_expire()` when called by standard admins.

### 16. `app/routes/kitchen.py`
- **Functions:** `get_kitchen_settings()`, `get_kitchen_setting()`, `update_kitchen_settings()`
- **Fix (PY-K1):** Scoped settings queries by `g.campus_id` and updated `upsert` conflict target to `on_conflict="key,campus_id"`.

### 17. `app/routes/leaderboard.py`
- **Functions:** `hall_of_fame()`, `hall_of_fame_inductees()`, `inductee_share_card()`
- **Fix (PY-L1):** Added campus filtering across all Hall of Fame endpoints.

### 18. `app/routes/delivery.py`
- **Functions:** `admin_create_hostel()`, `admin_create_gate()`
- **Fix (B9):** Enforced campus resolution in hostel and gate creation, returning 400 if `campus_id` cannot be resolved.

### 19. `app/routes/exclusive_spin.py` & `app/routes/free_sides.py`
- **Functions:** `do_spin()`, `redeem_free_side()`
- **Fix (B16, B17):**
  - Updated `do_spin()` to use `get_db()` (service-role client) with explicit `user_id` filtering for the OCC credit update on `exclusive_spins`.
  - Updated `redeem_free_side()` to use `get_db()` for `free_side_credits` update and `order_items` insert. Added compensating rollback to restore credit if `order_items` insertion fails.

---

## Unit Testing & Verification

- **Test Suite:** `tests/test_phase3_remediation.py` was created to validate all remediation fixes.
- **Result:** `230 passed, 1 skipped` across the full test suite (`python3 -m pytest tests/`). Zero test failures.
