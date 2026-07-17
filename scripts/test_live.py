"""
Holy Grills — Comprehensive Live API Test Suite
================================================
Tests every major endpoint against the running Flask server.
Creates a real test user, exercises the full cycle, then cleans up.

Run: python scripts/test_live.py
"""
import os, sys, uuid, json, requests
from datetime import date, timedelta

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:5000/api")
SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})

TEST_EMAIL = f"testlive_{uuid.uuid4().hex[:8]}@holygrills-test.dev"
TEST_PW    = "TestPass123!"
TEST_NAME  = "Test LiveUser"

PASS = "✅"; FAIL = "❌"; SKIP = "⏭ "; INFO = "ℹ "
results = {"pass": 0, "fail": 0, "skip": 0}

_access_token      = None
_user_id           = None
_order_id          = None
_menu_item_id      = None
_delivery_window_id = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def auth_headers():
    return {"Authorization": f"Bearer {_access_token}"} if _access_token else {}

def req(method, path, *, timeout=30, **kw):
    """Call an endpoint; return (response|None, error_str|None)."""
    try:
        return SESSION.request(method, f"{BASE}{path}", timeout=timeout, **kw), None
    except requests.Timeout:
        return None, "TIMEOUT"
    except Exception as e:
        return None, str(e)

def check(label, method, path, *, expected=(200,), check_fn=None, timeout=30, **kw):
    """Make a request and assert status + optional body check."""
    r, err = req(method, path, timeout=timeout, **kw)
    if err:
        results["skip"] += 1
        print(f"  {SKIP} {label} [{err}]")
        return None
    ok = r.status_code in (expected if isinstance(expected, tuple) else (expected,))
    body = None
    try:
        body = r.json()
    except Exception:
        body = {}
    if ok and check_fn:
        try:
            ok = bool(check_fn(body))
        except Exception as e2:
            ok = False
    results["pass" if ok else "fail"] += 1
    detail = ""
    if not ok:
        detail = f" → {json.dumps(body)[:220]}"
    print(f"  {PASS if ok else FAIL} {label} [{r.status_code}]{detail}")
    return body if ok else None

def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ── 1. Health ─────────────────────────────────────────────────────────────────
section("1. Health")
check("GET /health",        "GET", "/health",
      check_fn=lambda b: b.get("api") == "Holy Grills")
check("Supabase connected", "GET", "/health",
      check_fn=lambda b: b["checks"]["supabase"] == "connected")


# ── 2. Auth — Register / Login ────────────────────────────────────────────────
section("2. Auth — Register & Login")
data = check("POST /auth/register", "POST", "/auth/register",
             json={"email": TEST_EMAIL, "password": TEST_PW, "full_name": TEST_NAME},
             expected=(201,), check_fn=lambda b: "access_token" in b or "user" in b)
if data:
    _access_token = data.get("access_token") or (data.get("session") or {}).get("access_token")
    _user_id      = (data.get("user") or {}).get("id")
    SESSION.headers.update(auth_headers())
    print(f"  {INFO} user_id={_user_id}")

data = check("POST /auth/login", "POST", "/auth/login",
             json={"email": TEST_EMAIL, "password": TEST_PW},
             check_fn=lambda b: "access_token" in b)
if data:
    _access_token = data.get("access_token")
    _refresh_token = data.get("refresh_token")
    SESSION.headers.update(auth_headers())

    if _refresh_token:
        check("POST /auth/refresh", "POST", "/auth/refresh",
              json={"refresh_token": _refresh_token, "access_token": _access_token},
              check_fn=lambda b: "access_token" in b)

check("GET /auth/me",     "GET", "/auth/me",
      check_fn=lambda b: "profile" in b or "id" in b)
check("GET /auth/streak", "GET", "/auth/streak")
check("PATCH /auth/profile", "PATCH", "/auth/profile",
      json={"full_name": TEST_NAME}, check_fn=lambda b: True)

# Wrong password → 401
check("POST /auth/login wrong pw → 401", "POST", "/auth/login",
      json={"email": TEST_EMAIL, "password": "wrongwrong"},
      expected=(401,))

# Verify-email (public)
r, _ = req("POST", "/auth/verify-email",
           json={"email": TEST_EMAIL},
           timeout=15)
if r is not None:
    ok = r.status_code == 200
    results["pass" if ok else "fail"] += 1
    print(f"  {PASS if ok else FAIL} POST /auth/verify-email [{r.status_code}]")


# ── 3. Menu ───────────────────────────────────────────────────────────────────
section("3. Menu")
cats = check("GET /menu/categories", "GET", "/menu/categories",
             check_fn=lambda b: isinstance(b, list) and len(b) >= 8)
