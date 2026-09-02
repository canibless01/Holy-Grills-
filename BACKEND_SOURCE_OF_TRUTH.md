# BACKEND SOURCE OF TRUTH — HOLY GRILLS PLATFORM REST API & ARCHITECTURE

Exhaustive, authoritative reference document covering all 311 REST API endpoints, 99 public database tables, PostgreSQL RPC functions, JWT auth & role security, Celery background tasks, external integrations, and system configuration settings.

## SYSTEM ARCHITECTURE OVERVIEW

- **Framework**: Flask 3.1.3 (Python 3.12)

- **Database**: Supabase PostgreSQL REST API (`postgrest`) with Service-Role and Anon access

- **Authentication**: Supabase JWT Auth with silent token rotation and profile role checks

- **Payment Processing**: Paystack API with HMAC Webhook verification and virtual accounts

- **Push & Email Notifications**: OneSignal API & Resend email integration

- **Background Jobs**: Celery 5.4.0 with Redis 5.2.1 broker & result backend

- **System Settings**: Dynamic system-wide and campus-scoped key-value configuration (`system_settings`)


---
## SECTION 1: API ENDPOINT INVENTORY

Total documented REST API endpoints: **311**


### `GET /api/academic-levels`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/academic_levels.py` (`list_academic_levels`)

**Summary:** List active academic levels in sort order.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/academic-levels/<level_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/academic_levels.py` (`get_academic_level`)

**Summary:** Get a single academic level by ID (active only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Academic level not found"`

---

### `GET /api/admin/abandoned-carts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`abandoned_carts`)

**Summary:** List abandoned carts for recovery (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `abandoned_carts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/abandoned-carts/<cart_id>/nudge`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`nudge_cart`)

**Summary:** Manually trigger recovery nudge for an abandoned cart (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `abandoned_carts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/academic-levels`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_list_academic_levels`)

**Summary:** List all academic levels including inactive ones (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `is_active`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/academic-levels`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_create_academic_level`)

**Summary:** Create a new academic level (admin only).


**Request Specification:**

```json
{
    "is_active": "any",
    "name": "any",
    "sort_order": "any",
    "value": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/admin/academic-levels/<level_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_deactivate_academic_level`)

**Summary:** Soft-delete (deactivate) an academic level (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Academic level not found"`

---

### `PATCH /api/admin/academic-levels/<level_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_update_academic_level`)

**Summary:** Update an academic level (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Academic level not found"`
- `"No valid fields to update"`

---

### `POST /api/admin/academic-levels/<level_id>/restore`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/academic_levels.py` (`admin_restore_academic_level`)

**Summary:** Reactivate a previously deactivated academic level (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Academic level not found"`

---

### `GET /api/admin/audit-log`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`audit_log`)

**Summary:** View admin audit log with pagination support (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `admin_audit_logs`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/campuses`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_campuses`)

**Summary:** List all campuses (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `campuses`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/cron/<job_name>`

**Authentication:** `super_admin` (JWT required)

**Source File:** `app/routes/admin.py` (`run_cron_job`)

**Summary:** Manually trigger a scheduled cron job (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/cron/status`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`cron_status`)

**Summary:** Show last run time, result, and status of every cron job (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `admin_audit_logs`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/delivery-batches`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_batches`)

**Summary:** List delivery batches with their assigned rider and order count (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status, window_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/delivery-batches`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`create_batch`)

**Summary:** Create a delivery batch and assign a rider (admin only).


**Request Specification:**

```json
{
    "order_ids": "any",
    "rider_id": "any",
    "window_id": "any",
    "zone": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, delivery_windows, orders, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Delivery window belongs to a different campus"`
- `"Rider account is deactivated"`
- `"Rider user profile not found"`

---

### `GET /api/admin/delivery-batches/<batch_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`get_batch`)

**Summary:** Get a delivery batch with all assigned orders (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, gates, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/admin/delivery-batches/<batch_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`cancel_batch`)

**Summary:** Cancel a delivery batch and unassign its orders (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/delivery-batches/<batch_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`update_batch`)

**Summary:** Update a delivery batch's status (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/delivery-batches/<batch_id>/orders`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_batch_orders`)

**Summary:** List all orders assigned to a delivery batch (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/delivery-windows`

**Authentication:** `admin, kitchen` (JWT required)

**Source File:** `app/routes/admin.py` (`list_windows`)

**Summary:** List delivery windows (admin/kitchen). Scoped by campus for kitchen users.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/delivery-windows`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`create_window`)

**Summary:** Create a delivery window (admin only).


**Request Specification:**

```json
{
    "campus_id": "any",
    "capacity": "any",
    "ends_at": "any",
    "is_active": "any",
    "label": "any",
    "starts_at": "any",
    "zone_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"capacity must be a positive integer"`
- `"is_active must be a boolean"`
- `"label must be a non-empty string"`

---

### `POST /api/admin/delivery-windows/<window_id>/close`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`close_window`)

**Summary:** Close a delivery window (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/delivery-windows/<window_id>/reopen`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`reopen_window`)

**Summary:** Reopen a previously closed delivery window (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/departments`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_list_departments`)

**Summary:** List all departments including inactive ones (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `faculty, is_active`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/departments`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_create_department`)

**Summary:** Create a new department (admin only).


**Request Specification:**

```json
{
    "faculty": "any",
    "is_active": "any",
    "name": "any",
    "slug": "any",
    "sort_order": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/admin/departments/<dept_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_deactivate_department`)

**Summary:** Soft-delete (deactivate) a department (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Department not found"`

---

### `PATCH /api/admin/departments/<dept_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_update_department`)

**Summary:** Update a department (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Department not found"`
- `"No valid fields to update"`

---

### `POST /api/admin/departments/<dept_id>/restore`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/departments.py` (`admin_restore_department`)

**Summary:** Reactivate a previously deactivated department (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Department not found"`

---

### `GET /api/admin/exclusive-spin-prizes`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`list_exclusive_spin_prizes`)

**Summary:** List exclusive-spin physical prize fulfilment records.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `exclusive_spin_fulfillments, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/exclusive-spin-prizes/<record_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`fulfil_exclusive_spin_prize`)

**Summary:** Mark an exclusive-spin physical prize as fulfilled.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `exclusive_spin_fulfillments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Prize record not found"`

---

### `GET /api/admin/feature-flags`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`list_feature_flags`)

**Summary:** List all feature flags.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `feature_flags`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/feature-flags`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`create_feature_flag`)

**Summary:** Create a disabled feature flag.


**Request Specification:**

```json
{
    "campus_id": "any",
    "description": "any",
    "feature_name": "any",
    "is_active": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `feature_flags`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Feature flag already exists"`

---

### `GET /api/admin/feature-flags/<flag_name>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`get_feature_flag`)

**Summary:** Get a specific feature flag.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `feature_flags`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/feature-flags/<flag_name>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`update_feature_flag`)

**Summary:** Create or update a feature flag (upsert).


**Request Specification:**

```json
{
    "campus_id": "any",
    "description": "any",
    "is_active": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `feature_flags`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/first-order-gifts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`list_first_order_gifts`)

**Summary:** Admin: list first-order gifts with user details.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `first_order_gifts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/first-order-gifts/<gift_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`update_first_order_gift`)

**Summary:** Admin: update a first-order gift status.


**Request Specification:**

```json
{
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `first_order_gifts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/hall-of-fame-rewards`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`list_hof_rewards`)

**Summary:** List Hall of Fame box reward records.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_rewards, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/hall-of-fame-rewards/<record_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`fulfil_hof_reward`)

**Summary:** Update a Hall of Fame reward record status.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/hp/bulk-grant`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`bulk_grant_hp`)

**Summary:** Bulk-grant HP to a segment of users (by tier, last-order date, etc.) — for promotions.


**Request Specification:**

```json
{
    "amount": "any",
    "campus_id": "any",
    "dry_run": "any",
    "last_order_after": "any",
    "last_order_before": "any",
    "reason": "any",
    "tier_slug": "any",
    "user_ids": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers, orders, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/hp/report`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`hp_report`)

**Summary:** HP loyalty program health report — totals, tier distribution, top earners.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/leaderboard-prizes`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`list_leaderboard_prizes`)

**Summary:** List leaderboard prize fulfilment records.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `month, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `leaderboard_reward_fulfillments, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/leaderboard-prizes/<record_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_feature_flags.py` (`fulfil_leaderboard_prize`)

**Summary:** Mark a leaderboard prize as fulfilled.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `leaderboard_reward_fulfillments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/orders`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_all_orders`)

**Summary:** List all orders across all users (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, limit, offset, payment_method, status, to_date, user_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/promo-codes`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_promos`)

**Summary:** List all promo codes (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_codes`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/promo-codes`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`create_promo`)

**Summary:** Create a promo code (admin only).


**Request Specification:**

```json
{
    "campus_id": "any",
    "code": "any",
    "created_by": "any",
    "is_active": "any",
    "used_count": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_codes`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/promo-codes/<promo_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`update_promo`)

**Summary:** Update or deactivate a promo code (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_codes`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"discount_value must not exceed 100 for a percentage discount"`
- `"is_active must be a boolean"`

---

### `GET /api/admin/promo-codes/<promo_id>/uses`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`promo_uses`)

**Summary:** Get redemption stats and usage history for a promo code (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_code_uses, promo_codes`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/reviews`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_reviews`)

**Summary:** List all order reviews with filters


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `kitchen_rating, limit, offset, rating, rider_rating`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_reviews, orders, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"kitchen_rating must be an integer between 1 and 5"`
- `"limit must be a non-negative integer"`
- `"limit must be between 0 and 200"`
- `"offset must be >= 0"`
- `"offset must be a non-negative integer"`
- `"rating must be an integer between 1 and 5"`
- `"rider_rating must be an integer between 1 and 5"`

---

### `GET /api/admin/settings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`list_settings`)

**Summary:** Admin: list all system settings.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `system_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/settings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`create_setting`)


**Request Specification:**

```json
{
    "campus_id": "any",
    "description": "any",
    "key": "any",
    "value": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `system_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/settings/<key>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin_gifts.py` (`update_setting`)


**Request Specification:**

```json
{
    "campus_id": "any",
    "description": "any",
    "value": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `system_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"hp_multiplier must be 0.5, 1.0, or 2.0"`

---

### `GET /api/admin/users`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`list_users`)

**Summary:** List all users with HP balance and tier info.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, offset, q, role`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/users/<user_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`get_user`)

**Summary:** Get full user profile with order history and HP ledger.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles, wallets`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"You don"`

---

### `POST /api/admin/users/<user_id>/activate`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`activate_user`)

**Summary:** Reactivate a previously deactivated user account (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/admin/users/<user_id>/deactivate`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`deactivate_user`)

**Summary:** Deactivate a user account (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Only super_admin users can deactivate a super_admin account"`
- `"You cannot deactivate your own account"`

---

### `GET /api/admin/users/<user_id>/hp`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`user_hp_history`)

**Summary:** Get HP transaction history for a specific user (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/admin/users/<user_id>/orders`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`user_order_history`)

**Summary:** Get complete order history for a specific user (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/admin/users/<user_id>/role`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`change_user_role`)

**Summary:** Change a user's role (admin only). Use with caution.


**Request Specification:**

```json
{
    "role": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Cannot change your own role"`
- `"Only super_admin can assign super_admin role"`

---

### `GET /api/admin/users/<user_id>/wallet`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/admin.py` (`user_wallet_history`)

**Summary:** Get wallet transaction history for a specific user (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, wallets`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/abandoned-carts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`abandoned_carts_analytics`)

**Summary:** Abandoned cart analytics — total, recovered, and unrecovered counts.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `abandoned_carts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/dashboard`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`dashboard_summary`)

**Summary:** Live admin dashboard — today's order pipeline, delivery batch status, revenue snapshot.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, delivery_windows, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/export`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`export_csv`)

**Summary:** Export analytics data as CSV (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, limit, to_date, type`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions, orders, profiles, wallet_transactions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/gifts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`gifts_analytics`)

**Summary:** Gift analytics — first-order gift status breakdown.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `first_order_gifts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/hp`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`hp_analytics`)

**Summary:** HP ecosystem analytics — issued vs redeemed, tier distribution.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers, hp_transactions, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/items`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`items_analytics`)

**Summary:** Item-level analytics — quantity sold and revenue per menu item over a date range.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, limit, to_date`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_items, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/marketplace`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`marketplace_analytics`)

**Summary:** Marketplace analytics — purchases, code inventory status.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings, marketplace_purchases`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/orders`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`orders_analytics`)

**Summary:** Order flow analytics — volume by window, zone coverage, status funnel, peak hours.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, delivery_windows, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/referrals`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`referral_analytics`)

**Summary:** Referral funnel analytics.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `referrals`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/retention`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`retention_analytics`)

**Summary:** Cohort retention — percentage of users who placed a second order,


**Request Specification:**

```json
{
    "retained": "any",
    "total": "any"
}
```

- **Query Parameters:** `campus_id, weeks`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/sales`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`sales_analytics`)

**Summary:** Sales analytics — revenue, order volume, AOV by date range.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/analytics/users`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/analytics.py` (`users_analytics`)

**Summary:** User analytics — DAU, MAU, and breakdown by tier.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers, orders, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/auth/account`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`delete_account`)

**Summary:** Delete the authenticated user's account (NDPR/GDPR self-deletion).


**Request Specification:**

```json
{
    "password": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/auth/addresses`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`list_addresses`)

**Summary:** List all saved delivery addresses for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `user_addresses`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/addresses`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`add_address`)

**Summary:** Save a new delivery address for the authenticated user.


**Request Specification:**

```json
{
    "address_line": "any",
    "city": "any",
    "hostel": "any",
    "is_default": "any",
    "label": "any",
    "landmark": "any",
    "latitude": "any",
    "line1": "any",
    "line2": "any",
    "longitude": "any",
    "state": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `user_addresses`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/auth/addresses/<address_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`delete_address`)

**Summary:** Delete a saved delivery address.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `user_addresses`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/auth/addresses/<address_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`update_address`)

**Summary:** Update a saved delivery address.


**Request Specification:**

```json
{
    "address_line": "any",
    "is_default": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `user_addresses`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/change-password`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`change_password`)

