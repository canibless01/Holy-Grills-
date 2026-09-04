# BACKEND SOURCE OF TRUTH — HOLY GRILLS PLATFORM REST API & ARCHITECTURE

Exhaustive, single-source-of-truth document detailing all REST API endpoints, 99 public database tables, order state machine, calculation formulas, transaction guarantees, complete webhook payloads, error recovery instructions, state persistence & caching, squad order logic, rider assignment logic, campaign/feature flag rules, and system configuration settings.

## SYSTEM ARCHITECTURE OVERVIEW

- **Framework**: Flask 3.1.3 (Python 3.12)

- **Database**: Supabase PostgreSQL (Project ID: `zaxdkrmzyibkvlsrgmvq`) via PostgREST REST API

- **Authentication**: Supabase JWT Auth with silent token rotation and profile role checks

- **Payment Processing**: Paystack API with HMAC Webhook verification and virtual accounts

- **Push & Email Notifications**: OneSignal API & Resend email integration

- **Background Jobs**: Celery 5.4.0 with Redis 5.2.1 broker & result backend

- **System Settings**: Dynamic system-wide and campus-scoped key-value configuration (`system_settings`)


---
## SECTION 1: ORDER STATE MACHINE

### Order Status Definitions

- **`scheduled`**: Order created for future fulfillment window; held in lock state until execution time arrives.
- **`received`**: Order successfully paid and received by the platform; queued for kitchen processing.
- **`preparing`**: Kitchen staff actively preparing meal items.
- **`ready`**: Kitchen meal preparation finished; order waiting in dispatch station for rider assignment or pickup.
- **`assigned`**: Delivery rider assigned to batch containing this order.
- **`out_for_delivery`**: Rider picked up order and is actively delivering to customer address/gate.
- **`delivered`**: Order successfully handed over to customer. Triggers HP earn credit and review prompt.
- **`delivery_attempted`**: Rider arrived at location but customer was unreachable or unavailable.
- **`unclaimed`**: Order remained uncollected at gate/pickup point past pickup grace timeout.
- **`cancelled`**: Order voided prior to fulfillment or due to uncollectibility.
- **`refunded`**: Order cancelled and funds returned to customer wallet/card balance.

### Allowed Status Transitions Matrix

| From Status | To Status | Allowed Roles | Validation Required | Side Effects |
|-------------|-----------|---------------|---------------------|--------------|
| `scheduled` | `received` | `system` (Celery) | Window `scheduled_for` timestamp reached | Places order in active kitchen queue |
| `scheduled` | `cancelled` | `student`, `admin` | Order is in future window | Releases lock reservation |
| `received` | `preparing` | `kitchen`, `admin` | `payment_status` = `'paid'` | Updates kitchen queue status |
| `received` | `cancelled` | `student`, `admin` | Order not yet being prepared | Initiates wallet/card refund |
| `received` | `refunded` | `admin` | Order cancelled prior to cooking | Debits/releases refund reservation |
| `preparing` | `ready` | `kitchen`, `admin` | Meal preparation completed | Dispatches 'order_ready' push notification |
| `preparing` | `cancelled` | `admin` | Item out of stock or kitchen issue | Triggers order refund flow |
| `ready` | `assigned` | `rider`, `admin` | Rider active and batch unassigned | Assigns order to rider batch |
| `ready` | `out_for_delivery` | `rider`, `admin` | Rider assigned | Dispatches 'out_for_delivery' notification |
| `assigned` | `out_for_delivery` | `rider`, `admin` | Batch picked up from kitchen | Sends rider contact details to customer |
| `out_for_delivery` | `delivered` | `rider`, `admin` | Customer handover confirmed | Credits HP earned, unlocks pending HP, sends delivery notification |
| `out_for_delivery` | `delivery_attempted` | `rider`, `admin` | Rider arrived, customer unreachable | Triggers customer contact alert |
| `delivery_attempted` | `delivered` | `rider`, `admin` | Customer re-contacted and handed over | Credits HP earned |
| `delivery_attempted` | `unclaimed` | `rider`, `admin` | Grace timeout elapsed | Marks order unclaimed |
| `unclaimed` | `cancelled` | `admin` | Uncollected meal discarded | No refund issued unless admin override |

### Disallowed Transition Error Response

- Invalid transition attempt returns HTTP 400 Bad Request: `"Cannot transition order status from '{current_status}' to '{new_status}'"`.

---
## SECTION 2: CALCULATION FORMULAS

### 1. HP Earn Calculation

- **Formula**: `line_base_hp = int(unit_price * quantity * HP_PER_NAIRA_FOOD)` (default `HP_PER_NAIRA_FOOD` = 0.1, i.e., 1 HP per ₦10 spent).

- **Item Multiplier**: `multiplied_line_hp = round(line_base_hp * hp_multiplier_snapshot)` (1.0x or 2.0x for promotional items).

- **Tier Multiplier**: `tier_multiplier` (Starter=1.0, Regular=1.1, Champion=1.2, Elite=1.3).

- **Total HP Earned**: `sum(round(multiplied_line_hp * tier_multiplier))` across all non-addon food items.

- **Example**: Customer on Champion tier (1.2x) orders 2 Jollof Rice bowls @ ₦1,500 each (`hp_multiplier_snapshot` = 1.0).

  - `line_base_hp` = `int(3000 * 0.1)` = `300 HP`.

  - `total_hp` = `round(300 * 1.2)` = `360 HP` earned upon delivery.

- **Location**: `app/services/hp_service.py:calculate_delivery_hp()`.

- **DB Columns**: `orders.hp_earned`, `order_items.hp_multiplier_snapshot`, `profiles.hp_balance`.


### 2. Delivery Fee Calculation

- **On-Campus**: Fixed fee lookup per hostel in `hostels.delivery_fee` (e.g. ₦200).

- **Off-Campus**: `fee = round(max(base_fee + (dist_km * rate_per_km), min_fee), 2)` where `dist_km` is great-circle Haversine distance (`R = 6371.0` km) from physically nearest gate (`gate.lat/lon`) to customer pin (`user_lat/lon`).

- **Max Distance**: Checked against `kitchen_settings.max_delivery_radius_km` (e.g. 10 km from campus center). Exceeding radius returns HTTP 400: `"Delivery location is outside the maximum allowed radius of 10.0 km"`.

- **Example**: Off-campus delivery 3.2 km from South Gate (`base_fee` = ₦200, `rate_per_km` = ₦100, `min_fee` = ₦300).

  - `raw_fee` = `200 + (3.2 * 100)` = `₦520.00` (greater than min_fee ₦300) → `Delivery Fee = ₦520.00`.

- **Location**: `app/routes/delivery.py:calculate_off_campus_fee()`.


### 3. Discount Application Order

1. **Subtotal**: Sum of item prices.

2. **Delivery Fee**: On-campus or off-campus distance calculation.

3. **Squad Delivery Discount**: Percentage discount applied to delivery fee if squad order criteria met.

4. **Promo Code Discount**: Applied to Subtotal (`percentage` or `fixed`). Verified against `min_order_amount`, `max_uses`, and `max_uses_per_user`.

5. **Squad Subtotal Discount**: Percentage discount applied to Subtotal if enabled.

6. **Order Lock Discount**: Applied to Subtotal if order lock active.

7. **Total Amount**: `max(0, Subtotal - Promo Discount - Squad Discount - Order Lock Discount) + Delivery Fee`.


### 4. HP Tier Calculation

- **Metric**: Rolling 120-day active HP earned (`recalculate_120day_hp`).

- **Thresholds**:

  - `starter`: 0 – 999 HP (1.0x multiplier)

  - `regular`: 1,000 – 4,999 HP (1.1x multiplier)

  - `champion`: 5,000 – 11,999 HP (1.2x multiplier)

  - `elite`: 12,000+ HP (1.3x multiplier)

- **Upgrade**: Immediate upon passing threshold on HP transaction credit.

- **Downgrade**: If rolling 120-day HP falls below maintenance threshold, `tier_grace_ends_at` is set to 30 days in future. User retains tier benefits during grace period; if unfulfilled after 30 days, tier is downgraded.

- **Location**: `app/services/hp_service.py:update_user_tier()`.


### 5. Leaderboard Ranking Calculation

- **Metric**: Sum of active HP earned in current calendar month (`monthly_hp_earned`). Ties broken by earlier account registration timestamp.

- **Reset Schedule**: 1st of month at 00:01 WAT via `reset_monthly_leaderboard` task.

- **Prizes**: Top 10 rankers receive exclusive spins and free side credits; #1 ranker inducted into Hall of Fame.


### 6. Reward Flash Sale Discount Calculation

- **Discount**: 50% discount on HP redemption cost (`flash_hp_cost = reward.hp_cost // 2`).

- **Example**: A reward costing 500 HP costs 250 HP during an active flash sale window.

- **Slot Locking**: Remaining quantity slots locked atomically via `hg_redeem_flash_reward_atomic` RPC.


---
## SECTION 3: API ENDPOINT INVENTORY

Total documented REST API endpoints: **324**


### `GET /api/academic-levels`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/academic_levels.py` (`list_academic_levels`)

**Summary:** List active academic levels in sort order.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/academic-levels/<level_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/academic_levels.py` (`get_academic_level`)

**Summary:** Get a single academic level by ID (active only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Error Responses & Recovery Instructions:**

- `"Academic level not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/abandoned-carts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`abandoned_carts`)

**Summary:** List abandoned carts for recovery (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `abandoned_carts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/abandoned-carts/<cart_id>/nudge`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`nudge_cart`)

**Summary:** Manually trigger recovery nudge for an abandoned cart (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `abandoned_carts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/academic-levels`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_list_academic_levels`)

**Summary:** List all academic levels including inactive ones (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `is_active`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/academic-levels`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_create_academic_level`)

**Summary:** Create a new academic level (admin only).


**Request Specification:**

```json
{
    "is_active": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "sort_order": "any // OPTIONAL \u2014 default: null",
    "value": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Error Responses & Recovery Instructions:**

- `"'name' and 'value' are required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/admin/academic-levels/<level_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_deactivate_academic_level`)

**Summary:** Soft-delete (deactivate) an academic level (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Error Responses & Recovery Instructions:**

- `"Academic level not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/admin/academic-levels/<level_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_update_academic_level`)

**Summary:** Update an academic level (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Error Responses & Recovery Instructions:**

- `"Academic level not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"No valid fields to update"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/admin/academic-levels/<level_id>/restore`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_restore_academic_level`)

**Summary:** Reactivate a previously deactivated academic level (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Error Responses & Recovery Instructions:**

- `"Academic level not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/audit-log`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`audit_log`)

**Summary:** View admin audit log with pagination support (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `admin_audit_logs`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/campuses`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_campuses`)

**Summary:** List all campuses (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `campuses`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/cron/<job_name>`

**Authentication:** `super_admin` (JWT required)

**Source File:** `app/routes/admin.py` (`run_cron_job`)

**Summary:** Manually trigger a scheduled cron job (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/cron/status`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`cron_status`)

**Summary:** Show last run time, result, and status of every cron job (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `admin_audit_logs`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/delivery-batches`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_batches`)

**Summary:** List delivery batches with their assigned rider and order count (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status, window_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/delivery-batches`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`create_batch`)

**Summary:** Create a delivery batch and assign a rider (admin only).


**Request Specification:**

```json
{
    "order_ids": "any // OPTIONAL \u2014 default: null",
    "rider_id": "any // OPTIONAL \u2014 default: null",
    "window_id": "any // OPTIONAL \u2014 default: null",
    "zone": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, delivery_windows, orders, profiles`


**Error Responses & Recovery Instructions:**

- `"Delivery window belongs to a different campus"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Rider account is deactivated"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Rider user profile not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/admin/delivery-batches/<batch_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`cancel_batch`)

**Summary:** Cancel a delivery batch and unassign its orders (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/delivery-batches/<batch_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`get_batch`)

**Summary:** Get a delivery batch with all assigned orders (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, gates, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/delivery-batches/<batch_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`update_batch`)

**Summary:** Update a delivery batch's status (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/delivery-batches/<batch_id>/orders`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_batch_orders`)

**Summary:** List all orders assigned to a delivery batch (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "orders": [
        {
            "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "order_number": "HG-9A8B7C6D5E",
            "status": "delivered",
            "payment_status": "paid",
            "total_amount": 3200.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/delivery-windows`

**Authentication:** `admin, kitchen` (JWT required)

**Source File:** `app/routes/admin.py` (`list_windows`)

**Summary:** List delivery windows (admin/kitchen). Scoped by campus for kitchen users.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "delivery_windows": [
        {
            "id": "c1a2b3c4",
            "name": "Lunch Window",
            "start_time": "12:00:00",
            "end_time": "14:00:00",
            "is_active": true
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/delivery-windows`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`create_window`)

**Summary:** Create a delivery window (admin only).


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "capacity": "any // OPTIONAL \u2014 default: null",
    "ends_at": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null",
    "label": "any // OPTIONAL \u2014 default: null",
    "starts_at": "any // OPTIONAL \u2014 default: null",
    "zone_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "delivery_windows": [
        {
            "id": "c1a2b3c4",
            "name": "Lunch Window",
            "start_time": "12:00:00",
            "end_time": "14:00:00",
            "is_active": true
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows`


**Error Responses & Recovery Instructions:**

- `"capacity must be a positive integer"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"is_active must be a boolean"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"label must be a non-empty string"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/admin/delivery-windows/<window_id>/close`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`close_window`)

**Summary:** Close a delivery window (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "delivery_windows": [
        {
            "id": "c1a2b3c4",
            "name": "Lunch Window",
            "start_time": "12:00:00",
            "end_time": "14:00:00",
            "is_active": true
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/delivery-windows/<window_id>/reopen`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`reopen_window`)

**Summary:** Reopen a previously closed delivery window (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "delivery_windows": [
        {
            "id": "c1a2b3c4",
            "name": "Lunch Window",
            "start_time": "12:00:00",
            "end_time": "14:00:00",
            "is_active": true
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/departments`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_list_departments`)

**Summary:** List all departments including inactive ones (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `faculty, is_active`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/departments`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_create_department`)

**Summary:** Create a new department (admin only).


**Request Specification:**

```json
{
    "faculty": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "slug": "any // OPTIONAL \u2014 default: null",
    "sort_order": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Error Responses & Recovery Instructions:**

- `"'name' and 'faculty' are required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/admin/departments/<dept_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_deactivate_department`)

**Summary:** Soft-delete (deactivate) a department (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Error Responses & Recovery Instructions:**

- `"Department not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/admin/departments/<dept_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_update_department`)

**Summary:** Update a department (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Error Responses & Recovery Instructions:**

- `"Department not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"No valid fields to update"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/admin/departments/<dept_id>/restore`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_restore_department`)

**Summary:** Reactivate a previously deactivated department (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Error Responses & Recovery Instructions:**

- `"Department not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/exclusive-spin-prizes`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`list_exclusive_spin_prizes`)

**Summary:** List exclusive-spin physical prize fulfilment records.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `exclusive_spin_fulfillments, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/exclusive-spin-prizes/<record_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`fulfil_exclusive_spin_prize`)

**Summary:** Mark an exclusive-spin physical prize as fulfilled.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `exclusive_spin_fulfillments`


**Error Responses & Recovery Instructions:**

- `"Prize record not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/feature-flags`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`list_feature_flags`)

**Summary:** List all feature flags.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `feature_flags`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/feature-flags`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`create_feature_flag`)

**Summary:** Create a disabled feature flag.


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "description": "any // OPTIONAL \u2014 default: null",
    "feature_name": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `feature_flags`


**Error Responses & Recovery Instructions:**

- `"Feature flag already exists"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/feature-flags/<flag_name>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`get_feature_flag`)

**Summary:** Get a specific feature flag.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `feature_flags`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/feature-flags/<flag_name>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`update_feature_flag`)

**Summary:** Create or update a feature flag (upsert).


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "description": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `feature_flags`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/first-order-gifts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`list_first_order_gifts`)

**Summary:** Admin: list first-order gifts with user details.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `first_order_gifts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/first-order-gifts/<gift_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`update_first_order_gift`)

**Summary:** Admin: update a first-order gift status.


**Request Specification:**

```json
{
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `first_order_gifts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/hall-of-fame-rewards`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`list_hof_rewards`)

**Summary:** List Hall of Fame box reward records.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_rewards, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/hall-of-fame-rewards/<record_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`fulfil_hof_reward`)

**Summary:** Update a Hall of Fame reward record status.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_rewards`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/hp/bulk-grant`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`bulk_grant_hp`)

**Summary:** Bulk-grant HP to a segment of users (by tier, last-order date, etc.) — for promotions.


**Request Specification:**

```json
{
    "amount": "any // OPTIONAL \u2014 default: null",
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "dry_run": "any // OPTIONAL \u2014 default: null",
    "last_order_after": "any // OPTIONAL \u2014 default: null",
    "last_order_before": "any // OPTIONAL \u2014 default: null",
    "reason": "any // OPTIONAL \u2014 default: null",
    "tier_slug": "any // OPTIONAL \u2014 default: null",
    "user_ids": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers, orders, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/hp/report`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`hp_report`)

**Summary:** HP loyalty program health report — totals, tier distribution, top earners.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "period": "monthly",
    "total_hp_issued": 125000,
    "total_hp_redeemed": 45000,
    "net_active_hp": 80000,
    "active_users_count": 340
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/leaderboard-prizes`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`list_leaderboard_prizes`)

**Summary:** List leaderboard prize fulfilment records.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `month, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `leaderboard_reward_fulfillments, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/leaderboard-prizes/<record_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`fulfil_leaderboard_prize`)

**Summary:** Mark a leaderboard prize as fulfilled.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `leaderboard_reward_fulfillments`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/orders`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_all_orders`)

**Summary:** List all orders across all users (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, limit, offset, payment_method, status, to_date, user_id`


**Response Specification (200 OK Response):**

```json
{
    "orders": [
        {
            "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "order_number": "HG-9A8B7C6D5E",
            "status": "delivered",
            "payment_status": "paid",
            "total_amount": 3200.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/promo-codes`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_promos`)

**Summary:** List all promo codes (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_codes`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/promo-codes`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`create_promo`)

**Summary:** Create a promo code (admin only).


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "code": "any // OPTIONAL \u2014 default: null",
    "created_by": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null",
    "used_count": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_codes`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/promo-codes/<promo_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`update_promo`)

**Summary:** Update or deactivate a promo code (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_codes`


**Error Responses & Recovery Instructions:**

- `"discount_value must not exceed 100 for a percentage discount"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"is_active must be a boolean"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/promo-codes/<promo_id>/uses`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`promo_uses`)

**Summary:** Get redemption stats and usage history for a promo code (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_code_uses, promo_codes`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/reviews`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_reviews`)

**Summary:** List all order reviews with filters


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `kitchen_rating, limit, offset, rating, rider_rating`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_reviews, orders, profiles`


**Error Responses & Recovery Instructions:**

- `"kitchen_rating must be an integer between 1 and 5"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"limit must be a non-negative integer"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"limit must be between 0 and 200"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"offset must be >= 0"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"offset must be a non-negative integer"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"rating must be an integer between 1 and 5"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"rider_rating must be an integer between 1 and 5"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/settings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`list_settings`)

**Summary:** Admin: list all system settings.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `system_settings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/settings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`create_setting`)


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "description": "any // OPTIONAL \u2014 default: null",
    "key": "any // OPTIONAL \u2014 default: null",
    "value": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `system_settings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/settings/<key>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`update_setting`)


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "description": "any // OPTIONAL \u2014 default: null",
    "value": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `system_settings`


**Error Responses & Recovery Instructions:**

- `"hp_multiplier must be 0.5, 1.0, or 2.0"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/users`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_users`)

**Summary:** List all users with HP balance and tier info.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, offset, q, role`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/users/<user_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`get_user`)

**Summary:** Get full user profile with order history and HP ledger.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles, wallets`


**Error Responses & Recovery Instructions:**

- `"You don't have permission to view users from that campus"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/admin/users/<user_id>/activate`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`activate_user`)

**Summary:** Reactivate a previously deactivated user account (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/users/<user_id>/deactivate`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`deactivate_user`)

**Summary:** Deactivate a user account (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- `"Only super_admin users can deactivate a super_admin account"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"You cannot deactivate your own account"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/users/<user_id>/hp`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`user_hp_history`)