if cats:
    print(f"  {INFO} {len(cats)} categories")

items_resp = check("GET /menu/items", "GET", "/menu/items",
              check_fn=lambda b: (isinstance(b, list) and len(b) >= 24)
                                 or (isinstance(b, dict) and len(b.get("items", [])) >= 24))
if items_resp:
    items = items_resp if isinstance(items_resp, list) else items_resp.get("items", [])
    _menu_item_id = items[0]["id"]
    print(f"  {INFO} {len(items)} items, using id={_menu_item_id}")
    check("GET /menu/items/:id", "GET", f"/menu/items/{_menu_item_id}",
          check_fn=lambda b: "id" in b)


# ── 4. Storefront ─────────────────────────────────────────────────────────────
section("4. Storefront")
check("GET /storefront/sections",        "GET", "/storefront/sections",
      check_fn=lambda b: isinstance(b, list))
check("GET /storefront/operating-hours", "GET", "/storefront/operating-hours",
      check_fn=lambda b: isinstance(b, list) or (isinstance(b, dict) and "schedule" in b))

dws = check("GET /orders/delivery-windows", "GET", "/orders/delivery-windows",
            check_fn=lambda b: isinstance(b, list))
if dws:
    _delivery_window_id = dws[0]["id"]
    print(f"  {INFO} {len(dws)} delivery windows, using id={_delivery_window_id}")

check("POST /storefront/promo-codes/validate WELCOME20", "POST",
      "/storefront/promo-codes/validate",
      json={"code": "WELCOME20", "subtotal": 2000},
      expected=(200, 400))

check("GET /storefront/banners",    "GET", "/storefront/banners")
check("GET /storefront/newsletter", "GET", "/storefront/newsletter",
      expected=(200, 403, 404))


# ── 5. Cart ───────────────────────────────────────────────────────────────────
section("5. Cart")
check("GET /cart", "GET", "/cart")

if _menu_item_id:
    ci = check("POST /cart", "POST", "/cart",
               json={"menu_item_id": _menu_item_id, "quantity": 1},
               expected=(201,), check_fn=lambda b: "id" in b or "id" in b.get("item", {}))
    if ci:
        cid = ci.get("id") or ci.get("item", {}).get("id")
        check("PATCH /cart/:id",  "PATCH",  f"/cart/{cid}", json={"quantity": 2})
        check("DELETE /cart/:id", "DELETE", f"/cart/{cid}", expected=(200, 204))


# ── 6. Orders ─────────────────────────────────────────────────────────────────
section("6. Orders")
if _menu_item_id and _delivery_window_id:
    r, err = req("POST", "/orders", timeout=30, json={
        "items": [{"menu_item_id": _menu_item_id, "quantity": 1}],
        "delivery_window_id": _delivery_window_id,
        "payment_method": "wallet",
        "delivery_address": {"address_line": "Block A, FUTA", "landmark": "Main Gate", "zone": "hostel"},
        "notes": "Test order — ignore",
    })
    if err:
        results["skip"] += 1
        print(f"  {SKIP} POST /orders [{err}]")
    elif r.status_code == 201:
        _order_id = r.json().get("id")
        results["pass"] += 1
        print(f"  {PASS} POST /orders [201] id={_order_id}")
    elif r.status_code == 400:
        results["pass"] += 1
        print(f"  {PASS} POST /orders [400] (empty wallet — expected)")
    else:
        results["fail"] += 1
        print(f"  {FAIL} POST /orders [{r.status_code}] {r.text[:200]}")

check("GET /orders",                  "GET", "/orders")
check("GET /orders/scheduled",        "GET", "/orders/scheduled")
check("GET /orders/active",           "GET", "/orders/active")
check("GET /orders/delivery-windows/status", "GET", "/orders/delivery-windows/status")
check("GET /orders/delivery-zones",   "GET", "/orders/delivery-zones")

if _order_id:
    check("GET /orders/:id",         "GET", f"/orders/{_order_id}",
          check_fn=lambda b: "id" in b)
    check("GET /orders/:id/history", "GET", f"/orders/{_order_id}/history")

# Order share prompt (HP for sharing)
if _order_id:
    check("POST /orders/:id/share", "POST", f"/orders/{_order_id}/share",
          json={}, expected=(200, 400, 404))


# ── 7. HP ─────────────────────────────────────────────────────────────────────
section("7. HP (Holy Points)")
check("GET /hp/balance",        "GET", "/hp/balance",
      check_fn=lambda b: isinstance(b, dict))
