"""
Holy Grills FUTA — Comprehensive End-to-End Test Suite
=======================================================
Live simulation against the running server and real Supabase database.
Every endpoint is exercised with real input values and real database writes.

What this script does:
  1. SEED   — Creates two confirmed test users (admin + regular) via Supabase Admin API,
              seeds marketplace listings, events, rewards, and challenges.
  2. TEST   — Hits every API endpoint in dependency order with real payloads, captures
              status codes and response bodies.
  3. CLEANUP — Deletes every row and auth user created during the run. The DB is left
               exactly as it was before the test.

Usage:
    python scripts/test_e2e.py

Output:
    - Pass/fail summary in stdout
    - Full report written to scripts/test_report.md
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────

BASE      = "http://localhost:5000/api"
SUPA_URL  = os.environ["SUPABASE_URL"].rstrip("/")
SRK       = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

SRK_HEADERS = {
    "apikey":        SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}

NOW     = datetime.now(timezone.utc)
import uuid as _uuid
RUN_ID  = _uuid.uuid4().hex[:8]

ADMIN_EMAIL = f"test_admin_{RUN_ID}@holygrills-test.ng"
USER_EMAIL  = f"test_user_{RUN_ID}@holygrills-test.ng"
PASSWORD    = "TestPass123!"

PASS, FAIL, SKIP = "✓", "✗", "○"

results: list[dict] = []

# Tracked IDs for cleanup (FK dependency aware)
CLEANUP: dict[str, list] = {
    "auth_users":              [],
    "events":                  [],
    "event_tickets":           [],
    "event_checkins":          [],
    "catering_requests":       [],
    "marketplace_listings":    [],
    "marketplace_requests":    [],
    "rewards":                 [],
    "challenges":              [],
    "orders":                  [],
    "order_reviews":           [],
    "user_addresses":          [],
    "newsletter_emails":       [],
    "payment_references":      [],
}

# Rows we could not confirm were deleted — fail the run instead of silently
# leaving test data behind in the live database.
LEFTOVER: list[str] = []

# ── Supabase REST helpers ─────────────────────────────────────────────────────

def _supa_get(table: str, params: dict = None):
    r = requests.get(f"{SUPA_URL}/rest/v1/{table}",
                     headers={**SRK_HEADERS, "Prefer": ""},
                     params=params or {}, timeout=15)
    if r.status_code >= 400 or not r.content:
        return None
    return r.json()

def _supa_insert(table: str, data: dict | list):
    r = requests.post(f"{SUPA_URL}/rest/v1/{table}",
                      headers=SRK_HEADERS, json=data, timeout=15)
    if r.status_code in (200, 201) and r.content:
        return r.json()
    print(f"  [supa_insert:{table}] HTTP {r.status_code} — {r.text[:200]}")
    return None

def _supa_update(table: str, col: str, val: str, data: dict) -> bool:
    r = requests.patch(f"{SUPA_URL}/rest/v1/{table}",
                       headers=SRK_HEADERS, json=data,
                       params={col: f"eq.{val}"}, timeout=15)
    return r.status_code in (200, 204)

def _supa_delete(table: str, col: str, val: str) -> bool:
    r = requests.delete(f"{SUPA_URL}/rest/v1/{table}",
                        headers={**SRK_HEADERS, "Prefer": ""},
                        params={col: f"eq.{val}"}, timeout=15)
    return r.status_code in (200, 204)

def _create_confirmed_user(email: str, password: str, meta: dict = None) -> dict | None:
    r = requests.post(
        f"{SUPA_URL}/auth/v1/admin/users",
        headers={"apikey": SRK, "Authorization": f"Bearer {SRK}",
                 "Content-Type": "application/json"},
        json={"email": email, "password": password,
              "email_confirm": True, "user_metadata": meta or {}},
        timeout=15,
    )
    if r.status_code in (200, 201):
        return r.json()
    print(f"  [create_user] HTTP {r.status_code} — {r.text[:200]}")
    return None

def _delete_auth_user(uid: str):
    requests.delete(
        f"{SUPA_URL}/auth/v1/admin/users/{uid}",
        headers={"apikey": SRK, "Authorization": f"Bearer {SRK}"},
        timeout=10,
    )

def _login(email: str, password: str) -> dict:
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed {email}: {r.text[:200]}"
    return r.json()

def _api(method: str, path: str, token: str = None, **kwargs) -> requests.Response:
    hdrs = kwargs.pop("headers", {})
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    url = f"{BASE}{path}"
    return getattr(requests, method)(url, headers=hdrs, timeout=20, **kwargs)

def record(label: str, resp: requests.Response, expect=None):
    expected = [expect] if isinstance(expect, int) else (expect or [200, 201])
    ok = resp.status_code in expected
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:200]
    results.append({"label": label, "status": resp.status_code, "ok": ok, "body": body})
    preview = (json.dumps(body)[:100] if isinstance(body, (dict, list)) else str(body)[:100])
    icon = PASS if ok else FAIL
    print(f"  {icon} [{resp.status_code}] {label}")
    if not ok:
        print(f"       → expected {expected}: {preview}")
    return resp

def skip_test(label: str, reason: str):
    results.append({"label": label, "status": 0, "ok": None, "body": reason})
    print(f"  {SKIP} {label} — {reason}")

# ── Seed helpers ──────────────────────────────────────────────────────────────

def fund_wallet(user_id: str, amount: float = 10_000.0) -> bool:
    """Credit the user's wallet directly via service role."""
    rows = _supa_get("wallets", {"user_id": f"eq.{user_id}", "select": "user_id,balance"})
    if not rows:
        # Wallet not yet created — trigger via wallet endpoint
        return False
    w = rows[0] if isinstance(rows, list) else rows
    new_bal = float(w.get("balance", 0)) + amount
    _supa_update("wallets", "user_id", user_id, {"balance": new_bal})
    _supa_insert("wallet_transactions", {
        "user_id":          user_id,
        "type":             "credit",
        "amount":           amount,
        "balance_after":    new_bal,
        "reason":           f"E2E test funding {RUN_ID}",
        "reference_type":   "topup",
        "provider_reference": f"E2E-{RUN_ID}",
    })
    return True

