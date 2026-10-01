# Database audit — test 2 (`zaxdkrmzyibkvlsrgmvq`)

Scope: this project only. Production is never touched. Every check in here is
read-only; the only writes anywhere in the tooling are the E2E suite's own
fixtures, which it deletes again.

**How to run**

```bash
make audit                 # inventory + (if SUPABASE_DB_URL is set) RLS/grants/RPC bodies
make audit ARGS="--search credit"   # "does something for this already exist?"
make audit ARGS="--dump-defs hg_create_order,hg_mark_order_paid,register_for_event_guest_paid"
make audit ARGS="--out docs/audit-report.md --json docs/audit-report.json"
```

`SUPABASE_DB_URL` (Supabase → Project Settings → Database → Connection string →
URI) is the switch that turns on the deep pass. PostgREST **cannot** expose RLS
policies, grants or function bodies, so the four RPC questions and the whole
RLS/grants audit need that connection. Put it in `.env`; it is never printed and
never leaves the machine.

**Report status** (updated after the live check of 2026-10-01)

| Area | Status |
|------|--------|
| Q1 free sides | **answered — never consumed anywhere**; fix shipped |
| Q2 reward redemption | **answered — reuse is possible**; fix shipped |
| Q3 event ticket payment_status | **answered — `pending_payment` / `pending`, 30-min expiry, no cleanup**; fix shipped |
| Q4 roles | answered from code (kitchen + rider accepted) |
| RLS, grants, advisor equivalents | tool ready; run `make audit` with `SUPABASE_DB_URL` |
| Duplicate search | tool ready (`make audit ARGS="--search …"`) |

**Correction:** the order RPC is **`hg_create_order_atomic`**, not `hg_create_order`
(the probe list in `scripts/db_audit.py` has been corrected).

---

## 1. The four questions

### Q1 — does the order RPC consume free-side selections/credits?

**DB side: confirmed NO** (checked live) — no function in the database references
`free_side_*`, `cart_free_side_selections` or `free_side_credits`.

**Python side: also NO — the consumer is dead code.** Quoted from the source:

* `app/routes/free_sides.py:298` defines `consume_free_side_selections(write_db, user_id, campus_id, order_id)`.
* Its docstring: *"…not yet wired into order_service.create_order() as of this pass; see CROSS_FILE_DEPENDENCIES.md."*
* `consume_free_side_selections` is **never called anywhere** in the repo (only its definition matches).
* `app/services/order_service.py` contains **zero** occurrences of `free_side`.
* `app/routes/free_sides.py:192` and `:270` still claim it *is* called from `create_order` — stale comments.

Net effect: `POST /free-sides/select` writes a `cart_free_side_selections` row and
nothing ever spends the `free_side_credits` row or adds a ₦0 `order_items` line.

**Fix shipped** — `_consume_free_sides` in `app/services/order_service.py` runs
immediately after `hg_create_order_atomic` returns and calls the new atomic RPC
`hg_consume_free_sides_atomic` (`migrations/2026-10-01_free_sides_reward_consumption.sql`),
which does the credit decrement, the ₦0 order line and the selection deletion in
one transaction. The old Python consumer stays as a fallback when the RPC is not
installed. See [FREE_SIDES_AND_REWARDS.md](FREE_SIDES_AND_REWARDS.md).

### Q2 — does the order RPC mark a reward redemption as used after delivery?

**Python side: no path exists.** `reward_redemptions` appears only in
`app/routes/rewards.py` (create, fulfil, reject, delivery-choice) — nothing in the
order flow, delivery flow or the delivery-HP service updates it.

**DB side: confirmed by the live check** — `hg_create_order_atomic` stores
`redemption_id` on the order, but nothing sets `reward_redemptions.attached_order_id`
and there is no used/consumed status (only `pending` / `fulfilled`). A fulfilled
reward could therefore ride unlimited orders.

**Fix shipped** — `hg_claim_reward_redemption_for_order` (conditional UPDATE,
first writer wins) plus a pre-check in `order_service.create_order` that returns a
clear 400 for an already-used reward, and a post-create claim whose failure is
logged as an error rather than swallowed.

### Q3 — what `payment_status` do `register_for_event*` give an unpaid card ticket?

**Python side: the RPC decides.** `app/routes/events.py:601` reads
`rpc_res.get("payment_status")` straight from the RPC result, with a
`"not_required"` fallback at `:606`/`:700`. There is no Python assignment of
`pending` anywhere — so this is entirely an RPC/column-default question.

**DB side: confirmed by the live check** — both `register_for_event*` RPCs create
card tickets as `status = pending_payment`, `payment_status = pending`, with a
30-minute `payment_expires_at`, and nothing ever cancelled expired ones.

