# Exhaustive Codebase Security Audit, Multi-Role Simulation & Verification Report

## Executive Summary
This report presents an end-to-end security audit, architecture review, and multi-role user flow simulation for the Holy Grills application backend.

The audit evaluated all 61 Python source files in the repository across all 33 route modules (`app/routes/`), 10 service modules (`app/services/`), middleware (`app/middleware/`), background tasks (`app/tasks/`), database REST abstraction (`app/db.py`), and utility modules (`app/utils/`).

---

## Key Security & Architectural Guardrails Audited & Enforced

### 1. Database Access Helper Discipline (`get_user_client` vs `get_db`)
- **Rule Enforced**: All authenticated requests (`@require_auth`, `@require_role`, or request-bound service functions) **strictly** use `get_user_client()`.
- **How it Works**: `get_user_client()` inspects Flask request context for `g.jwt_token`. When present, it wraps table queries and RPC calls with `UserSupabaseClient`, passing the user's JWT bearer token in the `Authorization` header to PostgREST. This ensures Row Level Security (RLS) policies and campus scoping are enforced on the database level.
- **Service-Role Reservation**: Service-role `get_db()` (full admin bypass) is reserved strictly for unauthenticated contexts:
  - Initial account registration (`POST /auth/register` and `auth_service.register`).
  - Unauthenticated credential validation (`auth_service.login`, `auth_service.refresh_token`, `auth_service.reset_password_request`).
  - Incoming payment gateway webhooks (`/webhooks/paystack`, `/webhooks/flutterwave`).
  - Async Celery background tasks (`app/tasks/scheduled.py`).

### 2. Multi-Tenant Campus Isolation (`campus_id`)
- **Scoping Rule**: Multi-tenancy is enforced via `campus_id`. Authentication middleware loads the user's `campus_id` from their `profiles` row into `g.campus_id`.
- **Atomic Operations**: All financial, ordering, and inventory RPCs (`hg_create_order_atomic`, `record_hp_transaction_atomic`, `credit_wallet_atomic`, `debit_wallet_atomic`) accept `p_campus_id` as an explicit parameter.
- **Global vs. Campus-Scoped Entities**:
  - Global (unscoped): `departments`, `academic_levels`, global events (`is_global = True` or `campus_id IS NULL`), system settings (`campus_id IS NULL`).
  - Campus-Scoped: `menu_items`, `delivery_windows`, `orders`, `kitchen_settings`, `operating_hours`, `squad_orders`, `squad_leaderboard`.

### 3. Role-Based Access Control (RBAC)
- Roles defined in `app/constants.py`: `student`, `kitchen`, `rider`, `admin`, `super_admin`.
- `ADMIN_ROLES = {"admin", "super_admin"}`.
- `super_admin` Privilege Guards: System settings writes (`app/routes/admin_gifts.py`) strictly require `g.user_role == 'super_admin'`. Role escalation to `super_admin` is restricted strictly to existing `super_admin` callers. User deactivation prevents self-deactivation and blocks standard `admin` users from deactivating a `super_admin`.

---

## Multi-Role Simulation Scenarios Verified

### Scenario A: Guest User (Unauthenticated)
1. **Public Catalog Browsing**:
   - `GET /storefront/config/public`: Retrieves public app configuration.
   - `GET /menu/categories`, `GET /menu/items`: Views available menu items and customization variation groups.
   - `GET /events`: Discovers active campus and global events.
2. **Guest Order & Event Ticket Registration**:
   - `POST /events/<event_id>/register`: Successfully registers as a guest (`is_guest = True`, storing guest email/name/phone).
   - Guest order creation generates a unique UUID `idempotency_key` internally and routes through `hg_create_order_atomic` RPC.

### Scenario B: Student / Authenticated User
1. **Auth & Identity**:
   - `POST /auth/register` -> `POST /auth/login`: Issues JWT token. `g.jwt_token` and `g.campus_id` attached on protected endpoints.
2. **Daily Engagement & Gamification**:
   - `POST /daily-checkin`: Claims daily login check-in HP. Streak updated in `streak_service.py` with monthly cap checks.
   - `POST /exclusive-spin/spin`: Executes spin draw using Optimistic Concurrency Control (OCC) credit deduction.
   - `POST /free-sides/redeem`: Redeems free side credit using OCC on `free_side_credits`.
3. **Ordering & Idempotency**:
   - `POST /cart/items`: Adds item with customization check and quantity cap (max 50).
   - `POST /order-locks`: Claim single active checkout lock per user.
   - `POST /orders`: Enforces item variation min/max selection constraints, resolves flat add-ons (`is_available=True`, `is_archived=False`), computes exact order totals, debits wallet via `debit_wallet_atomic`, and locks items atomically in `hg_create_order_atomic`.
4. **Order Milestone & Referral Trigger**:
   - Payment confirmation via `confirm_order_payment` executes `hg_mark_order_paid` and `hg_complete_referral_atomic`.
   - On delivery, `_handle_delivery_rewards` applies one-time `next_order_hp_multiplier`, awards food HP, and unlocks pending HP FIFO via `unlock_pending_hp_fifo_atomic`.

### Scenario C: Kitchen Staff
1. **Queue & Windows**:
   - `GET /kitchen/queue`: Views live queue (`received`, `preparing`) scoped to `g.campus_id`. Financial data stripped for kitchen role.
   - `GET /kitchen/windows`: Monitors current and upcoming delivery window order counts.
   - `GET /kitchen/batch-summary/<window_id>`: Aggregates total item quantities for kitchen prep.
2. **Batch Advancement**:
   - `POST /kitchen/batch/<batch_id>/advance`: Advances orders using strict state machine transition map (`received` -> `preparing` -> `ready` -> `assigned` -> `out_for_delivery` -> `delivered`).

### Scenario D: Rider Staff
1. **Delivery Batch Management**:
   - `GET /delivery/active-batch`: Views assigned delivery batch.
   - `POST /riders/orders/<order_id>/pickup`: Updates status to `out_for_delivery`.
   - Order status transitions strictly enforce rider assignment matching `delivery_batches.rider_id`.

### Scenario E: Admin & Super Admin
1. **Campus Management & Analytics**:
   - `GET /analytics/hp`: HP ecosystem analytics scoped via `get_user_client()`.
   - `POST /hp/admin/grant`, `POST /hp/admin/expire`: Admin HP manual adjustments restricted to admin's assigned campus.
2. **System Settings & Governance**:
   - System settings writes restricted strictly to `super_admin`.
   - Role change requests validated against `VALID_ROLES`. Self-role changes forbidden (403). Standard admins blocked from deactivating super admins (403).

---

## Test Execution Results
All automated unit and integration tests passed cleanly:
- **Test Command**: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_ANON_KEY=dummy SUPABASE_SERVICE_ROLE_KEY=dummy JWT_SECRET=dummy PYTHONPATH=. /home/jules/.pyenv/versions/3.12.13/bin/pytest tests/`
- **Results**: 230 passed, 1 skipped, 0 failures, 0 errors.
