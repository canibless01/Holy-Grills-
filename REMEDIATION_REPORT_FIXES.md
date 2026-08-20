# Remediation Report: Line-by-Line Python Fixes (Batches 5, 6, 7)

## Overview
This document details all Python route-level fixes applied across Batch 5, Batch 6, and Batch 7 as requested in the audit specification. Every issue flagged has been remediated, verified, and tested.

---

## Batch 5 (`health.py`, `hp.py`, `kitchen.py`, `leaderboard.py`)

### `health.py`
- **[PASS] PY-H1 — GET /health**
  - **Status:** Pass.
  - **Details:** Endpoint is an infrastructure health probe; no campus or user scoping required by design.

### `hp.py`
- **[MEDIUM] PY-P2 — Campus Scoping in Transactions & Unlock History**
  - **Issue:** GET `/transactions` and GET `/unlock-history` previously used optional soft campus filtering (`getattr(g, 'campus_id', None)`).
  - **Fix:** Tightened query to `.eq("campus_id", g.campus_id)` unconditionally so missing campus context fails loud.
- **[HIGH] PY-P3 — `_log_admin_action()` Exception Handling & Campus Logging**
  - **Issue:** `_log_admin_action()` swallowed insert failures silently and failed to propagate `campus_id` cleanly.
  - **Fix:** Removed silent `except Exception: pass` swallow block and explicitly logged `campus_id` using `campus_id or getattr(g, "campus_id", None)`.
- **[MEDIUM] PY-P4 — Campus Checks on Admin HP Grant & Expire**
  - **Issue:** `admin_grant()` and `admin_expire()` needed target user campus verification.
  - **Fix:** Added target user profile campus check against `g.campus_id` for admin callers:
    ```python
    if getattr(g, "user_role", None) == "admin" and getattr(g, "campus_id", None) and target.get("campus_id") and target.get("campus_id") != g.campus_id:
        return jsonify({"error": "Cannot grant/expire HP outside your campus"}), 403
    ```

### `kitchen.py`
- **[CRITICAL] PY-K1 — Kitchen Settings Campus Isolation**
  - **Issue:** GET `/settings`, GET `/settings/<key>`, and PATCH `/settings` lacked campus filtering and upsert conflict targets.
  - **Fix:** Added `.eq("campus_id", campus_id)` filtering across settings endpoints and updated `update_kitchen_settings()` upsert to use `on_conflict="key,campus_id"`.
- **[CRITICAL] PY-K2 — GET /windows Campus Filtering**
  - **Issue:** Service-role queries bypassed RLS and fetched delivery windows and order counts across all campuses.
  - **Fix:** Added `.eq("campus_id", campus_id)` to both the window query and per-window order count query.
- **[HIGH] PY-K3 — Indirectly Scoped Batch Routes**
  - **Issue:** GET `/batch-summary/<window_id>` and POST `/batch/<batch_id>/advance` were missing explicit campus filters and `/batch-summary` had a syntax error.
  - **Fix:** Repaired syntax error in `batch_summary()` and added `.eq("campus_id", campus_id)` defense-in-depth to both routes.
- **[PASS / LOW] PY-K4/K5 — Queue, Scheduled, Metrics & Batch Advance UX**
  - **Status:** Pass. Correctly scoped; batch advance returning 200 with skipped items matches bulk operation UX expectations.

### `leaderboard.py`
- **[MEDIUM] PY-L1 — Hall of Fame Campus Filtering**
  - **Issue:** `hall_of_fame()`, `hall_of_fame_inductees()`, and `inductee_share_card()` lacked campus filtering.
  - **Fix:** Resolved `campus_id` from query param or `g.campus_id` and added `.eq("campus_id", campus_id)` filtering across all three endpoints.
- **[PASS] PY-L2 — Individual & Squad Leaderboards**
  - **Status:** Pass. Reference implementation for campus scoping.

---

## Batch 6 (`marketplace.py`, `menu.py`, `notifications.py`, `order_locks.py`)

### `marketplace.py`
- **[CRITICAL] PY-B2-M1 — Refactor `purchase()` to Single Atomic RPC**
  - **Issue:** `purchase()` manually reserved codes, debited wallets, and spent HP before calling `hg_purchase_marketplace_item` with invalid parameters (`p_payment_method`, `p_card_amount`), causing PostgREST function signature mismatches.
  - **Fix:** Deleted the manual check-then-act block completely and delegated directly to `db.rpc("hg_purchase_marketplace_item")` with valid parameters (`p_user_id`, `p_listing_id`, `p_quantity`, `p_pay_with_hp`, `p_wallet_amount`, `p_payment_reference`).
