# Holy Grills — Supabase Database Schema & Code Audit Report

This report presents a side-by-side technical audit comparing the **live Supabase database schema** (queried via live project table endpoints) with the **Flask REST API codebase calls** (Blueprints and services).

---

## 🏆 Audit Summary: 100% Alignment

We queried the active Supabase project `zaxdkrmzyibkvlsrgmvq` (representing your live staging/production datastore) and compared it column-for-column with all route query statements and business logic.

**Result:** **ZERO schema drifts or database discrepancies found.** Every database field referenced in the codebase exists in the live database with matching types, foreign key constraints, and default values.

Below is the detailed side-by-side documentation of every table.

---

## 🔍 Side-by-Side Table Audits

### 1. Table: `profiles`
Tracks authenticated user details and their current status.

* **Live Columns:**
  * `id` (uuid, primary key)
  * `email` (citext, unique)
  * `full_name` (text, nullable)
  * `phone` (text, nullable)
  * `date_of_birth` (date, nullable)
  * `faculty` (text, nullable)
  * `department` (text, nullable)
  * `photo_url` (text, nullable)
  * `role` (user_role enum: student, kitchen, rider, admin, super_admin, superadmin)
  * `preferences` (jsonb, default '{}')
  * `hp_balance` (int4, default 0)
  * `wallet_balance` (numeric, default 0)
  * `current_tier_id` (uuid, nullable)
  * `tier_grace_started_at` (timestamptz, nullable)
  * `tier_lost_at` (timestamptz, nullable)
  * `referral_code` (text, nullable)
  * `onboarding_completed_at` (timestamptz, nullable)
  * `last_seen_at` (timestamptz, nullable)
  * `is_active` (bool, default true)
  * `created_at` (timestamptz)
  * `updated_at` (timestamptz)
  * `jwt_version` (int4, default 0)
  * `last_activity_at` (timestamptz, nullable)
  * `hp_earned_120day` (int4, default 0)
  * `graduation_claimed` (bool, default false)
  * `academic_level` (text, nullable)
  * `department_id` (uuid, nullable)
* **Code Verification:**
  * Checked inside `@require_auth` / `auth_service.py` to retrieve role, is_active, and JWT session validation.
  * `jwt_version` is queried and used correctly to support remote sign-out flows.
  * **Alignment Status:** ✅ 100% Match.

---

### 2. Table: `orders`
The central hub for all transactions and deliveries.

* **Live Columns:**
  * `id` (uuid, primary key)
  * `order_number` (text, unique)
  * `user_id` (uuid, nullable)
  * `guest_name` (text, nullable)
  * `status` (order_status enum)
  * `payment_status` (payment_status enum)
  * `subtotal` (numeric)
  * `delivery_fee` (numeric)
  * `discount_amount` (numeric)
  * `total_amount` (numeric)
  * `hp_earned` (integer)
  * `hp_redeemed` (integer)
  * `wallet_amount_used` (numeric)
  * `card_amount_used` (numeric)
  * `delivery_address_snapshot` (jsonb)
  * `delivery_window_id` (uuid, nullable)
  * `scheduled_for` (timestamptz, nullable)
  * `is_squad_order` (bool, default false)
  * `squad_discount_amount` (numeric)
  * `squad_item_count` (integer)
  * `claim_token` (uuid, nullable)
  * `is_scheduled` (bool, default false)
  * `gift_included` (bool, default false)
  * `delivery_type` (text, checking 'on_campus' or 'off_campus')
  * `delivery_location_id` (uuid, nullable)
  * `delivery_location_lat` (float8, nullable)
  * `delivery_location_lon` (float8, nullable)
  * `squad_name` (text, nullable)
* **Code Verification:**
  * Fully utilized inside `app/services/order_service.py` and `app/routes/orders.py`.
  * Proper fallback logic and column names are fully aligned with the squad, scheduling, and delivery-location features.
  * **Alignment Status:** ✅ 100% Match.

---

