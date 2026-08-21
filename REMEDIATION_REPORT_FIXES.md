# Remediation Report: Line-by-Line Python Fixes & PWA/Push System Milestones

## Overview
This document details all Python route-level audit fixes across Batches 5, 6, and 7, as well as the implementation details for PWA Installation, Push Subscription, and PWA+Push Bonus system milestones.

---

## Part 1: Batch Audit Fixes

### Batch 5 (`health.py`, `hp.py`, `kitchen.py`, `leaderboard.py`)
- **`health.py` (PY-H1):** Pass by design (infrastructure probe).
- **`hp.py` (PY-P2, PY-P3, PY-P4):**
  - Tightened `GET /transactions` and `GET /unlock-history` to unconditional `.eq("campus_id", g.campus_id)` filtering.
  - Updated `_log_admin_action()` to propagate `campus_id` and raise database exceptions.
  - Added target user campus checks in `admin_grant()` and `admin_expire()`.
- **`kitchen.py` (PY-K1, PY-K2, PY-K3):**
  - Repaired syntax error in `batch_summary()`.
  - Added `.eq("campus_id", campus_id)` filtering across settings, windows, batch summary, and batch advance.
  - Set composite conflict target `on_conflict="key,campus_id"` for `update_kitchen_settings()`.
- **`leaderboard.py` (PY-L1):** Confirmed Hall of Fame routes (`/hall-of-fame`, `/hall-of-fame/inductees`, `/hall-of-fame/inductees/<id>/card`) are global across all campuses per specification, while individual (`/leaderboard`, `/my-rank`) and squad (`/squad`, `/squad/my-rank`) leaderboards are campus-scoped with `.eq("campus_id", campus_id)`.

### Batch 6 (`marketplace.py`, `menu.py`, `notifications.py`, `order_locks.py`)
- **`marketplace.py` (PY-B2-M1, M2, M3, M4):**
  - Refactored `purchase()` to call `db.rpc("hg_purchase_marketplace_item")` directly.
  - Expanded `LISTING_STATUSES` to `("pending", "active", "paused", "rejected", "archived", "draft")`.
  - Updated `restore_inventory_on_refund()` to restore `inventory_count` and release assigned access codes back to `status="available"`.
- **`menu.py` (PY-B2-N1):** Confirmed `campus_id` on child table inserts.
- **`notifications.py` (PY-B2-P2):** Handled race conditions and unique constraint errors in `push_subscribe()`.
- **`order_locks.py` (PY-B2-L1):** Handled `uq_order_locks_one_active_per_user` unique constraint in `create_lock()`.

### Batch 7 (`riders.py`, `rewards.py`, `referrals.py`, `saved_for_later.py`)
- **`riders.py` (PY-RD1, RD2):** Enforced rider batch ownership in `update_order_status()`, and added `campus_id` to `rider_profiles` in `toggle_availability()`.
- **`rewards.py` (PY-RW1, RW2, RW3):** Populated `campus_id` in `create_reward()`, guarded redemption rejection refunds for `pending` status only, and added campus filtering on admin routes.
- **`referrals.py` (PY-R1):** Optimized `my_referrals()` with batch profile lookups.
- **`saved_for_later.py`:** Confirmed user/campus scoping.

---

## Part 2: PWA & Push System Milestones Implementation Report

### 1. Files Changed / Added
- **`app/services/milestone_service.py`**: Added `SYSTEM_VERIFIED_TRIGGERS`, `check_and_award_pwa_push_bonus()`, dynamic `system_settings` HP resolution, race-safe DB insertion before HP awards, and system milestone support in `get_user_milestones()`.
- **`app/routes/challenges.py`**: Added `POST /pwa-installed`, `POST /push-subscribed`, and `GET /pwa-push-bonus-status` endpoints.
- **`tests/test_pwa_push_milestones.py`**: Added 7 comprehensive unit/integration tests covering all PWA, Push, and Bonus milestone scenarios.

### 2. Endpoints Added / Modified
- `POST /api/challenges/pwa-installed` — Claims PWA install milestone for authenticated user.
- `POST /api/challenges/push-subscribed` — Registers/updates Web Push subscription and claims Push subscribe milestone.
- `GET /api/challenges/pwa-push-bonus-status` — Returns status of PWA, Push, and Bonus milestones; automatically claims bonus when eligible.

### 3. Database Assumptions & Uniqueness Constraints
- `milestones` table has rows with `trigger_type` IN (`pwa_install`, `push_subscribe`, `pwa_push_bonus`) with `time_window IS NULL`.
- `user_milestones` table has unique constraint on `(user_id, milestone_id, period_key)` where `period_key IS NULL` for lifetime system milestones.
- Uniqueness constraint at the database layer is the final race-condition protection.

### 4. System Settings Used
- `PWA_INSTALL_HP` — Configured HP reward for PWA installation.
- `PUSH_SUBSCRIBE_HP` — Configured HP reward for Web Push subscription.
- `PWA_PUSH_BONUS_HP` — Configured HP reward for completing both PWA and Push.
- Resolved dynamically via `get_validated_setting(db, key, required=True, minimum=1)`. Fails safely with log error if missing.

### 5. Authentication & Guest Handling
- Endpoints require `@require_auth`. Guest users (unauthenticated) receive 401.
- No guest `user_milestones` rows are created.
- When a guest logs in or registers later, the frontend calls the authenticated endpoint and Python evaluates/awards the milestone against the authenticated `user_id`.

### 6. Duplicate Claims & Race Safety
- `user_milestones` insertion happens **before** `_award_milestone_hp()`.
- Re-subscribing, clearing browser data, or calling endpoints on multiple devices returns `already_completed: True` and 0 HP without double-awarding.

### 7. Bonus Eligibility Resolution
- `pwa_push_bonus` is evaluated automatically whenever `pwa_install` or `push_subscribe` completes, or via `GET /pwa-push-bonus-status`.
- Awarded only when BOTH `pwa_install` and `push_subscribe` are completed by the same authenticated user.

### 8. Historical HP Immutability
- `user_milestones.hp_awarded` records the exact actual HP amount awarded at completion time.
- Subsequent changes to `system_settings` change rewards for future users only and do not rewrite historical completion records.

### 9. Test Suite Verification
- `pytest tests/`: 237 passed, 1 skipped (0 failures).
