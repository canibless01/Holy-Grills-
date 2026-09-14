# Stage 5–16 Fix Sheet Progress & Verification Document

This document tracks implementation progress and verification across Stages 5 through 16.

## Status Overview

- [x] **Stage 5 — Secret menu (`app/routes/menu.py`)**
  - Add `is_secret` filter (`q.eq("is_secret", "false")`) when no search query (`search`) is provided in `list_items()`.
  - Add `"is_secret"` to `MENU_ITEM_COLUMNS` and `MENU_ITEM_UPDATE_COLUMNS`.

- [x] **Stage 6 & Monthly Cap Fix — Event active HP, universal pending cap (`app/services/hp_service.py`)**
  - In `earn_pending_hp`: `is_instant_active = source_type == "event"`, `status = "active" if is_instant_active else "pending"`.
  - Run `check_monthly_cap` and `update_monthly_tracker` directly inside `earn_pending_hp` for all pending HP awards.
  - Remove redundant `check_monthly_cap` / `update_monthly_tracker` calls in milestone awards, weekly streak awards, and order-share prompt.

- [x] **Stage 7 — Multipliers & Auto-Rotation**
  - `_get_menu_multiplier(campus_id)` reading `menu_hp_multiplier` from `system_settings`.
  - Read `_get_food_earn_rate()` and `_get_unlock_rate()` from `system_settings`.
  - `calculate_delivery_hp` multiplier multiplication: `line_base_hp * item_multiplier * event_multiplier * menu_multiplier`.
  - Delete fee-preview single-use multiplier reset from `create_order` in `order_service.py`.
  - Add rotation helpers (`_pick_next_rotation_date`, `_notify_admins_multiplier_rotation`, `_broadcast_flash_reward_event`).
  - Add env configs in `config.py` and `rotate_hp_multiplier_event` task in `scheduled.py`. Add Celery beat schedule and register in `admin.py`.

- [x] **Stage 8 — Flash reward rotation**
  - Add `flash_rotation_eligible` to `REWARD_UPDATE_COLUMNS` in `rewards.py`.
  - Add `rotate_flash_rewards()` task in `scheduled.py`, Celery beat schedule, message strings, and admin job tracking in `admin.py`.

- [x] **Stage 9 — Redeemed item delivery**
  - Add `fulfillment_type` to `REWARD_COLUMNS` / `REWARD_UPDATE_COLUMNS`.
  - Update `admin_update_redemption()` for approval notification and wider refund status checking.
  - Add `POST /api/rewards/redemptions/<redemption_id>/checkout` in `app/routes/rewards.py`.
  - Update `create_order()` and `update_order_status()` in `order_service.py` to attach and fulfill redemptions.

- [x] **Stage 12 — Segment-triggered notifications**
  - Add `resolve_segment_user_ids()` helper in `notification_service.py`.
  - Update `send_blast()` and `send_scheduled_notifications()`. Run due blasts check.

- [x] **Stage 13 — Email provider toggle (Resend / OneSignal)**
  - Add `get_email_provider()`, `_dispatch_email_via_onesignal()`, `_dispatch_email_async()` in `notification_service.py`.
  - Update `send_email()` in `email.py` to check database `email_templates` and send via configured provider.

- [x] **Stage 14 — Order-history reminder suggestions**
  - Add `GET /api/orders/suggestions` in `app/routes/orders.py`.

- [x] **Stage 16 — HP Economics Module**
  - Create `app/services/economics_service.py`.
  - Integrate economics calculations in `create_reward()`, `update_reward()`, and `admin_update_redemption()`.

- [x] **Settings write permission & Guest order linking**
  - Add `require_settings_write_access()` in `app/routes/admin_gifts.py`.
  - Add `guest_order_confirmed` email template and confirmation email in `create_order()`.
  - Add retroactive guest order HP credit backfill in `auth_service.register()`.