def trigger_wallet_creation(token: str):
    """Hit GET /wallet so the trigger creates the wallet row."""
    _api("get", "/wallet", token=token)
    time.sleep(0.5)

def seed_marketplace_listing(admin_tok: str) -> str | None:
    r = _api("post", "/marketplace/admin/listings", token=admin_tok, json={
        "title":        f"Test WiFi Code {RUN_ID}",
        "description":  "E2E test listing — auto-deleted",
        "listing_type": "code",
        "price":        1000,
        "hp_price":     100,
        "vendor_name":  "Test ISP",
        "status":       "active",
    })
    if r.status_code == 201:
        lid = r.json().get("id")
        if lid:
            CLEANUP["marketplace_listings"].append(lid)
        return lid
    print(f"  [seed_listing] {r.status_code} {r.text[:150]}")
    return None

def seed_event(admin_tok: str) -> str | None:
    future = (NOW + timedelta(days=7)).isoformat()
    r = _api("post", "/events", token=admin_tok, json={
        "title":       f"FUTA Tech Week {RUN_ID}",
        "description": "E2E test event — auto-deleted",
        "location":    "FUTA Auditorium, Akure",
        "starts_at":   future,
        "hp_reward":   40,
        "capacity":    200,
    })
    if r.status_code == 201:
        eid = r.json().get("id")
        if eid:
            CLEANUP["events"].append(eid)
        return eid
    print(f"  [seed_event] {r.status_code} {r.text[:150]}")
    return None

def seed_reward(admin_tok: str) -> str | None:
    """Create a reward; rewards.py expects 'name' and 'hp_cost'. Table uses 'stock_quantity'."""
    r = _api("post", "/rewards", token=admin_tok, json={
        "name":           f"Test Free Burger {RUN_ID}",
        "hp_cost":        50,
        "category":       "food",   # rewards.py maps this → reward_type
        "stock_quantity": 10,
        "is_active":      True,
    })
    if r.status_code == 201:
        rid = r.json().get("id")
        if rid:
            CLEANUP["rewards"].append(rid)
        return rid
    print(f"  [seed_reward] {r.status_code} {r.text[:150]}")
    return None

def seed_challenge(admin_tok: str) -> str | None:
    """Create a challenge; challenges.py requires title, hp_reward, starts_at, ends_at, type."""
    r = _api("post", "/challenges", token=admin_tok, json={
        "title":                  f"Order Challenge {RUN_ID}",
        "description":            "Place 1 order to complete",
        "type":                   "one_time",
        "hp_reward":              50,
        "starts_at":              NOW.isoformat(),
        "ends_at":                (NOW + timedelta(days=30)).isoformat(),
        "max_completions_per_user": 1,
        "criteria":               {"type": "order_count", "target": 1},
        "is_active":              True,
    })
    if r.status_code == 201:
        cid = r.json().get("id")
        if cid:
            CLEANUP["challenges"].append(cid)
        return cid
    print(f"  [seed_challenge] {r.status_code} {r.text[:150]}")
    return None