**Summary:** Change password for the authenticated user.


**Request Specification:**

```json
{
    "current_password": "any",
    "new_password": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/device-token`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`register_device_token`)

**Summary:** Register or update a push-notification device token for the authenticated user.


**Request Specification:**

```json
{
    "device_model": "any",
    "platform": "any",
    "token": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `device_tokens`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/login`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`login`)

**Summary:** Login with email and password.


**Request Specification:**

```json
{
    "email": "any",
    "password": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/logout`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`logout`)

**Summary:** Logout and invalidate session.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/logout-all-devices`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`logout_all_devices`)

**Summary:** Revoke all sessions and device tokens for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/auth/me`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`me`)

**Summary:** Get authenticated user's full profile including HP balance, tier, and wallet.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/auth/profile`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`update_profile`)

**Summary:** Update user profile fields.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/profile/photo`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`update_profile_photo`)

**Summary:** Update user profile photo with Cloudinary URL.


**Request Specification:**

```json
{
    "photo_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"photo_url is required"`

---

### `POST /api/auth/refresh`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`refresh`)

**Summary:** Silently rotate the access token when it is within the expiry window.


**Request Specification:**

```json
{
    "access_token": "any",
    "refresh_token": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/register`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`register`)

**Summary:** Register a new student account.


**Request Specification:**

```json
{
    "academic_level": "any",
    "campus_id": "any",
    "date_of_birth": "any",
    "department": "any",
    "email": "any",
    "full_name": "any",
    "password": "any",
    "phone": "any",
    "referred_by_code": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `campuses`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/reset-password`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`reset_password`)

**Summary:** Request password reset email.


**Request Specification:**

```json
{
    "email": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/auth/streak`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/auth.py` (`get_login_streak`)

**Summary:** Get the authenticated user's current login streak.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/auth/verify-email`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/auth.py` (`verify_email`)

**Summary:** Resend the email verification link to an unconfirmed address.


**Request Specification:**

```json
{
    "email": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/cart`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`get_cart`)

**Summary:** Get the authenticated user's cart with current item prices.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/cart`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`add_to_cart`)

**Summary:** Add an item to the cart. If the item already exists, quantity is incremented.


**Request Specification:**

```json
{
    "menu_item_id": "any",
    "notes": "any",
    "quantity": "any",
    "selected_addons": "any",
    "selected_variations": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items, menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Menu item not found"`

---

### `DELETE /api/cart`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`clear_cart`)

**Summary:** Remove all items from the authenticated user's cart.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/cart/<item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`remove_cart_item`)

**Summary:** Remove a single item from the cart.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/cart/<item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/cart.py` (`update_cart_item`)

**Summary:** Update quantity or notes for a cart item. Setting quantity to 0 removes it.


**Request Specification:**

```json
{
    "notes": "any",
    "quantity": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/checkin`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/daily_checkin.py` (`record_checkin`)

**Summary:** Record daily check-in for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Check-in failed, please try again"`
- `"Unable to resolve campus for this request"`

---

### `GET /api/checkin/history`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/daily_checkin.py` (`checkin_history`)

**Summary:** Return daily check-in history for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `daily_checkins`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/delivery/admin/gates`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_list_gates`)

**Summary:** List all gates including inactive (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/delivery/admin/gates`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_create_gate`)

**Summary:** Create a delivery gate (admin only).


**Request Specification:**

```json
{
    "base_fee": "any",
    "campus_id": "any",
    "is_active": "any",
    "lat": "any",
    "lon": "any",
    "min_fee": "any",
    "name": "any",
    "rate_per_km": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Unable to resolve campus for this request"`
- `"campus_id is required for super_admin"`

---

### `DELETE /api/delivery/admin/gates/<gate_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_delete_gate`)

**Summary:** Deactivate a gate (admin only). Does not permanently delete.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Gate not found"`

---

### `PATCH /api/delivery/admin/gates/<gate_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_update_gate`)

**Summary:** Update a delivery gate (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Gate not found"`
- `"No valid fields to update"`

---

### `GET /api/delivery/admin/hostels`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_list_hostels`)

**Summary:** List all hostels including inactive ones (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/delivery/admin/hostels`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_create_hostel`)

**Summary:** Create a new on-campus hostel (admin only).


**Request Specification:**

```json
{
    "campus_id": "any",
    "delivery_fee": "any",
    "gate_id": "any",
    "is_active": "any",
    "name": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Unable to resolve campus for this request"`
- `"campus_id is required for super_admin"`

---

### `DELETE /api/delivery/admin/hostels/<hostel_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_delete_hostel`)

**Summary:** Deactivate a hostel (admin only). Does not permanently delete.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Hostel not found"`

---

### `PATCH /api/delivery/admin/hostels/<hostel_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/delivery.py` (`admin_update_hostel`)

**Summary:** Update an on-campus hostel (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Hostel not found"`
- `"No valid fields to update"`

---

### `POST /api/delivery/calculate-fee`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/delivery.py` (`calculate_fee`)

**Summary:** Preview the delivery fee before placing an order.


**Request Specification:**

```json
{
    "campus_id": "any",
    "delivery_location_id": "any",
    "delivery_type": "any",
    "lat": "any",
    "lon": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates, hostels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Gate not found"`
- `"Hostel not found"`
- `"This location is outside our delivery area."`
- `"delivery_type must be "`

---

### `GET /api/delivery/gates`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/delivery.py` (`list_gates`)

**Summary:** List all active delivery gates (used for off-campus fee calculation) for the selected campus.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `gates`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/delivery/hostels`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/delivery.py` (`list_hostels`)

**Summary:** List all active on-campus hostels with their delivery fees for the selected campus.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hostels`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/departments`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/departments.py` (`list_departments`)

**Summary:** List active departments, optionally grouped by faculty.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `faculty, grouped`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/departments/<dept_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/departments.py` (`get_department`)

**Summary:** Get a single department by ID.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Department not found"`

---

### `GET /api/departments/faculties`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/departments.py` (`list_faculties`)

**Summary:** List distinct faculty names from active departments.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `departments`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/docs/`

**Authentication:** Public (No auth token required)

**Source File:** `/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/flask/views.py` (`apidocs`)

**Summary:** The /apidocs


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/docs/apispec.json`

**Authentication:** Public (No auth token required)

**Source File:** `/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/flask/views.py` (`apispec`)

**Summary:** The /apispec_1.json and other specs


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/docs/static/<path:filename>`

**Authentication:** Public (No auth token required)

**Source File:** `/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/flask/blueprints.py` (`send_static_file`)

**Summary:** The view function used to serve files from


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`list_events`)

**Summary:** List published upcoming events for the selected campus (or all if unspecified).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`create_event`)

**Summary:** Create a new event listing (admin only).


**Request Specification:**

```json
{
    "ends_at": "any",
    "hp_per_attendee": "any",
    "hp_reward": "any",
    "is_published": "any",
    "organizer_id": "any",
    "slug": "any",
    "starts_at": "any",
    "title": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Unable to resolve campus for this request"`

---

### `GET /api/events/<event_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`get_event`)

**Summary:** Get event detail.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_tickets, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/events/<event_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`delete_event`)

**Summary:** Delete an event (admin only). Cascades to event_tickets and checkins.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_tickets, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/events/<event_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`update_event`)

**Summary:** Update an event (admin only).


**Request Specification:**

```json
{
    "hp_per_attendee": "any",
    "hp_reward": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_tickets, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/<event_id>/checkin`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/events.py` (`checkin`)

**Summary:** Check in to a Holy Grills event using QR token or ticket ID / guest email.


**Request Specification:**

```json
{
    "email": "any",
    "guest_email": "any",
    "qr_token": "any",
    "ticket_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_tickets, events, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Invalid door QR token"`

---

### `POST /api/events/<event_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`update_event_image`)

**Summary:** Update event image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"image_url is required"`

---

### `POST /api/events/<event_id>/qr`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`generate_event_qr`)

**Summary:** Generate a QR token for event check-in (admin only).


**Request Specification:**

```json
{
    "qr_token": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/<event_id>/register`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/events.py` (`register_for_event`)

**Summary:** Register for an event. Supports ticket tiers, an optional HP discount


**Request Specification:**

```json
{
    "callback_url": "any",
    "email": "any",
    "guest_email": "any",
    "guest_name": "any",
    "guest_phone": "any",
    "name": "any",
    "payment_method": "any",
    "phone": "any",
    "promo_code": "any",
    "registration_answers": "any",
    "tier_id": "any",
    "use_hp": "any",
    "wallet_amount": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events, profiles, promo_codes`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"This ticket has no HP discount available"`
- `"Ticket tier not found"`

---

### `GET /api/events/<event_id>/registrants`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`list_event_registrants`)

**Summary:** List all registrants for an event (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `format`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_ticket_tiers, event_tickets, events, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/<event_id>/send-registrants-to-host`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`send_registrants_to_host`)

**Summary:** Email the full registrant list to the event organiser / host.


**Request Specification:**

```json
{
    "custom_message": "any",
    "host_email": "any",
    "host_name": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, event_tickets, events, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Failed to send email — check RESEND_API_KEY"`
- `"host_email is required"`

---

### `GET /api/events/<event_id>/tickets/<ticket_id>/pdf`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/events.py` (`download_ticket_pdf`)

**Summary:** Download a PDF version of an event ticket, with the same QR the


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `guest_email`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, event_tickets, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"You do not have access to this ticket"`

---

### `GET /api/events/<event_id>/tiers`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`list_event_tiers`)

**Summary:** List ticket tiers for an event (public).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/<event_id>/tiers`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`create_event_tier`)

**Summary:** Create a ticket tier for an event (admin only).


**Request Specification:**

```json
{
    "capacity": "any",
    "color": "any",
    "description": "any",
    "early_bird_deadline": "any",
    "features": "any",
    "icon": "any",
    "is_early_bird": "any",
    "name": "any",
    "price_hp": "any",
    "price_naira": "any",
    "terms": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/<event_id>/tiers/comparison`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`get_tier_comparison`)

**Summary:** Fetch tier comparison view for an event (public).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/admin`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`admin_list_events`)

**Summary:** List all events including unpublished (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, published_only`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/catering-requests`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`list_catering_requests`)

**Summary:** List catering/event partnership requests (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `catering_requests`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/events/catering-requests`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`submit_catering_request`)

**Summary:** Submit a catering / event partnership request.


**Request Specification:**

```json
{
    "campus_id": "any",
    "event_name": "any",
    "organizer_name": "any",
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `catering_requests, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"campus_id is required"`

---

### `PATCH /api/events/catering-requests/<request_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`update_catering_request`)

