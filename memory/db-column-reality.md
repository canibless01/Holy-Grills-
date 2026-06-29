---
name: DB column reality
description: Actual production column names for tables where assumptions were wrong — prevents future 500 errors.
---

## Critical column corrections

**`order_items`** — no `unit_price`; use `price_snapshot` (unit) or `line_total` (total).

**`orders`** — no `payment_method`, no `refund_amount`, no `refund_reason`, no `refunded_by`.
- Payment split via `wallet_amount_used` and `card_amount_used`.
- Refund info stored in `notes` (text) and `refunded_at` (timestamp).
- `refunded_at` exists; `deactivated_at`, `deactivation_reason` also exist on `profiles`.

**`hp_transactions`** — no `notes`; use `source` (text) or `metadata` (jsonb).

**`menu_categories`** — no `image_url`, no `updated_at`. Real columns: `id, name, slug, description, sort_order, is_active, created_at`.

**`profiles`** — no `deletion_requested_at`, no `deletion_reason`.
- Use `deactivated_at` + `deactivation_reason` for account deletion.

**Why:** These were found by running test_new_apis.py against the live Supabase DB and reading PostgREST error messages.

**How to apply:** Before writing any new endpoint that touches these tables, grep for the column name in this file first. When in doubt, check live column list via `GET /rest/v1/<table>?limit=1`.