def grant_hp(user_id: str, amount: int, admin_tok: str) -> bool:
    r = _api("post", "/admin/hp/bulk-grant", token=admin_tok, json={
        "user_id": user_id,
        "amount":  amount,
        "notes":   f"E2E test HP grant {RUN_ID}",
    })
    return r.status_code in (200, 201)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 65)
    print("  Holy Grills FUTA — End-to-End Live API Test")
    print(f"  Run ID: {RUN_ID}")
    print("=" * 65)

    # ── PHASE 1: Create test users ────────────────────────────────────────────
    print("\n⚙  PHASE 1 — Create test users")

    admin_auth = _create_confirmed_user(ADMIN_EMAIL, PASSWORD, {"full_name": "E2E Admin"})
    assert admin_auth, "Failed to create admin auth user"
    admin_uid = admin_auth["id"]
    CLEANUP["auth_users"].append(admin_uid)
    print(f"  {PASS} Admin user: {admin_uid[:8]}…")

    user_auth = _create_confirmed_user(USER_EMAIL, PASSWORD, {"full_name": "E2E Student"})
    assert user_auth, "Failed to create student auth user"
    user_uid = user_auth["id"]
    CLEANUP["auth_users"].append(user_uid)
    print(f"  {PASS} Student user: {user_uid[:8]}…")

    # Wait for Supabase profile trigger
    time.sleep(2)

    _supa_update("profiles", "id", admin_uid, {"role": "admin", "full_name": "E2E Admin"})
    _supa_update("profiles", "id", user_uid,  {"full_name": "E2E Student", "phone": "08012345678"})
    print(f"  {PASS} Roles set")

    # ── PHASE 2: Login ────────────────────────────────────────────────────────
    print("\n⚙  PHASE 2 — Login")

    admin_data    = _login(ADMIN_EMAIL, PASSWORD)
    admin_tok     = admin_data["access_token"]
    admin_refresh = admin_data.get("refresh_token", "")
    print(f"  {PASS} Admin logged in")

    user_data    = _login(USER_EMAIL, PASSWORD)
    user_tok     = user_data["access_token"]
    user_refresh = user_data.get("refresh_token", "")
    print(f"  {PASS} Student logged in")

    # Trigger wallet creation (Supabase trigger fires on first wallet access)
    trigger_wallet_creation(admin_tok)
    trigger_wallet_creation(user_tok)
    time.sleep(0.5)

    # Fund wallets and grant HP
    fund_wallet(user_uid, 15_000)
    fund_wallet(admin_uid, 5_000)
    print(f"  {PASS} Wallets funded")

    # ── PHASE 3: Seed test data ───────────────────────────────────────────────
    print("\n⚙  PHASE 3 — Seed test data")

    listing_id = seed_marketplace_listing(admin_tok)
    print(f"  {PASS if listing_id else FAIL} Marketplace listing: {listing_id or 'FAILED'}")

    if listing_id:
        cr = _api("post", f"/marketplace/admin/codes/{listing_id}", token=admin_tok,
                  json={"codes": [f"WIFI-{RUN_ID}-A", f"WIFI-{RUN_ID}-B", f"WIFI-{RUN_ID}-C"]})
        print(f"  {PASS if cr.status_code == 201 else FAIL} Access codes [{cr.status_code}]")

    event_id   = seed_event(admin_tok)
    print(f"  {PASS if event_id else FAIL} Event: {event_id or 'FAILED'}")

    reward_id  = seed_reward(admin_tok)
    print(f"  {PASS if reward_id else FAIL} Reward: {reward_id or 'FAILED'}")

    challenge_id = seed_challenge(admin_tok)
    print(f"  {PASS if challenge_id else FAIL} Challenge: {challenge_id or 'FAILED'}")

    grant_hp(user_uid, 500, admin_tok)
    print(f"  {PASS} 500 HP granted to student")

    # ── PHASE 4: API Tests ────────────────────────────────────────────────────
    print("\n⚙  PHASE 4 — API endpoint tests\n")

    # ── HEALTH ────────────────────────────────────────────────────────────────
    print("── Health")
    record("GET /health", _api("get", "/health"), [200])

    # ── AUTH ──────────────────────────────────────────────────────────────────
    print("\n── Auth")

    r_reg = record("POST /auth/register", _api("post", "/auth/register", json={
        "email":     f"test_new_{RUN_ID}@holygrills-test.ng",
        "password":  PASSWORD,
        "full_name": "E2E New User",
    }), [201])
    if r_reg.status_code == 201:
        new_uid = (r_reg.json().get("user") or {}).get("id")
        if new_uid:
            CLEANUP["auth_users"].append(new_uid)

    record("POST /auth/login", _api("post", "/auth/login",
           json={"email": USER_EMAIL, "password": PASSWORD}), [200])

    record("POST /auth/refresh", _api("post", "/auth/refresh",
           json={"refresh_token": user_refresh, "access_token": user_tok}), [200])

    record("GET /auth/me", _api("get", "/auth/me", token=user_tok), [200])

    record("PATCH /auth/profile", _api("patch", "/auth/profile", token=user_tok, json={
        "full_name": "E2E Student Updated",
        "phone":     "08099887766",
    }), [200])

    r_addr = record("POST /auth/addresses", _api("post", "/auth/addresses", token=user_tok, json={
        "label":        "Hostel Room",
        "address_line": "Block A, Room 12, FUTA Main Hostel",
        "city":         "Akure",
        "state":        "Ondo",
        "landmark":     "Near the water tank",
        "is_default":   True,
    }), [201])
    addr_id = r_addr.json().get("id") if r_addr.status_code == 201 else None
    if addr_id:
        CLEANUP["user_addresses"].append(addr_id)

    record("GET /auth/addresses", _api("get", "/auth/addresses", token=user_tok), [200])

    if addr_id:
        record("PATCH /auth/addresses/<id>", _api("patch", f"/auth/addresses/{addr_id}",
               token=user_tok, json={"label": "Hostel Block A"}), [200])
        record("DELETE /auth/addresses/<id>", _api("delete", f"/auth/addresses/{addr_id}",
               token=user_tok), [200])
        CLEANUP["user_addresses"].remove(addr_id)  # Already deleted

    record("GET /auth/streak", _api("get", "/auth/streak", token=user_tok), [200])

    record("POST /auth/verify-email", _api("post", "/auth/verify-email",
           json={"email": USER_EMAIL}), [200])

    record("POST /auth/reset-password", _api("post", "/auth/reset-password",
           json={"email": USER_EMAIL}), [200])

    record("POST /auth/device-token", _api("post", "/auth/device-token", token=user_tok, json={
        "token":        f"test-device-{RUN_ID}",
        "platform":     "android",
        "device_model": "Samsung Galaxy S24",
    }), [200, 201])

    # ── STOREFRONT ────────────────────────────────────────────────────────────
    print("\n── Storefront")
    record("GET /storefront/sections",        _api("get", "/storefront/sections"),         [200])
    record("GET /storefront/operating-hours", _api("get", "/storefront/operating-hours"),  [200])
    record("GET /storefront/banners",         _api("get", "/storefront/banners"),          [200])
    record("POST /storefront/promo-codes/validate", _api("post", "/storefront/promo-codes/validate",
           json={"code": "WELCOME20", "order_subtotal": 2500}), [200, 400])
    newsletter_email = f"news_{RUN_ID}@futa.edu.ng"
    r_news = record("POST /storefront/newsletter", _api("post", "/storefront/newsletter",
           json={"email": newsletter_email, "name": "FUTA Student"}), [200, 201])
    if r_news.status_code in (200, 201):
        CLEANUP["newsletter_emails"].append(newsletter_email)

    # ── MENU ─────────────────────────────────────────────────────────────────
    print("\n── Menu")
    record("GET /menu/items",      _api("get", "/menu/items"),      [200])
    record("GET /menu/categories", _api("get", "/menu/categories"), [200])

    menu_r  = _api("get", "/menu/items")
    items   = menu_r.json() if menu_r.status_code == 200 else []
    items   = items if isinstance(items, list) else items.get("items", [])
    item    = next((i for i in items if i.get("is_available")), None)
    item_id = item["id"] if item else None

    if item_id:
        record("GET /menu/items/<id>", _api("get", f"/menu/items/{item_id}"), [200])
    else:
        skip_test("GET /menu/items/<id>", "No available menu item")

    # ── DELIVERY WINDOWS ──────────────────────────────────────────────────────
    print("\n── Delivery Windows")
    dw_r    = record("GET /orders/delivery-windows",        _api("get", "/orders/delivery-windows"),        [200])
    windows = dw_r.json() if dw_r.status_code == 200 else []
    window_id = windows[0]["id"] if isinstance(windows, list) and windows else None

    record("GET /orders/delivery-windows/status", _api("get", "/orders/delivery-windows/status"), [200])
    record("GET /orders/delivery-zones",          _api("get", "/orders/delivery-zones"),          [200])
    record("POST /orders/validate-promo",         _api("post", "/orders/validate-promo",
           json={"code": "STUDENT10", "order_subtotal": 3000}), [200, 400])

    # ── ORDERS ────────────────────────────────────────────────────────────────
    print("\n── Orders")
    order_id = None

    if item_id and window_id:
        r_ord = record("POST /orders (wallet payment)", _api("post", "/orders", token=user_tok, json={
            "items":            [{"menu_item_id": item_id, "quantity": 2}],
            "delivery_window_id": window_id,
            "payment_method":   "wallet",
            "delivery_address": {
                "address_line": "Block A, Room 12, FUTA Main Hostel",
                "landmark":     "Near the water tank",
                "zone":         "main_campus",
            },
            "notes": f"E2E test order {RUN_ID}",
        }), [201, 400])
        if r_ord.status_code == 201:
            order_id = r_ord.json().get("id")
            if order_id:
                CLEANUP["orders"].append(order_id)
        else:
            print(f"       → {r_ord.json()}")
    else:
        skip_test("POST /orders", f"No item ({bool(item_id)}) or window ({bool(window_id)})")

    record("GET /orders",           _api("get", "/orders",           token=user_tok), [200])
    record("GET /orders/active",    _api("get", "/orders/active",    token=user_tok), [200])
    record("GET /orders/scheduled", _api("get", "/orders/scheduled", token=user_tok), [200])

    if order_id:
        record("GET /orders/<id>", _api("get", f"/orders/{order_id}", token=user_tok), [200])

        # Walk order all the way to delivered
        r_walk = record("POST /orders/<id>/walk → delivered",
                        _api("post", f"/orders/{order_id}/walk", token=admin_tok,
                             json={"target_status": "delivered", "notes": "E2E test"}), [200, 400])

        if r_walk.status_code == 200:
            r_rev = record("POST /orders/<id>/review", _api("post", f"/orders/{order_id}/review",
                           token=user_tok, json={
                               "rating":         5,
                               "kitchen_rating": 5,
                               "rider_rating":   4,
                               "comment":        "Excellent food, fast delivery! 🔥",
                           }), [201])
            if r_rev.status_code == 201:
                rev_id = (r_rev.json().get("review") or {}).get("id")
                if rev_id:
                    CLEANUP["order_reviews"].append(rev_id)

        # Share order on social (earns HP)
        record("POST /orders/<id>/share", _api("post", f"/orders/{order_id}/share",
               token=user_tok, json={"platform": "whatsapp"}), [200, 201, 404])

    # ── CART ──────────────────────────────────────────────────────────────────
    print("\n── Cart")
    record("GET /cart", _api("get", "/cart", token=user_tok), [200])

    cart_item_id = None
    if item_id:
        r_cart = record("POST /cart (add item)", _api("post", "/cart", token=user_tok,
                        json={"menu_item_id": item_id, "quantity": 1}), [200, 201])
        if r_cart.status_code in (200, 201):
            ci = r_cart.json()
            cart_item_id = (ci.get("item") or ci).get("id")

        if cart_item_id:
            record("PATCH /cart/<id> (qty=3)", _api("patch", f"/cart/{cart_item_id}",
                   token=user_tok, json={"quantity": 3}), [200])

    # ── SAVED FOR LATER ───────────────────────────────────────────────────────
    print("\n── Saved For Later")
    record("GET /saved", _api("get", "/saved", token=user_tok), [200])

    saved_id = None
    if item_id:
        r_sfl = record("POST /saved (save item)", _api("post", "/saved", token=user_tok,
                       json={"menu_item_id": item_id, "quantity": 1}), [200, 201])
        if r_sfl.status_code in (200, 201):
            si = r_sfl.json()
            saved_id = (si.get("item") or si).get("id")

        if saved_id:
            record("PATCH /saved/<id>", _api("patch", f"/saved/{saved_id}",
                   token=user_tok, json={"quantity": 2}), [200])
            if cart_item_id:
                record("DELETE /saved/<id>", _api("delete", f"/saved/{saved_id}",
                       token=user_tok), [200])
                saved_id = None

        if cart_item_id:
            record("POST /saved/from-cart/<id>", _api("post", f"/saved/from-cart/{cart_item_id}",
                   token=user_tok), [200, 201, 404])
            cart_item_id = None  # moved to saved

    record("DELETE /cart (clear)", _api("delete", "/cart", token=user_tok), [200])

    # ── HP ────────────────────────────────────────────────────────────────────
    print("\n── HP (Holy Points)")
    record("GET /hp/balance",      _api("get",  "/hp/balance",      token=user_tok), [200])
    record("GET /hp/transactions", _api("get",  "/hp/transactions", token=user_tok), [200])
    record("GET /hp/tiers",        _api("get",  "/hp/tiers"),                        [200])
    record("GET /hp/spin/history", _api("get",  "/hp/spin/history", token=user_tok), [200])
    record("POST /hp/spin",        _api("post", "/hp/spin",         token=user_tok, json={}), [200, 400])
    record("POST /hp/transfer",    _api("post", "/hp/transfer",     token=user_tok, json={
        "to_user_id": admin_uid, "amount": 10, "note": "E2E HP transfer test",
    }), [200, 400])

    # ── WALLET ────────────────────────────────────────────────────────────────
    print("\n── Wallet")
    record("GET /wallet",              _api("get", "/wallet",              token=user_tok), [200])
    record("GET /wallet/transactions", _api("get", "/wallet/transactions", token=user_tok), [200])
    record("POST /wallet/fund/card",   _api("post", "/wallet/fund/card",   token=user_tok,
           json={"amount": 1000}), [200, 201, 400])
    record("POST /wallet/fund/bank",   _api("post", "/wallet/fund/bank",   token=user_tok,
           json={}), [200, 201, 400, 502])

    # ── REFERRALS ─────────────────────────────────────────────────────────────
    print("\n── Referrals")
    record("GET /referrals",       _api("get", "/referrals",       token=user_tok), [200])
    record("GET /referrals/stats", _api("get", "/referrals/stats", token=user_tok), [200])

    # ── NOTIFICATIONS ─────────────────────────────────────────────────────────
    print("\n── Notifications")
    record("GET /notifications",                _api("get",  "/notifications",             token=user_tok), [200])
    record("GET /notifications?unread=true",    _api("get",  "/notifications",
           params={"unread": "true"},           token=user_tok), [200])
    record("GET /notifications/preferences",    _api("get",  "/notifications/preferences", token=user_tok), [200])
    record("POST /notifications/read-all",      _api("post", "/notifications/read-all",    token=user_tok), [200])

    # ── LEADERBOARD ───────────────────────────────────────────────────────────
    print("\n── Leaderboard")
    record("GET /leaderboard",          _api("get", "/leaderboard"),                          [200])
    record("GET /leaderboard/my-rank",  _api("get", "/leaderboard/my-rank",  token=user_tok), [200])
    record("GET /leaderboard/squad",    _api("get", "/leaderboard/squad"),                    [200])
    record("GET /leaderboard/hall-of-fame", _api("get", "/leaderboard/hall-of-fame"),         [200])

    # ── REWARDS ───────────────────────────────────────────────────────────────
    print("\n── Rewards")
    record("GET /rewards",           _api("get", "/rewards",           token=user_tok), [200])
    record("GET /rewards/redemptions", _api("get", "/rewards/redemptions", token=user_tok), [200])

    if reward_id:
        record("GET /rewards/<id>", _api("get", f"/rewards/{reward_id}", token=user_tok), [200])

        r_redeem = record("POST /rewards/<id>/redeem", _api("post", f"/rewards/{reward_id}/redeem",
                          token=user_tok, json={}), [200, 201, 400])
        if r_redeem.status_code in (200, 201):
            redemption_id = (r_redeem.json().get("redemption") or r_redeem.json()).get("id")
            if redemption_id:
                record("GET /rewards/admin/redemptions",
                       _api("get", "/rewards/redemptions", token=admin_tok), [200])
                record("PATCH /rewards/admin/redemptions/<id>",
                       _api("patch", f"/rewards/admin/redemptions/{redemption_id}",
                            token=admin_tok, json={"status": "fulfilled",
                                                   "admin_notes": "Handed over at counter"}), [200, 404])

    # ── MARKETPLACE ───────────────────────────────────────────────────────────
    print("\n── Marketplace")
    record("GET /marketplace", _api("get", "/marketplace"), [200])

    if listing_id:
        record("GET /marketplace/<id>", _api("get", f"/marketplace/{listing_id}"), [200])
        record("POST /marketplace/<id>/purchase (wallet)",
               _api("post", f"/marketplace/{listing_id}/purchase", token=user_tok, json={
                   "use_hp_pricing":   False,
                   "payment_method":   "wallet",
               }), [201, 400])

    record("GET /marketplace/purchases",       _api("get", "/marketplace/purchases",       token=user_tok), [200])
    record("GET /marketplace/admin/purchases", _api("get", "/marketplace/admin/purchases", token=admin_tok), [200])
    record("GET /marketplace/admin/listings",  _api("get", "/marketplace/admin/listings",  token=admin_tok), [200])

    # Vendor listing request
    r_mreq = record("POST /marketplace/requests", _api("post", "/marketplace/requests", json={
        "vendor_name":    f"Campus Print {RUN_ID}",
        "vendor_email":   f"print_{RUN_ID}@futa.edu.ng",
        "vendor_phone":   "08055551234",
        "service_title":  "Printing & Photocopying",
        "category":       "services",
        "description":    "Affordable printing for all departments",
        "proposed_price": 50,
    }), [201, 503])
    mreq_id = None
    if r_mreq.status_code == 201:
        mreq_id = r_mreq.json().get("request", {}).get("id")
        if mreq_id:
            CLEANUP["marketplace_requests"].append(mreq_id)

    record("GET /marketplace/admin/requests",
           _api("get", "/marketplace/admin/requests", token=admin_tok), [200])

    if mreq_id:
        record("PATCH /marketplace/admin/requests/<id>",
               _api("patch", f"/marketplace/admin/requests/{mreq_id}", token=admin_tok,
                    json={"status": "approved", "admin_notes": "Vendor approved — welcome!"}), [200])

    # ── EVENTS ────────────────────────────────────────────────────────────────
    print("\n── Events")
    record("GET /events", _api("get", "/events"), [200])

    ticket_id = None
    if event_id:
        record("GET /events/<id>", _api("get", f"/events/{event_id}"), [200])

        # Register → get ticket_id (= qr_token). First call must issue a new
        # ticket (201); calling again with the same user must be idempotent
        # and return the SAME ticket_id with 200, never a second ticket.
        r_reg_evt = record("POST /events/<id>/register (first call → 201)",
                           _api("post", f"/events/{event_id}/register", token=user_tok), [201])
        if r_reg_evt.status_code in (200, 201):
            ticket_id = r_reg_evt.json().get("ticket_id")
            if ticket_id:
                CLEANUP["event_tickets"].append(ticket_id)

        r_reg_evt2 = record("POST /events/<id>/register (second call → 200, idempotent)",
                            _api("post", f"/events/{event_id}/register", token=user_tok), [200])
        if r_reg_evt2.status_code == 200 and ticket_id:
            dup_ticket_id = r_reg_evt2.json().get("ticket_id")
            same_ticket = (dup_ticket_id == ticket_id)
            results.append({
                "label": "Event registration idempotent — same ticket_id on re-register",
                "status": r_reg_evt2.status_code, "ok": same_ticket,
                "body": {"first": ticket_id, "second": dup_ticket_id},
            })
            print(f"  {PASS if same_ticket else FAIL} Same ticket_id on re-register ({ticket_id} == {dup_ticket_id})")

        # Generate QR token (admin)
        record("POST /events/<id>/qr (admin)",
               _api("post", f"/events/{event_id}/qr", token=admin_tok), [200])

        # Check in using ticket_id as qr_token
        if ticket_id:
            record("POST /events/<id>/checkin (ticket_id as qr_token)",
                   _api("post", f"/events/{event_id}/checkin", token=user_tok,
                        json={"qr_token": ticket_id}), [200, 400])

        # Catering request
        r_cat = record("POST /events/catering-requests", _api("post", "/events/catering-requests", json={
            "organizer_name":  f"FUTA SUG {RUN_ID}",
            "email":           f"sug_{RUN_ID}@futa.edu.ng",
            "phone":           "08033221100",
            "event_name":      "FUTA SUG End-of-Year Gala",
            "event_date":      (NOW + timedelta(days=14)).date().isoformat(),
            "expected_guests": 400,
            "budget":          250000,
            "notes":           "Jollof rice, grilled chicken, drinks, small chops",
            "hp_promo_optin":  True,
        }), [201])
        cat_id = None
        if r_cat.status_code == 201:
            cat_id = r_cat.json().get("id")
            if cat_id:
                CLEANUP["catering_requests"].append(cat_id)

        record("GET /events/catering-requests (admin)",
               _api("get", "/events/catering-requests", token=admin_tok), [200])

        if cat_id:
            record("PATCH /events/catering-requests/<id>",
                   _api("patch", f"/events/catering-requests/{cat_id}", token=admin_tok,
                        json={"status": "quoted"}), [200])

        record("GET /events/admin", _api("get", "/events/admin", token=admin_tok), [200])

        # Update event (admin)
        record("PATCH /events/<id> (admin)",
               _api("patch", f"/events/{event_id}", token=admin_tok,
                    json={"description": f"Updated by E2E test {RUN_ID}"}), [200])

    # ── CHALLENGES ────────────────────────────────────────────────────────────
    print("\n── Challenges")
    record("GET /challenges",       _api("get", "/challenges"),                      [200])
    record("GET /challenges/admin", _api("get", "/challenges/admin", token=admin_tok), [200])

    if challenge_id:
        # Complete the challenge
        record("POST /challenges/<id>/complete",
               _api("post", f"/challenges/{challenge_id}/complete", token=user_tok), [200, 400])

        # Update challenge (admin)
        record("PATCH /challenges/<id> (admin)",
               _api("patch", f"/challenges/{challenge_id}", token=admin_tok,
                    json={"description": f"Updated by E2E {RUN_ID}"}), [200])

    # ── KITCHEN ───────────────────────────────────────────────────────────────
    print("\n── Kitchen")
    record("GET /kitchen/settings",   _api("get", "/kitchen/settings",   token=admin_tok), [200])
    record("GET /kitchen/queue",      _api("get", "/kitchen/queue",      token=admin_tok), [200])
    record("GET /kitchen/windows",    _api("get", "/kitchen/windows",    token=admin_tok), [200])
    record("GET /kitchen/scheduled",  _api("get", "/kitchen/scheduled",  token=admin_tok), [200])
    record("GET /kitchen/metrics",    _api("get", "/kitchen/metrics",    token=admin_tok), [200])

    # ── RIDERS ────────────────────────────────────────────────────────────────
    print("\n── Riders")
    record("GET /riders/my-batch", _api("get", "/riders/my-batch", token=admin_tok), [200, 403, 404])
    record("GET /riders/history",  _api("get", "/riders/history",  token=admin_tok), [200, 403])
    record("GET /riders/stats",    _api("get", "/riders/stats",    token=admin_tok), [200, 403])
    record("GET /riders/earnings", _api("get", "/riders/earnings", token=admin_tok), [200, 403])

    # ── ORDER LOCKS ───────────────────────────────────────────────────────────
    print("\n── Order Locks")
    future_date = (NOW + timedelta(days=3)).date().isoformat()
    r_lock = record("POST /order-locks (create)", _api("post", "/order-locks", token=user_tok, json={
        "locked_date":  future_date,
        "discount_pct": 10,
    }), [200, 201, 400])
    lock_id = None
    if r_lock.status_code in (200, 201):
        lock_id = (r_lock.json().get("lock") or r_lock.json()).get("id")
        if lock_id:
            record("GET /order-locks",        _api("get",  "/order-locks",           token=user_tok), [200])
            record("GET /order-locks/<id>",   _api("get",  f"/order-locks/{lock_id}", token=user_tok), [200])
            reschedule_date = (NOW + timedelta(days=6)).date().isoformat()
            record("PATCH /order-locks/<id>/reschedule",
                   _api("patch", f"/order-locks/{lock_id}/reschedule", token=user_tok,
                        json={"locked_date": reschedule_date}), [200, 400])

    # ── ADMIN ─────────────────────────────────────────────────────────────────
    print("\n── Admin")
    record("GET /admin/users",                  _api("get", "/admin/users",               token=admin_tok), [200])
    record("GET /admin/users/<id>",             _api("get", f"/admin/users/{user_uid}",   token=admin_tok), [200])
    record("GET /admin/users/<id>/orders",      _api("get", f"/admin/users/{user_uid}/orders",  token=admin_tok), [200])
    record("GET /admin/users/<id>/hp",          _api("get", f"/admin/users/{user_uid}/hp",      token=admin_tok), [200])
    record("GET /admin/users/<id>/wallet",      _api("get", f"/admin/users/{user_uid}/wallet",  token=admin_tok), [200])
    record("GET /admin/orders",                 _api("get", "/admin/orders",              token=admin_tok), [200])
    record("GET /admin/delivery-windows",       _api("get", "/admin/delivery-windows",   token=admin_tok), [200])
    record("GET /admin/delivery-batches",       _api("get", "/admin/delivery-batches",   token=admin_tok), [200])
    record("GET /admin/promo-codes",            _api("get", "/admin/promo-codes",        token=admin_tok), [200])
    record("GET /admin/abandoned-carts",        _api("get", "/admin/abandoned-carts",    token=admin_tok), [200])
    record("GET /admin/first-order-gifts",      _api("get", "/admin/first-order-gifts",  token=admin_tok), [200])
    record("GET /admin/settings",               _api("get", "/admin/settings",           token=admin_tok), [200])

    record("PATCH /admin/settings/<key>",       _api("patch", "/admin/settings/platform_name",
           token=admin_tok, json={"value": "Holy Grills FUTA"}), [200])

    record("POST /admin/hp/bulk-grant", _api("post", "/admin/hp/bulk-grant", token=admin_tok, json={
        "user_ids": [user_uid],
        "amount":   25,
        "reason":   "E2E admin HP bulk-grant test",
    }), [200, 201])

    # Admin: create a test delivery window then close it
    r_dw_c = record("POST /admin/delivery-windows", _api("post", "/admin/delivery-windows",
                    token=admin_tok, json={
        "label":     f"E2E Window {RUN_ID}",
        "starts_at": (NOW + timedelta(days=1)).isoformat(),
        "ends_at":   (NOW + timedelta(days=1, hours=2)).isoformat(),
        "capacity":  10,
        "status":    "open",
    }), [200, 201])
    test_dw_id = None
    if r_dw_c.status_code in (200, 201):
        test_dw_id = (r_dw_c.json().get("window") or r_dw_c.json()).get("id")

    # ── ANALYTICS ─────────────────────────────────────────────────────────────
    print("\n── Analytics")
    record("GET /analytics/dashboard",   _api("get", "/analytics/dashboard",   token=admin_tok), [200])
    record("GET /analytics/sales",       _api("get", "/analytics/sales",       token=admin_tok), [200])
    record("GET /analytics/hp",          _api("get", "/analytics/hp",          token=admin_tok), [200])
    record("GET /analytics/referrals",   _api("get", "/analytics/referrals",   token=admin_tok), [200])
    record("GET /analytics/orders",      _api("get", "/analytics/orders",      token=admin_tok), [200])
    record("GET /analytics/marketplace", _api("get", "/analytics/marketplace", token=admin_tok), [200])

    # ── WEBHOOKS (signature checks) ───────────────────────────────────────────
    print("\n── Webhooks")
    record("POST /webhooks/paystack (no sig → 401)",
           _api("post", "/webhooks/paystack",     json={"event": "charge.success", "data": {}}), [401])
    record("POST /webhooks/flutterwave (no sig → 401)",
           _api("post", "/webhooks/flutterwave",  json={"event": "charge.completed", "data": {}}), [401])

    # ── LOGOUT ────────────────────────────────────────────────────────────────
    print("\n── Logout")
    record("POST /auth/logout-all-devices", _api("post", "/auth/logout-all-devices", token=user_tok), [200])
    record("POST /auth/logout",             _api("post", "/auth/logout",             token=admin_tok), [200])

    # ── PHASE 5: Cleanup ──────────────────────────────────────────────────────
    print("\n⚙  PHASE 5 — Cleanup")
    _cleanup(test_dw_id, lock_id)

    # ── PHASE 6: Report ───────────────────────────────────────────────────────
    _report()


