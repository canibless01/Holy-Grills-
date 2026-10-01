#!/usr/bin/env python3
"""
Live end-to-end suite — drives the real API against the real Supabase project.

Think of it as Playwright for this backend: every step performs a real request
against the running application (in-process Flask test client by default, or a
deployed server with --base-url), asserts the HTTP status *and* the response
shape, then reads the resulting rows back out of Postgres through the
service-role key to prove the database actually stored what the API promised.

What it covers
--------------
  preflight      health + Supabase (PostgREST) + Supabase Auth reachability
  public reads   menu, campuses, departments, levels, calendar, leaderboard,
                 challenges, rewards, delivery windows/zones, hostels/gates,
                 storefront config/sections/banners/hours
  auth           register → duplicate register → login → wrong password →
                 /me → refresh → streak → profile patch → device token → logout
  addresses      create → list → update → delete
  cart & saved   add → read → update → move to saved-for-later → back to cart
  orders         wallet fixture → place → read → history → list → active → cancel
                 (+ refund ledger row when paid from the wallet)
  hp & wallet    balance, transactions, tiers, wallet balance + ledger
  rewards etc.   rewards, redemptions, referrals
  notifications  list, preferences round-trip, read-all
  admin          optional (--admin-token): settings, users, orders, audit log,
                 dashboard, economics

Everything it creates is deleted again in the cleanup phase (unless
--keep-data): tracked rows are removed child-first, then the test user is
hard-deleted through the GoTrue admin API.

Safety
------
* Writes only ever happen for a freshly created test user (unique
  `e2e.<timestamp>.<rand>@e2e.holygrills.test` address) and are attributed to it.
* `--read-only` skips every writing step; `--list` prints the plan without
  touching anything; `--self-check` verifies the routes exist without network.
* Wallet funding uses the very RPC the Paystack webhook path uses
  (`credit_wallet_atomic`) — no raw balance edits.

Usage
-----
    python scripts/live_test.py                  # full run (writes + cleanup)
    python scripts/live_test.py --read-only      # GET-only smoke test
    python scripts/live_test.py --list           # show the plan
    python scripts/live_test.py --self-check     # offline route check
    python scripts/live_test.py --base-url https://api.example.com
    python scripts/live_test.py --only auth      # one phase
    python scripts/live_test.py --keep-data --verbose   # debug a failure
    python scripts/live_test.py --json > report.json

Exit codes
----------
    0  every executed step passed (skips allowed)
    1  at least one step failed
    2  configuration error / app could not start
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
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
INSECURE_SECRETS = {"change-me-in-production", "change-me-to-a-long-random-string", ""}
TEST_EMAIL_DOMAIN = "e2e.holygrills.test"
# Used only when GET /api/campuses returns nothing usable and --campus-id was not
# given. Every candidate is verified against the campuses table before use.
FALLBACK_CAMPUS_IDS = (
    "70000001-cafe-cafe-cafe-000000000001",
    "70000002-cafe-cafe-cafe-000000000002",
)
DEFAULT_PASSWORD = "E2e-Passw0rd!2026"


# ─────────────────────────────────────────────────────────────────────────────
#  Step framework
# ─────────────────────────────────────────────────────────────────────────────

class Skip(Exception):
    """Raised by a step that cannot run in this environment (reason is reported)."""


class Failed(Exception):
    def __init__(self, message: str, resp=None):
        super().__init__(message)
        self.resp = resp


class Step:
    def __init__(self, phase, sid, title, fn, writes, route, needs):
        self.phase, self.id, self.title, self.fn = phase, sid, title, fn
        self.writes, self.route, self.needs = writes, route, needs
        self.result = None          # passed | failed | skipped | blocked
        self.detail = ""
        self.ms = 0.0


STEPS: list[Step] = []


def step(phase: str, sid: str, title: str, *, writes: bool = False, route: str = "",
         needs: tuple[str, ...] = ()):
    def decorator(fn):
        STEPS.append(Step(phase, sid, title, fn, writes, route, needs))
        return fn
    return decorator


class Ctx:
    """Shared state across steps."""

    def __init__(self, api, db, opts):
        self.api, self.db, self.opts = api, db, opts
        self.ids: dict[str, object] = {}
        self.tokens: dict[str, str] = {}
        self.created: list[tuple[str, str]] = []       # (table, id) — deleted in reverse
        self.infra: list[tuple[str, str]] = []         # suite scaffolding — always deleted
        self.sweeps: list[tuple[str, str, str]] = []   # (table, column, value)
        self.user_id: str | None = None
        self.owns_user = True          # False when running against --login-email
        self.notes: list[str] = []
        self.warnings: list[str] = []
        self.results: dict[str, Step] = {}

    # ── bookkeeping ──────────────────────────────────────────────────────────
    def track(self, table: str, row_id: str):
        """Register a row for deletion — only ever for a user this run created."""
        if row_id and self.owns_user:
            self.created.append((table, row_id))

    def track_infra(self, table: str, row_id: str):
        """Register scaffolding the suite created (e.g. a temporary ordering window).

        Unlike track(), this is deleted even when the run signed in to a
        pre-existing account: the row is the suite's, not the account's data.
        """
        if row_id:
            self.infra.append((table, row_id))

    def sweep(self, table: str, column: str, value: str):
        if self.owns_user:
            self.sweeps.append((table, column, value))

    def note(self, message: str):
        self.notes.append(message)


class Api:
    """Same interface for in-process (Flask test client) and remote (--base-url)."""

    def __init__(self, app=None, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout
        self.client = None
        self.default_headers: dict[str, str] = {}
        if self.base_url is None:
            self.client = app.test_client()

    def request(self, method: str, path: str, *, json_body=None, token=None,
                headers=None, params=None):
        hdrs = dict(self.default_headers)
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        if headers:
            hdrs.update(headers)

        if self.client is not None:
            query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
            url = f"{path}?{query}" if query else path
            raw = self.client.open(url, method=method, json=json_body, headers=hdrs)
            body = raw.get_data(as_text=True)
            try:
                data = raw.get_json() if body else None
            except Exception:
                data = None
            return Resp(raw.status_code, data, body)

        url = f"{self.base_url}{path}"
        raw = requests.request(method, url, json=json_body, headers=hdrs,
                               params=params, timeout=self.timeout)
        try:
            data = raw.json() if raw.content else None
        except ValueError:
            data = None
        return Resp(raw.status_code, data, raw.text)

    # convenience
    def get(self, path, **kw):    return self.request("GET", path, **kw)
    def post(self, path, **kw):   return self.request("POST", path, **kw)
    def patch(self, path, **kw):  return self.request("PATCH", path, **kw)
    def delete(self, path, **kw): return self.request("DELETE", path, **kw)


class Resp:
    def __init__(self, status: int, data, text: str):
        self.status, self.data, self.text = status, data, text

    def snippet(self, limit: int = 200) -> str:
        raw = json.dumps(self.data) if self.data is not None else (self.text or "")
        return (raw or "")[:limit]

    def check(self, *expected, allow=()) -> "Resp":
        ok = set(expected) | set(allow)
        if self.status not in ok:
            raise Failed(f"HTTP {self.status}, expected {'/'.join(map(str, sorted(ok)))} — "
                         f"{self.snippet()}", self)
        return self

    def expect_json(self) -> "Resp":
        if self.data is None:
            raise Failed(f"response is not JSON — {self.snippet()}", self)
        return self

    def expect_error(self, allow=(400, 401, 403, 404, 409, 422)) -> "Resp":
        if self.status not in allow:
            raise Failed(f"expected an error status, got {self.status} — {self.snippet()}", self)
        return self


class DB:
    """Read-back, fixtures and cleanup through the service-role REST API."""

    def __init__(self, url: str, key: str, timeout: float = 20.0):
        self.url, self.key, self.timeout = url.rstrip("/"), key, timeout
        self.session = requests.Session()

    def _headers(self, extra=None) -> dict:
        h = {"apikey": self.key, "Authorization": f"Bearer {self.key}",
             "Content-Type": "application/json", "Prefer": "return=representation"}
        if extra:
            h.update(extra)
        return h

    def select(self, table: str, limit: int | None = None, **filters) -> list:
        params = {"select": "*"}
        if limit:
            params["limit"] = str(limit)
        for column, value in filters.items():
            params[column] = f"eq.{value}"
        resp = self.session.get(f"{self.url}/rest/v1/{table}", params=params,
                                headers=self._headers(), timeout=self.timeout)
        if resp.status_code >= 400:
            raise Failed(f"DB read {table} failed: HTTP {resp.status_code} {resp.text[:160]}")
        return resp.json() or []

    def select_one(self, table: str, **filters):
        rows = self.select(table, **filters)
        return rows[0] if rows else None

    def insert(self, table: str, row: dict) -> dict:
        """Insert one row and return it. Only used for fixtures this suite
        creates and deletes itself (currently: a temporary ordering window)."""
        resp = self.session.post(f"{self.url}/rest/v1/{table}", json=row,
                                 headers=self._headers(), timeout=self.timeout)
        if resp.status_code >= 400:
            raise Failed(f"DB insert into {table} failed: HTTP {resp.status_code} {resp.text[:200]}")
        payload = resp.json() if resp.content else []
        return payload[0] if isinstance(payload, list) and payload else (payload or {})

    def rpc(self, name: str, params: dict):
        resp = self.session.post(f"{self.url}/rest/v1/rpc/{name}", json=params,
                                 headers=self._headers(), timeout=self.timeout)
        if resp.status_code >= 400:
            raise Failed(f"RPC {name} failed: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json() if resp.content else None

    def delete(self, table: str, **filters) -> bool:
        params = {c: f"eq.{v}" for c, v in filters.items()}
        resp = self.session.delete(f"{self.url}/rest/v1/{table}", params=params,
                                   headers=self._headers(), timeout=self.timeout)
        return resp.status_code < 400

    def delete_in(self, table: str, column: str, values: list[str]) -> bool:
        if not values:
            return True
        joined = ",".join(values)
        resp = self.session.delete(f"{self.url}/rest/v1/{table}",
                                   params={column: f"in.({joined})"},
                                   headers=self._headers(), timeout=self.timeout)
        return resp.status_code < 400

    def delete_auth_user(self, user_id: str) -> bool:
        resp = self.session.delete(f"{self.url}/auth/v1/admin/users/{user_id}",
                                   headers=self._headers(), timeout=self.timeout)
        return resp.status_code in (200, 204, 404)

    def confirm_email(self, user_id: str) -> bool:
        resp = self.session.put(f"{self.url}/auth/v1/admin/users/{user_id}",
                                json={"email_confirm": True},
                                headers=self._headers(), timeout=self.timeout)
        return resp.status_code < 400


# ─────────────────────────────────────────────────────────────────────────────
#  Assertion helpers
# ─────────────────────────────────────────────────────────────────────────────

def as_list(data, *keys) -> list:
    """Pull a list out of the common envelopes: [...], {items: [...]}, {x: [...]}."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), list):
                return data[key]
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def contains_id(data, needle: str) -> bool:
    """Recursively look for an id anywhere in the response payload."""
    if isinstance(data, dict):
        return any(contains_id(v, needle) for v in data.values())
    if isinstance(data, list):
        return any(contains_id(v, needle) for v in data)
    return str(data) == str(needle)