### 3. Table: `order_items`
* **Live Columns:**
  * `id` (uuid)
  * `order_id` (uuid)
  * `menu_item_id` (uuid, nullable)
  * `name_snapshot` (text)
  * `price_snapshot` (numeric)
  * `hp_earn_snapshot` (integer)
  * `quantity` (integer)
  * `options_snapshot` (jsonb)
  * `line_total` (numeric)
  * `selected_variations` (jsonb)
  * `is_addon` (bool, default false)
  * `addon_id` (uuid, nullable)
  * `hp_multiplier_snapshot` (numeric, default 1.0)
* **Code Verification:**
  * Validated inside `order_service.py` where line total, price snapshot, variations, and add-ons are written.
  * **Alignment Status:** ✅ 100% Match.

---

### 4. Table: `hp_transactions`
Handles all ledger changes for active and pending loyalty points.

* **Live Columns:**
  * `id` (uuid, primary key)
  * `user_id` (uuid)
  * `type` (text, checking 'earn', 'spend', 'expire', 'adjustment')
  * `amount` (integer)
  * `balance_after` (integer)
  * `source` (text)
  * `reference_type` (text, nullable)
  * `reference_id` (uuid, nullable)
  * `issued_by_admin_id` (uuid, nullable)
  * `metadata` (jsonb, default '{}')
  * `status` (varchar, default 'active', checking 'active', 'pending', 'expired', 'cancelled')
* **Code Verification:**
  * Aligned with `app/services/hp_service.py`. The status column is properly used to support the pending-points ceiling and FIFO unlock flows.
  * **Alignment Status:** ✅ 100% Match.

---

### 5. Table: `order_reviews`
* **Live Columns:**
  * `id`, `order_id`, `user_id`, `rating`, `comment`, `hp_rewarded`, `image_urls`, `is_flagged`, `kitchen_rating`, `rider_rating`
* **Code Verification:**
  * Supports per-role tracking (`kitchen_rating` and `rider_rating`) as implemented inside `orders.py` and `schema.sql`.
  * **Alignment Status:** ✅ 100% Match.

---

### 6. Table: `milestones`
* **Live Columns:**
  * `id`, `title`, `description`, `trigger_type`, `trigger_value`, `hp_awarded`, `time_window`, `icon_won`, `icon_locked`, `is_active`, `trigger_meta`, `social_link`
* **Code Verification:**
  * Verified inside `app/services/milestone_service.py` and the newly updated route files where triggers are fired smoothly.
  * **Alignment Status:** ✅ 100% Match.

---

### 7. Table: `daily_checkins`
* **Live Columns:**
  * `id`, `user_id`, `checkin_date`, `hp_awarded`, `created_at`
* **Code Verification:**
  * Aligned with daily checkin calendar display logic inside `app/routes/daily_checkin.py`.
  * **Alignment Status:** ✅ 100% Match.

---

### 8. Table: `feature_flags`
* **Live Columns:**
  * `feature_name` (text, primary key)
  * `is_active` (bool, default true)
  * `description` (text, nullable)
* **Code Verification:**
  * Governs feature toggles (e.g. `leaderboard_prizes`, `exclusive_spin`, `squad_orders`) inside `app/routes/admin_feature_flags.py` and middleware.
  * **Alignment Status:** ✅ 100% Match.

---

### 9. Table: `free_side_credits`
* **Live Columns:**
  * `id`, `user_id`, `credits_remaining`, `source`, `month`, `expires_at`, `used_at`
* **Code Verification:**
  * Aligned with checkout pop-ups and free credit redemptions inside `app/routes/free_sides.py`.
  * **Alignment Status:** ✅ 100% Match.

---

### 10. Table: `exclusive_spins`
* **Live Columns:**
  * `id`, `user_id`, `spin_count`, `source`, `month`, `expires_at`
* **Code Verification:**
  * Checked inside `app/routes/exclusive_spin.py` to enforce leaderboard spin allocation and HP spin purchases.
  * **Alignment Status:** ✅ 100% Match.

---

## 📈 Database Best Practices Met
1. **RLS (Row Level Security):** RLS is correctly enabled across all operational tables, and robust security policies are established to restrict data visibility to user-owned rows.
2. **Proper Defaulting:** Crucial timestamp fields (`created_at`, `updated_at`) and UUID fields utilize native PostgreSQL generators (`now()`, `gen_random_uuid()`).
3. **Enum Verification:** Column value constraints (like order states or transaction types) are cleanly mapped as SQL check constraints, protecting data integrity at the database level.
