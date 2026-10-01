# Free sides, reward consumption, expired tickets

Three gaps confirmed against the live test 2 database on 2026-10-01, and what was
changed for each. Database work lives in
[`migrations/2026-10-01_free_sides_reward_consumption.sql`](../migrations/2026-10-01_free_sides_reward_consumption.sql);
**run its STEP 0 checks before STEP 1–2** and tell me if any name is already taken.

---

## 1. Free-side credits were never spent

**Confirmed:** no function in the DB references `free_side_*`, and
`consume_free_side_selections()` in `app/routes/free_sides.py` was never called
from anywhere. `POST /free-sides/select` wrote a `cart_free_side_selections` row
and the credit stayed forever.

**Change — one migration, one call site**

| File | Change |
|------|--------|
| `migrations/…free_sides_reward_consumption.sql` | `hg_consume_free_sides_atomic(p_user_id, p_order_id, p_campus_id)` — for each selection: lock the oldest usable credit (`FOR UPDATE SKIP LOCKED`), decrement it, insert the ₦0 `order_items` line, delete the selection. One transaction; retry-safe because the selection disappears as it is consumed. `service_role` only. |
| `app/services/order_service.py` | `_consume_free_sides()` runs right after `hg_create_order_atomic` returns. Feature-flag gated (`free_side_credits`), **never fails the order** — a failure logs a warning and leaves the selection for the next checkout. Falls back to the Python consumer if the RPC is absent. |
| `app/routes/free_sides.py` | Removed the two comments claiming `create_order` already called the consumer, and dropped the `CROSS_FILE_DEPENDENCIES.md` reference from the docstring. |

Why the RPC is a separate function rather than inline in `hg_create_order_atomic`:
it keeps that function (which you have already verified) untouched, and the
consumption is atomic in itself. The residual window is "order created, RPC call
failed" — harmless, because the seat/credit is not lost, only deferred.

**Test after applying**

```sql
SELECT id, user_id, credits_remaining, used_at FROM free_side_credits   WHERE user_id = '<u>';
SELECT id FROM cart_free_side_selections                                WHERE user_id = '<u>';
SELECT name_snapshot, price_snapshot FROM order_items WHERE order_id = '<o>' AND price_snapshot = 0;
```

---

## 2. A fulfilled reward could be used on unlimited orders

**Confirmed:** `hg_create_order_atomic` stores `redemption_id` on the order;
nothing writes `reward_redemptions.attached_order_id`; the only statuses are
`pending` and `fulfilled`, so "used" was unrepresentable.

**Change**

| File | Change |
|------|--------|
| `migrations/…sql` | Adds `reward_redemptions.used_at` (idempotent) + index on `attached_order_id`, and `hg_claim_reward_redemption_for_order(p_redemption_id, p_user_id, p_order_id)`: a conditional UPDATE that only matches `attached_order_id IS NULL AND status = 'fulfilled'`, so the first caller wins and every later call returns `claimed = false` with a reason. `service_role` only. |
| `app/services/order_service.py` | Before the order is priced: `_assert_redemption_claimable()` rejects a spent/unfulfilled/foreign reward with a 400. After the order exists: `_claim_reward_redemption()` attaches it; a lost race is logged at ERROR level because the customer already received the discount on that order. |

**Why not only the RPC:** the pre-check gives the customer a clean error instead
of a charge-then-fail, and the post-create claim is the enforcement. A reward that
loses the race is a rare, logged, reconcilable event — versus the current
unlimited reuse.

**Reconcile what already happened** (STEP 0d in the migration):

```sql
SELECT redemption_id, count(*) FROM orders
WHERE redemption_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1;
```

---

## 3. Abandoned card tickets held seats and appeared in host emails

**Confirmed:** both `register_for_event*` RPCs write `status = pending_payment`,
`payment_status = pending`, `payment_expires_at = now() + 30 min`. Nothing
cancelled expired rows, and `send-registrants-to-host` had no payment filter.

**Change**

| File | Change |
|------|--------|
| `app/routes/events.py` | New `_event_has_priced_tier()` and `_registrants_for_event()`. A priced event lists/emails only `payment_status in ('paid','not_required')`, and cancelled tickets are excluded even if once paid. Responses carry `total_all_statuses`, `excluded_unpaid`, `excluded_cancelled`, `include_unpaid`, `priced_event`; the JSON/CSV registrant list and the host email gained a **Payment** column, and the email states what was excluded. Override with `?include_unpaid=true` (list) or `include_unpaid: true` (email body). |

**No Python expiry job — deliberately.** The database already runs one every
15 minutes that cancels expired unpaid tickets and releases the tier seat. A
second job in this repo (originally built at 5-minute cadence) would race it, so
it was removed along with its Celery beat entry and its
`/api/admin/cron/cancel-expired-event-tickets` trigger. The 15-minute gap before
the database job runs is covered by the `payment_status` filter above.

**Resolved (was STEP 0e)** — `event_tickets.status` is plain text with no
restrictive CHECK constraint, `cancelled` is the word the database job already
uses, and there is no `cancellation_reason` column. Nothing left to pin down
here; the migration's STEP 0e is now informational only.

---

## Test accounts for the audit (test 2)

Created by the project owner; used by `make smoke`/`make e2e` and the RLS
impersonation pass. All `@holygrills.test` — never production.

| Email | Role | Campus | `auth.users.id` |
|-------|------|--------|-----------------|
| `claude.audit.test1@holygrills.test` | student | FUTA Main | `3d022e3c-92cb-4841-abba-1a7869a0dda4` |
| `claude.audit.admin@holygrills.test` | admin | FUTA Main | `fe363f5a-fe10-4273-bc0c-8671d92d0436` |
| `claude.audit.superadmin@holygrills.test` | super_admin | — | `b3c99cad-a4af-4eb8-af91-432aeb9a3fb5` |

`.env` (local, git-ignored) takes:

```ini
E2E_CAMPUS_ID=70000001-cafe-cafe-cafe-000000000001
E2E_ADMIN_EMAIL=claude.audit.admin@holygrills.test
E2E_ADMIN_PASSWORD=ClaudeAudit!Admin1
E2E_STUDENT_ID=3d022e3c-92cb-4841-abba-1a7869a0dda4
E2E_ADMIN_ID=fe363f5a-fe10-4273-bc0c-8671d92d0436
E2E_SUPERADMIN_ID=b3c99cad-a4af-4eb8-af91-432aeb9a3fb5
```

The superadmin UUID came through the message wrapped across two lines; I joined
it as `b3c99cad-a4af-4eb8-af91-432aeb9a3fb5`. **Check the last group** — if it is
wrong, RLS impersonation for that role silently sees nothing.

Two ways to use the accounts:

```bash
# read-only E2E as the real student (no writes to a real account)
make smoke BASE_URL=http://localhost:5000 LOGIN_EMAIL=claude.audit.test1@holygrills.test \
           LOGIN_PASSWORD='ClaudeAudit!Test1'

# RLS audit as each role, inside a rolled-back transaction (SELECTs only)
make audit ARGS="--impersonate student:3d022e3c-… --impersonate admin:fe363f5a-… \
                 --impersonate superadmin:b3c99cad-…"
```

Admin passwords belong in `.env` only for test 2, and should be rotated after the
audit — anything in that file is available to whoever can read the shell.
