#!/usr/bin/env python3
"""
Database audit — duplicates, RLS, grants, RPC behaviour, security advisor.

Built for the "verify against the live DB, never guess" rule.  Two passes:

  REST pass (always runs, service-role key only)
      * inventory of every table and RPC in the live schema (from PostgREST's
        OpenAPI spec) — this is the "search before proposing anything" step
      * duplicate-table / near-duplicate-name search
      * what the **anon** key can reach per table (RLS + grants at the HTTP level)
      * every table the code references but the schema does not expose, and
        every table in the schema the code never touches

  SQL pass (runs when SUPABASE_DB_URL is set — psycopg2, already a dependency)
      * real RLS state per table: enabled? forced? policies (cmd, roles, quals)
      * grants per table and per function for anon / authenticated / service_role
      * function bodies (pg_get_functiondef), which is the only way to answer
        the open questions — the REST API cannot expose them
      * security-advisor equivalents: RLS disabled on a public table, RLS on but
        no policies, SECURITY DEFINER executable by anon, mutable search_path,
        views without security_invoker, functions with PUBLIC EXECUTE

Questions this script is built to answer (see docs/DATABASE_AUDIT.md):
    a) does hg_create_order consume free_side_selections / free-side credits?
    b) does the order RPC mark a reward redemption as used after delivery?
    c) what payment_status do register_for_event* give an unpaid card ticket?
    d) does profiles.role accept kitchen and rider (DB side of the role route)?

Usage
-----
    python scripts/db_audit.py                    # REST pass + SQL pass if configured
    python scripts/db_audit.py --rest-only        # no database connection needed
    python scripts/db_audit.py --search credit    # is there already a table/RPC for this?
    python scripts/db_audit.py --out docs/audit.md --json docs/audit.json
    python scripts/db_audit.py --dump-defs hg_create_order,hg_mark_order_paid

Exit codes
----------
    0  audit completed, no high-severity findings
    1  high-severity findings (missing RLS, anon-executable SECURITY DEFINER, …)
    2  configuration problem (no keys, or SUPABASE_DB_URL unset for the deep pass)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("needs `requests` (pip install -r requirements.txt)", file=sys.stderr)
    raise SystemExit(2)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BACKEND_ROOT = Path(__file__).resolve().parent.parent
TABLE_CALL_RE = re.compile(r"""\.table\(\s*["']([a-z0-9_]+)["']\s*\)""")
RPC_CALL_RE = re.compile(r"""\.rpc\(\s*["']([a-z0-9_]+)["']""")

# The four open questions from the ecosystem map, expressed as text probes over
# pg_get_functiondef output. Each probe names the functions to read and the
# tokens that constitute evidence.
PROBES = {
    "Q1_free_sides_in_create_order": {
        "question": "Does hg_create_order consume free_side_selections / free-side credits?",
        "functions": ["hg_create_order_atomic"],
        "look_for": ["free_side", "cart_free_side_selections", "free_side_credits"],
        "absence_means": "the RPC never reads free-side tables, so a selected free side "
                         "is recorded but never spent nor added to the order",
    },
    "Q2_reward_redemption_marked_used": {
        "question": "Does the order RPC mark a reward redemption as used after delivery?",
        "functions": ["hg_create_order_atomic", "hg_mark_order_paid", "hg_redeem_reward",
                      "hg_credit_delivery_hp_atomic"],
        "look_for": ["reward_redemptions", "attached_order_id", "used_at"],
        "absence_means": "nothing in the order path updates reward_redemptions, so the "
                         "reward is never consumed (the Python side has no such update either)",
    },
    "Q3_event_ticket_payment_status": {
        "question": "What payment_status do register_for_event* give an unpaid card ticket?",
        "functions": ["register_for_event_paid", "register_for_event_guest_paid"],
        "look_for": ["payment_status", "pending", "unpaid", "not_required", "paid", "INSERT"],
        "absence_means": "payment_status is not assigned by the RPC — the column default rules",
    },
    "Q4_role_check_constraint": {
        "question": "Does the database accept kitchen and rider in profiles.role?",
        "functions": [],
        "sql": """
            SELECT c.conname, pg_get_constraintdef(c.oid) AS definition
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = 'profiles' AND c.contype = 'c'
        """,
        "look_for": ["role", "student", "admin", "kitchen", "rider", "super_admin"],
        "absence_means": "profiles.role has no CHECK constraint — the five-role list is only "
                         "enforced in Python (app/constants.py VALID_ROLES)",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  Reporting
# ─────────────────────────────────────────────────────────────────────────────

class Report:
    def __init__(self, as_json: bool = False):
        self.as_json = as_json
        self.lines: list[str] = []
        self.findings: list[dict] = []
        self.data: dict = {}
        self.tty = sys.stdout.isatty()

    def paint(self, text, code):
        return f"\033[{code}m{text}\033[0m" if self.tty and not self.as_json else text

    def head(self, title: str, level: int = 2):
        line = f"{'#' * level} {title}"
        self.lines.append(f"\n{line}\n")
        if not self.as_json:
            print(f"\n{self.paint(title.upper(), '1;36')}")

    def text(self, message: str = ""):
        self.lines.append(message)
        if not self.as_json:
            print(message)

    def finding(self, severity: str, title: str, detail: str, fix: str = ""):
        self.findings.append({"severity": severity, "title": title, "detail": detail, "fix": fix})
        if not self.as_json:
            colour = {"high": "31", "medium": "33", "low": "90"}.get(severity, "0")
            print(f"  {self.paint(severity.upper().ljust(6), colour)} {title}")
            if detail:
                print(f"         {detail[:160]}")
            if fix:
                print(f"         → {fix[:160]}")

    def table(self, headers: list[str], rows: list[list], limit: int = 60):
        if not rows:
            self.text("_none_")
            return
        head = "| " + " | ".join(headers) + " |"
        sep = "|" + "|".join("---" for _ in headers) + "|"
        body = ["| " + " | ".join(str(c) for c in row) + " |" for row in rows[:limit]]
        if len(rows) > limit:
            body.append(f"| _… {len(rows) - limit} more_ |" + " |" * (len(headers) - 1))
        block = "\n".join([head, sep] + body)
        self.lines.append(block)
        if not self.as_json:
            for row in rows[:limit]:
                print("  " + "  ".join(str(c)[:38].ljust(20) for c in row))
            if len(rows) > limit:
                print(f"  … {len(rows) - limit} more")


# ─────────────────────────────────────────────────────────────────────────────
#  REST pass
# ─────────────────────────────────────────────────────────────────────────────

def fetch_spec(url: str, key: str, timeout: float) -> dict | None:
    try:
        resp = requests.get(
            f"{url.rstrip('/')}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Accept": "application/openapi+json, application/json"},
            timeout=timeout,
        )
        if resp.status_code < 400 and "json" in resp.headers.get("content-type", ""):
            return resp.json()
    except requests.exceptions.RequestException:
        return None
    return None


def spec_inventory(spec: dict) -> tuple[list[str], dict[str, list[str]]]:
    """(tables, {rpc: parameters}) from a PostgREST OpenAPI document."""
    tables = sorted((spec.get("definitions") or {}).keys())
    rpcs: dict[str, list[str]] = {}
    for path, ops in (spec.get("paths") or {}).items():
        match = re.match(r"^/rpc/([A-Za-z0-9_]+)$", path or "")
        if not match:
            continue
        params: set[str] = set()
        for op in (ops or {}).values():
            if not isinstance(op, dict):
                continue
            for param in op.get("parameters") or []:
                name = (param or {}).get("name")
                if name:
                    params.add(name)
                for prop in (((param or {}).get("schema") or {}).get("properties") or {}):
                    params.add(prop)
        rpcs[match.group(1)] = sorted(params)
    return tables, rpcs


def code_references() -> tuple[set[str], set[str]]:
    tables, rpcs = set(), set()
    for path in BACKEND_ROOT.glob("app/**/*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        tables.update(TABLE_CALL_RE.findall(text))
        rpcs.update(RPC_CALL_RE.findall(text))
    return tables, rpcs


def anon_reachability(url: str, anon_key: str, tables: list[str],
                      timeout: float, workers: int = 8) -> dict[str, str]:
    """What the anon key gets per table: open / empty(allowed) / denied / missing."""
    import concurrent.futures

    def probe(table: str) -> tuple[str, str]:
        try:
            resp = requests.get(
                f"{url.rstrip('/')}/rest/v1/{table}",
                params={"select": "*", "limit": "0"},
                headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}"},
                timeout=timeout,
            )
        except requests.exceptions.RequestException:
            return table, "unreachable"
        if resp.status_code < 400:
            return table, "allowed"
        if resp.status_code in (401, 403):
            return table, "denied"
        if resp.status_code == 404:
            return table, "missing"
        return table, f"http:{resp.status_code}"

    out: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for table, status in pool.map(probe, tables):
            out[table] = status
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  SQL pass
# ─────────────────────────────────────────────────────────────────────────────

def connect(db_url: str):
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 is not installed — pip install -r requirements.txt", file=sys.stderr)
        return None
    try:
        conn = psycopg2.connect(db_url, connect_timeout=15)
        conn.autocommit = True
        return conn
    except Exception as exc:  # noqa: BLE001
        print(f"could not connect with SUPABASE_DB_URL: {exc}", file=sys.stderr)
        return None


def query(conn, sql: str, params=None) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall() if cur.description else []


def sql_rls(conn, rep: Report) -> None:
    rep.head("RLS state per table (pg_class)")
    rows = query(conn, """
        SELECT c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity,
               (SELECT count(*) FROM pg_policies p
                 WHERE p.schemaname = 'public' AND p.tablename = c.relname) AS policies
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m')
        ORDER BY c.relkind, c.relname
    """)
    rep.data["rls"] = [{"table": r[0], "kind": r[1], "rls_enabled": r[2],
                        "rls_forced": r[3], "policies": r[4]} for r in rows]

    tables_no_rls = [(r[0], r[4]) for r in rows if r[1] in ("r", "p") and not r[2]]
    rls_no_policy = [(r[0],) for r in rows if r[1] in ("r", "p") and r[2] and r[4] == 0]

    rep.table(["table", "kind", "rls", "forced", "policies"],
              [[r[0], r[1], "yes" if r[2] else "NO", "yes" if r[3] else "-", r[4]] for r in rows])

    for table, _ in tables_no_rls:
        rep.finding("high", f"RLS disabled on public.{table}",
                    "any role with a grant can read/write every row",
                    "ALTER TABLE public.%s ENABLE ROW LEVEL SECURITY; then add policies" % table)
    for (table,) in rls_no_policy:
        rep.finding("medium", f"RLS enabled but no policies on public.{table}",
                    "only the service-role key can touch it (safe but possibly unintended)",
                    "add policies if the anon/authenticated roles should read it")


def sql_policies(conn, rep: Report) -> None:
    rep.head("Policies (pg_policies)")
    rows = query(conn, """
        SELECT tablename, policyname, array_to_string(roles, ','), cmd,
               COALESCE(qual, ''), COALESCE(with_check, '')
        FROM pg_policies WHERE schemaname = 'public'
        ORDER BY tablename, policyname
    """)
    rep.data["policies"] = [{"table": r[0], "policy": r[1], "roles": r[2], "cmd": r[3],
                             "using": r[4], "with_check": r[5]} for r in rows]
    rep.table(["table", "policy", "roles", "cmd", "using"],
              [[r[0], r[1], r[2], r[3], (r[4] or r[5])[:40]] for r in rows])

    for r in rows:
        roles = (r[2] or "").split(",")
        if "anon" in roles and r[3] in ("INSERT", "UPDATE", "DELETE", "ALL"):
            rep.finding("high", f"anon can {r[3]} on public.{r[0]} (policy {r[1]})",
                        f"with check: {(r[5] or '-')[:80]}",
                        "restrict write policies to the authenticated role")
        elif "public" in roles and r[3] in ("INSERT", "UPDATE", "DELETE", "ALL"):
            rep.finding("high", f"PUBLIC can {r[3]} on public.{r[0]} (policy {r[1]})",
                        "the PUBLIC pseudo-role includes every role",
                        "replace PUBLIC with the roles that need it")


def sql_grants(conn, rep: Report) -> None:
    rep.head("Table grants")
    rows = query(conn, """
        SELECT table_name, grantee, string_agg(DISTINCT privilege_type, ',' ORDER BY privilege_type)
        FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND grantee IN ('anon','authenticated','service_role','PUBLIC')
        GROUP BY 1, 2 ORDER BY 1, 2
    """)
    rep.data["table_grants"] = [{"table": r[0], "grantee": r[1], "privileges": r[2]} for r in rows]
    rep.table(["table", "grantee", "privileges"], [[r[0], r[1], r[2]] for r in rows])

    for table, grantee, privileges in rows:
        can_write = any(p in privileges for p in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"))
        if grantee in ("anon", "PUBLIC") and can_write:
            rep.finding("high", f"{grantee} has write grants on public.{table}",
                        f"privileges: {privileges}",
                        "REVOKE INSERT/UPDATE/DELETE on this table from " + grantee)
        if grantee == "PUBLIC":
            rep.finding("medium", f"PUBLIC holds grants on public.{table}",
                        f"privileges: {privileges}", "grant to named roles only")

    rep.head("Function grants (anon / authenticated)")
    rows = query(conn, """
        SELECT routine_name, grantee, string_agg(DISTINCT privilege_type, ',')
        FROM information_schema.routine_privileges
        WHERE routine_schema = 'public' AND grantee IN ('anon','authenticated','PUBLIC')
        GROUP BY 1, 2 ORDER BY 1, 2
    """)
    rep.data["function_grants"] = [{"function": r[0], "grantee": r[1], "privileges": r[2]}
                                   for r in rows]
    rep.table(["function", "grantee", "privileges"], [[r[0], r[1], r[2]] for r in rows])


def sql_functions(conn, rep: Report) -> None:
    rep.head("Functions: security + search_path")
    rows = query(conn, """
        SELECT p.proname, p.prosecdef,
               COALESCE(array_to_string(p.proconfig, ','), ''),
               pg_get_function_identity_arguments(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' ORDER BY p.proname
    """)
    rep.data["functions"] = [{"name": r[0], "security_definer": r[1], "config": r[2],
                              "args": r[3]} for r in rows]
    rep.table(["function", "security definer", "config", "arguments"],
              [[r[0], "yes" if r[1] else "-", r[2] or "-", r[3][:40]] for r in rows])

    anon_executable = {r[0] for r in query(conn, """
        SELECT DISTINCT routine_name FROM information_schema.routine_privileges
        WHERE routine_schema='public' AND grantee IN ('anon','PUBLIC')
          AND privilege_type='EXECUTE'
    """)}

    for name, secdef, config, _args in rows:
        if secdef and not config:
            severity = "high" if name in anon_executable else "medium"
            rep.finding(severity, f"SECURITY DEFINER without a pinned search_path: {name}",
                        "a caller-controlled search_path can hijack unqualified references",
                        f"ALTER FUNCTION public.{name}(...) SET search_path = public, pg_temp;")
        if secdef and name in anon_executable:
            rep.finding("medium", f"anon can execute SECURITY DEFINER {name}",
                        "runs with the definer's privileges for an unauthenticated caller",
                        f"REVOKE EXECUTE ON FUNCTION public.{name}(...) FROM anon;")


def sql_probes(conn, rep: Report) -> None:
    """The four open questions, answered from the actual function bodies."""
    rep.head("RPC behaviour probes")
    answers: dict[str, dict] = {}

    def load_defs(names: list[str]) -> dict[str, str]:
        if not names:
            return {}
        rows = query(conn, """
            SELECT p.proname, pg_get_functiondef(p.oid)
            FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname = ANY(%s)
        """, (names,))
        return {r[0]: r[1] for r in rows}

    for key, probe in PROBES.items():
        entry: dict = {"question": probe["question"], "status": "unknown", "evidence": []}
        if probe.get("functions"):
            defs = load_defs(probe["functions"])
            missing = [f for f in probe["functions"] if f not in defs]
            for name in probe["functions"]:
                body = defs.get(name)
                if not body:
                    continue
                hits = sorted({token for token in probe["look_for"]
                               if re.search(re.escape(token), body, re.IGNORECASE)})
                entry["evidence"].append({"function": name, "tokens": hits,
                                          "lines": body.count("\n")})
            entry["missing_functions"] = missing
            any_tokens = [t for e in entry["evidence"] for t in e["tokens"]]
            entry["status"] = "referenced" if any_tokens else "not-referenced"
        else:
            sql = probe.get("sql")
            if sql:
                rows = query(conn, sql)
                entry["rows"] = [list(r) for r in rows]
                blob = json.dumps(entry["rows"]).lower()
                entry["status"] = ("referenced"
                                   if any(t.lower() in blob for t in probe["look_for"])
                                   else "not-referenced")
                if not rows:
                    entry["status"] = "no-constraint"

        answers[key] = entry
        rep.text(f"**{probe['question']}**")
        rep.text(f"- status: `{entry['status']}`")
        for name in entry.get("missing_functions", []):
            rep.text(f"- __function not found: `{name}`__")
        for e in entry.get("evidence", []):
            found = ", ".join("`" + t + "`" for t in e["tokens"])
            expected = ", ".join("`" + t + "`" for t in probe["look_for"])
            rep.text(f"- `{e['function']}` ({e['lines']} lines): tokens → "
                     + (found if found else f"none of {expected}"))
        for row in entry.get("rows", []):
            rep.text(f"- {row}")
        if entry["status"] == "not-referenced":
            rep.finding("high", probe["question"], probe["absence_means"])
        rep.text()

    rep.data["probes"] = answers


def sql_impersonate(conn, rep: Report, subjects: list[tuple[str, str]], sample: int = 3) -> None:
    """What each role actually sees, by impersonating it inside a transaction.

    This is the empirical RLS test: set the Postgres role and the JWT claims
    PostgREST would set, then read a few rows. An empty result where a policy
    should allow reads is a bug; rows visible to `anon` are a leak.

    Runs in a transaction that is always rolled back, and only ever does SELECTs.
    """
    rep.head("RLS impersonation")
    relations = [r[0] for r in query(conn, """
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v') ORDER BY c.relname
    """)]

    subjects = [("anon", None)] + subjects
    for label, user_id in subjects:
        role = "anon" if label == "anon" else "authenticated"
        claims = json.dumps({"role": role, "sub": user_id} if user_id else {"role": "anon"})
        visible, denied, errored = [], [], []
        try:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute(f"SET LOCAL ROLE {role}")
                cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (claims,))
                for table in relations:
                    try:
                        cur.execute(f'SELECT count(*) FROM public."{table}"')
                        count = cur.fetchone()[0]
                        (visible if count else denied).append((table, count))
                    except Exception:                          # noqa: BLE001
                        errored.append(table)
                        cur.execute("ROLLBACK; BEGIN; SET LOCAL ROLE " + role)
                        cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (claims,))
                cur.execute("ROLLBACK")
        except Exception as exc:                               # noqa: BLE001
            rep.finding("medium", f"could not impersonate {label}",
                        str(exc)[:160],
                        "the role may not exist, or the connection user cannot SET ROLE to it")
            continue

        rep.text(f"**{label}**" + (f" ({user_id})" if user_id else " (no JWT)"))
        rep.text(f"- rows visible: {len(visible)} table(s) → "
                 + (", ".join(f"{t}({c})" for t, c in visible[:12]) or "_none_")
                 + (" …" if len(visible) > 12 else ""))
        rep.text(f"- empty but readable (RLS filtered): {len(denied)}")
        if errored:
            rep.text(f"- permission denied: {len(errored)} → " + ", ".join(errored[:12])
                     + (" …" if len(errored) > 12 else ""))
        rep.data.setdefault("impersonation", {})[label] = {
            "user_id": user_id,
            "visible": [{"table": t, "rows": c} for t, c in visible],
            "empty": [t for t, _ in denied],
            "denied": errored,
        }

        if label == "anon":
            sensitive = {"profiles", "orders", "wallets", "wallet_transactions",
                         "hp_transactions", "event_tickets", "device_tokens",
                         "user_addresses", "notification_preferences"}
            leaks = [(t, c) for t, c in visible if t in sensitive]
            if leaks:
                rep.finding("high", "anon can read rows from customer tables",
                            ", ".join(f"{t}({c} rows)" for t, c in leaks),
                            "revoke the anon grant or tighten the RLS policy")
        if label != "anon" and not visible:
            rep.finding("medium", f"authenticated user {label} sees no rows anywhere",
                        "either every policy is missing or the grant is absent",
                        "a normal user must at least see their own profiles row")
        rep.text()


def sql_duplicates(conn, rep: Report) -> None:
    """Duplicate / near-duplicate relations and functions (parallel sessions)."""
    rep.head("Duplicate search")
    tables = [r[0] for r in query(conn, """
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m') ORDER BY 1
    """)]
    funcs = [r[0] for r in query(conn, """
        SELECT DISTINCT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' ORDER BY 1
    """)]

    def clusters(names: list[str]) -> list[list[str]]:
        out, seen = [], set()
        for name in names:
            if name in seen:
                continue
            stem = re.sub(r"(_?(old|new|v\d+|tmp|temp|backup|copy|test|dup\w*))+$", "", name)
            group = sorted(n for n in names
                           if n == name or re.sub(r"(_?(old|new|v\d+|tmp|temp|backup|copy|test|dup\w*))+$", "", n) == stem)
            if len(group) > 1:
                out.append(group)
                seen.update(group)
        return out

    dup_tables, dup_funcs = clusters(tables), clusters(funcs)
    rep.data["duplicate_tables"] = dup_tables
    rep.data["duplicate_functions"] = dup_funcs
    if dup_tables or dup_funcs:
        for group in dup_tables:
            rep.finding("medium", "similar table names", ", ".join(group),
                        "confirm which one is authoritative before adding another")
        for group in dup_funcs:
            rep.finding("medium", "similar function names", ", ".join(group),
                        "confirm which one is authoritative before adding another")
    else:
        rep.text("no near-duplicate table or function names found")
    rep.text(f"\n{len(tables)} relations, {len(funcs)} functions in public.")
    return tables, funcs


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit the live database against the codebase.")
    parser.add_argument("--rest-only", action="store_true",
                        help="skip the SQL pass even if SUPABASE_DB_URL is set")
    parser.add_argument("--search", default="",
                        help="look for an existing table/function matching this text")
    parser.add_argument("--impersonate", action="append", default=[],
                        metavar="LABEL:UUID",
                        help="also run the RLS check as `authenticated` with this JWT sub "
                             "(repeatable, e.g. --impersonate student:3d022e3c-…). "
                             "Defaults to E2E_STUDENT_ID / E2E_ADMIN_ID when set.")
    parser.add_argument("--dump-defs", default="",
                        help="print pg_get_functiondef for these functions (comma-separated)")
    parser.add_argument("--out", default="", help="also write the markdown report here")
    parser.add_argument("--json", default="", help="also write the machine-readable report here")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--env-file", default=str(BACKEND_ROOT / ".env"))
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    if load_dotenv is not None and env_file.exists():
        load_dotenv(env_file, override=False)

    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    anon_key = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    db_url = (os.environ.get("SUPABASE_DB_URL") or "").strip()

    # RLS impersonation subjects: --impersonate wins, then the .env ids
    subjects: list[tuple[str, str]] = []
    for item in args.impersonate:
        label, _, uid = item.partition(":")
        if label and uid:
            subjects.append((label.strip(), uid.strip()))
    if not subjects:
        for label, env_name in (("student", "E2E_STUDENT_ID"),
                                ("admin", "E2E_ADMIN_ID"),
                                ("superadmin", "E2E_SUPERADMIN_ID")):
            uid = (os.environ.get(env_name) or "").strip()
            if uid:
                subjects.append((label, uid))

    if not url or not service_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing — run scripts/check_supabase.py first.",
              file=sys.stderr)
        return 2

    rep = Report(as_json=False)
    started = time.time()
    rep.text("# Holy Grills — database audit")
    rep.text(f"project: `{url}`  ·  {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")

    # ── REST pass ────────────────────────────────────────────────────────────
    rep.head("Schema inventory (PostgREST OpenAPI)")
    spec = fetch_spec(url, service_key, args.timeout)
    live_tables, live_rpcs = ([], {})
    if spec is None:
        rep.finding("high", "could not fetch the PostgREST spec",
                    "the service-role key may be wrong, or the project is unreachable")
    else:
        live_tables, live_rpcs = spec_inventory(spec)
        rep.text(f"PostgREST {spec.get('info', {}).get('version')} — "
                 f"**{len(live_tables)} tables/views, {len(live_rpcs)} RPCs** exposed")
        rep.data["inventory"] = {"tables": live_tables, "rpcs": sorted(live_rpcs),
                                 "pgrst_version": spec.get("info", {}).get("version"),
                                 "schema_title": spec.get("info", {}).get("title")}

    code_tables, code_rpcs = code_references()
    rep.text(f"code references: {len(code_tables)} tables, {len(code_rpcs)} RPCs")

    if live_tables:
        missing = sorted(code_tables - set(live_tables))
        unused = sorted(set(live_tables) - code_tables)
        if missing:
            rep.finding("high", "code calls tables the schema does not expose",
                        ", ".join(missing[:12]) + (" …" if len(missing) > 12 else ""),
                        "run scripts/contract_check.py for the exact columns")
        if unused:
            rep.finding("low", "tables no code path touches",
                        ", ".join(unused[:15]) + (" …" if len(unused) > 15 else ""),
                        "expected for admin-only or job-managed tables; check for strays")
        rep.data["missing_tables"] = missing
        rep.data["unused_tables"] = unused

    if code_rpcs and live_rpcs:
        missing_rpcs = sorted(code_rpcs - set(live_rpcs))
        if missing_rpcs:
            rep.finding("high", "code calls RPCs the schema does not expose",
                        ", ".join(missing_rpcs),
                        "apply the migration or fix the call site")

    if args.search and live_tables:
        needle = args.search.lower()
        hits_t = [t for t in live_tables if needle in t.lower()]
        hits_f = [f for f, p in live_rpcs.items()
                  if needle in f.lower() or any(needle in x.lower() for x in p)]
        rep.head(f"Search: {args.search!r}")
        rep.text(f"tables/views: {', '.join(hits_t) or '_none_'}")
        rep.text(f"RPCs (name or parameter): {', '.join(hits_f) or '_none_'}")
        rep.data["search"] = {"term": args.search, "tables": hits_t, "rpcs": hits_f}

    if anon_key and live_tables:
        rep.head("Reachability with the anon key")
        reach = anon_reachability(url, anon_key, live_tables, args.timeout)
        counts: dict[str, int] = {}
        for status in reach.values():
            counts[status] = counts.get(status, 0) + 1
        rep.text(" · ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
        reachable = sorted(t for t, s in reach.items() if s == "allowed")
        rep.data["anon_reachability"] = reach
        if reachable:
            rep.finding("medium", f"{len(reachable)} table(s) answer the anon key",
                        ", ".join(reachable[:15]) + (" …" if len(reachable) > 15 else ""),
                        "RLS is the only thing filtering rows — verify every policy")
        rep.text("_Note: a 200 with an empty array means the grant exists; RLS still filters rows._")

    # ── SQL pass ─────────────────────────────────────────────────────────────
    if args.dump_defs:
        if not db_url:
            print("--dump-defs needs SUPABASE_DB_URL (see .env.example)", file=sys.stderr)
            return 2
        conn = connect(db_url)
        if conn is None:
            return 2
        for name in [n.strip() for n in args.dump_defs.split(",") if n.strip()]:
            rows = query(conn, """
                SELECT pg_get_functiondef(p.oid) FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname='public' AND p.proname = %s
            """, (name,))
            print(f"\n-- ── {name} ──")
            for (definition,) in rows:
                print(definition)
            if not rows:
                print(f"-- {name}: not found")
        return 0

    if args.rest_only or not db_url:
        if not args.rest_only:
            rep.head("SQL pass — skipped")
            rep.finding("medium", "SUPABASE_DB_URL is not set",
                        "RLS policies, grants and RPC bodies cannot be read through PostgREST",
                        "add the connection URI to .env and re-run — see docs/DATABASE_AUDIT.md")
    else:
        conn = connect(db_url)
        if conn is None:
            return 2
        try:
            sql_probes(conn, rep)
            sql_rls(conn, rep)
            sql_policies(conn, rep)
            sql_grants(conn, rep)
            sql_functions(conn, rep)
            if subjects:
                sql_impersonate(conn, rep, subjects)
            else:
                rep.head("RLS impersonation — skipped")
                rep.text("_no subjects given; pass --impersonate student:<uuid> or set "
                         "E2E_STUDENT_ID / E2E_ADMIN_ID / E2E_SUPERADMIN_ID in .env_")
            sql_duplicates(conn, rep)
        finally:
            conn.close()

    # ── summary ──────────────────────────────────────────────────────────────
    high = [f for f in rep.findings if f["severity"] == "high"]
    medium = [f for f in rep.findings if f["severity"] == "medium"]
    rep.head("Summary", 1)
    rep.text(f"- high: {len(high)} · medium: {len(medium)} "
             f"· low: {len([f for f in rep.findings if f['severity'] == 'low'])}")
    for f in high + medium:
        rep.text(f"- **{f['severity']}** — {f['title']}: {f['detail'][:220]}"
                 + (f"\n  - fix: {f['fix']}" if f["fix"] else ""))
    rep.text(f"\n_generated in {time.time() - started:.1f}s_")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(rep.lines), encoding="utf-8")
        print(f"\nreport written to {args.out}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps({"findings": rep.findings, "data": rep.data},
                                              indent=2, default=str), encoding="utf-8")
        print(f"json written to {args.json}")

    if not rep.as_json and not args.out:
        print()
    return 1 if high else 0


if __name__ == "__main__":
    raise SystemExit(main())
