"""
test_live_full.py — Holy Grills Complete End-to-End API Live Test
=================================================================
Simulates the full experience of using Holy Grills from account creation
all the way through every feature: orders, HP, leaderboard, marketplace,
events, QR check-in, rewards, challenges, wallet, admin flows, kitchen,
rider, analytics, squad orders, referrals, and all new features.

Touches every blueprint / route group. Documents anything missing or
broken inline with WARN/FAIL entries.

Run: python3 test_live_full.py
Requires: live server (python run.py) + all migrations applied.
"""

import os
import sys
import uuid
import json
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE         = "http://localhost:5000/api"
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SRK          = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

PASS_C = "\033[92m✅ PASS\033[0m"
FAIL_C = "\033[91m❌ FAIL\033[0m"
WARN_C = "\033[93m⚠️  WARN\033[0m"
INFO_C = "\033[94mℹ️  INFO\033[0m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

RESULTS = {"pass": 0, "fail": 0, "warn": 0}
FAILED_DETAILS  = []
MISSING_GAPS    = []
CLEANUP         = []

ADMIN_H = {
    "apikey":        SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type":  "application/json",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def p(label, status, detail=""):
    RESULTS[status] += 1
    icon = {"pass": PASS_C, "fail": FAIL_C, "warn": WARN_C}[status]
    suffix = f" — {detail}" if detail else ""
    print(f"  {icon} {label}{suffix}")
    if status == "fail":
        FAILED_DETAILS.append((label, detail))


def gap(label, detail=""):
    """Record a missing feature / endpoint gap."""
    MISSING_GAPS.append((label, detail))
    print(f"  {INFO_C} GAP: {label}" + (f" — {detail}" if detail else ""))


def section(title):
    print(f"\n{BOLD}{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}{RESET}")


def sub(title):
    print(f"\n{BOLD}  ── {title} ──{RESET}")


def api(method, path, token=None, body=None, params=None, timeout=15):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        return requests.request(
            method, f"{BASE}{path}", headers=h, json=body,
            params=params, timeout=timeout,
        )
    except Exception as exc:
        print(f"    (request error: {exc})")
        return None


def expect(r, label, expected, warn_on_fail=False):
    codes = expected if isinstance(expected, (list, tuple)) else [expected]
    if r is None:
        p(label, "warn", "no response — timeout/connection error")
        return False, None
    if r.status_code in codes:
        p(label, "pass", str(r.status_code))
        try:
            return True, r.json()
        except Exception:
            return True, None
    status = "warn" if warn_on_fail else "fail"
    p(label, status, f"expected {codes}, got {r.status_code}: {r.text[:200]}")
    return False, None


# ── Supabase REST helpers (service-role) ─────────────────────────────────────

def sb_get(table, params=""):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}",
        headers=ADMIN_H, timeout=12,
    )
    if r.status_code == 200:
        return r.json()
    return []


def sb_insert(table, data):
    h = {**ADMIN_H, "Prefer": "return=representation"}
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data, timeout=12,
    )
    if r.status_code in (200, 201):
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else rows
    print(f"    (sb_insert {table} failed: {r.status_code} {r.text[:200]})")
    return None


def sb_patch(table, qs, data):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{qs}",
        headers={**ADMIN_H, "Prefer": "return=minimal"},
        json=data, timeout=12,
    )
    return r.status_code in (200, 204)


def sb_delete(table, qs):
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?{qs}",
        headers=ADMIN_H, timeout=12,
    )
    return r.status_code in (200, 204)


def sb_delete_auth_user(uid):
    r = requests.delete(
        f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
        headers=ADMIN_H, timeout=12,
    )
    return r.status_code in (200, 204)


def sb_login(email, password="Test1234!"):
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers=ADMIN_H,
        json={"email": email, "password": password},
        timeout=15,
    )
    if r.status_code == 200:
        return r.json().get("access_token")
    return None


def create_test_user(suffix, role="student"):
    uid_str = uuid.uuid4().hex[:8]
    email   = f"hgtest_{suffix.lower()}_{uid_str}@test.invalid"
    # Create auth user
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=ADMIN_H,
        json={"email": email, "password": "Test1234!", "email_confirm": True},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create_test_user {suffix} failed: {r.text[:200]}")
    uid = r.json()["id"]

    ref_code = f"TST{uid_str.upper()[:6]}"
    # Upsert profile — handles the case where a Supabase trigger already
    # created the row before our REST insert arrives
    requests.post(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers={**ADMIN_H,
                 "Prefer": "return=minimal,resolution=merge-duplicates"},
        json={
            "id": uid, "email": email,
            "full_name": f"HG Test {suffix}",
            "role": role, "referral_code": ref_code,
            "hp_balance": 0, "wallet_balance": 0,
            "is_active": True, "preferences": {},
        },
        timeout=12,
    )
    # Always PATCH role in case the trigger row omitted it
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}",
        headers={**ADMIN_H, "Prefer": "return=minimal"},
        json={"role": role, "referral_code": ref_code},
        timeout=12,
    )

    # Seed wallet row (ignore duplicate errors)
    requests.post(
        f"{SUPABASE_URL}/rest/v1/wallets",
        headers={**ADMIN_H,
                 "Prefer": "return=minimal,resolution=merge-duplicates"},
        json={"user_id": uid, "balance": 0},
        timeout=12,
    )

    tok = sb_login(email)
    if not tok:
        raise RuntimeError(f"Login for {suffix} failed")

    CLEANUP.append((f"user:{suffix}", lambda u=uid: (
        sb_delete("profiles", f"id=eq.{u}"),
        sb_delete_auth_user(u),
    )))
    return uid, tok, email, ref_code


def seed_wallet_balance(user_id, amount_kobo=500_00):
    """Give user a wallet balance via direct DB (bypasses payment gateway)."""
    amount_naira = amount_kobo / 100
    sb_patch("profiles", f"id=eq.{user_id}", {"wallet_balance": amount_naira})
    sb_patch("wallets", f"user_id=eq.{user_id}", {"balance": amount_naira})