**Fix shipped**
* `app/routes/events.py` — `_registrants_for_event()` filters a priced event to
  `payment_status in ('paid','not_required')` for both the registrant list and the
  host email, adds a Payment column, and reports `excluded_unpaid` /
  `total_all_statuses` (`?include_unpaid=true`, or `include_unpaid` in the body,
  overrides).
* `app/tasks/scheduled.py` — new `cancel_expired_event_tickets` job (every 5 min)
  cancels expired `pending_payment` tickets, releases the tier seat, notifies the
  buyer; wired into the beat schedule, `/api/admin/cron/cancel-expired-event-tickets`
  and the cron-status table.

### Q4 — does `PATCH /admin/users/<id>/role` accept kitchen and rider?

**Answered from code: yes — with a campus-admin restriction.**

* `VALID_ROLES = {student, admin, kitchen, rider, super_admin}` (`app/constants.py:8`); the route rejects anything else with `ADMIN_INVALID_ROLE` (400).
* `app/routes/admin.py:289` — a **campus admin** (`require_role("admin")`, not super_admin) may only change a role *within* `_CAMPUS_ADMIN_MANAGED_ROLES = ("student", "kitchen", "rider")` (`admin.py:46`); anything else → 403 `ADMIN_ROLE_CHANGE_SUPER_ONLY`. So a campus admin **can** set kitchen and rider, but cannot create admins.
* `admin.py:300` — leaving `super_admin`, or a target with no campus, requires a campus in the request.
* Self-role-change is refused (`ADMIN_CANNOT_CHANGE_OWN_ROLE`, `admin.py:269`).

**DB side: scripted.** Probe `Q4_role_check_constraint` returns the CHECK
constraints on `profiles` and reports whether `kitchen`/`rider` are among them —
if absent, the five-role rule is enforced only in Python, so any direct
service-role write could set an unknown role.

---

## 2. RLS, grants and advisor checks

All of the following run in the audit's SQL pass and are reported with the same
severity model (`high` / `medium` / `low`):

| Check | Source | Why it matters |
|-------|--------|----------------|
| RLS enabled / forced per table | `pg_class.relrowsecurity` | an RLS-less table with an `anon` grant is world-readable through PostgREST |
| RLS on but zero policies | `pg_policies` count | silently service-role-only; often an oversight |
| Policy roles + command + qual | `pg_policies` | flags `anon`/`PUBLIC` INSERT/UPDATE/DELETE policies |
| Table grants per role | `information_schema.role_table_grants` | a write grant to `anon`/`PUBLIC` is a bypass even with RLS on |
| Function grants per role | `information_schema.routine_privileges` | who can call each RPC |
| `SECURITY DEFINER` without pinned `search_path` | `pg_proc.proconfig` | classic privilege-escalation vector |
| `SECURITY DEFINER` executable by `anon` | joined with `routine_privileges` | unauthenticated callers running as the definer |
| Views without `security_invoker` | `pg_class.reloptions` | views bypass the underlying tables' RLS |
| Reachability with the **anon** key | REST, every table | the empirical answer: what an unauthenticated caller can actually hit |
| Duplicate/near-duplicate tables and functions | name clustering | "parallel sessions built duplicates before" |

The Supabase dashboard's own **Advisors → Security** page is the vendor view of
the same ground; the script covers it so it can run in CI without dashboard
access. Run both — the advisor also flags leaked-password protection and
extension versions.

---

## 3. Findings so far (evidence-backed)

| # | Severity | Finding | Where |
|---|----------|---------|-------|
| F1 | high (functional) | Free-side credits are never consumed at checkout; `consume_free_side_selections()` is dead code and two comments claim otherwise | `app/routes/free_sides.py:192,270,298`; `app/services/order_service.py` (0 refs) |
| F2 | medium | `reward_redemptions` is never marked used outside `rewards.py` — the closing step lives (or does not live) in an RPC | `app/routes/rewards.py` only |
| F3 | low | Docs reference files that do not exist in this checkout: `CROSS_FILE_DEPENDENCIES.md`, `migrations/schema.sql`, `scripts/seed.py`, `scripts/seed.sql` | repo root |

---

## 4. Open items and answer path

1. **`SUPABASE_DB_URL`** — needed for Q1–Q3, RLS, grants and advisor checks. Add it to `.env` and run `make audit`.
2. If you would rather not hand over a DB connection: run
   `make audit ARGS="--dump-defs hg_create_order,hg_mark_order_paid,register_for_event_paid,register_for_event_guest_paid"`
   and paste the output — same answers, no credentials.
3. `CROSS_FILE_DEPENDENCIES.md` is referenced by the code but missing — is it somewhere else, or should the reference be dropped?

Fixes are queued behind the probe results, because both F1 and F2 have the same
trap: if the RPC already does the work, the Python "fix" would double-apply it.