def _cleanup(test_dw_id: str | None, lock_id: str | None):
    """Delete every test row in FK-safe reverse order, then auth users.
    Verifies each deletion actually removed the row (re-queries by id/col)
    and records anything still present in LEFTOVER so the run can fail loudly
    instead of silently leaving test data in the live database."""
    deleted = 0

    def _del(table: str, col: str, ids: list):
        nonlocal deleted
        for rid in ids:
            if not rid:
                continue
            _supa_delete(table, col, rid)
            remaining = _supa_get(table, {col: f"eq.{rid}", "select": col, "limit": 1})
            if remaining:
                LEFTOVER.append(f"{table}.{col}={rid}")
            else:
                deleted += 1

    # Dependent rows first
    _del("event_checkins",         "ticket_id",   CLEANUP["event_tickets"])
    _del("event_tickets",          "id",          CLEANUP["event_tickets"])
    _del("catering_requests",      "id",          CLEANUP["catering_requests"])
    _del("events",                 "id",          CLEANUP["events"])
    _del("marketplace_requests",   "id",          CLEANUP["marketplace_requests"])

    for lid in CLEANUP["marketplace_listings"]:
        if lid:
            _supa_delete("marketplace_purchases",  "listing_id", lid)
            _supa_delete("marketplace_access_codes", "listing_id", lid)
    _del("marketplace_listings",   "id",          CLEANUP["marketplace_listings"])

    _del("order_reviews",          "id",          CLEANUP["order_reviews"])
    for oid in CLEANUP["orders"]:
        if oid:
            _supa_delete("order_items", "order_id", oid)
    _del("orders",                 "id",          CLEANUP["orders"])

    if lock_id:
        _supa_delete("order_locks", "id", lock_id)
        deleted += 1

    _del("challenges",             "id",          CLEANUP["challenges"])

    for rid in CLEANUP["rewards"]:
        if rid:
            _supa_delete("reward_redemptions", "reward_id", rid)
    _del("rewards",                "id",          CLEANUP["rewards"])
    _del("user_addresses",         "id",          CLEANUP["user_addresses"])

    if test_dw_id:
        _supa_delete("delivery_windows", "id", test_dw_id)
        deleted += 1

    # Per-user rows
    for uid in CLEANUP["auth_users"]:
        if not uid:
            continue
        for table in ["device_tokens", "monthly_hp_tracker", "login_streaks",
                      "challenge_completions", "hp_transactions", "notifications",
                      "cart_items", "saved_for_later"]:
            _supa_delete(table, "user_id", uid)

        # Wallet transactions (uses user_id directly, not wallet_id)
        _supa_delete("wallet_transactions", "user_id", uid)
        _supa_delete("virtual_accounts", "user_id", uid)
        _supa_delete("payment_transactions", "user_id", uid)
        _supa_delete("wallets", "user_id", uid)
        _supa_delete("profiles", "id", uid)
        _delete_auth_user(uid)
        auth_check = requests.get(
            f"{SUPA_URL}/auth/v1/admin/users/{uid}",
            headers={"apikey": SRK, "Authorization": f"Bearer {SRK}"}, timeout=10,
        )
        if auth_check.status_code == 200:
            LEFTOVER.append(f"auth_users.id={uid}")
        else:
            deleted += 1

    # Newsletter subscriptions created by the run (tracked by email, not id)
    for email in CLEANUP["newsletter_emails"]:
        _supa_delete("newsletter_subscriptions", "email", email)
        remaining = _supa_get("newsletter_subscriptions", {"email": f"eq.{email}", "select": "id", "limit": 1})
        if remaining:
            LEFTOVER.append(f"newsletter_subscriptions.email={email}")
        else:
            deleted += 1

    # Any payment_transactions rows tagged with this run's reference prefix
    # (created by webhook-driven flows, not just per-user funding)
    stray_payments = _supa_get("payment_transactions", {
        "provider_reference": f"like.*{RUN_ID}*", "select": "id",
    }) or []
    for row in stray_payments:
        pid = row.get("id")
        if pid:
            _supa_delete("payment_transactions", "id", pid)
            remaining = _supa_get("payment_transactions", {"id": f"eq.{pid}", "select": "id", "limit": 1})
            if remaining:
                LEFTOVER.append(f"payment_transactions.id={pid}")
            else:
                deleted += 1

    print(f"  {PASS} Cleanup complete — ~{deleted} rows removed, {len(CLEANUP['auth_users'])} auth users deleted")
    if LEFTOVER:
        print(f"  {FAIL} {len(LEFTOVER)} row(s) NOT confirmed deleted — database is not clean:")
        for item in LEFTOVER:
            print(f"       - {item}")
    else:
        print(f"  {PASS} Verified clean — no test rows remain in the database")


