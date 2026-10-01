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

**Report status**

| Area | Status |
|------|--------|
| Schema inventory (tables/RPCs), duplicate search | pending first run |
| RPC behaviour (Q1–Q3) | pending `SUPABASE_DB_URL` |
| Q4 roles | answered from code, DB-side check scripted |
| RLS, grants, security-advisor equivalents | pending `SUPABASE_DB_URL` |

---

## 1. The four questions

### Q1 — does `hg_create_order` consume free-side selections/credits?

**Python side: confirmed NO — the consumer is dead code.** Not inferred; quoted
from the source:

* `app/routes/free_sides.py:298` defines `consume_free_side_selections(write_db, user_id, campus_id, order_id)`.
* Its docstring: *"…not yet wired into order_service.create_order() as of this pass; see CROSS_FILE_DEPENDENCIES.md."*
* `consume_free_side_selections` is **never called anywhere** in the repo (only its definition matches).
* `app/services/order_service.py` contains **zero** occurrences of `free_side`.
* `app/routes/free_sides.py:192` and `:270` still claim it *is* called from `create_order` — stale comments.

Net effect: `POST /free-sides/select` writes a `cart_free_side_selections` row and
nothing ever spends the `free_side_credits` row or adds a ₦0 `order_items` line.

**DB side: to confirm** — the only way the credit could still be spent is if the
RPC reads those tables itself. Probe `Q1_free_sides_in_create_order` reads
`pg_get_functiondef('hg_create_order')` and reports whether `free_side`,
`cart_free_side_selections` or `free_side_credits` appear.

> **Do not wire the Python consumer before this probe runs.** If the RPC already
> decrements credits, adding the Python call double-spends them.

### Q2 — does the order RPC mark a reward redemption as used after delivery?

**Python side: no path exists.** `reward_redemptions` appears only in
`app/routes/rewards.py` (create, fulfil, reject, delivery-choice) — nothing in the
order flow, delivery flow or the delivery-HP service updates it.

**DB side: to confirm** — probe `Q2_reward_redemption_marked_used` reads
`hg_create_order`, `hg_mark_order_paid`, `hg_redeem_reward` and
`hg_credit_delivery_hp_atomic` and reports which of them mention
`reward_redemptions` / a `used` status.

### Q3 — what `payment_status` do `register_for_event*` give an unpaid card ticket?

**Python side: the RPC decides.** `app/routes/events.py:601` reads
`rpc_res.get("payment_status")` straight from the RPC result, with a
`"not_required"` fallback at `:606`/`:700`. There is no Python assignment of
`pending` anywhere — so this is entirely an RPC/column-default question.

**DB side: to confirm** — probe `Q3_event_ticket_payment_status` extracts the
assignment from both `register_for_event_paid` and `register_for_event_guest_paid`,
and (because a column default would be invisible in the body) also reports the
`event_tickets.payment_status` default. This matters for gap 2 of the ecosystem
map: `send-registrants-to-host` has no payment filter, so the value written here
determines whether unpaid card tickets get emailed to a host.

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