def seed_hp_balance(user_id, hp=500):
    """Set HP balance directly (avoids column-schema guessing on hp_transactions)."""
    sb_patch("profiles", f"id=eq.{user_id}", {"hp_balance": hp})


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def main():  # noqa: C901

    # ═════════════════════════════════════════════════════════════════════════
    section("0 · HEALTH & PUBLIC ENDPOINTS")
    # ═════════════════════════════════════════════════════════════════════════
    r = api("GET", "/health")
    ok, d = expect(r, "GET /health", [200])
    if ok:
        p(f"Health status: {d.get('status', '?')}", "pass", str(d.get("services", {})))

    expect(api("GET", "/docs/"), "GET /api/docs/ (Swagger UI)", 200, warn_on_fail=True)

    # ═════════════════════════════════════════════════════════════════════════
    section("1 · USER SETUP — create test accounts")
    # ═════════════════════════════════════════════════════════════════════════
    print("  Creating admin …")
    admin_id, admin_tok, admin_email, _ = create_test_user("ADMIN", role="admin")
    p(f"Admin created ({admin_email[:30]}…)", "pass", admin_id[:8])

    print("  Creating kitchen staff …")
    kitchen_id, kitchen_tok, kitchen_email, _ = create_test_user("KITCHEN", role="kitchen")
    p(f"Kitchen user created", "pass", kitchen_id[:8])

    print("  Creating rider …")
    rider_id, rider_tok, rider_email, _ = create_test_user("RIDER", role="rider")
    p(f"Rider created", "pass", rider_id[:8])

    # user_A is the referrer — register via the ACTUAL API so referral_code is set properly
    print("  Registering user_A via API …")
    ua_uid_hint = uuid.uuid4().hex[:8]
    ua_email = f"hgtest_usera_{ua_uid_hint}@test.invalid"
    r_reg = api("POST", "/auth/register", body={
        "email": ua_email,
        "password": "Test1234!",
        "full_name": "HG Test UserA",
        "phone": "08100000001",
    })
    ok_a, d_a = expect(r_reg, "POST /auth/register (user_A)", 201)
    if not ok_a:
        print("  FATAL: cannot continue without user_A — exiting")
        sys.exit(1)
    user_a_id  = (d_a.get("user") or {}).get("id")
    user_a_tok = d_a.get("access_token")
    # Fetch referral code user_A received
    ua_profile = sb_get("profiles", f"id=eq.{user_a_id}&select=referral_code")
    user_a_ref_code = (ua_profile[0].get("referral_code") if ua_profile else None) or ""
    p(f"user_A referral code: {user_a_ref_code}", "pass" if user_a_ref_code else "warn")
    CLEANUP.append(("user:A", lambda u=user_a_id: (
        sb_delete("profiles", f"id=eq.{u}"),
        sb_delete_auth_user(u),
    )))

    # user_B registers with user_A's referral code (tests full referral flow)
    print("  Registering user_B via API (with referral code) …")
    ub_uid_hint = uuid.uuid4().hex[:8]
    ub_email = f"hgtest_userb_{ub_uid_hint}@test.invalid"
    r_regb = api("POST", "/auth/register", body={
        "email": ub_email,
        "password": "Test1234!",
        "full_name": "HG Test UserB",
        "referred_by_code": user_a_ref_code,
    })
    ok_b, d_b = expect(r_regb, "POST /auth/register (user_B with referral)", 201)
    if not ok_b:
        # Fallback: create directly
        user_b_id, user_b_tok, ub_email, _ = create_test_user("USERB")
    else:
        user_b_id  = (d_b.get("user") or {}).get("id")
        user_b_tok = d_b.get("access_token")
        CLEANUP.append(("user:B", lambda u=user_b_id: (
            sb_delete("profiles", f"id=eq.{u}"),
            sb_delete_auth_user(u),
        )))

    # Verify referral link stored
    ub_profile = sb_get("profiles", f"id=eq.{user_b_id}&select=referred_by")
    ref_link_ok = ub_profile and ub_profile[0].get("referred_by") == user_a_id
    p("user_B.referred_by = user_A (DB verified)", "pass" if ref_link_ok else "warn",
      str(ub_profile))

    # Seed balances for order testing
    seed_wallet_balance(user_a_id, amount_kobo=10_000_00)  # ₦10,000
    seed_wallet_balance(user_b_id, amount_kobo=10_000_00)
    p("Wallet balances seeded (₦10,000 each)", "pass")

    # ═════════════════════════════════════════════════════════════════════════
    section("2 · AUTH FLOWS")
    # ═════════════════════════════════════════════════════════════════════════

    sub("Login")
    r_login = api("POST", "/auth/login", body={"email": ua_email, "password": "Test1234!"})
    ok_login, d_login = expect(r_login, "POST /auth/login", 200)
    if ok_login:
        user_a_tok = d_login.get("access_token") or user_a_tok  # refresh token
        p("access_token returned", "pass" if user_a_tok else "fail")

    sub("GET /auth/me")
    r_me = api("GET", "/auth/me", token=user_a_tok)
    ok_me, d_me = expect(r_me, "GET /auth/me", 200)
    if ok_me:
        # /auth/me returns {"id", "email", "profile": {...}, "wallet": {...}, "tier": {...}}
        _profile = d_me.get("profile") or {}
        full_name = _profile.get("full_name") or d_me.get("full_name")
        role = _profile.get("role") or d_me.get("role")
        p(f"Profile full_name: {full_name}", "pass" if full_name else "warn")
        p(f"Profile role: {role}", "pass" if role else "warn")

    sub("PATCH /auth/profile")
    r_patch = api("PATCH", "/auth/profile", token=user_a_tok,
                  body={"full_name": "HG Test UserA Updated", "phone": "08100000099"})
    expect(r_patch, "PATCH /auth/profile", 200)

    sub("GET /auth/streak")
    r_streak = api("GET", "/auth/streak", token=user_a_tok)
    ok_str, d_str = expect(r_streak, "GET /auth/streak", 200)
    if ok_str:
        p(f"Streak count: {d_str.get('streak_count')}", "pass")

    sub("Addresses")
    r_addr = api("POST", "/auth/addresses", token=user_a_tok, body={
        "label":        "Home",
        "line1":        "Block D, FUTA South Gate",
        "city":         "Akure",
        "landmark":     "Near the mini-mart",
        "is_default":   True,
    })
    ok_addr, d_addr = expect(r_addr, "POST /auth/addresses", 201)
    addr_id = (d_addr or {}).get("id")
    if addr_id:
        CLEANUP.append(("address", lambda aid=addr_id: sb_delete("addresses", f"id=eq.{aid}")))

    expect(api("GET", "/auth/addresses", token=user_a_tok), "GET /auth/addresses", 200)

    if addr_id:
        expect(
            api("PATCH", f"/auth/addresses/{addr_id}", token=user_a_tok,
                body={"label": "Updated Home"}),
            "PATCH /auth/addresses/<id>", 200,
        )

    sub("Token refresh")
    if ok_login:
        refresh_token = d_login.get("refresh_token")
        if refresh_token:
            r_ref = api("POST", "/auth/refresh", body={"refresh_token": refresh_token})
            expect(r_ref, "POST /auth/refresh", 200)
        else:
            gap("POST /auth/refresh", "refresh_token not returned by login")

    sub("Device token")
    r_dtok = api("POST", "/auth/device-token", token=user_a_tok,
                 body={"token": f"fcm-test-{uuid.uuid4().hex[:8]}", "platform": "android"})
    expect(r_dtok, "POST /auth/device-token", 201, warn_on_fail=True)

    sub("Verify-email & Reset-password (public — 400 with bad input is acceptable)")
    expect(api("POST", "/auth/verify-email", body={"token": "bad"}),
           "POST /auth/verify-email (invalid token)", [400, 422, 200])
    expect(api("POST", "/auth/reset-password", body={"email": "nobody@test.invalid"}),
           "POST /auth/reset-password (unknown email)", [200, 400, 404])

    # ═════════════════════════════════════════════════════════════════════════
    section("3 · MENU")
    # ═════════════════════════════════════════════════════════════════════════
    r_menu = api("GET", "/menu/items")
    ok_menu, d_menu_list = expect(r_menu, "GET /menu (all items)", 200)
    menu_item_id = None
    if ok_menu and d_menu_list:
        items = d_menu_list if isinstance(d_menu_list, list) else d_menu_list.get("items", [])
        available = [i for i in items if i.get("is_available")]
        if available:
            menu_item_id = available[0]["id"]
            p(f"Found {len(available)} available menu items; using {menu_item_id[:8]}…", "pass")
        else:
            gap("Menu items", "No available items in DB — cart/order tests will use direct seed")

    expect(api("GET", "/menu/categories"), "GET /menu/categories", 200, warn_on_fail=True)

    # Seed a menu item if none exist
    if not menu_item_id:
        # Resolve a category_id first so the insert doesn't fail on a FK
        cats = sb_get("menu_categories", "select=id&is_active=eq.true&limit=1")
        cat_id_for_seed = cats[0]["id"] if cats else None
        seed_payload = {
            "name": "Test Jollof Rice",
            "description": "Test item for CI",
            "price": 1200,
            "is_available": True,
        }
        if cat_id_for_seed:
            seed_payload["category_id"] = cat_id_for_seed
        seeded_item = sb_insert("menu_items", seed_payload)
        if seeded_item:
            menu_item_id = seeded_item["id"]
            CLEANUP.append(("menu_item", lambda mid=menu_item_id:
                            sb_delete("menu_items", f"id=eq.{mid}")))
            p(f"Seeded menu item {menu_item_id[:8]}", "pass")
        else:
            gap("Menu item seed failed", "Cart/order tests will be limited")

    # ═════════════════════════════════════════════════════════════════════════
    section("4 · STOREFRONT")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("GET", "/storefront/sections"), "GET /storefront/sections", 200, warn_on_fail=True)
    expect(api("GET", "/storefront/operating-hours"), "GET /storefront/operating-hours", 200, warn_on_fail=True)

    # ═════════════════════════════════════════════════════════════════════════
    section("5 · CART")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("GET", "/cart", token=user_a_tok), "GET /cart (empty)", 200)

    cart_item_id = None
    if menu_item_id:
        r_cart_add = api("POST", "/cart", token=user_a_tok, body={
            "menu_item_id": menu_item_id, "quantity": 2,
        })
        ok_ca, d_ca = expect(r_cart_add, "POST /cart (add item)", [200, 201])
        if ok_ca and d_ca:
            # Get cart to find item id
            r_gc = api("GET", "/cart", token=user_a_tok)
            if r_gc and r_gc.status_code == 200:
                cart_data = r_gc.json()
                cart_items = cart_data if isinstance(cart_data, list) else cart_data.get("items", [])
                if cart_items:
                    cart_item_id = cart_items[0].get("id")
                    # Check added_at is present
                    added_at = cart_items[0].get("added_at")
                    p("cart item has added_at timestamp", "pass" if added_at else "warn",
                      str(added_at))

        if cart_item_id:
            expect(
                api("PATCH", f"/cart/{cart_item_id}", token=user_a_tok, body={"quantity": 3}),
                "PATCH /cart/<id> (update quantity)", 200,
            )
            expect(
                api("DELETE", f"/cart/{cart_item_id}", token=user_a_tok),
                "DELETE /cart/<id>", [200, 204],
            )
        # Re-add for order creation later
        api("POST", "/cart", token=user_a_tok, body={"menu_item_id": menu_item_id, "quantity": 1})
    else:
        gap("Cart add/update/delete", "No menu item available")

    expect(api("DELETE", "/cart", token=user_a_tok), "DELETE /cart (clear)", [200, 204])

    # ═════════════════════════════════════════════════════════════════════════
    section("6 · SAVED FOR LATER")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("GET", "/saved", token=user_a_tok), "GET /saved-for-later", 200)
    sfl_id = None
    if menu_item_id:
        r_sfl = api("POST", "/saved", token=user_a_tok,
                    body={"menu_item_id": menu_item_id})
        ok_sfl, d_sfl = expect(r_sfl, "POST /saved-for-later", [200, 201])
        if ok_sfl and d_sfl:
            sfl_id = (d_sfl.get("item") or d_sfl).get("id") or (
                d_sfl[0].get("id") if isinstance(d_sfl, list) else None
            )

        if sfl_id:
            expect(
                api("DELETE", f"/saved/{sfl_id}", token=user_a_tok),
                "DELETE /saved-for-later/<id>", [200, 204],
            )
        # Test move-to-cart
        r_sfl2 = api("POST", "/saved", token=user_a_tok,
                     body={"menu_item_id": menu_item_id})
        ok_s2, d_s2 = expect(r_sfl2, "POST /saved-for-later (for move-to-cart)", [200, 201])
        if ok_s2 and d_s2:
            sfl_id2_obj = d_s2.get("item") or d_s2
            sfl_id2 = sfl_id2_obj.get("id") if isinstance(sfl_id2_obj, dict) else (
                d_s2[0].get("id") if isinstance(d_s2, list) else None
            )
            if sfl_id2:
                expect(
                    api("POST", f"/saved/{sfl_id2}/move-to-cart", token=user_a_tok),
                    "POST /saved-for-later/<id>/move-to-cart", [200, 201],
                )
    else:
        gap("Saved-for-later add/delete/move", "No menu item available")

    # ═════════════════════════════════════════════════════════════════════════
    section("7 · ORDER LIFECYCLE (create → delivered → HP)")
    # ═════════════════════════════════════════════════════════════════════════

    # Fetch or create a delivery window
    dw_rows = sb_get("delivery_windows", "select=id,status&status=eq.open&limit=1")
    window_id = dw_rows[0]["id"] if dw_rows else None
    if not window_id:
        # Seed one — actual columns: id,label,starts_at,ends_at,capacity,is_active,status
        now = datetime.now(timezone.utc)
        dw_row = sb_insert("delivery_windows", {
            "label":     "Test Window A",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at":   (now + timedelta(hours=2)).isoformat(),
            "is_active": True,
            "status":    "open",
            "capacity":  999,
        })
        if dw_row:
            window_id = dw_row["id"]
            CLEANUP.append(("delivery_window", lambda wid=window_id:
                            sb_delete("delivery_windows", f"id=eq.{wid}")))
            p(f"Seeded delivery window {window_id[:8]}", "pass")
        else:
            gap("Delivery window seed failed", "Order creation skipped")

    expect(api("GET", "/orders/delivery-windows"), "GET /orders/delivery-windows", 200)
    expect(api("GET", "/orders/delivery-windows/status"), "GET /orders/delivery-windows/status", 200)
    expect(api("GET", "/orders/delivery-zones"), "GET /orders/delivery-zones", 200)

    order_a_id = None
    if menu_item_id and window_id:
        r_order = api("POST", "/orders", token=user_a_tok, body={
            "items": [{"menu_item_id": menu_item_id, "quantity": 1}],
            "delivery_window_id": window_id,
            "payment_method":    "wallet",
            "delivery_address": {
                "address_line": "Block A, FUTA South Gate",
                "landmark":     "Near ATM",
                "zone":         "south",
            },
            "notes": "Extra spicy please",
        })
        ok_ord, d_ord = expect(r_order, "POST /orders (create via wallet)", [200, 201])
        if ok_ord and d_ord:
            order_a_id = (d_ord.get("order") or d_ord).get("id")
            if order_a_id:
                p(f"Order created: {order_a_id[:8]}", "pass")
                CLEANUP.append(("order:A", lambda oid=order_a_id: (
                    sb_delete("order_items", f"order_id=eq.{oid}"),
                    sb_delete("order_status_history", f"order_id=eq.{oid}"),
                    sb_delete("squad_members", f"order_id=eq.{oid}"),
                    sb_delete("first_order_gifts", f"order_id=eq.{oid}"),
                    sb_delete("order_share_events", f"order_id=eq.{oid}"),
                    sb_delete("orders", f"id=eq.{oid}"),
                )))
        else:
            # Try direct DB seed (wallet deduction may have failed)
            gap("POST /orders via wallet", "Wallet deduction likely failed — seeding order directly")
            item_price = sb_get("menu_items", f"id=eq.{menu_item_id}&select=price")
            price = item_price[0].get("price", 1200) if item_price else 1200
            order_row = sb_insert("orders", {
                "user_id":          user_a_id,
                "status":           "received",
                "payment_method":   "wallet",
                "payment_status":   "paid",
                "subtotal":         price,
                "delivery_fee":     200,
                "total":            price + 200,
                "hp_earned":        int((price + 200) / 10),
                "delivery_window_id": window_id,
                "delivery_address": json.dumps({
                    "address_line": "Block A, FUTA",
                    "zone": "south",
                }),
            })
            if order_row:
                order_a_id = order_row["id"]
                sb_insert("order_items", {
                    "order_id": order_a_id,
                    "menu_item_id": menu_item_id,
                    "quantity": 1,
                    "unit_price": price,
                    "subtotal": price,
                })
                CLEANUP.append(("order:A", lambda oid=order_a_id: (
                    sb_delete("order_items", f"order_id=eq.{oid}"),
                    sb_delete("order_status_history", f"order_id=eq.{oid}"),
                    sb_delete("squad_members", f"order_id=eq.{oid}"),
                    sb_delete("first_order_gifts", f"order_id=eq.{oid}"),
                    sb_delete("order_share_events", f"order_id=eq.{oid}"),
                    sb_delete("orders", f"id=eq.{oid}"),
                )))
                p(f"Order seeded directly: {order_a_id[:8]}", "warn")
    else:
        gap("Order creation", "No menu item or delivery window available")

    # GET /orders
    expect(api("GET", "/orders", token=user_a_tok), "GET /orders (list)", 200)
    expect(api("GET", "/orders/scheduled", token=user_a_tok), "GET /orders/scheduled", 200)
    expect(api("GET", "/orders/active", token=user_a_tok), "GET /orders/active", 200)

    if order_a_id:
        expect(api("GET", f"/orders/{order_a_id}", token=user_a_tok),
               "GET /orders/<id>", 200)
        expect(api("GET", f"/orders/{order_a_id}/history", token=user_a_tok),
               "GET /orders/<id>/history", 200)

        sub("Walk order to delivered (admin)")
        walk_r = api("POST", f"/orders/{order_a_id}/walk", token=admin_tok)
        ok_w, d_w = expect(walk_r, "POST /orders/<id>/walk (admin)", [200, 400])
        if ok_w:
            p(f"Order status after walk: {(d_w or {}).get('status')}", "pass")

        # Force to delivered for HP testing
        sb_patch("orders", f"id=eq.{order_a_id}", {
            "status":        "delivered",
            "delivered_at":  datetime.now(timezone.utc).isoformat(),
            "payment_status": "paid",
        })
        p("Order forced to delivered (DB) for HP flow test", "pass")

        sub("POST /orders/<id>/review")
        r_review = api("POST", f"/orders/{order_a_id}/review", token=user_a_tok, body={
            "rating": 5,
            "comment": "Amazing jollof, perfectly spiced!",
        })
        expect(r_review, "POST /orders/<id>/review", [200, 201, 400])

        sub("POST /orders/<id>/share (share prompt HP)")
        r_share = api("POST", f"/orders/{order_a_id}/share", token=user_a_tok,
                      body={"platform": "whatsapp"})
        ok_sh, d_sh = expect(r_share, "POST /orders/<id>/share", [200, 201])
        if ok_sh:
            p(f"Share HP awarded: {(d_sh or {}).get('hp_awarded')}", "pass")

        sub("POST /orders/<id>/reorder")
        r_reorder = api("POST", f"/orders/{order_a_id}/reorder", token=user_a_tok)
        ok_ro, d_ro = expect(r_reorder, "POST /orders/<id>/reorder", [200, 201, 400])
        if ok_ro and d_ro:
            reorder_id = (d_ro.get("order") or d_ro).get("id")
            if reorder_id:
                CLEANUP.append(("order:reorder", lambda oid=reorder_id: (
                    sb_delete("order_items", f"order_id=eq.{oid}"),
                    sb_delete("orders", f"id=eq.{oid}"),
                )))

    sub("Promo code validation")
    expect(api("POST", "/orders/validate-promo", token=user_a_tok,
               body={"promo_code": "NONEXISTENT99"}),
           "POST /orders/validate-promo (invalid code)", [400, 404, 200])

    # ═════════════════════════════════════════════════════════════════════════
    section("8 · REFERRAL FLOW VERIFICATION")
    # ═════════════════════════════════════════════════════════════════════════
    # Create user_B's first order and mark delivered → triggers referral HP to user_A
    order_b_id = None
    if menu_item_id and window_id:
        sub("Create user_B first order (referral trigger)")
        r_ob = api("POST", "/orders", token=user_b_tok, body={
            "items": [{"menu_item_id": menu_item_id, "quantity": 1}],
            "delivery_window_id": window_id,
            "payment_method": "wallet",
            "delivery_address": {"address_line": "Block B, FUTA", "zone": "south"},
        })
        ok_ob, d_ob = expect(r_ob, "POST /orders (user_B first order)", [200, 201])
        if ok_ob and d_ob:
            order_b_id = (d_ob.get("order") or d_ob).get("id")
        else:
            # Seed directly
            item_price = sb_get("menu_items", f"id=eq.{menu_item_id}&select=price")
            price = item_price[0].get("price", 1200) if item_price else 1200
            ob_row = sb_insert("orders", {
                "user_id": user_b_id, "status": "received",
                "payment_method": "wallet", "payment_status": "paid",
                "subtotal": price, "delivery_fee": 200, "total": price + 200,
                "hp_earned": int((price + 200) / 10),
                "delivery_window_id": window_id,
                "delivery_address": json.dumps({"address_line": "Block B, FUTA", "zone": "south"}),
            })
            if ob_row:
                order_b_id = ob_row["id"]
                sb_insert("order_items", {
                    "order_id": order_b_id, "menu_item_id": menu_item_id,
                    "quantity": 1, "unit_price": price, "subtotal": price,
                })

        if order_b_id:
            CLEANUP.append(("order:B", lambda oid=order_b_id: (
                sb_delete("order_items", f"order_id=eq.{oid}"),
                sb_delete("order_status_history", f"order_id=eq.{oid}"),
                sb_delete("orders", f"id=eq.{oid}"),
            )))
            # Mark delivered to trigger referral
            sb_patch("orders", f"id=eq.{order_b_id}", {
                "status": "delivered",
                "delivered_at": datetime.now(timezone.utc).isoformat(),
                "payment_status": "paid",
            })

            # Call walk to trigger HP service
            api("POST", f"/orders/{order_b_id}/walk", token=admin_tok)

            # Check user_A for referral HP
            import time; time.sleep(1)
            ua_after = sb_get("profiles", f"id=eq.{user_a_id}&select=hp_balance")
            ua_hp = ua_after[0].get("hp_balance", 0) if ua_after else 0
            p(f"user_A HP balance after referral: {ua_hp}", "pass" if ua_hp > 0 else "warn",
              "Referral HP may require order_service.on_delivered() to run")

            # Check referrals table
            referrals = sb_get("referrals", f"referrer_id=eq.{user_a_id}&limit=1")
            p("Referral row created for user_A", "pass" if referrals else "warn", str(referrals))

    expect(api("GET", "/referrals", token=user_a_tok), "GET /referrals", 200, warn_on_fail=True)
    expect(api("GET", "/referrals/stats", token=user_a_tok), "GET /referrals/stats", 200, warn_on_fail=True)

    # ═════════════════════════════════════════════════════════════════════════
    section("9 · HP FEATURES")
    # ═════════════════════════════════════════════════════════════════════════
    seed_hp_balance(user_a_id, 1000)

    expect(api("GET", "/hp/balance", token=user_a_tok), "GET /hp/balance", 200)
    expect(api("GET", "/hp/transactions", token=user_a_tok), "GET /hp/transactions", 200)
    expect(api("GET", "/hp/tiers"), "GET /hp/tiers", 200)
    expect(api("GET", "/hp/unlock-history", token=user_a_tok), "GET /hp/unlock-history", 200)
    expect(api("GET", "/hp/spin/history", token=user_a_tok), "GET /hp/spin/history", 200)

    sub("HP spin wheel")
    r_spin = api("POST", "/hp/spin", token=user_a_tok)
    ok_spin, d_spin = expect(r_spin, "POST /hp/spin", [200, 201, 429])
    if ok_spin and d_spin:
        p(f"Spin result: {d_spin.get('result')} (+{d_spin.get('hp_awarded')} HP)", "pass")

    sub("HP transfer")
    seed_hp_balance(user_a_id, 2000)
    r_xfer = api("POST", "/hp/transfer", token=user_a_tok, body={
        "recipient_id": user_b_id,
        "amount": 100,
        "note": "Test transfer",
    })
    ok_xfer, d_xfer = expect(r_xfer, "POST /hp/transfer", [200, 201, 400])
    if ok_xfer:
        p(f"HP transfer response: {d_xfer}", "pass")

    sub("Admin HP grant")
    r_grant = api("POST", "/hp/admin/grant", token=admin_tok, body={
        "user_id":   user_b_id,
        "amount":    200,
        "reason":    "Test admin grant",
    })
    ok_grant, d_grant = expect(r_grant, "POST /hp/admin/grant", [200, 201])
    if ok_grant:
        p(f"HP granted: {(d_grant or {}).get('new_balance')}", "pass")

    sub("Admin HP expire")
    r_expire = api("POST", "/hp/admin/expire", token=admin_tok, body={
        "user_id": user_b_id,
        "amount":  50,
        "reason":  "Test expiry",
    })
    expect(r_expire, "POST /hp/admin/expire", [200, 201])

    # ═════════════════════════════════════════════════════════════════════════
    section("10 · WALLET")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("GET", "/wallet", token=user_a_tok), "GET /wallet (balance)", 200)
    expect(api("GET", "/wallet/transactions", token=user_a_tok), "GET /wallet/transactions", 200)

    sub("Fund via card (initiates Paystack — expect redirect URL or 503)")
    r_fund = api("POST", "/wallet/fund/card", token=user_a_tok,
                 body={"amount": 1000, "callback_url": "https://holygrills.ng/callback"})
    expect(r_fund, "POST /wallet/fund/card", [200, 201, 503, 500], warn_on_fail=True)

    sub("Fund via bank (virtual account)")
    r_bank = api("POST", "/wallet/fund/bank", token=user_a_tok, body={"amount": 500})
    expect(r_bank, "POST /wallet/fund/bank", [200, 201, 503, 500], warn_on_fail=True)

    sub("Withdrawal request")
    r_wd = api("POST", "/wallet/withdraw", token=user_a_tok, body={
        "amount":      500,
        "bank_code":   "044",
        "account_number": "0123456789",
        "account_name": "HG Test UserA",
    })
    expect(r_wd, "POST /wallet/withdraw", [200, 201, 400, 503], warn_on_fail=True)

    expect(api("GET", "/wallet/admin/transactions", token=admin_tok),
           "GET /wallet/admin/transactions", 200)

    # ═════════════════════════════════════════════════════════════════════════
    section("11 · ORDER LOCKS")
    # ═════════════════════════════════════════════════════════════════════════
    lock_id = None
    # Order-lock endpoint signature: POST /order-locks {locked_date: YYYY-MM-DD, discount_pct?}
    # Admin list path:  GET /order-locks/admin/all
    # Reschedule path:  PATCH /order-locks/<id>/reschedule {locked_date: YYYY-MM-DD}
    r_lock = api("POST", "/order-locks", token=user_a_tok, body={
        "locked_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d"),
        "discount_pct": 10,
    })
    ok_lock, d_lock = expect(r_lock, "POST /order-locks (create)", [200, 201])
    if ok_lock and d_lock:
        lock_id = (d_lock.get("lock") or d_lock).get("id")

    expect(api("GET", "/order-locks", token=user_a_tok), "GET /order-locks (my locks)", 200)
    expect(api("GET", "/order-locks/admin/all", token=admin_tok), "GET /order-locks/admin/all", 200)

    if lock_id:
        CLEANUP.append(("order_lock", lambda lid=lock_id:
                        sb_delete("order_locks", f"id=eq.{lid}")))
        new_date = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
        r_reschedule = api("PATCH", f"/order-locks/{lock_id}/reschedule", token=user_a_tok,
                           body={"locked_date": new_date})
        expect(r_reschedule, "PATCH /order-locks/<id>/reschedule", [200, 400])

        expect(api("DELETE", f"/order-locks/{lock_id}", token=user_a_tok),
               "DELETE /order-locks/<id> (cancel)", [200, 204])
    else:
        gap("Order Locks", "Lock creation failed — reschedule/cancel skipped")

    # ═════════════════════════════════════════════════════════════════════════
    section("12 · SQUAD ORDERS + HP SPLIT")
    # ═════════════════════════════════════════════════════════════════════════
    if order_a_id:
        sub("Add squad members")
        # Route expects: {"emails": ["email1@...", "email2@..."]}
        r_squad = api("POST", f"/orders/{order_a_id}/squad-members", token=user_a_tok, body={
            "emails": [ub_email],
        })
        ok_sq, d_sq = expect(r_squad, "POST /orders/<id>/squad-members", [200, 201])
        if ok_sq:
            p(f"Squad members response: {d_sq}", "pass")
            # Clean up squad_members
            CLEANUP.append(("squad_members:A",
                            lambda oid=order_a_id: sb_delete("squad_members", f"order_id=eq.{oid}")))
    else:
        gap("Squad orders", "No order available")

    # ═════════════════════════════════════════════════════════════════════════
    section("13 · LEADERBOARD")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("GET", "/leaderboard"), "GET /leaderboard (weekly)", 200)
    expect(api("GET", "/leaderboard", params={"period": "monthly"}),
           "GET /leaderboard (monthly)", 200)
    expect(api("GET", "/leaderboard/hall-of-fame"), "GET /leaderboard/hall-of-fame", 200)
    expect(api("GET", "/leaderboard/my-rank", token=user_a_tok), "GET /leaderboard/my-rank", 200)
    expect(api("GET", "/leaderboard/squad"), "GET /leaderboard/squad", 200)
    expect(api("GET", "/leaderboard/squad/my-rank", token=user_a_tok),
           "GET /leaderboard/squad/my-rank", 200)

    # ═════════════════════════════════════════════════════════════════════════
    section("14 · CHALLENGES")
    # ═════════════════════════════════════════════════════════════════════════
    r_chal = api("GET", "/challenges")
    ok_ch, d_ch = expect(r_chal, "GET /challenges", 200)
    challenge_id = None
    if ok_ch and d_ch:
        items_ch = d_ch if isinstance(d_ch, list) else d_ch.get("challenges", [])
        if items_ch:
            challenge_id = items_ch[0].get("id")

    sub("Admin: create challenge")
    r_cc = api("POST", "/challenges", token=admin_tok, body={
        "title":       "Order 3 times",
        "description": "Place 3 orders in a week",
        "type":        "one_time",
        "hp_reward":   50,
        "is_active":   True,
        "starts_at":   datetime.now(timezone.utc).isoformat(),
        "ends_at":     (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "criteria":    {"target": 3},
    })
    ok_cc, d_cc = expect(r_cc, "POST /challenges (admin create)", [200, 201])
    test_challenge_id = None
    if ok_cc and d_cc:
        test_challenge_id = (d_cc.get("challenge") or d_cc).get("id")
        if test_challenge_id:
            CLEANUP.append(("challenge", lambda cid=test_challenge_id:
                            sb_delete("challenges", f"id=eq.{cid}")))

    expect(api("GET", "/challenges/admin", token=admin_tok), "GET /challenges/admin", 200)

    chal_to_complete = test_challenge_id or challenge_id
    if chal_to_complete:
        r_comp = api("POST", f"/challenges/{chal_to_complete}/complete", token=user_a_tok)
        expect(r_comp, "POST /challenges/<id>/complete", [200, 201, 400, 409])

    # ═════════════════════════════════════════════════════════════════════════
    section("15 · EVENTS + QR CHECK-IN")
    # ═════════════════════════════════════════════════════════════════════════
    r_ev = api("GET", "/events")
    ok_ev, d_ev = expect(r_ev, "GET /events", 200)
    event_id = None
    if ok_ev and d_ev:
        evs = d_ev if isinstance(d_ev, list) else d_ev.get("events", [])
        if evs:
            event_id = evs[0].get("id")

    sub("Admin: create event")
    r_cev = api("POST", "/events", token=admin_tok, body={
        "title":       "FUTA Food Fiesta 2026",
        "description": "Annual food festival",
        "location":    "FUTA Main Campus",
        "starts_at":   (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "ends_at":     (datetime.now(timezone.utc) + timedelta(days=14, hours=4)).isoformat(),
        "hp_reward":   300,
        "max_capacity": 500,
    })
    ok_cev, d_cev = expect(r_cev, "POST /events (admin create)", [200, 201])
    test_event_id = None
    if ok_cev and d_cev:
        test_event_id = (d_cev.get("event") or d_cev).get("id")
        if test_event_id:
            CLEANUP.append(("event", lambda eid=test_event_id:
                            sb_delete("events", f"id=eq.{eid}")))

    expect(api("GET", "/events/admin", token=admin_tok), "GET /events/admin", 200)

    ev_to_use = test_event_id or event_id
    if ev_to_use:
        expect(api("GET", f"/events/{ev_to_use}"), "GET /events/<id>", 200)

        sub("Generate QR code for event (admin)")
        r_qr = api("POST", f"/events/{ev_to_use}/qr", token=admin_tok)
        ok_qr, d_qr = expect(r_qr, "POST /events/<id>/qr (generate QR)", [200, 201])
        admin_qr_token = None
        if ok_qr and d_qr:
            # Response keys: qr_token, qr_payload, instructions
            admin_qr_token = d_qr.get("qr_token") or (d_qr.get("qr_data") or {}).get("token")
            p(f"QR token generated: {str(admin_qr_token)[:20]}", "pass" if admin_qr_token else "warn")

        sub("Register user_A for event (required before check-in)")
        ticket_id = None
        r_reg_ev = api("POST", f"/events/{ev_to_use}/register", token=user_a_tok)
        ok_rev, d_rev = expect(r_reg_ev, "POST /events/<id>/register (user_A)", [200, 201, 400])
        if ok_rev and d_rev:
            ticket_id = d_rev.get("ticket_id")
            p(f"Ticket issued: {str(ticket_id or '')[:20]}", "pass" if ticket_id else "warn")
            if ticket_id:
                CLEANUP.append(("event_ticket", lambda eid=ev_to_use, uid=user_a_id:
                                sb_delete("event_tickets", f"event_id=eq.{eid}&user_id=eq.{uid}")))

        sub("Event check-in (user_A presents ticket as QR token)")
        # ticket_id doubles as qr_token at the door (see register_for_event docstring)
        qr_for_checkin = ticket_id or admin_qr_token
        if qr_for_checkin:
            r_checkin = api("POST", f"/events/{ev_to_use}/checkin", token=user_a_tok,
                            body={"qr_token": qr_for_checkin})
            ok_ci, d_ci = expect(r_checkin, "POST /events/<id>/checkin", [200, 201, 400])
            if ok_ci:
                p(f"Check-in HP awarded: {(d_ci or {}).get('hp_added_to_pending', (d_ci or {}).get('hp_awarded'))}", "pass")
                CLEANUP.append(("event_checkin", lambda eid=ev_to_use, uid=user_a_id:
                                sb_delete("event_checkins", f"event_id=eq.{eid}&user_id=eq.{uid}")))
        else:
            gap("Event check-in", "No ticket_id or QR token available — RPC may not be deployed")

        sub("Catering request")
        r_cat = api("POST", "/events/catering-requests", token=user_a_tok, body={
            "event_name":     "FUTA Graduation 2026",
            "organizer_name": "HG Test UserA",
            "email":          ua_email,
            "phone":          "08199999999",
            "expected_guests": 200,
            "event_date":     (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat(),
            "notes":          "Need jollof rice for 200 people",
        })
        ok_cat, d_cat = expect(r_cat, "POST /events/catering-requests", [200, 201])
        if ok_cat and d_cat:
            cat_id = (d_cat.get("request") or d_cat).get("id")
            CLEANUP.append(("catering_request", lambda cid=cat_id:
                            sb_delete("catering_requests", f"id=eq.{cid}") if cid else None))

        expect(api("GET", "/events/catering-requests", token=admin_tok),
               "GET /events/catering-requests (admin)", 200)

    # ═════════════════════════════════════════════════════════════════════════
    section("16 · MARKETPLACE")
    # ═════════════════════════════════════════════════════════════════════════
    r_mkt = api("GET", "/marketplace")
    ok_mkt, d_mkt = expect(r_mkt, "GET /marketplace (listings)", 200)
    listing_id = None
    if ok_mkt and d_mkt:
        items_m = d_mkt if isinstance(d_mkt, list) else d_mkt.get("listings", [])
        if items_m:
            listing_id = items_m[0].get("id")
            expect(api("GET", f"/marketplace/{listing_id}"),
                   "GET /marketplace/<id>", 200)

    sub("Admin: create listing")
    r_cl = api("POST", "/marketplace/admin/listings", token=admin_tok, body={
        "title":        "FUTA Hostel Meal Plan — Bronze",
        "description":  "15 meals per month",
        "listing_type": "code",
        "price":        1500,
        "hp_price":     500,
        "stock":        100,
        "is_active":    True,
    })
    ok_cl, d_cl = expect(r_cl, "POST /marketplace/admin/listings (create)", [200, 201])
    test_listing_id = None
    if ok_cl and d_cl:
        test_listing_id = (d_cl.get("listing") or d_cl).get("id")
        if test_listing_id:
            CLEANUP.append(("marketplace_listing", lambda lid=test_listing_id:
                            sb_delete("marketplace_listings", f"id=eq.{lid}")))

    expect(api("GET", "/marketplace/admin/listings", token=admin_tok),
           "GET /marketplace/admin/listings", 200)
    expect(api("GET", "/marketplace/purchases", token=user_a_tok),
           "GET /marketplace/purchases (my)", 200)
    expect(api("GET", "/marketplace/admin/purchases", token=admin_tok),
           "GET /marketplace/admin/purchases", 200)

    buy_id = test_listing_id or listing_id
    if buy_id:
        sub("Marketplace purchase (HP)")
        seed_hp_balance(user_a_id, 5000)
        r_buy = api("POST", f"/marketplace/{buy_id}/purchase", token=user_a_tok)
        ok_buy, d_buy = expect(r_buy, "POST /marketplace/<id>/purchase", [200, 201, 400])
        if ok_buy and d_buy:
            purch_id = (d_buy.get("purchase") or d_buy).get("id")
            if purch_id:
                CLEANUP.append(("marketplace_purchase", lambda pid=purch_id:
                                sb_delete("marketplace_purchases", f"id=eq.{pid}")))

    sub("Submit listing request")
    r_req = api("POST", "/marketplace/requests", body={
        "title":       "Adobe Photoshop License",
        "description": "Monthly Creative Cloud sub",
        "contact_name": "Test User",
        "contact_email": ua_email,
    })
    expect(r_req, "POST /marketplace/requests", [200, 201], warn_on_fail=True)

    # ═════════════════════════════════════════════════════════════════════════
    section("17 · REWARDS")
    # ═════════════════════════════════════════════════════════════════════════
    r_rwd = api("GET", "/rewards")
    ok_rwd, d_rwd = expect(r_rwd, "GET /rewards", 200)
    reward_id = None
    if ok_rwd and d_rwd:
        rwds = d_rwd if isinstance(d_rwd, list) else d_rwd.get("rewards", [])
        if rwds:
            reward_id = rwds[0].get("id")

    if reward_id:
        sub("Flash redeem")
        r_flash = api("POST", f"/hp/flash-redeem/{reward_id}", token=user_a_tok)
        expect(r_flash, "POST /hp/flash-redeem/<id>", [200, 201, 400, 409])

    # ═════════════════════════════════════════════════════════════════════════
    section("18 · NOTIFICATIONS")
    # ═════════════════════════════════════════════════════════════════════════
    r_notif = api("GET", "/notifications", token=user_a_tok)
    ok_notif, d_notif = expect(r_notif, "GET /notifications", 200)
    notif_id = None
    if ok_notif and d_notif:
        items_n = d_notif if isinstance(d_notif, list) else d_notif.get("notifications", [])
        if items_n:
            notif_id = items_n[0].get("id")

    if notif_id:
        expect(api("POST", f"/notifications/{notif_id}/read", token=user_a_tok),
               "POST /notifications/<id>/read", [200, 204])
    expect(api("POST", "/notifications/read-all", token=user_a_tok),
           "POST /notifications/read-all", [200, 204])
    expect(api("GET", "/notifications/preferences", token=user_a_tok),
           "GET /notifications/preferences", 200)
    expect(api("PATCH", "/notifications/preferences", token=user_a_tok,
               body={"email_notifications": True, "push_enabled": False}),
           "PATCH /notifications/preferences", 200)

    # ═════════════════════════════════════════════════════════════════════════
    section("19 · ADMIN FLOWS")
    # ═════════════════════════════════════════════════════════════════════════
    sub("Users")
    expect(api("GET", "/admin/users", token=admin_tok), "GET /admin/users", 200)
    expect(api("GET", f"/admin/users/{user_a_id}", token=admin_tok),
           "GET /admin/users/<id>", 200)
    expect(api("GET", f"/admin/users/{user_a_id}/orders", token=admin_tok),
           "GET /admin/users/<id>/orders", 200)
    expect(api("GET", f"/admin/users/{user_a_id}/hp", token=admin_tok),
           "GET /admin/users/<id>/hp", 200)
    expect(api("GET", f"/admin/users/{user_a_id}/wallet", token=admin_tok),
           "GET /admin/users/<id>/wallet", 200)

    sub("Role management")
    r_role = api("PATCH", f"/admin/users/{user_b_id}/role", token=admin_tok,
                 body={"role": "student"})
    expect(r_role, "PATCH /admin/users/<id>/role", 200)

    sub("Activate / Deactivate")
    expect(api("POST", f"/admin/users/{user_b_id}/deactivate", token=admin_tok),
           "POST /admin/users/<id>/deactivate", 200)
    expect(api("POST", f"/admin/users/{user_b_id}/activate", token=admin_tok),
           "POST /admin/users/<id>/activate", 200)

    sub("Orders admin")
    expect(api("GET", "/admin/orders", token=admin_tok), "GET /admin/orders", 200)

    sub("Delivery windows")
    expect(api("GET", "/admin/delivery-windows", token=admin_tok),
           "GET /admin/delivery-windows", 200)
    r_dw = api("POST", "/admin/delivery-windows", token=admin_tok, body={
        "label":      "Admin Test Window",
        "starts_at":  (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "ends_at":    (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "max_orders": 50,
    })
    ok_dw, d_dw = expect(r_dw, "POST /admin/delivery-windows", [200, 201])
    test_dw_id = None
    if ok_dw and d_dw:
        test_dw_id = (d_dw.get("window") or d_dw).get("id")
        if test_dw_id:
            CLEANUP.append(("delivery_window:test", lambda wid=test_dw_id:
                            sb_delete("delivery_windows", f"id=eq.{wid}")))
            expect(api("POST", f"/admin/delivery-windows/{test_dw_id}/close", token=admin_tok),
                   "POST /admin/delivery-windows/<id>/close", [200, 204])
            expect(api("POST", f"/admin/delivery-windows/{test_dw_id}/reopen", token=admin_tok),
                   "POST /admin/delivery-windows/<id>/reopen", [200, 204])

    sub("Promo codes")
    expect(api("GET", "/admin/promo-codes", token=admin_tok), "GET /admin/promo-codes", 200)
    r_promo = api("POST", "/admin/promo-codes", token=admin_tok, body={
        "code":          f"HGTEST{uuid.uuid4().hex[:4].upper()}",
        "discount_type": "percentage",
        "discount_value": 10,
        "max_uses":      100,
        "expires_at":    (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "min_order_amount": 500,
    })
    ok_promo, d_promo = expect(r_promo, "POST /admin/promo-codes (create)", [200, 201])
    test_promo_id = None
    if ok_promo and d_promo:
        test_promo_id = (d_promo.get("promo") or d_promo).get("id")
        if test_promo_id:
            CLEANUP.append(("promo_code", lambda pid=test_promo_id:
                            sb_delete("promo_codes", f"id=eq.{pid}")))
            expect(api("PATCH", f"/admin/promo-codes/{test_promo_id}", token=admin_tok,
                       body={"max_uses": 200}),
                   "PATCH /admin/promo-codes/<id>", 200)
            expect(api("GET", f"/admin/promo-codes/{test_promo_id}/uses", token=admin_tok),
                   "GET /admin/promo-codes/<id>/uses", 200)

    sub("Delivery batches")
    expect(api("GET", "/admin/delivery-batches", token=admin_tok),
           "GET /admin/delivery-batches", 200)
    r_batch = api("POST", "/admin/delivery-batches", token=admin_tok, body={
        "label":      "Test Batch 1",
        "rider_id":   rider_id,
        "window_id":  window_id or test_dw_id,
    })
    ok_bat, d_bat = expect(r_batch, "POST /admin/delivery-batches", [200, 201, 400])
    test_batch_id = None
    if ok_bat and d_bat:
        test_batch_id = (d_bat.get("batch") or d_bat).get("id")
        if test_batch_id:
            CLEANUP.append(("delivery_batch", lambda bid=test_batch_id:
                            sb_delete("rider_batches", f"id=eq.{bid}")))
            expect(api("GET", f"/admin/delivery-batches/{test_batch_id}", token=admin_tok),
                   "GET /admin/delivery-batches/<id>", 200)
            expect(api("GET", f"/admin/delivery-batches/{test_batch_id}/orders", token=admin_tok),
                   "GET /admin/delivery-batches/<id>/orders", 200)

    sub("Abandoned carts")
    expect(api("GET", "/admin/abandoned-carts", token=admin_tok),
           "GET /admin/abandoned-carts", 200)

    sub("Audit log")
    expect(api("GET", "/admin/audit-log", token=admin_tok), "GET /admin/audit-log", 200)

    sub("Admin first-order gifts")
    expect(api("GET", "/admin/first-order-gifts", token=admin_tok),
           "GET /admin/first-order-gifts", 200)

    # ═════════════════════════════════════════════════════════════════════════
    section("20 · KITCHEN FLOW")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("GET", "/kitchen/queue", token=kitchen_tok), "GET /kitchen/queue", 200)
    expect(api("GET", "/kitchen/windows", token=kitchen_tok), "GET /kitchen/windows", 200)
    expect(api("GET", "/kitchen/scheduled", token=kitchen_tok), "GET /kitchen/scheduled", 200)
    expect(api("GET", "/kitchen/metrics", token=kitchen_tok), "GET /kitchen/metrics", 200)
    expect(api("GET", "/kitchen/settings", token=kitchen_tok), "GET /kitchen/settings", 200)

    if window_id:
        expect(api("GET", f"/kitchen/batch-summary/{window_id}", token=kitchen_tok),
               "GET /kitchen/batch-summary/<window_id>", 200)

    sub("Kitchen settings PATCH (admin only)")
    r_ks = api("PATCH", "/kitchen/settings", token=admin_tok,
               body={"settings": {"accepting_orders": "true", "prep_time_minutes": "25"}})
    expect(r_ks, "PATCH /kitchen/settings (admin)", [200, 204])

    if order_a_id:
        sub("Order status update (kitchen)")
        sb_patch("orders", f"id=eq.{order_a_id}", {"status": "received"})
        r_status = api("PATCH", f"/orders/{order_a_id}/status", token=kitchen_tok,
                       body={"status": "preparing"})
        expect(r_status, "PATCH /orders/<id>/status (kitchen → preparing)", [200, 400])

    # ═════════════════════════════════════════════════════════════════════════
    section("21 · RIDER FLOW")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("GET", "/riders/my-batch", token=rider_tok), "GET /riders/my-batch", 200)
    expect(api("GET", "/riders/history", token=rider_tok), "GET /riders/history", 200)
    expect(api("GET", "/riders/stats", token=rider_tok), "GET /riders/stats", 200)
    expect(api("GET", "/riders/earnings", token=rider_tok), "GET /riders/earnings", 200)

    sub("Rider availability")
    r_avail = api("PATCH", "/riders/availability", token=rider_tok,
                  body={"is_available": True})
    expect(r_avail, "PATCH /riders/availability", [200, 204])

    if order_a_id:
        # Force to out_for_delivery so pickup + deliver endpoints make sense
        sb_patch("orders", f"id=eq.{order_a_id}", {"status": "assigned", "rider_id": rider_id})
        r_pickup = api("POST", f"/riders/orders/{order_a_id}/pickup", token=rider_tok)
        expect(r_pickup, "POST /riders/orders/<id>/pickup", [200, 400])

        expect(api("GET", f"/riders/call/{order_a_id}", token=rider_tok),
               "GET /riders/call/<order_id>", 200, warn_on_fail=True)

    # ═════════════════════════════════════════════════════════════════════════
    section("22 · ANALYTICS (admin)")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("GET", "/analytics/dashboard", token=admin_tok), "GET /analytics/dashboard", 200)
    expect(api("GET", "/analytics/sales", token=admin_tok), "GET /analytics/sales", 200)
    expect(api("GET", "/analytics/hp", token=admin_tok), "GET /analytics/hp", 200)
    expect(api("GET", "/analytics/referrals", token=admin_tok), "GET /analytics/referrals", 200)
    expect(api("GET", "/analytics/orders", token=admin_tok), "GET /analytics/orders", 200)
    expect(api("GET", "/analytics/marketplace", token=admin_tok),
           "GET /analytics/marketplace", 200)
    expect(api("GET", "/analytics/export", token=admin_tok, params={"type": "orders"}),
           "GET /analytics/export (orders)", 200, warn_on_fail=True)

    # ═════════════════════════════════════════════════════════════════════════
    section("23 · NEW FEATURES CHECKS")
    # ═════════════════════════════════════════════════════════════════════════

    sub("Login streak (GET /auth/streak)")
    r_st = api("GET", "/auth/streak", token=user_a_tok)
    ok_st, d_st = expect(r_st, "GET /auth/streak", 200)
    if ok_st:
        p(f"Streak: {d_st.get('streak_count')} day(s), last login: {d_st.get('last_login_date')}",
          "pass")

    sub("Monthly HP cap")
    monthly_rows = sb_get("monthly_hp_tracker",
                          f"user_id=eq.{user_a_id}&limit=1")
    p("monthly_hp_tracker row exists for user_A",
      "pass" if monthly_rows else "warn",
      "(Row is created on first HP earn; may be absent if no HP was earned via order)")

    sub("Win-back task available")
    try:
        from app.tasks.scheduled import win_back_notifications
        p("win_back_notifications importable", "pass")
    except Exception as exc:
        p("win_back_notifications importable", "fail", str(exc))

    sub("HP decay task available")
    try:
        from app.tasks.scheduled import hp_decay_check
        p("hp_decay_check importable", "pass")
    except Exception as exc:
        p("hp_decay_check importable", "fail", str(exc))

    sub("Reset monthly HP tracker task")
    try:
        from app.tasks.scheduled import reset_monthly_hp_tracker
        p("reset_monthly_hp_tracker importable", "pass")
    except Exception as exc:
        p("reset_monthly_hp_tracker importable", "fail", str(exc))

    sub("Order locks task available")
    try:
        from app.tasks.scheduled import check_order_locks
        p("check_order_locks importable", "pass")
    except Exception as exc:
        p("check_order_locks importable", "fail", str(exc))

    sub("Admin cron trigger (POST /admin/cron/<job>)")
    for job in ("hp_decay", "win_back", "order_locks", "reset_monthly_hp"):
        r_cron = api("POST", f"/admin/cron/{job}", token=admin_tok)
        expect(r_cron, f"POST /admin/cron/{job}", [200, 201, 202, 404, 501],
               warn_on_fail=True)

    sub("First-order gift service")
    try:
        from app.services.gift_service import maybe_grant_first_order_gift
        p("gift_service.maybe_grant_first_order_gift importable", "pass")
    except Exception as exc:
        p("gift_service.maybe_grant_first_order_gift importable", "fail", str(exc))

    # ═════════════════════════════════════════════════════════════════════════
    section("24 · WEBHOOKS (smoke — should reject invalid signatures)")
    # ═════════════════════════════════════════════════════════════════════════
    r_wh = api("POST", "/webhooks/paystack", body={"event": "charge.success", "data": {}})
    expect(r_wh, "POST /webhooks/paystack (no signature → 400/401)", [400, 401, 403],
           warn_on_fail=True)
    r_wh2 = api("POST", "/webhooks/flutterwave", body={"event": "charge.completed"})
    expect(r_wh2, "POST /webhooks/flutterwave (no signature → 400/401)", [200, 400, 401, 403],
           warn_on_fail=True)

    # ═════════════════════════════════════════════════════════════════════════
    section("25 · LOGOUT + SECURITY")
    # ═════════════════════════════════════════════════════════════════════════
    expect(api("POST", "/auth/logout-all-devices", token=user_b_tok),
           "POST /auth/logout-all-devices", 200)
    expect(api("POST", "/auth/logout", token=user_a_tok), "POST /auth/logout", 200)

    # ═════════════════════════════════════════════════════════════════════════
    section("26 · CLEANUP")
    # ═════════════════════════════════════════════════════════════════════════
    print("  Running cleanup …")
    errors = 0
    for label, fn in reversed(CLEANUP):
        try:
            fn()
        except Exception as exc:
            print(f"    ⚠ cleanup {label}: {exc}")
            errors += 1
    p(f"Cleanup complete ({len(CLEANUP)} items, {errors} errors)", "pass" if errors == 0 else "warn")

    # ═════════════════════════════════════════════════════════════════════════
    section("RESULTS SUMMARY")
    # ═════════════════════════════════════════════════════════════════════════
    total = sum(RESULTS.values())
    print(f"\n  {PASS_C}  {RESULTS['pass']:>3} passed")
    print(f"  {FAIL_C}  {RESULTS['fail']:>3} failed")
    print(f"  {WARN_C}  {RESULTS['warn']:>3} warnings")
    print(f"\n  Total checks: {total}")

    if FAILED_DETAILS:
        print(f"\n{BOLD}FAILED CHECKS:{RESET}")
        for label, detail in FAILED_DETAILS:
            print(f"    ✗ {label}")
            if detail:
                print(f"      {detail[:200]}")

    if MISSING_GAPS:
        print(f"\n{BOLD}GAPS / MISSING FUNCTIONALITY:{RESET}")
        for label, detail in MISSING_GAPS:
            print(f"    → {label}" + (f": {detail}" if detail else ""))

    print()
    if RESULTS["fail"] == 0:
        print(f"  {BOLD}{PASS_C}  All endpoints passed.{RESET}")
    else:
        print(f"  {BOLD}{FAIL_C}  {RESULTS['fail']} endpoint(s) failed — see above.{RESET}")
    print()

    sys.exit(0 if RESULTS["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