**Summary:** Get HP transaction history for a specific user (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/users/<user_id>/orders`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`user_order_history`)

**Summary:** Get complete order history for a specific user (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Response):**

```json
{
    "orders": [
        {
            "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "order_number": "HG-9A8B7C6D5E",
            "status": "delivered",
            "payment_status": "paid",
            "total_amount": 3200.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/users/<user_id>/role`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`change_user_role`)

**Summary:** Change a user's role (admin only). Use with caution.


**Request Specification:**

```json
{
    "role": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- `"Cannot change your own role"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Only super_admin can assign super_admin role"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/admin/users/<user_id>/wallet`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`user_wallet_history`)

**Summary:** Get wallet transaction history for a specific user (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, wallets`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/abandoned-carts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`abandoned_carts_analytics`)

**Summary:** Abandoned cart analytics — total, recovered, and unrecovered counts.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `abandoned_carts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/dashboard`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`dashboard_summary`)

**Summary:** Live admin dashboard — today's order pipeline, delivery batch status, revenue snapshot.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, delivery_windows, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/export`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`export_csv`)

**Summary:** Export analytics data as CSV (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, limit, to_date, type`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions, orders, profiles, wallet_transactions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/gifts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`gifts_analytics`)

**Summary:** Gift analytics — first-order gift status breakdown.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `first_order_gifts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/hp`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`hp_analytics`)

**Summary:** HP ecosystem analytics — issued vs redeemed, tier distribution.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date`


**Response Specification (200 OK Response):**

```json
{
    "period": "monthly",
    "total_hp_issued": 125000,
    "total_hp_redeemed": 45000,
    "net_active_hp": 80000,
    "active_users_count": 340
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers, hp_transactions, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/items`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`items_analytics`)

**Summary:** Item-level analytics — quantity sold and revenue per menu item over a date range.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, limit, to_date`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_items, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/marketplace`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`marketplace_analytics`)

**Summary:** Marketplace analytics — purchases, code inventory status.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings, marketplace_purchases`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/orders`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`orders_analytics`)

**Summary:** Order flow analytics — volume by window, zone coverage, status funnel, peak hours.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date`


**Response Specification (200 OK Response):**

```json
{
    "orders": [
        {
            "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "order_number": "HG-9A8B7C6D5E",
            "status": "delivered",
            "payment_status": "paid",
            "total_amount": 3200.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, delivery_windows, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/referrals`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`referral_analytics`)

**Summary:** Referral funnel analytics.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `referrals`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/retention`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`retention_analytics`)

**Summary:** Cohort retention — percentage of users who placed a second order,


**Request Specification:**

```json
{
    "retained": "any // OPTIONAL \u2014 default: null",
    "total": "any // OPTIONAL \u2014 default: null"
}
```

- **Query Parameters:** `campus_id, weeks`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/sales`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`sales_analytics`)

**Summary:** Sales analytics — revenue, order volume, AOV by date range.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/users`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`users_analytics`)

**Summary:** User analytics — DAU, MAU, and breakdown by tier.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers, orders, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/auth/account`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`delete_account`)

**Summary:** Delete the authenticated user's account (NDPR/GDPR self-deletion).


**Request Specification:**

```json
{
    "password": "any // REQUIRED \u2014 validation: must be provided and non-empty"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/auth/addresses`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`list_addresses`)

**Summary:** List all saved delivery addresses for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `user_addresses`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/addresses`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`add_address`)

**Summary:** Save a new delivery address for the authenticated user.


**Request Specification:**

```json
{
    "address_line": "any // OPTIONAL \u2014 default: null",
    "city": "any // OPTIONAL \u2014 default: null",
    "hostel": "any // OPTIONAL \u2014 default: null",
    "is_default": "any // OPTIONAL \u2014 default: null",
    "label": "any // OPTIONAL \u2014 default: null",
    "landmark": "any // OPTIONAL \u2014 default: null",
    "latitude": "any // OPTIONAL \u2014 default: null",
    "line1": "any // OPTIONAL \u2014 default: null",
    "line2": "any // OPTIONAL \u2014 default: null",
    "longitude": "any // OPTIONAL \u2014 default: null",
    "state": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `user_addresses`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/auth/addresses/<address_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`delete_address`)

**Summary:** Delete a saved delivery address.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `user_addresses`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/auth/addresses/<address_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`update_address`)

**Summary:** Update a saved delivery address.


**Request Specification:**

```json
{
    "address_line": "any // OPTIONAL \u2014 default: null",
    "is_default": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `user_addresses`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/change-password`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`change_password`)

**Summary:** Change password for the authenticated user.


**Request Specification:**

```json
{
    "current_password": "any // OPTIONAL \u2014 default: null",
    "new_password": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/device-token`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`register_device_token`)

**Summary:** Register or update a push-notification device token for the authenticated user.


**Request Specification:**

```json
{
    "device_model": "any // OPTIONAL \u2014 default: null",
    "platform": "any // OPTIONAL \u2014 default: null",
    "token": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `device_tokens`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/login`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`login`)

**Summary:** Login with email and password.


**Request Specification:**

```json
{
    "email": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "password": "any // REQUIRED \u2014 validation: must be provided and non-empty"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/logout`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`logout`)

**Summary:** Logout and invalidate session.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/logout-all-devices`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`logout_all_devices`)

**Summary:** Revoke all sessions and device tokens for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/auth/me`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`me`)

**Summary:** Get authenticated user's full profile including HP balance, tier, and wallet.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/auth/profile`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`update_profile`)

**Summary:** Update user profile fields.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/profile/photo`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`update_profile_photo`)

**Summary:** Update user profile photo with Cloudinary URL.


**Request Specification:**

```json
{
    "photo_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- `"photo_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/auth/refresh`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`refresh`)

**Summary:** Silently rotate the access token when it is within the expiry window.


**Request Specification:**

```json
{
    "access_token": "any // OPTIONAL \u2014 default: null",
    "refresh_token": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/register`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`register`)

**Summary:** Register a new student account.


**Request Specification:**

```json
{
    "academic_level": "any // OPTIONAL \u2014 default: null",
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "date_of_birth": "any // OPTIONAL \u2014 default: null",
    "department": "any // OPTIONAL \u2014 default: null",
    "email": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "full_name": "any // OPTIONAL \u2014 default: null",
    "password": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "phone": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "referred_by_code": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `campuses`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/reset-password`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`reset_password`)

**Summary:** Request password reset email.


**Request Specification:**

```json
{
    "email": "any // REQUIRED \u2014 validation: must be provided and non-empty"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/auth/streak`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`get_login_streak`)

**Summary:** Get the authenticated user's current login streak.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/verify-email`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`verify_email`)

**Summary:** Resend the email verification link to an unconfirmed address.


**Request Specification:**

```json
{
    "email": "any // REQUIRED \u2014 validation: must be provided and non-empty"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/cart`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`clear_cart`)

**Summary:** Remove all items from the authenticated user's cart.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/cart`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`get_cart`)

**Summary:** Get the authenticated user's cart with current item prices.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/cart`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`add_to_cart`)

**Summary:** Add an item to the cart. If the item already exists, quantity is incremented.


**Request Specification:**

```json
{
    "menu_item_id": "any // OPTIONAL \u2014 default: null",
    "notes": "any // OPTIONAL \u2014 default: null",
    "quantity": "any // OPTIONAL \u2014 default: null",
    "selected_addons": "any // OPTIONAL \u2014 default: null",
    "selected_variations": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items, menu_items`


**Error Responses & Recovery Instructions:**

- `"Menu item not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/cart/<item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`remove_cart_item`)

**Summary:** Remove a single item from the cart.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/cart/<item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`update_cart_item`)

**Summary:** Update quantity or notes for a cart item. Setting quantity to 0 removes it.


**Request Specification:**

```json
{
    "notes": "any // OPTIONAL \u2014 default: null",
    "quantity": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/challenges`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/challenges.py` (`list_challenges`)

**Summary:** List active challenges (milestones with time_window set).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `time_window`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/challenges/<milestone_id>/complete`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/challenges.py` (`complete_challenge`)

**Summary:** Attempt to complete a challenge or claim a badge.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/challenges/admin`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/challenges.py` (`admin_list_milestones`)

**Summary:** List all milestones (admin).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `is_active, limit, offset, time_window`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/challenges/admin`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/challenges.py` (`admin_create_milestone`)

**Summary:** Create a new milestone (admin).


**Request Specification:**

```json
{
    "time_window": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/challenges/admin/<milestone_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/challenges.py` (`admin_delete_milestone`)

**Summary:** Deactivate (soft-delete) a milestone (admin).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/challenges/admin/<milestone_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/challenges.py` (`admin_update_milestone`)

**Summary:** Update a milestone (admin).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/challenges/admin/<milestone_id>/grant`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/challenges.py` (`admin_grant_milestone`)

**Summary:** Manually grant a milestone to a user (admin).


**Request Specification:**

```json
{
    "user_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/challenges/badges`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/challenges.py` (`list_badges`)

**Summary:** List all badges (lifetime milestones, time_window IS NULL).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/challenges/my`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/challenges.py` (`my_milestones`)

**Summary:** Get the authenticated user's full milestone progress (badges + challenges).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/challenges/push-subscribed`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/challenges.py` (`push_subscribed_challenge`)

**Summary:** Register Web Push subscription and claim push subscription system milestone reward.


**Request Specification:**

```json
{
    "device_label": "any // OPTIONAL \u2014 default: null",
    "subscription": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones, push_subscriptions`


**Error Responses & Recovery Instructions:**

- `"Failed to update subscription"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Push subscribe milestone not configured or inactive"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/challenges/pwa-installed`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/challenges.py` (`pwa_installed`)

**Summary:** Claim PWA installation system milestone reward.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones`


**Error Responses & Recovery Instructions:**

- `"PWA install milestone not configured or inactive"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/challenges/pwa-push-bonus-status`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/challenges.py` (`pwa_push_bonus_status`)

**Summary:** Get PWA + Push Subscription bonus eligibility and status. Automatically awards bonus if eligible.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "pwa_install": {
        "completed": true,
        "hp_awarded": 50
    },
    "push_subscribe": {
        "completed": true,
        "hp_awarded": 50
    },
    "pwa_push_bonus": {
        "completed": true,
        "hp_awarded": 100
    }
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/challenges/social-follow`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/challenges.py` (`social_follow`)

**Summary:** Self-declare a social follow (one-time, HP → Pending, subject to monthly cap).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `milestones`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/checkin`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/daily_checkin.py` (`record_checkin`)

**Summary:** Record daily check-in for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- `"Check-in failed, please try again"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Unable to resolve campus for this request"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/checkin/history`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/daily_checkin.py` (`checkin_history`)

**Summary:** Return daily check-in history for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "history": [
        {
            "status": "received",
            "created_at": "2026-03-31T12:00:00Z",
            "changed_by": "customer"
        },
        {
            "status": "preparing",
            "created_at": "2026-03-31T12:05:00Z",
            "changed_by": "kitchen"
        },
        {
            "status": "delivered",
            "created_at": "2026-03-31T12:25:00Z",
            "changed_by": "rider"
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `daily_checkins`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/delivery/admin/gates`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_list_gates`)

**Summary:** List all gates including inactive (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/delivery/admin/gates`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_create_gate`)

**Summary:** Create a delivery gate (admin only).


**Request Specification:**

```json
{
    "base_fee": "any // OPTIONAL \u2014 default: null",
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null",
    "lat": "any // OPTIONAL \u2014 default: null",
    "lon": "any // OPTIONAL \u2014 default: null",
    "min_fee": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "rate_per_km": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Error Responses & Recovery Instructions:**

- `"'name' is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Unable to resolve campus for this request"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"campus_id is required for super_admin"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/delivery/admin/gates/<gate_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_delete_gate`)

**Summary:** Deactivate a gate (admin only). Does not permanently delete.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Error Responses & Recovery Instructions:**

- `"Gate not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/delivery/admin/gates/<gate_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_update_gate`)

**Summary:** Update a delivery gate (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Error Responses & Recovery Instructions:**

- `"Gate not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"No valid fields to update"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/delivery/admin/hostels`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_list_hostels`)

**Summary:** List all hostels including inactive ones (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/delivery/admin/hostels`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_create_hostel`)

**Summary:** Create a new on-campus hostel (admin only).


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "delivery_fee": "any // OPTIONAL \u2014 default: null",
    "gate_id": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Error Responses & Recovery Instructions:**

- `"Unable to resolve campus for this request"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"campus_id is required for super_admin"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/delivery/admin/hostels/<hostel_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_delete_hostel`)

**Summary:** Deactivate a hostel (admin only). Does not permanently delete.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Error Responses & Recovery Instructions:**

- `"Hostel not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/delivery/admin/hostels/<hostel_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_update_hostel`)

**Summary:** Update an on-campus hostel (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Error Responses & Recovery Instructions:**

- `"Hostel not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"No valid fields to update"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/delivery/calculate-fee`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/delivery.py` (`calculate_fee`)

**Summary:** Preview the delivery fee before placing an order.


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "delivery_location_id": "any // OPTIONAL \u2014 default: null",
    "delivery_type": "any // OPTIONAL \u2014 default: null",
    "lat": "any // OPTIONAL \u2014 default: null",
    "lon": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates, hostels`


**Error Responses & Recovery Instructions:**

- `"'delivery_location_id' is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Gate not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Hostel not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"This location is outside our delivery area."` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"delivery_type must be 'on_campus' or 'off_campus'"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/delivery/gates`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/delivery.py` (`list_gates`)

**Summary:** List all active delivery gates (used for off-campus fee calculation) for the selected campus.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/delivery/hostels`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/delivery.py` (`list_hostels`)

**Summary:** List all active on-campus hostels with their delivery fees for the selected campus.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/departments`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/departments.py` (`list_departments`)

**Summary:** List active departments, optionally grouped by faculty.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `faculty, grouped`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/departments/<dept_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/departments.py` (`get_department`)

**Summary:** Get a single department by ID.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Error Responses & Recovery Instructions:**

- `"Department not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/departments/faculties`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/departments.py` (`list_faculties`)

**Summary:** List distinct faculty names from active departments.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/docs/`

**Authentication:** Public (No auth token required)

**Source File:** `/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/flask/views.py` (`apidocs`)

**Summary:** The /apidocs


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/docs/apispec.json`

**Authentication:** Public (No auth token required)

**Source File:** `/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/flask/views.py` (`apispec`)

**Summary:** The /apispec_1.json and other specs


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/docs/static/<path:filename>`

**Authentication:** Public (No auth token required)

**Source File:** `/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/flask/blueprints.py` (`send_static_file`)

**Summary:** The view function used to serve files from


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`list_events`)

**Summary:** List published upcoming events for the selected campus (or all if unspecified).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`create_event`)

**Summary:** Create a new event listing (admin only).


**Request Specification:**

```json
{
    "ends_at": "any // OPTIONAL \u2014 default: null",
    "hp_per_attendee": "any // OPTIONAL \u2014 default: null",
    "hp_reward": "any // OPTIONAL \u2014 default: null",
    "is_published": "any // OPTIONAL \u2014 default: null",
    "organizer_id": "any // OPTIONAL \u2014 default: null",
    "slug": "any // OPTIONAL \u2014 default: null",
    "starts_at": "any // OPTIONAL \u2014 default: null",
    "title": "any // REQUIRED \u2014 validation: must be provided and non-empty"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Error Responses & Recovery Instructions:**

- `"Unable to resolve campus for this request"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/events/<event_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`delete_event`)

**Summary:** Delete an event (admin only). Cascades to event_tickets and checkins.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_tickets, events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/<event_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`get_event`)

**Summary:** Get event detail.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_tickets, events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/events/<event_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`update_event`)

**Summary:** Update an event (admin only).


**Request Specification:**

```json
{
    "hp_per_attendee": "any // OPTIONAL \u2014 default: null",
    "hp_reward": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_tickets, events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/<event_id>/checkin`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/events.py` (`checkin`)

**Summary:** Check in to a Holy Grills event using QR token or ticket ID / guest email.


**Request Specification:**

```json
{
    "email": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "guest_email": "any // OPTIONAL \u2014 default: null",
    "qr_token": "any // OPTIONAL \u2014 default: null",
    "ticket_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_tickets, events, profiles`


**Error Responses & Recovery Instructions:**

- `"Invalid door QR token"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/events/<event_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`update_event_image`)

**Summary:** Update event image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Error Responses & Recovery Instructions:**

- `"image_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/events/<event_id>/qr`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`generate_event_qr`)

**Summary:** Generate a QR token for event check-in (admin only).


**Request Specification:**

```json
{
    "qr_token": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/<event_id>/register`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/events.py` (`register_for_event`)

**Summary:** Register for an event. Supports ticket tiers, an optional HP discount


**Request Specification:**

```json
{
    "callback_url": "any // OPTIONAL \u2014 default: null",
    "email": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "guest_email": "any // OPTIONAL \u2014 default: null",
    "guest_name": "any // OPTIONAL \u2014 default: null",
    "guest_phone": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "payment_method": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "phone": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "promo_code": "any // OPTIONAL \u2014 default: null",
    "registration_answers": "any // OPTIONAL \u2014 default: null",
    "tier_id": "any // OPTIONAL \u2014 default: null",
    "use_hp": "any // OPTIONAL \u2014 default: null",
    "wallet_amount": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events, profiles, promo_codes`


**Error Responses & Recovery Instructions:**

- `"This ticket has no HP discount available"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Ticket tier not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/events/<event_id>/registrants`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`list_event_registrants`)

**Summary:** List all registrants for an event (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `format`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_ticket_tiers, event_tickets, events, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/<event_id>/send-registrants-to-host`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`send_registrants_to_host`)

**Summary:** Email the full registrant list to the event organiser / host.


**Request Specification:**

```json
{
    "custom_message": "any // OPTIONAL \u2014 default: null",
    "host_email": "any // OPTIONAL \u2014 default: null",
    "host_name": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, event_tickets, events, profiles`


**Error Responses & Recovery Instructions:**

- `"Failed to send email — check RESEND_API_KEY"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"host_email is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/events/<event_id>/tickets/<ticket_id>/pdf`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/events.py` (`download_ticket_pdf`)

**Summary:** Download a PDF version of an event ticket, with the same QR the


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `guest_email`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, event_tickets, events`


**Error Responses & Recovery Instructions:**

- `"You do not have access to this ticket"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/events/<event_id>/tiers`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`list_event_tiers`)

**Summary:** List ticket tiers for an event (public).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/<event_id>/tiers`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`create_event_tier`)

**Summary:** Create a ticket tier for an event (admin only).


**Request Specification:**

```json
{
    "capacity": "any // OPTIONAL \u2014 default: null",
    "color": "any // OPTIONAL \u2014 default: null",
    "description": "any // OPTIONAL \u2014 default: null",
    "early_bird_deadline": "any // OPTIONAL \u2014 default: null",
    "features": "any // OPTIONAL \u2014 default: null",
    "icon": "any // OPTIONAL \u2014 default: null",
    "is_early_bird": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "price_hp": "any // OPTIONAL \u2014 default: null",
    "price_naira": "any // OPTIONAL \u2014 default: null",
    "terms": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/<event_id>/tiers/comparison`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`get_tier_comparison`)

**Summary:** Fetch tier comparison view for an event (public).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/admin`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`admin_list_events`)

**Summary:** List all events including unpublished (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, published_only`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/catering-requests`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`list_catering_requests`)

**Summary:** List catering/event partnership requests (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `catering_requests`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/catering-requests`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`submit_catering_request`)

**Summary:** Submit a catering / event partnership request.


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "event_name": "any // OPTIONAL \u2014 default: null",
    "organizer_name": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `catering_requests, profiles`


**Error Responses & Recovery Instructions:**

- `"campus_id is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/events/catering-requests/<request_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`update_catering_request`)

**Summary:** Respond to a catering request — accept, reject, or add notes (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `catering_requests, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/my-tickets`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/events.py` (`my_tickets`)

**Summary:** Show all tickets for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_tickets, events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/events/tiers/<tier_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`delete_event_tier`)

**Summary:** Delete a ticket tier (admin only). Forbidden if any tickets sold.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/events/tiers/<tier_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`update_event_tier`)

**Summary:** Update a ticket tier (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/tiers/<tier_id>/detail`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`get_tier_detail`)

**Summary:** Return full tier detail with event info.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/exclusive-spin`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/exclusive_spin.py` (`my_spins`)

**Summary:** Return the authenticated user's available exclusive spin credits.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/exclusive-spin/spin`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/exclusive_spin.py` (`do_spin`)

**Summary:** Consume one exclusive spin credit and return the prize.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `exclusive_spins`


**Error Responses & Recovery Instructions:**

- `"No spin credits available or concurrent update occurred. Please try again."` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/free-sides`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/free_sides.py` (`my_free_sides`)

**Summary:** Return the authenticated user's free side credit balance and active rows.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/free-sides/redeem`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/free_sides.py` (`redeem_free_side`)

**Summary:** Redeem one free side credit.


**Request Specification:**

```json
{
    "order_id": "any // OPTIONAL \u2014 default: null",
    "side_choice": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `free_side_credits, order_items, orders`


**Error Responses & Recovery Instructions:**

- `"Failed to apply free side to order — your credit has not been used, please try again"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"No credits available or concurrent update occurred. Please try again."` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"This order can no longer be modified"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"order_id is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/graduation/claim`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/graduation.py` (`claim_graduation`)

**Summary:** Claim the graduation HP bonus. One-time only.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels, profiles, system_settings`


**Error Responses & Recovery Instructions:**

- `"Failed to award graduation HP — please try again"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/health`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/health.py` (`health`)

**Summary:** API health check — connectivity to Supabase and Redis.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/hp/admin/expire`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/hp.py` (`admin_expire`)

**Summary:** Admin manually expires HP for a user.


**Request Specification:**

```json
{
    "amount": "any // OPTIONAL \u2014 default: null",
    "notes": "any // OPTIONAL \u2014 default: null",
    "user_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- `"Cannot expire HP outside your campus"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Target user profile not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/hp/admin/grant`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/hp.py` (`admin_grant`)

**Summary:** Admin manually grants HP to a user.


**Request Specification:**

```json
{
    "amount": "any // OPTIONAL \u2014 default: null",
    "notes": "any // OPTIONAL \u2014 default: null",
    "user_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- `"Cannot grant HP outside your campus"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Target user profile not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"amount must be a positive number — use /admin/expire to reduce HP"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/hp/balance`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`balance`)

**Summary:** Get user's HP balance: active, pending, total_visible.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/hp/bundles`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/hp.py` (`list_hp_bundles`)

**Summary:** List available HP bundle tiers that can be purchased.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/hp/bundles/purchase`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`purchase_hp_bundle`)

**Summary:** Purchase an HP bundle (event hosts). Charges card via Paystack reference, credits HP.


**Request Specification:**

```json
{
    "amount": "any // OPTIONAL \u2014 default: null",
    "hp_amount": "any // OPTIONAL \u2014 default: null",
    "paystack_reference": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_bundle_purchases`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/hp/flash-redeem/<reward_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`flash_redeem`)

**Summary:** Redeem a reward at the flash-sale price (50% HP discount, limited slots, 24h window).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/hp/tiers`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/hp.py` (`list_tiers`)

**Summary:** List all tiers with thresholds and perks.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/hp/transactions`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`transactions`)

**Summary:** Get HP transaction history for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, type`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/hp/transfer`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`transfer_hp`)

**Summary:** Transfer active HP to another user.


**Request Specification:**

```json
{
    "amount": "any // OPTIONAL \u2014 default: null",
    "notes": "any // OPTIONAL \u2014 default: null",
    "recipient_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions, orders, profiles, system_settings`


**Error Responses & Recovery Instructions:**

- `"Transfer failed and could not be auto-refunded — contact support"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Transfer failed — your HP has been refunded, please try again"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/hp/unlock-history`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`unlock_history`)

**Summary:** Get HP unlock history for the authenticated user (from hp_transactions type=unlock).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "history": [
        {
            "status": "received",
            "created_at": "2026-03-31T12:00:00Z",
            "changed_by": "customer"
        },
        {
            "status": "preparing",
            "created_at": "2026-03-31T12:05:00Z",
            "changed_by": "kitchen"
        },
        {
            "status": "delivered",
            "created_at": "2026-03-31T12:25:00Z",
            "changed_by": "rider"
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/batch-summary/<window_id>`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`batch_summary`)

**Summary:** Get aggregated item counts across all active orders in a delivery window batch.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/kitchen/batch/<batch_id>/advance`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`batch_advance`)

**Summary:** Advance every order in a delivery-window batch to its next status.


**Request Specification:**

```json
{
    "from_status": "any // OPTIONAL \u2014 default: null",
    "notes": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- `"No advanceable orders found in this batch"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/kitchen/metrics`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`kitchen_metrics`)

**Summary:** Kitchen performance metrics — average prep time, throughput per window, completion rate.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `window_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/queue`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`live_queue`)

**Summary:** Get live order queue for kitchen. Shows received and preparing orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `window_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/scheduled`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`scheduled_orders`)

**Summary:** Get all scheduled orders awaiting promotion to the live queue.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `window_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/settings`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`get_kitchen_settings`)

**Summary:** Get all kitchen settings as a key/value map.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `kitchen_settings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/kitchen/settings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`update_kitchen_settings`)

**Summary:** Update one or more kitchen settings (key/value upsert). Admin only.


**Request Specification:**

```json
{
    "settings": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `kitchen_settings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/settings/<key>`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`get_kitchen_setting`)

**Summary:** Get a single kitchen setting by key.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `kitchen_settings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/windows`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`delivery_windows`)

**Summary:** Get current and upcoming delivery windows for kitchen view.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`get_leaderboard`)

**Summary:** Get leaderboard. period_type: monthly | weekly | all_time.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, period_type`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `leaderboard_snapshots, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/hall-of-fame`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`hall_of_fame`)

**Summary:** Permanent Hall of Fame — global monthly leaderboard #1 winners by period,


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_inductees, leaderboard_snapshots`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/hall-of-fame/inductees`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`hall_of_fame_inductees`)

**Summary:** All Hall of Fame inductees — users who reached 4 top-4 leaderboard finishes (global).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_inductees, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/hall-of-fame/inductees/<inductee_user_id>/card`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`inductee_share_card`)

**Summary:** Shareable induction card data for a specific Hall of Fame inductee (global).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_inductees, profiles`


**Error Responses & Recovery Instructions:**

- `"Inductee not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/leaderboard/my-rank`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/leaderboard.py` (`my_rank`)

**Summary:** Get authenticated user's current rank and HP stats.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, period_type`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `leaderboard_snapshots, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/squad`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`squad_leaderboard`)

**Summary:** Squad leaderboard — ranks squads by combined HP earned from squad orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, period_type`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles, squad_members`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/squad/my-rank`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/leaderboard.py` (`squad_my_rank`)

**Summary:** Get the authenticated user's position in the squad leaderboard.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, period_type`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/marketplace`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/marketplace.py` (`list_listings`)

**Summary:** List active marketplace listings with availability filters (login required).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `category, listing_type, q`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listing_availability, marketplace_listings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/marketplace/<listing_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/marketplace.py` (`get_listing`)

**Summary:** Get marketplace listing detail (login required).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/<listing_id>/purchase`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/marketplace.py` (`purchase`)

**Summary:** Purchase a marketplace listing. Uses atomic hg_purchase_marketplace_item RPC.


**Request Specification:**

```json
{
    "payment_method": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "payment_reference": "any // OPTIONAL \u2014 default: null",
    "use_hp": "any // OPTIONAL \u2014 default: null",
    "wallet_amount": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/admin/codes/<listing_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`upload_codes`)

**Summary:** Upload access codes for a listing (admin only). Accepts list of code strings.


**Request Specification:**

```json
{
    "codes": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/marketplace/admin/listings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_list_listings`)

**Summary:** List all marketplace listings regardless of status (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/admin/listings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_create_listing`)

**Summary:** Create a marketplace listing directly (admin only).


**Request Specification:**

```json
{
    "listing_type": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/marketplace/admin/listings/<listing_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_delete_listing`)

**Summary:** Delete a marketplace listing (admin only). Also removes associated access codes.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings, marketplace_purchases`


**Error Responses & Recovery Instructions:**

- `"Cannot delete listing with existing purchase history"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/marketplace/admin/listings/<listing_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_get_listing`)

**Summary:** Get full marketplace listing detail, including archived/rejected listings (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings, marketplace_purchases`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/marketplace/admin/listings/<listing_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_update_listing`)

**Summary:** Approve, reject, or update a marketplace listing (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/marketplace/admin/listings/<listing_id>/availability`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`update_listing_availability`)


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listing_availability`


**Error Responses & Recovery Instructions:**

- `"At least one availability field is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"campus_id is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/marketplace/admin/listings/<listing_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`update_listing_image`)

**Summary:** Update marketplace listing image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Error Responses & Recovery Instructions:**

- `"image_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/marketplace/admin/purchases`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_all_purchases`)

**Summary:** List all marketplace purchases across all users (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, listing_id, offset, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_purchases`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/marketplace/admin/purchases/<purchase_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_update_purchase`)

**Summary:** Admin: update marketplace purchase status with buyer notification.


**Request Specification:**

```json
{
    "admin_note": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_purchases`


**Error Responses & Recovery Instructions:**

- `"Cannot refund card portion: purchase has no payment_reference"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/marketplace/admin/requests`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_list_requests`)

**Summary:** List vendor listing requests for admin review.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_requests`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/marketplace/admin/requests/<request_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_respond_to_request`)

**Summary:** Approve or reject a vendor listing request (admin only).


**Request Specification:**

```json
{
    "admin_notes": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_requests`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/listings/<listing_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`update_listing_image`)

**Summary:** Update marketplace listing image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Error Responses & Recovery Instructions:**

- `"image_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/marketplace/purchases`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/marketplace.py` (`my_purchases`)

**Summary:** Get the authenticated user's marketplace purchase history.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_purchases`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/requests`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/marketplace.py` (`submit_listing_request`)

**Summary:** Submit a vendor listing request for admin review (login required).


**Request Specification:**

```json
{
    "category": "any // OPTIONAL \u2014 default: null",
    "description": "any // OPTIONAL \u2014 default: null",
    "proposed_price": "any // OPTIONAL \u2014 default: null",
    "service_title": "any // OPTIONAL \u2014 default: null",
    "vendor_email": "any // OPTIONAL \u2014 default: null",
    "vendor_name": "any // OPTIONAL \u2014 default: null",
    "vendor_phone": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_requests, profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/menu/addons`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/menu.py` (`list_addons`)

**Summary:** List available add-on items — optional extras customers can append to any order


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addons`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/menu/addons`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_addon`)

**Summary:** Create an add-on item (admin only).


**Request Specification:**

```json
{
    "description": "any // OPTIONAL \u2014 default: null",
    "group_id": "any // OPTIONAL \u2014 default: null",
    "is_available": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "price": "any // OPTIONAL \u2014 default: null",
    "sort_order": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addons`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/addons/<addon_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_addon`)

**Summary:** Update an add-on item (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addons`


**Error Responses & Recovery Instructions:**

- `"Add-on not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/menu/addons/<addon_id>/archive`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`archive_addon`)

**Summary:** Archive an add-on item (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addons`


**Error Responses & Recovery Instructions:**

- `"Add-on not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/menu/categories`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/menu.py` (`list_categories`)

**Summary:** List all active menu categories for the current campus (guest or authenticated).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/menu/categories`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_category`)

**Summary:** Create a new menu category (admin only).


**Request Specification:**

```json
{
    "description": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "slug": "any // OPTIONAL \u2014 default: null",
    "sort_order": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/menu/categories/<category_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`delete_category`)

**Summary:** Deactivate a menu category (admin only). Does not delete items within it.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/categories/<category_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_category`)

**Summary:** Update a menu category (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/menu/items`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/menu.py` (`list_items`)

**Summary:** List menu items with availability, daily stock, and kitchen capacity metadata for the current campus (guest or authenticated).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `available_only, category, is_featured, q`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories, menu_item_availability, menu_items`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/menu/items`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_item`)

**Summary:** Create a new menu item (admin only).


**Request Specification:**

```json
{
    "hp_multiplier": "any // OPTIONAL \u2014 default: null",
    "is_available": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "slug": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items`


**Error Responses & Recovery Instructions:**

- `"hp_multiplier must be 0.5, 1.0, or 2.0"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/menu/items/<item_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/menu.py` (`get_item`)

**Summary:** Get single menu item detail including variation groups, options, and daily stock.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_groups, menu_item_variation_options, menu_items`


**Error Responses & Recovery Instructions:**

- `"Item not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/menu/items/<item_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_item`)

**Summary:** Update a menu item (admin only). Supports setting or clearing daily_limit.


**Request Specification:**

```json
{
    "hp_multiplier": "any // OPTIONAL \u2014 default: null",
    "is_available": "any // OPTIONAL \u2014 default: null",
    "updated_at": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items`


**Error Responses & Recovery Instructions:**

- `"Menu item not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"hp_multiplier must be 0.5, 1.0, or 2.0"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/menu/items/<item_id>/addon-groups`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_addon_group`)

**Summary:** Create a required (or optional) add-on group on a menu item, e.g.


**Request Specification:**

```json
{
    "is_required": "any // OPTIONAL \u2014 default: null",
    "max_select": "any // OPTIONAL \u2014 default: null",
    "min_select": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "sort_order": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addon_groups, menu_items`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/menu/items/<item_id>/addon-groups/<group_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`delete_addon_group`)

**Summary:** Permanently delete an add-on group and all its linked add-ons (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addon_groups`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/items/<item_id>/addon-groups/<group_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_addon_group`)

**Summary:** Update an add-on group (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addon_groups`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/menu/items/<item_id>/addons`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/menu.py` (`get_item_addons`)

**Summary:** Get add-on groups (e.g. "Sides", "Sauces") for a menu item, each with its


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addon_groups, menu_addons, menu_items`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/menu/items/<item_id>/archive`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`archive_item`)

**Summary:** Soft-archive a menu item (admin only). Order history is preserved.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/items/<item_id>/availability`

**Authentication:** `admin, kitchen` (JWT required)

**Source File:** `app/routes/menu.py` (`update_item_availability`)

**Summary:** Update this campus's availability for a menu item — on/off, daily cap,


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_availability, menu_items`


**Error Responses & Recovery Instructions:**

- `"At least one availability field is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"campus_id is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/menu/items/<item_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_menu_item_image`)

**Summary:** Update menu item image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items`


**Error Responses & Recovery Instructions:**

- `"image_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/menu/items/<item_id>/variation-groups`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_variation_group`)

**Summary:** Create a variation group on a menu item (admin only).


**Request Specification:**

```json
{
    "is_required": "any // OPTIONAL \u2014 default: null",
    "max_selections": "any // OPTIONAL \u2014 default: null",
    "min_selections": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "sort_order": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_groups`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/menu/items/<item_id>/variation-groups/<group_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`delete_variation_group`)

**Summary:** Delete a variation group and all its options (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_groups, menu_item_variation_options`


**Error Responses & Recovery Instructions:**

- `"Variation group not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/menu/items/<item_id>/variation-groups/<group_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_variation_group`)

**Summary:** Update a variation group (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_groups`


**Error Responses & Recovery Instructions:**

- `"Variation group not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/menu/items/<item_id>/variation-groups/<group_id>/options`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_variation_option`)

**Summary:** Add a choice option to a variation group (admin only).


**Request Specification:**

```json
{
    "is_available": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "price_delta": "any // OPTIONAL \u2014 default: null",
    "sort_order": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_options`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/menu/items/<item_id>/variation-groups/<group_id>/options/<option_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`delete_variation_option`)

**Summary:** Delete a variation option (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_options`


**Error Responses & Recovery Instructions:**

- `"Variation option not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/menu/items/<item_id>/variation-groups/<group_id>/options/<option_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_variation_option`)

**Summary:** Update a variation option (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_options`


**Error Responses & Recovery Instructions:**

- `"Variation option not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/menu/items/bulk-availability`

**Authentication:** `admin, kitchen` (JWT required)

**Source File:** `app/routes/menu.py` (`bulk_update_availability`)

**Summary:** Bulk update availability for multiple menu items (admin/kitchen).


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "is_available": "any // OPTIONAL \u2014 default: null",
    "item_ids": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_availability, menu_items`


**Error Responses & Recovery Instructions:**

- `"campus_id is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/menu/kitchen-capacity`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/menu.py` (`get_kitchen_capacity`)

**Summary:** Get the kitchen's current daily order capacity and today's order count.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/kitchen-capacity`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`set_kitchen_capacity`)

**Summary:** Set the kitchen's daily order capacity (admin only).


**Request Specification:**

```json
{
    "daily_order_capacity": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `kitchen_settings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/notifications`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`my_notifications`)

**Summary:** Get authenticated user's notification inbox.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, unread_only`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notifications`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/notifications/<notification_id>/read`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`mark_read`)

**Summary:** Mark a notification as read.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/notifications/blasts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/notifications.py` (`list_blasts`)

**Summary:** List notification blast history (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, offset, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_blasts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/notifications/blasts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/notifications.py` (`create_blast`)

**Summary:** Create and optionally send a notification blast (admin only).


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "created_by": "any // OPTIONAL \u2014 default: null",
    "scheduled_at": "any // OPTIONAL \u2014 default: null",
    "segment": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_blasts`


**Error Responses & Recovery Instructions:**

- `"Unable to create blast for the specified campus"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/notifications/blasts/<blast_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/notifications.py` (`get_blast`)

**Summary:** Get a single notification blast's detail (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_blasts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/notifications/preferences`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`get_preferences`)

**Summary:** Get the authenticated user's notification preferences.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_preferences`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/notifications/preferences`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`update_preferences`)

**Summary:** Update the authenticated user's notification preferences.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_preferences`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/notifications/read-all`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`mark_all_read`)

**Summary:** Mark all in-app notifications as read.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notifications`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/order-locks`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`list_locks`)

**Summary:** List the authenticated user's order locks.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/order-locks`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`create_lock`)

**Summary:** Lock-in a future order date with a discount.


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "discount_pct": "any // OPTIONAL \u2014 default: null",
    "locked_date": "any // OPTIONAL \u2014 default: null",
    "reschedule_count": "any // OPTIONAL \u2014 default: null",
    "reward_hp_amount": "any // OPTIONAL \u2014 default: null",
    "reward_type": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Error Responses & Recovery Instructions:**

- `"User already has an active lock"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"reward_type must be 'discount' or 'hp'"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/order-locks/<lock_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`cancel_lock`)

**Summary:** Cancel an active order lock.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/order-locks/<lock_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`get_lock`)

**Summary:** Get a specific order lock.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/order-locks/<lock_id>/reschedule`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`reschedule_lock`)

**Summary:** Reschedule a locked order date. Allowed once only.


**Request Specification:**

```json
{
    "locked_date": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/order-locks/admin/all`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/order_locks.py` (`admin_list_locks`)

**Summary:** Admin: list all order locks with filters.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, date, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`list_orders`)

**Summary:** List authenticated user's orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Response):**

```json
{
    "orders": [
        {
            "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "order_number": "HG-9A8B7C6D5E",
            "status": "delivered",
            "payment_status": "paid",
            "total_amount": 3200.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/orders.py` (`create_order`)


**Request Specification:**

```json
{
    "items": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "payment_method": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "user_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/<order_id>`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/orders.py` (`get_order`)

**Summary:** Get order detail. Authenticated users can only see their own orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `claim_token`


**Response Specification (200 OK Response):**

```json
{
    "orders": [
        {
            "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "order_number": "HG-9A8B7C6D5E",
            "status": "delivered",
            "payment_status": "paid",
            "total_amount": 3200.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/<order_id>/call-rider`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`call_assigned_rider`)

**Summary:** Return a dynamic call link for the rider assigned to the order.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "call_link": "tel:+2348012345678",
    "rider_phone": "08012345678",
    "rider_name": "Delivery Rider Alex"
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/cancel`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`cancel_order`)

**Summary:** Cancel an order. Only the order owner can cancel, and only while status is 'received'.


**Request Specification:**

```json
{
    "reason": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/claim`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`claim_guest_order`)

**Summary:** Link a guest order to a newly created account.


**Request Specification:**

```json
{
    "claim_token": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- `"Order is already owned or claimed"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/orders/<order_id>/history`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/orders.py` (`order_status_history`)

**Summary:** Get the full status change history for an order.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "history": [
        {
            "status": "received",
            "created_at": "2026-03-31T12:00:00Z",
            "changed_by": "customer"
        },
        {
            "status": "preparing",
            "created_at": "2026-03-31T12:05:00Z",
            "changed_by": "kitchen"
        },
        {
            "status": "delivered",
            "created_at": "2026-03-31T12:25:00Z",
            "changed_by": "rider"
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_status_logs, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/refund`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/orders.py` (`refund_order`)

**Summary:** Initiate a refund for an order (admin only).


**Request Specification:**

```json
{
    "reason": "any // OPTIONAL \u2014 default: null",
    "refund_amount": "any // OPTIONAL \u2014 default: null",
    "refund_to_wallet": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, wallet_transactions`


**Error Responses & Recovery Instructions:**

- `"Cannot refund an unpaid cancelled order"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"This order has already been fully refunded."` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/orders/<order_id>/reorder`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`reorder`)

**Summary:** Fetch items from a past order to pre-populate a new order (reorder helper).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items, order_items, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/review`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`submit_review`)

**Summary:** Submit an order review with optional kitchen and rider star ratings (earns HP on every review).


**Request Specification:**

```json
{
    "comment": "any // OPTIONAL \u2014 default: null",
    "kitchen_rating": "any // OPTIONAL \u2014 default: null",
    "rating": "any // OPTIONAL \u2014 default: null",
    "rider_rating": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_reviews, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/review/images`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`add_review_images`)

**Summary:** Add images to an order review.


**Request Specification:**

```json
{
    "image_urls": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_reviews`


**Error Responses & Recovery Instructions:**

- `"image_urls is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/orders/<order_id>/scheduled`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`cancel_scheduled_order`)

**Summary:** Cancel a scheduled order before it is due for preparation.


**Request Specification:**

```json
{
    "reason": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/share`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`record_order_share`)

**Summary:** Record that the user shared their order confirmation (e.g. on WhatsApp).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_share_events, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/squad-members`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`add_squad_members`)

**Summary:** Add squad members to a squad order for HP splitting.


**Request Specification:**

```json
{
    "emails": "any // OPTIONAL \u2014 default: null",
    "split_hp": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles, squad_members`


**Error Responses & Recovery Instructions:**

- `"At least one email is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/orders/<order_id>/status`

**Authentication:** `admin, kitchen, rider` (JWT required)

**Source File:** `app/routes/orders.py` (`update_status`)

**Summary:** Update order status (kitchen/rider/admin).


**Request Specification:**

```json
{
    "notes": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/walk`

**Authentication:** `admin, kitchen, rider` (JWT required)

**Source File:** `app/routes/orders.py` (`walk_order_status`)

**Summary:** Walk an order through all intermediate states to reach a target status in


**Request Specification:**

```json
{
    "notes": "any // OPTIONAL \u2014 default: null",
    "target_status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/active`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`active_order`)

**Summary:** Get the authenticated user's current active (in-progress) order, if any.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "orders": [
        {
            "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "order_number": "HG-9A8B7C6D5E",
            "status": "delivered",
            "payment_status": "paid",
            "total_amount": 3200.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/delivery-windows`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/orders.py` (`list_delivery_windows`)

**Summary:** List upcoming open delivery windows available for ordering.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "delivery_windows": [
        {
            "id": "c1a2b3c4",
            "name": "Lunch Window",
            "start_time": "12:00:00",
            "end_time": "14:00:00",
            "is_active": true
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/delivery-windows/status`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/orders.py` (`delivery_windows_status`)

**Summary:** Return whether the kitchen is currently open and list available delivery


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "delivery_windows": [
        {
            "id": "c1a2b3c4",
            "name": "Lunch Window",
            "start_time": "12:00:00",
            "end_time": "14:00:00",
            "is_active": true
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows, operating_hour_overrides, operating_hours`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/delivery-zones`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/orders.py` (`list_delivery_zones`)

**Summary:** List delivery zones with fees and estimated delivery times.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "zones": [
        {
            "id": "z1a2b3",
            "name": "Main Campus North",
            "delivery_fee": 200.0,
            "is_active": true
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_zones`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/scheduled`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`list_scheduled_orders`)

**Summary:** List the authenticated user's upcoming scheduled orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "orders": [
        {
            "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "order_number": "HG-9A8B7C6D5E",
            "status": "delivered",
            "payment_status": "paid",
            "total_amount": 3200.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/validate-promo`

**Authentication:** Optional JWT (Authenticated or Guest checkout context)

**Source File:** `app/routes/orders.py` (`validate_promo`)

**Summary:** Validate a promo code against an order subtotal without applying it.


**Request Specification:**

```json
{
    "code": "any // OPTIONAL \u2014 default: null",
    "order_subtotal": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "valid": true,
    "promo_code_id": "p1a2b3",
    "discount_amount": 300.0,
    "message": "Promo code SAVE10 applied successfully"
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/push/subscribe`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`push_unsubscribe`)

**Summary:** Deactivate all Web Push subscriptions for the authenticated user (or one endpoint).


**Request Specification:**

```json
{
    "endpoint": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `push_subscriptions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/push/subscribe`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`push_subscribe`)

**Summary:** Register a browser Web Push subscription for the authenticated user.


**Request Specification:**

```json
{
    "device_label": "any // OPTIONAL \u2014 default: null",
    "subscription": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `push_subscriptions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/referrals`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/referrals.py` (`my_referrals`)

**Summary:** Get authenticated user's referral stats and list.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, referrals`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/referrals/complete`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/referrals.py` (`complete_referral`)

**Summary:** Internal endpoint called when a referred user completes their first order.


**Request Specification:**

```json
{
    "order_id": "any // OPTIONAL \u2014 default: null",
    "referred_user_id": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `referrals`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/referrals/stats`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/referrals.py` (`referral_stats`)

**Summary:** Get a lightweight summary of the authenticated user's referral performance


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, referrals`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/rewards`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/rewards.py` (`list_rewards`)

**Summary:** List active rewards. Optionally filter by category.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `category, reward_type`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/rewards`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`create_reward`)

**Summary:** Create a new reward (admin only).


**Request Specification:**

```json
{
    "campus_id": "any // OPTIONAL \u2014 default: null",
    "is_active": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "reward_type": "any // OPTIONAL \u2014 default: null",
    "stock_quantity": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, rewards`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/rewards/<reward_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`delete_reward`)

**Summary:** Deactivate (soft-delete) a reward (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/rewards/<reward_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/rewards.py` (`get_reward`)

**Summary:** Get reward detail.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/rewards/<reward_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`update_reward`)

**Summary:** Update a reward (admin only).


**Request Specification:**

```json
{
    "updated_at": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/rewards/<reward_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`update_reward_image`)

**Summary:** Update reward image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Error Responses & Recovery Instructions:**

- `"image_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/rewards/<reward_id>/redeem`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/rewards.py` (`redeem_reward`)

**Summary:** Redeem a reward using HP via atomic hg_redeem_reward RPC.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers, rewards`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/rewards/admin/redemptions`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`admin_list_redemptions`)

**Summary:** List all reward redemptions across all users (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, offset, reward_id, status`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `reward_redemptions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/rewards/admin/redemptions/<redemption_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`admin_update_redemption`)

**Summary:** Fulfil or reject a reward redemption (admin only).


**Request Specification:**

```json
{
    "fulfilled_at": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `reward_redemptions, rewards`


**Error Responses & Recovery Instructions:**

- `"Cannot reject an already-fulfilled redemption"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/rewards/redemptions`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/rewards.py` (`my_redemptions`)

**Summary:** Get authenticated user's reward redemption history.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `reward_redemptions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/riders/availability`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`toggle_availability`)

**Summary:** Toggle rider online/offline availability status.


**Request Specification:**

```json
{
    "is_available": "any // OPTIONAL \u2014 default: null",
    "location_lat": "any // OPTIONAL \u2014 default: null",
    "location_lng": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rider_profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/call/<order_id>`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`get_customer_call_link`)

**Summary:** Get a click-to-call link for the customer.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/earnings`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`rider_earnings`)

**Summary:** Get the authenticated rider's earnings summary for a period.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `period`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/history`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`delivery_history`)

**Summary:** Get the authenticated rider's completed delivery history.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "history": [
        {
            "status": "received",
            "created_at": "2026-03-31T12:00:00Z",
            "changed_by": "customer"
        },
        {
            "status": "preparing",
            "created_at": "2026-03-31T12:05:00Z",
            "changed_by": "kitchen"
        },
        {
            "status": "delivered",
            "created_at": "2026-03-31T12:25:00Z",
            "changed_by": "rider"
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/my-batch`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`my_batch`)

**Summary:** Get the current delivery batch assigned to this rider.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, sequencing`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, delivery_windows, gates, order_items, orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/riders/orders/<order_id>/attempt`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`mark_attempted`)

**Summary:** Mark a delivery as attempted (customer unreachable).


**Request Specification:**

```json
{
    "notes": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/riders/orders/<order_id>/deliver`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`mark_delivered`)

**Summary:** Mark an order as delivered.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/riders/orders/<order_id>/pickup`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`mark_picked_up`)

**Summary:** Confirm order pickup from kitchen. Transitions order from 'assigned' → 'out_for_delivery'.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "order_number": "HG-9A8B7C6D5E",
    "status": "received",
    "payment_status": "paid",
    "subtotal": 3000.0,
    "delivery_fee": 200.0,
    "discount_amount": 0.0,
    "total_amount": 3200.0,
    "hp_earned": 360,
    "items": [
        {
            "menu_item_id": "8a2c1b",
            "quantity": 2,
            "unit_price": 1500.0
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/stats`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`rider_stats`)

**Summary:** Get performance statistics for the authenticated rider.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders, rider_profiles`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/saved`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`list_saved`)

**Summary:** Get all items the authenticated user has saved for later.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `saved_for_later`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/saved`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`save_item`)

**Summary:** Save a menu item for later. If already saved, updates quantity.


**Request Specification:**

```json
{
    "menu_item_id": "any // OPTIONAL \u2014 default: null",
    "notes": "any // OPTIONAL \u2014 default: null",
    "quantity": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items, saved_for_later`


**Error Responses & Recovery Instructions:**

- `"quantity must be a valid integer"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/saved/<item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`remove_saved_item`)

**Summary:** Remove a saved-for-later item.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `saved_for_later`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/saved/<item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`update_saved_item`)

**Summary:** Update quantity or notes on a saved-for-later item.


**Request Specification:**

```json
{
    "notes": "any // OPTIONAL \u2014 default: null",
    "quantity": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `saved_for_later`


**Error Responses & Recovery Instructions:**

- `"quantity must be a valid integer"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/saved/<item_id>/move-to-cart`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`move_saved_to_cart`)

**Summary:** Move a saved-for-later item into the active cart.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items, saved_for_later`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/saved/from-cart/<cart_item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`move_cart_to_saved`)

**Summary:** Move an active cart item to the saved-for-later list.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items, saved_for_later`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/storefront/banners`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`list_banners`)

**Summary:** Get active promotional banners for the storefront homepage.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `placement`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/banners`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`create_banner`)

**Summary:** Create a new promotional banner (admin only).


**Request Specification:**

```json
{
    "images": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Error Responses & Recovery Instructions:**

- `"'images' must be a non-empty list of URL strings"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/storefront/banners/<banner_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`delete_banner`)

**Summary:** Delete a banner (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Error Responses & Recovery Instructions:**

- `"Banner not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/storefront/banners/<banner_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_banner`)

**Summary:** Update a banner (admin only). Pass `images` array to enable/update carousel slides.


**Request Specification:**

```json
{
    "images": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Error Responses & Recovery Instructions:**

- `"'images' must be a non-empty list of URL strings"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Banner not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/storefront/banners/<banner_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_banner_image`)

**Summary:** Update banner image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any // OPTIONAL \u2014 default: null",
    "mobile_image_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Error Responses & Recovery Instructions:**

- `"Banner not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"image_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/storefront/config/public`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`get_public_config`)

**Summary:** Get public system settings and configs (e.g. WhatsApp, etc).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `system_settings`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/storefront/early-supporters`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`list_early_supporters`)

**Summary:** Get the public-facing Early Supporters list.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/early-supporters`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`create_early_supporter`)

**Summary:** Add a new Early Supporter entry (admin only).


**Request Specification:**

```json
{
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "note": "any // OPTIONAL \u2014 default: null",
    "photo_url": "any // OPTIONAL \u2014 default: null",
    "social_links": "any // OPTIONAL \u2014 default: null",
    "sort_order": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- `"'name' is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `DELETE /api/storefront/early-supporters/<section_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`delete_early_supporter`)

**Summary:** Deactivate an Early Supporter entry (admin only — soft delete).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- `"Early supporter not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `PATCH /api/storefront/early-supporters/<section_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_early_supporter`)

**Summary:** Update an Early Supporter entry (admin only).


**Request Specification:**

```json
{
    "is_active": "any // OPTIONAL \u2014 default: null",
    "name": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "sort_order": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- `"Early supporter not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/storefront/early-supporters/<section_id>/photo`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_early_supporter_photo`)

**Summary:** Update early supporter photo with Cloudinary URL.


**Request Specification:**

```json
{
    "photo_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- `"Early supporter not found"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"photo_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/storefront/newsletter`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`newsletter_list`)

**Summary:** List newsletter subscribers (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `active_only, limit, offset`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `newsletter_subscriptions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/newsletter`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`newsletter_subscribe`)

**Summary:** Subscribe an email address to the Holy Grills newsletter.


**Request Specification:**

```json
{
    "email": "any // REQUIRED \u2014 validation: must be provided and non-empty",
    "full_name": "any // OPTIONAL \u2014 default: null",
    "source": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `newsletter_subscriptions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/newsletter/unsubscribe`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`newsletter_unsubscribe`)

**Summary:** Unsubscribe an email address from the newsletter.


**Request Specification:**

```json
{
    "email": "any // REQUIRED \u2014 validation: must be provided and non-empty"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `newsletter_subscriptions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/storefront/operating-hours`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`get_hours`)

**Summary:** Get current operating hours schedule and any today-specific override.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `operating_hour_overrides, operating_hours`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/storefront/operating-hours`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_hours`)

**Summary:** Update operating hours for a day (admin only).


**Request Specification:**

```json
{
    "day": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `operating_hours`


**Error Responses & Recovery Instructions:**

- `"At least one of open_time, close_time, is_closed is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"No operating-hours row exists for this campus/weekday yet"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/storefront/operating-hours/override`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`set_override`)

**Summary:** Set a date-specific operating hours override (e.g., public holiday closure).


**Request Specification:**

```json
{
    "date": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `operating_hour_overrides`


**Error Responses & Recovery Instructions:**

- `"date (or override_date) is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/storefront/promo-codes/validate`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`validate_promo`)

**Summary:** [DEPRECATED] Validate a promo code — use POST /orders/validate-promo instead.


**Request Specification:**

```json
{
    "code": "any // OPTIONAL \u2014 default: null",
    "order_subtotal": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "valid": true,
    "promo_code_id": "p1a2b3",
    "discount_amount": 300.0,
    "message": "Promo code SAVE10 applied successfully"
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_codes`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/storefront/sections`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`list_sections`)

**Summary:** Get active storefront CMS sections (homepage, banners, etc).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/sections`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`create_section`)

**Summary:** Create a new CMS homepage section (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/storefront/sections/<section_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`delete_section`)

**Summary:** Deactivate (soft-delete) a CMS homepage section (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/storefront/sections/<section_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_section`)

**Summary:** Update a storefront section (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/sections/<section_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_section_image`)

**Summary:** Update storefront section image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Error Responses & Recovery Instructions:**

- `"image_url is required"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/upload/signature`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/uploads.py` (`upload_signature`)

**Summary:** Generate a short-lived Cloudinary signature for a direct client upload.


**Request Specification:**

```json
{
    "folder": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- `"Cloudinary upload is not configured"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Invalid upload folder"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/wallet`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/wallet.py` (`get_balance`)

**Summary:** Get wallet balance and virtual account info.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `virtual_accounts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/wallet/admin/transactions`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/wallet.py` (`admin_wallet_transactions`)

**Summary:** List wallet transactions (admin only). Scoped to caller campus_id unless super_admin.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date, type, user_id`


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `wallet_transactions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/wallet/fund/bank`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/wallet.py` (`request_virtual_account`)

**Summary:** Provision a Paystack Dedicated Virtual Account for bank transfers.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Response):**

```json
{
    "account_number": "1234567890",
    "bank_name": "Wema Bank",
    "account_name": "HolyGrills - John Doe",
    "reference": "HG-VA-102938"
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, virtual_accounts`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/wallet/fund/card`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/wallet.py` (`fund_via_card`)

**Summary:** Initialize a card payment to top up wallet.


**Request Specification:**

```json
{
    "amount": "any // OPTIONAL \u2014 default: null",
    "callback_url": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "authorization_url": "https://checkout.paystack.com/30092831",
    "reference": "HG-WAL-172839210-9A8B",
    "status": "pending"
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Error Responses & Recovery Instructions:**

- `"Card payments are not configured on this server."` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.
- `"Payment gateway unavailable. Please try again later."` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `GET /api/wallet/transactions`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/wallet.py` (`wallet_transactions`)

**Summary:** Get wallet transaction history. Filter by type: topup, order_payment, refund, withdrawal, bank_transfer.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `type`


**Response Specification (200 OK Response):**

```json
{
    "transactions": [
        {
            "id": "t1",
            "amount": 2000.0,
            "type": "credit",
            "source": "paystack_card",
            "created_at": "2026-03-31T12:00:00Z"
        }
    ]
}
```


**Database & Service Interactions:**

- **Database Tables:** `wallet_transactions`


**Error Responses & Recovery Instructions:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/webhooks/flutterwave`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/webhooks.py` (`flutterwave_webhook`)

**Summary:** Flutterwave webhook handler.


**Request Specification:**

```json
{
    "flw_ref": "any // OPTIONAL \u2014 default: null",
    "id": "any // OPTIONAL \u2014 default: null",
    "status": "any // OPTIONAL \u2014 default: null",
    "tx_ref": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- `"Webhook processing failed"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

### `POST /api/webhooks/paystack`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/webhooks.py` (`paystack_webhook`)

**Summary:** Paystack webhook handler.


**Request Specification:**

```json
{
    "id": "any // OPTIONAL \u2014 default: null",
    "reference": "any // OPTIONAL \u2014 default: null",
    "transfer_code": "any // OPTIONAL \u2014 default: null"
}
```


**Response Specification (200 OK Response):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Error Responses & Recovery Instructions:**

- `"Webhook processing failed"` → **User Action**: Show alert to user; **Retry Allowed**: Yes; **Recovery Flow**: Prompt user for input correction or retry request.

---

## SECTION 4: AUTHENTICATION & AUTHORIZATION

### JWT Authentication Flow

1. **Token Issuance**: Supabase Auth issues access tokens (`JWT`) signed with `JWT_SECRET` upon login (`POST /api/auth/login`) or registration (`POST /api/auth/register`).

2. **Token Verification**: `@require_auth` and `@require_role` middleware extract Bearer tokens from HTTP `Authorization` header (`Authorization: Bearer <access_token>`). Tokens are validated via `db.auth_get_user(token)` REST call to Supabase.

3. **Silent Token Rotation**: Clients receive token expiration claims. When tokens are within `JWT_REFRESH_WINDOW_MINUTES` (default 5 minutes), client applications issue `POST /api/auth/refresh` to obtain new active JWTs without interrupting user session.

4. **Guest Flow**: Endpoints decorated with `@optional_auth` allow unauthenticated requests (with `g.user_id = None`), but if a Bearer token is provided, it MUST be valid.


### Role Definitions & Hierarchy

| Role | Access Level | Description |

|------|--------------|-------------|

| `student` | Standard User | Can place orders, manage wallet, redeem HP, view marketplace & events |

| `kitchen` | Operations | Kitchen staff; can view and update order preparation statuses |

| `rider` | Delivery | Delivery riders; can accept batches, update delivery statuses, call customers |

| `admin` | Campus Admin | Full admin capabilities scoped to their assigned `campus_id` |

| `super_admin` | Global Admin | Unrestricted access across all campuses, system settings, and administrative routes |


### Campus Scoping Helpers

- `resolve_scoped_campus_id(requested_campus_id)`: For `super_admin`, returns requested campus ID or `None` (all campuses). For non-super_admin users, strictly returns `g.campus_id`.

- `assert_owns_campus(record_campus_id)`: Aborts with HTTP 403 Forbidden if a non-super_admin user attempts to mutate/access data belonging to a different campus.


## SECTION 5: DATABASE SCHEMA & COLUMN MEANINGS

Total public schema tables documented: **99**


### Table: `public.abandoned_carts`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `recovered_order_id` → `orders.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the abandoned_carts record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | YES | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `guest_email` | `citext` | YES | `NULL` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `guest_phone` | `text` | YES | `NULL` | Contact phone number used for delivery alerts. | API Request / Profile | upon record creation | NULL if phone number not provided | None |
| `cart_payload` | `jsonb` | NO | `NULL` | Data field storing cart payload for abandoned_carts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `last_recovery_sent_at` | `timestamp with time zone` | YES | `NULL` | Data field storing last recovery sent at for abandoned_carts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `next_recovery_at` | `timestamp with time zone` | YES | `NULL` | Data field storing next recovery at for abandoned_carts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `recovery_attempts` | `integer` | NO | `0` | Data field storing recovery attempts for abandoned_carts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_recovered` | `boolean` | NO | `false` | Data field storing is recovered for abandoned_carts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `recovered_order_id` | `uuid` | YES | `NULL` | Data field storing recovered order id for abandoned_carts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `last_active_at` | `timestamp with time zone` | NO | `now()` | Data field storing last active at for abandoned_carts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_abandoned_carts_next_recovery_at` ON (`next_recovery_at`)
- `idx_abandoned_carts_recovered_order_id` ON (`recovered_order_id`)
- `idx_abandoned_carts_recovery_full` ON (`is_recovered,
next_recovery_at, last_active_at`)
- `idx_abandoned_carts_user` ON (`user_id`)

**RLS Policies:**
- `abandoned_carts: admins all`
- `abandoned_carts: users manage own`

---

### Table: `public.academic_levels`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the academic_levels record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for academic_levels record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `value` | `text` | NO | `NULL` | Data field storing value for academic_levels record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for academic_levels record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for academic_levels record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Unique Constraints:**
- `academic_levels_value_key`: UNIQUE (`value`)

---

### Table: `public.admin_audit_logs`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `actor_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the admin_audit_logs record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `action` | `text` | NO | `NULL` | Data field storing action for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `entity_type` | `text` | NO | `NULL` | Data field storing entity type for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `entity_id` | `text` | YES | `NULL` | Data field storing entity id for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `actor_id` | `uuid` | YES | `NULL` | Data field storing actor id for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `actor_role` | `text` | YES | `NULL` | Data field storing actor role for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ip_address` | `inet` | YES | `NULL` | Data field storing ip address for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_agent` | `text` | YES | `NULL` | Data field storing user agent for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `before_value` | `jsonb` | YES | `NULL` | Data field storing before value for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `after_value` | `jsonb` | YES | `NULL` | Data field storing after value for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `session_id` | `text` | YES | `NULL` | Data field storing session id for admin_audit_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_admin_audit_logs_actor_id` ON (`actor_id`)

**RLS Policies:**
- `admin_audit_logs: admins all`
- `admin_audit_logs: admins read`

---

### Table: `public.banners`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `created_by` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `uuid_generate_v4()` | Primary key UUID unique identifier for the banners record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `title` | `text` | NO | `NULL` | Data field storing title for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `subtitle` | `text` | YES | `NULL` | Data field storing subtitle for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `image_url` | `text` | YES | `NULL` | Data field storing image url for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `mobile_image_url` | `text` | YES | `NULL` | Data field storing mobile image url for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `action_url` | `text` | YES | `NULL` | Data field storing action url for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `action_label` | `text` | YES | `NULL` | Data field storing action label for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `placement` | `text` | NO | `'home'::text` | Data field storing placement for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `starts_at` | `timestamp with time zone` | YES | `NULL` | Data field storing starts at for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ends_at` | `timestamp with time zone` | YES | `NULL` | Data field storing ends at for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `target_roles` | `text[]` | NO | `'{}'::text[]` | Data field storing target roles for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_by` | `uuid` | YES | `NULL` | Data field storing created by for banners record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_banners_active_placement` ON (`placement, sort_order`)
- `idx_banners_created_by` ON (`created_by`)

**RLS Policies:**
- `banners: admins all`
- `banners: public read active`

---

### Table: `public.batch_orders`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `added_by` → `profiles.id`, `batch_id` → `delivery_batches.id`, `order_id` → `orders.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the batch_orders record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `batch_id` | `uuid` | NO | `NULL` | Data field storing batch id for batch_orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `order_id` | `uuid` | NO | `NULL` | Data field storing order id for batch_orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sequence` | `integer` | YES | `NULL` | Data field storing sequence for batch_orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `added_by` | `uuid` | YES | `NULL` | Data field storing added by for batch_orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_batch_orders_added_by` ON (`added_by`)
- `idx_batch_orders_batch` ON (`batch_id`)

**Unique Constraints:**
- `batch_orders_batch_id_order_id_key`: UNIQUE (`batch_id, order_id`)
- `batch_orders_order_id_key`: UNIQUE (`order_id`)

---

### Table: `public.campuses`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the campuses record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for campuses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `slug` | `text` | NO | `NULL` | Data field storing slug for campuses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for campuses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Unique Constraints:**
- `campuses_name_key`: UNIQUE (`name`)
- `campuses_slug_key`: UNIQUE (`slug`)

**RLS Policies:**
- `Allow select for everyone`

---

### Table: `public.cart_items`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `menu_item_id` → `menu_items.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `uuid_generate_v4()` | Primary key UUID unique identifier for the cart_items record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `menu_item_id` | `uuid` | NO | `NULL` | Data field storing menu item id for cart_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `quantity` | `integer` | NO | `1` | Data field storing quantity for cart_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `options` | `jsonb` | NO | `'{}'::jsonb` | Data field storing options for cart_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `added_at` | `timestamp with time zone` | NO | `now()` | Data field storing added at for cart_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_cart_items_menu_item_id` ON (`menu_item_id`)

**Unique Constraints:**
- `uq_cart_items_user_menu_item`: UNIQUE (`user_id, menu_item_id`)

**Check Constraints:**
- `cart_items_quantity_check`: `(quantity > 0)`

**RLS Policies:**
- `cart_items: users manage own`

---

### Table: `public.catering_requests`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `assigned_to` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the catering_requests record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `organizer_name` | `text` | NO | `NULL` | Data field storing organizer name for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `email` | `citext` | NO | `NULL` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `phone` | `text` | NO | `NULL` | Contact phone number used for delivery alerts. | API Request / Profile | upon record creation | NULL if phone number not provided | None |
| `organization` | `text` | YES | `NULL` | Data field storing organization for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `event_name` | `text` | NO | `NULL` | Data field storing event name for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `event_date` | `date` | NO | `NULL` | Data field storing event date for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `expected_guests` | `integer` | NO | `NULL` | Data field storing expected guests for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `budget` | `numeric(14,2)` | YES | `NULL` | Data field storing budget for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `notes` | `text` | YES | `NULL` | Data field storing notes for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'new'::text` | Data field storing status for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `assigned_to` | `uuid` | YES | `NULL` | Data field storing assigned to for catering_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `quoted_amount` | `numeric(14,2)` | YES | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `hp_promo_optin` | `boolean` | NO | `false` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |

**Indexes:**
- `idx_catering_requests_assigned_to` ON (`assigned_to`)

**Check Constraints:**
- `catering_requests_status_check`: `(status = ANY (ARRAY['new'::text, 'contacted'::text, 'quoted'::text, 'confirmed'::text, 'in_progress'::text, 'completed'::text, 'cancelled'::text, 'rejected'::text]))`
- `chk_catering_guests_pos`: `(expected_guests > 0)`

**RLS Policies:**
- `catering_requests: admins all`
- `catering_requests: public insert`

---

### Table: `public.challenge_completions`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the challenge_completions record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `challenge_id` | `uuid` | NO | `NULL` | Data field storing challenge id for challenge_completions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `hp_transaction_id` | `uuid` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `completed_at` | `timestamp with time zone` | NO | `now()` | Data field storing completed at for challenge_completions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |

**Indexes:**
- `idx_challenge_completions_challenge` ON (`challenge_id`)
- `idx_challenge_completions_hp_tx_id` ON (`hp_transaction_id`)
- `idx_challenge_completions_user` ON (`user_id`)

**RLS Policies:**
- `challenge_completions: admins all`
- `challenge_completions: users read
own`

---

### Table: `public.challenges`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `created_by` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the challenges record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_reward` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `criteria` | `jsonb` | NO | `NULL` | Data field storing criteria for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `starts_at` | `timestamp with time zone` | YES | `NULL` | Data field storing starts at for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ends_at` | `timestamp with time zone` | YES | `NULL` | Data field storing ends at for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `max_completions_per_user` | `integer` | NO | `1` | Data field storing max completions per user for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `type` | `text` | NO | `'one_time'::text` | Data field storing type for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `target_count` | `integer` | NO | `1` | Data field storing target count for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_by` | `uuid` | YES | `NULL` | Data field storing created by for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `title` | `text` | YES | `NULL` | Data field storing title for challenges record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | YES | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_challenges_active` ON (`starts_at, ends_at`)
- `idx_challenges_created_by` ON (`created_by`)

**Check Constraints:**
- `challenges_type_check`: `(type = ANY (ARRAY['one_time'::text, 'recurring'::text, 'daily'::text, 'weekly'::text, 'monthly'::text, 'event'::text]))`
- `chk_challenges_hp_reward_pos`: `(hp_reward > 0)`

**RLS Policies:**
- `challenges: admins all`
- `challenges: public read active`

---

### Table: `public.cron_locks`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `job_name`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `job_name` | `text` | NO | `NULL` | Data field storing job name for cron_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `locked_at` | `timestamp with time zone` | NO | `now()` | Data field storing locked at for cron_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**RLS Policies:**
- `Admins manage cron_locks`

---

### Table: `public.daily_checkins`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the daily_checkins record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `checkin_date` | `date` | NO | `NULL` | Data field storing checkin date for daily_checkins record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_daily_checkins_date` ON (`checkin_date`)
- `idx_daily_checkins_user_id` ON (`user_id`)

---

### Table: `public.delivery_assignments`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the delivery_assignments record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `order_id` | `uuid` | NO | `NULL` | Data field storing order id for delivery_assignments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `rider_id` | `uuid` | NO | `NULL` | Data field storing rider id for delivery_assignments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `batch_id` | `uuid` | YES | `NULL` | Data field storing batch id for delivery_assignments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'assigned'::text` | Data field storing status for delivery_assignments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `note` | `text` | YES | `NULL` | Data field storing note for delivery_assignments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `completed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing completed at for delivery_assignments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_delivery_assignments_batch_id` ON (`batch_id`)
- `idx_delivery_assignments_rider` ON (`rider_id`)

**RLS Policies:**
- `delivery_assignments: admins all`
- `delivery_assignments: riders read`

---

### Table: `public.delivery_batches`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `delivery_window_id` → `delivery_windows.id`, `rider_id` → `profiles.id`, `window_id` → `delivery_windows.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the delivery_batches record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `rider_id` | `uuid` | YES | `NULL` | Data field storing rider id for delivery_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'open'::text` | Data field storing status for delivery_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `notes` | `text` | YES | `NULL` | Data field storing notes for delivery_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `completed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing completed at for delivery_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `zone` | `text` | YES | `NULL` | Data field storing zone for delivery_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_window_id` | `uuid` | YES | `NULL` | Data field storing delivery window id for delivery_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `window_id` | `uuid` | YES | `NULL` | Data field storing window id for delivery_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_delivery_batches_delivery_window` ON (`delivery_window_id`)
- `idx_delivery_batches_rider` ON (`rider_id`)
- `idx_delivery_batches_rider_status` ON (`rider_id,
status`)
- `idx_delivery_batches_status` ON (`status`)
- `idx_delivery_batches_window_id` ON (`window_id`)
- `idx_delivery_batches_window_zone` ON (`delivery_window_id, zone`)

**Check Constraints:**
- `delivery_batches_status_check`: `(status = ANY (ARRAY['open'::text, 'assigned'::text, 'in_progress'::text, 'completed'::text, 'cancelled'::text]))`

**RLS Policies:**
- `delivery_batches: admins all`
- `delivery_batches: riders read`

---

### Table: `public.delivery_windows`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `created_by` → `profiles.id`, `zone_id` → `delivery_zones.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the delivery_windows record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `label` | `text` | NO | `NULL` | Data field storing label for delivery_windows record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `starts_at` | `timestamp with time zone` | NO | `NULL` | Data field storing starts at for delivery_windows record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ends_at` | `timestamp with time zone` | NO | `NULL` | Data field storing ends at for delivery_windows record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `capacity` | `integer` | YES | `NULL` | Data field storing capacity for delivery_windows record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for delivery_windows record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `zone_id` | `uuid` | YES | `NULL` | Data field storing zone id for delivery_windows record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'open'::text` | Data field storing status for delivery_windows record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_by` | `uuid` | YES | `NULL` | Data field storing created by for delivery_windows record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_delivery_windows_active` ON (`starts_at,
ends_at`)
- `idx_delivery_windows_created_by` ON (`created_by`)
- `idx_delivery_windows_zone_id` ON (`zone_id`)

**Check Constraints:**
- `chk_delivery_windows_capacity_pos`: `(capacity > 0)`
- `chk_delivery_windows_dates`: `(ends_at > starts_at)`
- `delivery_windows_status_check`: `(status = ANY (ARRAY['open'::text, 'full'::text, 'closed'::text, 'cancelled'::text, 'locked'::text]))`

**RLS Policies:**
- `delivery_windows: admins all`
- `delivery_windows: public read
active`

---

### Table: `public.delivery_zones`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `uuid_generate_v4()` | Primary key UUID unique identifier for the delivery_zones record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for delivery_zones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for delivery_zones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_fee` | `numeric(10,2)` | NO | `0` | Data field storing delivery fee for delivery_zones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `min_order` | `numeric(10,2)` | NO | `0` | Data field storing min order for delivery_zones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for delivery_zones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `polygon` | `jsonb` | YES | `NULL` | Data field storing polygon for delivery_zones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Check Constraints:**
- `delivery_zones_delivery_fee_check`: `(delivery_fee >= (0)::numeric)`
- `delivery_zones_min_order_check`: `(min_order >= (0)::numeric)`

**RLS Policies:**
- `delivery_zones: admins all`
- `delivery_zones: public read active`

---

### Table: `public.departments`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the departments record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for departments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `slug` | `text` | NO | `NULL` | Data field storing slug for departments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `faculty` | `text` | NO | `NULL` | Data field storing faculty for departments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for departments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for departments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_departments_faculty` ON (`faculty`)
- `idx_departments_is_active` ON (`is_active`)
- `idx_departments_slug` ON (`slug`)
- `idx_departments_sort_order` ON (`sort_order`)

**Unique Constraints:**
- `departments_slug_key`: UNIQUE (`slug`)

---

### Table: `public.device_fingerprints`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the device_fingerprints record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `fingerprint` | `text` | NO | `NULL` | Data field storing fingerprint for device_fingerprints record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `platform` | `text` | NO | `'unknown'::text` | Data field storing platform for device_fingerprints record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_device_fingerprints_fingerprint` ON (`fingerprint`)
- `idx_device_fingerprints_user` ON (`user_id`)

**RLS Policies:**
- `Admins manage device fingerprints`

---

### Table: `public.device_tokens`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the device_tokens record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `token` | `text` | NO | `NULL` | Data field storing token for device_tokens record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `platform` | `text` | NO | `'unknown'::text` | Data field storing platform for device_tokens record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `device_model` | `text` | YES | `NULL` | Data field storing device model for device_tokens record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Unique Constraints:**
- `device_tokens_user_id_token_key`: UNIQUE (`user_id, token`)

**RLS Policies:**
- `Users manage own device tokens`

---

### Table: `public.event_checkins`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `checked_in_by` → `profiles.id`, `hp_transaction_id` → `hp_transactions.id`, `ticket_id` → `event_tickets.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the event_checkins record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `ticket_id` | `uuid` | NO | `NULL` | Data field storing ticket id for event_checkins record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `qr_code` | `text` | NO | `NULL` | Data field storing qr code for event_checkins record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `checked_in_by` | `uuid` | YES | `NULL` | Data field storing checked in by for event_checkins record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_transaction_id` | `uuid` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_event_checkins_checked_in_by` ON (`checked_in_by`)
- `idx_event_checkins_hp_tx_id` ON (`hp_transaction_id`)
- `idx_event_checkins_ticket_created` ON (`ticket_id,
created_at`)

**Unique Constraints:**
- `event_checkins_ticket_id_key`: UNIQUE (`ticket_id`)

**RLS Policies:**
- `event_checkins: admins all`

---

### Table: `public.event_ticket_tiers`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the event_ticket_tiers record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `event_id` | `uuid` | NO | `NULL` | Data field storing event id for event_ticket_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `name` | `text` | NO | `NULL` | Data field storing name for event_ticket_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `price_naira` | `numeric(12,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `price_hp` | `integer` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `capacity` | `integer` | YES | `NULL` | Data field storing capacity for event_ticket_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sold_count` | `integer` | NO | `0` | Data field storing sold count for event_ticket_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for event_ticket_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for event_ticket_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for event_ticket_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_event_ticket_tiers_event_id` ON (`event_id`)

---

### Table: `public.event_tickets`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `event_id` → `events.id`, `tier_id` → `event_ticket_tiers.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the event_tickets record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `event_id` | `uuid` | NO | `NULL` | Data field storing event id for event_tickets record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `quantity` | `integer` | NO | `1` | Data field storing quantity for event_tickets record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for event_tickets record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `qr_code` | `text` | YES | `encode(gen_random_bytes(24), 'hex'::text)` | Data field storing qr code for event_tickets record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `qr_expires_at` | `timestamp with time zone` | YES | `NULL` | Data field storing qr expires at for event_tickets record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `tier_id` | `uuid` | YES | `NULL` | Data field storing tier id for event_tickets record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_event_tickets_event` ON (`event_id`)
- `idx_event_tickets_tier_id` ON (`tier_id`)
- `idx_event_tickets_user` ON (`user_id`)
- `uq_event_tickets_active_user_event` ON (`event_id,
user_id`)

**Unique Constraints:**
- `event_tickets_qr_code_key`: UNIQUE (`qr_code`)

**RLS Policies:**
- `event_tickets: admins all`
- `event_tickets: users read own`

---

### Table: `public.events`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `organizer_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the events record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `title` | `text` | NO | `NULL` | Data field storing title for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `slug` | `text` | NO | `NULL` | Data field storing slug for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `starts_at` | `timestamp with time zone` | NO | `NULL` | Data field storing starts at for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ends_at` | `timestamp with time zone` | NO | `NULL` | Data field storing ends at for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `location` | `text` | NO | `NULL` | Data field storing location for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `image_url` | `text` | YES | `NULL` | Data field storing image url for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ticket_price` | `numeric(14,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `hp_reward` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `capacity` | `integer` | YES | `NULL` | Data field storing capacity for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_published` | `boolean` | NO | `false` | Data field storing is published for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `hp_promo_enabled` | `boolean` | NO | `false` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `is_featured` | `boolean` | NO | `false` | Data field storing is featured for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `organizer_id` | `uuid` | YES | `NULL` | Data field storing organizer id for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | YES | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `hp_per_attendee` | `integer` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `funding_source` | `text` | YES | `NULL` | Data field storing funding source for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `max_attendees` | `integer` | YES | `NULL` | Data field storing max attendees for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_required` | `integer` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `total_value` | `numeric(10,2)` | YES | `NULL::numeric` | Data field storing total value for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_paid` | `boolean` | NO | `false` | Data field storing is paid for events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_events_featured` ON (`is_featured`)
- `idx_events_organizer_id` ON (`organizer_id`)
- `idx_events_published` ON (`starts_at`)

**Unique Constraints:**
- `events_slug_key`: UNIQUE (`slug`)

**Check Constraints:**
- `events_funding_source_check`: `(funding_source = ANY (ARRAY['host_prepaid'::text, 'hg_funded'::text, NULL::text]))`

**RLS Policies:**
- `events: admins all`
- `events: public read published`

---

### Table: `public.exclusive_spins`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the exclusive_spins record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `spin_count` | `integer` | NO | `0` | Data field storing spin count for exclusive_spins record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `source` | `text` | NO | `NULL` | Data field storing source for exclusive_spins record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `month` | `text` | YES | `NULL` | Data field storing month for exclusive_spins record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `expires_at` | `timestamp with time zone` | NO | `NULL` | Data field storing expires at for exclusive_spins record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_exclusive_spins_active` ON (`user_id,
expires_at`)
- `idx_exclusive_spins_expires_at` ON (`expires_at`)
- `idx_exclusive_spins_user_id` ON (`user_id`)

**Check Constraints:**
- `exclusive_spins_spin_count_check`: `(spin_count >= 0)`

**RLS Policies:**
- `Allow authenticated users to read
their own exclusive spins`

---

### Table: `public.feature_flags`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `feature_name`

- **Foreign Keys:** `updated_by` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `feature_name` | `text` | NO | `NULL` | Data field storing feature name for feature_flags record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for feature_flags record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for feature_flags record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_by` | `uuid` | YES | `NULL` | Data field storing updated by for feature_flags record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_feature_flags_updated_by` ON (`updated_by`)

---

### Table: `public.first_order_gifts`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `order_id` → `orders.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the first_order_gifts record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `order_id` | `uuid` | YES | `NULL` | Data field storing order id for first_order_gifts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for first_order_gifts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `claimed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing claimed at for first_order_gifts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_first_order_gifts_order_id` ON (`order_id`)
- `idx_first_order_gifts_status` ON (`status`)

**Unique Constraints:**
- `first_order_gifts_user_id_key`: UNIQUE (`user_id`)

**Check Constraints:**
- `first_order_gifts_status_check`: `(status = ANY (ARRAY['pending'::text, 'fulfilled'::text, 'cancelled'::text]))`

**RLS Policies:**
- `Admins manage first_order_gifts`
- `Users view own gift`

---

### Table: `public.flash_redemptions`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `reward_id` → `rewards.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the flash_redemptions record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `reward_id` | `uuid` | NO | `NULL` | Data field storing reward id for flash_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `window_starts_at` | `timestamp with time zone` | NO | `NULL` | Data field storing window starts at for flash_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `window_ends_at` | `timestamp with time zone` | NO | `NULL` | Data field storing window ends at for flash_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `quantity_limit` | `integer` | NO | `5` | Data field storing quantity limit for flash_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `discount_pct` | `numeric(5,2)` | NO | `0.50` | Data field storing discount pct for flash_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for flash_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `flash_redemptions_is_active_idx` ON (`is_active`)
- `flash_redemptions_reward_id_idx` ON (`reward_id`)

**RLS Policies:**
- `Admins manage flash_redemptions`
- `Anyone can view flash_redemptions`

---

### Table: `public.free_side_credits`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the free_side_credits record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `credits_remaining` | `integer` | NO | `0` | Data field storing credits remaining for free_side_credits record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `source` | `text` | NO | `NULL` | Data field storing source for free_side_credits record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `month` | `text` | YES | `NULL` | Data field storing month for free_side_credits record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `expires_at` | `timestamp with time zone` | NO | `NULL` | Data field storing expires at for free_side_credits record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `used_at` | `timestamp with time zone` | YES | `NULL` | Data field storing used at for free_side_credits record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_free_side_credits_active` ON (`user_id,
expires_at`)
- `idx_free_side_credits_expires_at` ON (`expires_at`)
- `idx_free_side_credits_user_id` ON (`user_id`)

**Check Constraints:**
- `free_side_credits_credits_remaining_check`: `(credits_remaining >= 0)`

---

### Table: `public.gates`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the gates record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for gates record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `lat` | `double precision` | YES | `NULL` | Data field storing lat for gates record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `lon` | `double precision` | YES | `NULL` | Data field storing lon for gates record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `base_fee` | `numeric(10,2)` | NO | `0` | Data field storing base fee for gates record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `rate_per_km` | `numeric(10,2)` | NO | `0` | Data field storing rate per km for gates record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `min_fee` | `numeric(10,2)` | NO | `0` | Data field storing min fee for gates record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for gates record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

---

### Table: `public.hall_of_fame_inductees`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the hall_of_fame_inductees record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `inducted_at` | `timestamp with time zone` | NO | `now()` | Data field storing inducted at for hall_of_fame_inductees record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `full_name` | `text` | NO | `NULL` | Data field storing full name for hall_of_fame_inductees record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `photo_url` | `text` | YES | `NULL` | Data field storing photo url for hall_of_fame_inductees record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `tier_at_induction` | `text` | YES | `NULL` | Data field storing tier at induction for hall_of_fame_inductees record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `top4_finish_count` | `integer` | NO | `4` | Data field storing top4 finish count for hall_of_fame_inductees record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**RLS Policies:**
- `Admins manage hall_of_fame`
- `Anyone reads hall_of_fame`

---

### Table: `public.hall_of_fame_rewards`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the hall_of_fame_rewards record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `inducted_at` | `timestamp with time zone` | NO | `now()` | Data field storing inducted at for hall_of_fame_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for hall_of_fame_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `notes` | `text` | YES | `NULL` | Data field storing notes for hall_of_fame_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `fulfilled_by` | `uuid` | YES | `NULL` | Data field storing fulfilled by for hall_of_fame_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `fulfilled_at` | `timestamp with time zone` | YES | `NULL` | Data field storing fulfilled at for hall_of_fame_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_hall_of_fame_rewards_fulfilled_by` ON (`fulfilled_by`)
- `idx_hof_rewards_status` ON (`status`)

---

### Table: `public.hostels`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `gate_id` → `gates.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the hostels record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for hostels record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `gate_id` | `uuid` | YES | `NULL` | Data field storing gate id for hostels record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_fee` | `numeric(10,2)` | NO | `0` | Data field storing delivery fee for hostels record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for hostels record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_hostels_gate_id` ON (`gate_id`)

---

### Table: `public.hp_bundle_purchases`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the hp_bundle_purchases record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `event_host_id` | `uuid` | NO | `NULL` | Data field storing event host id for hp_bundle_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_amount` | `integer` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `naira_paid` | `numeric(12,2)` | NO | `NULL` | Data field storing naira paid for hp_bundle_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `price_per_hp` | `numeric(10,4)` | NO | `5.0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `status` | `text` | NO | `'completed'::text` | Data field storing status for hp_bundle_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `hp_bundle_purchases_event_host_id_idx` ON (`event_host_id`)

**RLS Policies:**
- `Admins manage hp_bundle_purchases`
- `Users view own hp_bundle_purchases`

---

### Table: `public.hp_bundles`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the hp_bundles record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for hp_bundles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_amount` | `integer` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `price_naira` | `numeric(10,2)` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `total_price` | `numeric(10,2)` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `description` | `text` | YES | `NULL` | Data field storing description for hp_bundles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for hp_bundles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for hp_bundles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_hp_bundles_active` ON (`is_active`)

**RLS Policies:**
- `Admins manage hp_bundles`
- `Anyone can view active hp_bundles`

---

### Table: `public.hp_expiry_log`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `hp_transaction_id` → `hp_transactions.id`, `notification_id` → `notifications.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the hp_expiry_log record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `hp_transaction_id` | `uuid` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `expired_amount` | `integer` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `previous_balance` | `integer` | NO | `NULL` | Data field storing previous balance for hp_expiry_log record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reason` | `text` | NO | `NULL` | Data field storing reason for hp_expiry_log record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `notification_id` | `uuid` | YES | `NULL` | Data field storing notification id for hp_expiry_log record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_hp_expiry_log_hp_tx_id` ON (`hp_transaction_id`)
- `idx_hp_expiry_log_notification_id` ON (`notification_id`)
- `idx_hp_expiry_log_user_created` ON (`user_id,
created_at DESC`)

**Check Constraints:**
- `hp_expiry_log_expired_amount_check`: `(expired_amount > 0)`
- `hp_expiry_log_previous_balance_check`: `(previous_balance >= 0)`

---

### Table: `public.hp_tiers`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the hp_tiers record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `min_points` | `integer` | NO | `0` | Data field storing min points for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `maintenance_points` | `integer` | NO | `0` | Data field storing maintenance points for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `earn_multiplier` | `numeric(8,2)` | NO | `1` | Data field storing earn multiplier for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `benefits` | `jsonb` | NO | `'{}'::jsonb` | Data field storing benefits for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `slug` | `text` | YES | `NULL` | Data field storing slug for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `badge_color_hex` | `text` | YES | `NULL` | Data field storing badge color hex for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for hp_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_hp_tiers_sort` ON (`sort_order`)

**Unique Constraints:**
- `hp_tiers_name_key`: UNIQUE (`name`)
- `uq_hp_tiers_slug`: UNIQUE (`slug`)

**Check Constraints:**
- `chk_hp_tiers_min_points_nonneg`: `((min_points >= 0) AND (maintenance_points >= 0))`
- `chk_hp_tiers_multiplier_pos`: `(earn_multiplier > (0)::numeric)`

**RLS Policies:**
- `hp_tiers: admins all`
- `hp_tiers: public read active`

---

### Table: `public.hp_transactions`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `issued_by_admin_id` → `profiles.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the hp_transactions record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `type` | `text` | NO | `NULL` | Data field storing type for hp_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `amount` | `integer` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `balance_after` | `integer` | NO | `NULL` | Data field storing balance after for hp_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `source` | `text` | NO | `NULL` | Data field storing source for hp_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reference_type` | `text` | YES | `NULL` | Data field storing reference type for hp_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reference_id` | `uuid` | YES | `NULL` | Data field storing reference id for hp_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `issued_by_admin_id` | `uuid` | YES | `NULL` | Data field storing issued by admin id for hp_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for hp_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `expires_at` | `timestamp with time zone` | YES | `NULL` | Data field storing expires at for hp_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `remaining_amount` | `integer, status character varying(20)` | NO | `'active'::character varying` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |

**Indexes:**
- `hp_transactions_unique_business_key_idx` ON (`user_id,
reference_type, reference_id`)
- `idx_hp_transactions_user_created` ON (`user_id,
created_at DESC`)
- `idx_hp_transactions_user_status` ON (`user_id,
status`)
- `idx_hp_tx_expiring` ON (`user_id,
expires_at`)
- `idx_hp_tx_issued_by_admin_id` ON (`issued_by_admin_id`)
- `idx_hp_tx_reference` ON (`reference_type,
reference_id`)
- `idx_hp_tx_type` ON (`user_id, type`)
- `uq_hp_transactions_reward_unique` ON (`user_id,
reference_type, reference_id`)

**Check Constraints:**
- `check_hp_tx_amount_positive`: `(amount > 0)`
- `hp_transactions_amount_check`: `(amount > 0)`
- `hp_transactions_status_check`: `((status)::text = ANY ((ARRAY['active'::character varying, 'pending'::character varying, 'expired'::character varying, 'cancelled'::character varying])::text[]))`
- `hp_transactions_type_check`: `(type = ANY (ARRAY['earn'::text, 'spend'::text, 'expire'::text, 'adjustment'::text]))`

**RLS Policies:**
- `hp_transactions: admins all`
- `hp_transactions: users read own`

---

### Table: `public.kitchen_settings`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `key`

- **Foreign Keys:** `updated_by` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `key` | `text` | NO | `NULL` | Data field storing key for kitchen_settings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `value` | `text` | NO | `''::text` | Data field storing value for kitchen_settings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | YES | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_by` | `uuid` | YES | `NULL` | Data field storing updated by for kitchen_settings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_kitchen_settings_updated_by` ON (`updated_by`)

**RLS Policies:**
- `Anyone can view kitchen_settings`
- `Kitchen and admins manage
kitchen_settings`

---

### Table: `public.leaderboard_entries`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the leaderboard_entries record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `period` | `text` | NO | `NULL` | Data field storing period for leaderboard_entries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `rank` | `integer` | NO | `NULL` | Data field storing rank for leaderboard_entries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_total` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for leaderboard_entries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `order_count` | `integer` | NO | `0` | Data field storing order count for leaderboard_entries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_leaderboard_entries_user_id` ON (`user_id`)
- `idx_leaderboard_period_rank` ON (`period,
rank`)

**RLS Policies:**
- `leaderboard_entries: admins all`
- `leaderboard_entries: public read`

---

### Table: `public.leaderboard_reward_fulfillments`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `fulfilled_by` → `profiles.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the leaderboard_reward_fulfillments record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `rank` | `integer` | NO | `NULL` | Data field storing rank for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `month` | `text` | NO | `NULL` | Data field storing month for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reward_type` | `text` | NO | `'leaderboard_prize'::text` | Data field storing reward type for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `free_sides` | `integer` | NO | `0` | Data field storing free sides for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `free_spins` | `integer` | NO | `0` | Data field storing free spins for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `notes` | `text` | YES | `NULL` | Data field storing notes for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `fulfilled_by` | `uuid` | YES | `NULL` | Data field storing fulfilled by for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `fulfilled_at` | `timestamp with time zone` | YES | `NULL` | Data field storing fulfilled at for leaderboard_reward_fulfillments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_lb_fulfillments_month` ON (`month`)
- `idx_lb_fulfillments_status` ON (`status`)
- `idx_leaderboard_reward_fulfillments_fulfilled_by` ON (`fulfilled_by`)
- `uq_lb_fulfillment_user_month` ON (`user_id, month`)

**Check Constraints:**
- `leaderboard_reward_fulfillments_rank_check`: `((rank >= 1) AND (rank <= 10))`
- `leaderboard_reward_fulfillments_status_check`: `(status = ANY (ARRAY['pending'::text, 'fulfilled'::text, 'cancelled'::text]))`

---

### Table: `public.leaderboard_snapshots`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the leaderboard_snapshots record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `period_key` | `text` | NO | `NULL` | Data field storing period key for leaderboard_snapshots record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ranking_type` | `text` | NO | `'weekly'::text` | Data field storing ranking type for leaderboard_snapshots record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `entries` | `jsonb` | NO | `NULL` | Data field storing entries for leaderboard_snapshots record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `prizes_awarded` | `jsonb` | NO | `'[]'::jsonb` | Data field storing prizes awarded for leaderboard_snapshots record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**RLS Policies:**
- `leaderboard_snapshots: admins all`
- `leaderboard_snapshots: public read`

---

### Table: `public.login_streak_rewards`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the login_streak_rewards record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `week_number` | `integer` | NO | `NULL` | Data field storing week number for login_streak_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for login_streak_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `uq_login_streak_rewards_week` ON (`week_number`)

**RLS Policies:**
- `Admins manage login_streak_rewards`
- `Anyone reads login_streak_rewards`

---

### Table: `public.login_streaks`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the login_streaks record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `streak_count` | `integer` | NO | `1` | Data field storing streak count for login_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `last_login_date` | `date` | NO | `CURRENT_DATE` | Data field storing last login date for login_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `last_updated` | `timestamp with time zone` | NO | `now()` | Data field storing last updated for login_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `current_week_start` | `date` | YES | `NULL` | Data field storing current week start for login_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `week_state` | `jsonb` | NO | `'{}'::jsonb` | Data field storing week state for login_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `cycle_week_number` | `integer` | NO | `1` | Data field storing cycle week number for login_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `consecutive_weeks` | `integer` | NO | `0` | Data field storing consecutive weeks for login_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_login_streaks_user` ON (`user_id`)

**Unique Constraints:**
- `login_streaks_user_id_key`: UNIQUE (`user_id`)

**Check Constraints:**
- `login_streaks_consecutive_weeks_check`: `(consecutive_weeks >= 0)`
- `login_streaks_cycle_week_number_check`: `(cycle_week_number >= 1)`
- `login_streaks_streak_count_check`: `(streak_count >= 0)`

**RLS Policies:**
- `Admins manage streaks`
- `Users view own streak`

---

### Table: `public.marketplace_access_codes`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the marketplace_access_codes record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `listing_id` | `uuid` | NO | `NULL` | Data field storing listing id for marketplace_access_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `batch_id` | `uuid` | YES | `NULL` | Data field storing batch id for marketplace_access_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `code` | `text` | NO | `NULL` | Data field storing code for marketplace_access_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'available'::text` | Data field storing status for marketplace_access_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `assigned_purchase_id` | `uuid` | YES | `NULL` | Data field storing assigned purchase id for marketplace_access_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `assigned_at` | `timestamp with time zone` | YES | `NULL` | Data field storing assigned at for marketplace_access_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_marketplace_access_codes_status_listing` ON (`status, listing_id`)
- `idx_marketplace_codes_available` ON (`listing_id`)
- `idx_marketplace_codes_listing` ON (`listing_id, status`)
- `idx_mkt_access_codes_batch_id` ON (`batch_id`)

**RLS Policies:**
- `marketplace_access_codes: admins
all`

---

### Table: `public.marketplace_code_batches`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the marketplace_code_batches record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `listing_id` | `uuid` | NO | `NULL` | Data field storing listing id for marketplace_code_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `uploaded_by` | `uuid` | YES | `NULL` | Data field storing uploaded by for marketplace_code_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `code_count` | `integer` | NO | `NULL` | Data field storing code count for marketplace_code_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for marketplace_code_batches record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_mkt_code_batches_listing_id` ON (`listing_id`)
- `idx_mkt_code_batches_uploaded_by` ON (`uploaded_by`)

**RLS Policies:**
- `marketplace_code_batches: admins
all`

---

### Table: `public.marketplace_listings`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the marketplace_listings record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `title` | `text` | NO | `NULL` | Data field storing title for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `slug` | `text` | NO | `NULL` | Data field storing slug for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `vendor_name` | `text` | NO | `NULL` | Data field storing vendor name for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `listing_type` | `text` | NO | `NULL` | Data field storing listing type for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `price` | `numeric(14,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `hp_price` | `integer` | YES | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `image_url` | `text` | YES | `NULL` | Data field storing image url for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `approved_by` | `uuid` | YES | `NULL` | Data field storing approved by for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `approved_at` | `timestamp with time zone` | YES | `NULL` | Data field storing approved at for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `rejection_reason` | `text` | YES | `NULL` | Data field storing rejection reason for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `inventory_count` | `integer` | YES | `NULL` | Data field storing inventory count for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `low_inventory_threshold` | `integer` | YES | `NULL` | Data field storing low inventory threshold for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_out_of_stock` | `boolean` | NO | `false` | Data field storing is out of stock for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `min_tier_id` | `uuid` | YES | `NULL` | Data field storing min tier id for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `is_featured` | `boolean` | NO | `false` | Data field storing is featured for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `available_from` | `timestamp with time zone` | YES | `NULL` | Data field storing available from for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `available_until` | `timestamp with time zone` | YES | `NULL` | Data field storing available until for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `vendor_contact_email` | `citext` | YES | `NULL` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `cash_price` | `numeric(10,2)` | YES | `NULL::numeric` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `total_value` | `numeric(10,2)` | YES | `NULL::numeric` | Data field storing total value for marketplace_listings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_marketplace_active` ON (`sort_order, created_at`)
- `idx_marketplace_featured` ON (`sort_order`)
- `idx_marketplace_listings_approved_by` ON (`approved_by`)
- `idx_marketplace_listings_min_tier_id` ON (`min_tier_id`)
- `idx_marketplace_title_trgm` ON (`title
gin_trgm_ops`)

**RLS Policies:**
- `marketplace_listings: admins all`
- `marketplace_listings: public read
active`

---

### Table: `public.marketplace_purchases`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the marketplace_purchases record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `listing_id` | `uuid` | NO | `NULL` | Data field storing listing id for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `quantity` | `integer` | NO | `1` | Data field storing quantity for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `pay_with_hp` | `boolean` | NO | `false` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_fulfilled` | `boolean` | NO | `false` | Data field storing is fulfilled for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `fulfilled_at` | `timestamp with time zone` | YES | `NULL` | Data field storing fulfilled at for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `payment_method` | `text` | YES | `NULL` | Data field storing payment method for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `wallet_amount` | `numeric(12,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `card_amount` | `numeric(12,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `payment_reference` | `text` | YES | `NULL` | Data field storing payment reference for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `wallet_tx_id` | `uuid` | YES | `NULL` | Data field storing wallet tx id for marketplace_purchases record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_tx_id` | `uuid` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |

**Indexes:**
- `idx_marketplace_purchases_listing` ON (`listing_id`)
- `idx_marketplace_purchases_user` ON (`user_id,
created_at DESC`)
- `idx_mkt_purchases_hp_tx_id` ON (`hp_tx_id`)
- `idx_mkt_purchases_wallet_tx_id` ON (`wallet_tx_id`)

**RLS Policies:**
- `marketplace_purchases: admins all`
- `marketplace_purchases: users read
own`

---

### Table: `public.marketplace_requests`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the marketplace_requests record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `vendor_name` | `text` | NO | `NULL` | Data field storing vendor name for marketplace_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `vendor_email` | `text` | NO | `NULL` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `vendor_phone` | `text` | YES | `NULL` | Contact phone number used for delivery alerts. | API Request / Profile | upon record creation | NULL if phone number not provided | None |
| `service_title` | `text` | NO | `NULL` | Data field storing service title for marketplace_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `category` | `text` | NO | `NULL` | Data field storing category for marketplace_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | NO | `NULL` | Data field storing description for marketplace_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `proposed_price` | `numeric` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for marketplace_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `admin_notes` | `text` | YES | `NULL` | Data field storing admin notes for marketplace_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reviewed_by` | `uuid` | YES | `NULL` | Data field storing reviewed by for marketplace_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reviewed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing reviewed at for marketplace_requests record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_marketplace_requests_reviewed_by` ON (`reviewed_by`)
- `idx_marketplace_requests_status` ON (`status,
created_at DESC`)

**RLS Policies:**
- `Admins manage marketplace requests`

---

### Table: `public.membership_rewards`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the membership_rewards record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `months` | `integer` | NO | `NULL` | Data field storing months for membership_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for membership_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `uq_membership_rewards_months` ON (`months`)

**RLS Policies:**
- `Admins manage membership_rewards`
- `Anyone reads membership_rewards`

---

### Table: `public.menu_addon_groups`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `menu_item_id` → `menu_items.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the menu_addon_groups record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `menu_item_id` | `uuid` | NO | `NULL` | Data field storing menu item id for menu_addon_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `name` | `text` | NO | `NULL` | Data field storing name for menu_addon_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_required` | `boolean` | NO | `false` | Data field storing is required for menu_addon_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `min_select` | `integer` | NO | `0` | Data field storing min select for menu_addon_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `max_select` | `integer` | NO | `1` | Data field storing max select for menu_addon_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for menu_addon_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_menu_addon_groups_item` ON (`menu_item_id`)

**Check Constraints:**
- `menu_addon_groups_check`: `((min_select >= 0) AND (max_select >= min_select))`

**RLS Policies:**
- `Admins manage addon groups`
- `Anyone can view addon groups`

---

### Table: `public.menu_addons`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `group_id` → `menu_addon_groups.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the menu_addons record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for menu_addons record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `''::text` | Data field storing description for menu_addons record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `price` | `numeric(10,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `is_available` | `boolean` | YES | `true` | Data field storing is available for menu_addons record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_archived` | `boolean` | YES | `false` | Data field storing is archived for menu_addons record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | YES | `0` | Data field storing sort order for menu_addons record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | YES | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | YES | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `group_id` | `uuid` | YES | `NULL` | Data field storing group id for menu_addons record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_menu_addons_available` ON (`is_available,
is_archived`)
- `idx_menu_addons_group_id` ON (`group_id`)

**RLS Policies:**
- `Admins manage menu_addons`
- `Anyone can view available
menu_addons`

---

### Table: `public.menu_categories`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the menu_categories record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for menu_categories record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `slug` | `text` | NO | `NULL` | Data field storing slug for menu_categories record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for menu_categories record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for menu_categories record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for menu_categories record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_menu_categories_active` ON (`sort_order`)

**Unique Constraints:**
- `menu_categories_slug_key`: UNIQUE (`slug`)

**RLS Policies:**
- `menu_categories: admins all`
- `menu_categories: public read active`

---

### Table: `public.menu_item_variation_groups`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the menu_item_variation_groups record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `menu_item_id` | `uuid` | NO | `NULL` | Data field storing menu item id for menu_item_variation_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `name` | `text` | NO | `NULL` | Data field storing name for menu_item_variation_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_required` | `boolean` | YES | `false` | Data field storing is required for menu_item_variation_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `min_selections` | `integer` | YES | `0` | Data field storing min selections for menu_item_variation_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `max_selections` | `integer` | YES | `1` | Data field storing max selections for menu_item_variation_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | YES | `0` | Data field storing sort order for menu_item_variation_groups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | YES | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_menu_item_variation_groups_item` ON (`menu_item_id`)

**RLS Policies:**
- `Admins manage
menu_item_variation_groups`
- `Anyone can view
menu_item_variation_groups`

---

### Table: `public.menu_item_variation_options`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the menu_item_variation_options record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `variation_group_id` | `uuid` | NO | `NULL` | Data field storing variation group id for menu_item_variation_options record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `name` | `text` | NO | `NULL` | Data field storing name for menu_item_variation_options record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `price_delta` | `numeric(10,2)` | YES | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `is_available` | `boolean` | YES | `true` | Data field storing is available for menu_item_variation_options record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | YES | `0` | Data field storing sort order for menu_item_variation_options record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | YES | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_menu_item_variation_options_group` ON (`variation_group_id`)

**RLS Policies:**
- `Admins manage
menu_item_variation_options`
- `Anyone can view available
variation_options`

---

### Table: `public.menu_items`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `category_id` → `menu_categories.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the menu_items record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `category_id` | `uuid` | NO | `NULL` | Data field storing category id for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `name` | `text` | NO | `NULL` | Data field storing name for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `slug` | `text` | NO | `NULL` | Data field storing slug for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `image_url` | `text` | YES | `NULL` | Data field storing image url for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `price` | `numeric(14,2)` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `hp_earn` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `is_available` | `boolean` | NO | `true` | Data field storing is available for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_featured` | `boolean` | NO | `false` | Data field storing is featured for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `tags` | `text[]` | NO | `'{}'::text[]` | Data field storing tags for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `options` | `jsonb` | NO | `'{}'::jsonb` | Data field storing options for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `deleted_at` | `timestamp with time zone` | YES | `NULL` | Data field storing deleted at for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `daily_limit` | `integer` | YES | `NULL` | Data field storing daily limit for menu_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_earn_value` | `integer` | YES | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `hp_multiplier` | `numeric(3,2)` | NO | `1.0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |

**Indexes:**
- `idx_menu_items_available` ON (`category_id`)
- `idx_menu_items_category` ON (`category_id`)
- `idx_menu_items_featured` ON (`is_featured`)
- `idx_menu_items_name_trgm` ON (`name gin_trgm_ops`)
- `idx_menu_items_not_deleted` ON (`id`)

**Unique Constraints:**
- `menu_items_slug_key`: UNIQUE (`slug`)

**Check Constraints:**
- `menu_items_hp_earn_check`: `(hp_earn >= 0)`
- `menu_items_hp_multiplier_check`: `(hp_multiplier = ANY (ARRAY[0.5, 1.0, 2.0]))`
- `menu_items_price_check`: `(price >= (0)::numeric)`

**RLS Policies:**
- `menu_items: admins all`
- `menu_items: public read available`

---

### Table: `public.milestones`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `created_by` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the milestones record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `title` | `text` | NO | `NULL` | Data field storing title for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `trigger_type` | `text` | NO | `NULL` | Data field storing trigger type for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `trigger_value` | `integer` | NO | `1` | Data field storing trigger value for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `time_window` | `text` | YES | `NULL` | Data field storing time window for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `icon_won` | `text` | YES | `NULL` | Data field storing icon won for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `icon_locked` | `text` | YES | `NULL` | Data field storing icon locked for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_by` | `uuid` | YES | `NULL` | Data field storing created by for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `social_link` | `text` | YES | `NULL` | Data field storing social link for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `trigger_meta` | `jsonb` | YES | `NULL` | Data field storing trigger meta for milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_milestones_created_by` ON (`created_by`)
- `idx_milestones_trigger_type` ON (`trigger_type,
is_active`)

**Check Constraints:**
- `milestones_time_window_check`: `(time_window = ANY (ARRAY['weekly'::text, 'monthly'::text]))`

**RLS Policies:**
- `Admins manage milestones`
- `Anyone can view active milestones`

---

### Table: `public.monthly_hp_tracker`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the monthly_hp_tracker record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `month` | `text` | NO | `NULL` | Data field storing month for monthly_hp_tracker record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `total_earned` | `integer` | NO | `0` | Data field storing total earned for monthly_hp_tracker record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_monthly_hp_tracker_user_month` ON (`user_id,
month`)

**RLS Policies:**
- `Admins manage monthly trackers`
- `Users view own monthly tracker`

---

### Table: `public.newsletter_subscriptions`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `uuid_generate_v4()` | Primary key UUID unique identifier for the newsletter_subscriptions record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `email` | `citext` | NO | `NULL` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `full_name` | `text` | YES | `NULL` | Data field storing full name for newsletter_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | YES | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `source` | `text` | NO | `'website'::text` | Data field storing source for newsletter_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `tags` | `text[]` | NO | `'{}'::text[]` | Data field storing tags for newsletter_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_confirmed` | `boolean` | NO | `false` | Data field storing is confirmed for newsletter_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `confirmed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing confirmed at for newsletter_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `unsubscribed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing unsubscribed at for newsletter_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_newsletter_user_id` ON (`user_id`)

**RLS Policies:**
- `newsletter_subscriptions: admins
all`
- `newsletter_subscriptions: public
insert`

---

### Table: `public.notification_blasts`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the notification_blasts record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `title` | `text` | NO | `NULL` | Data field storing title for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `body` | `text` | NO | `NULL` | Data field storing body for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `channels` | `text[]` | NO | `'{}'::text[]` | Data field storing channels for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `segment` | `jsonb` | NO | `'{}'::jsonb` | Data field storing segment for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `action_url` | `text` | YES | `NULL` | Data field storing action url for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `scheduled_at` | `timestamp with time zone` | YES | `NULL` | Data field storing scheduled at for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'draft'::text` | Data field storing status for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_by` | `uuid` | YES | `NULL` | Data field storing created by for notification_blasts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_notification_blasts_created_by` ON (`created_by`)
- `idx_notification_blasts_scheduled` ON (`scheduled_at`)

**RLS Policies:**
- `notification_blasts: admins all`

---

### Table: `public.notification_deliveries`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the notification_deliveries record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `notification_id` | `uuid` | YES | `NULL` | Data field storing notification id for notification_deliveries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `blast_id` | `uuid` | YES | `NULL` | Data field storing blast id for notification_deliveries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | YES | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `channel` | `text` | NO | `NULL` | Data field storing channel for notification_deliveries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'queued'::text` | Data field storing status for notification_deliveries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `provider_message_id` | `text` | YES | `NULL` | Data field storing provider message id for notification_deliveries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `error_message` | `text` | YES | `NULL` | Data field storing error message for notification_deliveries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivered_at` | `timestamp with time zone` | YES | `NULL` | Data field storing delivered at for notification_deliveries record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_notification_deliveries_blast_id` ON (`blast_id`)
- `idx_notification_deliveries_notif_id` ON (`notification_id`)
- `idx_notification_deliveries_user` ON (`user_id, created_at DESC`)

**RLS Policies:**
- `notification_deliveries: admins all`
- `notification_deliveries: users read`

---

### Table: `public.notification_log`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the notification_log record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `type` | `text` | NO | `NULL` | Data field storing type for notification_log record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sent_at` | `timestamp with time zone` | NO | `now()` | Data field storing sent at for notification_log record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_notification_log_user_sent` ON (`user_id,
sent_at DESC`)
- `idx_notification_log_user_type` ON (`user_id, type,
sent_at DESC`)

**RLS Policies:**
- `Admins manage notification_log`

---

### Table: `public.notification_preferences`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the notification_preferences record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `push_enabled` | `boolean` | NO | `true` | Data field storing push enabled for notification_preferences record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `email_enabled` | `boolean` | NO | `true` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `order_updates` | `boolean` | NO | `true` | Data field storing order updates for notification_preferences record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `promotions` | `boolean` | NO | `true` | Data field storing promotions for notification_preferences record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_updates` | `boolean` | NO | `true` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `delivery_updates` | `boolean` | NO | `true` | Data field storing delivery updates for notification_preferences record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**RLS Policies:**
- `Users manage own notification
preferences`

---

### Table: `public.notifications`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the notifications record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | YES | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `title` | `text` | NO | `NULL` | Data field storing title for notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `body` | `text` | NO | `NULL` | Data field storing body for notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `channel` | `text` | NO | `'in_app'::text` | Data field storing channel for notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `action_url` | `text` | YES | `NULL` | Data field storing action url for notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `read_at` | `timestamp with time zone` | YES | `NULL` | Data field storing read at for notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `type` | `text` | NO | `'system'::text` | Data field storing type for notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_notifications_unread` ON (`user_id,
created_at DESC`)
- `idx_notifications_user` ON (`user_id,
created_at DESC`)

**Check Constraints:**
- `notifications_channel_check`: `(channel = ANY (ARRAY['in_app'::text, 'email'::text, 'sms'::text, 'push'::text]))`

**RLS Policies:**
- `notifications: admins all`
- `notifications: users read own`
- `notifications: users update own`

---

### Table: `public.operating_hour_overrides`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the operating_hour_overrides record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `date` | `date` | NO | `NULL` | Data field storing date for operating_hour_overrides record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `opens_at` | `time without time zone` | YES | `NULL` | Data field storing opens at for operating_hour_overrides record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `closes_at` | `time without time zone` | YES | `NULL` | Data field storing closes at for operating_hour_overrides record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_closed` | `boolean` | NO | `false` | Data field storing is closed for operating_hour_overrides record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reason` | `text` | YES | `NULL` | Data field storing reason for operating_hour_overrides record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**RLS Policies:**
- `operating_hour_overrides: admins
all`
- `operating_hour_overrides: public
read`

---

### Table: `public.operating_hours`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the operating_hours record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `weekday` | `integer` | NO | `NULL` | Data field storing weekday for operating_hours record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `opens_at` | `time without time zone` | YES | `NULL` | Data field storing opens at for operating_hours record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `closes_at` | `time without time zone` | YES | `NULL` | Data field storing closes at for operating_hours record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_closed` | `boolean` | NO | `false` | Data field storing is closed for operating_hours record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Unique Constraints:**
- `operating_hours_weekday_key`: UNIQUE (`weekday`)

**Check Constraints:**
- `operating_hours_weekday_check`: `((weekday >= 0) AND (weekday <= 6))`

**RLS Policies:**
- `operating_hours: admins all`
- `operating_hours: public read`

---

### Table: `public.order_addon_selections`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the order_addon_selections record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `order_item_id` | `uuid` | NO | `NULL` | Data field storing order item id for order_addon_selections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `addon_id` | `uuid` | NO | `NULL` | Data field storing addon id for order_addon_selections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `group_id` | `uuid` | YES | `NULL` | Data field storing group id for order_addon_selections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `name_snapshot` | `text` | NO | `NULL` | Data field storing name snapshot for order_addon_selections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `price_delta_snapshot` | `numeric(10,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `quantity` | `integer` | NO | `1` | Data field storing quantity for order_addon_selections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_order_addon_selections_addon_id` ON (`addon_id`)
- `idx_order_addon_selections_group_id` ON (`group_id`)
- `idx_order_addon_selections_order_item` ON (`order_item_id`)

**RLS Policies:**
- `Admins/kitchen manage addon
selections`

---

### Table: `public.order_items`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `addon_id` → `menu_addons.id`, `menu_item_id` → `menu_items.id`, `order_id` → `orders.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the order_items record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `order_id` | `uuid` | NO | `NULL` | Data field storing order id for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `menu_item_id` | `uuid` | YES | `NULL` | Data field storing menu item id for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `name_snapshot` | `text` | NO | `NULL` | Data field storing name snapshot for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `price_snapshot` | `numeric(14,2)` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `hp_earn_snapshot` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `quantity` | `integer` | NO | `NULL` | Data field storing quantity for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `options_snapshot` | `jsonb` | NO | `'{}'::jsonb` | Data field storing options snapshot for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `line_total` | `numeric(14,2)` | NO | `0` | Data field storing line total for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `selected_variations` | `jsonb` | YES | `'[]'::jsonb` | Data field storing selected variations for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_addon` | `boolean` | YES | `false` | Data field storing is addon for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `addon_id` | `uuid` | YES | `NULL` | Data field storing addon id for order_items record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_multiplier_snapshot` | `numeric(3,2)` | NO | `1.0` | Frozen snapshot of menu item HP earn multiplier at checkout time to preserve historical calculations. | order_service.create_order | at checkout time | defaults to 1.0 | menu_items.hp_multiplier |

**Indexes:**
- `idx_order_items_addon_id` ON (`addon_id`)
- `idx_order_items_menu_item_id` ON (`menu_item_id`)
- `idx_order_items_order_id` ON (`order_id`)

**Check Constraints:**
- `chk_order_items_line_total_nonneg`: `(line_total >= (0)::numeric)`
- `order_items_quantity_check`: `(quantity > 0)`

**RLS Policies:**
- `order_items: admins all`
- `order_items: users read own`

---

### Table: `public.order_locks`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `order_id` → `orders.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the order_locks record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `locked_date` | `date` | NO | `NULL` | Data field storing locked date for order_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `discount_pct` | `numeric(5,2)` | NO | `10` | Data field storing discount pct for order_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'active'::text` | Data field storing status for order_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reminder_sent_at` | `timestamp with time zone` | YES | `NULL` | Data field storing reminder sent at for order_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reschedule_count` | `integer` | NO | `0` | Data field storing reschedule count for order_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `order_id` | `uuid` | YES | `NULL` | Data field storing order id for order_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `reward_type` | `text` | NO | `'discount'::text` | Data field storing reward type for order_locks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reward_hp_amount` | `integer` | YES | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |

**Indexes:**
- `idx_order_locks_locked_date` ON (`locked_date`)
- `idx_order_locks_order_id` ON (`order_id`)
- `idx_order_locks_user_status` ON (`user_id, status`)

**Check Constraints:**
- `order_locks_discount_pct_check`: `((discount_pct >= (1)::numeric) AND (discount_pct <= (50)::numeric))`
- `order_locks_reschedule_count_check`: `(reschedule_count >= 0)`
- `order_locks_reward_type_check`: `(reward_type = ANY (ARRAY['discount'::text, 'hp'::text]))`
- `order_locks_status_check`: `(status = ANY (ARRAY['active'::text, 'used'::text, 'expired'::text, 'cancelled'::text]))`

**RLS Policies:**
- `Admins manage all locks`
- `Users manage own locks`

---

### Table: `public.order_reviews`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `order_id` → `orders.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the order_reviews record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `order_id` | `uuid` | NO | `NULL` | Data field storing order id for order_reviews record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `rating` | `integer` | NO | `NULL` | Data field storing rating for order_reviews record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `comment` | `text` | YES | `NULL` | Data field storing comment for order_reviews record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_rewarded` | `integer` | NO | `30` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `image_urls` | `text[]` | NO | `'{}'::text[]` | Data field storing image urls for order_reviews record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_flagged` | `boolean` | NO | `false` | Data field storing is flagged for order_reviews record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `hp_awarded` | `integer` | NO | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `kitchen_rating` | `smallint` | YES | `NULL` | Data field storing kitchen rating for order_reviews record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `rider_rating` | `smallint` | YES | `NULL` | Data field storing rider rating for order_reviews record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_order_reviews_kitchen_rating` ON (`kitchen_rating`)
- `idx_order_reviews_order_id` ON (`order_id`)
- `idx_order_reviews_rider_rating` ON (`rider_rating`)
- `idx_order_reviews_user_id` ON (`user_id`)

**Unique Constraints:**
- `order_reviews_order_id_key`: UNIQUE (`order_id`)

**Check Constraints:**
- `order_reviews_kitchen_rating_check`: `((kitchen_rating >= 1) AND (kitchen_rating <= 5))`
- `order_reviews_rating_check`: `((rating >= 1) AND (rating <= 5))`
- `order_reviews_rider_rating_check`: `((rider_rating >= 1) AND (rider_rating <= 5))`

**RLS Policies:**
- `order_reviews: admins all`
- `order_reviews: public read`
- `order_reviews: users update`

---

### Table: `public.order_share_events`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the order_share_events record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `order_id` | `uuid` | NO | `NULL` | Data field storing order id for order_share_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `platform` | `text` | NO | `'whatsapp'::text` | Data field storing platform for order_share_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_order_share_events_order_id` ON (`order_id`)
- `idx_order_share_events_user` ON (`user_id,
created_at DESC`)

**RLS Policies:**
- `Admins manage share events`
- `Users view own share events`

---

### Table: `public.order_status_logs`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `changed_by` → `profiles.id`, `order_id` → `orders.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the order_status_logs record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `order_id` | `uuid` | NO | `NULL` | Data field storing order id for order_status_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `order_status` | NO | `NULL` | Data field storing status for order_status_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `changed_by` | `uuid` | YES | `NULL` | Data field storing changed by for order_status_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `note` | `text` | YES | `NULL` | Data field storing note for order_status_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for order_status_logs record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_order_status_logs_changed_by` ON (`changed_by`)
- `idx_order_status_logs_order` ON (`order_id,
created_at DESC`)

**RLS Policies:**
- `order_status_logs: admins all`
- `order_status_logs: users read own`

---

### Table: `public.order_streak_rewards`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the order_streak_rewards record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `weeks` | `integer` | NO | `NULL` | Data field storing weeks for order_streak_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for order_streak_rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `uq_order_streak_rewards_weeks` ON (`weeks`)

**RLS Policies:**
- `Admins manage order_streak_rewards`
- `Anyone reads order_streak_rewards`

---

### Table: `public.order_streaks`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the order_streaks record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `streak_weeks` | `integer` | NO | `0` | Data field storing streak weeks for order_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `longest_streak` | `integer` | NO | `0` | Data field storing longest streak for order_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `last_order_week` | `text` | YES | `NULL` | Data field storing last order week for order_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `last_updated` | `timestamp with time zone` | NO | `now()` | Data field storing last updated for order_streaks record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_order_streaks_user` ON (`user_id`)

**Unique Constraints:**
- `order_streaks_user_id_key`: UNIQUE (`user_id`)

**Check Constraints:**
- `order_streaks_streak_weeks_check`: `(streak_weeks >= 0)`

**RLS Policies:**
- `Admins manage order_streaks`
- `Users view own order streak`

---

### Table: `public.orders`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `batch_id` → `delivery_batches.id`, `delivery_window_id` → `delivery_windows.id`, `promo_code_id` → `promo_codes.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the orders record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `order_number` | `text` | NO | `('HG-'::text || upper(substr(replace((gen_random_uuid())::text, '-'::text, ''::text), 1, 10)))` | Data field storing order number for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | YES | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `guest_name` | `text` | YES | `NULL` | Data field storing guest name for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `guest_email` | `citext` | YES | `NULL` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `guest_phone` | `text` | YES | `NULL` | Contact phone number used for delivery alerts. | API Request / Profile | upon record creation | NULL if phone number not provided | None |
| `status` | `order_status` | NO | `'received'::order_status` | Data field storing status for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `payment_status` | `payment_status` | NO | `'pending'::payment_status` | Data field storing payment status for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `subtotal` | `numeric(14,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `delivery_fee` | `numeric(14,2)` | NO | `0` | Data field storing delivery fee for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `discount_amount` | `numeric(14,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `total_amount` | `numeric(14,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `hp_earned` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `hp_redeemed` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `hp_credited_at` | `timestamp with time zone` | YES | `NULL` | Timestamp recording when earned HP was credited to user profile upon order delivery. | Celery / Order Service | when order transitions to 'delivered' status | NULL before order is delivered | orders.status, profiles.hp_balance |
| `wallet_amount_used` | `numeric(14,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `card_amount_used` | `numeric(14,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `delivery_address_snapshot` | `jsonb` | NO | `'{}'::jsonb` | Data field storing delivery address snapshot for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_window_id` | `uuid` | YES | `NULL` | Data field storing delivery window id for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `notes` | `text` | YES | `NULL` | Data field storing notes for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `scheduled_for` | `timestamp with time zone` | YES | `NULL` | Data field storing scheduled for for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `payment_confirmed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing payment confirmed at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `received_at` | `timestamp with time zone` | YES | `now()` | Data field storing received at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `paid_at` | `timestamp with time zone` | YES | `NULL` | Data field storing paid at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `preparing_at` | `timestamp with time zone` | YES | `NULL` | Data field storing preparing at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ready_at` | `timestamp with time zone` | YES | `NULL` | Data field storing ready at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `assigned_at` | `timestamp with time zone` | YES | `NULL` | Data field storing assigned at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `out_for_delivery_at` | `timestamp with time zone` | YES | `NULL` | Data field storing out for delivery at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivered_at` | `timestamp with time zone` | YES | `NULL` | Data field storing delivered at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `cancelled_at` | `timestamp with time zone` | YES | `NULL` | Data field storing cancelled at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `refunded_at` | `timestamp with time zone` | YES | `NULL` | Data field storing refunded at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `promo_code_id` | `uuid` | YES | `NULL` | Data field storing promo code id for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `batch_id` | `uuid` | YES | `NULL` | Data field storing batch id for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `payment_reference` | `text` | YES | `NULL` | Data field storing payment reference for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_attempted_at` | `timestamp with time zone` | YES | `NULL` | Data field storing delivery attempted at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `unclaimed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing unclaimed at for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_squad_order` | `boolean` | NO | `false` | Data field storing is squad order for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `squad_discount_amount` | `numeric(10,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `squad_item_count` | `integer` | NO | `0` | Data field storing squad item count for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `claim_token` | `uuid` | YES | `NULL` | Data field storing claim token for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_scheduled` | `boolean` | NO | `false` | Data field storing is scheduled for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `gift_included` | `boolean` | NO | `false` | Data field storing gift included for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_type` | `text` | YES | `NULL` | Data field storing delivery type for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_location_id` | `uuid` | YES | `NULL` | Data field storing delivery location id for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_location_lat` | `double precision` | YES | `NULL` | Data field storing delivery location lat for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `delivery_location_lon` | `double precision` | YES | `NULL` | Data field storing delivery location lon for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `squad_name` | `text` | YES | `NULL` | Data field storing squad name for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `idempotency_key` | `text` | YES | `NULL` | Data field storing idempotency key for orders record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_orders_active` ON (`user_id, status, created_at DESC`)
- `idx_orders_batch_id` ON (`batch_id`)
- `idx_orders_claim_token` ON (`claim_token`)
- `idx_orders_created_at` ON (`created_at DESC`)
- `idx_orders_guest_claim` ON (`guest_email, user_id,
hp_credited_at`)
- `idx_orders_is_scheduled` ON (`is_scheduled`)
- `idx_orders_is_squad_order` ON (`is_squad_order`)
- `idx_orders_payment_status` ON (`payment_status`)
- `idx_orders_promo_code_id` ON (`promo_code_id`)
- `idx_orders_status` ON (`status, created_at`)
- `idx_orders_user_created` ON (`user_id, created_at
DESC`)
- `idx_orders_user_id` ON (`user_id`)
- `idx_orders_window_id` ON (`delivery_window_id`)

**Unique Constraints:**
- `orders_idempotency_key_key`: UNIQUE (`idempotency_key`)
- `orders_order_number_key`: UNIQUE (`order_number`)

**Check Constraints:**
- `check_order_totals_positive`: `((subtotal >= (0)::numeric) AND (delivery_fee >= (0)::numeric) AND (discount_amount >= (0)::numeric) AND (total_amount >= (0)::numeric) AND (wallet_amount_used >= (0)::numeric) AND (card_amount_used >= (0)::numeric))`
- `chk_orders_delivery_fee_nonneg`: `(delivery_fee >= (0)::numeric)`
- `chk_orders_discount_nonneg`: `(discount_amount >= (0)::numeric)`
- `chk_orders_subtotal_nonneg`: `(subtotal >= (0)::numeric)`
- `chk_orders_total_nonneg`: `(total_amount >= (0)::numeric)`
- `orders_check`: `((user_id IS NOT NULL) OR (guest_email IS NOT NULL) OR (guest_phone IS NOT NULL))`
- `orders_delivery_type_check`: `(delivery_type = ANY (ARRAY['on_campus'::text, 'off_campus'::text]))`

**RLS Policies:**
- `orders: admins delete`
- `orders: admins update all`
- `orders: users insert own`
- `orders: users read own`

---

### Table: `public.payments`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `order_id` → `orders.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the payments record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `order_id` | `uuid` | YES | `NULL` | Data field storing order id for payments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | YES | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `provider` | `text` | NO | `NULL` | Data field storing provider for payments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reference` | `text` | NO | `NULL` | Data field storing reference for payments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `amount` | `numeric(14,2)` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for payments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `confirmed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing confirmed at for payments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for payments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `failure_reason` | `text` | YES | `NULL` | Data field storing failure reason for payments record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_payments_order_id` ON (`order_id`)
- `idx_payments_status` ON (`status`)
- `idx_payments_user_id` ON (`user_id`)

**Unique Constraints:**
- `payments_reference_key`: UNIQUE (`reference`)

**Check Constraints:**
- `check_payment_amount_positive`: `(amount >= (0)::numeric)`
- `chk_payments_amount_pos`: `(amount > (0)::numeric)`
- `payments_amount_check`: `(amount >= (0)::numeric)`

**RLS Policies:**
- `payments: admins all`
- `payments: users read own`

---

### Table: `public.profiles`

- **Campus Scoped:** YES (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `campus_id` → `campuses.id`, `current_tier_id` → `hp_tiers.id`, `deactivated_by` → `profiles.id`, `department_id` → `departments.id`, `referred_by` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `NULL` | Primary key UUID unique identifier for the profiles record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `email` | `citext` | NO | `NULL` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `full_name` | `text` | YES | `NULL` | Data field storing full name for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `phone` | `text` | YES | `NULL` | Contact phone number used for delivery alerts. | API Request / Profile | upon record creation | NULL if phone number not provided | None |
| `date_of_birth` | `date` | YES | `NULL` | Data field storing date of birth for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `faculty` | `text` | YES | `NULL` | Data field storing faculty for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `department` | `text` | YES | `NULL` | Data field storing department for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `photo_url` | `text` | YES | `NULL` | Data field storing photo url for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `role` | `user_role` | NO | `'student'::user_role` | Data field storing role for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `preferences` | `jsonb` | NO | `'{}'::jsonb` | Data field storing preferences for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_balance` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `wallet_balance` | `numeric(14,2)` | NO | `0` | Data field storing wallet balance for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `current_tier_id` | `uuid` | YES | `NULL` | Data field storing current tier id for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `tier_grace_started_at` | `timestamp with time zone` | YES | `NULL` | Data field storing tier grace started at for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `tier_lost_at` | `timestamp with time zone` | YES | `NULL` | Data field storing tier lost at for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `referral_code` | `text` | YES | `NULL` | Data field storing referral code for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `onboarding_completed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing onboarding completed at for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `last_seen_at` | `timestamp with time zone` | YES | `NULL` | Data field storing last seen at for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `push_enabled` | `boolean` | NO | `false` | Data field storing push enabled for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `email_notifications` | `boolean` | NO | `true` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `has_scheduled_order` | `boolean` | NO | `false` | Data field storing has scheduled order for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `deactivated_at` | `timestamp with time zone` | YES | `NULL` | Data field storing deactivated at for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `deactivated_by` | `uuid` | YES | `NULL` | Data field storing deactivated by for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `referred_by` | `uuid` | YES | `NULL` | Data field storing referred by for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `tier_grace_ends_at` | `timestamp with time zone` | YES | `NULL` | Expiration timestamp for 30-day tier grace period when rolling 120-day HP drops below maintenance threshold. | Celery task recalculate_120day_hp | when rolling 120-day HP falls below tier threshold | NULL if user is in good tier standing | profiles.tier |
| `last_hp_activity_at` | `timestamp with time zone` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `deactivation_reason` | `text` | YES | `NULL` | Data field storing deactivation reason for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `jwt_version` | `integer` | NO | `0` | Data field storing jwt version for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `last_activity_at` | `timestamp with time zone` | YES | `NULL` | Data field storing last activity at for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_earned_120day` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `graduation_claimed` | `boolean` | NO | `false` | Data field storing graduation claimed for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `top4_finish_count` | `integer` | NO | `0` | Data field storing top4 finish count for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `academic_level` | `text` | YES | `NULL` | Data field storing academic level for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `department_id` | `uuid` | YES | `NULL` | Data field storing department id for profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `campus_id` | `uuid` | YES | `NULL` | Foreign key referencing campuses.id enforcing multi-campus isolation. | API / Auth Middleware | upon record creation | NULL for global platform records | campuses.id |

**Indexes:**
- `idx_profiles_campus_id` ON (`campus_id`)
- `idx_profiles_current_tier_id` ON (`current_tier_id`)
- `idx_profiles_deactivated_by` ON (`deactivated_by`)
- `idx_profiles_department_id` ON (`department_id`)
- `idx_profiles_is_active` ON (`is_active`)
- `idx_profiles_jwt_version` ON (`id, jwt_version`)
- `idx_profiles_last_hp_activity` ON (`last_hp_activity_at`)
- `idx_profiles_referred_by` ON (`referred_by`)
- `idx_profiles_role` ON (`role`)

**Unique Constraints:**
- `profiles_email_key`: UNIQUE (`email`)
- `profiles_referral_code_key`: UNIQUE (`referral_code`)

**Check Constraints:**
- `profiles_hp_balance_check`: `(hp_balance >= 0)`
- `profiles_wallet_balance_check`: `(wallet_balance >= (0)::numeric)`

**RLS Policies:**
- `profiles: admins delete`
- `profiles: users read own`
- `profiles: users update own`

---

### Table: `public.promo_code_uses`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `order_id` → `orders.id`, `promo_code_id` → `promo_codes.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the promo_code_uses record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `promo_code_id` | `uuid` | NO | `NULL` | Data field storing promo code id for promo_code_uses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | YES | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `order_id` | `uuid` | YES | `NULL` | Data field storing order id for promo_code_uses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `discount_amount` | `numeric(14,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_promo_code_uses_order` ON (`order_id`)
- `idx_promo_code_uses_promo` ON (`promo_code_id`)
- `idx_promo_code_uses_user` ON (`user_id`)

**Unique Constraints:**
- `promo_code_uses_promo_code_id_order_id_key`: UNIQUE (`promo_code_id, order_id`)
- `uq_promo_code_uses_user_order`: UNIQUE (`user_id, order_id`)

**RLS Policies:**
- `promo_code_uses: admins all`
- `promo_code_uses: users read own`

---

### Table: `public.promo_codes`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `created_by` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the promo_codes record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `code` | `citext` | NO | `NULL` | Data field storing code for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `discount_type` | `text` | NO | `NULL` | Data field storing discount type for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `discount_value` | `numeric(14,2)` | NO | `NULL` | Data field storing discount value for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `scope` | `text` | NO | `'cart'::text` | Data field storing scope for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `applicable_item_ids` | `uuid[]` | NO | `'{}'::uuid[]` | Data field storing applicable item ids for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `applicable_category_ids` | `uuid[]` | NO | `'{}'::uuid[]` | Data field storing applicable category ids for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `max_uses` | `integer` | YES | `NULL` | Data field storing max uses for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `max_uses_per_user` | `integer` | YES | `NULL` | Data field storing max uses per user for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `starts_at` | `timestamp with time zone` | YES | `NULL` | Data field storing starts at for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `ends_at` | `timestamp with time zone` | YES | `NULL` | Data field storing ends at for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `used_count` | `integer` | NO | `0` | Data field storing used count for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `min_order_amount` | `numeric(12,2)` | NO | `0` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `created_by` | `uuid` | YES | `NULL` | Data field storing created by for promo_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_promo_codes_active` ON (`code, ends_at`)
- `idx_promo_codes_created_by` ON (`created_by`)

**Unique Constraints:**
- `promo_codes_code_key`: UNIQUE (`code`)

**Check Constraints:**
- `check_promo_max_uses`: `((max_uses IS NULL) OR (used_count <= max_uses))`
- `chk_promo_codes_discount_pos`: `(discount_value > (0)::numeric)`
- `chk_promo_codes_used_count_nonneg`: `(used_count >= 0)`
- `promo_codes_used_count_check`: `(used_count >= 0)`

**RLS Policies:**
- `promo_codes: admins all`
- `promo_codes: authenticated read
active`

---

### Table: `public.push_subscriptions`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the push_subscriptions record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `subscription` | `jsonb` | NO | `NULL` | Data field storing subscription for push_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `device_label` | `text` | YES | `NULL` | Data field storing device label for push_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for push_subscriptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_push_subscriptions_active` ON (`user_id`)

**RLS Policies:**
- `push_subscriptions: admins read all`
- `push_subscriptions: users crud own`

---

### Table: `public.referral_codes`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the referral_codes record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `code` | `text` | NO | `NULL` | Data field storing code for referral_codes record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Unique Constraints:**
- `referral_codes_code_key`: UNIQUE (`code`)
- `referral_codes_user_id_key`: UNIQUE (`user_id`)

**RLS Policies:**
- `referral_codes: admins all`
- `referral_codes: users read own`

---

### Table: `public.referral_milestones`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the referral_milestones record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `referral_count` | `integer` | NO | `NULL` | Data field storing referral count for referral_milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `is_repeating` | `boolean` | NO | `false` | Data field storing is repeating for referral_milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `repeat_interval` | `integer` | YES | `NULL` | Data field storing repeat interval for referral_milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for referral_milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `uq_referral_milestones_count` ON (`referral_count`)

**RLS Policies:**
- `Admins manage referral_milestones`
- `Anyone reads referral_milestones`

---

### Table: `public.referrals`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `referred_user_id` → `profiles.id`, `referrer_id` → `profiles.id`, `trigger_order_id` → `orders.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the referrals record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `referrer_id` | `uuid` | NO | `NULL` | Data field storing referrer id for referrals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `referred_user_id` | `uuid` | NO | `NULL` | Data field storing referred user id for referrals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `trigger_order_id` | `uuid` | YES | `NULL` | Data field storing trigger order id for referrals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for referrals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_referrals_referred` ON (`referred_user_id`)
- `idx_referrals_referrer` ON (`referrer_id`)
- `idx_referrals_referrer_created` ON (`referrer_id,
created_at DESC`)
- `idx_referrals_trigger_order_id` ON (`trigger_order_id`)

**Unique Constraints:**
- `referrals_referred_user_id_trigger_order_id_key`: UNIQUE (`referred_user_id, trigger_order_id`)
- `uq_referrals_referred_user`: UNIQUE (`referred_user_id`)

**RLS Policies:**
- `referrals: admins all`
- `referrals: users read own`

---

### Table: `public.reward_redemptions`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the reward_redemptions record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `reward_id` | `uuid` | NO | `NULL` | Data field storing reward id for reward_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for reward_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_cost_snapshot` | `integer` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `fulfilled_at` | `timestamp with time zone` | YES | `NULL` | Data field storing fulfilled at for reward_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `notes` | `text` | YES | `NULL` | Data field storing notes for reward_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `fulfilled_by` | `uuid` | YES | `NULL` | Data field storing fulfilled by for reward_redemptions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_reward_redemptions_fulfilled_by` ON (`fulfilled_by`)
- `idx_reward_redemptions_reward_id` ON (`reward_id`)
- `idx_reward_redemptions_user` ON (`user_id,
created_at DESC`)

**RLS Policies:**
- `reward_redemptions: admins all`
- `reward_redemptions: users read own`

---

### Table: `public.rewards`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `min_tier_id` → `hp_tiers.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the rewards record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `name` | `text` | NO | `NULL` | Data field storing name for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_cost` | `integer` | NO | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `reward_type` | `text` | NO | `NULL` | Data field storing reward type for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `stock_quantity` | `integer` | YES | `NULL` | Data field storing stock quantity for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `min_tier_id` | `uuid` | YES | `NULL` | Data field storing min tier id for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `expires_at` | `timestamp with time zone` | YES | `NULL` | Data field storing expires at for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `max_per_user` | `integer` | NO | `1` | Data field storing max per user for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `image_url` | `text` | YES | `NULL` | Data field storing image url for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `flash_enabled` | `boolean` | YES | `false` | Data field storing flash enabled for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `flash_hp_cost` | `integer` | YES | `NULL` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `flash_max_qty` | `integer` | YES | `NULL` | Data field storing flash max qty for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `flash_slots_remaining` | `integer` | YES | `NULL` | Data field storing flash slots remaining for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `flash_starts_at` | `timestamp with time zone` | YES | `NULL` | Data field storing flash starts at for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `flash_ends_at` | `timestamp with time zone` | YES | `NULL` | Data field storing flash ends at for rewards record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_rewards_active` ON (`hp_cost`)
- `idx_rewards_min_tier_id` ON (`min_tier_id`)

**Check Constraints:**
- `check_reward_stock`: `((stock_quantity IS NULL) OR (stock_quantity >= 0))`
- `chk_rewards_hp_cost_pos`: `(hp_cost > 0)`
- `rewards_hp_cost_check`: `(hp_cost > 0)`

**RLS Policies:**
- `rewards: admins all`
- `rewards: public read active`

---

### Table: `public.rider_profiles`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the rider_profiles record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `is_available` | `boolean` | NO | `false` | Data field storing is available for rider_profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `availability_updated_at` | `timestamp with time zone` | YES | `NULL` | Data field storing availability updated at for rider_profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `location_lat` | `double precision` | YES | `NULL` | Data field storing location lat for rider_profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `location_lng` | `double precision` | YES | `NULL` | Data field storing location lng for rider_profiles record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Unique Constraints:**
- `rider_profiles_user_id_key`: UNIQUE (`user_id`)

**RLS Policies:**
- `Admins manage all rider profiles`
- `Riders manage own profile`

---

### Table: `public.saved_for_later`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `menu_item_id` → `menu_items.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the saved_for_later record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `menu_item_id` | `uuid` | NO | `NULL` | Data field storing menu item id for saved_for_later record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `quantity` | `integer` | NO | `1` | Data field storing quantity for saved_for_later record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `notes` | `text` | YES | `NULL` | Data field storing notes for saved_for_later record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_saved_for_later_menu_item_id` ON (`menu_item_id`)
- `idx_saved_for_later_user` ON (`user_id`)

**Unique Constraints:**
- `saved_for_later_user_id_menu_item_id_key`: UNIQUE (`user_id, menu_item_id`)

**Check Constraints:**
- `saved_for_later_quantity_check`: `(quantity >= 1)`

**RLS Policies:**
- `Users manage own saved items`

---

### Table: `public.scheduled_notifications`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the scheduled_notifications record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `title` | `text` | NO | `NULL` | Data field storing title for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `body` | `text` | NO | `NULL` | Data field storing body for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `frequency` | `text` | NO | `NULL` | Data field storing frequency for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `send_time` | `text` | NO | `NULL` | Data field storing send time for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `target_segment` | `text` | NO | `'all'::text` | Data field storing target segment for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `last_sent_at` | `timestamp with time zone` | YES | `NULL` | Data field storing last sent at for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `next_send_at` | `timestamp with time zone` | YES | `NULL` | Data field storing next send at for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_by` | `uuid` | YES | `NULL` | Data field storing created by for scheduled_notifications record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_scheduled_notifications_created_by` ON (`created_by`)

**RLS Policies:**
- `Admins manage
scheduled_notifications`

---

### Table: `public.squad_members`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `order_id` → `orders.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the squad_members record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `order_id` | `uuid` | NO | `NULL` | Data field storing order id for squad_members record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `user_id` | `uuid` | YES | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `email` | `text` | NO | `NULL` | Contact email address used for receipts and notification delivery. | API Request / Profile | upon record creation | NULL if user registered via phone only | None |
| `hp_share` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `invite_sent` | `boolean` | NO | `false` | Data field storing invite sent for squad_members record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_registered` | `boolean` | NO | `false` | Data field storing is registered for squad_members record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `referral_attributed` | `boolean` | NO | `false` | Data field storing referral attributed for squad_members record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_squad_members_email` ON (`email`)
- `idx_squad_members_order` ON (`order_id`)
- `idx_squad_members_user_id` ON (`user_id`)

**Check Constraints:**
- `squad_members_hp_share_check`: `(hp_share >= 0)`

**RLS Policies:**
- `Admins manage squad members`
- `Users view own squad entries`

---

### Table: `public.storefront_sections`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the storefront_sections record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `key` | `text` | NO | `NULL` | Data field storing key for storefront_sections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `title` | `text` | YES | `NULL` | Data field storing title for storefront_sections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `section_type` | `text` | NO | `NULL` | Data field storing section type for storefront_sections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `content` | `jsonb` | NO | `NULL` | Data field storing content for storefront_sections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `sort_order` | `integer` | NO | `0` | Data field storing sort order for storefront_sections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for storefront_sections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `published_at` | `timestamp with time zone` | YES | `NULL` | Data field storing published at for storefront_sections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_by` | `uuid` | YES | `NULL` | Data field storing created by for storefront_sections record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_storefront_sections_created_by` ON (`created_by`)

**RLS Policies:**
- `storefront_sections: admins all`
- `storefront_sections: public read
active`

---

### Table: `public.system_settings`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `key`

- **Foreign Keys:** `updated_by` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `key` | `text` | NO | `NULL` | Data field storing key for system_settings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `value` | `jsonb` | NO | `'{}'::jsonb` | Data field storing value for system_settings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `description` | `text` | YES | `NULL` | Data field storing description for system_settings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_by` | `uuid` | YES | `NULL` | Data field storing updated by for system_settings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `is_public` | `boolean` | NO | `false` | Data field storing is public for system_settings record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_system_settings_public` ON (`is_public`)
- `idx_system_settings_updated_by` ON (`updated_by`)

**RLS Policies:**
- `Admins manage system_settings`
- `Anyone can read system_settings`
- `system_settings: admins all`
- `system_settings: public read
nonsensitive`

---

### Table: `public.user_addresses`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the user_addresses record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `label` | `text` | YES | `NULL` | Data field storing label for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `line1` | `text` | NO | `NULL` | Data field storing line1 for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `line2` | `text` | YES | `NULL` | Data field storing line2 for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hostel` | `text` | YES | `NULL` | Data field storing hostel for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `landmark` | `text` | YES | `NULL` | Data field storing landmark for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `city` | `text` | NO | `'Akure'::text` | Data field storing city for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `state` | `text` | NO | `'Ondo'::text` | Data field storing state for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `latitude` | `numeric(10,7)` | YES | `NULL` | Data field storing latitude for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `longitude` | `numeric(10,7)` | YES | `NULL` | Data field storing longitude for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_default` | `boolean` | NO | `false` | Data field storing is default for user_addresses record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_user_addresses_default` ON (`user_id`)
- `idx_user_addresses_user` ON (`user_id`)
- `uq_user_addresses_default` ON (`user_id`)

**RLS Policies:**
- `user_addresses: admins all`
- `user_addresses: users crud own`

---

### Table: `public.user_milestones`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `milestone_id` → `milestones.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the user_milestones record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `milestone_id` | `uuid` | NO | `NULL` | Data field storing milestone id for user_milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `completed_at` | `timestamp with time zone` | NO | `now()` | Data field storing completed at for user_milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_awarded` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `period_key` | `text` | YES | `NULL` | Data field storing period key for user_milestones record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_user_milestones_milestone_id` ON (`milestone_id`)
- `idx_user_milestones_user` ON (`user_id,
completed_at DESC`)
- `uq_user_milestones_lifetime` ON (`user_id,
milestone_id`)
- `uq_user_milestones_recurring` ON (`user_id,
milestone_id, period_key`)

**RLS Policies:**
- `Admins manage user_milestones`
- `Users view own milestones`

---

### Table: `public.user_tiers`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `previous_tier_id` → `hp_tiers.id`, `tier_id` → `hp_tiers.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `uuid_generate_v4()` | Primary key UUID unique identifier for the user_tiers record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `tier_id` | `uuid` | NO | `NULL` | Data field storing tier id for user_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `event` | `text` | NO | `NULL` | Data field storing event for user_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `hp_at_event` | `integer` | NO | `0` | Loyalty point value (Holy Points). | HP Service / RPC | upon record creation | NULL if HP bonus not earned | None |
| `previous_tier_id` | `uuid` | YES | `NULL` | Data field storing previous tier id for user_tiers record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_user_tiers_previous_tier_id` ON (`previous_tier_id`)
- `idx_user_tiers_tier_id` ON (`tier_id`)
- `idx_user_tiers_user` ON (`user_id, created_at
DESC`)

**Check Constraints:**
- `user_tiers_event_check`: `(event = ANY (ARRAY['upgrade'::text, 'downgrade'::text, 'maintain'::text, 'grace'::text, 'lost'::text]))`

**RLS Policies:**
- `user_tiers: admins all`
- `user_tiers: users read own`

---

### Table: `public.virtual_accounts`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the virtual_accounts record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `provider` | `text` | NO | `NULL` | Data field storing provider for virtual_accounts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `account_number` | `text` | NO | `NULL` | Data field storing account number for virtual_accounts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `account_name` | `text` | NO | `NULL` | Data field storing account name for virtual_accounts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `bank_name` | `text` | NO | `NULL` | Data field storing bank name for virtual_accounts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `provider_customer_id` | `text` | YES | `NULL` | Data field storing provider customer id for virtual_accounts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for virtual_accounts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `is_active` | `boolean` | NO | `true` | Data field storing is active for virtual_accounts record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `uq_virtual_accounts_active_user_provider` ON (`user_id,
provider`)

**Unique Constraints:**
- `virtual_accounts_provider_account_number_key`: UNIQUE (`provider, account_number`)
- `virtual_accounts_user_id_key`: UNIQUE (`user_id`)

**RLS Policies:**
- `virtual_accounts: admins all`
- `virtual_accounts: users read own`

---

### Table: `public.wallet_topups`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the wallet_topups record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `amount` | `numeric(14,2)` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `provider` | `text` | NO | `NULL` | Data field storing provider for wallet_topups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for wallet_topups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `callback_url` | `text` | YES | `NULL` | Data field storing callback url for wallet_topups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `provider_reference` | `text` | YES | `NULL` | Data field storing provider reference for wallet_topups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `confirmed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing confirmed at for wallet_topups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `failure_reason` | `text` | YES | `NULL` | Data field storing failure reason for wallet_topups record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_wallet_topups_status` ON (`user_id, status`)
- `idx_wallet_topups_user` ON (`user_id,
created_at DESC`)

**Check Constraints:**
- `chk_wallet_topups_amount_pos`: `(amount > (0)::numeric)`

**RLS Policies:**
- `wallet_topups: admins all`
- `wallet_topups: users insert own`
- `wallet_topups: users read own`

---

### Table: `public.wallet_transactions`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the wallet_transactions record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `type` | `text` | NO | `NULL` | Data field storing type for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `amount` | `numeric(14,2)` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `balance_after` | `numeric(14,2)` | NO | `NULL` | Data field storing balance after for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reason` | `text` | YES | `NULL` | Data field storing reason for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reference_type` | `text` | YES | `NULL` | Data field storing reference type for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reference_id` | `uuid` | YES | `NULL` | Data field storing reference id for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `provider` | `text` | YES | `NULL` | Data field storing provider for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `provider_reference` | `text` | YES | `NULL` | Data field storing provider reference for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `issued_by_admin_id` | `uuid` | YES | `NULL` | Data field storing issued by admin id for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` | Data field storing metadata for wallet_transactions record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_wallet_tx_issued_by_admin_id` ON (`issued_by_admin_id`)
- `idx_wallet_tx_reference` ON (`reference_type, reference_id`)
- `idx_wallet_tx_type` ON (`user_id,
type`)
- `idx_wallet_tx_user_created` ON (`user_id,
created_at DESC`)

**RLS Policies:**
- `wallet_transactions: admins all`
- `wallet_transactions: users read own`

---

### Table: `public.wallet_withdrawals`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the wallet_withdrawals record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `amount` | `numeric(12,2)` | NO | `NULL` | Monetary value stored in Naira (NGN). | API / Order Service | upon record creation | NULL if discount or fee not applicable | None |
| `bank_code` | `text` | NO | `NULL` | Data field storing bank code for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `account_number` | `text` | NO | `NULL` | Data field storing account number for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `account_name` | `text` | NO | `NULL` | Data field storing account name for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `narration` | `text` | YES | `NULL` | Data field storing narration for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reference` | `text` | NO | `NULL` | Data field storing reference for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'pending'::text` | Data field storing status for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `processed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing processed at for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `failure_reason` | `text` | YES | `NULL` | Data field storing failure reason for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `metadata` | `jsonb` | YES | `NULL` | Data field storing metadata for wallet_withdrawals record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Indexes:**
- `idx_wallet_withdrawals_user_id` ON (`user_id`)

**RLS Policies:**
- `Admins manage all withdrawals`
- `Users view own withdrawals`

---

### Table: `public.wallets`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `user_id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `user_id` | `uuid` | NO | `NULL` | Foreign key referencing profiles.id identifying the user account owner. | API / JWT Auth Context | upon record creation | NULL for unauthenticated guest orders | profiles.id |
| `balance` | `numeric(14,2)` | NO | `0` | Data field storing balance for wallets record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `currency` | `text` | NO | `'NGN'::text` | Data field storing currency for wallets record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `updated_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |

**Check Constraints:**
- `chk_wallets_balance_nonneg`: `(balance >= (0)::numeric)`
- `wallets_balance_check`: `(balance >= (0)::numeric)`

**RLS Policies:**
- `wallets: admins all`
- `wallets: users read own`

---

### Table: `public.webhook_events`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default | Business Meaning | Source of Truth | When Set | When NULL | Related Columns |
|-------------|-----------|----------|---------|------------------|-----------------|----------|-----------|-----------------|
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary key UUID unique identifier for the webhook_events record. | PostgreSQL gen_random_uuid() | upon record creation | never NULL | None |
| `event_type` | `text` | NO | `NULL` | Data field storing event type for webhook_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `provider` | `text` | YES | `NULL` | Data field storing provider for webhook_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `reference` | `text` | NO | `''::text` | Data field storing reference for webhook_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `payload` | `jsonb` | YES | `NULL` | Data field storing payload for webhook_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `status` | `text` | NO | `'processed'::text` | Data field storing status for webhook_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `error` | `text` | YES | `NULL` | Data field storing error for webhook_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |
| `created_at` | `timestamp with time zone` | NO | `now()` | Audit timestamp tracking creation or last modification time. | PostgreSQL now() | upon record creation | never NULL | None |
| `processed_at` | `timestamp with time zone` | YES | `NULL` | Data field storing processed at for webhook_events record. | API Endpoint | upon record creation | not applicable / NULL if omitted | None |

**Indexes:**
- `idx_webhook_events_provider_ref` ON (`provider,
reference`)
- `webhook_events_created_at_idx` ON (`created_at
DESC`)
- `webhook_events_event_type_idx` ON (`event_type`)
- `webhook_events_reference_idx` ON (`reference`)

**Unique Constraints:**
- `webhook_events_provider_event_type_reference_key`: UNIQUE (`provider, event_type, reference`)

**RLS Policies:**
- `Admins manage webhook_events`

---

## SECTION 6: RPC FUNCTIONS & TRANSACTION GUARANTEES

All critical mutations execute inside atomic PostgreSQL transactions via RPCs:


### `hg_create_order_atomic`

- **Parameters:** `p_user_id` (uuid), `p_items` (jsonb), `p_payment_method` (text), `p_delivery_type` (text), `p_delivery_location_id` (uuid), `p_promo_code` (text), `p_use_hp` (boolean), `p_campus_id` (uuid), `p_idempotency_key` (text)

- **Return Type:** `jsonb` containing created order object or error description

- **Called From:** ``app/services/order_service.py` (`create_order`)`

- **Security & Grants:** ``service_role` and `authenticated``

- **Logic Summary:** Atomically validates kitchen capacity, item daily limits, promo code validity, applies HP discounts, reserves inventory, debits wallet balance if applicable, creates order and order items, and returns the resulting order record.


### `credit_wallet_atomic`

- **Parameters:** `p_user_id` (uuid), `p_amount` (numeric), `p_source` (text), `p_reference` (text), `p_description` (text)

- **Return Type:** `jsonb` with `success`, `new_balance`, `transaction_id`

- **Called From:** ``app/services/wallet_service.py` (`credit_wallet`)`

- **Security & Grants:** ``service_role``

- **Logic Summary:** Locks profile row (`FOR UPDATE`), increases `wallet_balance`, records a wallet transaction in `wallet_transactions`, and checks top-up thresholds to award loyalty points if applicable.


### `debit_wallet_atomic`

- **Parameters:** `p_user_id` (uuid), `p_amount` (numeric), `p_reference` (text), `p_description` (text)

- **Return Type:** `jsonb` with `success`, `new_balance`, `transaction_id`

- **Called From:** ``app/services/wallet_service.py` (`debit_wallet`)`

- **Security & Grants:** ``service_role``

- **Logic Summary:** Locks profile row (`FOR UPDATE`), checks sufficient balance (`wallet_balance >= p_amount`), decrements balance, and records transaction in `wallet_transactions`.


### `record_hp_transaction_atomic`

- **Parameters:** `p_user_id` (uuid), `p_amount` (integer), `p_type` (text: earn|spend|expire|adjustment), `p_status` (text: active|pending), `p_source` (text), `p_reference_type` (text), `p_reference_id` (uuid), `p_issued_by_admin_id` (uuid), `p_notes` (text), `p_campus_id` (uuid)

- **Return Type:** `jsonb` with `success`, `new_balance`, `transaction_id`

- **Called From:** ``app/services/hp_service.py` (`record_hp_transaction`)`

- **Security & Grants:** ``service_role``

- **Logic Summary:** Enforces transaction idempotency via unique index, updates `profiles.hp_balance`, recalculates user tier status, and records transaction entry.


### `unlock_pending_hp_fifo_atomic`

- **Parameters:** `p_user_id` (uuid), `p_spend_amount_naira` (numeric)

- **Return Type:** `jsonb` with `unlocked_amount`, `remaining_pending_balance`

- **Called From:** ``app/services/hp_service.py` (`unlock_pending_hp_fifo`)`

- **Security & Grants:** ``service_role``

- **Logic Summary:** Unlocks pending HP entries chronologically (FIFO order) based on naira spend conversion rate until cap or spend value is reached.


### `hg_redeem_flash_reward_atomic`

- **Parameters:** `p_user_id` (uuid), `p_reward_id` (uuid)

- **Return Type:** `jsonb` with `success`, `redemption_id`, `remaining_slots`, `have`

- **Called From:** ``app/services/hp_service.py` (`redeem_flash_reward`)`

- **Security & Grants:** ``service_role``

- **Logic Summary:** Validates active flash sale window, locks remaining quantity slots, verifies active HP balance, deducts HP cost, decrements remaining slots, and records reward redemption.


### `try_acquire_cron_lock`

- **Parameters:** `p_job_name` (text)

- **Return Type:** `boolean` (true if lock acquired, false if already running)

- **Called From:** ``app/tasks/scheduled.py``

- **Security & Grants:** ``service_role``

- **Logic Summary:** Checks `cron_locks` table for job lock or expired timeout; if free, sets lock timestamp and returns true to prevent concurrent task execution across Celery workers.


### `release_cron_lock`

- **Parameters:** `p_job_name` (text)

- **Return Type:** `boolean`

- **Called From:** ``app/tasks/scheduled.py``

- **Security & Grants:** ``service_role``

- **Logic Summary:** Clears the job lock entry from `cron_locks` table upon scheduled job completion.


### `hg_purchase_marketplace_item`

- **Parameters:** `p_user_id` (uuid), `p_listing_id` (uuid), `p_payment_method` (text), `p_use_hp` (boolean)

- **Return Type:** `jsonb` with `purchase_id`, `cash_amount`, `hp_used`

- **Called From:** ``app/routes/marketplace.py` (`purchase_listing`)`

- **Security & Grants:** ``service_role` and `authenticated``

- **Logic Summary:** Validates marketplace listing stock, applies HP discount if requested, debits wallet balance or initializes card payment, records purchase transaction, and updates listing quantity.


### `claim_guest_order`

- **Parameters:** `p_order_id` (uuid), `p_user_id` (uuid)

- **Return Type:** `jsonb` with `success`, `message`

- **Called From:** ``app/routes/orders.py` (`claim_guest_order`)`

- **Security & Grants:** ``service_role` and `authenticated``

- **Logic Summary:** Links an unassigned guest order to an authenticated user's profile matching their email or phone number and credits earned HP.


### `hg_anonymize_user`

- **Parameters:** `p_user_id` (uuid)

- **Return Type:** `jsonb` with `success`

- **Called From:** ``app/routes/auth.py` (`delete_account`)`

- **Security & Grants:** ``service_role` and `authenticated``

- **Logic Summary:** Anonymizes personal identification fields in `profiles`, `orders`, and related tables upon user account deletion request.


---
## SECTION 7: BACKGROUND JOBS & SCHEDULED TASKS

All background tasks run via Celery Beat scheduler in West Africa Time (`Africa/Lagos` = UTC+1).


### `reset_monthly_leaderboard`

- **Schedule:** `crontab(hour=0, minute=1, day_of_month=1)` (1st of each month at 00:01 WAT)

- **What It Does:** Aggregates HP earned in previous calendar month per user, awards leaderboard prizes (exclusive spins, free side credits), inducts top rankers into Hall of Fame, and archives snapshot to `leaderboard_snapshots`.

- **Database Tables:** `hp_transactions`, `leaderboard_snapshots`, `exclusive_spins`, `free_side_credits`, `hall_of_fame_inductees`

- **Campus Loop:** YES — loops through all active campuses


### `recalculate_120day_hp`

- **Schedule:** `crontab(hour=2, minute=0)` (Daily at 02:00 WAT)

- **What It Does:** Recalculates rolling 120-day active HP balance for tier determination across all profiles.

- **Database Tables:** `profiles`, `hp_transactions`

- **Campus Loop:** NO — global user scan


### `tier_grace_period_check`

- **Schedule:** `crontab(hour=3, minute=0)` (Daily at 03:00 WAT)

- **What It Does:** Checks users whose tier qualification has expired; applies tier downgrades if grace period has elapsed without meeting criteria.

- **Database Tables:** `profiles`

- **Campus Loop:** NO — global profile scan


### `birthday_hp_awards`

- **Schedule:** `crontab(hour=8, minute=0)` (Daily at 08:00 WAT)

- **What It Does:** Finds users whose birthday is today (`date_of_birth`), awards `BIRTHDAY_HP` bonus points, and sends birthday notification.

- **Database Tables:** `profiles`, `hp_transactions`, `notifications`

- **Campus Loop:** NO — global user scan


### `scan_abandoned_carts`

- **Schedule:** `crontab(minute='*/30')` (Every 30 minutes)

- **What It Does:** Scans server-side carts idle over 60 minutes, records abandoned cart entries, and dispatches recovery nudges.

- **Database Tables:** `cart_items`, `abandoned_carts`, `notifications`

- **Campus Loop:** NO — global scan


### `monthly_birthday_report`

- **Schedule:** `crontab(hour=7, minute=0, day_of_month=1)` (1st of month at 07:00 WAT)

- **What It Does:** Generates administrative summary report of upcoming user birthdays for the current month.

- **Database Tables:** `profiles`

- **Campus Loop:** YES — per campus


### `process_scheduled_orders`

- **Schedule:** `crontab(minute='*/5')` (Every 5 minutes)

- **What It Does:** Checks `order_locks` and scheduled orders due for fulfillment window, transitions orders to `received` status for kitchen queue.

- **Database Tables:** `order_locks`, `orders`

- **Campus Loop:** YES — per campus


### `win_back_notifications`

- **Schedule:** `crontab(hour=10, minute=0)` (Daily at 10:00 WAT)

- **What It Does:** Identifies users inactive for >30 days and dispatches re-engagement push notifications.

- **Database Tables:** `profiles`, `orders`, `notifications`

- **Campus Loop:** NO — global scan


### `hp_decay_check`

- **Schedule:** `crontab(hour=5, minute=0)` (Daily at 05:00 WAT)

- **What It Does:** Enforces HP decay for accounts inactive beyond `HP_EXPIRY_INACTIVITY_DAYS` (90 days). Deducts 10% monthly decay.

- **Database Tables:** `profiles`, `hp_transactions`

- **Campus Loop:** NO — global user scan


### `check_order_locks`

- **Schedule:** `crontab(hour=9, minute=0)` (Daily at 09:00 WAT)

- **What It Does:** Reviews active order locks, updates lock availability status, and releases expired lock reservations.

- **Database Tables:** `order_locks`

- **Campus Loop:** YES — per campus


### `reset_monthly_hp_tracker`

- **Schedule:** `crontab(hour=0, minute=5, day_of_month=1)` (1st of month at 00:05 WAT)

- **What It Does:** Resets `monthly_hp_earned` counter on user profiles for the new calendar month.

- **Database Tables:** `profiles`

- **Campus Loop:** NO — global user update


### `membership_anniversary_awards`

- **Schedule:** `crontab(hour=6, minute=0)` (Daily at 06:00 WAT)

- **What It Does:** Identifies users celebrating 1-year or multi-year account registration anniversaries and awards anniversary HP bonuses.

- **Database Tables:** `profiles`, `hp_transactions`, `notifications`

- **Campus Loop:** NO — global user scan


### `send_scheduled_notifications`

- **Schedule:** `crontab(minute='*/15')` (Every 15 minutes)

- **What It Does:** Dispatches pending blasts and scheduled notifications whose `scheduled_at` timestamp has arrived.

- **Database Tables:** `notification_blasts`, `notifications`

- **Campus Loop:** NO — queue scan


### `check_post_delivery_nudges`

- **Schedule:** `crontab(minute='*/30')` (Every 30 minutes)

- **What It Does:** Sends review prompts and satisfaction survey notifications for orders delivered within the last 2 hours.

- **Database Tables:** `orders`, `notifications`

- **Campus Loop:** NO — recent order scan


---
## SECTION 8: EXTERNAL INTEGRATIONS

### 1. Paystack Payment Gateway

- **Purpose**: Online card checkout, split payments, and dedicated Wema Wema virtual bank accounts.

- **Endpoints Handled**: `POST /api/wallet/fund/card`, `POST /api/wallet/fund/bank`, `POST /api/webhooks/paystack`

- **Webhook Security**: Verifies HMAC SHA512 signature (`X-Paystack-Signature` header against `PAYSTACK_WEBHOOK_SECRET`).

- **Idempotency**: Webhook events check `payment_webhooks` table on `(provider='paystack', event_type, reference)` UNIQUE constraint.


### 2. Cloudinary Image Storage

- **Purpose**: Direct client-side image uploads for user profile avatars, storefront banners, review images, and reward images.

- **Endpoint**: `POST /api/upload/signature`

- **Mechanism**: Backend computes SHA-1 HMAC upload signature using `CLOUDINARY_API_SECRET`, returning parameters so clients upload directly to Cloudinary CDN.


### 3. OneSignal Push & Email

- **Purpose**: Mobile push notifications and transactional email dispatch.

- **Service File**: `app/services/notification_service.py`

- **Throttling & Preferences**: Enforces notification frequency caps and respects user channel preferences in `notification_preferences`.


### 4. Resend Transactional Email

- **Purpose**: Direct email delivery fallback for order receipts, password resets, and account verification.

- **Utils File**: `app/utils/email.py`


### 5. Redis Service

- **Purpose**: Celery message broker, task result storage, distributed cron lock coordination, and API rate limiting.

- **Environment Config**: `REDIS_URL` (default `redis://localhost:6379/0`).


---
## SECTION 9: STATE PERSISTENCE & CACHING

- **JWT Sessions**: Access token TTL = `3600`s (1 hour). Refresh token TTL = `2592000`s (30 days). Silent rotation window = `5` minutes (`JWT_REFRESH_WINDOW_MINUTES`).

- **Server Carts**: Server-side `cart_items` persist until cleared upon successful order placement (`create_order`). Carts idle >60 minutes are scanned into `abandoned_carts`.

- **Order Archiving**: Orders persist indefinitely for financial auditability. Closed orders remain queryable by customer.

- **HP Expiry & Decay**: Inactivity beyond `HP_EXPIRY_INACTIVITY_DAYS` (90 days) triggers 10% monthly decay check (`hp_decay_check`).

- **Redis Cache Keys & TTLs**:

  - Task result backend: `3600`s TTL.

  - Cron job distributed lock (`try_acquire_cron_lock`): `600`s – `1800`s TTL.

  - IP rate limiting bucket: `60`s – `3600`s window TTL.


---
## SECTION 10: SQUAD ORDER LOGIC

- **Squad Creation**: Initiated during order checkout by adding squad member emails (`POST /api/orders/<order_id>/squad-members`).

- **Member Limits**: Min items = 3 (`SQUAD_ORDER_MIN_ITEMS`), Max items = 20 (`SQUAD_ORDER_MAX_ITEMS`).

- **HP Splitting**: Earned HP on delivered squad order is split evenly among registered members + organizer via `award_active_hp` RPC (`share = total_hp // len(registered_ids)`).

- **Discounts**: Squad subtotal discount (5%) and squad delivery discount (50%) applied when item threshold met.

- **Referral Attribution**: If a referee joins a squad order, referrer earns referral HP bonus upon referee's first delivered order.

- **Payment Failures**: Organizer pays total amount upfront or via split payment; squad members receive HP bonus post-delivery.


---
## SECTION 11: RIDER ASSIGNMENT LOGIC

- **Batching**: Orders grouped by gate/zone into delivery batches (`delivery_batches`). Max capacity = 5 orders per batch.

- **Rider Selection**: Active available riders (`is_available = true` on `rider_profiles`) assigned to batch. Stops ordered via nearest-neighbour sequencing starting from batch gate position (`find_nearest_gate`).

- **Batch Progression**: `assigned` → `out_for_delivery` (rider picks up batch) → `delivered` or `delivery_attempted`.


---
## SECTION 12: FEATURE FLAGS & CAMPAIGN LOGIC

- **Feature Flags**: Managed in `feature_flags` table (e.g. `squad_order_enabled`, `whatsapp_support_enabled`). Can be global or campus-scoped.

- **Promo Codes**: Validated against `min_order_amount`, `starts_at`, `ends_at`, `max_uses`, `max_uses_per_user`, and campus scope.

- **Referrals**: `REFERRAL_HP` awarded to referrer when referee completes first order (`complete_referral`).

- **Rewards & Flash Sales**: 50% discount during active flash window (`flash_hp_cost = reward.hp_cost // 2`). Quantity slots locked atomically via `hg_redeem_flash_reward_atomic` RPC.

- **First-Order Gift**: Configured via `first_order_gift_enabled` setting; awards gift item on user's first order.

- **Birthday HP**: `BIRTHDAY_HP` (150 HP) awarded automatically on user's birthday by `birthday_hp_awards` task.

- **Graduation Bonus**: Awarded to graduating students (level >= `graduation_min_level`, default 400).


---
## SECTION 13: COMPLETE WEBHOOK PAYLOADS

### 1. Paystack Webhook (`POST /api/webhooks/paystack`)

- **Verification Header**: `X-Paystack-Signature` verified against HMAC SHA512 hash of raw body using `PAYSTACK_WEBHOOK_SECRET`.

- **Idempotency**: Checked against `payment_webhooks` table on `(provider='paystack', event_type, reference)` UNIQUE constraint.

- **Sample `charge.success` Payload**:

```json
{
    "event": "charge.success",
    "data": {
        "id": 30092831,
        "domain": "test",
        "status": "success",
        "reference": "HG-WAL-172839210-9A8B",
        "amount": 500000,
        "gateway_response": "Successful",
        "paid_at": "2026-03-31T12:00:00.000Z",
        "channel": "card",
        "currency": "NGN",
        "ip_address": "102.89.23.1",
        "metadata": {
            "user_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "type": "wallet_funding"
        },
        "customer": {
            "id": 128391,
            "first_name": "John",
            "last_name": "Doe",
            "email": "student@futa.edu.ng",
            "phone": "08012345678"
        }
    }
}
```

- **Sample `charge.failed` Payload**:

```json
{
    "event": "charge.failed",
    "data": {
        "id": 30092832,
        "domain": "test",
        "status": "failed",
        "reference": "HG-WAL-172839210-FAIL",
        "amount": 500000,
        "gateway_response": "Declined - Insufficient Funds",
        "paid_at": "2026-03-31T12:01:00.000Z",
        "channel": "card",
        "currency": "NGN"
    }
}
```

- **Sample `transfer.success` Payload**:

```json
{
    "event": "transfer.success",
    "data": {
        "amount": 100000,
        "currency": "NGN",
        "domain": "test",
        "failures": null,
        "id": 102938,
        "reason": "Wallet refund",
        "reference": "HG-REF-10293",
        "source": "balance",
        "status": "success",
        "transfer_code": "TRF_10293"
    }
}
```

### 2. Flutterwave Webhook (`POST /api/webhooks/flutterwave`)

- **Verification Header**: `verif-hash` header matched against `FLUTTERWAVE_SECRET_HASH`.

- **Sample `charge.completed` Payload**:

```json
{
    "event": "charge.completed",
    "data": {
        "id": 123456,
        "tx_ref": "HG-FLW-102938120",
        "flw_ref": "FLW-MOCK-192830",
        "amount": 2500,
        "currency": "NGN",
        "status": "successful",
        "customer": {
            "email": "guest@example.com",
            "name": "Guest Customer"
        }
    }
}
```

---
## SECTION 14: SYSTEM SETTINGS REFERENCE

The `system_settings` table stores runtime configuration key-values. Settings can be global (`campus_id IS NULL`) or overridden per-campus (`campus_id = <uuid>`).


| Setting Key | Default Value | Purpose | Consuming Files |

|-------------|---------------|---------|-----------------|

| `hp_multiplier` | `1` | Active loyalty points earn multiplier | `app/services/hp_service.py` |

| `daily_checkin_hp` | `10` | HP awarded for daily check-in | `app/routes/daily_checkin.py` |

| `free_side_options` | `["Coleslaw", "Extra Sauce", "Soft Drink"]` | Side credit choices | `app/routes/free_sides.py` |

| `first_order_gift_enabled` | `true` | Welcome gift toggle | `app/services/gift_service.py` |

| `monthly_pending_cap` | `1000` | Monthly cap on pending HP unlock | `app/services/streak_service.py` |

| `graduation_min_level` | `400` | Minimum academic level for graduation eligibility | `app/routes/graduation.py` |

| `whatsapp_support_number` | `"2348000000000"` | Support contact number | `app/routes/storefront.py` |

| `whatsapp_support_enabled` | `true` | Toggle support button in app | `app/routes/storefront.py` |
