# Summary of Python Backend Fixes & Enhancements

This document provides a comprehensive summary of all Python backend fixes, security hardening, and operational feature enhancements implemented across the codebase.

---

## 1. Critical Fixes

### CRITICAL B1: Event Check-in Door QR Enforcement
* **File:** `app/routes/events.py` (`checkin`)
* **Problem:** Event check-in awarded HP and marked attendance based on ticket lookup alone without verifying that the attendee actually scanned the physical door QR code.
* **Fix Implemented:**
  - Evaluated `door_qr_matched` and checked caller role (`getattr(g, "user_role", None) in ("admin", "super_admin")`).
  - Added a strict check right after ticket lookup: if neither `door_qr_matched` is `True` nor the caller is an admin, returned HTTP 400 forbidding check-in and HP award.

### CRITICAL B2: Marketplace Purchase Paystack Payment Verification
* **File:** `app/routes/marketplace.py` (`purchase`)
* **Problem:** Card-funded or split-funded marketplace purchases executed `hg_purchase_marketplace_item` RPC immediately without verifying Paystack card payment references or amounts.
* **Fix Implemented:**
  - Computed `card_amount = total_value - wallet_amount`.
  - Initialized `card_amount = 0.0` as default when `use_hp` is True.
  - When `card_amount > 0`:
    1. Validated `payment_reference` is present.
    2. Called `verify_payment(reference)` from `payment_service`.
    3. Checked transaction status (`txn_data.get("status") == "success"`) and verified kobo amount paid (`paid_kobo >= int(round(card_amount * 100))`), returning HTTP 402 on failure.
  - Corrected `use_hp` logic to strictly respect the caller's requested `payment_method` (`wallet`, `hp`, `card`, `split`).

---

## 2. Specific B1–B9 Specifications

### B1. Idempotent Squad HP Distribution (`app/routes/orders.py`)
* **Function:** `add_squad_members`
* **Fix Implemented:** Added atomic status claim check on `orders.squad_hp_distributed_at`. Only the request that successfully updates `squad_hp_distributed_at` from `NULL` triggers `_distribute_squad_hp()`, preventing duplicate HP distribution.

### B2. Order Double-Refund Prevention (`app/routes/orders.py`)
* **Function:** `refund_order`
* **Fix Implemented:**
  - Updated order select query to include `card_refund_total`.
  - Replaced regex parsing of notes with `card_refund_total` column calculation.
  - Recorded card refund increment in `orders.card_refund_total` immediately after Paystack refund call succeeds.

### B3. Defensive Insert in Order Share Recording (`app/routes/orders.py`)
* **Function:** `record_order_share`
* **Fix Implemented:** Wrapped `db.table("order_share_events").insert(...).execute()` in a try-except block, logging warnings and returning HTTP 400 if DB insert fails.

### B4. Kitchen Capacity Campus Scoping (`app/services/order_service.py`)
* **Function:** `_check_kitchen_capacity` & `create_order`
* **Fix Implemented:** Updated `_check_kitchen_capacity(db, campus_id)` to accept `campus_id` and scope both `kitchen_settings` lookup and `orders` count to the caller's `campus_id`. Passed `campus_id` from `g.campus_id` in `create_order()`.

### B5. Independent Cleanups
* **B5a (`order_service.py`):** Updated `_handle_delivery_rewards` to execute `db.rpc("hg_reset_next_order_multiplier", {"p_user_id": user_id})` directly without invalid `.execute()` call.
* **B5b (`order_service.py`):** Added zero-row check in `update_order_status`, raising `ValueError` if status update returns empty.
* **B5d (`order_locks.py`):** Removed dead code functions `cancel_lock_write()` and `_get_setting()`.
* **B5e (`referrals.py`):** Sanitized error responses in `my_referrals` and `referral_stats`, replacing raw exception exposure with generic messages and server log entries.
* **B5f (`rewards.py`):** Fixed `create_reward` so session `g.campus_id` takes precedence over request body input.

### B6. Split-Batch Authorization Update (`app/services/order_service.py`)
* **Functions:** `walk_order_to_status` & `update_order_status`
* **Fix Implemented:** Replaced raw `delivery_batches` query for rider checks with `db.rpc("hg_effective_rider", {"p_order_id": order_id})`, accurately evaluating rider overrides from `delivery_assignments`.

### B7. Split-Batch Query Fixes (`app/routes/riders.py`)
* **Functions:** `my_batch`, `delivery_history`, `rider_earnings`
* **Fix Implemented:**
  - `my_batch` & `delivery_history`: Excluded orders reassigned away from the rider via `delivery_assignments`.
  - `rider_earnings`: Excluded reassigned-away orders and included cross-batch orders individually assigned to the rider via `delivery_assignments`.

### B8. New Admin Reassignment Routes (`app/routes/admin.py`)
* **Routes Implemented:**
  - `POST /delivery-batches/<batch_id>/reassign`: Bulk/individual order reassignment via `delivery_assignments` upsert.
  - `DELETE /delivery-batches/<batch_id>/reassign/<order_id>`: Clears per-order rider override.
  - Added `.order("created_at", ascending=True)` to `list_batch_orders`.
  - Added `status` and `gate_id` filters to `list_batches`.

### B9. Auto-Batch-by-Gate (`app/services/order_service.py` & `app/routes/admin.py`)
* **Fix Implemented:** In `create_order()`, called `db.rpc("hg_auto_assign_order_to_batch", {"p_order_id": result["order_id"]})` after atomic order creation to auto-assign same-window, same-gate orders into open batches.

---

## 3. Additional Quality & Security Fixes

* **`events.py`:**
  - Added `is_published` check in `get_event` for non-admin callers.
  - Implemented explicit column allowlist for `submit_catering_request`.
  - Refactored `list_event_registrants` and `send_registrants_to_host` into shared helper `_get_event_registrants_data` ensuring guest registrant details (`guest_name`, `guest_email`, `guest_phone`, `is_guest`) are exported and emailed.
  - Applied `html.escape()` on dynamic values in host email generation.
  - Validated `price_naira` and `price_hp` numeric types in `create_event_tier`.
* **`kitchen.py`:** Fixed indentation in `update_kitchen_settings` so all keys in request payload are upserted instead of returning early on the first iteration.
* **`admin.py`:** Added `limit` and `offset` pagination parameters to `list_windows`.
* **`analytics.py`:** Added `or []` fallbacks on queries in `marketplace_analytics` and renamed loop variable `g` in `gifts_analytics()`.
* **`db.py`:** Formatted string filter values in PostgREST `in_` filter queries and set standard 30s timeouts on outbound HTTP requests.

---

## 4. Verification & Testing

* Executed pytest test suite using dummy Supabase/JWT credentials:
  `SUPABASE_URL="https://dummy.supabase.co" SUPABASE_SERVICE_ROLE_KEY="dummy" SUPABASE_ANON_KEY="dummy" JWT_SECRET="dummy" PYTHONPATH=. pytest tests/ -v`
* **Result:** All **246 tests passed**, 1 test skipped, 0 failures.
