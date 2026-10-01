# Free sides, reward consumption, expired tickets

Three gaps confirmed against the live test 2 database on 2026-10-01, and what was
changed for each. The database side is **applied and verified on test 2** — see
[`migrations/2026-10-01_free_sides_reward_consumption.sql`](../migrations/2026-10-01_free_sides_reward_consumption.sql),
now a record of what is live plus verification queries (**not** a script — the
canonical definitions live in the database; re-running the old draft would
overwrite them).

---

## 1. Free-side credits were never spent

**Confirmed:** no function in the DB references `free_side_*`, and
`consume_free_side_selections()` in `app/routes/free_sides.py` was never called
from anywhere. `POST /free-sides/select` wrote a `cart_free_side_selections` row
and the credit stayed forever.

**Change — one migration, one call site**

| File | Change |
|------|--------|
| `migrations/…free_sides_reward_consumption.sql` | **Live on test 2.** `hg_consume_free_sides_atomic(p_user_id, p_order_id, p_campus_id)` — per selection: lock the oldest usable credit (`FOR UPDATE SKIP LOCKED`), decrement it, insert the ₦0 `order_items` line (now carrying `campus_id`), delete the selection. One transaction; retry-safe because the selection disappears as it is consumed. The applied version also takes row locks on the selections, so two simultaneous checkouts cannot double-spend. `service_role` only. |
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

**Confirmed:** `hg_create_order_atomic` stored `redemption_id` on the order;
nothing wrote `reward_redemptions.attached_order_id`; the only statuses were
`pending` and `fulfilled`, so "used" was unrepresentable. **Fixed in the database
itself:** `hg_create_order_atomic` now claims `p_redemption_id` inside the same
transaction as the order, and refuses the whole order when the reward is spent,
unfulfilled or not the buyer's.

**Change**

| File | Change |
|------|--------|
| `migrations/…sql` | **Live on test 2.** `reward_redemptions.used_at` + the partial index `ix_reward_redemptions_attached_order`, and `hg_claim_reward_redemption_for_order(p_redemption_id, p_user_id, p_order_id)` — a conditional UPDATE matching `attached_order_id IS NULL AND status = 'fulfilled'`. With the claim now inside `hg_create_order_atomic`, this helper is a safety net: it returns `claimed = true` with `already_attached = true` for an order that already carries the reward. `service_role` only. |
| `app/services/order_service.py` | Before the order is priced: `_assert_redemption_claimable()` rejects a spent/unfulfilled/foreign reward with a 400 (kept, and now a courtesy pre-check — the database is the authority). After the order exists: `_claim_reward_redemption()` runs as a safety net; `already_attached = true` counts as success, and only a genuine refusal logs an ERROR. `_normalize_rpc_error()` maps the database's *"Reward redemption is not available (already used, not fulfilled, or not yours)"* to `MSG.REWARD_REDEMPTION_UNAVAILABLE`, so the refusal is a clean **400**, not a raw RPC string or a 500. |

**Why not only the RPC:** the pre-check gives the customer a clean error instead
of a charge-then-fail, and the post-create claim is the enforcement. A reward that
loses the race is a rare, logged, reconcilable event — versus the current
unlimited reuse.

**Reconcile what already happened** (query 3d in the migration record):

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
| `app/routes/events.py` | New `_event_has_priced_tier()` and `_registrants_for_event()`. A priced event lists/emails only `payment_status in ('paid','not_required')`; cancelled and expired tickets are excluded even if once paid. Responses carry `total_all_statuses`, `excluded_unpaid`, `excluded_cancelled`, `include_unpaid`, `priced_event`; the JSON/CSV registrant list and the host email gained a **Payment** column, and the email states what was excluded. Override with `?include_unpaid=true` (list) or `include_unpaid: true` (email body). |

**No Python expiry job — deliberately.** The database owns it:
**`hg_event_ticket_payment_expiry`** runs every 15 minutes, cancels expired
unpaid tickets, sets `payment_status = 'expired'` and releases the tier seat. A
second job in this repo (originally built at 5-minute cadence) would race it, so
it was removed along with its Celery beat entry and its
`/api/admin/cron/cancel-expired-event-tickets` trigger. The window before the
database job runs is covered by the `payment_status` filter above, which drops
anything not `paid` / `not_required` — `expired` included.

**Resolved (was STEP 0e)** — `event_tickets.status` is plain text with no
restrictive CHECK constraint, `cancelled` is the word the database job writes,
`payment_status` becomes `expired`, and there is no `cancellation_reason` column.
Nothing left to pin down here.

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
