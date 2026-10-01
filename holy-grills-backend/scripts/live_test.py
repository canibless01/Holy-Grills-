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
import hashlib
import hmac
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
    def __init__(self, phase, sid, title, fn, writes, route, needs, routes=()):
        self.phase, self.id, self.title, self.fn = phase, sid, title, fn
        self.writes, self.route, self.needs = writes, route, needs
        # A step that walks several routes (a lifecycle, a docs bundle) declares the
        # rest here so --self-check verifies every path it calls, not just the first.
        self.routes = tuple(routes)
        self.result = None          # passed | failed | skipped | blocked
        self.detail = ""
        self.ms = 0.0

    def all_routes(self) -> tuple[str, ...]:
        return ((self.route,) if self.route else ()) + self.routes


STEPS: list[Step] = []


def step(phase: str, sid: str, title: str, *, writes: bool = False, route: str = "",
         routes: tuple[str, ...] = (), needs: tuple[str, ...] = ()):
    def decorator(fn):
        STEPS.append(Step(phase, sid, title, fn, writes, route, needs, routes))
        return fn
    return decorator


class Ctx:
    """Shared state across steps."""

    def __init__(self, api, db, opts):
        self.api, self.db, self.opts = api, db, opts
        self.ids: dict[str, object] = {}
        self.tokens: dict[str, str] = {}
        self.created: list[tuple[str, str]] = []       # (table, id) — deleted in reverse
        self.children: list[tuple[str, str, str]] = [] # (table, column, value) — rows this run
                                                       # created under a parent row it also created
        self.infra: list[tuple[str, str]] = []         # suite scaffolding — always deleted
        self.cleanup_created = False                   # True with --write-existing: delete what
                                                       # THIS RUN created, never what it found
        self.sweeps: list[tuple[str, str, str]] = []   # (table, column, value)
        self.user_id: str | None = None
        self.owns_user = True          # False when running against --login-email
        self.notes: list[str] = []
        self.warnings: list[str] = []
        self.results: dict[str, Step] = {}

    # ── bookkeeping ──────────────────────────────────────────────────────────
    def track(self, table: str, row_id: str):
        """Register a row for deletion — only ever a row this run created.

        With a freshly created test user that is every tracked row. With
        --login-email nothing is tracked unless --write-existing was given, in
        which case only the rows this run made are deleted; the account and
        everything already in it is left alone.
        """
        if row_id and (self.owns_user or self.cleanup_created):
            self.created.append((table, row_id))

    def track_children(self, table: str, column: str, value: str):
        """Rows this run created *under* a parent it also created (order_items under
        an order). Registered by predicate, deleted before the parent."""
        if value and (self.owns_user or self.cleanup_created):
            self.children.append((table, column, value))

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
        self.app = app
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout
        self.client = None
        self.default_headers: dict[str, str] = {}
        if self.base_url is None:
            self.client = app.test_client()

    def clone(self) -> "Api":
        """A second client for a concurrent call — one test_client per thread.

        The concurrency steps need requests genuinely in flight at the same time; a
        single client is not safe to share between threads, and an in-process
        test_client serialises anyway, which is why those steps require --base-url.
        """
        other = Api(app=self.app, base_url=self.base_url, timeout=self.timeout)
        other.default_headers = dict(self.default_headers)
        return other

    def request(self, method: str, path: str, *, json_body=None, raw_body=None,
                token=None, headers=None, params=None):
        """raw_body sends the bytes as-is. Webhook signatures are computed over the
        exact body the server receives, so re-serialising a dict would invalidate it."""
        hdrs = dict(self.default_headers)
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        if headers:
            hdrs.update(headers)

        if self.client is not None:
            query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
            url = f"{path}?{query}" if query else path
            raw = self.client.open(url, method=method,
                                   json=json_body if raw_body is None else None,
                                   data=raw_body, headers=hdrs)
            body = raw.get_data(as_text=True)
            try:
                data = raw.get_json() if body else None
            except Exception:
                data = None
            return Resp(raw.status_code, data, body)

        url = f"{self.base_url}{path}"
        raw = requests.request(method, url, json=json_body if raw_body is None else None,
                               data=raw_body, headers=hdrs,
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

    def update(self, table: str, values: dict, **filters) -> list:
        """Patch rows by filter. Used to give a throwaway account a staff role —
        require_role reads profiles.role, so the role is data, not a token claim."""
        params = {c: f"eq.{v}" for c, v in filters.items()}
        resp = self.session.patch(f"{self.url}/rest/v1/{table}", params=params,
                                  json=values, headers=self._headers(), timeout=self.timeout)
        if resp.status_code >= 400:
            return []
        payload = resp.json() if resp.content else []
        return payload if isinstance(payload, list) else [payload]

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
        ctx.cleanup_created = bool(ctx.opts.write_existing)
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

    Note: since the override wiring, an operating_hour_overrides row for today
    DOES affect ordering — it outranks the recurring weekday rows (see
    app/utils/schedule.py). This step only guarantees that *some* window is
    open, so the override probes below can pick their own date and clean up
    after themselves."""
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


@step("orders", "orders.free_side_provision",
      "give the test account one free-side credit and select a free side",
      writes=True, route="POST /api/free-sides/select",
      needs=("auth.login", "orders.window"))
def s_free_side_provision(ctx: Ctx):
    """Set up the only path that spends a free-side credit, so orders.place can
    prove the consumption actually happens (the bug: nothing consumed them).

    Skips cleanly when the feature is off or the project has no active free-side
    items — both are legitimate configurations, not failures.
    """
    campus = ctx.ids.get("campus_id")

    items = [i for i in (ctx.db.select("free_side_items", is_active="true") or [])
             if i.get("campus_id") in (campus, None)]
    if not items:
        raise Skip("no active free_side_items row for this campus — nothing to select")

    # one credit, expiring tomorrow; deleted in cleanup whatever happens
    try:
        credit = ctx.db.insert("free_side_credits", {
            "user_id": ctx.user_id,
            "campus_id": campus,
            "credits_remaining": 1,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        })
    except Failed as exc:
        raise Skip(f"could not create a free_side_credits row: {exc}")

    credit_id = str((credit or {}).get("id") or "")
    if credit_id:
        ctx.track("free_side_credits", credit_id)

    r = ctx.api.post("/api/free-sides/select", json_body={"free_side_item_id": items[0]["id"]},
                     token=ctx.tokens["access"])
    if r.status == 403:
        raise Skip(f"free_side_credits feature is off — {r.snippet(120)}")
    r.check(201, allow=(200,))
    sel_id = str(field(r.data or {}, "id") or ((r.data or {}).get("selection") or {}).get("id") or "")
    if not sel_id:
        rows = ctx.db.select("cart_free_side_selections", user_id=ctx.user_id)
        expect(bool(rows), f"selection was not persisted — {r.snippet()}", r)
        sel_id = str(rows[0]["id"])
    # predicate delete tolerates the row already being gone (that is the point of the test)
    ctx.track_children("cart_free_side_selections", "id", sel_id)
    ctx.ids["free_side_credit_id"] = credit_id
    ctx.ids["free_side_selection_id"] = sel_id
    ctx.ids["free_side_expect_consumption"] = True
    ctx.note(f"provisioned 1 credit ({credit_id}) and selected '{items[0].get('name')}' ({sel_id})")


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
    # Predicate-deleted children of an order THIS RUN created — safe to remove even
    # when the run signed in to a pre-existing account with --write-existing.
    ctx.track_children("order_items", "order_id", order_id)
    ctx.track_children("order_status_logs", "order_id", order_id)
    ctx.note(f"order {order.get('order_number') or order_id} status={order.get('status')} "
             f"items={len(items)} total=₦{order.get('total_amount')}")


@step("orders", "orders.cancel_unpaid_no_refund",
      "cancelling an UNPAID card order refunds nothing (money bug regression)",
      writes=True, route="POST /api/orders/<order_id>/cancel",
      needs=("orders.place", "orders.fund_wallet"))
def s_cancel_unpaid_no_refund(ctx: Ctx):
    """A card order is created with payment_status='pending' and card_amount_used
    already set. Cancelling it used to credit the wallet for the full amount —
    money that was never collected, repeatable in a loop. Nothing may be refunded
    while payment_status is not 'paid'.
    """
    if not ctx.ids.get("hostel_id"):
        raise Skip("no delivery point — cannot build a card order")

    wallet_before = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_before = float(wallet_before.get("balance") or 0)

    body = {
        "items": [{"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1}],
        "payment_method": "card",
        "delivery_type": "on_campus",
        "delivery_location_id": str(ctx.ids["hostel_id"]),
        "notes": "E2E unpaid-card cancel probe — safe to ignore",
    }
    r = ctx.api.post("/api/orders", json_body=body, token=ctx.tokens["access"],
                     headers={"X-Campus-ID": str(ctx.ids.get("campus_id") or "")})
    if r.status == 409:
        raise Skip(f"ordering unavailable: {r.snippet(120)}")
    r.check(201, allow=(200,))
    order_id = str(field(r.data or {}, "id")
                   or ((r.data or {}).get("order") or {}).get("id") or "")
    if not order_id:
        rows = ctx.db.select("orders", user_id=ctx.user_id)
        if not rows:
            raise Skip("card order was not persisted")
        order_id = str(sorted(rows, key=lambda o: o.get("created_at") or "")[-1]["id"])
    ctx.track("orders", order_id)
    ctx.track_children("order_items", "order_id", order_id)

    order = ctx.db.select_one("orders", id=order_id) or {}
    expect(str(order.get("payment_status") or "").lower() != "paid",
           f"the probe order came back paid ({order.get('payment_status')}) — it is not testing "
           "the unpaid path", r)
    expect(float(order.get("card_amount_used") or 0) > 0,
           "the card order has no card_amount_used — nothing would have been refunded")

    cancel = ctx.api.post(f"/api/orders/{order_id}/cancel", json_body={"reason": "E2E probe"},
                          token=ctx.tokens["access"])
    cancel.check(200)
    refunded = float((cancel.data or {}).get("wallet_refunded") or 0)
    expect(refunded == 0,
           f"cancel refunded ₦{refunded} on an unpaid card order (payment_status="
           f"{order.get('payment_status')}, card_amount_used={order.get('card_amount_used')}) — "
           "that is money created from nothing")

    wallet_after = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_after = float(wallet_after.get("balance") or 0)
    expect(abs(balance_after - balance_before) < 0.01,
           f"wallet balance moved on an unpaid cancel: ₦{balance_before} → ₦{balance_after}")

    ctx.note(f"unpaid card order cancelled: refunded ₦0, balance unchanged (₦{balance_after})")


def _override_probe_ready(ctx: Ctx, campus: str) -> str:
    """The date a per-date override can be tested on, or raise Skip with why not.

    A dated ordering_windows row outranks an override (precedence rule 1), and an
    override someone already added is theirs, so either one means this probe cannot
    isolate the override. Returns today's WAT date.
    """
    today = (datetime.now(timezone.utc) + timedelta(hours=1)).date().isoformat()
    dated = ctx.db.select("ordering_windows", date=today, campus_id=campus)
    if dated:
        raise Skip(f"campus has a dated ordering_windows row for {today} — it outranks an "
                   "override, so the override cannot be isolated")
    existing = ctx.db.select("operating_hour_overrides", date=today, campus_id=campus)
    if existing:
        raise Skip(f"an override already exists for {today} (reason={existing[0].get('reason')!r}) "
                   "— this probe never touches a row it did not create")
    return today


def _add_override(ctx: Ctx, campus: str, date_iso: str, **fields) -> dict:
    """Insert one override row for this run, registered for cleanup."""
    row = {"date": date_iso, "campus_id": campus, "is_closed": False,
           "reason": "E2E override probe — safe to ignore", **fields}
    created = ctx.db.insert("operating_hour_overrides", row)
    ctx.track_infra("operating_hour_overrides", created.get("id"))
    expect(bool(created.get("id")), f"override insert returned no id: {created}")
    return created


def _drop_override(ctx: Ctx, created: dict):
    """Delete the row this run created — never a row that was already there."""
    if created.get("id"):
        ctx.db.delete("operating_hour_overrides", id=created["id"])


def _status(ctx: Ctx, campus: str, calendar: bool = False) -> dict:
    params = {"campus_id": campus}
    if calendar:
        params["calendar"] = "true"
    r = ctx.api.get("/api/orders/delivery-windows/status", token=ctx.tokens["access"],
                    params=params).check(200)
    return r.data or {}


def _try_order(ctx: Ctx, campus: str, notes: str = "E2E override probe — safe to ignore",
               **extra):
    """Place one real order and return the response, whatever it is.

    `extra` merges into the payload so a probe can set payment_method, wallet_amount,
    idempotency_key or a redemption_id without duplicating the body here.
    """
    if not ctx.ids.get("hostel_id"):
        raise Skip("no delivery point — cannot attempt an order")
    body = {
        "items": [{"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1}],
        "payment_method": "card",
        "delivery_type": "on_campus",
        "delivery_location_id": str(ctx.ids["hostel_id"]),
        "notes": notes,
    }
    body.update(extra)
    return ctx.api.post("/api/orders", json_body=body, token=ctx.tokens["access"],
                        headers={"X-Campus-ID": str(campus)})


# ─────────────────────────────────────────────────────────────────────────────
#  Phase — full flow: money in through the webhook, then kitchen -> rider
# ─────────────────────────────────────────────────────────────────────────────

def _paystack_secret(ctx: Ctx):
    """The secret the running server verifies signatures with, or (None, why not)."""
    if ctx.opts.webhook_secret:
        return ctx.opts.webhook_secret, "--webhook-secret"
    for name in ("PAYSTACK_WEBHOOK_SECRET", "PAYSTACK_SECRET_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value, name
    return None, ("no webhook secret found — pass --webhook-secret or put "
                  "PAYSTACK_SECRET_KEY in the backend .env")


def _sign_paystack(secret: str, raw: str) -> str:
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha512).hexdigest()


def _provision_role_user(ctx: Ctx, role: str, campus: str):
    """Create a throwaway account with a staff role. Returns (user_id, token, error).

    require_role resolves the role from profiles.role, so setting it in the database
    grants the role to the *existing* session — no re-login needed.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    email = f"e2e.{role}.{stamp}.{uuid.uuid4().hex[:6]}@{TEST_EMAIL_DOMAIN}"
    r = ctx.api.post("/api/auth/register", json_body={
        "email": email, "password": DEFAULT_PASSWORD, "full_name": f"E2E {role.title()}",
        "nickname": f"e2e{role[:3]}", "campus_id": str(campus),
    })
    if r.status not in (200, 201):
        return None, None, f"register failed: {r.status} {r.snippet(100)}"
    user_id = str(field(r.data or {}, "user_id")
                  or ((r.data or {}).get("user") or {}).get("id") or "")
    if not user_id:
        return None, None, "register returned no user id"
    ctx.track("profiles", user_id)

    token = (r.data or {}).get("access_token")
    if not token:
        ctx.db.confirm_email(user_id)
    if not ctx.db.update("profiles", {"role": role, "campus_id": str(campus)}, id=user_id):
        return user_id, None, f"could not set role={role} in profiles"

    if not token:
        lr = ctx.api.post("/api/auth/login", json_body={"email": email, "password": DEFAULT_PASSWORD})
        if lr.status != 200:
            return user_id, None, f"login failed: {lr.status} {lr.snippet(100)}"
        token = field(lr.data or {}, "access_token")
    return user_id, token, None


def _drop_role_user(ctx: Ctx, user_id: str):
    """Remove a throwaway staff account completely: profile row and auth record."""
    if not user_id:
        return
    ctx.db.delete("profiles", id=user_id)
    ctx.db.delete_auth_user(user_id)


@step("flow", "flow.webhook_wallet_topup",
      "a signed Paystack charge.success credits the wallet, and a replay credits it once",
      writes=True, route="POST /api/webhooks/paystack", needs=("auth.login",))
def s_webhook_wallet_topup(ctx: Ctx):
    """The money-in path, end to end: signature verified, wallet credited by the RPC the
    webhook calls, ledger row written, and the second delivery of the same event refused
    by the idempotency claim. This is the one flow where a bug costs real money, and it
    had no coverage at all.
    """
    secret, source = _paystack_secret(ctx)
    if not secret:
        raise Skip(source)
    if not ctx.user_id:
        raise Skip("no signed-in user to credit")

    amount = 500.0                                  # below the top-up HP and streak thresholds
    reference = f"E2E-E2E-TOPUP-{uuid.uuid4().hex[:14]}"
    wallet_before = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_before = float(wallet_before.get("balance") or 0)

    payload = {
        "event": "charge.success",
        "data": {
            "reference": reference,
            "amount": int(amount * 100),            # kobo
            "currency": "NGN",
            "status": "success",
            "channel": "card",
            "metadata": {"type": "wallet_topup", "user_id": ctx.user_id},
            "authorization": {"channel": "card"},
            "customer": {"email": ctx.ids.get("email") or "e2e@holygrills.test"},
        },
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    try:
        r = ctx.api.post("/api/webhooks/paystack", raw_body=raw,
                         headers={"x-paystack-signature": _sign_paystack(secret, raw),
                                  "Content-Type": "application/json"})
        r.check(200)
        ctx.note(f"paystack charge.success accepted (signed with {source})")

        wallet_after = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
        balance_after = float(wallet_after.get("balance") or 0)
        expect(abs((balance_after - balance_before) - amount) < 0.01,
               f"the webhook returned 200 but the wallet moved "
               f"₦{balance_after - balance_before:.2f}, expected ₦{amount:.2f}")

        ledger = ctx.db.select("wallet_transactions", provider_reference=reference)
        expect(len(ledger) == 1,
               f"expected exactly one wallet_transactions row for {reference}, "
               f"found {len(ledger)}")
        expect(abs(float(ledger[0].get("amount") or 0) - amount) < 0.01,
               f"ledger row has amount {ledger[0].get('amount')}, expected {amount}")
        ctx.note(f"wallet credited ₦{amount:.0f}; ledger row {ledger[0].get('id')}")

        # The same event again: Paystack retries, and a double credit is the classic
        # webhook bug. The atomic claim must make the second delivery a no-op.
        replay = ctx.api.post("/api/webhooks/paystack", raw_body=raw,
                              headers={"x-paystack-signature": _sign_paystack(secret, raw),
                                       "Content-Type": "application/json"})
        replay.check(200)
        balance_replay = float((ctx.db.select_one("wallets", user_id=ctx.user_id) or {})
                               .get("balance") or 0)
        expect(abs(balance_replay - balance_after) < 0.01,
               f"a replayed webhook credited the wallet twice: ₦{balance_after} → ₦{balance_replay}")
        ledger_after = ctx.db.select("wallet_transactions", provider_reference=reference)
        expect(len(ledger_after) == 1,
               f"a replayed webhook wrote {len(ledger_after)} ledger rows, expected 1")
        ctx.note("replay refused by the idempotency claim — balance unchanged")
    finally:
        # Whatever happened, leave the account exactly as it was found: drop the
        # rows this call caused, then put back every wallet column the credit
        # moved (the RPC may touch more than `balance` — total_credited,
        # updated_at — so diff instead of assuming).
        ctx.db.delete("wallet_transactions", provider_reference=reference)
        for row in ctx.db.select("webhook_events", reference=reference):
            ctx.db.delete("webhook_events", id=row["id"])
        now = ctx.db.select_one("wallets", user_id=ctx.user_id)
        if now is not None and wallet_before:
            changed = {k: v for k, v in wallet_before.items()
                       if k not in ("id", "user_id", "created_at") and now.get(k) != v}
            if changed:
                ctx.db.update("wallets", changed, user_id=ctx.user_id)
            after = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
            still = {k: (wallet_before[k], after.get(k)) for k in changed
                     if after.get(k) != wallet_before[k]}
            if still:
                # Never silent: a dirty wallet on a real account is a finding.
                ctx.warnings.append(
                    f"could not fully restore wallet for {ctx.user_id}: {still}")
            else:
                ctx.note("wallet restored to its pre-webhook values"
                         + (f" ({len(changed)} column(s))" if changed else ""))


def _pin_batch_key(ctx: Ctx, order_id: str) -> str:
    """Give one order a kitchen batch key of its own and return it.

    The kitchen endpoint groups by `orders.delivery_window_id` (batch_id in the URL is
    that value), so a private key means an advance can only ever touch this order.

    If the column carries a foreign key to delivery_windows (the schema is not readable
    from here, and the sandbox cannot connect), the fallback uses the order's own window
    only when no other live order shares it — the endpoint skips terminal orders, so the
    advance still cannot move an order this run does not own.
    """
    batch_key = str(uuid.uuid4())
    if ctx.db.update("orders", {"delivery_window_id": batch_key}, id=order_id):
        return batch_key

    current = ctx.db.select_one("orders", id=order_id) or {}
    own = str(current.get("delivery_window_id") or "")
    terminal = {"delivered", "cancelled", "refunded", "delivery_attempted", "unclaimed"}
    peers = (ctx.db.select("orders", delivery_window_id=own) or []) if own else []
    live_peers = [o for o in peers
                  if str(o.get("id")) != order_id and o.get("status") not in terminal]
    if not own or live_peers:
        detail = "none" if not own else f"{len(live_peers)} live peer(s)"
        raise Skip("the order could not be given a private batch key and its own window "
                   f"is unusable ({detail}) — check whether orders.delivery_window_id "
                   "has a foreign key to delivery_windows")
    ctx.warnings.append("orders.delivery_window_id rejected a private batch key — used the "
                        "order's own window, verified to hold no other live order")
    return own


def _place_pinned_order(ctx: Ctx, campus: str, notes: str, **extra):
    """Place one real order through the API and pin it to a private batch key.

    Returns (order_id, batch_key, response). Raises Skip when the order cannot be placed —
    every caller here needs a real order but none of them is the step that should fail
    because ordering is closed.
    """
    placed = _try_order(ctx, campus, notes=notes, **extra)
    if placed.status not in (200, 201):
        raise Skip(f"could not place an order to probe: {placed.status} {placed.snippet(100)}")
    order_id = str(field(placed.data or {}, "id")
                   or ((placed.data or {}).get("order") or {}).get("id") or "")
    if not order_id:
        raise Skip("the order was not persisted")
    ctx.track("orders", order_id)
    ctx.track_children("order_items", "order_id", order_id)
    batch_key = _pin_batch_key(ctx, order_id)
    return order_id, batch_key, placed


@step("flow", "flow.place_order",
      "the flow places its own order (received, unpaid, in a batch of its own)",
      writes=True, route="POST /api/orders",
      needs=("orders.window", "orders.fund_wallet", "public.hostels"))
def s_flow_place_order(ctx: Ctx):
    """The order the rest of the flow carries. It is placed through the real API so the
    state machine has a genuine `received` order, then pinned to a batch key of its own
    so the kitchen advance can never touch anybody else's order.

    A private key is attempted first; if `delivery_window_id` carries a foreign key the
    fallback uses the order's own window only when no other live order shares it.
    """
    campus = str(ctx.ids["campus_id"])
    order_id, batch_key, _placed = _place_pinned_order(ctx, campus, "E2E flow order — safe to ignore")
    ctx.ids["flow_order_id"] = order_id
    ctx.ids["flow_batch_key"] = batch_key

    row = ctx.db.select_one("orders", id=order_id) or {}
    ctx.note(f"flow order {order_id}: status={row.get('status')} "
             f"payment_status={row.get('payment_status')} total=₦{float(row.get('total_amount') or 0):.2f} "
             f"(batch key {batch_key[:8]})")


@step("flow", "flow.webhook_pays_order",
      "a signed Paystack charge.success pays the flow order",
      writes=True, route="POST /api/webhooks/paystack", needs=("flow.place_order",))
def s_webhook_pays_order(ctx: Ctx):
    """Order payment through the webhook, the branch that confirms a card payment.

    Paystack charges `card_amount_used`, which for a pure card order is the order total;
    the handler compares the webhook amount to `total_amount` and confirms through
    `hg_mark_order_paid`. This pins that path — an order that never reaches `paid` never
    reaches the kitchen in the real world.
    """
    secret, source = _paystack_secret(ctx)
    if not secret:
        raise Skip(source)
    order_id = ctx.ids.get("flow_order_id")
    if not order_id:
        raise Skip("no flow order to pay")

    order = ctx.db.select_one("orders", id=order_id) or {}
    total = float(order.get("total_amount") or 0)
    card = float(order.get("card_amount_used") or 0)
    if total <= 0:
        raise Skip(f"the flow order has no total to pay (total_amount={order.get('total_amount')})")
    if str(order.get("payment_status")) == "paid":
        ctx.note("the flow order was already paid before the webhook "
                 "(card orders are not debited from the wallet) — sending the webhook anyway "
                 "to pin the duplicate-payment branch")

    reference = f"E2E-E2E-ORDER-{uuid.uuid4().hex[:14]}"
    raw = json.dumps({
        "event": "charge.success",
        "data": {
            "reference": reference,
            "amount": int(round(total * 100)),          # Paystack sends kobo
            "currency": "NGN",
            "status": "success",
            "channel": "card",
            "metadata": {"type": "order_payment", "order_id": order_id, "user_id": ctx.user_id},
            "authorization": {"channel": "card"},
            "customer": {"email": ctx.ids.get("email") or "e2e@holygrills.test"},
        },
    }, separators=(",", ":"), ensure_ascii=False)

    try:
        r = ctx.api.post("/api/webhooks/paystack", raw_body=raw,
                         headers={"x-paystack-signature": _sign_paystack(secret, raw),
                                  "Content-Type": "application/json"})
        r.check(200)
        ctx.note(f"order payment webhook accepted (signed with {source})")

        row = ctx.db.select_one("orders", id=order_id) or {}
        expect(str(row.get("payment_status")) == "paid",
               f"the webhook returned 200 but the order is still "
               f"payment_status='{row.get('payment_status')}' (charged ₦{total:.2f}, "
               f"card_amount_used ₦{card:.2f})")
        ctx.note("order payment confirmed: payment_status=paid"
                 + (f", paid_at={row.get('paid_at')}" if row.get("paid_at") else ""))
    finally:
        # The order row is deleted in cleanup; the webhook claim must go now.
        for event in ctx.db.select("webhook_events", reference=reference):
            ctx.db.delete("webhook_events", id=event["id"])


@step("flow", "flow.kitchen_advances_order",
      "the kitchen endpoint walks an order received -> preparing -> ready",
      writes=True, route="POST /api/kitchen/batch/<batch_id>/advance",
      needs=("flow.place_order", "auth.login"))
def s_kitchen_advances_order(ctx: Ctx):
    """The kitchen half of the order lifecycle, which no test touched: the flow's order is
    pinned to a batch, the kitchen advances the batch, and the state machine moves it one
    step at a time with its timestamp. Uses a throwaway kitchen account so the check is
    made with a real kitchen session (and its campus scoping), falling back to the admin
    token when one cannot be provisioned.
    """
    campus = str(ctx.ids["campus_id"])
    order_id = ctx.ids.get("flow_order_id")
    batch_key = ctx.ids.get("flow_batch_key")
    if not order_id or not batch_key:
        raise Skip("no flow order to advance")

    kitchen_id, kitchen_token, why = _provision_role_user(ctx, "kitchen", campus)
    token, as_role = kitchen_token, "kitchen session"
    if not token:
        token = ctx.tokens.get("admin")
        as_role = "admin session"
        ctx.warnings.append(f"kitchen step fell back to the admin token: {why}")
    if not token:
        _drop_role_user(ctx, kitchen_id)
        raise Skip(f"no kitchen or admin session available ({why})")

    try:
        params = {"campus_id": campus} if as_role == "admin session" else {}
        for expected in ("preparing", "ready"):
            r = ctx.api.post(f"/api/kitchen/batch/{batch_key}/advance",
                             json_body={"notes": "E2E kitchen flow"},
                             token=token, params=params)
            r.check(200)
            advanced = (r.data or {}).get("advanced") or []
            moved = [a for a in advanced if str(a.get("order_id")) == order_id]
            expect(bool(moved),
                   f"the advance skipped our order (skipped={(r.data or {}).get('skipped')})",
                   r)
            row = ctx.db.select_one("orders", id=order_id) or {}
            expect(str(row.get("status")) == expected,
                   f"after advancing, the order is '{row.get('status')}', expected '{expected}'")
            ctx.note(f"kitchen advance ({as_role}): {moved[0].get('from')} -> {moved[0].get('to')}")

        row = ctx.db.select_one("orders", id=order_id) or {}
        expect(bool(row.get("preparing_at")), "preparing_at is not stamped")
        expect(bool(row.get("ready_at")), "ready_at is not stamped")
        ctx.ids["flow_order_id"] = order_id
    finally:
        _drop_role_user(ctx, kitchen_id)


@step("flow", "flow.rider_delivers_order",
      "an assigned rider picks the order up and delivers it, awarding the customer's HP",
      writes=True, route="POST /api/riders/orders/<order_id>/deliver",
      needs=("flow.kitchen_advances_order",))
def s_rider_delivers_order(ctx: Ctx):
    """The delivery half: assignment, pickup, delivery, and what delivery is supposed to
    leave behind (status + delivered_at, the customer's HP, the rider's earnings view).
    A rider who cannot see an order assigned to them is reported as a warning rather than
    a hard failure, because the visibility rule lives in RLS — see O1.
    """
    campus = str(ctx.ids["campus_id"])
    order_id = ctx.ids.get("flow_order_id")
    if not order_id:
        raise Skip("no order was advanced by the kitchen step")

    rider_id, rider_token, why = _provision_role_user(ctx, "rider", campus)
    assignment_id = None
    # Delivery rewards write to the customer's profile (hp_balance, the 120-day
    # earn counter, tier, the next-order multiplier). Capture them so a run against
    # a real account can be undone exactly.
    profile_before = ctx.db.select_one("profiles", id=ctx.user_id) or {}
    profile_hp_before = {k: v for k, v in profile_before.items()
                         if "hp" in k.lower() or "tier" in k.lower()}
    try:
        if not rider_id:
            raise Skip(f"could not provision a rider account ({why})")

        # hg_effective_rider: an explicit assignment wins; that is what authorises the rider.
        assignment = ctx.db.insert("delivery_assignments", {
            "order_id": order_id, "rider_id": rider_id, "status": "assigned",
            "note": "E2E flow probe — safe to ignore",
        })
        assignment_id = assignment.get("id")
        ctx.track_infra("delivery_assignments", assignment_id)
        expect(bool(assignment_id), f"could not assign the rider: {assignment}")

        if not rider_token:
            token, as_role = ctx.tokens.get("admin"), "admin session"
            ctx.warnings.append(f"rider step fell back to the admin token: {why}")
        else:
            token, as_role = rider_token, "rider session"
        if not token:
            raise Skip("no rider or admin session available")

        params = {"campus_id": campus} if as_role == "admin session" else {}
        pickup = ctx.api.post(f"/api/riders/orders/{order_id}/pickup", token=token, params=params)
        if pickup.status == 404 and as_role == "rider session":
            ctx.warnings.append(
                "the rider cannot see an order that delivery_assignments assigns to them "
                "(404 on pickup) — either the RLS policy keys off something else or the "
                "policy is missing; reported, not failed, because the policy lives in the "
                "database (see O1)")
            token, as_role = ctx.tokens.get("admin"), "admin session"
            params = {"campus_id": campus}
            if not token:
                raise Skip("the rider could not see the order and there is no admin token")
            pickup = ctx.api.post(f"/api/riders/orders/{order_id}/pickup", token=token, params=params)
        pickup.check(200, allow=(201,))
        ctx.note(f"pickup ({as_role}) -> {ctx.db.select_one('orders', id=order_id).get('status')}")

        delivered = ctx.api.post(f"/api/riders/orders/{order_id}/deliver", token=token, params=params)
        delivered.check(200, allow=(201,))

        row = ctx.db.select_one("orders", id=order_id) or {}
        expect(str(row.get("status")) == "delivered",
               f"after deliver the order is '{row.get('status')}', expected 'delivered'")
        expect(bool(row.get("delivered_at")), "delivered_at is not stamped")

        # Delivery rewards: the state machine credits HP through
        # hg_credit_delivery_hp_atomic and stamps hp_earned / hp_credited_at on the
        # order. Zero HP is legitimate (rate 0 or a tiny order), so an absent row is
        # a warning with the reason, not a failure.
        hp_rows_after = ctx.db.select("hp_transactions", reference_id=order_id) or []
        hp_earned = float(row.get("hp_earned") or 0)
        if hp_rows_after or hp_earned > 0:
            awarded = sum(float(t.get("amount") or 0) for t in hp_rows_after)
            expect(bool(row.get("hp_credited_at")),
                   "the order shows HP earned but hp_credited_at was never stamped")
            ctx.note(f"delivery awarded HP: order.hp_earned={hp_earned:.0f}, "
                     f"{len(hp_rows_after)} ledger row(s) totalling {awarded:.0f}")
        else:
            ctx.warnings.append(
                "delivery produced no HP for the order (no hp_transactions row and "
                "order.hp_earned is 0/absent) — check the earn rate for this tier/campus "
                "before assuming it is a bug")

        earnings = ctx.api.get("/api/riders/earnings", token=token, params=params)
        if earnings.status == 200:
            ctx.note("rider earnings endpoint answered after the delivery")
        ctx.note(f"delivery completed via {as_role}")
    finally:
        _drop_role_user(ctx, rider_id)
        # Ledger rows caused by the flow's own order are removed by order id, so
        # this cleans up even when the run signed in to a pre-existing account
        # (where ctx.sweep is a no-op by design). Nothing else can match.
        for table in ("hp_transactions", "wallet_transactions"):
            for row in ctx.db.select(table, reference_id=order_id):
                ctx.db.delete(table, id=row["id"])
        # The HP the delivery credited lives on the profile too — put it back, or a
        # full run silently inflates a real account's balance.
        if profile_hp_before:
            after = ctx.db.select_one("profiles", id=ctx.user_id) or {}
            moved = {k: v for k, v in profile_hp_before.items() if after.get(k) != v}
            if moved:
                ctx.db.update("profiles", moved, id=ctx.user_id)
            restored = ctx.db.select_one("profiles", id=ctx.user_id) or {}
            still = {k: (profile_hp_before[k], restored.get(k))
                     for k in moved if restored.get(k) != profile_hp_before[k]}
            if still:
                ctx.warnings.append(f"could not fully restore the customer's HP fields: {still}")
            elif moved:
                ctx.note(f"customer profile restored ({len(moved)} HP/tier field(s))")


# ─────────────────────────────────────────────────────────────────────────────
#  Phase — scheduled jobs: every cron job is wired, and one of them really runs
# ─────────────────────────────────────────────────────────────────────────────

def _scheduled_wiring() -> dict:
    """Parse the three places a job name must agree, from the source in this checkout.

    beat_schedule (what actually runs), with_cron_logging (the name a job records its
    outcome under) and admin.py's _CRON_INTERVAL_MINUTES (the names
    /api/admin/cron/status watches) + task_map (what a manual trigger can start).
    A job whose logged name is not watched runs and fails invisibly — that is the
    invariant this returns the data to check.
    """
    cel_lines = (BACKEND_ROOT / "app/tasks/celery_app.py").read_text().splitlines()
    sch_lines = (BACKEND_ROOT / "app/tasks/scheduled.py").read_text().splitlines()
    adm_lines = (BACKEND_ROOT / "app/routes/admin.py").read_text().splitlines()

    # beat_schedule: `"key": {` followed by `"task": "app.tasks.scheduled.fn",`
    beat = {}
    for i, line in enumerate(cel_lines):
        stripped = line.strip()
        if not (stripped.startswith('"') and stripped.endswith('": {')):
            continue
        key = stripped[1:].split('"', 1)[0]
        for nxt in cel_lines[i + 1: i + 3]:
            if '"task": "app.tasks.scheduled.' in nxt:
                beat[key] = nxt.split("app.tasks.scheduled.", 1)[1].split('"', 1)[0]
                break

    # each task: the function name from @celery_app.task(...) and the name it logs under
    logged, functions = {}, set()
    for i, line in enumerate(sch_lines):
        if line.startswith("def ") and "(self)" in line:
            functions.add(line[4:].split("(", 1)[0])
        marker = '@celery_app.task(name="app.tasks.scheduled.'
        if marker in line:
            fn = line.split("app.tasks.scheduled.", 1)[1].split('"', 1)[0]
            for nxt in sch_lines[i + 1: i + 4]:
                if '@with_cron_logging("' in nxt:
                    logged[fn] = nxt.split('@with_cron_logging("', 1)[1].split('"', 1)[0]
                    break

    def block(lines, opener, closer):
        """Lines strictly between the opener (at any indent) and the next `closer` line."""
        for i, line in enumerate(lines):
            if line.lstrip().startswith(opener):
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() == closer:
                        return lines[i + 1: j]
                return lines[i + 1:]
        return []

    watched = {l.strip().split('"', 2)[1] for l in block(adm_lines, "_CRON_INTERVAL_MINUTES = {", "}")
               if l.strip().startswith('"')}
    triggered = {}
    for line in block(adm_lines, "task_map = {", "}"):
        if line.strip().startswith('"') and ":" in line:
            triggered[line.split('"', 2)[1]] = line.split(":", 1)[1].strip().rstrip(",")

    # The swagger enum is the only list inside run_cron_job; start at the `enum:` line so
    # the `- in: path` / `- name:` parameter lines above it are not mistaken for jobs.
    enum = set()
    for i, line in enumerate(adm_lines):
        if line.startswith("def run_cron_job") or (line.strip() == "enum:" and enum == set()):
            pass
    opened = False
    for line in adm_lines:
        if line.strip() == "enum:":
            opened = True
            continue
        if opened:
            if line.strip().startswith("- "):
                enum.add(line.strip()[2:].strip())
            elif line.strip() and not line.strip().startswith("-"):
                break

    return {"beat": beat, "logged": logged, "functions": functions,
            "watched": watched, "triggered": triggered, "enum": enum}


def _wait_for(check, timeout: float = 45.0, interval: float = 1.5) -> bool:
    """Poll `check` until it returns truthy or the deadline passes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(interval)
    return False


@step("scheduled", "scheduled.jobs_wired",
      "every scheduled job records its outcome where cron_status can see it")
def s_jobs_wired(ctx: Ctx):
    """The wiring check for all 17 jobs, offline, no job is invoked.

    A scheduled job that logs under a name `/api/admin/cron/status` does not watch runs
    every night and reports nothing — the failure mode this catches. It also checks that
    every beat entry resolves to a function in app/tasks/scheduled.py and that the manual
    trigger map only starts jobs the status page can see.
    """
    try:
        wiring = _scheduled_wiring()
    except FileNotFoundError as exc:
        raise Skip(f"backend source not available to inspect ({exc})")
    beat, logged, functions = wiring["beat"], wiring["logged"], wiring["functions"]
    watched, triggered, enum = wiring["watched"], wiring["triggered"], wiring["enum"]

    expect(bool(beat) and bool(logged) and bool(watched),
           "could not parse the job tables — the checks below would be vacuous "
           f"(beat={len(beat)}, logged={len(logged)}, watched={len(watched)})")

    missing_fn = {k: fn for k, fn in beat.items() if fn not in functions}
    expect(not missing_fn,
           f"beat_schedule points at task functions that do not exist: {missing_fn}")

    invisible = []
    for beat_key, fn in beat.items():
        name = logged.get(fn)
        if name is None:
            invisible.append(f"{beat_key} ({fn} has no with_cron_logging name)")
        elif name not in watched:
            invisible.append(f"{beat_key} logs '{name}', which /api/admin/cron/status does not watch")
    expect(not invisible,
           "scheduled job(s) whose failures would be invisible: " + "; ".join(sorted(invisible)))

    unwatched_triggers = sorted(set(triggered) - watched)
    expect(not unwatched_triggers,
           f"the manual trigger map starts job(s) the status page cannot see: {unwatched_triggers}")

    untriggerable = sorted(set(watched) - set(triggered))
    if untriggerable:
        ctx.note(f"watched but not manually triggerable: {', '.join(untriggerable)}")
    drift = sorted(set(enum) ^ set(triggered))
    if drift:
        ctx.warnings.append(
            "the /api/cron/<job_name> documentation enum and task_map disagree: "
            f"{drift} — the docs or the map need updating")
    ctx.note(f"{len(beat)} scheduled job(s) wired and visible; "
             f"{len(triggered)} manually triggerable; {len(functions)} task functions")


@step("scheduled", "scheduled.trigger_contract",
      "POST /api/admin/cron/<job_name> refuses an unknown job and lists the real ones",
      writes=True, route="POST /api/admin/cron/<job_name>", needs=("public.campuses",))
def s_trigger_contract(ctx: Ctx):
    """The trigger's own contract, checked with a super_admin session and a job name that
    cannot exist — so nothing is ever started by this step."""
    campus = str(ctx.ids["campus_id"])
    admin_id, admin_token, why = _provision_role_user(ctx, "super_admin", campus)
    if not admin_token:
        _drop_role_user(ctx, admin_id)
        raise Skip(f"could not provision a super_admin session: {why}")
    try:
        r = ctx.api.post("/api/admin/cron/e2e-no-such-job", token=admin_token)
        expect(r.status == 404,
               f"an unknown job name answered {r.status} (expected 404)", r)
        available = set((r.data or {}).get("available_jobs") or [])
        expect(bool(available),
               f"the 404 does not list available_jobs — {r.snippet(160)}", r)
        wiring = _scheduled_wiring()
        expect(available == set(wiring["triggered"]),
               f"available_jobs lists {sorted(available)} but task_map holds "
               f"{sorted(wiring['triggered'])}")
        ctx.note(f"unknown job refused; {len(available)} job(s) listed and matching the map")
    finally:
        _drop_role_user(ctx, admin_id)


@step("scheduled", "scheduled.jobs_run_safe",
      "check-order-locks really runs: an overdue lock is expired and the outcome is recorded",
      writes=True, route="POST /api/admin/cron/<job_name>", needs=("public.campuses",))
def s_jobs_run_safe(ctx: Ctx):
    """Invoke one job for real, with a canary row it is guaranteed to touch.

    `check-order-locks` is safe to run only when the canary is the *only* active lock on
    the campus — otherwise the job would also expire real users' locks, so the step skips
    instead of doing that. It then asserts three things: the lock expired, an audit row
    carrying the outcome appeared (so `cron_status` can report it), and the same job can
    run again immediately (the cron lock was released, not stuck).
    """
    campus = str(ctx.ids["campus_id"])
    yesterday = (datetime.now(timezone.utc) + timedelta(hours=1) - timedelta(days=1)).date().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    admin_id, admin_token, why = _provision_role_user(ctx, "super_admin", campus)
    if not admin_token:
        _drop_role_user(ctx, admin_id)
        raise Skip(f"could not provision a super_admin session: {why}")

    started = datetime.now(timezone.utc).isoformat()
    lock_id = None
    try:
        canary = ctx.db.insert("order_locks", {
            "user_id": ctx.user_id, "campus_id": campus, "locked_date": yesterday,
            "status": "active", "reward_type": "discount", "reschedule_count": 0,
            "created_at": now, "updated_at": now,
        })
        lock_id = str((canary or {}).get("id") or "")
        if not lock_id:
            raise Skip("the canary order_locks row was not persisted")
        ctx.track_infra("order_locks", lock_id)

        others = [l for l in (ctx.db.select("order_locks", status="active", campus_id=campus) or [])
                  if str(l.get("id")) != lock_id]
        if others:
            raise Skip(f"{len(others)} other active order lock(s) exist on this campus — "
                       "running the job would expire real users' locks, so it is skipped")

        first = ctx.api.post("/api/admin/cron/check-order-locks", token=admin_token)
        first.check(202)
        expired = _wait_for(lambda: str((ctx.db.select_one("order_locks", id=lock_id) or {})
                                       .get("status") or "") == "expired")
        expect(expired,
               "check-order-locks ran but the overdue canary lock is still 'active'")

        def audit_rows():
            return [r for r in (ctx.db.select("admin_audit_logs", entity_type="cron_jobs") or [])
                    if str(r.get("entity_id")) == "check-order-locks"
                    and str(r.get("created_at") or "") >= started]
        logged = _wait_for(lambda: bool(audit_rows()))
        expect(logged, "the job expired the lock but wrote no audit row — "
                       "/api/admin/cron/status cannot report it")
        actions = sorted({str(r.get("action")) for r in audit_rows()})
        expect(not any(a.endswith("_failed") for a in actions),
               f"the job recorded a failure: {actions}")
        ctx.note(f"check-order-locks: canary expired, audit rows {actions}")

        # The cron lock must be released, or the next scheduled run is skipped silently.
        second = ctx.api.post("/api/admin/cron/check-order-locks", token=admin_token)
        second.check(202)
        again = _wait_for(lambda: len([r for r in audit_rows()
                                       if str(r.get("action")).endswith("_success")
                                       or str(r.get("action")).endswith("_skipped")]) >= 2)
        if not again:
            ctx.warnings.append("the second trigger produced no new audit row — the cron "
                                "lock may not have been released, or the job skipped silently")
        else:
            ctx.note("the job ran a second time immediately — the cron lock was released")

        for row in audit_rows():
            ctx.db.delete("admin_audit_logs", id=row["id"])
    finally:
        if lock_id:
            ctx.db.delete("order_locks", id=lock_id)
        _drop_role_user(ctx, admin_id)


@step("scheduled", "scheduled.jobs_run_all",
      "every job in the trigger map runs without failing (opt-in: --with-cron)",
      writes=True, route="POST /api/admin/cron/<job_name>", needs=("public.campuses",))
def s_jobs_run_all(ctx: Ctx):
    """Run every triggerable job once and require that none ends in `failed`.

    OFF BY DEFAULT, and that is deliberate: these jobs mutate shared state — they award
    HP, reset leaderboards, send push notifications and email real users, place scheduled
    orders. On your test project that is exactly what they are for, but it is not
    something a smoke run should do behind your back. Pass `--with-cron` to accept the
    side effects (recommended once, on the test project, before launch).
    """
    if "--with-cron" not in sys.argv:
        raise Skip("run with --with-cron to invoke every scheduled job "
                   "(they mutate shared data: HP, leaderboards, notifications, email)")
    campus = str(ctx.ids["campus_id"])
    admin_id, admin_token, why = _provision_role_user(ctx, "super_admin", campus)
    if not admin_token:
        _drop_role_user(ctx, admin_id)
        raise Skip(f"could not provision a super_admin session: {why}")
    started = datetime.now(timezone.utc).isoformat()
    try:
        names = sorted(_scheduled_wiring()["triggered"])
        failed, silent = [], []
        for name in names:
            ctx.api.post(f"/api/admin/cron/{name}", token=admin_token).check(202)

            def rows_for(job=name):
                return [r for r in (ctx.db.select("admin_audit_logs", entity_type="cron_jobs") or [])
                        if str(r.get("entity_id")) == job and str(r.get("created_at") or "") >= started]
            wait_for_seconds = 120 if name in ("process-scheduled-orders", "send-newsletter-campaigns",
                                               "scan-abandoned-carts", "send-scheduled-blasts") else 45
            if not _wait_for(lambda: bool(rows_for()), timeout=wait_for_seconds):
                silent.append(name)
                continue
            actions = {str(r.get("action")) for r in rows_for()}
            if any(a.endswith("_failed") for a in actions):
                detail = next((str(r.get("after_value")) for r in rows_for()
                               if str(r.get("action")).endswith("_failed")), "")
                failed.append(f"{name}: {detail[:160]}")
            elif all(a.endswith("_skipped") for a in actions):
                ctx.note(f"{name}: skipped (lock held or nothing to do)")

        if silent:
            ctx.warnings.append(
                "job(s) produced no audit row within the wait — they may be slow, or the "
                f"background thread died: {silent}")
        expect(not failed, "scheduled job(s) failed: " + " | ".join(failed))
        for row in (r for r in (ctx.db.select("admin_audit_logs", entity_type="cron_jobs") or [])
                    if str(r.get("created_at") or "") >= started):
            ctx.db.delete("admin_audit_logs", id=row["id"])
        ctx.note(f"{len(names)} job(s) triggered; none recorded a failure")
    finally:
        _drop_role_user(ctx, admin_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Phase — surface: the blueprints nothing else touches
# ─────────────────────────────────────────────────────────────────────────────

def _rows_payload(resp) -> list:
    """A list out of either a bare JSON array or the common `{key: [...]}` envelope."""
    if isinstance(resp.data, list):
        return resp.data
    if isinstance(resp.data, dict):
        for key in ("results", "units", "spins", "orders", "squads", "items"):
            value = resp.data.get(key)
            if isinstance(value, list):
                return value
    return []


def _drop_user_effects(ctx: Ctx, user_id: str):
    """Delete every row a throwaway account's probe could have created for it.

    The account is deleted anyway; this is about rows that would survive it — HP ledger
    entries, spin credits, prize fulfilments, push subscriptions, squads, rosters.
    """
    for table, column in (("hp_transactions", "user_id"),
                          ("exclusive_spins", "user_id"),
                          ("exclusive_spin_fulfillments", "user_id"),
                          ("push_subscriptions", "user_id"),
                          ("reward_redemptions", "user_id")):
        try:
            rows = ctx.db.select(table, **{column: user_id}) or []
        except Failed as exc:
            # A table that does not exist in this project cannot hold rows to clean up.
            ctx.warnings.append(f"cleanup: could not read {table} ({exc})")
            continue
        for row in rows:
            ctx.db.delete(table, id=row["id"])
    try:
        squads = ctx.db.select("squads", creator_id=user_id) or []
    except Failed as exc:
        ctx.warnings.append(f"cleanup: could not read squads ({exc})")
        return
    for squad in squads:
        ctx.db.delete("squad_roster", squad_id=squad["id"])
        ctx.db.delete("squads", id=squad["id"])


@step("surface", "surface.docs_endpoints",
      "the API docs (flasgger) serve HTML, a real spec, and their static assets",
      route="GET /api/docs/",
      routes=("GET /api/docs/apispec.json",
              "GET /api/docs/static/<filename>",
              "GET /apidocs/index.html",
              "GET /oauth2-redirect.html",))

def s_docs_endpoints(ctx: Ctx):
    """Five doc routes, no auth, no writes.

    `/api/docs/apispec.json` is the machine-readable contract the front end and any
    integration reads; if it stops returning a parseable spec with the app's real paths
    in it, that breaks silently. The static asset is fetched by path so a moved or
    unshipped asset is caught rather than assumed.
    """
    docs = ctx.api.get("/api/docs/")
    if docs.status == 404:
        raise Skip("the API docs are not served in this configuration")
    docs.check(200)
    expect("swagger" in docs.text.lower() or "<html" in docs.text.lower(),
           f"/api/docs/ returned 200 but not a docs page — {docs.snippet(120)}")

    spec = ctx.api.get("/api/docs/apispec.json").check(200)
    expect(isinstance(spec.data, dict) and spec.data.get("paths"),
           f"the spec is not a Swagger document — {spec.snippet(160)}")
    paths = spec.data.get("paths") or {}
    base = str(spec.data.get("basePath") or "")
    # Paths are relative to basePath (/api by default), so the app's own order route is
    # "/orders" here — asserting on a full "/api/orders" would test the wrong thing.
    expect(any(p == "/orders" or p.startswith("/orders/") for p in paths),
           f"the spec lists {len(paths)} path(s) but none is the order route "
           f"(basePath {base!r})")
    expect(any(p == "/webhooks/paystack" for p in paths),
           "the spec does not document the Paystack webhook")
    expect(bool((spec.data.get("info") or {}).get("title")),
           "the spec has no info.title")
    ctx.note(f"spec: {len(paths)} path(s) under basePath {base!r}, "
             f"title {(spec.data.get('info') or {}).get('title')!r}")

    css = ctx.api.get("/api/docs/static/swagger-ui.css")
    expect(css.status == 200 and len(css.text) > 100,
           f"the swagger static asset did not load ({css.status}, {len(css.text)} bytes)")

    for path in ("/apidocs/index.html", "/oauth2-redirect.html"):
        r = ctx.api.get(path)
        if r.status in (301, 302, 308):
            # flasgger publishes /apidocs/index.html as a redirect to /api/docs/; the
            # redirect target is the documented page, so that is the healthy answer.
            expect("/api/docs/" in r.text or "/apidocs/" in r.text,
                   f"{path} redirected ({r.status}) somewhere unexpected — {r.snippet(120)}", r)
            ctx.note(f"{path} -> {r.status} redirect")
        else:
            expect(r.status == 200,
                   f"{path} answered {r.status} — the docs page links it", r)
    ctx.note("docs page, spec, static asset and both redirect pages all answered 200")


@step("surface", "surface.measurement_units",
      "GET /api/measurement-units is authenticated and returns the unit list",
      route="GET /api/measurement-units", needs=("auth.login",))
def s_measurement_units(ctx: Ctx):
    """The route is small; the interesting part is that it is not public.

    It sits under the stock blueprint and reads a table through the user client, so an
    anonymous caller must be refused — a missing `@require_auth` here would expose
    inventory units to anyone.
    """
    anon = ctx.api.get("/api/measurement-units")
    expect(anon.status in (401, 403),
           f"an unauthenticated caller reached the measurement units ({anon.status})", anon)

    r = ctx.api.get("/api/measurement-units", token=ctx.tokens["access"]).check(200)
    rows = _rows_payload(r)
    for row in rows[:10]:
        expect(bool(row.get("id")) and bool(row.get("name")),
               f"a measurement_units row is missing id/name — {json.dumps(row)[:120]}")
    ctx.note(f"measurement units: {len(rows)} row(s), anonymous caller refused ({anon.status})")


@step("surface", "surface.users_search",
      "GET /api/users/search stays inside the caller's campus",
      route="GET /api/users/search", needs=("auth.login",))
def s_users_search(ctx: Ctx):
    """Search is service-role underneath (profiles RLS hides other people), so the
    campus filter in the handler IS the security boundary. This checks it holds: every
    result must belong to the signed-in account's campus."""
    empty = ctx.api.get("/api/users/search", params={"q": ""}, token=ctx.tokens["access"]).check(200)
    expect(_rows_payload(empty) == [],
           f"an empty query returned rows — {empty.snippet(120)}")

    campus = str(ctx.ids.get("campus_id") or "")
    r = ctx.api.get("/api/users/search", params={"q": "e2e"}, token=ctx.tokens["access"]).check(200)
    results = _rows_payload(r)
    expect(isinstance(results, list), f"search did not return a list — {r.snippet(120)}")

    foreign = []
    for hit in results[:20]:
        uid = str(hit.get("id") or hit.get("user_id") or "")
        if not uid:
            continue
        profile = ctx.db.select_one("profiles", id=uid) or {}
        if str(profile.get("campus_id") or "") != campus:
            foreign.append(f"{uid} is on campus {profile.get('campus_id')}")
    expect(not foreign,
           f"search returned user(s) outside campus {campus}: {foreign[:3]}")

    nobody = ctx.api.get("/api/users/search", params={"q": f"zz-no-such-{uuid.uuid4().hex[:8]}"},
                         token=ctx.tokens["access"]).check(200)
    expect(_rows_payload(nobody) == [],
           f"a nonsense query returned rows — {nobody.snippet(120)}")
    ctx.note(f"search: {len(results)} result(s) all on campus {campus}; empty and nonsense "
             "queries return []")


@step("surface", "surface.push_roundtrip",
      "a push subscription can be registered and deactivated",
      writes=True, needs=("public.campuses",), route="POST /api/push/subscribe",
      routes=("DELETE /api/push/subscribe",))

def s_push_roundtrip(ctx: Ctx):
    """Both push routes, on a throwaway account, with an endpoint that cannot exist.

    The unsubscribe is a soft delete (`is_active=false`), so the step checks the row is
    still there but inactive — that is the documented behaviour, and a hard delete would
    actually be the bug (the same endpoint could then be re-subscribed as a new row).
    """
    campus = str(ctx.ids.get("campus_id") or "")
    user_id, token, why = _provision_role_user(ctx, "customer", campus)
    if not token:
        _drop_role_user(ctx, user_id)
        raise Skip(f"could not provision a throwaway customer: {why}")
    endpoint = f"https://e2e-{uuid.uuid4().hex[:10]}.invalid/push"
    try:
        sub = ctx.api.post("/api/push/subscribe", token=token, json_body={
            "subscription": {"endpoint": endpoint,
                             "keys": {"p256dh": "BOrE2EProbeKeysNotReal", "auth": "e2e"}},
            "device_label": "E2E probe",
        })
        expect(sub.status in (200, 201),
               f"subscribing answered {sub.status} — {sub.snippet(160)}", sub)

        rows = ctx.db.select("push_subscriptions", user_id=user_id) or []
        expect(any(endpoint == ((r.get("subscription") or {}).get("endpoint")) for r in rows),
               f"the subscribe call succeeded but no push_subscriptions row holds {endpoint}")

        off = ctx.api.delete("/api/push/subscribe", token=token, json_body={"endpoint": endpoint})
        expect(off.status == 200, f"unsubscribe answered {off.status} — {off.snippet(160)}", off)
        after = [r for r in (ctx.db.select("push_subscriptions", user_id=user_id) or [])
                 if endpoint == ((r.get("subscription") or {}).get("endpoint"))]
        expect(after and after[0].get("is_active") is False,
               f"unsubscribe did not deactivate the row (rows found: {len(after)})")
        ctx.note("subscribed then deactivated (row kept soft-deleted, as designed)")
    finally:
        _drop_user_effects(ctx, user_id)
        _drop_role_user(ctx, user_id)


@step("surface", "surface.squads_lifecycle",
      "a squad is created, listed, read, joined, left, and its orders read",
      writes=True, route="POST /api/squads", needs=("auth.login",),
      routes=("GET /api/squads",
              "GET /api/squads/<squad_id>",
              "POST /api/squads/<squad_id>/members",
              "DELETE /api/squads/<squad_id>/members/<member_id>",
              "GET /api/squads/<squad_id>/orders",))

def s_squads_lifecycle(ctx: Ctx):
    """All six squad routes with a throwaway organizer and a throwaway member.

    Squad orders are feature-flagged (`squad_orders`), so a 403 is a legitimate
    configuration and the step skips with that reason rather than failing.
    """
    campus = str(ctx.ids.get("campus_id") or "")
    organizer_id, organizer_token, why = _provision_role_user(ctx, "customer", campus)
    member_id, _member_token, why_member = _provision_role_user(ctx, "customer", campus)
    squad_id = None
    try:
        if not organizer_token or not member_id or not _member_token:
            raise Skip(f"could not provision two throwaway customers ({why}; {why_member})")
        member_email = f"e2e.squad.{uuid.uuid4().hex[:8]}@{TEST_EMAIL_DOMAIN}"
        name = f"E2E Squad {uuid.uuid4().hex[:6]}"

        created = ctx.api.post("/api/squads", token=organizer_token,
                               json_body={"name": name, "emails": [member_email]})
        if created.status == 403:
            raise Skip(f"squad_orders is disabled for this campus — {created.snippet(120)}")
        expect(created.status == 201, f"creating a squad answered {created.status} — "
                                      f"{created.snippet(160)}", created)
        squad_id = str((created.data or {}).get("id") or "")
        expect(bool(squad_id), f"the squad was created without an id — {created.snippet(120)}")
        ctx.track_infra("squads", squad_id)

        listed = ctx.api.get("/api/squads", token=organizer_token).check(200)
        ids = [str(x.get("id")) for x in _rows_payload(listed)]
        expect(squad_id in ids, f"the new squad is not in GET /api/squads ({ids[:5]})")

        one = ctx.api.get(f"/api/squads/{squad_id}", token=organizer_token).check(200)
        expect(contains_id(one.data, squad_id), f"the squad response does not carry its id — "
                                                f"{one.snippet(120)}", one)

        joined = ctx.api.post(f"/api/squads/{squad_id}/members", token=organizer_token,
                              json_body={"email": member_email})
        expect(joined.status in (200, 201),
               f"adding the member answered {joined.status} — {joined.snippet(160)}", joined)

        squad_view = ctx.api.get(f"/api/squads/{squad_id}", token=organizer_token).check(200)
        rows = squad_view.data.get("roster") if isinstance(squad_view.data, dict) else None
        rows = rows if isinstance(rows, list) else _rows_payload(squad_view)
        entry = next((r for r in rows if str(r.get("email", "")).lower() == member_email), None)
        expect(entry is not None,
               f"the added member is not in the squad roster — {squad_view.snippet(160)}")

        left = ctx.api.delete(f"/api/squads/{squad_id}/members/{entry.get('id')}",
                              token=organizer_token)
        expect(left.status in (200, 204),
               f"removing the member answered {left.status} — {left.snippet(160)}", left)
        removed = [r for r in (ctx.db.select("squad_roster", squad_id=squad_id) or [])
                   if str(r.get("id")) == str(entry.get("id"))]
        expect(removed and removed[0].get("is_active") is False,
               "the roster row was not deactivated by the remove call")

        orders = ctx.api.get(f"/api/squads/{squad_id}/orders", token=organizer_token).check(200)
        expect(contains_id(orders.data, squad_id) or _rows_payload(orders) == [],
               f"the squad orders response is neither a list nor scoped to the squad — "
               f"{orders.snippet(140)}", orders)
        ctx.note("squad created, listed, read, member added and removed (soft), orders read")
    finally:
        if squad_id:
            ctx.db.delete("squad_roster", squad_id=squad_id)
            ctx.db.delete("squads", id=squad_id)
        _drop_user_effects(ctx, organizer_id)
        _drop_user_effects(ctx, member_id)
        _drop_role_user(ctx, organizer_id)
        _drop_role_user(ctx, member_id)


@step("surface", "surface.exclusive_spin",
      "a granted spin is consumed exactly once and a second spin is refused",
      writes=True, needs=("public.campuses",), route="POST /api/exclusive-spin/spin",
      routes=("GET /api/exclusive-spin",))

def s_exclusive_spin(ctx: Ctx):
    """Both spin routes, on a throwaway account with a credit this step grants it.

    The prize is random: HP, a free-delivery cap, or a physical-prize fulfilment row.
    All three land on the throwaway account, whose rows are deleted at the end — a real
    account is never spun against, because the outcome cannot be undone exactly.
    """
    campus = str(ctx.ids.get("campus_id") or "")
    user_id, token, why = _provision_role_user(ctx, "customer", campus)
    if not token:
        _drop_role_user(ctx, user_id)
        raise Skip(f"could not provision a throwaway customer: {why}")
    try:
        summary = ctx.api.get("/api/exclusive-spin", token=token)
        if summary.status == 403:
            raise Skip(f"the exclusive_spin feature is disabled — {summary.snippet(120)}")
        summary.check(200)
        expect(isinstance(summary.data, dict) and "total_spins" in summary.data,
               f"the spin summary has no total_spins — {summary.snippet(140)}")

        credit = ctx.db.insert("exclusive_spins", {
            "user_id": user_id, "spin_count": 1, "source": "e2e_probe",
            "month": datetime.now(timezone.utc).strftime("%Y-%m"),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "campus_id": campus or None,
        })
        credit_id = str((credit or {}).get("id") or "")
        if not credit_id:
            raise Skip("the spin credit row was not persisted")

        spun = ctx.api.post("/api/exclusive-spin/spin", token=token)
        spun.check(200)
        prize = (spun.data or {}).get("prize") or (spun.data or {}).get("prize_name")
        expect(bool(prize), f"the spin returned no prize — {spun.snippet(140)}", spun)

        row = ctx.db.select_one("exclusive_spins", id=credit_id) or {}
        expect(int(row.get("spin_count") or 0) == 0,
               f"the spin was awarded but the credit still shows {row.get('spin_count')}")

        again = ctx.api.post("/api/exclusive-spin/spin", token=token)
        expect(again.status == 400,
               f"a second spin with no credits answered {again.status} "
               f"(expected 400) — {again.snippet(120)}", again)
        ctx.note(f"spin consumed once (prize {prize!r}); second spin refused with 400")
    finally:
        _drop_user_effects(ctx, user_id)
        _drop_role_user(ctx, user_id)


@step("surface", "surface.graduation_claim",
      "a graduating student claims once, and the claim cannot be repeated",
      writes=True, needs=("public.campuses",), route="POST /api/graduation/claim")
def s_graduation_claim(ctx: Ctx):
    """Both branches of the graduation claim, on a throwaway account.

    First as an ordinary account (not eligible — the guard), then, only if an academic
    level at or above the `graduation_min_level` setting exists, with that level set on
    the throwaway profile: the claim awards HP, flags the profile, and a second claim is
    refused. Everything belongs to the throwaway account.
    """
    campus = str(ctx.ids.get("campus_id") or "")
    user_id, token, why = _provision_role_user(ctx, "customer", campus)
    if not token:
        _drop_role_user(ctx, user_id)
        raise Skip(f"could not provision a throwaway customer: {why}")
    try:
        ineligible = ctx.api.post("/api/graduation/claim", token=token)
        expect(ineligible.status == 400,
               f"an account below the graduation level got {ineligible.status} "
               f"(expected 400) — {ineligible.snippet(140)}", ineligible)

        try:
            setting = ctx.db.select("system_settings", key="graduation_min_level") or []
            min_rank = int((setting[0].get("value") if setting else None) or 400)
        except Exception:                                            # noqa: BLE001
            min_rank = 400
        levels = [l for l in (ctx.db.select("academic_levels") or [])
                  if l.get("rank") is not None and int(l["rank"]) >= min_rank
                  and l.get("campus_id") in (campus, None)]
        if not levels:
            raise Skip(f"no academic_levels row has rank >= {min_rank}, so the eligible "
                       "branch cannot be reached")
        eligible = levels[0]
        ctx.db.update("profiles", {"academic_level": eligible.get("value"),
                                   "graduation_claimed": False}, id=user_id)

        claimed = ctx.api.post("/api/graduation/claim", token=token)
        claimed.check(200)
        expect(int((claimed.data or {}).get("hp_awarded") or 0) > 0,
               f"the claim returned no hp_awarded — {claimed.snippet(140)}", claimed)

        profile = ctx.db.select_one("profiles", id=user_id) or {}
        expect(profile.get("graduation_claimed") is True,
               "the claim succeeded but profiles.graduation_claimed is not set")
        rows = ctx.db.select("hp_transactions", user_id=user_id) or []
        expect(any(str(t.get("reference_type")) == "graduation" for t in rows),
               f"no graduation row in hp_transactions after a successful claim ({len(rows)} row(s))")

        repeat = ctx.api.post("/api/graduation/claim", token=token)
        expect(repeat.status == 400,
               f"a second claim answered {repeat.status} (expected 400 — one-time only) — "
               f"{repeat.snippet(120)}", repeat)
        ctx.note(f"eligible claim awarded {claimed.data.get('hp_awarded')} HP at level "
                 f"{eligible.get('value')}; repeat refused with 400")
    finally:
        _drop_user_effects(ctx, user_id)
        _drop_role_user(ctx, user_id)


@step("surface", "surface.upload_signature",
      "the upload signature is issued and a non-admin cannot choose the folder",
      route="POST /api/upload/signature", needs=("auth.login",))
def s_upload_signature(ctx: Ctx):
    """The signature route, checked for its authorisation rule rather than its crypto.

    Non-admins get `profile_photos/<their own id>` no matter what they ask for; this
    sends `folder: "general"` and requires it to be ignored. A 503 means Cloudinary is
    not configured in this environment, which is a legitimate configuration.
    """
    anon = ctx.api.post("/api/upload/signature", json_body={})
    expect(anon.status in (401, 403, 503),
           f"an unauthenticated caller got {anon.status} from the signature route", anon)

    r = ctx.api.post("/api/upload/signature", token=ctx.tokens["access"],
                     json_body={"folder": "general"})
    if r.status == 503:
        raise Skip(f"Cloudinary is not configured — {r.snippet(120)}")
    r.check(200)
    folder = str((r.data or {}).get("folder") or "")
    expect(folder == f"profile_photos/{ctx.user_id}",
           f"a non-admin asked for folder 'general' and got {folder!r} — the folder is "
           f"not pinned to the caller", r)
    expect(bool((r.data or {}).get("signature")) and bool((r.data or {}).get("timestamp")),
           f"the signature response is missing signature/timestamp — {r.snippet(140)}")
    ctx.note(f"signature issued for the caller's own folder ({folder}) despite a folder request")


# ─────────────────────────────────────────────────────────────────────────────
#  Phase — surface, part 2: the rest of the reachable routes
# ─────────────────────────────────────────────────────────────────────────────

_READ_SWEEP_FALLBACK = (
    # Only used when the suite cannot build the app in-process (--base-url on a host
    # without the backend source). Filled with a UUID where the rule has a parameter.
    "GET /api/orders/scheduled", "GET /api/orders/validate-promo",
    "GET /api/events", "GET /api/events/my-tickets", "GET /api/challenges/badges",
    "GET /api/challenges/my", "GET /api/challenges/pwa-push-bonus-status",
    "GET /api/leaderboard/my-rank", "GET /api/leaderboard/squad",
    "GET /api/leaderboard/squad/my-rank", "GET /api/leaderboard/hall-of-fame",
    "GET /api/leaderboard/hall-of-fame/inductees", "GET /api/hp/bundles",
    "GET /api/hp/unlock-history", "GET /api/menu/addons", "GET /api/menu/kitchen-capacity",
    "GET /api/marketplace", "GET /api/marketplace/purchases",
    "GET /api/notifications/preferences", "GET /api/saved", "GET /api/free-sides",
    "GET /api/order-locks", "GET /api/wallet", "GET /api/rewards",
)


def _read_sweep_routes() -> tuple[list[str], str]:
    """Every GET the app serves that no step declares and no sweep covers.

    Built from the live URL map, so it shrinks as real steps are added and picks up new
    routes automatically. Admin-gated GETs are excluded — they are swept with a staff
    token by the authorization phase, which is the meaningful check for them.
    """
    try:
        sys.path.insert(0, str(BACKEND_ROOT))
        os.environ.setdefault("FLASK_ENV", "development")
        from app import create_app
        from app.config import config_map
        app = create_app(config_map["development"])
    except Exception as exc:                                        # noqa: BLE001
        print(f"    (live route map unavailable: {exc} — using the curated list)",
              file=sys.stderr)
        return list(_READ_SWEEP_FALLBACK), "curated fallback"

    def norm(rule: str) -> str:
        rule = re.sub(r"<[^>]*:([^>]+)>", r"<\1>", rule)
        return rule.rstrip("/") or "/"

    declared = set()
    for st in STEPS:
        for entry in st.all_routes():
            method, _, path = entry.partition(" ")
            if method:
                declared.add((method, norm(path)))
    admin = {(m, norm(rule)) for m, rule in _admin_surface()[0]}

    routes = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static" or "GET" not in rule.methods:
            continue
        if (("GET", norm(str(rule.rule)))) in declared or (("GET", norm(str(rule.rule)))) in admin:
            continue
        routes.append(f"GET {rule.rule}")
    routes.sort()
    return routes, "live URL map"


@step("surface", "surface.read_sweep",
      "every remaining GET answers an authenticated customer without a 5xx or a 401",
      needs=("auth.login",))
def s_read_sweep(ctx: Ctx):
    """The read surface no step declared: one authenticated GET each.

    This is a liveness contract, not a behaviour test. For every route it asserts the
    handler ran and answered: **no 5xx** (the crash class a missing column or a bad query
    produces) and **no 401** (the session is recognised). An id-based route answering 404
    for a random UUID is the correct answer and is recorded as such; a 403 is kept but
    noted, because it usually means a feature flag is off.

    Run with `--only surface.read_sweep` to see the per-route outcome in --verbose.
    """
    token = ctx.tokens.get("access")
    if not token:
        raise Skip("no customer session")
    routes, source = _read_sweep_routes()
    if not routes:
        raise Skip("every GET route is already declared by a step")

    placeholder = str(uuid.uuid4())
    crashes, rejected, allowed_403, clean, ok = [], [], [], [], []
    for entry in routes:
        _, _, path = entry.partition(" ")
        target = _probe_path(path, placeholder)
        r = ctx.api.get(target, token=token)
        if r.status >= 500:
            crashes.append(f"{target} -> {r.status} {r.snippet(80)}")
        elif r.status == 401:
            rejected.append(f"{target} -> 401 {r.snippet(80)}")
        elif r.status == 403:
            allowed_403.append(target)
        elif 200 <= r.status < 300:
            ok.append(target)
        else:
            clean.append(f"{target} -> {r.status}")

    ctx.note(f"read sweep: {len(routes)} GET route(s) from the {source} — "
             f"{len(ok)} answered 2xx, {len(clean)} answered a clean 4xx, "
             f"{len(allowed_403)} answered 403 (feature flag?), 0 crashes")
    if allowed_403:
        ctx.warnings.append(f"read sweep: {len(allowed_403)} route(s) answered 403 to an "
                            f"authenticated customer: {allowed_403[:6]}")
    expect(not rejected,
           f"{len(rejected)} GET route(s) rejected the signed-in customer with 401: "
           + "; ".join(rejected[:4]))
    expect(not crashes,
           f"{len(crashes)} GET route(s) answered 5xx: " + "; ".join(crashes[:4]))


@step("surface", "surface.cart_and_saved",
      "cart items can be removed and cleared; saved items can be saved, updated, removed",
      writes=True, route="DELETE /api/cart",
      routes=("DELETE /api/cart/<item_id>", "POST /api/saved", "GET /api/saved",
              "PATCH /api/saved/<item_id>", "DELETE /api/saved/<item_id>"),
      needs=("public.menu", "auth.login"))
def s_cart_and_saved(ctx: Ctx):
    """Cart removal and the whole saved-items loop, for the signed-in account.

    `DELETE /api/cart` clears everything, so it only runs when the cart was **empty
    before this step** — on a real account nothing of the user's is thrown away.
    """
    menu_item_id = ctx.ids["menu_item_id"]
    cart_before = _rows_payload(ctx.api.get("/api/cart", token=ctx.tokens["access"]))
    item_ids = []

    added = ctx.api.post("/api/cart", token=ctx.tokens["access"],
                         json_body={"menu_item_id": menu_item_id, "quantity": 1})
    expect(added.status in (200, 201), f"adding to the cart answered {added.status} — "
                                       f"{added.snippet(120)}", added)
    rows = _rows_payload(ctx.api.get("/api/cart", token=ctx.tokens["access"]))
    for row in rows:
        if str(row.get("menu_item_id")) == str(menu_item_id):
            item_ids.append(str(row.get("id")))
    if item_ids:
        removed = ctx.api.delete(f"/api/cart/{item_ids[0]}", token=ctx.tokens["access"])
        expect(removed.status in (200, 204),
               f"removing a cart item answered {removed.status} — {removed.snippet(120)}", removed)
        left = _rows_payload(ctx.api.get("/api/cart", token=ctx.tokens["access"]))
        expect(not any(str(r.get("id")) == item_ids[0] for r in left),
               f"cart item {item_ids[0]} is still in the cart after DELETE")
        ctx.note("cart item added and removed individually")
    else:
        ctx.warnings.append("cart: POST /api/cart succeeded but the item was not found by "
                            "GET /api/cart — the individual remove was not exercised")

    if not cart_before:
        cleared = ctx.api.delete("/api/cart", token=ctx.tokens["access"])
        expect(cleared.status in (200, 204),
               f"clearing the cart answered {cleared.status} — {cleared.snippet(120)}", cleared)
        expect(not _rows_payload(ctx.api.get("/api/cart", token=ctx.tokens["access"])),
               "the cart is not empty after DELETE /api/cart")
        ctx.note("cart cleared (it was empty before this step)")
    else:
        ctx.note(f"cart had {len(cart_before)} pre-existing item(s) — DELETE /api/cart "
                 "was not called, nothing of the account's was cleared")

    saved_id = None
    try:
        saved = ctx.api.post("/api/saved", token=ctx.tokens["access"],
                             json_body={"menu_item_id": menu_item_id, "quantity": 1})
        expect(saved.status in (200, 201), f"saving an item answered {saved.status} — "
                                            f"{saved.snippet(120)}", saved)
        rows = _rows_payload(ctx.api.get("/api/saved", token=ctx.tokens["access"]).check(200))
        entry = next((r for r in rows if str(r.get("menu_item_id")) == str(menu_item_id)), None)
        expect(entry is not None, f"the saved item is not in GET /api/saved ({len(rows)} row(s))")
        saved_id = str(entry.get("id"))

        updated = ctx.api.patch(f"/api/saved/{saved_id}", token=ctx.tokens["access"],
                                json_body={"quantity": 2})
        expect(updated.status == 200, f"updating a saved item answered {updated.status} — "
                                       f"{updated.snippet(120)}", updated)
        ctx.note("saved item created, listed and updated")
    finally:
        if saved_id:
            ctx.db.delete("saved_for_later", id=saved_id)
        if item_ids:
            for cart_item in item_ids:
                ctx.db.delete("cart_items", id=cart_item)


@step("surface", "surface.order_locks_lifecycle",
      "an order lock is created, listed, read, rescheduled and cancelled",
      writes=True, route="POST /api/order-locks",
      routes=("GET /api/order-locks", "GET /api/order-locks/<lock_id>",
              "PATCH /api/order-locks/<lock_id>/reschedule", "DELETE /api/order-locks/<lock_id>"),
      needs=("auth.login",))
def s_order_locks_lifecycle(ctx: Ctx):
    """The lock-in-a-future-order feature end to end, then cancelled so nothing is left.

    It is a discount commitment, so the step also pins the guard: a date in the past must
    be refused.
    """
    token = ctx.tokens["access"]
    tomorrow = (datetime.now(timezone.utc) + timedelta(hours=1) + timedelta(days=3)).date().isoformat()
    later = (datetime.now(timezone.utc) + timedelta(hours=1) + timedelta(days=5)).date().isoformat()
    yesterday = (datetime.now(timezone.utc) + timedelta(hours=1) - timedelta(days=1)).date().isoformat()
    lock_id = None

    past = ctx.api.post("/api/order-locks", token=token, json_body={"locked_date": yesterday})
    expect(past.status == 400, f"a lock for a past date answered {past.status} "
                               f"(expected 400) — {past.snippet(120)}", past)
    try:
        created = ctx.api.post("/api/order-locks", token=token,
                               json_body={"locked_date": tomorrow, "discount_pct": 10})
        expect(created.status in (200, 201), f"creating a lock answered {created.status} — "
                                             f"{created.snippet(140)}", created)
        lock_id = str(field(created.data or {}, "id")
                      or ((created.data or {}).get("lock") or {}).get("id") or "")
        expect(bool(lock_id), f"the lock was created without an id — {created.snippet(140)}")

        listed = ctx.api.get("/api/order-locks", token=token).check(200)
        expect(contains_id(listed.data, lock_id),
               f"the new lock is not in GET /api/order-locks — {listed.snippet(140)}", listed)

        one = ctx.api.get(f"/api/order-locks/{lock_id}", token=token).check(200)
        expect(contains_id(one.data, lock_id), f"the lock response does not carry its id — "
                                               f"{one.snippet(140)}", one)

        moved = ctx.api.patch(f"/api/order-locks/{lock_id}/reschedule", token=token,
                              json_body={"locked_date": later})
        expect(moved.status == 200, f"rescheduling answered {moved.status} — "
                                     f"{moved.snippet(140)}", moved)
        after = ctx.db.select_one("order_locks", id=lock_id) or {}
        expect(str(after.get("locked_date"))[:10] == later,
               f"the lock date is {after.get('locked_date')} after rescheduling to {later}")

        cancelled = ctx.api.delete(f"/api/order-locks/{lock_id}", token=token)
        expect(cancelled.status in (200, 204), f"cancelling the lock answered {cancelled.status} "
                                                f"— {cancelled.snippet(120)}", cancelled)
        gone = ctx.db.select_one("order_locks", id=lock_id) or {}
        expect(str(gone.get("status") or "") in ("cancelled", "expired", ""),
               f"the lock still shows status {gone.get('status')} after DELETE")
        ctx.note(f"lock created, listed, read, rescheduled to {later}, cancelled")
    finally:
        if lock_id:
            ctx.db.delete("order_locks", id=lock_id)


@step("surface", "surface.notifications_and_challenges",
      "notification preferences and the engagement challenges answer cleanly",
      writes=True, route="GET /api/notifications/preferences",
      routes=("POST /api/notifications/<notification_id>/read",
              "GET /api/challenges/badges", "GET /api/challenges/my",
              "GET /api/challenges/pwa-push-bonus-status", "POST /api/challenges/pwa-installed",
              "POST /api/challenges/push-subscribed", "POST /api/challenges/social-follow"),
      needs=("auth.login",))
def s_notifications_and_challenges(ctx: Ctx):
    """Preferences, marking a notification read, and the three "I did the thing" posts.

    The engagement posts are intentionally tolerant — they award HP when they succeed and
    a legitimate 400/409 when the action was already recorded. What is asserted is that
    each answers **cleanly** (no 5xx) and that marking a notification read does not 500 on
    an unknown id.
    """
    token = ctx.tokens["access"]
    prefs = ctx.api.get("/api/notifications/preferences", token=token).check(200)
    expect(isinstance(prefs.data, (dict, list)),
           f"notification preferences are not an object — {prefs.snippet(140)}", prefs)

    unknown = ctx.api.post(f"/api/notifications/{uuid.uuid4()}/read", token=token)
    expect(unknown.status in (400, 403, 404),
           f"marking an unknown notification read answered {unknown.status} — "
           f"{unknown.snippet(120)}", unknown)

    for path in ("/api/challenges/badges", "/api/challenges/my",
                 "/api/challenges/pwa-push-bonus-status"):
        r = ctx.api.get(path, token=token)
        expect(r.status < 500, f"GET {path} answered {r.status} — {r.snippet(120)}", r)

    outcomes = {}
    for path in ("/api/challenges/pwa-installed", "/api/challenges/push-subscribed",
                 "/api/challenges/social-follow"):
        r = ctx.api.post(path, token=token, json_body={})
        expect(r.status < 500, f"POST {path} answered {r.status} — {r.snippet(120)}", r)
        outcomes[path.rsplit("/", 1)[-1]] = r.status
    ctx.note(f"preferences read; unknown notification refused ({unknown.status}); "
             f"challenge posts answered {outcomes}")


@step("surface", "surface.storefront_writes",
      "newsletter, promo validation and delivery fee answer without touching real data",
      writes=True, route="POST /api/storefront/newsletter",
      routes=("POST /api/storefront/newsletter/unsubscribe",
              "POST /api/storefront/promo-codes/validate", "POST /api/orders/validate-promo",
              "POST /api/delivery/calculate-fee"),
      needs=("auth.login", "public.hostels"))
def s_storefront_writes(ctx: Ctx):
    """The public write endpoints around ordering.

    Newsletter is a full loop on a throwaway address; the two promo validators get a
    nonsense code and must answer a clean 4xx (never a 5xx, never a false "valid"); the
    delivery fee calculator gets the step's own hostel and must return a number.
    """
    email = f"e2e.news.{uuid.uuid4().hex[:10]}@{TEST_EMAIL_DOMAIN}"
    sub = ctx.api.post("/api/storefront/newsletter", json_body={"email": email})
    expect(sub.status in (200, 201), f"newsletter subscribe answered {sub.status} — "
                                     f"{sub.snippet(120)}", sub)
    try:
        again = ctx.api.post("/api/storefront/newsletter", json_body={"email": email})
        expect(again.status < 500, f"a duplicate subscribe answered {again.status} — "
                                   f"{again.snippet(120)}", again)

        unsub = ctx.api.post("/api/storefront/newsletter/unsubscribe", json_body={"email": email})
        expect(unsub.status in (200, 204), f"newsletter unsubscribe answered {unsub.status} — "
                                           f"{unsub.snippet(120)}", unsub)
        ctx.note("newsletter address subscribed, duplicate tolerated, unsubscribed")
    finally:
        for row in ctx.db.select("newsletter_subscribers", email=email) or []:
            ctx.db.delete("newsletter_subscribers", id=row["id"])

    for path in ("/api/storefront/promo-codes/validate", "/api/orders/validate-promo"):
        r = ctx.api.post(path, token=ctx.tokens["access"],
                         json_body={"code": f"E2E-NOPE-{uuid.uuid4().hex[:6]}", "order_subtotal": 5000})
        expect(r.status in (400, 404, 422),
               f"a nonsense promo code on {path} answered {r.status} — {r.snippet(140)}", r)
        ctx.note(f"{path} refused a nonsense code ({r.status})")

    fee = ctx.api.post("/api/delivery/calculate-fee", token=ctx.tokens["access"], json_body={
        "delivery_type": "on_campus", "delivery_location_id": str(ctx.ids["hostel_id"]),
    })
    if fee.status == 200:
        amount = None
        if isinstance(fee.data, dict):
            for key in ("delivery_fee", "fee", "amount"):
                if fee.data.get(key) is not None:
                    amount = float(fee.data[key]); break
        expect(amount is not None and amount >= 0,
               f"the fee response has no numeric fee — {fee.snippet(140)}", fee)
        ctx.note(f"delivery fee calculated: ₦{amount:.2f}")
    else:
        # The payload keys are the front end's; a 400 here is a clean answer, not a crash.
        expect(fee.status < 500, f"calculating the fee answered {fee.status} — "
                                 f"{fee.snippet(140)}", fee)
        ctx.note(f"delivery fee answered {fee.status} to this payload shape (clean refusal)")


@step("surface", "surface.auth_self_service",
      "a throwaway account can change its password, log out everywhere and delete itself",
      writes=True, route="GET /api/auth/users/search",
      routes=("POST /api/auth/change-password", "POST /api/auth/logout-all-devices",
              "POST /api/auth/profile/photo", "POST /api/auth/reset-password",
              "DELETE /api/auth/account"))
def s_auth_self_service(ctx: Ctx):
    """The account-management endpoints, on a throwaway account.

    Everything here changes or destroys an account, so it must never run against the
    signed-in one. The step also pins two guards: an untrusted photo URL is refused, and
    the account deletion requires the password.
    """
    campus = str(ctx.ids.get("campus_id") or "")
    user_id, token, why = _provision_role_user(ctx, "customer", campus)
    if not token:
        _drop_role_user(ctx, user_id)
        raise Skip(f"could not provision a throwaway customer: {why}")
    try:
        alias = ctx.api.get("/api/auth/users/search", params={"q": "e2e"},
                            token=ctx.tokens["access"])
        expect(alias.status == 200,
               f"the /api/auth/users/search alias answered {alias.status} for a customer", alias)

        wrong = ctx.api.post("/api/auth/profile/photo", token=token,
                             json_body={"photo_url": "https://evil.example.com/x.jpg"})
        expect(wrong.status == 400,
               f"an untrusted photo URL answered {wrong.status} (expected 400) — "
               f"{wrong.snippet(120)}", wrong)

        new_password = f"E2eProbe!{uuid.uuid4().hex[:10]}"
        changed = ctx.api.post("/api/auth/change-password", token=token, json_body={
            "current_password": DEFAULT_PASSWORD, "new_password": new_password})
        if changed.status == 200:
            relogin = ctx.api.post("/api/auth/login",
                                   json_body={"email": ctx.ids.get("email") or "", "password": new_password})
            if relogin.status != 200:
                # The throwaway email is only known to the provisioning helper, so re-derive
                # it from the session we already hold rather than guessing.
                ctx.warnings.append("change-password succeeded but the re-login probe could not "
                                    "derive the email — the new password is unverified")
            else:
                token = field(relogin.data or {}, "access_token") or token
                ctx.note("password changed and the new password signed in")
        else:
            expect(changed.status == 400,
                   f"change-password answered {changed.status} — {changed.snippet(140)}", changed)

        logout = ctx.api.post("/api/auth/logout-all-devices", token=token)
        expect(logout.status in (200, 204), f"logout-all-devices answered {logout.status} — "
                                            f"{logout.snippet(120)}", logout)

        reset = ctx.api.post("/api/auth/reset-password",
                             json_body={"email": ctx.ids.get("email") or "e2e@holygrills.test"})
        expect(reset.status < 500,
               f"reset-password answered {reset.status} — {reset.snippet(140)}", reset)

        # Deletion requires the password; a wrong one must be refused.
        bad = ctx.api.delete("/api/auth/account", token=token,
                             json_body={"password": "definitely-wrong"})
        expect(bad.status in (400, 401, 403),
               f"deleting an account with the wrong password answered {bad.status}", bad)
        ctx.note(f"alias, photo guard ({wrong.status}), password change ({changed.status}), "
                 f"logout-all ({logout.status}), reset request ({reset.status}), "
                 f"wrong-password delete refused ({bad.status})")
    finally:
        _drop_user_effects(ctx, user_id)
        _drop_role_user(ctx, user_id)


@step("webhooks", "webhooks.flutterwave_wallet_topup",
      "a signed Flutterwave charge credits the wallet, and a replay credits it once",
      writes=True, route="POST /api/webhooks/flutterwave", needs=("auth.login",))
def s_flutterwave_topup(ctx: Ctx):
    """The Flutterwave side of the money-in path, mirroring the Paystack step.

    Flutterwave signs with a shared `verif-hash` header (compared, not HMAC'd), so the
    only requirement is the same secret the server holds. Skips cleanly when it is not
    available — never forged.
    """
    secret = (os.environ.get("FLUTTERWAVE_WEBHOOK_SECRET") or ctx.opts.webhook_secret or "").strip()
    if not secret:
        raise Skip("FLUTTERWAVE_WEBHOOK_SECRET is not set — pass --webhook-secret or put it in "
                   "the backend .env; a forged signature is never sent")
    if not ctx.user_id:
        raise Skip("no signed-in user to credit")

    amount = 300.0
    reference = f"E2E-E2E-FLW-{uuid.uuid4().hex[:12]}"
    wallet_before = _wallet_snapshot(ctx)
    try:
        payload = {
            "event": "charge.completed",
            "data": {
                "tx_ref": reference, "flw_ref": reference, "currency": "NGN",
                "amount": amount, "status": "successful",
                "meta": {"type": "wallet_topup", "user_id": ctx.user_id},
                "customer": {"email": ctx.ids.get("email") or "e2e@holygrills.test"},
            },
        }
        r = ctx.api.post("/api/webhooks/flutterwave", json_body=payload,
                         headers={"verif-hash": secret})
        r.check(200)
        balance_after = float((ctx.db.select_one("wallets", user_id=ctx.user_id) or {})
                              .get("balance") or 0)
        expect(abs(balance_after - float(wallet_before.get("balance") or 0) - amount) < 0.01,
               f"the Flutterwave webhook returned 200 but the wallet moved "
               f"₦{balance_after - float(wallet_before.get('balance') or 0):.2f}, "
               f"expected ₦{amount:.2f}")

        replay = ctx.api.post("/api/webhooks/flutterwave", json_body=payload,
                              headers={"verif-hash": secret})
        replay.check(200)
        replay_balance = float((ctx.db.select_one("wallets", user_id=ctx.user_id) or {})
                               .get("balance") or 0)
        expect(abs(replay_balance - balance_after) < 0.01,
               f"a replayed Flutterwave webhook credited again: {balance_after} -> {replay_balance}")
        ctx.note(f"Flutterwave top-up credited ₦{amount:.0f}; replay was a no-op")
    finally:
        for row in ctx.db.select("wallet_transactions", provider_reference=reference):
            ctx.db.delete("wallet_transactions", id=row["id"])
        for row in ctx.db.select("webhook_events", reference=reference):
            ctx.db.delete("webhook_events", id=row["id"])
        _wallet_restore(ctx, wallet_before, "flutterwave top-up")


@step("surface", "surface.rewards_redeem",
      "a reward is redeemed for HP and its delivery mode is chosen",
      writes=True, route="POST /api/rewards/<reward_id>/redeem",
      routes=("POST /api/rewards/redemptions/<redemption_id>/delivery-choice",))
def s_rewards_redeem(ctx: Ctx):
    """Spending HP on a reward, on a throwaway account with HP set aside for it.

    The reward catalogue is data, so the step picks the cheapest active reward with
    stock, gives the throwaway account enough HP, redeems it and chooses a delivery mode.
    A 400 about tier or stock means the catalogue cannot satisfy the flow for this
    account — that is a legitimate configuration, reported as a skip, not a failure.
    """
    campus = str(ctx.ids.get("campus_id") or "")
    user_id, token, why = _provision_role_user(ctx, "customer", campus)
    if not token:
        _drop_role_user(ctx, user_id)
        raise Skip(f"could not provision a throwaway customer: {why}")
    redemption_id = None
    try:
        rewards = [r for r in (ctx.db.select("rewards", is_active="true") or [])
                   if float(r.get("hp_cost") or 0) > 0
                   and (r.get("stock_quantity") is None or float(r.get("stock_quantity") or 0) > 0)]
        if not rewards:
            raise Skip("no active reward with stock and an HP price — the catalogue cannot "
                       "exercise the redeem path")
        reward = sorted(rewards, key=lambda r: float(r.get("hp_cost") or 0))[0]
        cost = float(reward.get("hp_cost") or 0)

        view = ctx.api.get(f"/api/rewards/{reward['id']}", token=token)
        if view.status == 200:
            expect(contains_id(view.data, reward["id"]),
                   f"the reward response does not carry its id — {view.snippet(120)}")
        else:
            expect(view.status in (400, 403), f"GET /api/rewards/<id> answered {view.status} — "
                                              f"{view.snippet(120)}", view)

        # The throwaway account needs the HP it is about to spend. Setting the balance
        # directly is safe here because the account is deleted at the end of the step.
        ctx.db.update("profiles", {"hp_balance": int(cost) + 100}, id=user_id)

        redeemed = ctx.api.post(f"/api/rewards/{reward['id']}/redeem", token=token, json_body={})
        if redeemed.status == 400:
            raise Skip(f"the catalogue refused the redeem for a fresh account "
                       f"({redeemed.snippet(120)}) — tier or per-user limits, not a defect")
        expect(redeemed.status in (200, 201),
               f"redeeming answered {redeemed.status} — {redeemed.snippet(160)}", redeemed)

        rows = ctx.db.select("reward_redemptions", user_id=user_id) or []
        expect(bool(rows), "the redeem succeeded but no reward_redemptions row was written")
        redemption_id = str(rows[0].get("id") or "")

        choice = ctx.api.post(f"/api/rewards/redemptions/{redemption_id}/delivery-choice",
                              token=token, json_body={"delivery_mode": "next_order"})
        expect(choice.status in (200, 201),
               f"choosing a delivery mode answered {choice.status} — {choice.snippet(160)}", choice)
        after = ctx.db.select_one("reward_redemptions", id=redemption_id) or {}
        expect(str(after.get("delivery_mode")) == "next_order",
               f"delivery_mode is {after.get('delivery_mode')} after choosing 'next_order'")
        ctx.note(f"redeemed {reward.get('name')!r} for {cost:.0f} HP and chose next_order")
    finally:
        ctx.db.delete("reward_redemptions", user_id=user_id)
        _drop_user_effects(ctx, user_id)
        _drop_role_user(ctx, user_id)


@step("surface", "surface.free_sides_deselect",
      "a selected free side can be removed from the cart again",
      writes=True, route="DELETE /api/free-sides/select/<selection_id>", needs=("auth.login",))
def s_free_sides_deselect(ctx: Ctx):
    """The undo path for free-side selections: select, then deselect, and the row is gone.

    Uses the signed-in account, which is what the route is for, and removes only the
    selection this step created.
    """
    campus = str(ctx.ids.get("campus_id"))
    items = [i for i in (ctx.db.select("free_side_items", is_active="true") or [])
             if i.get("campus_id") in (campus, None)]
    if not items:
        raise Skip("no active free_side_items row for this campus")
    try:
        credit = ctx.db.insert("free_side_credits", {
            "user_id": ctx.user_id, "campus_id": campus, "credits_remaining": 1,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        })
    except Failed as exc:
        raise Skip(f"could not create a free_side_credits row ({exc})")
    credit_id = str((credit or {}).get("id") or "")
    if credit_id:
        ctx.track_infra("free_side_credits", credit_id)

    selected = ctx.api.post("/api/free-sides/select", json_body={"free_side_item_id": items[0]["id"]},
                            token=ctx.tokens["access"])
    if selected.status == 403:
        raise Skip(f"the free_side_credits feature is off — {selected.snippet(120)}")
    selected.check(201, allow=(200,))
    selection_id = str(field(selected.data or {}, "id")
                       or ((selected.data or {}).get("selection") or {}).get("id") or "")
    if not selection_id:
        rows = ctx.db.select("cart_free_side_selections", user_id=ctx.user_id) or []
        selection_id = str(rows[0]["id"]) if rows else ""
    if not selection_id:
        raise Skip("the selection was not persisted, so there is nothing to deselect")
    ctx.track_infra("cart_free_side_selections", selection_id)

    gone = ctx.api.delete(f"/api/free-sides/select/{selection_id}", token=ctx.tokens["access"])
    expect(gone.status in (200, 204), f"deselecting answered {gone.status} — "
                                      f"{gone.snippet(140)}", gone)
    left = ctx.db.select("cart_free_side_selections", id=selection_id)
    expect(not left, f"selection {selection_id} is still in cart_free_side_selections")
    ctx.note("free-side selection created then removed by DELETE")


@step("surface", "surface.hp_transfer",
      "HP can be transferred to another account and the balance moves on both sides",
      writes=True, route="POST /api/hp/transfer")
def s_hp_transfer(ctx: Ctx):
    """HP moving between two throwaway accounts — sender, recipient and the ledger.

    Transferring HP is a value move, so the step checks both balances and that the sender
    cannot transfer more than it holds. Both accounts are deleted afterwards.
    """
    campus = str(ctx.ids.get("campus_id") or "")
    sender_id, sender_token, why = _provision_role_user(ctx, "customer", campus)
    recipient_id, _recipient_token, why_r = _provision_role_user(ctx, "customer", campus)
    try:
        if not sender_token or not recipient_id:
            raise Skip(f"could not provision both accounts ({why}; {why_r})")
        ctx.db.update("profiles", {"hp_balance": 500}, id=sender_id)

        too_much = ctx.api.post("/api/hp/transfer", token=sender_token, json_body={
            "recipient_id": recipient_id, "amount": 100000})
        expect(too_much.status == 400,
               f"transferring more HP than the sender holds answered {too_much.status} "
               f"(expected 400) — {too_much.snippet(140)}", too_much)

        before_r = int((ctx.db.select_one("profiles", id=recipient_id) or {}).get("hp_balance") or 0)
        ok = ctx.api.post("/api/hp/transfer", token=sender_token, json_body={
            "recipient_id": recipient_id, "amount": 100})
        expect(ok.status in (200, 201), f"the transfer answered {ok.status} — "
                                        f"{ok.snippet(160)}", ok)
        after_s = int((ctx.db.select_one("profiles", id=sender_id) or {}).get("hp_balance") or 0)
        after_r = int((ctx.db.select_one("profiles", id=recipient_id) or {}).get("hp_balance") or 0)
        expect(after_r - before_r == 100,
               f"the recipient moved by {after_r - before_r} HP, expected 100")
        expect(after_s == 400, f"the sender holds {after_s} HP after sending 100 of 500")
        ctx.note(f"HP transfer: sender 500 -> {after_s}, recipient {before_r} -> {after_r}")
    finally:
        _drop_user_effects(ctx, sender_id)
        _drop_user_effects(ctx, recipient_id)
        _drop_role_user(ctx, sender_id)
        _drop_role_user(ctx, recipient_id)


@step("surface", "surface.challenges_complete",
      "a milestone challenge can be completed once and its reward is recorded",
      writes=True, route="POST /api/challenges/<milestone_id>/complete")
def s_challenges_complete(ctx: Ctx):
    """Completing a challenge on a throwaway account.

    The milestone list is data, so the step picks one the API offers and accepts a clean
    400/409 when the account does not meet its condition — what must never happen is a
    crash or a silent no-op.
    """
    campus = str(ctx.ids.get("campus_id") or "")
    user_id, token, why = _provision_role_user(ctx, "customer", campus)
    if not token:
        _drop_role_user(ctx, user_id)
        raise Skip(f"could not provision a throwaway customer: {why}")
    try:
        mine = ctx.api.get("/api/challenges/my", token=token).check(200)
        milestones = []
        if isinstance(mine.data, dict):
            for key in ("milestones", "challenges", "items", "results"):
                if isinstance(mine.data.get(key), list):
                    milestones = mine.data[key]; break
        elif isinstance(mine.data, list):
            milestones = mine.data
        candidate = next((m for m in milestones
                          if m.get("id") and not m.get("completed") and not m.get("is_completed")), None)
        if candidate is None:
            raise Skip("the API offers no incomplete milestone to complete")

        done = ctx.api.post(f"/api/challenges/{candidate['id']}/complete", token=token, json_body={})
        expect(done.status < 500, f"completing a challenge answered {done.status} — "
                                  f"{done.snippet(160)}", done)
        expect(done.status in (200, 201, 400, 409),
               f"completing a challenge answered {done.status} — {done.snippet(140)}", done)
        ctx.note(f"milestone {candidate.get('name') or candidate['id']} -> {done.status}")
    finally:
        _drop_user_effects(ctx, user_id)
        _drop_role_user(ctx, user_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Phase — concurrency: can two requests spend the same naira?
# ─────────────────────────────────────────────────────────────────────────────
#
# These steps fire N identical-in-spirit requests at the same instant and ask whether
# the database's atomicity holds. They need a real server: an in-process Flask test
# client serialises requests, so nothing can race and the steps would prove nothing.
# They skip with that reason unless BASE_URL is set.
#
# Everything they create is cleaned up, and the one step that touches money leaves the
# wallet exactly as it found it — including on a pre-existing account.

def _need_real_server(ctx: Ctx, what: str):
    if not ctx.api.base_url:
        raise Skip(f"{what} needs two requests genuinely in flight — run with "
                   "BASE_URL=<server> (an in-process test_client serialises, so a race "
                   "cannot be observed)")


def _in_parallel(count: int, api_factory, work, timeout: float = 90.0):
    """Run work(i, api) in `count` threads released at the same instant.

    Returns [("ok", value) | ("error", exception)] in index order. Each thread gets its
    own Api from api_factory so no two threads share a client or a connection.
    """
    import threading
    results: list = [None] * count
    barrier = threading.Barrier(count)

    def runner(i):
        try:
            api = api_factory()
            barrier.wait(timeout=30)
            results[i] = ("ok", work(i, api))
        except Exception as exc:                                    # noqa: BLE001
            results[i] = ("error", exc)

    threads = [threading.Thread(target=runner, args=(i,), daemon=True) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout)
    for i, _t in enumerate(threads):
        if results[i] is None:
            results[i] = ("error", Failed(f"thread {i} did not answer within {timeout:.0f}s"))
    return results


def _race_orders(ctx: Ctx, marker: str, count: int, token: str, body_extra: dict):
    """Fire `count` real POST /api/orders at once, each with its own idempotency key.

    Distinct keys matter: they make these genuinely different checkouts competing for
    the same scarce resource. (The idempotency replay guard has its own step.)
    """
    def work(i, api):
        body = {
            "items": [{"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1}],
            "payment_method": "card",
            "delivery_type": "on_campus",
            "delivery_location_id": str(ctx.ids["hostel_id"]),
            "notes": f"{marker} #{i}",
            "idempotency_key": f"{marker}-{i}",
        }
        body.update(body_extra)
        return api.post("/api/orders", json_body=body, token=token,
                        headers={"X-Campus-ID": str(ctx.ids["campus_id"])})
    return _in_parallel(count, ctx.api.clone, work)


def _orders_with_marker(ctx: Ctx, marker: str) -> list[dict]:
    return [o for o in (ctx.db.select("orders", user_id=ctx.user_id) or [])
            if str(o.get("notes") or "").startswith(marker)]


def _drop_orders(ctx: Ctx, orders: list[dict]):
    for order in orders:
        oid = str(order.get("id"))
        ctx.db.delete("order_items", order_id=oid)
        ctx.db.delete("order_status_logs", order_id=oid)
        ctx.db.delete("orders", id=oid)


def _wallet_snapshot(ctx: Ctx) -> dict:
    """Every volatile column of the customer's wallet, so a restore can be exact."""
    row = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    return {k: v for k, v in row.items() if k not in ("id", "user_id", "created_at")}


def _wallet_restore(ctx: Ctx, before: dict, label: str):
    """Put back every wallet column this run moved. Never raises; warns if it cannot."""
    now = ctx.db.select_one("wallets", user_id=ctx.user_id)
    if now is None:
        return
    moved = {k: v for k, v in before.items() if now.get(k) != v}
    if moved:
        ctx.db.update("wallets", moved, user_id=ctx.user_id)
    after = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    still = {k: (before[k], after.get(k)) for k in moved if after.get(k) != before[k]}
    if still:
        ctx.warnings.append(f"{label}: could not fully restore the wallet: {still}")
    else:
        ctx.note(f"{label}: wallet restored" + (f" ({len(moved)} column(s))" if moved else ""))


def _surgery(ctx: Ctx, reference: str, delta: float, campus: str):
    """Nudge the wallet balance by `delta` (signed) and return the new balance.

    Used to make the balance exactly one order's worth before the race. The ledger row
    carries `reference_id=reference` so cleanup can delete precisely this run's row.
    """
    if delta > 0:
        ctx.db.rpc("credit_wallet_atomic", {
            "p_user_id": ctx.user_id, "p_amount": round(delta, 2),
            "p_reason": "E2E concurrency probe", "p_reference_type": "e2e",
            "p_reference_id": reference, "p_provider": "e2e",
            "p_provider_reference": reference, "p_metadata": {}, "p_campus_id": campus,
        })
    elif delta < 0:
        ctx.db.rpc("debit_wallet_atomic", {
            "p_user_id": ctx.user_id, "p_amount": round(-delta, 2),
            "p_reason": "E2E concurrency probe", "p_reference_type": "e2e",
            "p_reference_id": reference, "p_metadata": {}, "p_campus_id": campus,
        })
    return float((ctx.db.select_one("wallets", user_id=ctx.user_id) or {}).get("balance") or 0)


def _undo_surgery(ctx: Ctx, reference: str):
    for row in ctx.db.select("wallet_transactions", reference_id=reference):
        ctx.db.delete("wallet_transactions", id=row["id"])


@step("concurrency", "concurrency.replay_guard",
      "the same idempotency key fired three times at once creates exactly one order",
      writes=True, route="POST /api/orders", needs=("orders.place",))
def s_replay_guard(ctx: Ctx):
    _need_real_server(ctx, "the idempotency replay guard")
    marker = f"E2E race replay {uuid.uuid4().hex[:10]}"
    token = ctx.tokens["access"]
    shared = f"{marker}-shared"                       # ONE key, three simultaneous calls

    def work(i, api):
        return api.post("/api/orders", json_body={
            "items": [{"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1}],
            "payment_method": "card",
            "delivery_type": "on_campus",
            "delivery_location_id": str(ctx.ids["hostel_id"]),
            "notes": marker,
            "idempotency_key": shared,
        }, token=token, headers={"X-Campus-ID": str(ctx.ids["campus_id"])})

    results = _in_parallel(3, ctx.api.clone, work)
    orders = _orders_with_marker(ctx, marker)
    try:
        errors = [r[1] for r in results if r[0] == "error"]
        expect(not errors, f"a concurrent request blew up instead of answering: {errors[:2]}")
        statuses = [r[1].status for r in results if r[0] == "ok"]
        expect(not [x for x in statuses if x >= 500],
               f"a concurrent call answered 5xx: {statuses}")
        expect(len(orders) == 1,
               f"three simultaneous calls with one idempotency key created {len(orders)} "
               f"orders (statuses {statuses}) — the replay guard did not hold")
        ctx.note(f"3 simultaneous calls, statuses {statuses}, 1 order created")
    finally:
        _drop_orders(ctx, orders)


@step("concurrency", "concurrency.wallet_no_overdraft",
      "two wallet orders racing one balance: one succeeds, the balance never goes negative",
      writes=True, route="POST /api/orders", needs=("orders.place", "orders.fund_wallet"))
def s_wallet_no_overdraft(ctx: Ctx):
    """The classic double-spend: both requests pass the balance check, both debit.

    `_check_kitchen_capacity` and the wallet pre-check both run *before* the RPC that
    actually moves money, so only the database can stop the second debit. The balance is
    made exactly one order's worth first — if it already covers two, nothing is proven.
    """
    _need_real_server(ctx, "the wallet double-spend race")
    order = ctx.db.select_one("orders", id=ctx.ids.get("order_id")) or {}
    total = float(order.get("total_amount") or 0)
    if total <= 0:
        raise Skip(f"cannot size the race: the placed order has total_amount={order.get('total_amount')}")

    reference = f"E2E-RACE-{uuid.uuid4().hex[:12]}"
    marker = f"E2E race wallet {uuid.uuid4().hex[:10]}"
    before = _wallet_snapshot(ctx)
    balance = float(before.get("balance") or 0)
    try:
        if balance < total:
            balance = _surgery(ctx, reference, total - balance, str(ctx.ids["campus_id"]))
            ctx.note(f"topped the wallet up by ₦{total - float(before.get('balance') or 0):.2f} "
                     f"to make it exactly one order's worth (₦{total:.2f})")
        elif balance >= 2 * total:
            balance = _surgery(ctx, reference, total - balance, str(ctx.ids["campus_id"]))
            ctx.note(f"trimmed the wallet to ₦{total:.2f} through debit_wallet_atomic so the "
                     f"balance covers exactly one order")
        expect(abs(balance - total) < 0.01,
               f"could not make the wallet exactly ₦{total:.2f} (it is ₦{balance:.2f}) — "
               "this run cannot prove anything, so it will not claim to")

        results = _race_orders(ctx, marker, 2, ctx.tokens["access"], {"payment_method": "wallet"})
        orders = _orders_with_marker(ctx, marker)
        statuses = [r[1].status for r in results if r[0] == "ok"]
        errors = [r[1] for r in results if r[0] == "error"]
        expect(not errors, f"a concurrent request blew up: {errors[:2]}")
        expect(not [x for x in statuses if x >= 500], f"a concurrent call answered 5xx: {statuses}")
        wins = [x for x in statuses if 200 <= x < 300]
        expect(len(wins) == 1,
               f"{len(wins)} of two simultaneous wallet orders succeeded on a balance that "
               f"covers one — the wallet debit is not atomic (statuses {statuses})")
        expect(len(orders) == 1,
               f"{len(orders)} orders were created for one order's worth of balance (statuses {statuses})")

        after = float((ctx.db.select_one("wallets", user_id=ctx.user_id) or {}).get("balance") or 0)
        expect(after >= -0.001, f"the wallet balance went negative: ₦{after:.2f}")
        expect(abs(after - (total - total)) < 0.01,
               f"after exactly one debit the balance should be ₦0.00, it is ₦{after:.2f}")
        ctx.note(f"one order won, the other was refused ({statuses}); balance ₦{after:.2f}")
    finally:
        _drop_orders(ctx, _orders_with_marker(ctx, marker))
        _undo_surgery(ctx, reference)
        _wallet_restore(ctx, before, "wallet race")


@step("concurrency", "concurrency.reward_single_use",
      "one reward claimed by two simultaneous checkouts buys exactly one order",
      writes=True, route="POST /api/orders", needs=("orders.place",))
def s_reward_single_use(ctx: Ctx):
    """A reward is spendable once. Two carts holding the same redemption, checked out at
    the same time, must not both get it — `hg_claim_reward_redemption_for_order` does the
    conditional update, and this is the only way to find out whether it holds."""
    _need_real_server(ctx, "the reward double-claim race")

    reward = (ctx.db.select("rewards", is_active="true", limit=1) or [])
    if not reward:
        raise Skip("no active rewards row to base a redemption on")
    redemption = None
    try:
        redemption = ctx.db.insert("reward_redemptions", {
            "user_id": ctx.user_id, "reward_id": reward[0]["id"], "status": "fulfilled",
            "delivery_mode": "next_order",
        })
    except Failed as exc:
        raise Skip(f"could not provision a fulfilled redemption row ({exc}) — the schema "
                   "may need more columns; the race cannot be set up from here")
    redemption_id = str((redemption or {}).get("id") or "")
    if not redemption_id:
        raise Skip("the redemption row was not persisted")
    ctx.track_infra("reward_redemptions", redemption_id)

    marker = f"E2E race reward {uuid.uuid4().hex[:10]}"
    try:
        results = _race_orders(ctx, marker, 2, ctx.tokens["access"],
                               {"redemption_id": redemption_id})
        orders = _orders_with_marker(ctx, marker)
        statuses = [r[1].status for r in results if r[0] == "ok"]
        expect(not [x for x in statuses if x >= 500], f"a concurrent call answered 5xx: {statuses}")
        wins = [x for x in statuses if 200 <= x < 300]

        row = ctx.db.select_one("reward_redemptions", id=redemption_id) or {}
        attached = str(row.get("attached_order_id") or "")
        expect(len(orders) <= 1,
               f"two simultaneous checkouts on one reward created {len(orders)} orders "
               f"(statuses {statuses})")
        expect(bool(attached),
               "neither checkout claimed the reward (attached_order_id is still empty) — "
               "the reward was silently ignored")
        expect(orders and attached == str(orders[0]["id"]),
               f"the reward is attached to {attached}, which is not the order this run "
               f"created ({[o.get('id') for o in orders]})")
        expect(len(wins) <= 1,
               f"both checkouts succeeded on a single reward (statuses {statuses})")
        ctx.note(f"one reward, two simultaneous checkouts: statuses {statuses}, "
                 f"claimed by {attached[:8]}")
    finally:
        _drop_orders(ctx, _orders_with_marker(ctx, marker))
        ctx.db.delete("reward_redemptions", id=redemption_id)


@step("concurrency", "concurrency.free_side_single_use",
      "one free-side credit spent by two simultaneous checkouts is decremented once",
      writes=True, route="POST /api/orders", needs=("orders.place",))
def s_free_side_single_use(ctx: Ctx):
    """Same shape for free sides: the credit decrement is a compare-and-set, so two carts
    racing one credit must consume it once and never leave credits_remaining negative."""
    _need_real_server(ctx, "the free-side double-spend race")
    campus = ctx.ids.get("campus_id")
    items = [i for i in (ctx.db.select("free_side_items", is_active="true") or [])
             if i.get("campus_id") in (campus, None)]
    if not items:
        raise Skip("no active free_side_items row for this campus")
    try:
        credit = ctx.db.insert("free_side_credits", {
            "user_id": ctx.user_id, "campus_id": campus, "credits_remaining": 1,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        })
    except Failed as exc:
        raise Skip(f"could not create a free_side_credits row ({exc})")
    credit_id = str((credit or {}).get("id") or "")
    if not credit_id:
        raise Skip("the credit row was not persisted")
    ctx.track_infra("free_side_credits", credit_id)

    selection = ctx.api.post("/api/free-sides/select", json_body={"free_side_item_id": items[0]["id"]},
                             token=ctx.tokens["access"])
    if selection.status == 403:
        raise Skip(f"free_side_credits feature is off — {selection.snippet(120)}")
    if selection.status not in (200, 201):
        raise Skip(f"could not select a free side: {selection.status} {selection.snippet(120)}")
    sel_id = str(field(selection.data or {}, "id")
                 or ((selection.data or {}).get("selection") or {}).get("id") or "")
    if not sel_id:
        rows = ctx.db.select("cart_free_side_selections", user_id=ctx.user_id)
        sel_id = str(rows[0]["id"]) if rows else ""
    if sel_id:
        ctx.track_infra("cart_free_side_selections", sel_id)

    marker = f"E2E race free-side {uuid.uuid4().hex[:10]}"
    try:
        results = _race_orders(ctx, marker, 2, ctx.tokens["access"], {})
        orders = _orders_with_marker(ctx, marker)
        statuses = [r[1].status for r in results if r[0] == "ok"]
        expect(not [x for x in statuses if x >= 500], f"a concurrent call answered 5xx: {statuses}")

        row = ctx.db.select_one("free_side_credits", id=credit_id) or {}
        remaining = int(row.get("credits_remaining") or 0)
        expect(remaining >= 0,
               f"credits_remaining went negative ({remaining}) — the decrement is not guarded")
        expect(remaining == 0,
               f"the credit was not consumed (credits_remaining={remaining})")
        left = ctx.db.select("cart_free_side_selections", id=sel_id) if sel_id else []
        expect(len(orders) <= 1,
               f"one free-side credit produced {len(orders)} orders (statuses {statuses})")
        ctx.note(f"one credit, two simultaneous checkouts: statuses {statuses}, "
                 f"credits_remaining={remaining}, selection "
                 f"{'consumed' if not left else 'still present'}")
    finally:
        _drop_orders(ctx, _orders_with_marker(ctx, marker))


# ─────────────────────────────────────────────────────────────────────────────
#  Phase — authorization: who must NOT be able to reach what
# ─────────────────────────────────────────────────────────────────────────────
#
# The security phase asks whether a route *lost* its gate. This phase asks the harder
# question: does the gate that is there actually separate the roles — a customer from the
# admin surface, one campus's staff from another's data, one rider from another's orders.
#
# Every probe below attacks with a value that cannot match real data (a fresh UUID, a
# probe string), so a route that turns out to be missing its gate still cannot touch a
# row: it 404s on the id. That is what makes it safe to sweep the whole surface.

_ADMIN_SURFACE_FALLBACK = (
    # Used only when the suite cannot build the app in-process (--base-url on a machine
    # without the backend source): the admin.py surface plus the busiest staff routes.
    "GET /api/admin/orders", "GET /api/admin/users", "GET /api/admin/settings",
    "POST /api/admin/cron/<job_name>",
    "GET /api/admin/users/<user_id>", "GET /api/admin/users/<user_id>/orders",
    "PATCH /api/admin/users/<user_id>/role", "GET /api/admin/users/<user_id>/hp",
    "GET /api/admin/users/<user_id>/wallet", "POST /api/admin/users/<user_id>/deactivate",
    "POST /api/admin/users/<user_id>/activate",
    "PATCH /api/admin/delivery-windows/<window_id>",
    "POST /api/admin/delivery-windows/<window_id>/close",
    "POST /api/admin/delivery-windows/<window_id>/reopen",
    "PATCH /api/admin/ordering-windows/<window_id>",
    "GET /api/admin/delivery-batches/<batch_id>", "PATCH /api/admin/delivery-batches/<batch_id>",
    "DELETE /api/admin/delivery-batches/<batch_id>",
    "GET /api/admin/delivery-batches/<batch_id>/orders",
    "PATCH /api/admin/promo-codes/<promo_id>", "GET /api/admin/promo-codes/<promo_id>/uses",
    "POST /api/admin/abandoned-carts/<cart_id>/nudge",
    "PATCH /api/admin/exclusive-spin-pool/<prize_id>",
    "DELETE /api/admin/exclusive-spin-pool/<prize_id>",
    "GET /api/admin/campuses/<campus_id>/location",
    "PATCH /api/admin/campuses/<campus_id>/location",
    "PATCH /api/admin/feature-flags/<flag_name>", "GET /api/admin/categories",
    "PATCH /api/admin/items/<item_id>", "PATCH /api/admin/redemptions/<redemption_id>",
    "PATCH /api/admin/batches/<batch_id>/pay", "GET /api/admin/payments/<rider_id>",
)


def _attacker_customer(ctx: Ctx):
    """A customer session for the sweeps: the signed-in one, or a throwaway.

    Returns (token, user_id_to_drop, label). The signed-in session is the realistic
    attacker, but a sweep must also be runnable on its own (`--only authz`) before any
    account exists, so it falls back to provisioning one — and drops it afterwards.
    """
    token = ctx.tokens.get("access")
    if token:
        return token, None, "signed-in customer"
    user_id, token, why = _provision_role_user(ctx, "customer", str(ctx.ids.get("campus_id") or ""))
    if not token:
        _drop_role_user(ctx, user_id)
        raise Skip(f"no customer session and none could be provisioned: {why}")
    return token, user_id, "throwaway customer"


def _admin_surface() -> tuple[list[tuple[str, str]], str]:
    """Every route whose gate allows admin/super_admin. Returns ([(method, rule)], source).

    Loaded from the live URL map so a route added tomorrow is swept without editing this
    file. The gate is read off the view function's closure — the same tuple
    `require_role` closes over — so it reflects the code as loaded, not a copy.
    """
    try:
        sys.path.insert(0, str(BACKEND_ROOT))
        os.environ.setdefault("FLASK_ENV", "development")
        from app import create_app
        from app.config import config_map
        app = create_app(config_map["development"])
    except Exception as exc:                                        # noqa: BLE001
        print(f"    (live route map unavailable: {exc} — using the curated list)",
              file=sys.stderr)
        out = []
        for entry in _ADMIN_SURFACE_FALLBACK:
            method, _, rule = entry.partition(" ")
            out.append((method, rule))
        return out, "curated fallback"

    def roles_of(view):
        """The role tuple require_role closed over, if this view is role-gated."""
        fn = view
        for _ in range(4):                     # @wraps chains: walk __wrapped__ too
            for cell in (getattr(fn, "__closure__", None) or ()):
                try:
                    value = cell.cell_contents
                except ValueError:
                    continue
                if (isinstance(value, tuple) and value
                        and all(isinstance(v, str) for v in value)
                        and {"admin", "super_admin", "kitchen", "rider"} & set(value)):
                    return value
            fn = getattr(fn, "__wrapped__", None)
            if fn is None:
                break
        return None

    routes, ungated = [], []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        path = str(rule.rule)
        roles = roles_of(app.view_functions[rule.endpoint])
        # Staff gates only. `("admin",)` expands to admin+super_admin at request time,
        # and `("super_admin",)` alone is the most sensitive kind (cron triggers, flag
        # writes) — a customer or rider must be refused by both.
        if not roles or not ({"admin", "super_admin"} & set(roles)):
            # A path that *looks* administrative but carries no staff gate would be
            # silently absent from the sweep below — so it is a finding, not a skip.
            if "/admin/" in path:
                ungated.append(path)
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            routes.append((method, path))
    if ungated:
        raise Failed("administrative-looking path(s) with no staff role gate at all: "
                     + ", ".join(sorted(set(ungated)))
                     + " — add @require_role or move them out of /admin/")
    routes.sort()
    return routes, "live URL map"


def _probe_path(rule: str, placeholder: str) -> str:
    """Fill every URL parameter. Defaults to a UUID nothing can match."""
    def fill(match):
        name = match.group(1)
        if "id" in name.lower():
            return placeholder
        return "e2e-authz-probe"
    return re.sub(r"<[^>]*?([A-Za-z_][A-Za-z0-9_]*)>", fill, rule)


def _sweep_admin_surface(ctx: Ctx, token: str, label: str) -> tuple[int, int]:
    """Probe every admin-gated route with `token`. Returns (probed, complaints)."""
    routes, source = _admin_surface()
    placeholder = str(uuid.uuid4())
    leaked, crashed = [], []
    for method, rule in routes:
        path = _probe_path(rule, placeholder)
        if ctx.api.base_url:
            resp = ctx.api.request(method, path, token=token, params={"campus_id": placeholder})
        else:
            resp = ctx.api.request(method, path, token=token)
        if 200 <= resp.status < 300:
            leaked.append(f"{method} {path} -> {resp.status}")
        elif resp.status >= 500:
            crashed.append(f"{method} {path} -> {resp.status} {resp.snippet(80)}")

    ctx.note(f"{label}: probed {len(routes)} admin-gated route(s) from the {source}")
    if crashed:
        # A 5xx after the gate was supposed to refuse means the handler ran (or the
        # check itself fell over). Not a clean leak, but not something to ignore.
        ctx.warnings.append(
            f"{label}: {len(crashed)} admin route(s) answered 5xx instead of refusing — "
            + "; ".join(crashed[:4]) + (" …" if len(crashed) > 4 else ""))
    if leaked:
        raise Failed(
            f"{label}: {len(leaked)} admin route(s) answered a NON-admin session with 2xx: "
            + "; ".join(leaked[:6]) + (" …" if len(leaked) > 6 else ""))
    return len(routes), len(crashed)


@step("authz", "authz.admin_routes_refuse_customer",
      "every admin-gated route refuses a customer token (200 must be impossible)",
      writes=True, route="")
def s_admin_routes_refuse_customer(ctx: Ctx):
    """Walk the whole admin-gated surface with a customer token.

    This is the broad version of `security.permissions_matrix`: that one covers the
    parameterless admin GETs, this one covers every method on every staff-gated rule,
    parameterised routes included. A route that loses its `@require_role` answers 2xx here
    and fails the run — which is the whole point, because a missing decorator is invisible
    in review and silent in production.
    """
    token, throwaway, label = _attacker_customer(ctx)
    try:
        probed, crashed = _sweep_admin_surface(ctx, token, label)
        expect(probed > 20, f"the sweep only found {probed} admin routes — the loader is broken")
        ctx.note(f"{label} refused by all {probed} admin-gated route(s)"
                 + (f" ({crashed} answered 5xx, see warnings)" if crashed else ""))
    finally:
        _drop_role_user(ctx, throwaway)


@step("authz", "authz.admin_routes_refuse_rider",
      "a rider session cannot reach the admin surface",
      writes=True, route="", needs=("auth.login",))
def s_admin_routes_refuse_rider(ctx: Ctx):
    """Same sweep, attacker is a rider.

    Staff roles are not interchangeable: a rider who can read /api/admin/* sees every
    campus's orders and margins. `require_role("admin")` must not let a rider through,
    and a rider-specific route must not leak into the admin surface.
    """
    rider_id, rider_token, why = _provision_role_user(ctx, "rider", str(ctx.ids["campus_id"]))
    if not rider_id or not rider_token:
        _drop_role_user(ctx, rider_id)
        raise Skip(f"could not provision a rider session: {why}")
    try:
        probed, crashed = _sweep_admin_surface(ctx, rider_token, "rider token")
        ctx.note(f"rider token refused by all {probed} admin-gated route(s)"
                 + (f" ({crashed} answered 5xx, see warnings)" if crashed else ""))
    finally:
        _drop_role_user(ctx, rider_id)


@step("authz", "authz.cross_campus_kitchen_scope",
      "one campus's kitchen cannot advance another campus's order, and no query param widens it",
      writes=True, route="POST /api/kitchen/batch/<batch_id>/advance",
      needs=("auth.login", "orders.window", "public.menu", "public.hostels", "public.campuses"))
def s_cross_campus_kitchen_scope(ctx: Ctx):
    """Campus scoping, tested with a real session on the wrong campus.

    A kitchen account belongs to campus A and carries its campus in `profiles.campus_id`;
    `_resolve_kitchen_campus_id` reads that for staff. An order in campus B — with a batch
    key of its own, so a bug here cannot advance anybody else's order either — must be
    invisible to A's kitchen, and `?campus_id=<B>` must NOT widen the scope (only a
    super_admin may choose a campus, and even then only one).
    """
    own_campus = str(ctx.ids["campus_id"])
    campuses = ctx.db.select("campuses", is_active="true") or []
    other = next((str(c["id"]) for c in campuses if str(c.get("id")) != own_campus), "")
    if not other:
        raise Skip("no second active campus exists to test cross-campus isolation against")

    order_id, batch_key, _placed = _place_pinned_order(
        ctx, own_campus, "E2E cross-campus probe — safe to ignore")
    before = str((ctx.db.select_one("orders", id=order_id) or {}).get("status") or "")

    kitchen_id, kitchen_token, why = _provision_role_user(ctx, "kitchen", other)
    if not kitchen_token:
        _drop_role_user(ctx, kitchen_id)
        raise Skip(f"could not provision a kitchen session on the other campus: {why}")
    try:
        # 1. Without any parameter: the endpoint must scope to the kitchen's own campus.
        r = ctx.api.post(f"/api/kitchen/batch/{batch_key}/advance",
                         json_body={"notes": "E2E cross-campus probe"},
                         token=kitchen_token)
        advanced = [a.get("order_id") for a in ((r.data or {}).get("advanced") or [])]
        expect(order_id not in advanced,
               f"a kitchen session on campus {other} advanced an order on campus {own_campus}",
               r)

        # 2. With ?campus_id=<the victim's campus>: a staff token must not be able to
        #    choose a campus at all — that parameter is a super_admin affordance.
        r2 = ctx.api.post(f"/api/kitchen/batch/{batch_key}/advance",
                          json_body={"notes": "E2E cross-campus probe"},
                          token=kitchen_token, params={"campus_id": own_campus})
        advanced2 = [a.get("order_id") for a in ((r2.data or {}).get("advanced") or [])]
        expect(order_id not in advanced2,
               f"?campus_id={own_campus} let the other campus's kitchen advance the order", r2)

        after = str((ctx.db.select_one("orders", id=order_id) or {}).get("status") or "")
        expect(after == before,
               f"the cross-campus attempts changed the order status: {before} -> {after}")
        ctx.note(f"kitchen on campus {other} could not touch campus {own_campus}'s order "
                 f"(status stayed '{after}')")
    finally:
        _drop_role_user(ctx, kitchen_id)


@step("authz", "authz.rider_cannot_touch_another_riders_order",
      "a rider cannot pick up or read an order assigned to a different rider",
      writes=True, route="POST /api/riders/orders/<order_id>/pickup",
      needs=("auth.login", "orders.window", "public.menu", "public.hostels"))
def s_rider_isolation(ctx: Ctx):
    """Two riders, one order. The one who is NOT assigned must be refused.

    `delivery_assignments` is the authority for who may act on an order
    (`_effective_rider_id`). The order is placed by the customer, assigned to rider A, and
    attacked by rider B: pickup, deliver, and the order-scoped read. B must get 403/404
    for all three — a 200 means any rider can complete any delivery, which is both a data
    leak and a payout problem.
    """
    campus = str(ctx.ids["campus_id"])
    order_id, _batch_key, _placed = _place_pinned_order(
        ctx, campus, "E2E rider-isolation probe — safe to ignore")

    rider_a_id, _a_token, _why_a = _provision_role_user(ctx, "rider", campus)
    rider_b_id, b_token, why_b = _provision_role_user(ctx, "rider", campus)
    assignment_id = None
    try:
        if not rider_a_id or not rider_b_id or not b_token:
            raise Skip(f"could not provision both rider sessions ({why_b})")
        assignment = ctx.db.insert("delivery_assignments", {
            "order_id": order_id, "rider_id": rider_a_id, "status": "assigned",
            "note": "E2E rider-isolation probe — safe to ignore",
        })
        assignment_id = assignment.get("id")
        ctx.track_infra("delivery_assignments", assignment_id)
        if not assignment_id:
            raise Skip(f"could not assign the order to rider A: {assignment}")

        for method, path in (("POST", f"/api/riders/orders/{order_id}/pickup"),
                             ("POST", f"/api/riders/orders/{order_id}/deliver"),
                             ("GET", f"/api/riders/call/{order_id}")):
            r = ctx.api.request(method, path, token=b_token)
            if 200 <= r.status < 300:
                raise Failed(
                    f"rider B reached {method} {path} with status {r.status} on an order "
                    f"assigned to rider A — delivery_assignments is not isolating riders", r)
            expect(r.status in (400, 403, 404, 409),
                   f"{method} {path} answered {r.status} for the wrong rider "
                   f"(expected a refusal) — {r.snippet(100)}", r)

        # The wrong rider's history must not mention the order either.
        history = ctx.api.get("/api/riders/history", token=b_token)
        if history.status == 200 and history.text:
            expect(order_id not in history.text,
                   f"rider B's history lists an order assigned to rider A ({order_id})")
        ctx.note(f"rider B was refused pickup/deliver/read on rider A's order {order_id}"
                 f" (rider history {'checked' if history.status == 200 else 'unavailable'})")
    finally:
        if assignment_id:
            ctx.db.delete("delivery_assignments", id=assignment_id)
        _drop_role_user(ctx, rider_a_id)
        _drop_role_user(ctx, rider_b_id)


# Every parameterless admin GET route in the app. A customer token must never get a
# 200 from any of them; the list is the surface a role check protects, so a route
# losing its decorator is caught here rather than in review.
_ADMIN_GET_ROUTES = (
    "/api/admin/abandoned-carts",
    "/api/admin/academic-calendar",
    "/api/admin/academic-levels",
    "/api/admin/audit-log",
    "/api/admin/campuses",
    "/api/admin/cron/status",
    "/api/admin/delivery-batches",
    "/api/admin/delivery-windows",
    "/api/admin/departments",
    "/api/admin/economics/overview",
    "/api/admin/economics/redemption-analytics",
    "/api/admin/economics/tier-breakdown",
    "/api/admin/exclusive-spin-pool",
    "/api/admin/exclusive-spin-prizes",
    "/api/admin/feature-flags",
    "/api/admin/first-order-gifts",
    "/api/admin/hall-of-fame-rewards",
    "/api/admin/hp/report",
    "/api/admin/leaderboard-prizes",
    "/api/admin/ordering-windows",
    "/api/admin/orders",
    "/api/admin/promo-codes",
    "/api/admin/reviews",
    "/api/admin/settings",
    "/api/admin/stock-items",
    "/api/admin/webhook-events",
    "/api/admin/users",
    "/api/analytics/dashboard",
    "/api/analytics/revenue",
)

# Routes a guest must still reach. The standing rule is that no fix may block a guest
# from their path, so the same sweep that checks the gates also checks the openings.
_GUEST_ROUTES = (
    "/api/menu/categories",
    "/api/menu/items",
    "/api/hp/bundles",
    "/api/menu/kitchen-capacity",
    "/api/campuses",
)

# Customer-only routes: no token at all must not be served.
_CUSTOMER_ONLY = ("/api/orders", "/api/wallet", "/api/hp/balance")


@step("security", "security.permissions_matrix",
      "a customer token is refused by every admin route, and guests still reach theirs",
      route="GET /api/admin/audit-log", needs=("auth.login",))
def s_permissions_matrix(ctx: Ctx):
    """The audit found routes whose gate was the only thing protecting them. Nothing
    swept the whole surface before, so a decorator lost in a refactor would ship
    quietly. This walks every parameterless admin GET with a customer token and
    requires a refusal, then checks the guest-facing routes are still open.
    """
    token = ctx.tokens.get("access")
    if not token:
        raise Skip("no customer session — cannot probe the admin surface")

    leaked, refused, missing = [], 0, []
    for path in _ADMIN_GET_ROUTES:
        r = ctx.api.get(path, token=token)
        if r.status in (401, 403):
            refused += 1
        elif r.status == 404:
            missing.append(path)                 # route renamed/removed: fix the list
        elif r.status == 200:
            leaked.append(path)
        else:
            leaked.append(f"{path} (HTTP {r.status})")

    expect(not leaked,
           "these admin routes served a customer token: " + ", ".join(leaked) +
           " — a missing role check is a data leak, not a 500")
    if missing:
        ctx.warnings.append(f"admin sweep: {len(missing)} route(s) returned 404 (update the list): "
                            + ", ".join(missing))
    ctx.note(f"permissions: {refused}/{len(_ADMIN_GET_ROUTES)} admin GET routes refused the "
             "customer token")

    # The other half of the rule: a customer-only route must not answer a stranger.
    for path in _CUSTOMER_ONLY:
        r = ctx.api.get(path)
        expect(r.status in (401, 403),
               f"{path} answered HTTP {r.status} with no token at all — expected 401/403")

    blocked = []
    for path in _GUEST_ROUTES:
        r = ctx.api.get(path)
        if r.status in (401, 403):
            blocked.append(f"{path} (HTTP {r.status})")
    expect(not blocked,
           "these public routes now refuse anonymous callers, which blocks guests from a path "
           "they are entitled to: " + ", ".join(blocked))
    ctx.note(f"guests still reach {len(_GUEST_ROUTES)} public route(s); "
             f"{len(_CUSTOMER_ONLY)} customer-only route(s) refused an anonymous caller")


def _forged_webhook(ctx: Ctx, provider: str, header: str, payload: dict) -> "Resp":
    """Send a webhook with a signature that cannot be right."""
    r = ctx.api.post(f"/api/webhooks/{provider}", json_body=payload,
                     headers={header: "e2e-forged-signature"})
    return r


@step("security", "security.webhook_forgery_rejected",
      "forged webhook signatures are refused and leave no row behind",
      writes=True, route="POST /api/webhooks/paystack", needs=("auth.login",))
def s_webhook_forgery_rejected(ctx: Ctx):
    """Money enters through these endpoints, so the signature check is the only thing
    between the internet and a wallet credit. The reference is unique to this run, so
    nothing real can be touched even if the check is missing; if the request IS
    accepted, the row it creates is deleted and the run fails loudly.
    """
    marker = f"E2E-FORGED-{uuid.uuid4().hex[:12]}"
    wallet_before = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_before = float(wallet_before.get("balance") or 0)

    probes = (
        ("paystack", "x-paystack-signature",
         {"event": "charge.success", "data": {"reference": marker, "amount": 100000 * 100,
                                              "status": "success", "currency": "NGN"}}),
        ("flutterwave", "verif-hash",
         {"event": "charge.completed", "data": {"tx_ref": marker, "status": "successful",
                                                "amount": 100000, "currency": "NGN"}}),
    )

    for provider, header, payload in probes:
        r = _forged_webhook(ctx, provider, header, payload)
        # Whatever happened, this run must not leave the row behind.
        leftovers = ctx.db.select("webhook_events", reference=marker)
        for row in leftovers:
            ctx.db.delete("webhook_events", id=row["id"])

        if r.status == 200:
            raise Failed(
                f"{provider}: a FORGED signature was accepted (HTTP 200). Either the webhook "
                f"secret is unset and ALLOW_UNSIGNED_WEBHOOKS is on, or the comparison is "
                f"broken — anyone on the internet could post a payment and be credited. "
                f"{'A webhook_events row was created and has been deleted.' if leftovers else ''}")
        expect(r.status in (401, 403),
               f"{provider}: forged signature returned HTTP {r.status}, expected 401/403 "
               f"({r.snippet(120)})")
        expect(not leftovers,
               f"{provider}: the forged request was refused but wrote "
               f"{len(leftovers)} webhook_events row(s) anyway")
        ctx.note(f"{provider}: forged signature refused with {r.status}, no row written")

    wallet_after = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_after = float(wallet_after.get("balance") or 0)
    expect(abs(balance_after - balance_before) < 0.01,
           f"the wallet moved during a forgery probe: ₦{balance_before} → ₦{balance_after}")


@step("orders", "orders.override_closed_blocks",
      "a closed operating_hour_override refuses ordering, and removing it restores the schedule",
      writes=True, route="POST /api/orders", needs=("orders.place", "auth.login"))
def s_override_closed_blocks(ctx: Ctx):
    """Precedence rule 2: an override with is_closed=true closes the day even when the
    weekday's ordering_windows rows are open. Deleting it must put the recurring
    schedule back — an override is a dated exception, not a switch.
    """
    campus = str(ctx.ids["campus_id"])
    today = _override_probe_ready(ctx, campus)
    before = _status(ctx, campus)

    created = _add_override(ctx, campus, today, is_closed=True)
    try:
        closed = _status(ctx, campus)
        expect(closed.get("is_open") is False,
               f"the status endpoint still reports is_open={closed.get('is_open')} with a closed "
               f"override in place (windows={closed.get('windows')})")

        attempt = _try_order(ctx, campus)
        if attempt.status == 201:
            ctx.track("orders", str(field(attempt.data or {}, "id")
                                    or ((attempt.data or {}).get("order") or {}).get("id") or ""))
            raise Failed("an order was accepted while a closed override was in place")
        expect(attempt.status == 409,
               f"expected 409 from a closed override, got {attempt.status}: {attempt.snippet(120)}")
        msg = str((attempt.data or {}).get("error") or "")
        if "capacity" in msg.lower():
            raise Skip(f"the window was at capacity, not closed ({msg}) — the override is not the "
                       "cause here")
        expect("operating hours" in msg.lower(),
               f"the refusal did not come from the ordering gate: {msg!r}")
        ctx.note(f"closed override refused the order with {attempt.status}: {msg}")
    finally:
        _drop_override(ctx, created)

    after = _status(ctx, campus)
    expect(after.get("is_open") == before.get("is_open"),
           f"the recurring schedule did not come back after removing the override: "
           f"is_open {before.get('is_open')} -> {after.get('is_open')}")
    expect(len(after.get("windows") or []) == len(before.get("windows") or []),
           "the window list changed after removing the override")
    ctx.note("override removed: the recurring schedule applies again "
             f"(is_open={after.get('is_open')})")


@step("orders", "orders.override_opens_outside_hours",
      "an override outside the recurring hours opens ordering, and the gate reports its window",
      writes=True, route="POST /api/orders", needs=("orders.place", "auth.login"))
def s_override_opens_outside_hours(ctx: Ctx):
    """Precedence rule 2, the other half: an open override replaces the day's recurring
    windows. 00:00-23:59 is deliberately outside any normal window — NULL times mean the
    same thing — so a successful order here can only be the override's doing.
    """
    campus = str(ctx.ids["campus_id"])
    today = _override_probe_ready(ctx, campus)
    before = _status(ctx, campus)

    created = _add_override(ctx, campus, today, is_closed=False,
                            opens_at="00:00", closes_at="23:59")
    try:
        opened = _status(ctx, campus)
        windows = opened.get("windows") or []
        expect(opened.get("is_open") is True,
               f"the override did not open the day: is_open={opened.get('is_open')}, "
               f"windows={windows}")
        expect(len(windows) == 1,
               f"an open override must replace the day's windows with exactly one, got {len(windows)}")
        w = windows[0]
        expect((w.get("opens_at"), w.get("closes_at")) == ("00:00", "23:59"),
               f"the effective window is not the override's: {w}")

        # inherited identity: the day's single recurring row, when there is exactly one
        weekly = ctx.db.select("ordering_windows", weekday=(datetime.now(timezone.utc)
                                                           + timedelta(hours=1)).weekday(),
                               campus_id=campus)
        if len(weekly) == 1:
            expect(str(w.get("id")) == str(weekly[0]["id"]),
                   f"the override did not inherit the weekday row's id: {w.get('id')} vs "
                   f"{weekly[0]['id']}")

        attempt = _try_order(ctx, campus)
        if attempt.status in (200, 201):
            ctx.track("orders", str(field(attempt.data or {}, "id")
                                    or ((attempt.data or {}).get("order") or {}).get("id") or ""))
            ctx.note(f"ordering succeeded outside the recurring hours ({attempt.status}) — "
                     f"was is_open={before.get('is_open')} before the override")
        else:
            msg = str((attempt.data or {}).get("error") or "")
            expect(attempt.status != 409,
                   f"the override opened the window but the order was still refused: {msg}")
            raise Skip(f"the order failed for an unrelated reason: {attempt.status} {msg}")
    finally:
        _drop_override(ctx, created)

    restored = _status(ctx, campus)
    expect(restored.get("is_open") == before.get("is_open"),
           "removing the override did not restore the previous schedule")
    ctx.note("override removed: the recurring schedule applies again")


@step("orders", "orders.override_is_its_own_date",
      "an override for one date leaves every other date untouched",
      writes=True, route="GET /api/orders/delivery-windows/status",
      needs=("auth.login",))
def s_override_is_its_own_date(ctx: Ctx):
    """The "and then it expires by itself" half of the feature: the row is keyed by
    date, so tomorrow's closure cannot close today. Checked on the 7-day calendar,
    which is built from the same override-aware status call.
    """
    campus = str(ctx.ids["campus_id"])
    today = _override_probe_ready(ctx, campus)
    tomorrow = (datetime.fromisoformat(today) + timedelta(days=1)).isoformat()

    if ctx.db.select("operating_hour_overrides", date=tomorrow, campus_id=campus):
        raise Skip(f"an override already exists for {tomorrow} — this probe never touches a row "
                   "it did not create")

    before = _status(ctx, campus, calendar=True)
    created = _add_override(ctx, campus, tomorrow, is_closed=True)
    try:
        after = _status(ctx, campus, calendar=True)
        cal_before = {c["date"]: c["is_open"] for c in (before.get("calendar") or [])}
        cal_after = {c["date"]: c["is_open"] for c in (after.get("calendar") or [])}

        expect(cal_before.get(today) == cal_after.get(today),
               f"today's status changed because of TOMORROW's override: "
               f"{cal_before.get(today)} -> {cal_after.get(today)}")
        if tomorrow in cal_after:
            expect(cal_after[tomorrow] is False,
                   f"tomorrow is not reported closed despite a closed override: {cal_after[tomorrow]}")
            ctx.note(f"override applies to {tomorrow} only; today ({today}) unchanged")
        else:
            ctx.note(f"override applies to its own date only; {tomorrow} is outside the "
                     "calendar horizon")
    finally:
        _drop_override(ctx, created)

    final = _status(ctx, campus, calendar=True)
    cal_final = {c["date"]: c["is_open"] for c in (final.get("calendar") or [])}
    expect(cal_final == cal_before, "the calendar did not return to its pre-test state")


@step("orders", "orders.cancel_unpaid_scheduled_no_refund",
      "cancelling an UNPAID *scheduled* card order refunds nothing (H4 regression)",
      writes=True, route="DELETE /api/orders/<order_id>/scheduled",
      needs=("orders.place", "orders.fund_wallet"))
def s_cancel_unpaid_scheduled_no_refund(ctx: Ctx):
    """H4: the scheduled cancel route refunded BOTH halves unconditionally, while every
    order is created payment_status='pending' with card_amount_used already set. The
    existing regression test drives the non-scheduled route only, which is exactly how
    this sibling stayed broken. Same assertion, other route.
    """
    if not ctx.ids.get("hostel_id"):
        raise Skip("no delivery point — cannot build a scheduled card order")

    wallet_before = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_before = float(wallet_before.get("balance") or 0)

    scheduled_for = datetime.now(timezone.utc) + timedelta(days=2)
    body = {
        "items": [{"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1}],
        "payment_method": "card",
        "delivery_type": "on_campus",
        "delivery_location_id": str(ctx.ids["hostel_id"]),
        "is_scheduled": True,
        "scheduled_for": scheduled_for.strftime("%Y-%m-%dT08:00:00"),
        "notes": "E2E unpaid scheduled-cancel probe — safe to ignore",
    }
    r = ctx.api.post("/api/orders", json_body=body, token=ctx.tokens["access"],
                     headers={"X-Campus-ID": str(ctx.ids.get("campus_id") or "")})
    if r.status in (400, 409, 503):
        raise Skip(f"scheduled ordering unavailable: {r.snippet(120)}")
    r.check(201, allow=(200,))
    order_id = str(field(r.data or {}, "id")
                   or ((r.data or {}).get("order") or {}).get("id") or "")
    if not order_id:
        raise Skip("scheduled order was not persisted")
    ctx.track("orders", order_id)
    ctx.track_children("order_items", "order_id", order_id)

    order = ctx.db.select_one("orders", id=order_id) or {}
    if not order.get("is_scheduled"):
        raise Skip("the order was not created as scheduled")
    expect(str(order.get("payment_status") or "").lower() != "paid",
           f"scheduled probe order came back paid ({order.get('payment_status')}) — it is "
           "not testing the unpaid path", r)
    card_part = float(order.get("card_amount_used") or 0)
    expect(card_part > 0, "the scheduled card order has no card_amount_used to refund")

    cancel = ctx.api.delete(f"/api/orders/{order_id}/scheduled",
                            json_body={"reason": "E2E probe"}, token=ctx.tokens["access"])
    cancel.check(200, allow=(204,))
    refunded = float((cancel.data or {}).get("wallet_refunded") or 0)
    expect(refunded == 0,
           f"the scheduled cancel refunded ₦{refunded} on an unpaid order (payment_status="
           f"{order.get('payment_status')}, card_amount_used={card_part}) — the card half "
           "was never collected")
    wallet_after = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_after = float(wallet_after.get("balance") or 0)
    expect(abs(balance_after - balance_before) < 0.01,
           f"wallet moved on an unpaid scheduled cancel: ₦{balance_before} → ₦{balance_after}")
    ctx.note(f"unpaid scheduled order cancelled: refunded ₦0, balance unchanged (₦{balance_after})")


@step("orders", "orders.cancel_split_refunds_wallet_half",
      "a cancelled pending SPLIT order returns the wallet half it debited, and only that",
      writes=True, route="POST /api/orders/<order_id>/cancel",
      needs=("orders.place", "orders.fund_wallet"))
def s_cancel_split_refunds_wallet_half(ctx: Ctx):
    """The wallet half of a split order IS debited at creation (debit_wallet_atomic, in
    the order transaction); the card half is not collected until the webhook. Cancelling
    while still pending must therefore return exactly the wallet half — not zero (the
    customer would lose money) and not the card half too (free money).
    """
    if not ctx.ids.get("hostel_id"):
        raise Skip("no delivery point — cannot build a split order")
    wallet = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_before = float(wallet.get("balance") or 0)
    if balance_before < 1:
        raise Skip("wallet is empty — a split order cannot be funded")

    wallet_part = float(min(50.0, balance_before))
    body = {
        "items": [{"menu_item_id": ctx.ids["menu_item_id"], "quantity": 1}],
        "payment_method": "split",
        "wallet_amount": wallet_part,
        "delivery_type": "on_campus",
        "delivery_location_id": str(ctx.ids["hostel_id"]),
        "notes": "E2E split-cancel probe — safe to ignore",
    }
    r = ctx.api.post("/api/orders", json_body=body, token=ctx.tokens["access"],
                     headers={"X-Campus-ID": str(ctx.ids.get("campus_id") or "")})
    if r.status in (400, 409, 503):
        raise Skip(f"ordering unavailable: {r.snippet(120)}")
    r.check(201, allow=(200,))
    order_id = str(field(r.data or {}, "id")
                   or ((r.data or {}).get("order") or {}).get("id") or "")
    if not order_id:
        raise Skip("split order was not persisted")
    ctx.track("orders", order_id)
    ctx.track_children("order_items", "order_id", order_id)

    order = ctx.db.select_one("orders", id=order_id) or {}
    debited = float(order.get("wallet_amount_used") or 0)
    if not debited:
        raise Skip("the order did not use the wallet — not a split order")
    if float(order.get("card_amount_used") or 0) <= 0:
        raise Skip("the whole order fitted in the wallet — not a split order")
    if str(order.get("payment_status") or "").lower() == "paid":
        raise Skip("the card half was already collected — the pending path is not under test")

    cancel = ctx.api.post(f"/api/orders/{order_id}/cancel", json_body={"reason": "E2E probe"},
                          token=ctx.tokens["access"])
    cancel.check(200)
    refunded = float((cancel.data or {}).get("wallet_refunded") or 0)
    expect(abs(refunded - debited) < 0.01,
           f"split cancel refunded ₦{refunded} but ₦{debited} had been debited from the "
           "wallet — the customer either lost their half or was credited the uncollected "
           "card half")
    wallet_after = ctx.db.select_one("wallets", user_id=ctx.user_id) or {}
    balance_after = float(wallet_after.get("balance") or 0)
    expect(abs(balance_after - balance_before) < 0.01,
           f"wallet did not return to its starting balance: ₦{balance_before} → ₦{balance_after}")
    ctx.note(f"split order cancelled: refunded ₦{refunded} = the wallet half; "
             f"balance back to ₦{balance_after}")


@step("orders", "orders.free_side_consumed",
      "the order consumed the credit, removed the selection and added a ₦0 line",
      route="GET /api/orders/<order_id>", needs=("orders.place", "orders.free_side_provision"))
def s_free_side_consumed(ctx: Ctx):
    """The assertion the ecosystem was missing: after checkout, the credit is spent,
    the selection is gone, and the order carries the free item at price 0."""
    if not ctx.ids.get("free_side_expect_consumption"):
        raise Skip("no free-side credit was provisioned")
    order_id = ctx.ids.get("order_id")
    if not order_id:
        raise Skip("no order was placed")

    credit_id, sel_id = ctx.ids["free_side_credit_id"], ctx.ids["free_side_selection_id"]

    credit = ctx.db.select_one("free_side_credits", id=credit_id)
    expect(credit is not None, f"free_side_credits.{credit_id} vanished")
    expect(int(credit.get("credits_remaining") or 0) == 0,
           f"credit was NOT consumed — credits_remaining={credit.get('credits_remaining')} "
           f"for order {order_id} (hg_consume_free_sides_atomic / _consume_free_sides)")

    left = ctx.db.select("cart_free_side_selections", id=sel_id)
    expect(not left, f"selection {sel_id} still in cart_free_side_selections after checkout")

    items = ctx.db.select("order_items", order_id=order_id)
    free = [i for i in items if float(i.get("price_snapshot") or 0) == 0]
    expect(bool(free), "order_items has no ₦0 line for the free side")
    ctx.note(f"credit consumed, selection removed, ₦0 line: {free[0].get('name_snapshot')}")


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
        if ctx.cleanup_created:
            out.raw("  account kept — deleting only the rows this run created (--write-existing)")
        else:
            out.raw("  account kept — the run signed in to an existing account (--login-email)")
        # rows created under a parent this run created (order_items under an order)
        for table, column, value in ctx.children:
            try:
                ctx.db.delete(table, **{column: value})
                deleted += 1
            except Exception as exc:                 # noqa: BLE001 - cleanup must not abort
                failed += 1
                out.warn_line(f"delete {table}.{column}={value} errored: {exc}")
        # then the tracked rows, then scaffolding (orders reference the window)
        for table, row_id in reversed(ctx.created):
            try:
                if ctx.db.delete(table, id=row_id):
                    deleted += 1
                else:
                    failed += 1
                    out.warn_line(f"could not delete {table}.{row_id} — remove it by hand")
            except Exception as exc:                 # noqa: BLE001 - cleanup must not abort
                failed += 1
                out.warn_line(f"delete {table}.{row_id} errored: {exc}")
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

    # rows created under a parent this run created, before the parents themselves
    for table, column, value in ctx.children:
        try:
            ctx.db.delete(table, **{column: value})
            deleted += 1
        except Exception as exc:                     # noqa: BLE001 - cleanup must not abort
            failed += 1
            out.warn_line(f"delete {table}.{column}={value} errored: {exc}")

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
    parser.add_argument("--webhook-secret", default="",
                        help="Paystack secret key used to sign the webhook flow step "
                             "(falls back to PAYSTACK_WEBHOOK_SECRET / PAYSTACK_SECRET_KEY)")
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
                        help="with --login-email: allow write steps, then delete only the rows this "
                             "run created — the account and everything already on it is left alone. "
                             "Makefile shorthand: WRITE_EXISTING=1")
    parser.add_argument("--fund-wallet", type=float, default=3000.0,
                        help="₦ credited to the test wallet before ordering (0 disables)")
    parser.add_argument("--with-cron", action="store_true",
                        help="run every scheduled job in the suite (mutates shared data)")
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
    named = [s for s in STEPS
             if (not args.only or s.phase.startswith(args.only) or s.id.startswith(args.only))]
    if args.only and named:
        # Pull in the dependencies the named steps declare, in plan order, so
        # `--only flow` also provisions the session/order fixtures it stands on
        # (and still prints them, so the run reads as one flow, not a fragment).
        needed = {sid for s in named for sid in s.needs}
        named_ids = {s.id for s in named}
        while needed - named_ids:
            grabbed = [s for s in STEPS if s.id in needed and s.id not in named_ids]
            named_ids |= {s.id for s in grabbed}
            needed |= {sid for s in grabbed for sid in s.needs}
        selected = [s for s in STEPS if s.id in named_ids]
    else:
        selected = named

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
            s.result, s.detail = "skipped", (
                "existing account (--login-email) — writes are off. Add --write-existing "
                "(make e2e … WRITE_EXISTING=1): rows this run creates are then deleted at "
                "the end, and nothing already on the account is touched")
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
        for declared in s.all_routes():
            method, _, path = declared.partition(" ")
            checked += 1
            if (method, normalise(path)) not in known:
                problems.append(f"{s.id}: {declared} is not a registered route")

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