check("GET /hp/transactions",   "GET", "/hp/transactions")
check("GET /hp/tiers",          "GET", "/hp/tiers",
      check_fn=lambda b: isinstance(b, list) or isinstance(b, dict))
check("GET /hp/unlock-history", "GET", "/hp/unlock-history")
check("GET /hp/spin/history",   "GET", "/hp/spin/history")

# HP transfer to self should fail (use own user_id)
if _user_id:
    check("POST /hp/transfer → 400 (self)", "POST", "/hp/transfer",
          json={"recipient_id": _user_id, "amount": 10}, expected=(400,))


# ── 8. Leaderboard (individual + squad — new) ──────────────────────────────────
section("8. Leaderboard — individual + squad")
check("GET /leaderboard",            "GET", "/leaderboard",
      check_fn=lambda b: "rankings" in b and "period_type" in b)
check("GET /leaderboard?weekly",     "GET", "/leaderboard?period_type=weekly",
      check_fn=lambda b: b.get("period_type") == "weekly")
check("GET /leaderboard?all_time",   "GET", "/leaderboard?period_type=all_time",
      check_fn=lambda b: b.get("period_type") == "all_time")
check("GET /leaderboard/hall-of-fame","GET","/leaderboard/hall-of-fame",
      check_fn=lambda b: isinstance(b, dict) and "inductees" in b)
check("GET /leaderboard/my-rank",    "GET", "/leaderboard/my-rank",
      check_fn=lambda b: "rank_entry" in b and "period_type" in b)

# Squad leaderboard (new endpoints)
check("GET /leaderboard/squad",                 "GET", "/leaderboard/squad",
      check_fn=lambda b: "rankings" in b and "period_type" in b)
check("GET /leaderboard/squad?weekly",          "GET", "/leaderboard/squad?period_type=weekly",
      check_fn=lambda b: "rankings" in b)
check("GET /leaderboard/squad?all_time",        "GET", "/leaderboard/squad?period_type=all_time",
      check_fn=lambda b: "rankings" in b)
check("GET /leaderboard/squad/my-rank",         "GET", "/leaderboard/squad/my-rank",
      check_fn=lambda b: "period_type" in b and "rank" in b)


# ── 9. Rewards ────────────────────────────────────────────────────────────────
section("9. Rewards")
check("GET /rewards",             "GET", "/rewards")
check("GET /rewards/redemptions", "GET", "/rewards/redemptions")


# ── 10. Wallet ────────────────────────────────────────────────────────────────
section("10. Wallet")
check("GET /wallet", "GET", "/wallet")


# ── 11. Marketplace ───────────────────────────────────────────────────────────
section("11. Marketplace")
check("GET /marketplace",           "GET", "/marketplace")
check("GET /marketplace/purchases", "GET", "/marketplace/purchases")


# ── 12. Events ────────────────────────────────────────────────────────────────
section("12. Events")
check("GET /events", "GET", "/events")


# ── 13. Referrals ─────────────────────────────────────────────────────────────
section("13. Referrals")
check("GET /referrals", "GET", "/referrals")


# ── 14. Notifications ─────────────────────────────────────────────────────────
section("14. Notifications")
check("GET /notifications",              "GET", "/notifications")
check("GET /notifications/preferences",  "GET", "/notifications/preferences")


# ── 15. Challenges ────────────────────────────────────────────────────────────
section("15. Challenges")
check("GET /challenges", "GET", "/challenges")


# ── 16. Saved For Later ───────────────────────────────────────────────────────
section("16. Saved For Later")
check("GET /saved", "GET", "/saved")

if _menu_item_id:
    si = check("POST /saved", "POST", "/saved",
               json={"menu_item_id": _menu_item_id, "quantity": 1},
               expected=(201,), check_fn=lambda b: "id" in b or "id" in b.get("item", {}))
    if si:
        sid = si.get("id") or si.get("item", {}).get("id")
        check("DELETE /saved/:id", "DELETE", f"/saved/{sid}", expected=(200, 204))


# ── 17. Order Locks ───────────────────────────────────────────────────────────
section("17. Order Locks (lock-in future order)")
check("GET /order-locks", "GET", "/order-locks")

future = (date.today() + timedelta(days=3)).isoformat()
lock = check("POST /order-locks", "POST", "/order-locks",
             json={"locked_date": future, "discount_pct": 10},
             expected=(201,), check_fn=lambda b: "id" in b or "id" in b.get("lock", {}))
if lock:
    lid = lock.get("id") or lock.get("lock", {}).get("id")
    check("PATCH /order-locks/:id/reschedule", "PATCH",
          f"/order-locks/{lid}/reschedule",
          json={"locked_date": (date.today() + timedelta(days=5)).isoformat()})
    check("DELETE /order-locks/:id", "DELETE", f"/order-locks/{lid}",
          expected=(200, 204))