**Summary:** Respond to a catering request — accept, reject, or add notes (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `catering_requests, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/my-tickets`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/events.py` (`my_tickets`)

**Summary:** Show all tickets for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_checkins, event_tickets, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/events/tiers/<tier_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`delete_event_tier`)

**Summary:** Delete a ticket tier (admin only). Forbidden if any tickets sold.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/events/tiers/<tier_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/events.py` (`update_event_tier`)

**Summary:** Update a ticket tier (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/events/tiers/<tier_id>/detail`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/events.py` (`get_tier_detail`)

**Summary:** Return full tier detail with event info.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `event_ticket_tiers, events`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/exclusive-spin`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/exclusive_spin.py` (`my_spins`)

**Summary:** Return the authenticated user's available exclusive spin credits.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/exclusive-spin/spin`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/exclusive_spin.py` (`do_spin`)

**Summary:** Consume one exclusive spin credit and return the prize.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `exclusive_spins`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"No spin credits available or concurrent update occurred. Please try again."`

---

### `GET /api/free-sides`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/free_sides.py` (`my_free_sides`)

**Summary:** Return the authenticated user's free side credit balance and active rows.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/free-sides/redeem`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/free_sides.py` (`redeem_free_side`)

**Summary:** Redeem one free side credit.


**Request Specification:**

```json
{
    "order_id": "any",
    "side_choice": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `free_side_credits, order_items, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Failed to apply free side to order — your credit has not been used, please try again"`
- `"No credits available or concurrent update occurred. Please try again."`
- `"This order can no longer be modified"`
- `"order_id is required"`

---

### `POST /api/graduation/claim`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/graduation.py` (`claim_graduation`)

**Summary:** Claim the graduation HP bonus. One-time only.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `academic_levels, profiles, system_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Failed to award graduation HP — please try again"`

---

### `GET /api/health`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/health.py` (`health`)

**Summary:** API health check — connectivity to Supabase and Redis.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/hp/admin/expire`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/hp.py` (`admin_expire`)

**Summary:** Admin manually expires HP for a user.


**Request Specification:**

```json
{
    "amount": "any",
    "notes": "any",
    "user_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Cannot expire HP outside your campus"`
- `"Target user profile not found"`

---

### `POST /api/hp/admin/grant`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/hp.py` (`admin_grant`)

**Summary:** Admin manually grants HP to a user.


**Request Specification:**

```json
{
    "amount": "any",
    "notes": "any",
    "user_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Cannot grant HP outside your campus"`
- `"Target user profile not found"`
- `"amount must be a positive number — use /admin/expire to reduce HP"`

---

### `GET /api/hp/balance`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`balance`)

**Summary:** Get user's HP balance: active, pending, total_visible.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/hp/bundles`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/hp.py` (`list_hp_bundles`)

**Summary:** List available HP bundle tiers that can be purchased.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/hp/bundles/purchase`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`purchase_hp_bundle`)

**Summary:** Purchase an HP bundle (event hosts). Charges card via Paystack reference, credits HP.


**Request Specification:**

```json
{
    "amount": "any",
    "hp_amount": "any",
    "paystack_reference": "any",
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_bundle_purchases`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/hp/flash-redeem/<reward_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`flash_redeem`)

**Summary:** Redeem a reward at the flash-sale price (50% HP discount, limited slots, 24h window).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/hp/tiers`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/hp.py` (`list_tiers`)

**Summary:** List all tiers with thresholds and perks.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/hp/transactions`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`transactions`)

**Summary:** Get HP transaction history for the authenticated user.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, type`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/hp/transfer`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`transfer_hp`)

**Summary:** Transfer active HP to another user.


**Request Specification:**

```json
{
    "amount": "any",
    "notes": "any",
    "recipient_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions, orders, profiles, system_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Transfer failed and could not be auto-refunded — contact support"`
- `"Transfer failed — your HP has been refunded, please try again"`

---

### `GET /api/hp/unlock-history`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/hp.py` (`unlock_history`)

**Summary:** Get HP unlock history for the authenticated user (from hp_transactions type=unlock).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_transactions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/batch-summary/<window_id>`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`batch_summary`)

**Summary:** Get aggregated item counts across all active orders in a delivery window batch.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/kitchen/batch/<batch_id>/advance`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`batch_advance`)

**Summary:** Advance every order in a delivery-window batch to its next status.


**Request Specification:**

```json
{
    "from_status": "any",
    "notes": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"No advanceable orders found in this batch"`

---

### `GET /api/kitchen/metrics`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`kitchen_metrics`)

**Summary:** Kitchen performance metrics — average prep time, throughput per window, completion rate.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `window_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/queue`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`live_queue`)

**Summary:** Get live order queue for kitchen. Shows received and preparing orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `window_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/scheduled`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`scheduled_orders`)

**Summary:** Get all scheduled orders awaiting promotion to the live queue.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `window_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/settings`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`get_kitchen_settings`)

**Summary:** Get all kitchen settings as a key/value map.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `kitchen_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/kitchen/settings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`update_kitchen_settings`)

**Summary:** Update one or more kitchen settings (key/value upsert). Admin only.


**Request Specification:**

```json
{
    "settings": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `kitchen_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/settings/<key>`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`get_kitchen_setting`)

**Summary:** Get a single kitchen setting by key.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `kitchen_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/kitchen/windows`

**Authentication:** `kitchen, admin` (JWT required)

**Source File:** `app/routes/kitchen.py` (`delivery_windows`)

**Summary:** Get current and upcoming delivery windows for kitchen view.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`get_leaderboard`)

**Summary:** Get leaderboard. period_type: monthly | weekly | all_time.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, period_type`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `leaderboard_snapshots, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/hall-of-fame`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`hall_of_fame`)

**Summary:** Permanent Hall of Fame — global monthly leaderboard #1 winners by period,


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_inductees, leaderboard_snapshots`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/hall-of-fame/inductees`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`hall_of_fame_inductees`)

**Summary:** All Hall of Fame inductees — users who reached 4 top-4 leaderboard finishes (global).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_inductees, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/hall-of-fame/inductees/<inductee_user_id>/card`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`inductee_share_card`)

**Summary:** Shareable induction card data for a specific Hall of Fame inductee (global).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hall_of_fame_inductees, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Inductee not found"`

---

### `GET /api/leaderboard/my-rank`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/leaderboard.py` (`my_rank`)

**Summary:** Get authenticated user's current rank and HP stats.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, period_type`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `leaderboard_snapshots, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/squad`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/leaderboard.py` (`squad_leaderboard`)

**Summary:** Squad leaderboard — ranks squads by combined HP earned from squad orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, period_type`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles, squad_members`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/leaderboard/squad/my-rank`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/leaderboard.py` (`squad_my_rank`)

**Summary:** Get the authenticated user's position in the squad leaderboard.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, period_type`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/marketplace`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/marketplace.py` (`list_listings`)

**Summary:** List active marketplace listings with availability filters (login required).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `category, listing_type, q`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listing_availability, marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/marketplace/<listing_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/marketplace.py` (`get_listing`)

**Summary:** Get marketplace listing detail (login required).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/<listing_id>/purchase`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/marketplace.py` (`purchase`)

**Summary:** Purchase a marketplace listing. Uses atomic hg_purchase_marketplace_item RPC.


**Request Specification:**

```json
{
    "payment_method": "any",
    "payment_reference": "any",
    "use_hp": "any",
    "wallet_amount": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/admin/codes/<listing_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`upload_codes`)

**Summary:** Upload access codes for a listing (admin only). Accepts list of code strings.


**Request Specification:**

```json
{
    "codes": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/marketplace/admin/listings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_list_listings`)

**Summary:** List all marketplace listings regardless of status (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/admin/listings`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_create_listing`)

**Summary:** Create a marketplace listing directly (admin only).


**Request Specification:**

```json
{
    "listing_type": "any",
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/marketplace/admin/listings/<listing_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_get_listing`)

**Summary:** Get full marketplace listing detail, including archived/rejected listings (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings, marketplace_purchases`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/marketplace/admin/listings/<listing_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_delete_listing`)

**Summary:** Delete a marketplace listing (admin only). Also removes associated access codes.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_access_codes, marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/marketplace/admin/listings/<listing_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_update_listing`)

**Summary:** Approve, reject, or update a marketplace listing (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/marketplace/admin/listings/<listing_id>/availability`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`update_listing_availability`)


**Request Specification:**

```json
{
    "campus_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listing_availability`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"At least one availability field is required"`
- `"campus_id is required"`

---

### `POST /api/marketplace/admin/listings/<listing_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`update_listing_image`)

**Summary:** Update marketplace listing image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"image_url is required"`

---

### `GET /api/marketplace/admin/purchases`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_all_purchases`)

**Summary:** List all marketplace purchases across all users (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, listing_id, offset, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_purchases`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/marketplace/admin/purchases/<purchase_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_update_purchase`)

**Summary:** Admin: update marketplace purchase status with buyer notification.


**Request Specification:**

```json
{
    "admin_note": "any",
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_purchases`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Cannot refund card portion: purchase has no payment_reference"`

---

### `GET /api/marketplace/admin/requests`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_list_requests`)

**Summary:** List vendor listing requests for admin review.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_requests`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/marketplace/admin/requests/<request_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`admin_respond_to_request`)

**Summary:** Approve or reject a vendor listing request (admin only).


**Request Specification:**

```json
{
    "admin_notes": "any",
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_requests`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/listings/<listing_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/marketplace.py` (`update_listing_image`)

**Summary:** Update marketplace listing image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_listings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"image_url is required"`

---

### `GET /api/marketplace/purchases`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/marketplace.py` (`my_purchases`)

**Summary:** Get the authenticated user's marketplace purchase history.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_purchases`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/marketplace/requests`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/marketplace.py` (`submit_listing_request`)

**Summary:** Submit a vendor listing request for admin review (login required).


**Request Specification:**

```json
{
    "category": "any",
    "description": "any",
    "proposed_price": "any",
    "service_title": "any",
    "vendor_email": "any",
    "vendor_name": "any",
    "vendor_phone": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `marketplace_requests, profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/menu/addons`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/menu.py` (`list_addons`)

**Summary:** List available add-on items — optional extras customers can append to any order


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addons`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/menu/addons`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_addon`)

**Summary:** Create an add-on item (admin only).


**Request Specification:**

```json
{
    "description": "any",
    "group_id": "any",
    "is_available": "any",
    "name": "any",
    "price": "any",
    "sort_order": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addons`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/addons/<addon_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_addon`)

**Summary:** Update an add-on item (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addons`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Add-on not found"`

---

### `POST /api/menu/addons/<addon_id>/archive`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`archive_addon`)

**Summary:** Archive an add-on item (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addons`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Add-on not found"`

---

### `GET /api/menu/categories`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/menu.py` (`list_categories`)

**Summary:** List all active menu categories for the current campus (guest or authenticated).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/menu/categories`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_category`)

**Summary:** Create a new menu category (admin only).


**Request Specification:**

```json
{
    "description": "any",
    "is_active": "any",
    "name": "any",
    "slug": "any",
    "sort_order": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/menu/categories/<category_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`delete_category`)

**Summary:** Deactivate a menu category (admin only). Does not delete items within it.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/categories/<category_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_category`)

**Summary:** Update a menu category (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/menu/items`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/menu.py` (`list_items`)

**Summary:** List menu items with availability, daily stock, and kitchen capacity metadata for the current campus (guest or authenticated).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `available_only, category, is_featured, q`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_categories, menu_item_availability, menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/menu/items`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_item`)

**Summary:** Create a new menu item (admin only).


**Request Specification:**

```json
{
    "hp_multiplier": "any",
    "is_available": "any",
    "name": "any",
    "slug": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"hp_multiplier must be 0.5, 1.0, or 2.0"`

---

### `GET /api/menu/items/<item_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/menu.py` (`get_item`)

**Summary:** Get single menu item detail including variation groups, options, and daily stock.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_groups, menu_item_variation_options, menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Item not found"`

---

### `PATCH /api/menu/items/<item_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_item`)

**Summary:** Update a menu item (admin only). Supports setting or clearing daily_limit.


**Request Specification:**

```json
{
    "hp_multiplier": "any",
    "is_available": "any",
    "updated_at": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Menu item not found"`
- `"hp_multiplier must be 0.5, 1.0, or 2.0"`

---

### `POST /api/menu/items/<item_id>/addon-groups`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_addon_group`)

**Summary:** Create a required (or optional) add-on group on a menu item, e.g.


**Request Specification:**

```json
{
    "is_required": "any",
    "max_select": "any",
    "min_select": "any",
    "name": "any",
    "sort_order": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addon_groups, menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/menu/items/<item_id>/addon-groups/<group_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`delete_addon_group`)

**Summary:** Permanently delete an add-on group and all its linked add-ons (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addon_groups`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/items/<item_id>/addon-groups/<group_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_addon_group`)

**Summary:** Update an add-on group (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addon_groups`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/menu/items/<item_id>/addons`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/menu.py` (`get_item_addons`)

**Summary:** Get add-on groups (e.g. "Sides", "Sauces") for a menu item, each with its


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_addon_groups, menu_addons, menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/menu/items/<item_id>/archive`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`archive_item`)

**Summary:** Soft-archive a menu item (admin only). Order history is preserved.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/items/<item_id>/availability`

**Authentication:** `admin, kitchen` (JWT required)

**Source File:** `app/routes/menu.py` (`update_item_availability`)

**Summary:** Update this campus's availability for a menu item — on/off, daily cap,


**Request Specification:**

```json
{
    "campus_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_availability, menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"At least one availability field is required"`
- `"campus_id is required"`

---

### `POST /api/menu/items/<item_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_menu_item_image`)

**Summary:** Update menu item image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"image_url is required"`

---

### `POST /api/menu/items/<item_id>/variation-groups`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_variation_group`)

**Summary:** Create a variation group on a menu item (admin only).


**Request Specification:**

```json
{
    "is_required": "any",
    "max_selections": "any",
    "min_selections": "any",
    "name": "any",
    "sort_order": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_groups`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/menu/items/<item_id>/variation-groups/<group_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`delete_variation_group`)

