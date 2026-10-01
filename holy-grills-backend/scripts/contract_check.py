#!/usr/bin/env python3
"""
Code ↔ live-database contract check.

`check_supabase.py` answers "can I reach Supabase?".  This script answers the
follow-up question that actually breaks deployments at runtime:

    **does every request this code makes match what the database expects?**

It statically extracts the database contract from the Python source (no
execution, no imports):

  * `.table("orders").select("id,status").eq("user_id", x).order("created_at")`
    → table `orders`, columns {id, status, user_id, created_at}
  * `.insert({...})` / `.update({...})` / `.upsert({...})` dict keys
  * `.rpc("credit_wallet_atomic", {...})` → function name + parameter names

…then verifies that contract against the live project:

  * tables      — exist (batched `select=<cols>&limit=0` probe per table)
  * columns     — exist (a failing batch is re-probed column-by-column so the
                  report names the exact offender, with SQLSTATE 42703 /
                  PGRST204 distinguishing "no such column")
  * RPCs        — resolved from PostgREST's OpenAPI spec, because calling an
                  unknown function would either fail ambiguously or *execute*
                  it.  Function parameters are checked there too.

Nothing is written: every probe is a read-only `SELECT ... LIMIT 0`.
Embedded selects (`order_items(...)`), `count`, casts (`id::text`) and aliases
(`label:name`) are understood and skipped correctly.

Usage
-----
    python scripts/contract_check.py                 # full check
    python scripts/contract_check.py --list           # print the contract, no network
    python scripts/contract_check.py --json           # machine-readable
    python scripts/contract_check.py --strict         # warnings fail too
    python scripts/contract_check.py --spec-only      # skip column probes
    python scripts/contract_check.py --ignore-tables audit_logs,tmp_x

Exit codes
----------
    0  contract holds (warnings allowed unless --strict)
    1  the code references something the database does not have
    2  configuration error
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("This script needs `requests` (pip install -r requirements.txt).", file=sys.stderr)
    raise SystemExit(2)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


BACKEND_ROOT = Path(__file__).resolve().parent.parent
COLUMN_METHODS = {
    "eq", "neq", "gt", "gte", "lt", "lte", "ilike", "like", "in_", "is_",
    "order", "contains", "containedby", "overlaps", "text_search", "match",
}
ROW_METHODS = {"insert", "update", "upsert"}
# SQLSTATE / PostgREST codes that mean "column not found"
COLUMN_ERROR_CODES = {"42703", "PGRST204"}
TABLE_ERROR_CODES = {"PGRST205", "42P01"}
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ─────────────────────────────────────────────────────────────────────────────
#  Static extraction
# ─────────────────────────────────────────────────────────────────────────────

class Contract:
    def __init__(self):
        # table -> {"columns": {col: [where...]}, "ops": set()}
        self.tables: dict[str, dict] = {}
        self.rpcs: dict[str, dict] = {}

    def add_table(self, table: str, where: str):
        slot = self.tables.setdefault(table, {"columns": {}, "ops": set()})
        slot["ops"].add(where)

    def add_column(self, table: str, column: str, where: str):
        slot = self.tables.setdefault(table, {"columns": {}, "ops": set()})
        slot["columns"].setdefault(column, []).append(where)

    def add_rpc(self, name: str, params: list[str], where: str):
        slot = self.rpcs.setdefault(name, {"params": {}, "ops": set()})
        slot["ops"].add(where)
        for p in params:
            slot["params"].setdefault(p, []).append(where)


def _const_str(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _flatten(node) -> tuple[object, list[tuple[str, object]]]:
    """Flatten `a.b(..).c(..).d` into (root, [(name, call_node|None), ...])."""
    parts: list[tuple[str, object]] = []
    cur = node
    while True:
        if isinstance(cur, ast.Call):
            func = cur.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            parts.append((name, cur))
            cur = func.value if hasattr(func, "value") else func
        elif isinstance(cur, ast.Attribute):
            parts.append((cur.attr, None))
            cur = cur.value
        else:
            break
    parts.reverse()
    return cur, parts


def _select_columns(raw: str) -> list[str]:
    """Parse a PostgREST select string into top-level column names."""
    out: list[str] = []
    depth = 0
    token = ""
    for ch in raw + ",":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            part = token.strip()
            token = ""
            if not part or "(" in part:      # skip embedded resources
                continue
            if part == "*" or part.startswith("*"):
                continue
            if "::" in part:                 # cast -> drop the cast
                part = part.split("::", 1)[0].strip()
            if ":" in part:                  # alias:column -> keep the column
                part = part.split(":", 1)[1].strip()
            if part.endswith("!inner"):
                part = part[: -len("!inner")]
            if "!" in part:                  # embed hint (fk/table) -> skip
                continue
            if part == "count":              # row-count modifier, not a column
                continue
                continue
            if part and IDENT_RE.match(part):
                out.append(part)
        else:
            token += ch
    return out


def _dict_keys(node) -> list[str]:
    if not isinstance(node, ast.Dict):
        return []
    keys = []
    for k in node.keys:
        value = _const_str(k)
        if value:
            keys.append(value)
    return keys


def _or_columns(raw: str) -> list[str]:
    """Columns referenced inside a PostgREST or=(...) filter string."""
    out = []
    body = raw.strip()
    if body.startswith("or=(") and body.endswith(")"):
        body = body[4:-1]
    elif body.startswith("and=(") and body.endswith(")"):
        body = body[5:-1]
    for chunk in body.split(","):
        chunk = chunk.strip()
        for sep in (".eq.", ".neq.", ".ilike.", ".like.", ".gt.", ".gte.", ".lt.", ".lte.", ".is.", ".in."):
            if sep in chunk:
                col = chunk.split(sep, 1)[0].strip()
                if IDENT_RE.match(col):
                    out.append(col)
                break
    return out


def extract_from_file(path: Path, root: Path, contract: Contract) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return
    rel = str(path.relative_to(root))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        root_node, parts = _flatten(node)
        if not parts:
            continue

        # only expressions rooted in something called `db` / `client` / `supabase`
        base_name = getattr(root_node, "id", None) or getattr(root_node, "attr", None) or ""
        if base_name not in {"db", "client", "supabase", "self", "get_db", "get_user_client"}:
            continue

        table = None
        table_index = None
        for i, (name, call) in enumerate(parts):
            if name == "table" and call is not None and call.args:
                table = _const_str(call.args[0])
                table_index = i
                break

        if table is not None:
            where = f"{rel}:{node.lineno}"
            contract.add_table(table, where)
            for name, call in parts[table_index + 1:]:
                if call is None:
                    continue
                if name == "select" and call.args:
                    raw = _const_str(call.args[0])
                    if raw:
                        for col in _select_columns(raw):
                            contract.add_column(table, col, where)
                elif name in COLUMN_METHODS and call.args:
                    col = _const_str(call.args[0])
                    if col and IDENT_RE.match(col):
                        contract.add_column(table, col.split(".")[0], where)
                elif name == "or_" and call.args:
                    raw = _const_str(call.args[0])
                    if raw:
                        for col in _or_columns(raw):
                            contract.add_column(table, col, where)
                elif name in ROW_METHODS and call.args:
                    for key in _dict_keys(call.args[0]):
                        contract.add_column(table, key, where)
            continue

        # db.rpc("name", {...})
        for name, call in parts:
            if name == "rpc" and call is not None and call.args:
                fn = _const_str(call.args[0])
                if fn:
                    params = _dict_keys(call.args[1]) if len(call.args) > 1 else []
                    contract.add_rpc(fn, params, f"{rel}:{node.lineno}")


def build_contract(root: Path) -> Contract:
    contract = Contract()
    for path in sorted(root.glob("app/**/*.py")):
        extract_from_file(path, root, contract)
    return contract


# ─────────────────────────────────────────────────────────────────────────────
#  Live verification
# ─────────────────────────────────────────────────────────────────────────────

class Live:
    """Read-only probes against the project (service-role key)."""

    def __init__(self, url: str, key: str, timeout: float, workers: int):
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout
        self.workers = workers
        self.local = threading.local()

    def session(self) -> requests.Session:
        if not hasattr(self.local, "session"):
            self.local.session = requests.Session()
        return self.local.session

    def get(self, resource: str, params: dict | None = None, headers: dict | None = None):
        h = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        if headers:
            h.update(headers)
        return self.session().get(f"{self.url}/rest/v1/{resource}", params=params, headers=h,
                                  timeout=self.timeout)

    @staticmethod
    def error_code(resp) -> tuple[str, str]:
        try:
            body = resp.json()
            return str(body.get("code") or ""), str(body.get("message") or "")
        except Exception:
            return "", (resp.text or "")[:120]


def probe_table(live: Live, table: str, columns: list[str]) -> tuple[str, list[str], str]:
    """Return (status, bad_columns, detail): status in {ok, missing, denied, error}."""
    params = {"select": ",".join(columns) if columns else "*", "limit": "0"}
    try:
        resp = live.get(table, params)
    except requests.exceptions.RequestException as exc:
        return "error", [], f"unreachable: {type(exc).__name__}"

    if resp.status_code < 400:
        return "ok", [], ""

    code, message = Live.error_code(resp)

    if code in TABLE_ERROR_CODES or "does not exist" in message and "relation" in message:
        return "missing_table", [], f"{resp.status_code} {code}".strip()

    if code in COLUMN_ERROR_CODES or resp.status_code == 400:
        bad: list[str] = []

        def probe_one(col: str):
            try:
                r = live.get(table, {"select": col, "limit": "0"})
                if r.status_code < 400:
                    return None
                c, m = Live.error_code(r)
                return col if (c in COLUMN_ERROR_CODES or r.status_code == 400) else None
            except requests.exceptions.RequestException:
                return col

        with concurrent.futures.ThreadPoolExecutor(max_workers=live.workers) as pool:
            for hit in pool.map(probe_one, columns):
                if hit:
                    bad.append(hit)
        if bad:
            return "missing_columns", sorted(bad), f"{resp.status_code} {code} — {message[:100]}"
        return "error", [], f"{resp.status_code} {code} — {message[:120]}"

    if resp.status_code in (401, 403):
        return "denied", [], f"{resp.status_code} {code}".strip()
    return "error", [], f"{resp.status_code} {code} — {message[:120]}"


def fetch_spec(live: Live) -> dict | None:
    """PostgREST OpenAPI document (service-role only) — used for RPC discovery."""
    try:
        resp = live.session().get(
            f"{live.url}/rest/v1/",
            headers={
                "apikey": live.key,
                "Authorization": f"Bearer {live.key}",
                "Accept": "application/openapi+json, application/json",
            },
            timeout=live.timeout,
        )
        if resp.status_code < 400 and "json" in resp.headers.get("content-type", ""):
            return resp.json()
    except (requests.exceptions.RequestException, ValueError):
        pass
    return None


def spec_rpcs(spec: dict) -> tuple[set[str], dict[str, set[str]]]:
    """Return (rpc names, {rpc: parameter names}) from a PostgREST OpenAPI doc."""
    names: set[str] = set()
    params: dict[str, set[str]] = {}

    for path, ops in (spec.get("paths") or {}).items():
        match = re.match(r"^/rpc/([A-Za-z0-9_]+)$", path or "")
        if not match:
            continue
        fn = match.group(1)
        names.add(fn)
        bucket = params.setdefault(fn, set())
        for op in (ops or {}).values():
            if not isinstance(op, dict):
                continue
            for param in op.get("parameters") or []:
                pname = (param or {}).get("name")
                if pname:
                    bucket.add(pname)
                schema = (param or {}).get("schema") or {}
                for prop in (schema.get("properties") or {}):
                    bucket.add(prop)

    # some versions expose the function as a definition too
    for key in ("definitions", "components"):
        block = spec.get(key) or {}
        if key == "components":
            block = block.get("schemas") or {}
        for name, definition in block.items():
            if name in names:
                for prop in (definition or {}).get("properties") or {}:
                    params.setdefault(name, set()).add(prop)
    return names, params


# ─────────────────────────────────────────────────────────────────────────────
#  Reporting
# ─────────────────────────────────────────────────────────────────────────────

class Out:
    def __init__(self, as_json: bool, colour: bool = True):
        self.json = as_json
        self.colour = colour and sys.stdout.isatty()

    def paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.colour else text

    def ok(self, msg):      print(self.paint("  PASS  ", "32") + msg) if not self.json else None
    def warn(self, msg):    print(self.paint("  WARN  ", "33") + msg) if not self.json else None
    def fail(self, msg):    print(self.paint("  FAIL  ", "31") + msg) if not self.json else None
    def info(self, msg):    print(("  · " + msg) if not self.json else None)
    def head(self, msg):    print(f"\n{msg}") if not self.json else None


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify the code↔database contract.")
    parser.add_argument("--list", action="store_true",
                        help="print the extracted contract and exit (no network)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--spec-only", action="store_true", help="check RPCs only, skip column probes")
    parser.add_argument("--ignore-tables", default="",
                        help="comma-separated tables to skip, e.g. migration-gated ones")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--env-file", default=str(BACKEND_ROOT / ".env"))
    args = parser.parse_args(argv)

    contract = build_contract(BACKEND_ROOT)
    ignore = {t.strip() for t in args.ignore_tables.split(",") if t.strip()}

    if args.list:
        if args.as_json:
            print(json.dumps({
                "tables": {t: sorted(v["columns"]) for t, v in sorted(contract.tables.items())},
                "rpcs": {r: sorted(v["params"]) for r, v in sorted(contract.rpcs.items())},
                "totals": {
                    "tables": len(contract.tables),
                    "columns": sum(len(v["columns"]) for v in contract.tables.values()),
                    "rpcs": len(contract.rpcs),
                },
            }, indent=2))
        else:
            print(f"Extracted contract from app/ — {len(contract.tables)} tables, "
                  f"{sum(len(v['columns']) for v in contract.tables.values())} distinct table.column "
                  f"references, {len(contract.rpcs)} RPCs\n")
            for table, meta in sorted(contract.tables.items()):
                cols = ", ".join(sorted(meta["columns"])) or "*"
                print(f"  {table}\n      {cols}")
            print("\n  RPCs")
            for name, meta in sorted(contract.rpcs.items()):
                print(f"      {name}({', '.join(sorted(meta['params']))})")
        return 0

    env_file = Path(args.env_file)
    if load_dotenv is not None and env_file.exists():
        load_dotenv(env_file, override=False)

    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing — run "
              "scripts/check_supabase.py first.", file=sys.stderr)
        return 2

    out = Out(args.as_json)
    live = Live(url, key, args.timeout, args.workers)
    started = time.time()
    failures: list[str] = []
    warnings: list[str] = []
    summary = {"tables_ok": 0, "tables_missing": [], "columns_missing": {}, "rpcs_missing": [],
               "rpc_params_missing": {}, "errors": []}

    # ── tables + columns ────────────────────────────────────────────────────
    tables = sorted(t for t in contract.tables if t not in ignore)
    if not args.spec_only:
        out.head(f"Verifying {len(tables)} tables and "
                 f"{sum(len(contract.tables[t]['columns']) for t in tables)} column references")

        def run(table: str):
            cols = sorted(contract.tables[table]["columns"])
            return table, probe_table(live, table, cols)

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for table, (status, bad, detail) in pool.map(run, tables):
                if status == "ok":
                    summary["tables_ok"] += 1
                    continue
                where = ", ".join(sorted(set(contract.tables[table]["ops"]))[:3])
                if status == "missing_table":
                    summary["tables_missing"].append(table)
                    failures.append(f"table '{table}' does not exist (used at {where})")
                    out.fail(f"missing table   {table}   [{where}]")
                elif status == "missing_columns":
                    summary["columns_missing"][table] = bad
                    for col in bad:
                        refs = ", ".join(sorted(set(contract.tables[table]["columns"].get(col, [])))[:3])
                        failures.append(f"column '{table}.{col}' does not exist (used at {refs})")
                    out.fail(f"missing columns {table}.{', '.join(bad)}   [{where}]")
                elif status == "denied":
                    warnings.append(f"table '{table}' denied to the service-role key ({detail})")
                    out.warn(f"not readable    {table}   ({detail})")
                else:
                    summary["errors"].append(f"{table}: {detail}")
                    warnings.append(f"could not verify '{table}': {detail}")
                    out.warn(f"unverified      {table}   ({detail})")

        if summary["tables_ok"]:
            out.ok(f"{summary['tables_ok']}/{len(tables)} tables have every referenced column")

    # ── RPCs (from the OpenAPI spec — never executed) ────────────────────────
    if contract.rpcs:
        spec = fetch_spec(live)
        if spec is None:
            out.warn("could not fetch the PostgREST OpenAPI spec — RPC checks skipped "
                     "(functions are never executed by this script)")
        else:
            known, rpc_params = spec_rpcs(spec)
            out.head(f"Verifying {len(contract.rpcs)} RPCs against {len(known)} exposed functions")
            if not known:
                out.warn("spec returned no /rpc/ paths — skipping RPC verification")
            for name in sorted(contract.rpcs):
                where = ", ".join(sorted(set(contract.rpcs[name]["ops"]))[:3])
                if name not in known:
                    summary["rpcs_missing"].append(name)
                    failures.append(f"RPC '{name}' is not exposed by the database (used at {where})")
                    out.fail(f"missing RPC     {name}   [{where}]")
                    continue
                expected = set(contract.rpcs[name]["params"])
                actual = rpc_params.get(name, set())
                unknown = sorted(p for p in expected if actual and p not in actual)
                if unknown:
                    summary["rpc_params_missing"][name] = unknown
                    for p in unknown:
                        refs = ", ".join(sorted(set(contract.rpcs[name]["params"].get(p, [])))[:3])
                        failures.append(f"RPC '{name}' has no parameter '{p}' (used at {refs})")
                    out.fail(f"bad RPC params  {name}: {', '.join(unknown)}   [{where}]")
                else:
                    out.ok(f"RPC {name} ({len(expected)} param(s))")

    elapsed = time.time() - started
    if args.as_json:
        print(json.dumps({
            "ok": not (failures or (args.strict and warnings)),
            "elapsed_seconds": round(elapsed, 2),
            "tables_referenced": len(tables),
            "rpcs_referenced": len(contract.rpcs),
            "failures": failures,
            "warnings": warnings,
            "summary": summary,
        }, indent=2))
    else:
        print("\n" + "─" * 68)
        if failures:
            print(Out(False, False).paint(f"✗ Contract check FAILED — {len(failures)} problem(s), "
                                          f"{len(warnings)} warning(s)", "31") + f"  ({elapsed:.1f}s)")
            for f in failures[:40]:
                print(f"    • {f}")
            if len(failures) > 40:
                print(f"    … and {len(failures) - 40} more")
        else:
            print(Out(False, False).paint("✓ Contract holds — every table, column and RPC the code "
                                          f"uses exists in the database ({elapsed:.1f}s)", "32"))
            if warnings:
                for w in warnings[:10]:
                    print(f"    • {w}")
        print("─" * 68)

    return 1 if failures or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