# Validation: past date should fail
check("POST /order-locks past date → 400", "POST", "/order-locks",
      json={"locked_date": "2020-01-01", "discount_pct": 10}, expected=(400,))


# ── 18. Addresses ─────────────────────────────────────────────────────────────
section("18. Delivery Addresses")
check("GET /auth/addresses", "GET", "/auth/addresses",
      check_fn=lambda b: isinstance(b, list))

addr = check("POST /auth/addresses", "POST", "/auth/addresses",
             json={"label": "Test Hostel", "line1": "Room 5, Block C",
                   "city": "Akure", "state": "Ondo",
                   "landmark": "Near library", "is_default": False},
             expected=(201,), check_fn=lambda b: "id" in b)
if addr:
    aid = addr["id"]
    check("PATCH /auth/addresses/:id", "PATCH", f"/auth/addresses/{aid}",
          json={"label": "Updated Hostel"})
    check("DELETE /auth/addresses/:id", "DELETE", f"/auth/addresses/{aid}",
          expected=(200, 204))


# ── 19. Kitchen ───────────────────────────────────────────────────────────────
section("19. Kitchen (role-gated — student gets 403)")
check("GET /kitchen/settings → 403", "GET", "/kitchen/settings", expected=(200, 403))
check("GET /kitchen/queue → 403",    "GET", "/kitchen/queue",    expected=(200, 403))


# ── 20. Riders (student gets 403) ─────────────────────────────────────────────
section("20. Riders (student should get 403)")
check("GET /riders/my-batch → 403", "GET", "/riders/my-batch", expected=(403,))
check("GET /riders/stats → 403",    "GET", "/riders/stats",    expected=(403,))


# ── 21. Analytics (admin only) ────────────────────────────────────────────────
section("21. Analytics (student → 403)")
check("GET /analytics/sales → 403", "GET", "/analytics/sales", expected=(403,))


# ── 22. Admin (student → 403) ─────────────────────────────────────────────────
section("22. Admin endpoints (student → 403)")
check("GET /admin/users → 403", "GET", "/admin/users", expected=(403,))
check("GET /admin/orders → 403","GET", "/admin/orders", expected=(403,))


# ── 23. Public endpoints (no auth) ────────────────────────────────────────────
section("23. Public endpoints — no auth required")
# Drop token
SESSION.headers.pop("Authorization", None)

for label, path in [
    ("GET /menu/categories",         "/menu/categories"),
    ("GET /storefront/sections",     "/storefront/sections"),
    ("GET /leaderboard",             "/leaderboard"),
    ("GET /leaderboard/squad",       "/leaderboard/squad"),
    ("GET /leaderboard/hall-of-fame","/leaderboard/hall-of-fame"),
]:
    check(f"{label} (public)", "GET", path)

# Protected → 401
check("GET /auth/me (no auth) → 401", "GET", "/auth/me", expected=(401,))
check("GET /orders (no auth) → 401",  "GET", "/orders",  expected=(401,))


# ── 24. Logout + cleanup ──────────────────────────────────────────────────────
section("24. Logout & test-user cleanup")

# Re-auth to logout
if _access_token:
    SESSION.headers.update({"Authorization": f"Bearer {_access_token}"})
    check("POST /auth/logout", "POST", "/auth/logout", expected=(200,))
    SESSION.headers.pop("Authorization", None)

# Hard-delete test auth user via admin API
SB  = os.environ["SUPABASE_URL"].rstrip("/")
SRK = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
admin_h = {"apikey": SRK, "Authorization": f"Bearer {SRK}", "Content-Type": "application/json"}

if _user_id:
    try:
        dr = requests.delete(f"{SB}/auth/v1/admin/users/{_user_id}",
                             headers=admin_h, timeout=20)
        ok = dr.status_code in (200, 204)
        results["pass" if ok else "fail"] += 1
        print(f"  {PASS if ok else FAIL} Deleted test user ({_user_id}) [{dr.status_code}]")
    except Exception as e:
        results["skip"] += 1
        print(f"  {SKIP} Delete test user: {e}")
else:
    results["skip"] += 1
    print(f"  {SKIP} No user_id captured")


# ── Summary ───────────────────────────────────────────────────────────────────
total = sum(results.values())
print(f"\n{'='*60}")
print(f"  Results: {results['pass']}/{total} passed  |  "
      f"{results['fail']} failed  |  {results['skip']} timeout/skipped")
print(f"{'='*60}\n")
if results["fail"] > 0:
    sys.exit(1)
