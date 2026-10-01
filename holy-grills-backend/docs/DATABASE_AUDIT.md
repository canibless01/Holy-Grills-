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

### Applied on test 2 — database-side changes that affect this repo

| Change | Repo-side effect |
|--------|------------------|
| `hg_create_order_atomic` claims `p_redemption_id` inside the order transaction and refuses the whole order with *"Reward redemption is not available (already used, not fulfilled, or not yours)"* | `order_service._normalize_rpc_error()` maps that text to `MSG.REWARD_REDEMPTION_UNAVAILABLE` → clean **400**. `_assert_redemption_claimable()` (pre-check) and the post-order claim call both stay; `already_attached = true` now counts as success |
| `hg_consume_free_sides_atomic` live, with row locks on the selections and `campus_id` on the ₦0 order line | `_consume_free_sides()` calls it as-is (signature unchanged); the Python consumer stays only as a fallback |
| `hg_hp_grant_segment` now requires the caller to be an admin of `p_campus` or a super_admin (service key still allowed) | `POST /admin/hp/bulk-grant` always passes `resolve_scoped_campus_id()` — the admin's own campus for staff, the requested campus or `None` (all campuses) for super_admin. A campus-less admin now gets a clean **400** (`MSG.ACCOUNT_NO_CAMPUS`) instead of an unscoped query, and a database refusal maps to **403**, not a generic 500 |
| `hg_event_ticket_payment_expiry` runs every 15 min; sets `status = 'cancelled'`, `payment_status = 'expired'`, releases the seat | No Python job (dropped); `app/routes/events.py` excludes cancelled/expired tickets from registrant lists and host emails |

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
* **No Python expiry job** — the database owns it: `hg_event_ticket_payment_expiry`
  runs every 15 minutes, cancels expired unpaid tickets, sets
  `payment_status = 'expired'` and releases the tier seat. A second job in this
  repo would race it, so none exists. The registrant filter also drops `expired`
  and `cancelled` rows outright.

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
| Reachability with the **anon** key | REST, every table | splits *reachable* from *readable* — see below |
| Duplicate/near-duplicate tables and functions | name clustering | "parallel sessions built duplicates before" |

The Supabase dashboard's own **Advisors → Security** page is the vendor view of
the same ground; the script covers it so it can run in CI without dashboard
access. Run both — the advisor also flags leaked-password protection and
extension versions.

### Reading the anon result (important)

PostgREST exposes the whole `public` schema to the `anon` key; **the grant is not
the finding — the rows are**. A `200 []` means RLS filtered every row, which is
the normal Supabase posture and not a leak. The probe therefore requests one real
row per table and classifies:

| Result | Meaning | Severity |
|--------|---------|----------|
| `exposed` | 200 **with a row** — an unauthenticated caller can read data | **high** |
| `empty` | 200 `[]` — grant exists, RLS filtered everything | informational |
| `denied` | 401/403 — no grant at all | — |
| `missing` | 404 — not in the schema cache | — |
| `unparseable` | 200 with a non-JSON body — unexpected for PostgREST, look by hand | low |

So "112 tables answer the anon key" with zero `exposed` is the expected shape of a
healthy project, not 112 vulnerabilities. The number to watch is `exposed`, and it
must be zero.

### Connecting (SUPABASE_DB_URL)

Without it, the audit can only do the REST pass: no policies, no grants, no
function bodies, and **no row-visibility check per role** — the part that actually
proves an RLS policy works. It reports that as `low` (a tooling gap), not as a
database finding.

Use the **connection pooler** URI (port 6543). The direct host
`db.<ref>.supabase.co` is IPv6-only and will not connect from most CI runners or
from Replit:

```ini
SUPABASE_DB_URL=postgresql://postgres.<ref>:<DB_PASSWORD>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

`<DB_PASSWORD>` is the database password on that settings page, not the
service-role key. With it set, `make audit` additionally impersonates each role
inside a rolled-back transaction and reports exactly which tables that role can
read — pass the accounts with `--impersonate`, or let it pick up `E2E_STUDENT_ID`,
`E2E_ADMIN_ID` and `E2E_SUPERADMIN_ID` from `.env`.

---

## 3. Findings so far (evidence-backed)

| # | Severity | Finding | Where |
|---|----------|---------|-------|
| F1 | high (functional) | Free-side credits are never consumed at checkout; `consume_free_side_selections()` is dead code and two comments claim otherwise | `app/routes/free_sides.py:192,270,298`; `app/services/order_service.py` (0 refs) |
| F2 | medium | `reward_redemptions` is never marked used outside `rewards.py` — the closing step lives (or does not live) in an RPC | `app/routes/rewards.py` only |
| F3 | low | Docs reference files that do not exist in this checkout: `migrations/schema.sql`, `scripts/seed.py`, `scripts/seed.sql` (the `CROSS_FILE_DEPENDENCIES.md` reference was dropped) | repo root |
| F4 | low | The deep SQL pass had not run: `SUPABASE_DB_URL` unset, so RLS policies, grants and per-role row visibility are still unverified | audit run of 2026-10-01 |

---

## 4. Open items and answer path

1. **`SUPABASE_DB_URL`** — still open: RLS, grants and the per-role visibility check
   have not run. Q1–Q3 are answered from the database itself. Add the pooler URI
   to `.env` (see *Connecting* above) and run `make audit`.
2. If you would rather not hand over a DB connection: run
   `make audit ARGS="--dump-defs hg_create_order,hg_mark_order_paid,register_for_event_paid,register_for_event_guest_paid"`
   and paste the output — same answers, no credentials.
3. `CROSS_FILE_DEPENDENCIES.md` is referenced by the code but missing — is it somewhere else, or should the reference be dropped?

Fixes are queued behind the probe results, because both F1 and F2 have the same
trap: if the RPC already does the work, the Python "fix" would double-apply it.
