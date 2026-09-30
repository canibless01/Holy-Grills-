#!/usr/bin/env python3
"""
Supabase connection preflight for the Holy Grills backend.

Run this before `python run.py` (or as a CI / deploy gate) to answer one
question: **is this backend actually connected to its Supabase project?**

It works in two layers:

  1. Offline config validation — no network required.
       * SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY are present
       * the URL points at a real project ref
       * both API keys are well-formed HS256 JWTs
       * both keys are signed by the project's JWT secret (when provided)
       * each key carries the role it is supposed to (anon vs service_role)
       * both keys belong to the project in SUPABASE_URL (the `ref` claim)
       * keys are not expired / not about to expire
       * the Flask SECRET_KEY is not left on its insecure default

  2. Live connectivity checks (skipped with --offline)
       * Supabase Auth  — GET /auth/v1/health
       * PostgREST      — GET /rest/v1/profiles with the service-role key
                          (exactly what GET /api/health probes)
       * PostgREST      — GET /rest/v1/menu_items with the anon key
       * Every table the app actually queries (discovered by scanning
         app/ for `.table("...")` calls) — exists / missing / denied

Usage
-----
    python scripts/check_supabase.py              # full check
    python scripts/check_supabase.py --offline    # config only, no network
    python scripts/check_supabase.py --json       # machine-readable output
    python scripts/check_supabase.py --tables-only
    python scripts/check_supabase.py --skip-tables
    python scripts/check_supabase.py --env-file .env.production

Exit codes
----------
    0  all checks passed (warnings allowed)
    1  one or more checks failed
    2  configuration error — required env vars are missing/empty

The script is read-only: it never inserts, updates or deletes anything.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover - requests is in requirements.txt
    print("This script needs `requests` (pip install -r requirements.txt).", file=sys.stderr)
    raise SystemExit(2)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is in requirements.txt
    load_dotenv = None


BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_REF_RE = re.compile(r"^https://([a-z0-9]{20})\.supabase\.co/?$")
INSECURE_SECRETS = {"change-me-in-production", "change-me-to-a-long-random-string", ""}

# Tables the app talks to, discovered from app/**/*.py at runtime so this list
# can never drift from the code. See discover_tables().
TABLE_CALL_RE = re.compile(r"""\.table\(\s*["']([a-z0-9_]+)["']\s*\)""")

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"
_GLYPH = {OK: "PASS", WARN: "WARN", FAIL: "FAIL", INFO: "INFO"}


class Report:
    """Collects check results and renders them as text or JSON."""

    def __init__(self, as_json: bool = False, verbose: bool = False):
        self.as_json = as_json
        self.verbose = verbose
        self.results: list[dict] = []
        self.started = time.time()

    def add(self, name: str, status: str, detail: str = "", hint: str = "", **extra):
        entry = {"check": name, "status": status, "detail": detail}
        if hint:
            entry["hint"] = hint
        if extra:
            entry["extra"] = extra
        self.results.append(entry)
        if not self.as_json and status != INFO:
            colour = {OK: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"}.get(status, "")
            reset = "\033[0m" if colour else ""
            line = f"  {colour}{_GLYPH[status]}{reset}  {name:<28} {detail}"
            print(line)
            if hint and status in (WARN, FAIL):
                print(f"          ↳ {hint}")
        elif not self.as_json and self.verbose:
            print(f"  {_GLYPH[INFO]}  {name:<28} {detail}")
        return entry

    @property
    def failed(self) -> list[dict]:
        return [r for r in self.results if r["status"] == FAIL]

    @property
    def warned(self) -> list[dict]:
        return [r for r in self.results if r["status"] == WARN]

    def section(self, title: str):
        if not self.as_json:
            print(f"\n{title}")

    def finish(self, project_ref: str | None):
        elapsed = time.time() - self.started
        if self.as_json:
            print(json.dumps({
                "ok": not self.failed,
                "project_ref": project_ref,
                "elapsed_seconds": round(elapsed, 2),
                "counts": {
                    "passed": len([r for r in self.results if r["status"] == OK]),
                    "warnings": len(self.warned),
                    "failures": len(self.failed),
                },
                "results": self.results,
            }, indent=2))
            return 1 if self.failed else 0

        passed = len([r for r in self.results if r["status"] == OK])
        print("\n" + "─" * 68)
        if self.failed:
            print(f"\033[31m✗ Supabase connection FAILED\033[0m — "
                  f"{len(self.failed)} failed, {len(self.warned)} warning(s), {passed} passed "
                  f"({elapsed:.1f}s)")
            for r in self.failed:
                print(f"    • {r['check']}: {r['detail']}")
                if r.get("hint"):
                    print(f"      → {r['hint']}")
        else:
            target = f" (project {project_ref})" if project_ref else ""
            print(f"\033[32m✓ Supabase connection OK{target}\033[0m — "
                  f"{passed} passed, {len(self.warned)} warning(s) ({elapsed:.1f}s)")
            if self.warned:
                print("  Warnings are non-fatal but worth fixing:")
                for r in self.warned:
                    print(f"    • {r['check']}: {r['detail']}")
        print("─" * 68)
        return 1 if self.failed else 0


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def mask(value: str) -> str:
    """Never print a full key."""
    if not value:
        return "(empty)"
    if len(value) <= 16:
        return value[:4] + "…"
    return f"{value[:8]}…{value[-4:]} ({len(value)} chars)"


def b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def decode_jwt(token: str) -> tuple[dict, dict, str]:
    """Return (header, payload, signature) without verifying anything."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a JWT (expected 3 dot-separated segments)")
    header = json.loads(b64url_decode(parts[0]))
    payload = json.loads(b64url_decode(parts[1]))
    return header, payload, parts[2]


def verify_hs256(token: str, secret: str) -> bool:
    """Constant-time HS256 signature check — the same maths Supabase uses."""
    try:
        header_b64, payload_b64, signature = token.split(".")
    except ValueError:
        return False
    expected = hmac.new(
        secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    try:
        actual = b64url_decode(signature)
    except Exception:
        return False
    return hmac.compare_digest(expected, actual)


def discover_tables(root: Path) -> list[str]:
    """Every table name the backend references via db.table("...")."""
    names: set[str] = set()
    for path in sorted(root.glob("app/**/*.py")):
        try:
            names.update(TABLE_CALL_RE.findall(path.read_text(encoding="utf-8")))
        except OSError:
            continue
    return sorted(names)


def request(session, method: str, url: str, *, api_key: str, timeout: float, params=None):
    return session.request(
        method,
        url,
        headers={"apikey": api_key, "Authorization": f"Bearer {api_key}"},
        params=params,
        timeout=timeout,
    )


def classify_error(resp, body: str) -> tuple[str, str]:
    """Map a PostgREST/Auth response to (hint, code)."""
    code = ""
    try:
        payload = json.loads(body)
        code = str(payload.get("code") or "")
        message = str(payload.get("message") or payload.get("error_description") or body)
    except Exception:
        message = body

    if resp.status_code == 401:
        return ("Key rejected — rotate/confirm it in Supabase → Project Settings → API keys.", code or message)
    if resp.status_code == 403:
        return ("Permission denied — check the key role and the table's RLS policies.", code or message)
    if resp.status_code == 404 and code == "PGRST205":
        return ("Table missing — apply the schema/migration for it in the Supabase SQL editor.", code)
    if resp.status_code == 429:
        return ("Rate limited by Supabase — retry later.", code or message)
    if resp.status_code >= 500:
        return ("Supabase returned a server error — check the project status page.", code or message)
    return (message[:160], code)


# ─────────────────────────────────────────────────────────────────────────────
#  Offline configuration checks
# ─────────────────────────────────────────────────────────────────────────────

def check_config(rep: Report, env: dict) -> str | None:
    rep.section("Configuration")

    url = (env.get("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = (env.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    anon_key = (env.get("SUPABASE_ANON_KEY") or "").strip()
    jwt_secret = (env.get("JWT_SECRET") or env.get("SUPABASE_JWT_SECRET") or "").strip()

    missing = [k for k, v in (
        ("SUPABASE_URL", url),
        ("SUPABASE_SERVICE_ROLE_KEY", service_key),
        ("SUPABASE_ANON_KEY", anon_key),
    ) if not v]
    if missing:
        rep.add("required env vars", FAIL, f"missing: {', '.join(missing)}",
                "Copy .env.example to .env and fill in the Supabase block.")
        return None
    rep.add("required env vars", OK, "SUPABASE_URL + service-role key + anon key present")

    project_ref = None
    match = PROJECT_REF_RE.match(url)
    if match:
        project_ref = match.group(1)
        rep.add("project url", OK, f"{url}  (ref {project_ref})")
    elif url.startswith("https://"):
        rep.add("project url", WARN, f"{url} (not a *.supabase.co URL)",
                "Fine for a custom domain — but confirm the project ref matches your keys.")
    else:
        rep.add("project url", FAIL, f"{url!r} is not an https:// URL",
                "Set SUPABASE_URL to your project URL, e.g. https://<ref>.supabase.co")
        return None

    # ── JWT secret / signing consistency ────────────────────────────────────
    if jwt_secret:
        source = "JWT_SECRET" if env.get("JWT_SECRET") else "SUPABASE_JWT_SECRET"
        rep.add("jwt secret", OK, f"present via {source} ({len(jwt_secret)} chars)")
    else:
        rep.add("jwt secret", WARN, "JWT_SECRET / SUPABASE_JWT_SECRET not set",
                "Set it to Supabase → Project Settings → API → JWT secret. Auth still works "
                "(tokens are validated live), but the refresh TTL optimisation is disabled.")

    # ── Key integrity ────────────────────────────────────────────────────────
    for label, key, expected_role in (
        ("anon key", anon_key, "anon"),
        ("service-role key", service_key, "service_role"),
    ):
        try:
            header, payload, _ = decode_jwt(key)
        except Exception as exc:
            rep.add(label, FAIL, f"unreadable JWT ({exc})",
                    f"Re-copy SUPABASE_{'ANON' if expected_role == 'anon' else 'SERVICE_ROLE'}_KEY "
                    "from Supabase → Project Settings → API.")
            continue

        role = payload.get("role")
        if header.get("alg") != "HS256":
            rep.add(label, WARN, f"unexpected alg '{header.get('alg')}' (expected HS256)")
        elif role != expected_role:
            rep.add(label, FAIL, f"role is '{role}', expected '{expected_role}'",
                    "The anon and service-role keys look swapped.")
        else:
            rep.add(label, OK, f"{mask(key)}  role={role}")

        ref = payload.get("ref")
        if project_ref and ref and ref != project_ref:
            rep.add(f"{label} project ref", FAIL,
                    f"key belongs to project '{ref}' but SUPABASE_URL is '{project_ref}'",
                    "The keys are from a different Supabase project than the URL.")
        elif project_ref and ref == project_ref:
            rep.add(f"{label} project ref", OK, f"matches {project_ref}")

        exp = payload.get("exp")
        if exp:
            remaining_days = (exp - time.time()) / 86400
            when = time.strftime("%Y-%m-%d", time.gmtime(exp))
            if remaining_days < 0:
                rep.add(f"{label} expiry", FAIL, f"expired on {when}",
                        "Generate a new API key in the Supabase dashboard.")
            elif remaining_days < 180:
                rep.add(f"{label} expiry", WARN, f"expires {when} ({remaining_days:.0f} days)",
                        "Plan a key rotation before it expires.")
            else:
                rep.add(f"{label} expiry", OK, f"valid until {when}")

        if jwt_secret:
            if verify_hs256(key, jwt_secret):
                rep.add(f"{label} signature", OK, "signed by the configured JWT secret")
            else:
                rep.add(f"{label} signature", FAIL, "NOT signed by the configured JWT secret",
                        "The stored JWT secret does not match this project — re-copy it from "
                        "Supabase → Project Settings → API → JWT secret.")

    # ── Flask session secret (production boot guard) ─────────────────────────
    secret_key = (env.get("SECRET_KEY") or env.get("SESSION_SECRET") or "").strip()
    if secret_key in INSECURE_SECRETS:
        rep.add("flask SECRET_KEY", WARN, "unset or still the public default",
                "Set a long random SECRET_KEY — production refuses to boot without it "
                "(newsletter unsubscribe tokens are signed with it).")
    else:
        rep.add("flask SECRET_KEY", OK, f"set ({mask(secret_key)})")

    return project_ref


# ─────────────────────────────────────────────────────────────────────────────
#  Live checks
# ─────────────────────────────────────────────────────────────────────────────

def check_auth(rep: Report, session, url: str, anon_key: str, timeout: float) -> None:
    rep.section("Live connectivity")
    try:
        started = time.time()
        resp = request(session, "GET", f"{url}/auth/v1/health",
                       api_key=anon_key, timeout=timeout)
        ms = (time.time() - started) * 1000
    except requests.exceptions.RequestException as exc:
        rep.add("auth service", FAIL, f"unreachable: {type(exc).__name__}",
                "Network cannot reach Supabase (offline, firewall/egress allow-list, or DNS). "
                "If you are in a sandboxed CI container, run this check where the internet is open.")
        return
    if resp.status_code == 200:
        rep.add("auth service", OK, f"/auth/v1/health → 200 ({ms:.0f} ms)")
    else:
        hint, code = classify_error(resp, resp.text)
        rep.add("auth service", FAIL, f"/auth/v1/health → {resp.status_code} {code}".strip(), hint)


def check_rest(rep: Report, session, url: str, key: str, table: str, label: str,
               timeout: float) -> None:
    try:
        started = time.time()
        resp = request(session, "GET", f"{url}/rest/v1/{table}",
                       api_key=key, timeout=timeout,
                       params={"select": "id", "limit": "1"})
        ms = (time.time() - started) * 1000
    except requests.exceptions.RequestException as exc:
        rep.add(label, FAIL, f"unreachable: {type(exc).__name__}",
                "Network cannot reach Supabase (offline, firewall/egress allow-list, or DNS).")
        return
    if resp.status_code < 400:
        rep.add(label, OK, f"{table} → {resp.status_code} ({ms:.0f} ms)")
    else:
        hint, code = classify_error(resp, resp.text)
        rep.add(label, FAIL, f"{table} → {resp.status_code} {code}".strip(), hint)


def check_tables(rep: Report, session, url: str, service_key: str, tables: list[str],
                 timeout: float, workers: int = 8) -> None:
    rep.section(f"Schema ({len(tables)} tables referenced by app/)")

    # requests.Session is not thread-safe: give every worker its own (keeps
    # connection pooling per thread without sharing mutable state).
    local = threading.local()

    def worker_session():
        if not hasattr(local, "session"):
            local.session = requests.Session()
        return local.session

    def probe(table: str):
        try:
            resp = request(worker_session(), "GET", f"{url}/rest/v1/{table}",
                           api_key=service_key, timeout=timeout,
                           params={"select": "*", "limit": "0"})
            if resp.status_code < 400:
                return table, OK, ""
            hint, code = classify_error(resp, resp.text)
            status = FAIL if (resp.status_code == 404 or code == "PGRST205") else WARN
            detail = f"{resp.status_code} {code if code.isupper() else ''}".strip()
            return table, status, f"{detail} — {hint}"[:150]
        except requests.exceptions.RequestException as exc:
            return table, FAIL, f"unreachable: {type(exc).__name__}"

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(probe, tables):
            results.append(row)

    unreachable = [t for t, s, d in results if s == FAIL and d.startswith("unreachable")]
    missing = [t for t, s, d in results if s == FAIL and not d.startswith("unreachable")]
    denied = [t for t, s, d in results if s == WARN]
    present = len(results) - len(missing) - len(denied) - len(unreachable)

    if unreachable:
        rep.add("table reachability", FAIL,
                f"{len(unreachable)}/{len(results)} tables unreachable — cannot verify the schema",
                "Same network problem as the connection checks above.")
        return

    if missing:
        rep.add("table reachability", FAIL,
                f"{len(missing)} of {len(results)} tables missing",
                "Apply the schema in the Supabase SQL editor: " + ", ".join(missing[:8]) +
                (" …" if len(missing) > 8 else ""),
                missing=missing)
    else:
        rep.add("table reachability", OK, f"all {len(results)} tables exist ({present} verified)")

    non_missing = [t for t in tables if t not in missing]
    if denied:
        rep.add("tables readable by service key", WARN,
                f"{len(denied)} table(s) answered with a permission error",
                "Service-role access is normally unrestricted — check RLS/grants for: " +
                ", ".join(denied[:8]) + (" …" if len(denied) > 8 else ""))
    elif non_missing:
        rep.add("tables readable by service key", OK,
                f"{len(non_missing)} table(s) probed read-only, no writes performed")


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the backend's Supabase connection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--offline", action="store_true",
                        help="run configuration checks only (no network calls)")
    parser.add_argument("--tables-only", action="store_true",
                        help="skip auth/REST checks and only verify the schema")
    parser.add_argument("--skip-tables", action="store_true",
                        help="skip the per-table schema sweep")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit a machine-readable report")
    parser.add_argument("--verbose", action="store_true", help="show informational lines")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="per-request timeout in seconds (default: 10)")
    parser.add_argument("--workers", type=int, default=8,
                        help="parallel requests for the schema sweep (default: 8)")
    parser.add_argument("--env-file", default=str(BACKEND_ROOT / ".env"),
                        help="path to the env file (default: <backend>/.env)")
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    if load_dotenv is not None and env_file.exists():
        load_dotenv(env_file, override=False)
    env = dict(os.environ)

    rep = Report(as_json=args.as_json, verbose=args.verbose)
    if not args.as_json:
        print("Holy Grills — Supabase connection check")
        print(f"env file : {env_file if env_file.exists() else '(not found — using process env)'}")
        print(f"python   : {sys.version.split()[0]}")

    project_ref = check_config(rep, env)
    if rep.failed:
        # Config is broken; live checks would only report the same thing louder.
        rep.finish(project_ref)
        return 2 if project_ref is None else 1

    url = (env.get("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = (env.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    anon_key = (env.get("SUPABASE_ANON_KEY") or "").strip()

    if args.offline:
        rep.section("Live connectivity")
        if not args.as_json:
            print("  SKIP  network checks            --offline: Auth, PostgREST and schema probes skipped")
        rep.add("network checks", INFO, "skipped (--offline)")
        return rep.finish(project_ref)

    session = requests.Session()
    if not args.tables_only:
        check_auth(rep, session, url, anon_key, args.timeout)
        check_rest(rep, session, url, service_key, "profiles", "database (service key)", args.timeout)
        check_rest(rep, session, url, anon_key, "menu_items", "database (anon key)", args.timeout)

    if not args.skip_tables:
        tables = discover_tables(BACKEND_ROOT)
        if tables:
            check_tables(rep, session, url, service_key, tables, args.timeout, args.workers)
        else:
            rep.add("schema sweep", WARN, "no db.table(...) calls found to verify")

    return rep.finish(project_ref)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