**Summary:** Delete a variation group and all its options (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_groups, menu_item_variation_options`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Variation group not found"`

---

### `PATCH /api/menu/items/<item_id>/variation-groups/<group_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_variation_group`)

**Summary:** Update a variation group (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_groups`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Variation group not found"`

---

### `POST /api/menu/items/<item_id>/variation-groups/<group_id>/options`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`create_variation_option`)

**Summary:** Add a choice option to a variation group (admin only).


**Request Specification:**

```json
{
    "is_available": "any",
    "name": "any",
    "price_delta": "any",
    "sort_order": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_options`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/menu/items/<item_id>/variation-groups/<group_id>/options/<option_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`delete_variation_option`)

**Summary:** Delete a variation option (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_options`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Variation option not found"`

---

### `PATCH /api/menu/items/<item_id>/variation-groups/<group_id>/options/<option_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`update_variation_option`)

**Summary:** Update a variation option (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_variation_options`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Variation option not found"`

---

### `PATCH /api/menu/items/bulk-availability`

**Authentication:** `admin, kitchen` (JWT required)

**Source File:** `app/routes/menu.py` (`bulk_update_availability`)

**Summary:** Bulk update availability for multiple menu items (admin/kitchen).


**Request Specification:**

```json
{
    "campus_id": "any",
    "is_available": "any",
    "item_ids": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_item_availability, menu_items`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"campus_id is required"`

---

### `GET /api/menu/kitchen-capacity`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/menu.py` (`get_kitchen_capacity`)

**Summary:** Get the kitchen's current daily order capacity and today's order count.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/menu/kitchen-capacity`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/menu.py` (`set_kitchen_capacity`)

**Summary:** Set the kitchen's daily order capacity (admin only).


**Request Specification:**

```json
{
    "daily_order_capacity": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `kitchen_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/notifications`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`my_notifications`)

**Summary:** Get authenticated user's notification inbox.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, unread_only`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notifications`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/notifications/<notification_id>/read`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`mark_read`)

**Summary:** Mark a notification as read.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/notifications/blasts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/notifications.py` (`list_blasts`)

**Summary:** List notification blast history (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, offset, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_blasts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/notifications/blasts`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/notifications.py` (`create_blast`)

**Summary:** Create and optionally send a notification blast (admin only).


**Request Specification:**

```json
{
    "campus_id": "any",
    "created_by": "any",
    "scheduled_at": "any",
    "segment": "any",
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_blasts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Unable to create blast for the specified campus"`

---

### `GET /api/notifications/blasts/<blast_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/notifications.py` (`get_blast`)

**Summary:** Get a single notification blast's detail (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_blasts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/notifications/preferences`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`get_preferences`)

**Summary:** Get the authenticated user's notification preferences.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_preferences`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/notifications/preferences`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`update_preferences`)

**Summary:** Update the authenticated user's notification preferences.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notification_preferences`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/notifications/read-all`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`mark_all_read`)

**Summary:** Mark all in-app notifications as read.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `notifications`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/order-locks`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`list_locks`)

**Summary:** List the authenticated user's order locks.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/order-locks`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`create_lock`)

**Summary:** Lock-in a future order date with a discount.


**Request Specification:**

```json
{
    "campus_id": "any",
    "discount_pct": "any",
    "locked_date": "any",
    "reschedule_count": "any",
    "reward_hp_amount": "any",
    "reward_type": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"User already has an active lock"`
- `"reward_type must be "`

---

### `GET /api/order-locks/<lock_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`get_lock`)

**Summary:** Get a specific order lock.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/order-locks/<lock_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`cancel_lock`)

**Summary:** Cancel an active order lock.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/order-locks/<lock_id>/reschedule`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/order_locks.py` (`reschedule_lock`)

**Summary:** Reschedule a locked order date. Allowed once only.


**Request Specification:**

```json
{
    "locked_date": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/order-locks/admin/all`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/order_locks.py` (`admin_list_locks`)

**Summary:** Admin: list all order locks with filters.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, date, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`list_orders`)

**Summary:** List authenticated user's orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/orders.py` (`create_order`)


**Request Specification:**

```json
{
    "items": "any",
    "payment_method": "any",
    "user_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/<order_id>`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/orders.py` (`get_order`)

**Summary:** Get order detail. Authenticated users can only see their own orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `claim_token`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/<order_id>/call-rider`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`call_assigned_rider`)

**Summary:** Return a dynamic call link for the rider assigned to the order.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/cancel`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`cancel_order`)

**Summary:** Cancel an order. Only the order owner can cancel, and only while status is 'received'.


**Request Specification:**

```json
{
    "reason": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/claim`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`claim_guest_order`)

**Summary:** Link a guest order to a newly created account.


**Request Specification:**

```json
{
    "claim_token": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- `"Order is already owned or claimed"`

---

### `GET /api/orders/<order_id>/history`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/orders.py` (`order_status_history`)

**Summary:** Get the full status change history for an order.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_status_logs, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/refund`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/orders.py` (`refund_order`)

**Summary:** Initiate a refund for an order (admin only).


**Request Specification:**

```json
{
    "reason": "any",
    "refund_amount": "any",
    "refund_to_wallet": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, wallet_transactions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- `"Cannot refund an unpaid cancelled order"`
- `"This order has already been fully refunded."`

---

### `POST /api/orders/<order_id>/reorder`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`reorder`)

**Summary:** Fetch items from a past order to pre-populate a new order (reorder helper).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items, order_items, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/review`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`submit_review`)

**Summary:** Submit an order review with optional kitchen and rider star ratings (earns HP on every review).


**Request Specification:**

```json
{
    "comment": "any",
    "kitchen_rating": "any",
    "rating": "any",
    "rider_rating": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_reviews, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/review/images`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`add_review_images`)

**Summary:** Add images to an order review.


**Request Specification:**

```json
{
    "image_urls": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_reviews`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- `"image_urls is required"`

---

### `DELETE /api/orders/<order_id>/scheduled`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`cancel_scheduled_order`)

**Summary:** Cancel a scheduled order before it is due for preparation.


**Request Specification:**

```json
{
    "reason": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_locks, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/share`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`record_order_share`)

**Summary:** Record that the user shared their order confirmation (e.g. on WhatsApp).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `order_share_events, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/squad-members`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`add_squad_members`)

**Summary:** Add squad members to a squad order for HP splitting.


**Request Specification:**

```json
{
    "emails": "any",
    "split_hp": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders, profiles, squad_members`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- `"At least one email is required"`

---

### `PATCH /api/orders/<order_id>/status`

**Authentication:** `admin, kitchen, rider` (JWT required)

**Source File:** `app/routes/orders.py` (`update_status`)

**Summary:** Update order status (kitchen/rider/admin).


**Request Specification:**

```json
{
    "notes": "any",
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/<order_id>/walk`

**Authentication:** `admin, kitchen, rider` (JWT required)

**Source File:** `app/routes/orders.py` (`walk_order_status`)

**Summary:** Walk an order through all intermediate states to reach a target status in


**Request Specification:**

```json
{
    "notes": "any",
    "target_status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/active`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`active_order`)

**Summary:** Get the authenticated user's current active (in-progress) order, if any.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/delivery-windows`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/orders.py` (`list_delivery_windows`)

**Summary:** List upcoming open delivery windows available for ordering.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/delivery-windows/status`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/orders.py` (`delivery_windows_status`)

**Summary:** Return whether the kitchen is currently open and list available delivery


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_windows, operating_hour_overrides, operating_hours`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/delivery-zones`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/orders.py` (`list_delivery_zones`)

**Summary:** List delivery zones with fees and estimated delivery times.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_zones`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/orders/scheduled`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/orders.py` (`list_scheduled_orders`)

**Summary:** List the authenticated user's upcoming scheduled orders.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/orders/validate-promo`

**Authentication:** Optional JWT (Public or Authenticated checkout context)

**Source File:** `app/routes/orders.py` (`validate_promo`)

**Summary:** Validate a promo code against an order subtotal without applying it.


**Request Specification:**

```json
{
    "code": "any",
    "order_subtotal": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Kitchen daily capacity (`kitchen_settings.daily_order_capacity`) and per-item limits verified.
- Storefront operating hours checked against West Africa Time (`ZoneInfo('Africa/Lagos')`).
- Wallet balance verified prior to debit; promo codes and HP discounts atomically applied.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/push/subscribe`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`push_subscribe`)

**Summary:** Register a browser Web Push subscription for the authenticated user.


**Request Specification:**

```json
{
    "device_label": "any",
    "subscription": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `push_subscriptions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/push/subscribe`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/notifications.py` (`push_unsubscribe`)

**Summary:** Deactivate all Web Push subscriptions for the authenticated user (or one endpoint).


**Request Specification:**

```json
{
    "endpoint": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `push_subscriptions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/referrals`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/referrals.py` (`my_referrals`)

**Summary:** Get authenticated user's referral stats and list.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, referrals`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/referrals/complete`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/referrals.py` (`complete_referral`)

**Summary:** Internal endpoint called when a referred user completes their first order.


**Request Specification:**

```json
{
    "order_id": "any",
    "referred_user_id": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `referrals`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/referrals/stats`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/referrals.py` (`referral_stats`)

**Summary:** Get a lightweight summary of the authenticated user's referral performance


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, referrals`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/rewards`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/rewards.py` (`list_rewards`)

**Summary:** List active rewards. Optionally filter by category.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `category, reward_type`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/rewards`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`create_reward`)

**Summary:** Create a new reward (admin only).


**Request Specification:**

```json
{
    "campus_id": "any",
    "is_active": "any",
    "name": "any",
    "reward_type": "any",
    "stock_quantity": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/rewards/<reward_id>`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/rewards.py` (`get_reward`)

**Summary:** Get reward detail.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/rewards/<reward_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`delete_reward`)

**Summary:** Deactivate (soft-delete) a reward (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/rewards/<reward_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`update_reward`)

**Summary:** Update a reward (admin only).


**Request Specification:**

```json
{
    "updated_at": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/rewards/<reward_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`update_reward_image`)

**Summary:** Update reward image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"image_url is required"`

---

### `POST /api/rewards/<reward_id>/redeem`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/rewards.py` (`redeem_reward`)

**Summary:** Redeem a reward using HP via atomic hg_redeem_reward RPC.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `hp_tiers, rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/rewards/admin/redemptions`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`admin_list_redemptions`)

**Summary:** List all reward redemptions across all users (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, limit, offset, reward_id, status`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `reward_redemptions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/rewards/admin/redemptions/<redemption_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/rewards.py` (`admin_update_redemption`)

**Summary:** Fulfil or reject a reward redemption (admin only).


**Request Specification:**

```json
{
    "fulfilled_at": "any",
    "status": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `reward_redemptions, rewards`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Cannot reject an already-fulfilled redemption"`

---

### `GET /api/rewards/redemptions`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/rewards.py` (`my_redemptions`)

**Summary:** Get authenticated user's reward redemption history.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `reward_redemptions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/riders/availability`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`toggle_availability`)

**Summary:** Toggle rider online/offline availability status.


**Request Specification:**

```json
{
    "is_available": "any",
    "location_lat": "any",
    "location_lng": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `rider_profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/call/<order_id>`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`get_customer_call_link`)

**Summary:** Get a click-to-call link for the customer.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/earnings`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`rider_earnings`)

**Summary:** Get the authenticated rider's earnings summary for a period.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `period`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/history`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`delivery_history`)

**Summary:** Get the authenticated rider's completed delivery history.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/my-batch`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`my_batch`)

**Summary:** Get the current delivery batch assigned to this rider.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, sequencing`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, delivery_windows, gates, order_items, orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/riders/orders/<order_id>/attempt`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`mark_attempted`)

**Summary:** Mark a delivery as attempted (customer unreachable).


**Request Specification:**

```json
{
    "notes": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/riders/orders/<order_id>/deliver`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`mark_delivered`)

**Summary:** Mark an order as delivered.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/riders/orders/<order_id>/pickup`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`mark_picked_up`)

**Summary:** Confirm order pickup from kitchen. Transitions order from 'assigned' → 'out_for_delivery'.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `orders`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/riders/stats`

**Authentication:** `rider, admin` (JWT required)

**Source File:** `app/routes/riders.py` (`rider_stats`)

**Summary:** Get performance statistics for the authenticated rider.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `delivery_batches, orders, rider_profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/saved`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`list_saved`)

**Summary:** Get all items the authenticated user has saved for later.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `saved_for_later`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/saved`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`save_item`)

**Summary:** Save a menu item for later. If already saved, updates quantity.


**Request Specification:**

```json
{
    "menu_item_id": "any",
    "notes": "any",
    "quantity": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `menu_items, saved_for_later`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"quantity must be a valid integer"`

---

### `DELETE /api/saved/<item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`remove_saved_item`)

**Summary:** Remove a saved-for-later item.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `saved_for_later`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/saved/<item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`update_saved_item`)

**Summary:** Update quantity or notes on a saved-for-later item.


**Request Specification:**

```json
{
    "notes": "any",
    "quantity": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `saved_for_later`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"quantity must be a valid integer"`

---

### `POST /api/saved/<item_id>/move-to-cart`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`move_saved_to_cart`)

**Summary:** Move a saved-for-later item into the active cart.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items, saved_for_later`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/saved/from-cart/<cart_item_id>`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/saved_for_later.py` (`move_cart_to_saved`)

**Summary:** Move an active cart item to the saved-for-later list.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `cart_items, saved_for_later`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/storefront/banners`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`list_banners`)

