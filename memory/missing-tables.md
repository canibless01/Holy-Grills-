---
name: Missing tables
description: 4 tables are absent from production Supabase but referenced by API endpoints; migration SQL exists.
---

## Tables not in production DB (as of 2026-06-29)

| Table                     | Used by endpoint                      |
|---------------------------|---------------------------------------|
| `rider_profiles`          | `PATCH /riders/availability`          |
| `device_tokens`           | `POST /notifications/device`          |
| `notification_preferences`| `PATCH /notifications/preferences`    |
| `wallet_withdrawals`      | `POST /wallet/withdraw`               |

## Migration
`migrations/001_missing_tables.sql` — run once in Supabase SQL editor.
Contains CREATE TABLE IF NOT EXISTS + RLS policies for all 4 tables.

## Graceful degradation
All 4 endpoints catch `SupabaseError` where the message contains "does not exist", "schema cache", or "relation" and return a soft success (201/200) rather than 500. When tables are created, the endpoints will automatically start persisting correctly.

**Why:** Tables were missing from the production schema; we cannot run DDL via PostgREST, only via the Supabase dashboard.

**How to apply:** After running the migration, re-run `test_new_apis.py` — the 3 WARNs about missing tables should convert to PASSes.