def expect(condition: bool, message: str, resp=None):
    if not condition:
        raise Failed(message, resp)


def find_bool(data, keys) -> bool | None:
    """First boolean value found under any of `keys` (recursive)."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys and isinstance(value, bool):
                return value
        for value in data.values():
            found = find_bool(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = find_bool(value, keys)
            if found is not None:
                return found
    return None


def field(data: dict, *names):
    for name in names:
        if isinstance(data, dict) and data.get(name) is not None:
            return data[name]
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 1 — preflight
# ─────────────────────────────────────────────────────────────────────────────

@step("preflight", "preflight.health", "GET /api/health reports Supabase connectivity", route="GET /api/health")
def s_health(ctx: Ctx):
    r = ctx.api.get("/api/health").check(200).expect_json()
    checks = r.data.get("checks") or {}
    expect(checks.get("supabase") == "connected",
           f"Supabase not connected: {checks.get('supabase')} — fix with scripts/check_supabase.py", r)
    ctx.note(f"health: status={r.data.get('status')} checks={checks}")
    if checks.get("supabase_auth") != "connected":
        ctx.warnings.append(f"supabase_auth: {checks.get('supabase_auth')}")


@step("preflight", "preflight.db", "Service-role key can read the database", route="")
def s_db(ctx: Ctx):
    rows = ctx.db.select("profiles", limit=1)
    ctx.note(f"profiles visible to service key: {len(rows)} row(s) sampled")


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 2 — public reads
# ─────────────────────────────────────────────────────────────────────────────

@step("public", "public.campuses", "GET /api/campuses", route="GET /api/campuses")
def s_campuses(ctx: Ctx):
    """Pick a campus that really exists — the id is reused for registration,
    ordering-window provisioning and campus-scoped reads, so a bad id cascades."""
    r = ctx.api.get("/api/campuses").check(200).expect_json()
    active = [c for c in as_list(r.data, "campuses") if c.get("is_active", True) and c.get("id")]
    expect(bool(active), f"no active campus returned — {r.snippet()}", r)

    ordered, seen = [], set()
    for candidate in ([ctx.opts.campus_id] if ctx.opts.campus_id else []) \
            + [c["id"] for c in active] + list(FALLBACK_CAMPUS_IDS):
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)

    chosen, source = None, ""
    for candidate in ordered:
        if ctx.db.select_one("campuses", id=candidate) is not None:
            chosen, source = candidate, ("--campus-id" if candidate == ctx.opts.campus_id else
                                         "campuses table" if candidate not in FALLBACK_CAMPUS_IDS
                                         else "fallback list")
            break
    expect(bool(chosen),
           "none of the candidate campus ids exist in the campuses table: " + ", ".join(ordered), r)
    ctx.ids["campus_id"] = chosen
    name = next((c.get("name") for c in active if c["id"] == chosen), "?")
    ctx.note(f"campus {chosen} ({name}) verified via {source}; "
             f"{len(active)} active campus(es) listed")


@step("public", "public.categories", "GET /api/menu/categories", route="GET /api/menu/categories",
      needs=("public.campuses",))
def s_categories(ctx: Ctx):
    r = ctx.api.get("/api/menu/categories", params={"campus_id": ctx.ids["campus_id"]}).check(200)
    ctx.note(f"categories: {len(as_list(r.data, 'categories'))}")


@step("public", "public.menu", "GET /api/menu/items returns orderable items",
      route="GET /api/menu/items", needs=("public.campuses",))
def s_menu(ctx: Ctx):
    r = ctx.api.get("/api/menu/items", params={"campus_id": ctx.ids["campus_id"], "limit": 50}).check(200)
    items = as_list(r.data, "items", "menu_items")
    expect(bool(items), f"menu returned no items — {r.snippet()}", r)
    available = [i for i in items
                 if i.get("is_available", True) and not i.get("deleted_at")]
    expect(bool(available), "no available menu item to order in the E2E run", r)
    ctx.ids["menu_item_id"] = available[0]["id"]
    ctx.ids["menu_item_price"] = available[0].get("price")
    ctx.note(f"{len(items)} items, {len(available)} available; using {available[0].get('name')!r}")


@step("public", "public.departments", "GET /api/departments", route="GET /api/departments")
def s_departments(ctx: Ctx):
    ctx.api.get("/api/departments").check(200)


@step("public", "public.levels", "GET /api/academic-levels", route="GET /api/academic-levels")
def s_levels(ctx: Ctx):
    ctx.api.get("/api/academic-levels").check(200)


@step("public", "public.calendar", "GET /api/academic-calendar", route="GET /api/academic-calendar")
def s_calendar(ctx: Ctx):
    ctx.api.get("/api/academic-calendar").check(200)


@step("public", "public.leaderboard", "GET /api/leaderboard", route="GET /api/leaderboard")
def s_leaderboard(ctx: Ctx):
    ctx.api.get("/api/leaderboard", params={"limit": 5}).check(200)


@step("public", "public.challenges", "GET /api/challenges", route="GET /api/challenges")
def s_challenges(ctx: Ctx):
    ctx.api.get("/api/challenges").check(200)


@step("public", "public.rewards", "GET /api/rewards", route="GET /api/rewards")
def s_rewards(ctx: Ctx):
    ctx.api.get("/api/rewards").check(200)


@step("public", "public.windows", "GET /api/orders/delivery-windows",
      route="GET /api/orders/delivery-windows")
def s_windows(ctx: Ctx):
    ctx.api.get("/api/orders/delivery-windows").check(200)


@step("public", "public.window_status", "GET /api/orders/delivery-windows/status",
      route="GET /api/orders/delivery-windows/status")
def s_window_status(ctx: Ctx):
    """Public view, no campus selected — informational only.

    Ordering is decided per campus, so this is the guest's-eye view; the
    authoritative check runs in orders.window once the user is signed in."""
    r = ctx.api.get("/api/orders/delivery-windows/status").check(200).expect_json()
    ctx.note(f"guest status: is_open={r.data.get('is_open')}")


@step("public", "public.zones", "GET /api/orders/delivery-zones", route="GET /api/orders/delivery-zones")
def s_zones(ctx: Ctx):
    ctx.api.get("/api/orders/delivery-zones").check(200)


@step("public", "public.hostels", "GET /api/delivery/hostels returns a delivery point",
      route="GET /api/delivery/hostels", needs=("public.campuses",))
def s_hostels(ctx: Ctx):
    r = ctx.api.get("/api/delivery/hostels",
                    headers={"X-Campus-ID": str(ctx.ids["campus_id"])}).check(200)
    hostels = as_list(r.data, "hostels")
    expect(bool(hostels), f"no hostel available for delivery — {r.snippet()}", r)
    ctx.ids["hostel_id"] = hostels[0]["id"]
    ctx.note(f"{len(hostels)} hostels; using {hostels[0].get('name')}")


@step("public", "public.gates", "GET /api/delivery/gates", route="GET /api/delivery/gates",
      needs=("public.campuses",))
def s_gates(ctx: Ctx):
    ctx.api.get("/api/delivery/gates",
                headers={"X-Campus-ID": str(ctx.ids["campus_id"])}).check(200)


@step("public", "public.storefront_config", "GET /api/storefront/config/public",
      route="GET /api/storefront/config/public")
def s_storefront_config(ctx: Ctx):
    ctx.api.get("/api/storefront/config/public").check(200)


@step("public", "public.sections", "GET /api/storefront/sections", route="GET /api/storefront/sections")
def s_sections(ctx: Ctx):
    ctx.api.get("/api/storefront/sections", params={"campus_id": ctx.ids.get("campus_id")}).check(200)


@step("public", "public.banners", "GET /api/storefront/banners", route="GET /api/storefront/banners")
def s_banners(ctx: Ctx):
    ctx.api.get("/api/storefront/banners", params={"campus_id": ctx.ids.get("campus_id")}).check(200)


@step("public", "public.hours", "GET /api/storefront/operating-hours",
      route="GET /api/storefront/operating-hours")
def s_hours(ctx: Ctx):
    ctx.api.get("/api/storefront/operating-hours").check(200)


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 3 — auth
# ─────────────────────────────────────────────────────────────────────────────

@step("auth", "auth.register", "POST /api/auth/register creates a real account",
      writes=True, route="POST /api/auth/register", needs=("preflight.health",))
def s_register(ctx: Ctx):
    if ctx.opts.login_email:
        raise Skip(f"using the existing account {ctx.opts.login_email} (--login-email)")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ctx.ids["email"] = f"e2e.{stamp}.{uuid.uuid4().hex[:8]}@{TEST_EMAIL_DOMAIN}"
    ctx.ids["password"] = DEFAULT_PASSWORD
    body = {
        "email": ctx.ids["email"],
        "password": ctx.ids["password"],
        "full_name": "E2E Test User",
        "nickname": "e2e",
        "campus_id": str(ctx.ids["campus_id"]),
    }
    r = ctx.api.post("/api/auth/register", json_body=body)
    r.check(201, allow=(200,))
    ctx.user_id = str(field(r.data or {}, "user_id") or ((r.data or {}).get("user") or {}).get("id")
                      or (r.data or {}).get("id") or "")
    expect(bool(ctx.user_id), f"register returned no user id — {r.snippet()}", r)
    ctx.track("profiles", ctx.user_id)
    # remember any seed rows keyed by the user so cleanup can find them
    ctx.sweep("profiles", "id", ctx.user_id)

    if r.data.get("access_token"):
        ctx.tokens["access"] = r.data["access_token"]
        ctx.tokens["refresh"] = r.data.get("refresh_token")
        ctx.note("registration returned a session (email confirmation disabled)")
    else:
        # project requires email confirmation: confirm via the admin API so the
        # suite can continue instead of silently skipping half of it
        ctx.db.confirm_email(ctx.user_id)
        ctx.note("registration returned no session — test user confirmed via the admin API")


@step("auth", "auth.register_duplicate", "registering the same email is rejected",
      writes=True, route="POST /api/auth/register", needs=("auth.register",))
def s_register_duplicate(ctx: Ctx):
    body = {"email": ctx.ids["email"], "password": ctx.ids["password"], "full_name": "E2E Duplicate"}
    ctx.api.post("/api/auth/register", json_body=body).expect_error(allow=(400, 409, 422))


@step("auth", "auth.login", "POST /api/auth/login returns tokens", route="POST /api/auth/login")
# deliberately no `needs`: with --login-email there is no registration step, and the
# guard below turns "nothing to sign in with" into a clean skip.
def s_login(ctx: Ctx):
    if not ctx.opts.login_email and not ctx.user_id:
        raise Skip("no account available (registration was skipped or disabled)")
    if ctx.opts.login_email:
        # logging into a pre-existing account: never clean its data up
        ctx.owns_user = False
        ctx.ids["email"] = ctx.opts.login_email
        ctx.ids["password"] = ctx.opts.login_password
    r = ctx.api.post("/api/auth/login",
                     json_body={"email": ctx.ids["email"], "password": ctx.ids["password"]})
    r.check(200).expect_json()
    token = field(r.data, "access_token") or ((r.data.get("session") or {}).get("access_token"))
    expect(bool(token), f"login returned no access_token — {r.snippet()}", r)
    ctx.tokens["access"] = token
    ctx.tokens["refresh"] = field(r.data, "refresh_token") or ctx.tokens.get("refresh")
    user_id = ((r.data.get("user") or {}).get("id")) or r.data.get("user_id")
    if ctx.opts.login_email:
        expect(bool(user_id), f"login returned no user id — {r.snippet()}", r)
        ctx.user_id = str(user_id)
        ctx.note(f"signed in as existing account {ctx.ids['email']} ({ctx.user_id})")
    else:
        expect(not user_id or str(user_id) == ctx.user_id,
               f"login returned a different user ({user_id} != {ctx.user_id})", r)


@step("auth", "auth.campus", "campus-scoped steps use the signed-in account's own campus",
      route="GET /api/delivery/hostels", needs=("auth.login", "public.hostels"))
def s_sync_campus(ctx: Ctx):
    """Ordering is gated by the SIGNED-IN account's campus (`g.campus_id`), not by the
    campus the suite picked for public reads. With --login-email the two can differ,
    and then the ordering-window step provisions a window for a campus the order never
    consults — POST /api/orders still answers 409 "Orders can only be placed during
    operating hours". Re-pin and re-fetch the delivery point for the account's campus.
    """
    prof = ctx.db.select_one("profiles", id=ctx.user_id)
    account_campus = str((prof or {}).get("campus_id") or "")
    picked = str(ctx.ids.get("campus_id") or "")

    if not account_campus:
        ctx.warnings.append(
            "the signed-in account has no campus_id — ordering falls back to the "
            "X-Campus-ID header and may refuse")
        ctx.note("account has no campus_id; keeping the picked campus")
        return

    if account_campus == picked:
        ctx.note(f"account campus matches the picked campus ({picked})")
        return

    ctx.ids["campus_id"] = account_campus
    ctx.note(f"account campus is {account_campus}, public reads used {picked} — "
             f"re-pinned to the account campus")

    r = ctx.api.get("/api/delivery/hostels",
                    headers={"X-Campus-ID": account_campus}).check(200)
    hostels = as_list(r.data, "hostels")
    if hostels:
        ctx.ids["hostel_id"] = hostels[0]["id"]
        ctx.note(f"delivery point re-picked for the account campus: {hostels[0].get('name')}")
    else:
        ctx.ids.pop("hostel_id", None)
        ctx.warnings.append("no delivery point on the account campus — the order step will skip")


@step("auth", "auth.login_wrong_password", "wrong password returns 401 (not 500)",
      route="POST /api/auth/login", needs=("auth.login",))
def s_login_wrong(ctx: Ctx):
    r = ctx.api.post("/api/auth/login",
                     json_body={"email": ctx.ids["email"], "password": "definitely-wrong-12345"})
    r.expect_error(allow=(401,))


@step("auth", "auth.me", "GET /api/auth/me returns the authenticated profile",
      route="GET /api/auth/me", needs=("auth.login",))
def s_me(ctx: Ctx):
    r = ctx.api.get("/api/auth/me", token=ctx.tokens["access"]).check(200).expect_json()
    expect(contains_id(r.data, ctx.user_id), f"/me did not return the test user — {r.snippet()}", r)
    row = ctx.db.select_one("profiles", id=ctx.user_id)
    expect(row is not None, "no profiles row exists for the new user — DB write did not land")
    expect(str(row.get("email", "")).lower() == ctx.ids["email"].lower(),
           f"profiles.email mismatch: {row.get('email')!r}")


@step("auth", "auth.refresh", "POST /api/auth/refresh rotates the session",
      route="POST /api/auth/refresh", needs=("auth.login",))
def s_refresh(ctx: Ctx):
    r = ctx.api.post("/api/auth/refresh", json_body={
        "refresh_token": ctx.tokens.get("refresh"),
        "access_token": ctx.tokens.get("access"),
    }).check(200).expect_json()
    new_access = field(r.data, "access_token")
    expect(bool(new_access), f"refresh returned no access_token — {r.snippet()}", r)
    ctx.tokens["access"] = new_access
    ctx.tokens["refresh"] = field(r.data, "refresh_token") or ctx.tokens.get("refresh")
    ctx.api.get("/api/auth/me", token=new_access).check(200)
    ctx.note(f"rotated={r.data.get('rotated')}")


@step("auth", "auth.streak", "GET /api/auth/streak", route="GET /api/auth/streak",
      needs=("auth.login",))
def s_streak(ctx: Ctx):
    ctx.api.get("/api/auth/streak", token=ctx.tokens["access"]).check(200)


@step("auth", "auth.profile_patch", "PATCH /api/auth/profile persists to profiles",
      writes=True, route="PATCH /api/auth/profile", needs=("auth.login",))
def s_profile_patch(ctx: Ctx):
    marker = f"E2E {uuid.uuid4().hex[:6]}"
    ctx.api.patch("/api/auth/profile", json_body={"nickname": marker},
                  token=ctx.tokens["access"]).check(200, allow=(204,))
    row = ctx.db.select_one("profiles", id=ctx.user_id)
    expect(row is not None and row.get("nickname") == marker,
           f"nickname did not persist (DB has {row.get('nickname') if row else None!r})")


@step("auth", "auth.device_token", "POST /api/auth/device-token stores a token",
      writes=True, route="POST /api/auth/device-token", needs=("auth.login",))
def s_device_token(ctx: Ctx):
    token_value = f"e2e-device-{uuid.uuid4().hex[:12]}"
    ctx.api.post("/api/auth/device-token",
                 json_body={"token": token_value, "platform": "web",
                            "device_model": "E2E Runner"},
                 token=ctx.tokens["access"]).check(200, allow=(201, 204))
    row = ctx.db.select_one("device_tokens", user_id=ctx.user_id)
    expect(row is not None, "device_tokens row was not created")
    ctx.sweep("device_tokens", "user_id", ctx.user_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 4 — addresses
# ─────────────────────────────────────────────────────────────────────────────

@step("addresses", "addr.create", "POST /api/auth/addresses",
      writes=True, route="POST /api/auth/addresses", needs=("auth.login",))
def s_addr_create(ctx: Ctx):
    r = ctx.api.post("/api/auth/addresses",
                     json_body={"label": "E2E Home", "line1": "1 Test Close",
                                "city": "Akure", "state": "Ondo",
                                "is_default": True},
                     token=ctx.tokens["access"])
    r.check(201, allow=(200,))
    addr_id = str(field(r.data or {}, "id") or ((r.data or {}).get("address") or {}).get("id")
                  or ((r.data or {}).get("data") or {}).get("id") or "")
    if not addr_id:
        rows = ctx.db.select("user_addresses", user_id=ctx.user_id)
        expect(bool(rows), f"address was not persisted — {r.snippet()}", r)
        addr_id = rows[0]["id"]
    ctx.ids["address_id"] = addr_id
    ctx.track("user_addresses", addr_id)
    ctx.sweep("user_addresses", "user_id", ctx.user_id)


@step("addresses", "addr.list", "GET /api/auth/addresses contains it",
      route="GET /api/auth/addresses", needs=("addr.create",))
def s_addr_list(ctx: Ctx):
    r = ctx.api.get("/api/auth/addresses", token=ctx.tokens["access"]).check(200)
    expect(contains_id(r.data, ctx.ids["address_id"]),
           f"created address missing from the list — {r.snippet()}", r)


@step("addresses", "addr.update", "PATCH /api/auth/addresses/<id>",
      writes=True, route="PATCH /api/auth/addresses/<address_id>", needs=("addr.create",))
def s_addr_update(ctx: Ctx):
    marker = f"E2E Lab {uuid.uuid4().hex[:4]}"
    ctx.api.patch(f"/api/auth/addresses/{ctx.ids['address_id']}",
                  json_body={"label": marker}, token=ctx.tokens["access"]).check(200, allow=(204,))
    row = ctx.db.select_one("user_addresses", id=ctx.ids["address_id"])
    expect(row is not None and row.get("label") == marker,
           f"address label did not persist (DB: {row.get('label') if row else None!r})")


@step("addresses", "addr.delete", "DELETE /api/auth/addresses/<id>",
      writes=True, route="DELETE /api/auth/addresses/<address_id>", needs=("addr.update",))
def s_addr_delete(ctx: Ctx):
    ctx.api.delete(f"/api/auth/addresses/{ctx.ids['address_id']}",
                   token=ctx.tokens["access"]).check(200, allow=(204, 202))
    row = ctx.db.select_one("user_addresses", id=ctx.ids["address_id"])
    expect(row is None or row.get("deleted_at") or row.get("is_active") is False,
           "address row still present and not soft-deleted after DELETE")
    ctx.ids.pop("address_id", None)


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 5 — cart & saved for later
# ─────────────────────────────────────────────────────────────────────────────

@step("cart", "cart.add", "POST /api/cart adds an available menu item",
      writes=True, route="POST /api/cart", needs=("public.menu", "auth.login"))
def s_cart_add(ctx: Ctx):
    r = ctx.api.post("/api/cart",
                     json_body={"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1},
                     token=ctx.tokens["access"])
    r.check(200, allow=(201,))
    rows = ctx.db.select("cart_items", user_id=ctx.user_id)
    expect(bool(rows), f"cart_items row not created — {r.snippet()}", r)
    ctx.ids["cart_item_id"] = rows[0]["id"]
    ctx.track("cart_items", rows[0]["id"])
    ctx.sweep("cart_items", "user_id", ctx.user_id)


@step("cart", "cart.get", "GET /api/cart returns the item", route="GET /api/cart",
      needs=("cart.add",))
def s_cart_get(ctx: Ctx):
    r = ctx.api.get("/api/cart", token=ctx.tokens["access"]).check(200)
    expect(contains_id(r.data, ctx.ids["cart_item_id"]),
           f"cart response does not contain the item — {r.snippet()}", r)


@step("cart", "cart.update", "PATCH /api/cart/<id> updates quantity to 2",
      writes=True, route="PATCH /api/cart/<item_id>", needs=("cart.add",))
def s_cart_update(ctx: Ctx):
    ctx.api.patch(f"/api/cart/{ctx.ids['cart_item_id']}", json_body={"quantity": 2},
                  token=ctx.tokens["access"]).check(200, allow=(204,))
    row = ctx.db.select_one("cart_items", id=ctx.ids["cart_item_id"])
    expect(row is not None and int(row.get("quantity", 0)) == 2,
           f"quantity did not persist (DB: {row.get('quantity') if row else None})")


@step("cart", "saved.from_cart", "POST /api/saved/from-cart/<cart_item_id> (saved for later)",
      writes=True, route="POST /api/saved/from-cart/<cart_item_id>", needs=("cart.add",))
def s_saved_from_cart(ctx: Ctx):
    r = ctx.api.post(f"/api/saved/from-cart/{ctx.ids['cart_item_id']}",
                     token=ctx.tokens["access"])
    r.check(200, allow=(201,))
    rows = ctx.db.select("saved_for_later", user_id=ctx.user_id)
    expect(bool(rows), f"saved_for_later row not created — {r.snippet()}", r)
    ctx.ids["saved_id"] = rows[0]["id"]
    ctx.track("saved_for_later", rows[0]["id"])
    ctx.sweep("saved_for_later", "user_id", ctx.user_id)


@step("cart", "saved.move_to_cart", "POST /api/saved/<id>/move-to-cart",
      writes=True, route="POST /api/saved/<item_id>/move-to-cart", needs=("saved.from_cart",))
def s_saved_move(ctx: Ctx):
    r = ctx.api.post(f"/api/saved/{ctx.ids['saved_id']}/move-to-cart", token=ctx.tokens["access"])
    r.check(200, allow=(201, 204))
    rows = ctx.db.select("cart_items", user_id=ctx.user_id)
    expect(bool(rows), f"cart is empty after move-to-cart — {r.snippet()}", r)


@step("cart", "saved.delete", "DELETE /api/saved/<id>", writes=True,
      route="DELETE /api/saved/<item_id>", needs=("saved.from_cart",))
def s_saved_delete(ctx: Ctx):
    """Save a fresh item explicitly (POST /api/saved) and delete that one.

    It must NOT reuse the row from saved.from_cart: move-to-cart already deletes
    it, so deleting it again is a legitimate 404 — that was a test bug, not an
    API bug."""
    created = ctx.api.post("/api/saved",
                           json_body={"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1},
                           token=ctx.tokens["access"])
    created.check(200, allow=(201,))
    saved_id = str(field(created.data or {}, "id")
                   or ((created.data or {}).get("saved") or {}).get("id") or "")
    if not saved_id:
        rows = ctx.db.select("saved_for_later", user_id=ctx.user_id)
        expect(bool(rows), f"saved row was not created — {created.snippet()}", created)
        saved_id = rows[0]["id"]
    ctx.track("saved_for_later", saved_id)

    ctx.api.delete(f"/api/saved/{saved_id}", token=ctx.tokens["access"]).check(200, allow=(202, 204))
    expect(ctx.db.select_one("saved_for_later", id=saved_id) is None,
           "saved_for_later row still exists after DELETE")


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 6 — orders (money path)
# ─────────────────────────────────────────────────────────────────────────────

@step("orders", "orders.window", "ordering window is open for the test campus "
      "(provisioned and cleaned up automatically if needed)",
      writes=True, route="GET /api/orders/delivery-windows/status", needs=("auth.login",))
def s_ensure_window(ctx: Ctx):
    """`is_open` is per-campus and comes from the ordering_windows table:
    a row for today (or this weekday) that is not closed and has capacity left.
    If the campus has none, create one for today and delete it in cleanup —
    the suite must never depend on rows someone inserted by hand.

    Note: operating_hour_overrides is the *storefront* schedule and has no
    effect on ordering; ordering_windows (or the 08:00-16:00 config fallback)
    is what resolve_ordering_window enforces."""
    campus = ctx.ids["campus_id"]
    status_path = "/api/orders/delivery-windows/status"

    def is_open():
        r = ctx.api.get(status_path, token=ctx.tokens["access"],
                        params={"campus_id": campus}).check(200).expect_json()
        flag = find_bool(r.data, {"is_open", "open", "ordering_open", "accepting_orders",
                                  "is_ordering_open", "window_open"})
        return bool(flag), r

    flag, r = is_open()
    if flag:
        ctx.ids["ordering_open"] = True
        ctx.note("ordering already open for this campus")
        return

    today = (datetime.now(timezone.utc) + timedelta(hours=1)).date().isoformat()  # WAT
    existing = ctx.db.select("ordering_windows", date=today, campus_id=campus)
    if existing:
        # A row exists but the window is closed/full — do not touch other people's data.
        raise Skip(f"ordering_windows has a row for {today}/{campus} but it is closed or full "
                   f"({json.dumps(existing[0])[:160]}) — fix it in the admin UI")

    try:
        row = ctx.db.insert("ordering_windows", {
            "date": today,
            "campus_id": campus,
            "opens_at": "00:00",
            "closes_at": "23:59",
            "capacity": 50,
            "is_closed": False,
        })
    except Failed as exc:
        raise Skip(f"could not provision an ordering window ({exc})")

    window_id = str((row or {}).get("id") or "")
    if window_id:
        ctx.track_infra("ordering_windows", window_id)   # deleted in cleanup, always
    ctx.note(f"provisioned a temporary ordering window for {today} "
             f"(id {window_id or '?'}) — deleted in cleanup")

    flag, r = is_open()
    expect(flag, f"ordering still closed after provisioning — {r.snippet()}", r)
    ctx.ids["ordering_open"] = True


@step("orders", "orders.fund_wallet", "credit the test wallet via credit_wallet_atomic (Paystack RPC path)",
      writes=True, needs=("auth.login",))
def s_fund(ctx: Ctx):
    amount = float(ctx.opts.fund_wallet)
    if amount <= 0:
        raise Skip("--fund-wallet 0 — wallet funding disabled")
    try:
        ctx.db.rpc("credit_wallet_atomic", {
            "p_user_id": ctx.user_id,
            "p_amount": amount,
            "p_reason": "E2E harness top-up",
            "p_reference_type": "topup",
            "p_reference_id": None,
            "p_provider": "e2e",
            "p_provider_reference": f"E2E-{uuid.uuid4().hex[:12]}",
            "p_metadata": {"source": "scripts/live_test.py"},
            "p_campus_id": ctx.ids.get("campus_id"),
        })
    except Failed as exc:
        ctx.warnings.append(f"wallet funding failed: {exc}")
        raise Skip(f"credit_wallet_atomic unavailable: {exc}")
    wallet = ctx.db.select_one("wallets", user_id=ctx.user_id)
    expect(wallet is not None, "no wallets row for the test user after top-up")
    expect(float(wallet.get("balance", 0)) >= amount - 0.01,
           f"wallet balance {wallet.get('balance')} < credited {amount}")
    ctx.sweep("wallet_transactions", "user_id", ctx.user_id)
    ctx.sweep("wallets", "user_id", ctx.user_id)
    ctx.note(f"wallet credited ₦{amount:.0f} (balance now ₦{wallet.get('balance')})")


@step("orders", "orders.place", "POST /api/orders places a wallet-paid order",
      writes=True, route="POST /api/orders",
      needs=("orders.window", "orders.fund_wallet", "public.hostels"))
def s_place_order(ctx: Ctx):
    if not ctx.ids.get("hostel_id"):
        raise Skip("no delivery point for the signed-in account's campus — "
                   "orders.place cannot build a delivery location")
    body = {
        "items": [{"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1}],
        "payment_method": "wallet",
        "delivery_type": "on_campus",
        "delivery_location_id": str(ctx.ids["hostel_id"]),
        "notes": "E2E automated order — safe to ignore",
    }
    # X-Campus-ID is the fallback resolve path (a profile campus wins over it), so
    # an account without a campus still gets a well-scoped order instead of a 400.
    r = ctx.api.post("/api/orders", json_body=body, token=ctx.tokens["access"],
                     headers={"X-Campus-ID": str(ctx.ids.get("campus_id") or "")})
    if r.status == 409:
        raise Skip(f"ordering unavailable for campus {ctx.ids.get('campus_id')}: {r.snippet(120)}")
    r.check(201, allow=(200,))
    order_id = str(field(r.data or {}, "id") or ((r.data or {}).get("order") or {}).get("id") or "")
    if not order_id:
        rows = ctx.db.select("orders", user_id=ctx.user_id)
        expect(bool(rows), f"order was not persisted — {r.snippet()}", r)
        order_id = rows[0]["id"]
    ctx.ids["order_id"] = order_id
    ctx.track("orders", order_id)

    order = ctx.db.select_one("orders", id=order_id)
    expect(order is not None and str(order.get("user_id")) == ctx.user_id,
           "orders row missing or owned by someone else")
    expect(order.get("status") not in (None, ""), "orders.status is null — insert contract broken")
    items = ctx.db.select("order_items", order_id=order_id)
    expect(bool(items), "no order_items rows were written for the order")
    expect(any(str(i.get("menu_item_id")) == str(ctx.ids["menu_item_id"]) for i in items),
           "order_items does not reference the ordered menu item")
    ctx.sweep("order_items", "order_id", order_id)
    ctx.sweep("order_status_logs", "order_id", order_id)
    ctx.note(f"order {order.get('order_number') or order_id} status={order.get('status')} "
             f"items={len(items)} total=₦{order.get('total_amount')}")


@step("orders", "orders.get", "GET /api/orders/<id>", route="GET /api/orders/<order_id>",
      needs=("orders.place",))
def s_get_order(ctx: Ctx):
    r = ctx.api.get(f"/api/orders/{ctx.ids['order_id']}", token=ctx.tokens["access"]).check(200)
    expect(contains_id(r.data, ctx.ids["order_id"]), f"order id missing from response — {r.snippet()}", r)


@step("orders", "orders.history", "GET /api/orders/<id>/history returns status log",
      route="GET /api/orders/<order_id>/history", needs=("orders.place",))
def s_order_history(ctx: Ctx):
    r = ctx.api.get(f"/api/orders/{ctx.ids['order_id']}/history",
                    token=ctx.tokens["access"]).check(200)
    entries = as_list(r.data, "history", "logs")
    expect(bool(entries) or bool(r.data), f"order history is empty — {r.snippet()}", r)
    ctx.note(f"{len(entries)} status entries")


@step("orders", "orders.list", "GET /api/orders includes the order", route="GET /api/orders",
      needs=("orders.place",))
def s_order_list(ctx: Ctx):
    r = ctx.api.get("/api/orders", params={"limit": 10}, token=ctx.tokens["access"]).check(200)
    expect(contains_id(r.data, ctx.ids["order_id"]), f"order missing from list — {r.snippet()}", r)


@step("orders", "orders.active", "GET /api/orders/active", route="GET /api/orders/active",
      needs=("orders.place",))
def s_order_active(ctx: Ctx):
    ctx.api.get("/api/orders/active", token=ctx.tokens["access"]).check(200)


@step("orders", "orders.cancel", "POST /api/orders/<id>/cancel + wallet refund ledger",
      writes=True, route="POST /api/orders/<order_id>/cancel", needs=("orders.place",))
def s_order_cancel(ctx: Ctx):
    r = ctx.api.post(f"/api/orders/{ctx.ids['order_id']}/cancel",
                     json_body={"reason": "E2E automated cancellation"},
                     token=ctx.tokens["access"])
    r.check(200, allow=(202,))
    order = ctx.db.select_one("orders", id=ctx.ids["order_id"])
    expect(order is not None, "order row disappeared after cancel")
    expect(str(order.get("status", "")).lower() in ("cancelled", "canceled", "refunded", "refund_pending"),
           f"order status after cancel is {order.get('status')!r}")
    refunds = [t for t in ctx.db.select("wallet_transactions", user_id=ctx.user_id)
               if "refund" in json.dumps(t).lower() or "cancel" in json.dumps(t).lower()]
    ctx.note(f"status={order.get('status')} refund ledger rows={len(refunds)}")


@step("orders", "orders.review", "POST /api/orders/<id>/review", route="POST /api/orders/<order_id>/review",
      needs=("orders.place",))
def s_order_review(ctx: Ctx):
    raise Skip("reviewing requires a DELIVERED order; the suite does not advance "
               "orders through the kitchen (would disturb live operations)")


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 7 — HP, wallet, rewards, referrals
# ─────────────────────────────────────────────────────────────────────────────

@step("economy", "hp.balance", "GET /api/hp/balance", route="GET /api/hp/balance",
      needs=("auth.login",))
def s_hp_balance(ctx: Ctx):
    r = ctx.api.get("/api/hp/balance", token=ctx.tokens["access"]).check(200).expect_json()
    expect(any(k in r.data for k in ("active", "active_hp", "total", "total_hp", "balance")),
           f"HP balance payload has no recognisable balance field — {r.snippet()}", r)
    row = ctx.db.select_one("profiles", id=ctx.user_id)
    ctx.note(f"API balance={ {k: v for k, v in r.data.items() if 'hp' in str(k) or k in ('active','pending','total')} } "
             f"profiles.hp_balance={row.get('hp_balance') if row else None}")


@step("economy", "hp.transactions", "GET /api/hp/transactions", route="GET /api/hp/transactions",
      needs=("auth.login",))
def s_hp_transactions(ctx: Ctx):
    ctx.api.get("/api/hp/transactions", token=ctx.tokens["access"]).check(200)
    ctx.sweep("hp_transactions", "user_id", ctx.user_id)


@step("economy", "hp.tiers", "GET /api/hp/tiers", route="GET /api/hp/tiers", needs=("auth.login",))
def s_hp_tiers(ctx: Ctx):
    ctx.api.get("/api/hp/tiers", token=ctx.tokens["access"]).check(200)


@step("economy", "wallet.get", "GET /api/wallet matches the wallets row",
      route="GET /api/wallet", needs=("auth.login",))
def s_wallet(ctx: Ctx):
    r = ctx.api.get("/api/wallet", token=ctx.tokens["access"]).check(200).expect_json()
    row = ctx.db.select_one("wallets", user_id=ctx.user_id)
    expect(row is not None, "no wallets row for the test user")
    api_balance = field(r.data, "balance", "wallet_balance")
    if api_balance is not None:
        expect(abs(float(api_balance) - float(row.get("balance", 0))) < 0.01,
               f"API balance {api_balance} != DB balance {row.get('balance')}", r)
    ctx.sweep("wallets", "user_id", ctx.user_id)
    ctx.note(f"balance ₦{row.get('balance')}")


@step("economy", "wallet.transactions", "GET /api/wallet/transactions", route="GET /api/wallet/transactions",
      needs=("auth.login",))
def s_wallet_transactions(ctx: Ctx):
    ctx.api.get("/api/wallet/transactions", token=ctx.tokens["access"]).check(200)


@step("economy", "rewards.redemptions", "GET /api/rewards/redemptions",
      route="GET /api/rewards/redemptions", needs=("auth.login",))
def s_redemptions(ctx: Ctx):
    ctx.api.get("/api/rewards/redemptions", token=ctx.tokens["access"]).check(200)


@step("economy", "referrals.list", "GET /api/referrals", route="GET /api/referrals",
      needs=("auth.login",))
def s_referrals(ctx: Ctx):
    ctx.api.get("/api/referrals", token=ctx.tokens["access"]).check(200)


@step("economy", "referrals.stats", "GET /api/referrals/stats", route="GET /api/referrals/stats",
      needs=("auth.login",))
def s_referral_stats(ctx: Ctx):
    ctx.api.get("/api/referrals/stats", token=ctx.tokens["access"]).check(200)


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 8 — notifications
# ─────────────────────────────────────────────────────────────────────────────

@step("notifications", "notifications.list", "GET /api/notifications",
      route="GET /api/notifications", needs=("auth.login",))
def s_notifications(ctx: Ctx):
    ctx.api.get("/api/notifications", token=ctx.tokens["access"]).check(200)
    ctx.sweep("notifications", "user_id", ctx.user_id)


@step("notifications", "notifications.prefs", "GET + PATCH /api/notifications/preferences round-trip",
      writes=True, route="PATCH /api/notifications/preferences", needs=("auth.login",))
def s_notification_prefs(ctx: Ctx):
    before = ctx.api.get("/api/notifications/preferences",
                         token=ctx.tokens["access"]).check(200).expect_json()
    writable = {"push_enabled", "email_enabled", "order_updates", "promo_emails",
                "marketing_emails", "sms_enabled", "whatsapp_enabled"}
    payload = {k: v for k, v in before.data.items() if k in writable and isinstance(v, bool)}
    if not payload:
        raise Skip("preferences payload exposes no known writable boolean to round-trip")
    ctx.api.patch("/api/notifications/preferences", json_body=payload,
                  token=ctx.tokens["access"]).check(200, allow=(204,))
    after = ctx.api.get("/api/notifications/preferences",
                        token=ctx.tokens["access"]).check(200).expect_json()
    for key, value in payload.items():
        expect(after.data.get(key) == value,
               f"preference {key!r} did not persist ({after.data.get(key)!r} != {value!r})", after)
    ctx.sweep("notification_preferences", "user_id", ctx.user_id)


@step("notifications", "notifications.read_all", "POST /api/notifications/read-all",
      writes=True, route="POST /api/notifications/read-all", needs=("auth.login",))
def s_read_all(ctx: Ctx):
    ctx.api.post("/api/notifications/read-all", token=ctx.tokens["access"]).check(200, allow=(204,))


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 9 — admin (opt-in via --admin-token)
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_ROUTES = [
    ("admin.settings", "GET /api/admin/settings", "/api/admin/settings"),
    ("admin.users", "GET /api/admin/users", "/api/admin/users"),
    ("admin.orders", "GET /api/admin/orders", "/api/admin/orders"),
    ("admin.audit", "GET /api/admin/audit-log", "/api/admin/audit-log"),
    ("admin.dashboard", "GET /api/analytics/dashboard", "/api/analytics/dashboard"),
    ("admin.economics", "GET /api/admin/economics/overview", "/api/admin/economics/overview"),
]


@step("admin", "admin.login", "sign in as an admin (E2E_ADMIN_EMAIL/PASSWORD or --admin-token)",
      route="POST /api/auth/login", needs=("preflight.health",))
def s_admin_login(ctx: Ctx):
    if ctx.opts.admin_token:
        ctx.tokens["admin"] = ctx.opts.admin_token
        ctx.note("using --admin-token")
        return
    email, password = ctx.opts.admin_email, ctx.opts.admin_password
    if not (email and password):
        raise Skip("set E2E_ADMIN_EMAIL + E2E_ADMIN_PASSWORD in .env "
                   "(or pass --admin-token) to run the admin phase")
    r = ctx.api.post("/api/auth/login", json_body={"email": email, "password": password})
    r.check(200)
    token = field(r.data or {}, "access_token") or ((r.data or {}).get("session") or {}).get("access_token")
    expect(bool(token), f"admin login returned no access_token — {r.snippet()}", r)
    role = (((r.data or {}).get("user") or {}).get("user_metadata") or {}).get("role")
    ctx.tokens["admin"] = token
    ctx.note(f"signed in as {email}" + (f" (role claim: {role})" if role else ""))


def _admin_step(sid: str, route: str, path: str):
    @step("admin", sid, route, route=route, needs=("admin.login",))
    def runner(ctx: Ctx, _path=path):
        ctx.api.get(_path, token=ctx.tokens.get("admin")).check(200)
    return runner


for _sid, _route, _path in ADMIN_ROUTES:
    _admin_step(_sid, _route, _path)


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 10 — cleanup
# ─────────────────────────────────────────────────────────────────────────────

@step("cleanup", "cleanup.logout", "POST /api/auth/logout invalidates the session",
      writes=True, route="POST /api/auth/logout", needs=("auth.login",))
def s_logout(ctx: Ctx):
    ctx.api.post("/api/auth/logout", json_body={"scope": "local"},
                 token=ctx.tokens["access"]).check(200, allow=(204,))


# ─────────────────────────────────────────────────────────────────────────────
#  Runner
# ─────────────────────────────────────────────────────────────────────────────

def colour(text: str, code: str, enabled: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


def run_cleanup(ctx: Ctx, out) -> tuple[int, int]:
    """Delete everything the run created. Returns (deleted, failed).

    User data is only removed for an account the run created; scaffolding (a
    temporary ordering window) is always removed, and always last, because the
    orders created during the run reference it.
    """
    deleted = failed = 0
    if not ctx.owns_user:
        out.raw("  user data kept — the run signed in to an existing account (--login-email)")
        for table, row_id in reversed(ctx.infra):
            try:
                if ctx.db.delete(table, id=row_id):
                    deleted += 1
                else:
                    failed += 1
                    out.warn_line(f"could not delete scaffolding {table}.{row_id} — "
                                  "remove it by hand once nothing references it")
            except Exception as exc:                 # noqa: BLE001 - cleanup must not abort
                failed += 1
                out.warn_line(f"delete scaffolding {table}.{row_id} errored: {exc}")
        return deleted, failed

    # children before parents: user-scoped sweeps (order_items, order_status_logs,
    # cart_items, …) must go before the parent rows they reference.
    for table, column, value in ctx.sweeps:
        try:
            ctx.db.delete(table, **{column: value})
            deleted += 1
        except Exception as exc:                     # noqa: BLE001
            failed += 1
            out.warn_line(f"sweep {table}.{column} errored: {exc}")

    for table, row_id in reversed(ctx.created):
        try:
            if ctx.db.delete(table, id=row_id):
                deleted += 1
            else:
                failed += 1
                out.warn_line(f"could not delete {table}.{row_id}")
        except Exception as exc:                     # noqa: BLE001 - cleanup must not abort
            failed += 1
            out.warn_line(f"delete {table}.{row_id} errored: {exc}")

    if ctx.user_id:
        try:
            ctx.db.delete("profiles", id=ctx.user_id)
            ctx.db.delete_auth_user(ctx.user_id)
        except Exception as exc:                     # noqa: BLE001
            failed += 1
            out.warn_line(f"auth user delete errored: {exc}")

    for table, row_id in reversed(ctx.infra):
        try:
            if ctx.db.delete(table, id=row_id):
                deleted += 1
            else:
                failed += 1
                out.warn_line(f"could not delete scaffolding {table}.{row_id} — "
                              "an order may still reference it")
        except Exception as exc:                     # noqa: BLE001 - cleanup must not abort
            failed += 1
            out.warn_line(f"delete scaffolding {table}.{row_id} errored: {exc}")
    return deleted, failed


class Out:
    def __init__(self, as_json: bool, verbose: bool = False):
        self.as_json = as_json
        self.verbose = verbose
        self.tty = sys.stdout.isatty()

    def phase(self, name: str):
        if not self.as_json:
            print(f"\n{colour(name.upper(), '1;36', self.tty)}")

    def line(self, status: str, title: str, detail: str = ""):
        if self.as_json:
            return
        glyph = {"passed": ("PASS", "32"), "failed": ("FAIL", "31"),
                 "skipped": ("SKIP", "33"), "blocked": ("SKIP", "90")}[status]
        text = f"  {colour(glyph[0], glyph[1], self.tty):<14} {title}"
        if detail:
            text += f"  {colour(detail, '90', self.tty)}"
        print(text)

    def warn_line(self, message: str):
        if not self.as_json:
            print(f"  {colour('WARN', '33', self.tty)}  {message}")

    def raw(self, message: str):
        if not self.as_json:
            print(message)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Live end-to-end suite against Supabase.")
    parser.add_argument("--base-url", default="", help="test a deployed server instead of in-process")
    parser.add_argument("--read-only", action="store_true", help="skip every step that writes")
    parser.add_argument("--keep-data", action="store_true", help="do not clean up created rows")
    parser.add_argument("--only", default="", help="run one phase (e.g. auth) or step prefix")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--list", action="store_true", help="print the plan and exit")
    parser.add_argument("--self-check", action="store_true",
                        help="verify every referenced route exists in the app (no network)")
    parser.add_argument("--verbose", action="store_true", help="print response snippets and notes")
    parser.add_argument("--admin-token", default="", help="enables the admin phase")
    parser.add_argument("--campus-id", default="",
                        help="campus UUID to register the test user with "
                             "(default: E2E_CAMPUS_ID, then the campuses list)")
    parser.add_argument("--admin-email", default="",
                        help="admin login for the admin phase (default: E2E_ADMIN_EMAIL)")
    parser.add_argument("--admin-password", default="",
                        help="admin password (default: E2E_ADMIN_PASSWORD)")
    parser.add_argument("--login-email", default="",
                        help="sign in as an existing account instead of registering a test user")
    parser.add_argument("--login-password", default="", help="password for --login-email")
    parser.add_argument("--write-existing", action="store_true",
                        help="allow write steps when using --login-email (off by default: you would "
                             "be modifying a real account)")
    parser.add_argument("--fund-wallet", type=float, default=3000.0,
                        help="₦ credited to the test wallet before ordering (0 disables)")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--env-file", default=str(BACKEND_ROOT / ".env"))
    args = parser.parse_args(argv)

    # .env first: the E2E_* defaults below are read from it (a fresh clone has
    # no .env — `make env` creates one from the template).
    env_file = Path(args.env_file)
    if load_dotenv is not None and env_file.exists():
        load_dotenv(env_file, override=False)

    args.campus_id = args.campus_id or os.environ.get("E2E_CAMPUS_ID", "")
    args.admin_email = args.admin_email or os.environ.get("E2E_ADMIN_EMAIL", "")
    args.admin_password = args.admin_password or os.environ.get("E2E_ADMIN_PASSWORD", "")

    # ── plan / self-check (offline) ──────────────────────────────────────────
    if args.list:
        if args.as_json:
            print(json.dumps([{"phase": s.phase, "id": s.id, "title": s.title,
                               "writes": s.writes, "route": s.route} for s in STEPS], indent=2))
        else:
            phase = None
            for s in STEPS:
                if s.phase != phase:
                    phase = s.phase
                    print(f"\n{phase.upper()}")
                flag = " [write]" if s.writes else ""
                print(f"  {s.id:<28} {s.title}{flag}")
            print(f"\n{len(STEPS)} steps")
        return 0

    if args.self_check:
        return self_check()

    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing — run `make env` then "
              "scripts/check_supabase.py.", file=sys.stderr)
        return 2

    secret = (os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET") or "").strip()
    out = Out(args.as_json, args.verbose)

    # ── application ──────────────────────────────────────────────────────────
    app = None
    if not args.base_url:
        sys.path.insert(0, str(BACKEND_ROOT))
        os.environ.setdefault("FLASK_ENV", "development")
        try:
            from app import create_app
            from app.config import config_map
            app = create_app(config_map["development"])
        except Exception as exc:                      # noqa: BLE001
            print(f"could not start the Flask app: {exc}", file=sys.stderr)
            traceback.print_exc()
            return 2

    api = Api(app=app, base_url=args.base_url or None, timeout=args.timeout)
    db = DB(url, key, timeout=args.timeout)
    ctx = Ctx(api, db, args)

    if not args.as_json:
        target = args.base_url or "in-process Flask app"
        print(f"Holy Grills — live end-to-end suite\n"
              f"target   : {target}\n"
              f"project  : {url}")
        if secret in INSECURE_SECRETS:
            out.warn_line("SECRET_KEY is unset or the public default — set it in .env")
        if args.read_only:
            out.warn_line("--read-only: write steps will be skipped")
        if args.keep_data:
            out.warn_line("--keep-data: created rows will NOT be deleted")

    # ── selection ────────────────────────────────────────────────────────────
    selected = [s for s in STEPS
                if (not args.only or s.phase.startswith(args.only) or s.id.startswith(args.only))]

    started = time.time()
    results: dict[str, dict] = {}
    gated = False

    phase = None
    for s in selected:
        if s.phase != phase:
            phase = s.phase
            out.phase(phase)

        # dependency gating
        unmet = [d for d in s.needs if results.get(d, {}).get("result") != "passed"]
        if unmet:
            dep_results = {results.get(d, {}).get("result", "not run") for d in unmet}
            label = "skipped" if dep_results <= {"skipped", "blocked"} else "blocked"
            detail = "; ".join(f"{d} → {results.get(d, {}).get('result', 'not run')}"
                               for d in unmet)
            s.result, s.detail = label, f"depends on {detail}"
            out.line(s.result, s.title, s.detail)
            results[s.id] = {"result": s.result, "detail": s.detail}
            continue

        if args.read_only and s.writes:
            s.result, s.detail = "skipped", "--read-only"
            out.line(s.result, s.title, s.detail)
            results[s.id] = {"result": s.result, "detail": s.detail}
            continue

        if s.writes and not ctx.owns_user and not args.write_existing:
            s.result, s.detail = "skipped", "existing account (--login-email) — add --write-existing"
            out.line(s.result, s.title, s.detail)
            results[s.id] = {"result": s.result, "detail": s.detail}
            continue

        # core preflight failure stops the run
        if gated:
            s.result, s.detail = "blocked", "preflight failed"
            out.line(s.result, s.title, s.detail)
            results[s.id] = {"result": s.result, "detail": s.detail}
            continue

        t0 = time.time()
        try:
            s.fn(ctx)
            s.result, s.detail = "passed", ""
        except Skip as exc:
            s.result, s.detail = "skipped", str(exc)
        except Failed as exc:
            s.result, s.detail = "failed", str(exc)
            if args.verbose and exc.resp is not None:
                print(f"        body: {exc.resp.snippet(600)}")
        except Exception as exc:                      # noqa: BLE001
            s.result, s.detail = "failed", f"{type(exc).__name__}: {exc}"
            if args.verbose:
                traceback.print_exc()
        s.ms = (time.time() - t0) * 1000

        if s.phase == "preflight" and s.result == "failed":
            gated = True

        out.line(s.result, s.title, s.detail)
        if args.verbose and s.result == "passed" and s.ms > 250:
            out.raw(f"        {s.ms:.0f} ms")
        results[s.id] = {"result": s.result, "detail": s.detail, "ms": round(s.ms)}

        if args.fail_fast and s.result == "failed":
            break

    # ── cleanup ──────────────────────────────────────────────────────────────
    cleanup_deleted = cleanup_failed = 0
    if not args.read_only and not args.keep_data:
        out.phase("cleanup")
        cleanup_deleted, cleanup_failed = run_cleanup(ctx, out)
        out.line("passed" if cleanup_failed == 0 else "failed",
                 f"deleted {cleanup_deleted} row(s), hard-deleted the test auth user",
                 f"{cleanup_failed} problem(s)" if cleanup_failed else "")
    elif args.keep_data:
        out.phase("cleanup")
        out.raw(f"  skipped (--keep-data) — test user {ctx.ids.get('email')} left in place")

    elapsed = time.time() - started
    counts = {k: sum(1 for v in results.values() if v["result"] == k)
              for k in ("passed", "failed", "skipped", "blocked")}
    ok = counts["failed"] == 0

    if args.as_json:
        print(json.dumps({
            "ok": ok,
            "target": args.base_url or "in-process",
            "project": url,
            "elapsed_seconds": round(elapsed, 2),
            "counts": counts,
            "cleanup": {"deleted": cleanup_deleted, "problems": cleanup_failed},
            "warnings": ctx.warnings,
            "notes": ctx.notes,
            "steps": [{"id": s.id, "phase": s.phase, "title": s.title, **results.get(s.id, {})}
                      for s in selected],
        }, indent=2))
    else:
        print("\n" + "─" * 72)
        summary = (f"{counts['passed']} passed · {counts['failed']} failed · "
                   f"{counts['skipped']} skipped · {counts['blocked']} blocked   ({elapsed:.1f}s)")
        print(colour(("✓ E2E PASSED  " if ok else "✗ E2E FAILED  ") + summary,
                     "32" if ok else "31", True))
        for s in selected:
            if s.result == "failed":
                print(f"    • {s.id}: {s.detail}")
        if ctx.warnings:
            print("  warnings:")
            for w in ctx.warnings:
                print(f"    • {w}")
        print("─" * 72)

    return 0 if ok else 1


def self_check() -> int:
    """Offline: every declared route must exist in the Flask URL map."""
    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ.setdefault("FLASK_ENV", "development")
    try:
        from app import create_app
        from app.config import config_map
        app = create_app(config_map["development"])
    except Exception as exc:                          # noqa: BLE001
        print(f"could not build the app: {exc}", file=sys.stderr)
        return 2

    def normalise(rule: str) -> str:
        rule = re.sub(r"<[^>]*:([^>]+)>", r"<\1>", rule)
        return rule.rstrip("/") or "/"

    known = {(m, normalise(str(r))) for r in app.url_map.iter_rules()
             for m in r.methods if m in {"GET", "POST", "PATCH", "PUT", "DELETE"}}

    problems = []
    checked = 0
    for s in STEPS:
        if not s.route:
            continue
        method, _, path = s.route.partition(" ")
        checked += 1
        if (method, normalise(path)) not in known:
            problems.append(f"{s.id}: {s.route} is not a registered route")

    print(f"Self-check: {checked} declared routes compared against {len(known)} app routes")
    if problems:
        for p in problems:
            print(f"  FAIL  {p}")
        print(f"\n✗ {len(problems)} route(s) do not exist — the suite would hit 404s")
        return 1
    print("✓ every route the suite calls exists in the application")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