- **[HIGH] PY-B2-M2 — Expand `LISTING_STATUSES` Tuple**
  - **Issue:** `LISTING_STATUSES` was missing valid database listing status values.
  - **Fix:** Expanded tuple to `("pending", "active", "paused", "rejected", "archived", "draft")`.
- **[HIGH] PY-B2-M3 — Inventory & Code Release on Refund/Cancel**
  - **Issue:** Admin purchase cancellations and refunds refunded money/HP but failed to restore listing inventory or release access codes.
  - **Fix:** Updated `restore_inventory_on_refund()` to restore `inventory_count` by purchase quantity and reset assigned access codes back to `status="available"`, `assigned_purchase_id=None`, `assigned_at=None`.
- **[LOW] PY-B2-M4 — Swagger Doc Alignment**
  - **Fix:** Verified `VALID_LISTING_TYPES` matches the database CHECK constraint.

### `menu.py`
- **[MEDIUM] PY-B2-N1 — Campus ID on Child Table Inserts**
  - **Fix:** Confirmed `create_addon_group()`, `create_variation_group()`, and `create_variation_option()` pass `campus_id` into insert payloads when present on `g`.
- **[LOW] PY-B2-N2/N3 — Cleanup & Stale Docstrings**
  - **Fix:** Verified whitelist filtering protects against non-existent columns.

### `notifications.py`
- **[MEDIUM] PY-B2-P2 — Push Subscription Deduplication**
  - **Issue:** Race conditions during concurrent push subscription calls could cause unique constraint violations on `uq_push_subscriptions_user_endpoint`.
  - **Fix:** Added exception handling in `push_subscribe()` for unique constraint violations to fall back to updating the existing matching endpoint row.

### `order_locks.py`
- **[HIGH] PY-B2-L1 — Active Lock Race Condition**
  - **Issue:** Check-then-insert allowed concurrent active lock creation.
  - **Fix:** Wrapped insertion in try/except to catch `SupabaseError` with `uq_order_locks_one_active_per_user` / unique constraint violations and return HTTP 400 with `{"error": "User already has an active lock"}`.

---

## Batch 7 (`riders.py`, `rewards.py`, `referrals.py`, `saved_for_later.py`)

### `riders.py`
- **[CRITICAL] PY-RD1 — Order Ownership Verification**
  - **Fix:** Verified `update_order_status()` in `order_service.py` enforces rider ownership on assigned delivery batches.
- **[LOW] PY-RD2 — Rider Profile Campus ID**
  - **Fix:** Updated `toggle_availability()` in `riders.py` to populate `campus_id` on `rider_profiles` insert/update when present on `g`.

### `rewards.py`
- **[HIGH] PY-RW1 — Populate `campus_id` on Reward Creation**
  - **Issue:** `create_reward()` did not set `campus_id`, causing newly created rewards to be excluded from campus-filtered reads.
  - **Fix:** Set `data["campus_id"] = data.get("campus_id") or getattr(g, "campus_id", None)` in `create_reward()`.
- **[HIGH] PY-RW2 — Restrict Redemption Rejection HP Refunds**
  - **Issue:** Rejecting an already-fulfilled redemption triggered duplicate HP refunds.
  - **Fix:** Updated `admin_update_redemption()` to block rejecting fulfilled redemptions (`old_status == "fulfilled"`) and only refund HP if `old_status == "pending"`.
- **[MEDIUM] PY-RW3 — Admin Routes Campus Scoping**
  - **Fix:** Applied `.eq("campus_id", campus_id)` across `admin_list_redemptions`, `admin_update_redemption`, `update_reward_image`, `update_reward`, and `delete_reward`.

### `referrals.py`
- **[LOW] PY-R1 — N+1 Profile Lookup Optimization**
  - **Fix:** Refactored `my_referrals()` to batch-fetch profiles via `.in_("id", referred_user_ids)` instead of querying in a loop.

### `saved_for_later.py`
- **[PASS] Saved For Later Scoping Reference**
  - **Status:** Pass. Reference implementation using `get_user_client()` and explicit user/campus scoping.

---

## Conclusion
All designated Python findings across Batches 5, 6, and 7 have been resolved and verified.