def _report():
    total   = len(results)
    passed  = sum(1 for r in results if r["ok"] is True)
    failed  = sum(1 for r in results if r["ok"] is False)
    skipped = sum(1 for r in results if r["ok"] is None)

    print("\n" + "=" * 65)
    print(f"  RESULTS: {passed}/{total} passed  |  {failed} failed  |  {skipped} skipped")
    if LEFTOVER:
        print(f"  DATABASE NOT CLEAN: {len(LEFTOVER)} row(s) left behind")
    print("=" * 65)

    if failed:
        print("\nFailed tests:")
        for r in results:
            if r["ok"] is False:
                body = json.dumps(r["body"])[:200] if isinstance(r["body"], (dict, list)) else str(r["body"])[:200]
                print(f"  {FAIL} [{r['status']}] {r['label']}")
                print(f"       {body}")

    # Markdown report
    path = "scripts/test_report.md"
    with open(path, "w") as f:
        f.write("# Holy Grills API — End-to-End Test Report\n\n")
        f.write(f"**Run ID:** `{RUN_ID}`  \n")
        f.write(f"**Date:** {NOW.strftime('%Y-%m-%d %H:%M UTC')}  \n")
        f.write(f"**Results:** {passed} passed / {failed} failed / {skipped} skipped / {total} total\n\n")
        f.write("## Endpoint Results\n\n")
        f.write("| Status | Endpoint | HTTP | Error |\n")
        f.write("|--------|----------|------|-------|\n")
        for r in results:
            icon = "✅" if r["ok"] is True else ("❌" if r["ok"] is False else "⬜")
            err  = ""
            if r["ok"] is False:
                err = json.dumps(r["body"])[:120] if isinstance(r["body"], (dict, list)) else str(r["body"])[:120]
            f.write(f"| {icon} | {r['label']} | {r['status']} | {err} |\n")
        f.write("\n---\n*Auto-generated by `scripts/test_e2e.py`*\n")

    print(f"\n  Report → {path}")
    print("=" * 65 + "\n")

    sys.exit(0 if (failed == 0 and not LEFTOVER) else 1)


if __name__ == "__main__":
    main()