**Summary:** Get active promotional banners for the storefront homepage.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `placement`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/banners`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`create_banner`)

**Summary:** Create a new promotional banner (admin only).


**Request Specification:**

```json
{
    "images": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/storefront/banners/<banner_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`delete_banner`)

**Summary:** Delete a banner (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Banner not found"`

---

### `PATCH /api/storefront/banners/<banner_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_banner`)

**Summary:** Update a banner (admin only). Pass `images` array to enable/update carousel slides.


**Request Specification:**

```json
{
    "images": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Banner not found"`

---

### `POST /api/storefront/banners/<banner_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_banner_image`)

**Summary:** Update banner image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any",
    "mobile_image_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `banners`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Banner not found"`
- `"image_url is required"`

---

### `GET /api/storefront/config/public`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`get_public_config`)

**Summary:** Get public system settings and configs (e.g. WhatsApp, etc).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `system_settings`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/storefront/early-supporters`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`list_early_supporters`)

**Summary:** Get the public-facing Early Supporters list.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/early-supporters`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`create_early_supporter`)

**Summary:** Add a new Early Supporter entry (admin only).


**Request Specification:**

```json
{
    "name": "any",
    "note": "any",
    "photo_url": "any",
    "social_links": "any",
    "sort_order": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/storefront/early-supporters/<section_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`delete_early_supporter`)

**Summary:** Deactivate an Early Supporter entry (admin only — soft delete).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Early supporter not found"`

---

### `PATCH /api/storefront/early-supporters/<section_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_early_supporter`)

**Summary:** Update an Early Supporter entry (admin only).


**Request Specification:**

```json
{
    "is_active": "any",
    "name": "any",
    "sort_order": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Early supporter not found"`

---

### `POST /api/storefront/early-supporters/<section_id>/photo`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_early_supporter_photo`)

**Summary:** Update early supporter photo with Cloudinary URL.


**Request Specification:**

```json
{
    "photo_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Early supporter not found"`
- `"photo_url is required"`

---

### `GET /api/storefront/newsletter`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`newsletter_list`)

**Summary:** List newsletter subscribers (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `active_only, limit, offset`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `newsletter_subscriptions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/newsletter`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`newsletter_subscribe`)

**Summary:** Subscribe an email address to the Holy Grills newsletter.


**Request Specification:**

```json
{
    "email": "any",
    "full_name": "any",
    "source": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `newsletter_subscriptions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/newsletter/unsubscribe`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`newsletter_unsubscribe`)

**Summary:** Unsubscribe an email address from the newsletter.


**Request Specification:**

```json
{
    "email": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `newsletter_subscriptions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/storefront/operating-hours`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`get_hours`)

**Summary:** Get current operating hours schedule and any today-specific override.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `operating_hour_overrides, operating_hours`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/storefront/operating-hours`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_hours`)

**Summary:** Update operating hours for a day (admin only).


**Request Specification:**

```json
{
    "day": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `operating_hours`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"At least one of open_time, close_time, is_closed is required"`
- `"No operating-hours row exists for this campus/weekday yet"`

---

### `POST /api/storefront/operating-hours/override`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`set_override`)

**Summary:** Set a date-specific operating hours override (e.g., public holiday closure).


**Request Specification:**

```json
{
    "date": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `operating_hour_overrides`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"date (or override_date) is required"`

---

### `POST /api/storefront/promo-codes/validate`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`validate_promo`)

**Summary:** [DEPRECATED] Validate a promo code — use POST /orders/validate-promo instead.


**Request Specification:**

```json
{
    "code": "any",
    "order_subtotal": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `promo_codes`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/storefront/sections`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/storefront.py` (`list_sections`)

**Summary:** Get active storefront CMS sections (homepage, banners, etc).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/sections`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`create_section`)

**Summary:** Create a new CMS homepage section (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `DELETE /api/storefront/sections/<section_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`delete_section`)

**Summary:** Deactivate (soft-delete) a CMS homepage section (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `PATCH /api/storefront/sections/<section_id>`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_section`)

**Summary:** Update a storefront section (admin only).


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/storefront/sections/<section_id>/image`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/storefront.py` (`update_section_image`)

**Summary:** Update storefront section image with Cloudinary URL.


**Request Specification:**

```json
{
    "image_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `storefront_sections`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"image_url is required"`

---

### `POST /api/upload/signature`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/uploads.py` (`upload_signature`)

**Summary:** Generate a short-lived Cloudinary signature for a direct client upload.


**Request Specification:**

```json
{
    "folder": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Cloudinary upload is not configured"`
- `"Invalid upload folder"`

---

### `GET /api/wallet`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/wallet.py` (`get_balance`)

**Summary:** Get wallet balance and virtual account info.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `virtual_accounts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Wallet transactions execute atomically via `credit_wallet_atomic` / `debit_wallet_atomic` RPCs.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `GET /api/wallet/admin/transactions`

**Authentication:** `admin` (JWT required)

**Source File:** `app/routes/wallet.py` (`admin_wallet_transactions`)

**Summary:** List wallet transactions (admin only). Scoped to caller campus_id unless super_admin.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `campus_id, from_date, to_date, type, user_id`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `wallet_transactions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Wallet transactions execute atomically via `credit_wallet_atomic` / `debit_wallet_atomic` RPCs.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/wallet/fund/bank`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/wallet.py` (`request_virtual_account`)

**Summary:** Provision a Paystack Dedicated Virtual Account for bank transfers.


**Request Specification:**

- **JSON Body:** None required / empty body


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles, virtual_accounts`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Wallet transactions execute atomically via `credit_wallet_atomic` / `debit_wallet_atomic` RPCs.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/wallet/fund/card`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/wallet.py` (`fund_via_card`)

**Summary:** Initialize a card payment to top up wallet.


**Request Specification:**

```json
{
    "amount": "any",
    "callback_url": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `profiles`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Wallet transactions execute atomically via `credit_wallet_atomic` / `debit_wallet_atomic` RPCs.

**Error Responses:**

- `"Card payments are not configured on this server."`
- `"Payment gateway unavailable. Please try again later."`

---

### `GET /api/wallet/transactions`

**Authentication:** Authenticated user (`student`, `admin`, `kitchen`, `rider`, `super_admin`) (JWT required)

**Source File:** `app/routes/wallet.py` (`wallet_transactions`)

**Summary:** Get wallet transaction history. Filter by type: topup, order_payment, refund, withdrawal, bank_transfer.


**Request Specification:**

- **JSON Body:** None required / empty body

- **Query Parameters:** `type`


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** `wallet_transactions`


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.
- Wallet transactions execute atomically via `credit_wallet_atomic` / `debit_wallet_atomic` RPCs.

**Error Responses:**

- Standard error payload structure: `{"error": "<description>", "message": "<details>", "request_id": "<id>"}` (HTTP 400 / 401 / 403 / 404 / 500)

---

### `POST /api/webhooks/flutterwave`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/webhooks.py` (`flutterwave_webhook`)

**Summary:** Flutterwave webhook handler.


**Request Specification:**

```json
{
    "flw_ref": "any",
    "id": "any",
    "status": "any",
    "tx_ref": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Webhook processing failed"`

---

### `POST /api/webhooks/paystack`

**Authentication:** Public (No auth token required)

**Source File:** `app/routes/webhooks.py` (`paystack_webhook`)

**Summary:** Paystack webhook handler.


**Request Specification:**

```json
{
    "id": "any",
    "reference": "any",
    "transfer_code": "any"
}
```


**Response Specification (200 OK Example):**

```json
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {}
}
```


**Database & Service Interactions:**

- **Database Tables:** None directly in route handler (delegated to service layer)


**Business Rules Enforced:**

- Request validation & permission checks enforced prior to execution.
- Campus isolation applied for non-super_admin users via `resolve_scoped_campus_id`.

**Error Responses:**

- `"Webhook processing failed"`

---

## SECTION 2: DATABASE SCHEMA

Total public schema tables documented: **99**


### Table: `public.abandoned_carts`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `recovered_order_id` → `orders.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | YES | `NULL` |
| `guest_email` | `citext` | YES | `NULL` |
| `guest_phone` | `text` | YES | `NULL` |
| `cart_payload` | `jsonb` | NO | `NULL` |
| `last_recovery_sent_at` | `timestamp with time zone` | YES | `NULL` |
| `next_recovery_at` | `timestamp with time zone` | YES | `NULL` |
| `recovery_attempts` | `integer` | NO | `0` |
| `is_recovered` | `boolean` | NO | `false` |
| `recovered_order_id` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `last_active_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `value` | `text` | NO | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `sort_order` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

**Unique Constraints:**
- `academic_levels_value_key`: UNIQUE (`value`)

---

### Table: `public.admin_audit_logs`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `actor_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `action` | `text` | NO | `NULL` |
| `entity_type` | `text` | NO | `NULL` |
| `entity_id` | `text` | YES | `NULL` |
| `actor_id` | `uuid` | YES | `NULL` |
| `actor_role` | `text` | YES | `NULL` |
| `ip_address` | `inet` | YES | `NULL` |
| `user_agent` | `text` | YES | `NULL` |
| `before_value` | `jsonb` | YES | `NULL` |
| `after_value` | `jsonb` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `session_id` | `text` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `uuid_generate_v4()` |
| `title` | `text` | NO | `NULL` |
| `subtitle` | `text` | YES | `NULL` |
| `image_url` | `text` | YES | `NULL` |
| `mobile_image_url` | `text` | YES | `NULL` |
| `action_url` | `text` | YES | `NULL` |
| `action_label` | `text` | YES | `NULL` |
| `placement` | `text` | NO | `'home'::text` |
| `sort_order` | `integer` | NO | `0` |
| `is_active` | `boolean` | NO | `true` |
| `starts_at` | `timestamp with time zone` | YES | `NULL` |
| `ends_at` | `timestamp with time zone` | YES | `NULL` |
| `target_roles` | `text[]` | NO | `'{}'::text[]` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_by` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `batch_id` | `uuid` | NO | `NULL` |
| `order_id` | `uuid` | NO | `NULL` |
| `sequence` | `integer` | YES | `NULL` |
| `added_by` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `slug` | `text` | NO | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `uuid_generate_v4()` |
| `user_id` | `uuid` | NO | `NULL` |
| `menu_item_id` | `uuid` | NO | `NULL` |
| `quantity` | `integer` | NO | `1` |
| `options` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `added_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `organizer_name` | `text` | NO | `NULL` |
| `email` | `citext` | NO | `NULL` |
| `phone` | `text` | NO | `NULL` |
| `organization` | `text` | YES | `NULL` |
| `event_name` | `text , event_date date` | NO | `NULL` |
| `expected_guests` | `integer` | NO | `NULL` |
| `budget` | `numeric(14,2)` | YES | `NULL` |
| `notes` | `text` | YES | `NULL` |
| `status` | `text` | NO | `'new'::text` |
| `assigned_to` | `uuid` | YES | `NULL` |
| `quoted_amount` | `numeric(14,2)` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `hp_promo_optin` | `boolean` | NO | `false` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `challenge_id` | `uuid` | NO | `NULL` |
| `user_id` | `uuid` | NO | `NULL` |
| `hp_transaction_id` | `uuid` | YES | `NULL` |
| `completed_at` | `timestamp with time zone` | NO | `now()` |
| `hp_awarded` | `integer` | NO | `0` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `hp_reward` | `integer` | NO | `0` |
| `criteria` | `jsonb` | NO | `NULL` |
| `starts_at` | `timestamp with time zone` | YES | `NULL` |
| `ends_at` | `timestamp with time zone` | YES | `NULL` |
| `max_completions_per_user` | `integer` | NO | `1` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `type` | `text` | NO | `'one_time'::text` |
| `target_count` | `integer` | NO | `1` |
| `created_by` | `uuid` | YES | `NULL` |
| `title` | `text` | YES | `NULL` |
| `updated_at` | `timestamp with time zone` | YES | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `job_name` | `text` | NO | `NULL` |
| `locked_at` | `timestamp with time zone` | NO | `now()` |

**RLS Policies:**
- `Admins manage cron_locks`

---

### Table: `public.daily_checkins`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid , checkin_date date` | NO | `NULL` |
| `hp_awarded` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `idx_daily_checkins_date` ON (`checkin_date`)
- `idx_daily_checkins_user_id` ON (`user_id`)

---

### Table: `public.delivery_assignments`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `order_id` | `uuid` | NO | `NULL` |
| `rider_id` | `uuid` | NO | `NULL` |
| `batch_id` | `uuid` | YES | `NULL` |
| `status` | `text` | NO | `'assigned'::text` |
| `note` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `completed_at` | `timestamp with time zone` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `rider_id` | `uuid` | YES | `NULL` |
| `status` | `text` | NO | `'open'::text` |
| `notes` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `completed_at` | `timestamp with time zone` | YES | `NULL` |
| `zone` | `text` | YES | `NULL` |
| `delivery_window_id` | `uuid` | YES | `NULL` |
| `window_id` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `label` | `text` | NO | `NULL` |
| `starts_at` | `timestamp with time zone` | NO | `NULL` |
| `ends_at` | `timestamp with time zone` | NO | `NULL` |
| `capacity` | `integer` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `zone_id` | `uuid` | YES | `NULL` |
| `status` | `text` | NO | `'open'::text` |
| `created_by` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `uuid_generate_v4()` |
| `name` | `text` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `delivery_fee` | `numeric(10,2)` | NO | `0` |
| `min_order` | `numeric(10,2)` | NO | `0` |
| `is_active` | `boolean` | NO | `true` |
| `polygon` | `jsonb` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `slug` | `text` | NO | `NULL` |
| `faculty` | `text` | NO | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `sort_order` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `fingerprint` | `text` | NO | `NULL` |
| `platform` | `text` | NO | `'unknown'::text` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `token` | `text` | NO | `NULL` |
| `platform` | `text` | NO | `'unknown'::text` |
| `device_model` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

**Unique Constraints:**
- `device_tokens_user_id_token_key`: UNIQUE (`user_id, token`)

**RLS Policies:**
- `Users manage own device tokens`

---

### Table: `public.event_checkins`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `checked_in_by` → `profiles.id`, `hp_transaction_id` → `hp_transactions.id`, `ticket_id` → `event_tickets.id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `ticket_id` | `uuid` | NO | `NULL` |
| `qr_code` | `text` | NO | `NULL` |
| `checked_in_by` | `uuid` | YES | `NULL` |
| `hp_transaction_id` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `event_id` | `uuid` | NO | `NULL` |
| `name` | `text` | NO | `NULL` |
| `price_naira` | `numeric(12,2)` | NO | `0` |
| `price_hp` | `integer` | NO | `0` |
| `capacity` | `integer` | YES | `NULL` |
| `sold_count` | `integer` | NO | `0` |
| `description` | `text` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `sort_order` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `idx_event_ticket_tiers_event_id` ON (`event_id`)

---

### Table: `public.event_tickets`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `event_id` → `events.id`, `tier_id` → `event_ticket_tiers.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `event_id` | `uuid` | NO | `NULL` |
| `user_id` | `uuid` | NO | `NULL` |
| `quantity` | `integer` | NO | `1` |
| `status` | `text` | NO | `'pending'::text` |
| `qr_code` | `text` | YES | `encode(gen_random_bytes(24), 'hex'::text)` |
| `qr_expires_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `tier_id` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `title` | `text` | NO | `NULL` |
| `slug` | `text` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `starts_at` | `timestamp with time zone` | NO | `NULL` |
| `ends_at` | `timestamp with time zone` | NO | `NULL` |
| `location` | `text` | NO | `NULL` |
| `image_url` | `text` | YES | `NULL` |
| `ticket_price` | `numeric(14,2)` | NO | `0` |
| `hp_reward` | `integer` | NO | `0` |
| `capacity` | `integer` | YES | `NULL` |
| `is_published` | `boolean` | NO | `false` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `hp_promo_enabled` | `boolean` | NO | `false` |
| `is_featured` | `boolean` | NO | `false` |
| `organizer_id` | `uuid` | YES | `NULL` |
| `updated_at` | `timestamp with time zone` | YES | `now()` |
| `hp_per_attendee` | `integer` | YES | `NULL` |
| `funding_source` | `text` | YES | `NULL` |
| `max_attendees` | `integer` | YES | `NULL` |
| `hp_required` | `integer` | YES | `NULL` |
| `total_value` | `numeric(10,2)` | YES | `NULL::numeric` |
| `is_paid` | `boolean` | NO | `false` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `spin_count` | `integer` | NO | `0` |
| `source` | `text` | NO | `NULL` |
| `month` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `expires_at` | `timestamp with time zone` | NO | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `feature_name` | `text` | NO | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `description` | `text` | YES | `NULL` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `updated_by` | `uuid` | YES | `NULL` |

**Indexes:**
- `idx_feature_flags_updated_by` ON (`updated_by`)

---

### Table: `public.first_order_gifts`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `order_id` → `orders.id`, `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `order_id` | `uuid` | YES | `NULL` |
| `status` | `text` | NO | `'pending'::text` |
| `claimed_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `reward_id` | `uuid` | NO | `NULL` |
| `window_starts_at` | `timestamp with time zone` | NO | `NULL` |
| `window_ends_at` | `timestamp with time zone` | NO | `NULL` |
| `quantity_limit` | `integer` | NO | `5` |
| `discount_pct` | `numeric(5,2)` | NO | `0.50` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `credits_remaining` | `integer` | NO | `0` |
| `source` | `text` | NO | `NULL` |
| `month` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `expires_at` | `timestamp with time zone` | NO | `NULL` |
| `used_at` | `timestamp with time zone` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `lat` | `double precision` | YES | `NULL` |
| `lon` | `double precision` | YES | `NULL` |
| `base_fee` | `numeric(10,2)` | NO | `0` |
| `rate_per_km` | `numeric(10,2)` | NO | `0` |
| `min_fee` | `numeric(10,2)` | NO | `0` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

---

### Table: `public.hall_of_fame_inductees`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `inducted_at` | `timestamp with time zone` | NO | `now()` |
| `full_name` | `text` | NO | `NULL` |
| `photo_url` | `text` | YES | `NULL` |
| `tier_at_induction` | `text` | YES | `NULL` |
| `top4_finish_count` | `integer` | NO | `4` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**RLS Policies:**
- `Admins manage hall_of_fame`
- `Anyone reads hall_of_fame`

---

### Table: `public.hall_of_fame_rewards`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `inducted_at` | `timestamp with time zone` | NO | `now()` |
| `status` | `text` | NO | `'pending'::text` |
| `notes` | `text` | YES | `NULL` |
| `fulfilled_by` | `uuid` | YES | `NULL` |
| `fulfilled_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `idx_hall_of_fame_rewards_fulfilled_by` ON (`fulfilled_by`)
- `idx_hof_rewards_status` ON (`status`)

---

### Table: `public.hostels`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `gate_id` → `gates.id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `gate_id` | `uuid` | YES | `NULL` |
| `delivery_fee` | `numeric(10,2)` | NO | `0` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `idx_hostels_gate_id` ON (`gate_id`)

---

### Table: `public.hp_bundle_purchases`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `event_host_id` | `uuid` | NO | `NULL` |
| `hp_amount` | `integer` | NO | `NULL` |
| `naira_paid` | `numeric(12,2)` | NO | `NULL` |
| `price_per_hp` | `numeric(10,4)` | NO | `5.0` |
| `status` | `text` | NO | `'completed'::text` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `hp_bundle_purchases_event_host_id_idx` ON (`event_host_id`)

**RLS Policies:**
- `Admins manage hp_bundle_purchases`
- `Users view own hp_bundle_purchases`

---

### Table: `public.hp_bundles`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `hp_amount` | `integer` | NO | `NULL` |
| `price_naira` | `numeric(10,2)` | NO | `NULL` |
| `total_price` | `numeric(10,2)` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `sort_order` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `hp_transaction_id` | `uuid` | YES | `NULL` |
| `expired_amount` | `integer` | NO | `NULL` |
| `previous_balance` | `integer` | NO | `NULL` |
| `reason` | `text` | NO | `NULL` |
| `notification_id` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `min_points` | `integer` | NO | `0` |
| `maintenance_points` | `integer` | NO | `0` |
| `earn_multiplier` | `numeric(8,2)` | NO | `1` |
| `benefits` | `jsonb` | NO | `'{}'::jsonb` |
| `sort_order` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `slug` | `text` | YES | `NULL` |
| `badge_color_hex` | `text` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `type` | `text` | NO | `NULL` |
| `amount` | `integer` | NO | `NULL` |
| `balance_after` | `integer` | NO | `NULL` |
| `source` | `text` | NO | `NULL` |
| `reference_type` | `text` | YES | `NULL` |
| `reference_id` | `uuid` | YES | `NULL` |
| `issued_by_admin_id` | `uuid` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `expires_at` | `timestamp with time zone` | YES | `NULL` |
| `remaining_amount` | `integer, status character varying(20)` | NO | `'active'::character varying` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `key` | `text` | NO | `NULL` |
| `value` | `text` | NO | `''::text` |
| `updated_at` | `timestamp with time zone` | YES | `now()` |
| `updated_by` | `uuid` | YES | `NULL` |

**Indexes:**
- `idx_kitchen_settings_updated_by` ON (`updated_by`)

**RLS Policies:**
- `Anyone can view kitchen_settings`
- `Kitchen and admins manage
kitchen_settings`

---

### Table: `public.leaderboard_entries`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `period` | `text` | NO | `NULL` |
| `user_id` | `uuid` | NO | `NULL` |
| `rank` | `integer` | NO | `NULL` |
| `hp_total` | `integer` | NO | `0` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `order_count` | `integer` | NO | `0` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `rank` | `integer` | NO | `NULL` |
| `month` | `text` | NO | `NULL` |
| `reward_type` | `text` | NO | `'leaderboard_prize'::text` |
| `free_sides` | `integer` | NO | `0` |
| `free_spins` | `integer` | NO | `0` |
| `status` | `text` | NO | `'pending'::text` |
| `notes` | `text` | YES | `NULL` |
| `fulfilled_by` | `uuid` | YES | `NULL` |
| `fulfilled_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `period_key` | `text` | NO | `NULL` |
| `ranking_type` | `text` | NO | `'weekly'::text` |
| `entries` | `jsonb` | NO | `NULL` |
| `prizes_awarded` | `jsonb` | NO | `'[]'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**RLS Policies:**
- `leaderboard_snapshots: admins all`
- `leaderboard_snapshots: public read`

---

### Table: `public.login_streak_rewards`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `week_number` | `integer` | NO | `NULL` |
| `hp_awarded` | `integer` | NO | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `streak_count` | `integer` | NO | `1, last_login_date date` |
| `last_updated` | `timestamp with time zone` | NO | `now(), current_week_start date` |
| `week_state` | `jsonb` | NO | `'{}'::jsonb` |
| `cycle_week_number` | `integer` | NO | `1` |
| `consecutive_weeks` | `integer` | NO | `0` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `listing_id` | `uuid` | NO | `NULL` |
| `batch_id` | `uuid` | YES | `NULL` |
| `code` | `text` | NO | `NULL` |
| `status` | `text` | NO | `'available'::text` |
| `assigned_purchase_id` | `uuid` | YES | `NULL` |
| `assigned_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `listing_id` | `uuid` | NO | `NULL` |
| `uploaded_by` | `uuid` | YES | `NULL` |
| `code_count` | `integer` | NO | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `idx_mkt_code_batches_listing_id` ON (`listing_id`)
- `idx_mkt_code_batches_uploaded_by` ON (`uploaded_by`)

**RLS Policies:**
- `marketplace_code_batches: admins
all`

---

### Table: `public.marketplace_listings`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `title` | `text` | NO | `NULL` |
| `slug` | `text` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `vendor_name` | `text` | NO | `NULL` |
| `listing_type` | `text` | NO | `NULL` |
| `price` | `numeric(14,2)` | NO | `0` |
| `hp_price` | `integer` | YES | `NULL` |
| `image_url` | `text` | YES | `NULL` |
| `status` | `text` | NO | `'pending'::text` |
| `approved_by` | `uuid` | YES | `NULL` |
| `approved_at` | `timestamp with time zone` | YES | `NULL` |
| `rejection_reason` | `text` | YES | `NULL` |
| `inventory_count` | `integer` | YES | `NULL` |
| `low_inventory_threshold` | `integer` | YES | `NULL` |
| `is_out_of_stock` | `boolean` | NO | `false` |
| `min_tier_id` | `uuid` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `is_featured` | `boolean` | NO | `false` |
| `sort_order` | `integer` | NO | `0` |
| `available_from` | `timestamp with time zone` | YES | `NULL` |
| `available_until` | `timestamp with time zone` | YES | `NULL` |
| `vendor_contact_email` | `citext` | YES | `NULL` |
| `cash_price` | `numeric(10,2)` | YES | `NULL::numeric` |
| `total_value` | `numeric(10,2)` | YES | `NULL::numeric` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `listing_id` | `uuid` | NO | `NULL` |
| `quantity` | `integer` | NO | `1` |
| `pay_with_hp` | `boolean` | NO | `false` |
| `status` | `text` | NO | `'pending'::text` |
| `is_fulfilled` | `boolean` | NO | `false` |
| `fulfilled_at` | `timestamp with time zone` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `payment_method` | `text` | YES | `NULL` |
| `wallet_amount` | `numeric(12,2)` | NO | `0` |
| `card_amount` | `numeric(12,2)` | NO | `0` |
| `payment_reference` | `text` | YES | `NULL` |
| `wallet_tx_id` | `uuid` | YES | `NULL` |
| `hp_tx_id` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `vendor_name` | `text` | NO | `NULL` |
| `vendor_email` | `text` | NO | `NULL` |
| `vendor_phone` | `text` | YES | `NULL` |
| `service_title` | `text` | NO | `NULL` |
| `category` | `text` | NO | `NULL` |
| `description` | `text` | NO | `NULL` |
| `proposed_price` | `numeric` | NO | `NULL` |
| `status` | `text` | NO | `'pending'::text` |
| `admin_notes` | `text` | YES | `NULL` |
| `reviewed_by` | `uuid` | YES | `NULL` |
| `reviewed_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `idx_marketplace_requests_reviewed_by` ON (`reviewed_by`)
- `idx_marketplace_requests_status` ON (`status,
created_at DESC`)

**RLS Policies:**
- `Admins manage marketplace requests`

---

### Table: `public.membership_rewards`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `months` | `integer` | NO | `NULL` |
| `hp_awarded` | `integer` | NO | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `menu_item_id` | `uuid` | NO | `NULL` |
| `name` | `text` | NO | `NULL` |
| `is_required` | `boolean` | NO | `false` |
| `min_select` | `integer` | NO | `0` |
| `max_select` | `integer` | NO | `1` |
| `sort_order` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `description` | `text` | YES | `''::text` |
| `price` | `numeric(10,2)` | NO | `0` |
| `is_available` | `boolean` | YES | `true` |
| `is_archived` | `boolean` | YES | `false` |
| `sort_order` | `integer` | YES | `0` |
| `created_at` | `timestamp with time zone` | YES | `now()` |
| `updated_at` | `timestamp with time zone` | YES | `now()` |
| `group_id` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `slug` | `text` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `sort_order` | `integer` | NO | `0` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `menu_item_id` | `uuid` | NO | `NULL` |
| `name` | `text` | NO | `NULL` |
| `is_required` | `boolean` | YES | `false` |
| `min_selections` | `integer` | YES | `0` |
| `max_selections` | `integer` | YES | `1` |
| `sort_order` | `integer` | YES | `0` |
| `created_at` | `timestamp with time zone` | YES | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `variation_group_id` | `uuid` | NO | `NULL` |
| `name` | `text` | NO | `NULL` |
| `price_delta` | `numeric(10,2)` | YES | `0` |
| `is_available` | `boolean` | YES | `true` |
| `sort_order` | `integer` | YES | `0` |
| `created_at` | `timestamp with time zone` | YES | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `category_id` | `uuid` | NO | `NULL` |
| `name` | `text` | NO | `NULL` |
| `slug` | `text` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `image_url` | `text` | YES | `NULL` |
| `price` | `numeric(14,2)` | NO | `NULL` |
| `hp_earn` | `integer` | NO | `0` |
| `is_available` | `boolean` | NO | `true` |
| `is_featured` | `boolean` | NO | `false` |
| `tags` | `text[]` | NO | `'{}'::text[]` |
| `options` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `deleted_at` | `timestamp with time zone` | YES | `NULL` |
| `daily_limit` | `integer` | YES | `NULL` |
| `hp_earn_value` | `integer` | YES | `0` |
| `hp_multiplier` | `numeric(3,2)` | NO | `1.0` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `title` | `text` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `trigger_type` | `text` | NO | `NULL` |
| `trigger_value` | `integer` | NO | `1` |
| `hp_awarded` | `integer` | NO | `0` |
| `time_window` | `text` | YES | `NULL` |
| `icon_won` | `text` | YES | `NULL` |
| `icon_locked` | `text` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_by` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `social_link` | `text` | YES | `NULL` |
| `trigger_meta` | `jsonb` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `month` | `text` | NO | `NULL` |
| `total_earned` | `integer` | NO | `0` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `idx_monthly_hp_tracker_user_month` ON (`user_id,
month`)

**RLS Policies:**
- `Admins manage monthly trackers`
- `Users view own monthly tracker`

---

### Table: `public.newsletter_subscriptions`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `uuid_generate_v4()` |
| `email` | `citext` | NO | `NULL` |
| `full_name` | `text` | YES | `NULL` |
| `user_id` | `uuid` | YES | `NULL` |
| `source` | `text` | NO | `'website'::text` |
| `tags` | `text[]` | NO | `'{}'::text[]` |
| `is_confirmed` | `boolean` | NO | `false` |
| `confirmed_at` | `timestamp with time zone` | YES | `NULL` |
| `unsubscribed_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `title` | `text` | NO | `NULL` |
| `body` | `text` | NO | `NULL` |
| `channels` | `text[]` | NO | `'{}'::text[]` |
| `segment` | `jsonb` | NO | `'{}'::jsonb` |
| `action_url` | `text` | YES | `NULL` |
| `scheduled_at` | `timestamp with time zone` | YES | `NULL` |
| `status` | `text` | NO | `'draft'::text` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_by` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**Indexes:**
- `idx_notification_blasts_created_by` ON (`created_by`)
- `idx_notification_blasts_scheduled` ON (`scheduled_at`)

**RLS Policies:**
- `notification_blasts: admins all`

---

### Table: `public.notification_deliveries`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `notification_id` | `uuid` | YES | `NULL` |
| `blast_id` | `uuid` | YES | `NULL` |
| `user_id` | `uuid` | YES | `NULL` |
| `channel` | `text` | NO | `NULL` |
| `status` | `text` | NO | `'queued'::text` |
| `provider_message_id` | `text` | YES | `NULL` |
| `error_message` | `text` | YES | `NULL` |
| `delivered_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `type` | `text` | NO | `NULL` |
| `sent_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `push_enabled` | `boolean` | NO | `true` |
| `email_enabled` | `boolean` | NO | `true` |
| `order_updates` | `boolean` | NO | `true` |
| `promotions` | `boolean` | NO | `true` |
| `hp_updates` | `boolean` | NO | `true` |
| `delivery_updates` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

**RLS Policies:**
- `Users manage own notification
preferences`

---

### Table: `public.notifications`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`

- **Foreign Keys:** `user_id` → `profiles.id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | YES | `NULL` |
| `title` | `text` | NO | `NULL` |
| `body` | `text` | NO | `NULL` |
| `channel` | `text` | NO | `'in_app'::text` |
| `action_url` | `text` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `read_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `type` | `text` | NO | `'system'::text` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid(), date date` |
| `is_closed` | `boolean` | NO | `false` |
| `reason` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**RLS Policies:**
- `operating_hour_overrides: admins
all`
- `operating_hour_overrides: public
read`

---

### Table: `public.operating_hours`

- **Campus Scoped:** NO (Nullable: YES)

- **Primary Key:** `id`


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `weekday` | `integer , opens_at time without time zone, closes_at time without time zone` | NO | `NULL` |
| `is_closed` | `boolean` | NO | `false` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `order_item_id` | `uuid` | NO | `NULL` |
| `addon_id` | `uuid` | NO | `NULL` |
| `group_id` | `uuid` | YES | `NULL` |
| `name_snapshot` | `text` | NO | `NULL` |
| `price_delta_snapshot` | `numeric(10,2)` | NO | `0` |
| `quantity` | `integer` | NO | `1` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `order_id` | `uuid` | NO | `NULL` |
| `menu_item_id` | `uuid` | YES | `NULL` |
| `name_snapshot` | `text` | NO | `NULL` |
| `price_snapshot` | `numeric(14,2)` | NO | `NULL` |
| `hp_earn_snapshot` | `integer` | NO | `0` |
| `quantity` | `integer` | NO | `NULL` |
| `options_snapshot` | `jsonb` | NO | `'{}'::jsonb` |
| `line_total` | `numeric(14,2)` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `selected_variations` | `jsonb` | YES | `'[]'::jsonb` |
| `is_addon` | `boolean` | YES | `false` |
| `addon_id` | `uuid` | YES | `NULL` |
| `hp_multiplier_snapshot` | `numeric(3,2)` | NO | `1.0` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid , locked_date date` | NO | `NULL` |
| `discount_pct` | `numeric(5,2)` | NO | `10` |
| `status` | `text` | NO | `'active'::text` |
| `reminder_sent_at` | `timestamp with time zone` | YES | `NULL` |
| `reschedule_count` | `integer` | NO | `0` |
| `order_id` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `reward_type` | `text` | NO | `'discount'::text` |
| `reward_hp_amount` | `integer` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `order_id` | `uuid` | NO | `NULL` |
| `user_id` | `uuid` | NO | `NULL` |
| `rating` | `integer` | NO | `NULL` |
| `comment` | `text` | YES | `NULL` |
| `hp_rewarded` | `integer` | NO | `30` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `image_urls` | `text[]` | NO | `'{}'::text[]` |
| `is_flagged` | `boolean` | NO | `false` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `hp_awarded` | `integer , kitchen_rating smallint, rider_rating smallint` | NO | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `order_id` | `uuid` | NO | `NULL` |
| `platform` | `text` | NO | `'whatsapp'::text` |
| `hp_awarded` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `order_id` | `uuid` | NO | `NULL` |
| `status` | `order_status` | NO | `NULL` |
| `changed_by` | `uuid` | YES | `NULL` |
| `note` | `text` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `weeks` | `integer` | NO | `NULL` |
| `hp_awarded` | `integer` | NO | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `streak_weeks` | `integer` | NO | `0` |
| `longest_streak` | `integer` | NO | `0` |
| `last_order_week` | `text` | YES | `NULL` |
| `last_updated` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `order_number` | `text` | NO | `('HG-'::text || upper(substr(replace((gen_random_uuid())::text, '-'::text, ''::text), 1, 10)))` |
| `user_id` | `uuid` | YES | `NULL` |
| `guest_name` | `text` | YES | `NULL` |
| `guest_email` | `citext` | YES | `NULL` |
| `guest_phone` | `text` | YES | `NULL` |
| `status` | `order_status` | NO | `'received'::order_status` |
| `payment_status` | `payment_status` | NO | `'pending'::payment_status` |
| `subtotal` | `numeric(14,2)` | NO | `0` |
| `delivery_fee` | `numeric(14,2)` | NO | `0` |
| `discount_amount` | `numeric(14,2)` | NO | `0` |
| `total_amount` | `numeric(14,2)` | NO | `0` |
| `hp_earned` | `integer` | NO | `0` |
| `hp_redeemed` | `integer` | NO | `0` |
| `hp_credited_at` | `timestamp with time zone` | YES | `NULL` |
| `wallet_amount_used` | `numeric(14,2)` | NO | `0` |
| `card_amount_used` | `numeric(14,2)` | NO | `0` |
| `delivery_address_snapshot` | `jsonb` | NO | `'{}'::jsonb` |
| `delivery_window_id` | `uuid` | YES | `NULL` |
| `notes` | `text` | YES | `NULL` |
| `scheduled_for` | `timestamp with time zone` | YES | `NULL` |
| `payment_confirmed_at` | `timestamp with time zone` | YES | `NULL` |
| `received_at` | `timestamp with time zone` | YES | `now()` |
| `paid_at` | `timestamp with time zone` | YES | `NULL` |
| `preparing_at` | `timestamp with time zone` | YES | `NULL` |
| `ready_at` | `timestamp with time zone` | YES | `NULL` |
| `assigned_at` | `timestamp with time zone` | YES | `NULL` |
| `out_for_delivery_at` | `timestamp with time zone` | YES | `NULL` |
| `delivered_at` | `timestamp with time zone` | YES | `NULL` |
| `cancelled_at` | `timestamp with time zone` | YES | `NULL` |
| `refunded_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `promo_code_id` | `uuid` | YES | `NULL` |
| `batch_id` | `uuid` | YES | `NULL` |
| `payment_reference` | `text` | YES | `NULL` |
| `delivery_attempted_at` | `timestamp with time zone` | YES | `NULL` |
| `unclaimed_at` | `timestamp with time zone` | YES | `NULL` |
| `is_squad_order` | `boolean` | NO | `false` |
| `squad_discount_amount` | `numeric(10,2)` | NO | `0` |
| `squad_item_count` | `integer` | NO | `0` |
| `claim_token` | `uuid` | YES | `NULL` |
| `is_scheduled` | `boolean` | NO | `false` |
| `gift_included` | `boolean` | NO | `false` |
| `delivery_type` | `text` | YES | `NULL` |
| `delivery_location_id` | `uuid` | YES | `NULL` |
| `delivery_location_lat` | `double precision` | YES | `NULL` |
| `delivery_location_lon` | `double precision` | YES | `NULL` |
| `squad_name` | `text` | YES | `NULL` |
| `idempotency_key` | `text` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `order_id` | `uuid` | YES | `NULL` |
| `user_id` | `uuid` | YES | `NULL` |
| `provider` | `text` | NO | `NULL` |
| `reference` | `text` | NO | `NULL` |
| `amount` | `numeric(14,2)` | NO | `NULL` |
| `status` | `text` | NO | `'pending'::text` |
| `confirmed_at` | `timestamp with time zone` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `failure_reason` | `text` | YES | `NULL` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `NULL` |
| `email` | `citext` | NO | `NULL` |
| `full_name` | `text` | YES | `NULL` |
| `phone` | `text, date_of_birth date` | YES | `NULL` |
| `faculty` | `text` | YES | `NULL` |
| `department` | `text` | YES | `NULL` |
| `photo_url` | `text` | YES | `NULL` |
| `role` | `user_role` | NO | `'student'::user_role` |
| `preferences` | `jsonb` | NO | `'{}'::jsonb` |
| `hp_balance` | `integer` | NO | `0` |
| `wallet_balance` | `numeric(14,2)` | NO | `0` |
| `current_tier_id` | `uuid` | YES | `NULL` |
| `tier_grace_started_at` | `timestamp with time zone` | YES | `NULL` |
| `tier_lost_at` | `timestamp with time zone` | YES | `NULL` |
| `referral_code` | `text` | YES | `NULL` |
| `onboarding_completed_at` | `timestamp with time zone` | YES | `NULL` |
| `last_seen_at` | `timestamp with time zone` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `push_enabled` | `boolean` | NO | `false` |
| `email_notifications` | `boolean` | NO | `true` |
| `has_scheduled_order` | `boolean` | NO | `false` |
| `deactivated_at` | `timestamp with time zone` | YES | `NULL` |
| `deactivated_by` | `uuid` | YES | `NULL` |
| `referred_by` | `uuid` | YES | `NULL` |
| `tier_grace_ends_at` | `timestamp with time zone` | YES | `NULL` |
| `last_hp_activity_at` | `timestamp with time zone` | YES | `NULL` |
| `deactivation_reason` | `text` | YES | `NULL` |
| `jwt_version` | `integer` | NO | `0` |
| `last_activity_at` | `timestamp with time zone` | YES | `NULL` |
| `hp_earned_120day` | `integer` | NO | `0` |
| `graduation_claimed` | `boolean` | NO | `false` |
| `top4_finish_count` | `integer` | NO | `0` |
| `academic_level` | `text` | YES | `NULL` |
| `department_id` | `uuid` | YES | `NULL` |
| `campus_id` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `promo_code_id` | `uuid` | NO | `NULL` |
| `user_id` | `uuid` | YES | `NULL` |
| `order_id` | `uuid` | YES | `NULL` |
| `discount_amount` | `numeric(14,2)` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `code` | `citext` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `discount_type` | `text` | NO | `NULL` |
| `discount_value` | `numeric(14,2)` | NO | `NULL` |
| `scope` | `text` | NO | `'cart'::text` |
| `applicable_item_ids` | `uuid[]` | NO | `'{}'::uuid[]` |
| `applicable_category_ids` | `uuid[]` | NO | `'{}'::uuid[]` |
| `max_uses` | `integer` | YES | `NULL` |
| `max_uses_per_user` | `integer` | YES | `NULL` |
| `starts_at` | `timestamp with time zone` | YES | `NULL` |
| `ends_at` | `timestamp with time zone` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `used_count` | `integer` | NO | `0` |
| `min_order_amount` | `numeric(12,2)` | NO | `0` |
| `created_by` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `subscription` | `jsonb` | NO | `NULL` |
| `device_label` | `text` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `code` | `text` | NO | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

**Unique Constraints:**
- `referral_codes_code_key`: UNIQUE (`code`)
- `referral_codes_user_id_key`: UNIQUE (`user_id`)

**RLS Policies:**
- `referral_codes: admins all`
- `referral_codes: users read own`

---

### Table: `public.referral_milestones`

- **Campus Scoped:** NO (Nullable: YES)


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `referral_count` | `integer` | NO | `NULL` |
| `hp_awarded` | `integer` | NO | `NULL` |
| `is_repeating` | `boolean` | NO | `false` |
| `repeat_interval` | `integer` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `referrer_id` | `uuid` | NO | `NULL` |
| `referred_user_id` | `uuid` | NO | `NULL` |
| `trigger_order_id` | `uuid` | YES | `NULL` |
| `status` | `text` | NO | `'pending'::text` |
| `hp_awarded` | `integer` | NO | `0` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `reward_id` | `uuid` | NO | `NULL` |
| `status` | `text` | NO | `'pending'::text` |
| `hp_cost_snapshot` | `integer` | YES | `NULL` |
| `fulfilled_at` | `timestamp with time zone` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `notes` | `text` | YES | `NULL` |
| `fulfilled_by` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `name` | `text` | NO | `NULL` |
| `description` | `text` | YES | `NULL` |
| `hp_cost` | `integer` | NO | `NULL` |
| `reward_type` | `text` | NO | `NULL` |
| `stock_quantity` | `integer` | YES | `NULL` |
| `min_tier_id` | `uuid` | YES | `NULL` |
| `is_active` | `boolean` | NO | `true` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `expires_at` | `timestamp with time zone` | YES | `NULL` |
| `max_per_user` | `integer` | NO | `1` |
| `image_url` | `text` | YES | `NULL` |
| `flash_enabled` | `boolean` | YES | `false` |
| `flash_hp_cost` | `integer` | YES | `NULL` |
| `flash_max_qty` | `integer` | YES | `NULL` |
| `flash_slots_remaining` | `integer` | YES | `NULL` |
| `flash_starts_at` | `timestamp with time zone` | YES | `NULL` |
| `flash_ends_at` | `timestamp with time zone` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `is_available` | `boolean` | NO | `false` |
| `availability_updated_at` | `timestamp with time zone` | YES | `NULL` |
| `location_lat` | `double precision` | YES | `NULL` |
| `location_lng` | `double precision` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `menu_item_id` | `uuid` | NO | `NULL` |
| `quantity` | `integer` | NO | `1` |
| `notes` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `title` | `text` | NO | `NULL` |
| `body` | `text` | NO | `NULL` |
| `frequency` | `text` | NO | `NULL` |
| `send_time` | `text` | NO | `NULL` |
| `target_segment` | `text` | NO | `'all'::text` |
| `is_active` | `boolean` | NO | `true` |
| `last_sent_at` | `timestamp with time zone` | YES | `NULL` |
| `next_send_at` | `timestamp with time zone` | YES | `NULL` |
| `created_by` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `order_id` | `uuid` | NO | `NULL` |
| `user_id` | `uuid` | YES | `NULL` |
| `email` | `text` | NO | `NULL` |
| `hp_share` | `integer` | NO | `0` |
| `invite_sent` | `boolean` | NO | `false` |
| `is_registered` | `boolean` | NO | `false` |
| `referral_attributed` | `boolean` | NO | `false` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `key` | `text` | NO | `NULL` |
| `title` | `text` | YES | `NULL` |
| `section_type` | `text` | NO | `NULL` |
| `content` | `jsonb` | NO | `NULL` |
| `sort_order` | `integer` | NO | `0` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `published_at` | `timestamp with time zone` | YES | `NULL` |
| `created_by` | `uuid` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `key` | `text` | NO | `NULL` |
| `value` | `jsonb` | NO | `'{}'::jsonb` |
| `description` | `text` | YES | `NULL` |
| `updated_by` | `uuid` | YES | `NULL` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `is_public` | `boolean` | NO | `false` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `label` | `text` | YES | `NULL` |
| `line1` | `text` | NO | `NULL` |
| `line2` | `text` | YES | `NULL` |
| `hostel` | `text` | YES | `NULL` |
| `landmark` | `text` | YES | `NULL` |
| `city` | `text` | NO | `'Akure'::text` |
| `state` | `text` | NO | `'Ondo'::text` |
| `latitude` | `numeric(10,7)` | YES | `NULL` |
| `longitude` | `numeric(10,7)` | YES | `NULL` |
| `is_default` | `boolean` | NO | `false` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `milestone_id` | `uuid` | NO | `NULL` |
| `completed_at` | `timestamp with time zone` | NO | `now()` |
| `hp_awarded` | `integer` | NO | `0` |
| `period_key` | `text` | YES | `NULL` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `uuid_generate_v4()` |
| `user_id` | `uuid` | NO | `NULL` |
| `tier_id` | `uuid` | NO | `NULL` |
| `event` | `text` | NO | `NULL` |
| `hp_at_event` | `integer` | NO | `0` |
| `previous_tier_id` | `uuid` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `provider` | `text` | NO | `NULL` |
| `account_number` | `text` | NO | `NULL` |
| `account_name` | `text` | NO | `NULL` |
| `bank_name` | `text` | NO | `NULL` |
| `provider_customer_id` | `text` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `is_active` | `boolean` | NO | `true` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `amount` | `numeric(14,2)` | NO | `NULL` |
| `provider` | `text` | NO | `NULL` |
| `status` | `text` | NO | `'pending'::text` |
| `callback_url` | `text` | YES | `NULL` |
| `provider_reference` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `confirmed_at` | `timestamp with time zone` | YES | `NULL` |
| `failure_reason` | `text` | YES | `NULL` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `type` | `text` | NO | `NULL` |
| `amount` | `numeric(14,2)` | NO | `NULL` |
| `balance_after` | `numeric(14,2)` | NO | `NULL` |
| `reason` | `text` | YES | `NULL` |
| `reference_type` | `text` | YES | `NULL` |
| `reference_id` | `uuid` | YES | `NULL` |
| `provider` | `text` | YES | `NULL` |
| `provider_reference` | `text` | YES | `NULL` |
| `issued_by_admin_id` | `uuid` | YES | `NULL` |
| `metadata` | `jsonb` | NO | `'{}'::jsonb` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `user_id` | `uuid` | NO | `NULL` |
| `amount` | `numeric(12,2)` | NO | `NULL` |
| `bank_code` | `text` | NO | `NULL` |
| `account_number` | `text` | NO | `NULL` |
| `account_name` | `text` | NO | `NULL` |
| `narration` | `text` | YES | `NULL` |
| `reference` | `text` | NO | `NULL` |
| `status` | `text` | NO | `'pending'::text` |
| `processed_at` | `timestamp with time zone` | YES | `NULL` |
| `failure_reason` | `text` | YES | `NULL` |
| `metadata` | `jsonb` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `user_id` | `uuid` | NO | `NULL` |
| `balance` | `numeric(14,2)` | NO | `0` |
| `currency` | `text` | NO | `'NGN'::text` |
| `updated_at` | `timestamp with time zone` | NO | `now()` |
| `created_at` | `timestamp with time zone` | NO | `now()` |

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


| Column Name | Data Type | Nullable | Default |
|-------------|-----------|----------|---------|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `event_type` | `text` | NO | `NULL` |
| `provider` | `text` | YES | `NULL` |
| `reference` | `text` | NO | `''::text` |
| `payload` | `jsonb` | YES | `NULL` |
| `status` | `text` | NO | `'processed'::text` |
| `error` | `text` | YES | `NULL` |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `processed_at` | `timestamp with time zone` | YES | `NULL` |

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

## SECTION 3: RPC FUNCTIONS

List of atomic PostgreSQL RPC functions defined in Supabase and invoked by Python service/route handlers:


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


---
## SECTION 5: BACKGROUND JOBS & SCHEDULED TASKS

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
## SECTION 6: EXTERNAL INTEGRATIONS

### 1. Paystack Payment Gateway

- **Purpose**: Online card checkout, split payments, and dedicated Wema Wema virtual bank accounts.

- **Endpoints Handled**: `POST /api/wallet/fund/card`, `POST /api/wallet/fund/bank`, `POST /api/webhooks/paystack`

- **Webhook Security**: Verifies HMAC SHA512 signature (`X-Paystack-Signature` header against `PAYSTACK_WEBHOOK_SECRET`).

- **Idempotency**: Webhook events check `payment_webhooks` table on `(provider, event_type, reference)` UNIQUE constraint.


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
## SECTION 7: SYSTEM SETTINGS

The `system_settings` table stores runtime configuration key-values. Settings can be global (`campus_id IS NULL`) or overridden per-campus (`campus_id = <uuid>`).


| Setting Key | Default Value | Purpose | Consuming Files |

|-------------|---------------|---------|-----------------|

| `hp_multiplier` | `1` | Active loyalty points earn multiplier (e.g., 2 for double HP events) | `app/services/hp_service.py` |

| `multiplier_expires_at` | `NULL` | Expiration timestamp for active HP multiplier event | `app/services/hp_service.py` |

| `daily_checkin_hp` | `10` | HP awarded for daily app check-in | `app/routes/daily_checkin.py` |

| `free_side_options` | `["Coleslaw", "Extra Sauce", "Soft Drink"]` | Admin-configurable options for free side credits | `app/routes/free_sides.py` |

| `first_order_gift_enabled` | `true` | Toggle for first-order welcome gift | `app/services/gift_service.py` |

| `first_order_gift_item_name` | `"First-Order Gift — Hot Dog"` | Display name of welcome gift item | `app/services/gift_service.py` |

| `launch_window_end_date` | `"2026-12-31"` | End date for welcome gift eligibility window | `app/services/gift_service.py` |

| `monthly_pending_cap` | `1000` | Monthly cap on pending HP unlock | `app/services/streak_service.py` |

| `graduation_min_level` | `400` | Minimum academic level for graduation reward eligibility | `app/routes/graduation.py` |

| `whatsapp_support_number` | `"2348000000000"` | WhatsApp customer support contact phone number | `app/routes/storefront.py` |

| `whatsapp_support_enabled` | `true` | Toggle floating WhatsApp support button in app | `app/routes/storefront.py` |

| `whatsapp_support_message` | `"Hello I need help with my order"` | Pre-filled support message template | `app/routes/storefront.py` |

| `notification_throttle_window_minutes` | `30` | Time window for notification rate limiting | `app/services/notification_service.py` |

| `notification_throttle_max_per_window` | `20` | Max non-critical notifications per window | `app/services/notification_service.py` |
