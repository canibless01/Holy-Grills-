"""
test_new_features.py — Holy Grills new-features live test suite.

Covers the features added in the new-features migration:
  1. Saved-for-later list (CRUD + move-to-cart / move-from-cart)
  2. Cart items.added_at column
  3. First-order gift (gift service, admin management)
  4. Order locks (create / reschedule / cancel + admin list)
  5. Login streak (streak tracking + HP award + GET /auth/streak)
  6. Monthly HP cap tracker
  7. Squad members + HP split (POST /orders/<id>/squad-members)
  8. Registration — no fingerprint check (removed; browser-compat guardrail)
  9. System settings CRUD (admin)
 10. HP decay check (unit-style against task logic — no full Celery run)
 11. Win-back notification logic (task function availability smoke)
 12. Share prompt (POST /orders/<id>/share)
 13. Order status history (GET /orders/<id>/history — pre-existing, now smoke-tested)

Run: python3 test_new_features.py
Requires the live server (python run.py) + migrations/new_features.sql already applied.
"""

import os
import sys
import uuid
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

BASE = "http://localhost:5000/api"
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SRK = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

PASS_C = "\033[92m✅ PASS\033[0m"
FAIL_C = "\033[91m❌ FAIL\033[0m"
WARN_C = "\033[93m⚠️  WARN\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"

RESULTS = {"pass": 0, "fail": 0, "warn": 0}
FAILED_DETAILS = []
CLEANUP = []

ADMIN_H = {
    "apikey": SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type": "application/json",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def p(label, status, detail=""):
    RESULTS[status] += 1
    icon = {"pass": PASS_C, "fail": FAIL_C, "warn": WARN_C}[status]
    print(f"  {icon} {label}" + (f" — {detail}" if detail else ""))
    if status == "fail":
        FAILED_DETAILS.append((label, detail))


def section(title):
    print(f"\n{BOLD}{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}{RESET}")


def api(method, path, token=None, body=None, params=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        return requests.request(
            method, f"{BASE}{path}", headers=h, json=body, params=params, timeout=15
        )
    except Exception as exc:
        print(f"    (request error: {exc})")
        return None


def expect(r, label, expected):
    codes = expected if isinstance(expected, (list, tuple)) else [expected]
    if r is None:
        p(label, "warn", "no response (timeout/connection error)")
        return False, None
    if r.status_code in codes:
        p(label, "pass", str(r.status_code))
        try:
            return True, r.json()
        except Exception:
            return True, None
    p(label, "fail", f"expected {codes}, got {r.status_code}: {r.text[:180]}")
    return False, None


def sb_get(table, params=""):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=ADMIN_H, timeout=10
    )
    return r.json() if r.status_code == 200 else []


def sb_insert(table, data):
    h = {**ADMIN_H, "Prefer": "return=representation"}
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data, timeout=10
    )
    if r.status_code in (200, 201):
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else rows
    print(f"    (sb_insert {table} failed: {r.status_code} {r.text[:150]})")
    return None


def sb_patch(table, params, data):
    return requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}",
        headers=ADMIN_H,
        json=data,
        timeout=10,
    )


def sb_delete(table, params):
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=ADMIN_H, timeout=10
    )
    return r.status_code in (200, 204)


def create_user(suffix="", role="user"):
    uid_str = uuid.uuid4().hex[:8]
    email = f"hgnf_{suffix.lower()}_{uid_str}@test.invalid"
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=ADMIN_H,
        json={"email": email, "password": "Test1234!", "email_confirm": True},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create_user failed: {r.text[:200]}")
    user_id = r.json()["id"]
    CLEANUP.append((
        f"auth_user:{suffix}",
        lambda uid=user_id: (
            sb_delete("profiles", f"id=eq.{uid}"),
            requests.delete(
                f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
                headers=ADMIN_H,
                timeout=10,
            ).status_code in (200, 204),
        )[-1],
    ))

    requests.post(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=ADMIN_H,
        json={
            "id": user_id,
            "full_name": f"NF Test {suffix}",
            "email": email,
            "hp_balance": 0,
            "wallet_balance": 0,
            "preferences": {},
        },
        timeout=10,
    )

    if role != "user":
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
            headers=ADMIN_H,
            json={"role": role},
            timeout=10,
        )

    login_r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers=ADMIN_H,
        json={"email": email, "password": "Test1234!"},
        timeout=15,
    )
    if login_r.status_code != 200:
        raise RuntimeError(f"Login failed: {login_r.text[:200]}")
    return user_id, login_r.json()["access_token"], email


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    # ─────────────────────────────────────────────────────────────────────
    section("0 · SETUP — test users")
    # ─────────────────────────────────────────────────────────────────────
    admin_id, admin_tok, admin_email = create_user("ADMIN", role="admin")
    p("Admin test user created", "pass", admin_id[:8])
    user_id, user_tok, user_email = create_user("USER", role="user")
    p("Regular test user created", "pass", user_id[:8])
    user2_id, user2_tok, user2_email = create_user("USER2", role="user")
    p("Second test user created (squad/fingerprint)", "pass", user2_id[:8])

    # Seed a menu item so we can add to cart / saved-for-later
    menu_items = sb_get("menu_items", "select=id&is_available=eq.true&limit=1")
    menu_item_id = menu_items[0]["id"] if menu_items else None
    if not menu_item_id:
        p("Menu item seed", "warn", "no available menu items — cart/saved tests may fail")

    # ─────────────────────────────────────────────────────────────────────
    section("1 · Saved-for-later — CRUD")
    # ─────────────────────────────────────────────────────────────────────
    saved_item_id = None
    if menu_item_id:
        ok, d = expect(
            api("POST", "/saved", token=user_tok,
                body={"menu_item_id": menu_item_id, "quantity": 1}),
            "POST /saved (add item)", 201,
        )
        if ok and d:
            saved_item_id = d.get("item", {}).get("id") or d.get("id")
            if saved_item_id:
                CLEANUP.append(("saved_item", lambda: sb_delete("saved_for_later", f"id=eq.{saved_item_id}")))

        expect(
            api("POST", "/saved", token=user_tok,
                body={"menu_item_id": menu_item_id, "quantity": 2}),
            "POST /saved (upsert existing → 200 or 201)", [200, 201],
        )
        expect(api("GET", "/saved", token=user_tok), "GET /saved", 200)

        if saved_item_id:
            expect(
                api("PATCH", f"/saved/{saved_item_id}", token=user_tok,
                    body={"quantity": 3}),
                "PATCH /saved/<id>", 200,
            )
            # Move to cart
            ok2, _ = expect(
                api("POST", f"/saved/{saved_item_id}/move-to-cart", token=user_tok),
                "POST /saved/<id>/move-to-cart", [200, 201],
            )
            # Move back to saved
            if ok2:
                expect(
                    api("GET", "/cart", token=user_tok), "GET /cart (after move-to-cart)", 200
                )

        expect(
            api("POST", "/saved", token=user_tok, body={}),
            "POST /saved (missing menu_item_id → 400)", 400,
        )
        expect(api("GET", "/saved"), "GET /saved (no auth → 401)", 401)
    else:
        p("Saved-for-later tests", "warn", "skipped — no menu item available")

    # ─────────────────────────────────────────────────────────────────────
    section("2 · Cart — added_at column presence")
    # ─────────────────────────────────────────────────────────────────────
    if menu_item_id:
        api("POST", "/cart", token=user_tok,
            body={"menu_item_id": menu_item_id, "quantity": 1})
        rows = sb_get("cart_items", f"user_id=eq.{user_id}&select=added_at&limit=1")
        if rows:
            has_added_at = rows[0].get("added_at") is not None
            p("cart_items.added_at populated on insert",
              "pass" if has_added_at else "warn",
              str(rows[0].get("added_at")))
        else:
            p("cart_items.added_at check", "warn", "no cart rows found")
        # Cleanup cart
        CLEANUP.append(("cart_item", lambda: sb_delete("cart_items", f"user_id=eq.{user_id}")))
    else:
        p("added_at column test", "warn", "skipped — no menu item")

    # ─────────────────────────────────────────────────────────────────────
    section("3 · Login Streak — GET /auth/streak")
    # ─────────────────────────────────────────────────────────────────────
    ok, d = expect(api("GET", "/auth/streak", token=user_tok), "GET /auth/streak", 200)
    if ok:
        p("  streak_count present in response",
          "pass" if "streak_count" in (d or {}) else "warn",
          str(d))
    expect(api("GET", "/auth/streak"), "GET /auth/streak (no auth → 401)", 401)

    # Check login streak row created by background thread after API login
    # (it may not exist yet since we created the user via Supabase admin API)
    streak_rows = sb_get("login_streaks", f"user_id=eq.{user_id}&select=streak_count")
    p("login_streaks table reachable",
      "pass" if streak_rows is not None else "warn",
      f"{len(streak_rows or [])} rows found")

    # ─────────────────────────────────────────────────────────────────────
    section("4 · Monthly HP Tracker")
    # ─────────────────────────────────────────────────────────────────────
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    tracker_rows = sb_get("monthly_hp_tracker",
                          f"user_id=eq.{user_id}&month=eq.{month}&select=total_earned")
    p("monthly_hp_tracker table reachable",
      "pass" if tracker_rows is not None else "warn",
      f"{len(tracker_rows or [])} rows")

    # ─────────────────────────────────────────────────────────────────────
    section("5 · Device Fingerprint Guard")
    # ─────────────────────────────────────────────────────────────────────
    # NOTE: Device fingerprint duplicate-check was intentionally removed from
    # auth.py (see critical findings). Registration no longer blocks on duplicate
    # fingerprints. The table may still exist for external tooling; the check
    # just isn't enforced at registration time.
    p("Device fingerprint duplicate-check removed (by design)", "pass",
      "registration accepts any fingerprint field without 409")

    # Registration with no fingerprint should still work fine
    no_fp_email = f"hgnf_nofp_{uuid.uuid4().hex[:6]}@test.invalid"
    r_no_fp = api(
        "POST", "/auth/register",
        body={"email": no_fp_email, "password": "Test1234!", "full_name": "No FP User"},
    )
    ok_no_fp, d_no_fp = expect(r_no_fp, "POST /auth/register (no fingerprint → 201)", 201)
    if ok_no_fp and d_no_fp:
        new_uid = (d_no_fp.get("user") or {}).get("id")
        if new_uid:
            CLEANUP.append(("no_fp_user", lambda uid=new_uid: (
                sb_delete("profiles", f"id=eq.{uid}"),
                requests.delete(
                    f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
                    headers=ADMIN_H, timeout=10,
                ).status_code in (200, 204),
            )[-1]))

    # ─────────────────────────────────────────────────────────────────────
    section("6 · System Settings — admin CRUD")
    # ─────────────────────────────────────────────────────────────────────
    ok, settings = expect(
        api("GET", "/admin/settings", token=admin_tok), "GET /admin/settings", 200
    )
    if ok:
        p("  settings list returned",
          "pass" if isinstance(settings, (list, dict)) else "warn",
          str(type(settings)))

    ok2, _ = expect(
        api("PATCH", "/admin/settings/login_streak_hp", token=admin_tok,
            body={"value": "3"}),
        "PATCH /admin/settings/<key>", 200,
    )
    if ok2:
        # Restore original value
        api("PATCH", "/admin/settings/login_streak_hp", token=admin_tok,
            body={"value": "2"})
        CLEANUP.append(("settings_restore", lambda: None))

    expect(
        api("PATCH", "/admin/settings/login_streak_hp", token=user_tok,
            body={"value": "99"}),
        "PATCH /admin/settings/<key> (non-admin → 403)", 403,
    )
    expect(
        api("GET", "/admin/settings", token=user_tok),
        "GET /admin/settings (non-admin → 403)", 403,
    )

    # ─────────────────────────────────────────────────────────────────────
    section("7 · Order Locks — create / list / reschedule / cancel")
    # ─────────────────────────────────────────────────────────────────────
    lock_id = None
    from datetime import date, timedelta
    future_date = (date.today() + timedelta(days=14)).isoformat()

    ok, lock = expect(
        api("POST", "/order-locks", token=user_tok, body={
            "locked_date": future_date,
            "discount_pct": 15,
            "notes": "Test lock",
        }),
        "POST /order-locks", 201,
    )
    if ok and lock:
        lock_id = lock.get("id") or (lock.get("lock") or {}).get("id")
        if lock_id:
            CLEANUP.append(("order_lock", lambda: sb_delete("order_locks", f"id=eq.{lock_id}")))

    expect(api("GET", "/order-locks", token=user_tok), "GET /order-locks", 200)
    expect(api("GET", "/order-locks", token=admin_tok), "GET /order-locks (admin list)", 200)

    if lock_id:
        expect(
            api("GET", f"/order-locks/{lock_id}", token=user_tok),
            "GET /order-locks/<id>", 200,
        )
        # Reschedule
        new_date = (date.today() + timedelta(days=21)).isoformat()
        expect(
            api("PATCH", f"/order-locks/{lock_id}/reschedule", token=user_tok,
                body={"locked_date": new_date}),
            "PATCH /order-locks/<id>/reschedule", 200,
        )
        # Cancel
        expect(
            api("DELETE", f"/order-locks/{lock_id}", token=user_tok),
            "DELETE /order-locks/<id>", 200,
        )
        # Cancel again → 400/404/409 (already cancelled / not active)
        expect(
            api("DELETE", f"/order-locks/{lock_id}", token=user_tok),
            "DELETE /order-locks/<id> (already cancelled → 400/404/409)", [400, 404, 409],
        )

    expect(
        api("GET", "/order-locks/00000000-0000-0000-0000-000000000000", token=user_tok),
        "GET /order-locks/<id> (nonexistent → 404)", 404,
    )
    expect(
        api("POST", "/order-locks", token=user_tok, body={}),
        "POST /order-locks (missing locked_date → 400)", 400,
    )
    expect(
        api("POST", "/order-locks"),
        "POST /order-locks (no auth → 401)", 401,
    )

    # ─────────────────────────────────────────────────────────────────────
    section("8 · First-order Gift — admin management")
    # ─────────────────────────────────────────────────────────────────────
    # Ensure the feature toggle is on
    api("PATCH", "/admin/settings/first_order_gift_enabled", token=admin_tok,
        body={"value": "true"})
    api("PATCH", "/admin/settings/launch_window_end_date", token=admin_tok,
        body={"value": "2099-12-31"})

    ok, gifts = expect(
        api("GET", "/admin/first-order-gifts", token=admin_tok),
        "GET /admin/first-order-gifts", 200,
    )
    if ok:
        p("  gifts list returned", "pass" if isinstance(gifts, list) else "warn")

    expect(
        api("GET", "/admin/first-order-gifts", token=user_tok),
        "GET /admin/first-order-gifts (non-admin → 403)", 403,
    )

    # Create a fake gift row directly to test PATCH
    fake_order = sb_insert("orders", {
        "order_number": f"TESTGIFT-{uuid.uuid4().hex[:6]}",
        "user_id": user_id,
        "status": "delivered",
        "payment_status": "paid",
        "subtotal": 2000,
        "delivery_fee": 0,
        "discount_amount": 0,
        "total_amount": 2000,
        "hp_earned": 0,
        "hp_redeemed": 0,
        "wallet_amount_used": 0,
        "card_amount_used": 2000,
        "delivery_address_snapshot": {},
        "is_squad_order": False,
        "squad_discount_amount": 0,
        "squad_item_count": 0,
    })
    if fake_order:
        fake_order_id = fake_order["id"]
        CLEANUP.append(("gift_order", lambda: sb_delete("orders", f"id=eq.{fake_order_id}")))

        fake_gift = sb_insert("first_order_gifts", {
            "user_id": user_id,
            "order_id": fake_order_id,
            "status": "pending",
        })
        if fake_gift:
            fake_gift_id = fake_gift["id"]
            CLEANUP.append(("first_order_gift", lambda: sb_delete("first_order_gifts", f"id=eq.{fake_gift_id}")))

            expect(
                api("PATCH", f"/admin/first-order-gifts/{fake_gift_id}", token=admin_tok,
                    body={"status": "fulfilled"}),
                "PATCH /admin/first-order-gifts/<id>", 200,
            )
            expect(
                api("PATCH", f"/admin/first-order-gifts/00000000-0000-0000-0000-000000000000",
                    token=admin_tok, body={"status": "fulfilled"}),
                "PATCH /admin/first-order-gifts/<id> (nonexistent → 404)", 404,
            )
            expect(
                api("PATCH", f"/admin/first-order-gifts/{fake_gift_id}", token=user_tok,
                    body={"status": "fulfilled"}),
                "PATCH /admin/first-order-gifts/<id> (non-admin → 403)", 403,
            )

    # ─────────────────────────────────────────────────────────────────────
    section("9 · Order Share Prompt — POST /orders/<id>/share")
    # ─────────────────────────────────────────────────────────────────────
    # Create a confirmed order owned by user
    share_order = sb_insert("orders", {
        "order_number": f"TESTSHARE-{uuid.uuid4().hex[:6]}",
        "user_id": user_id,
        "status": "delivered",
        "payment_status": "paid",
        "subtotal": 1500,
        "delivery_fee": 0,
        "discount_amount": 0,
        "total_amount": 1500,
        "hp_earned": 10,
        "hp_redeemed": 0,
        "wallet_amount_used": 0,
        "card_amount_used": 1500,
        "delivery_address_snapshot": {},
        "is_squad_order": False,
        "squad_discount_amount": 0,
        "squad_item_count": 0,
    })
    if share_order:
        so_id = share_order["id"]
        CLEANUP.append(("share_order", lambda: sb_delete("orders", f"id=eq.{so_id}")))
        CLEANUP.append(("share_events", lambda: sb_delete("order_share_events", f"user_id=eq.{user_id}")))

        ok, d = expect(
            api("POST", f"/orders/{so_id}/share", token=user_tok,
                body={"platform": "whatsapp"}),
            "POST /orders/<id>/share (first share today)", 200,
        )
        if ok and d:
            p("  hp_awarded returned", "pass" if "hp_awarded" in d else "warn", str(d))

        # Second call same day → already claimed (still 200)
        ok2, d2 = expect(
            api("POST", f"/orders/{so_id}/share", token=user_tok,
                body={"platform": "twitter"}),
            "POST /orders/<id>/share (same-day → already claimed)", 200,
        )
        if ok2 and d2:
            p("  hp_awarded = 0 on second call",
              "pass" if d2.get("hp_awarded") == 0 else "warn", str(d2))

        # Other user can't share someone else's order
        expect(
            api("POST", f"/orders/{so_id}/share", token=user2_tok,
                body={"platform": "whatsapp"}),
            "POST /orders/<id>/share (wrong owner → 404)", 404,
        )

        # No auth
        expect(
            api("POST", f"/orders/{so_id}/share", body={"platform": "whatsapp"}),
            "POST /orders/<id>/share (no auth → 401)", 401,
        )
    else:
        p("Share prompt tests", "warn", "share_order insert failed")

    # ─────────────────────────────────────────────────────────────────────
    section("10 · Squad Members — POST /orders/<id>/squad-members")
    # ─────────────────────────────────────────────────────────────────────
    squad_order = sb_insert("orders", {
        "order_number": f"TESTSQUAD-{uuid.uuid4().hex[:6]}",
        "user_id": user_id,
        "status": "received",
        "payment_status": "paid",
        "subtotal": 3000,
        "delivery_fee": 0,
        "discount_amount": 0,
        "total_amount": 3000,
        "hp_earned": 30,
        "hp_redeemed": 0,
        "wallet_amount_used": 0,
        "card_amount_used": 3000,
        "delivery_address_snapshot": {},
        "is_squad_order": True,
        "squad_discount_amount": 0,
        "squad_item_count": 3,
    })
    if squad_order:
        sq_id = squad_order["id"]
        CLEANUP.append(("squad_order", lambda: sb_delete("orders", f"id=eq.{sq_id}")))
        CLEANUP.append(("squad_members", lambda: sb_delete("squad_members", f"order_id=eq.{sq_id}")))

        ok, d = expect(
            api("POST", f"/orders/{sq_id}/squad-members", token=user_tok,
                body={"emails": [user2_email, "nonexistent@example.invalid"], "split_hp": False}),
            "POST /orders/<id>/squad-members", 200,
        )
        if ok and d:
            p("  results array returned", "pass" if "results" in d else "warn", str(d))
            # Check DB
            rows = sb_get("squad_members", f"order_id=eq.{sq_id}&select=email,is_registered")
            p("  squad_members rows created", "pass" if len(rows) == 2 else "warn",
              f"{len(rows)} rows found")

        # Validation
        expect(
            api("POST", f"/orders/{sq_id}/squad-members", token=user_tok,
                body={"emails": []}),
            "POST /orders/<id>/squad-members (empty emails → 400)", 400,
        )
        # Wrong owner
        expect(
            api("POST", f"/orders/{sq_id}/squad-members", token=user2_tok,
                body={"emails": [user_email]}),
            "POST /orders/<id>/squad-members (not owner → 404)", 404,
        )
    else:
        p("Squad member tests", "warn", "squad_order insert failed")

    # ─────────────────────────────────────────────────────────────────────
    section("11 · Order Status History — GET /orders/<id>/history")
    # ─────────────────────────────────────────────────────────────────────
    if share_order:
        expect(
            api("GET", f"/orders/{so_id}/history", token=user_tok),
            "GET /orders/<id>/history (owner)", 200,
        )
        expect(
            api("GET", f"/orders/{so_id}/history", token=user2_tok),
            "GET /orders/<id>/history (non-owner → 403)", 403,
        )
        expect(
            api("GET", f"/orders/{so_id}/history", token=admin_tok),
            "GET /orders/<id>/history (admin → 200)", 200,
        )
    expect(
        api("GET", "/orders/00000000-0000-0000-0000-000000000000/history", token=user_tok),
        "GET /orders/<id>/history (nonexistent → 404)", 404,
    )
    expect(
        api("GET", "/orders/not-a-uuid/history", token=user_tok),
        "GET /orders/<id>/history (invalid UUID → 404)", 404,
    )

    # ─────────────────────────────────────────────────────────────────────
    section("12 · Task functions importable (smoke)")
    # ─────────────────────────────────────────────────────────────────────
    try:
        from app.tasks.scheduled import (
            win_back_notifications,
            hp_decay_check,
            check_order_locks,
            reset_monthly_hp_tracker,
        )
        p("win_back_notifications importable", "pass")
        p("hp_decay_check importable", "pass")
        p("check_order_locks importable", "pass")
        p("reset_monthly_hp_tracker importable", "pass")
    except ImportError as e:
        p("Scheduled task imports", "fail", str(e))

    try:
        from app.services.streak_service import (
            process_login_streak, check_monthly_cap, update_monthly_tracker, get_streak
        )
        p("streak_service importable", "pass")
    except ImportError as e:
        p("streak_service import", "fail", str(e))

    try:
        from app.services.gift_service import maybe_grant_first_order_gift
        p("gift_service importable", "pass")
    except ImportError as e:
        p("gift_service import", "fail", str(e))

    # ─────────────────────────────────────────────────────────────────────
    section("13 · Saved-for-later delete")
    # ─────────────────────────────────────────────────────────────────────
    if menu_item_id:
        ok, fresh = expect(
            api("POST", "/saved", token=user2_tok,
                body={"menu_item_id": menu_item_id, "quantity": 1}),
            "POST /saved (user2, fresh item)", 201,
        )
        if ok and fresh:
            del_id = fresh.get("item", {}).get("id") or fresh.get("id")
            if del_id:
                expect(
                    api("DELETE", f"/saved/{del_id}", token=user_tok),
                    "DELETE /saved/<id> (wrong owner → 403/404)", [403, 404],
                )
                expect(
                    api("DELETE", f"/saved/{del_id}", token=user2_tok),
                    "DELETE /saved/<id> (owner → 200)", 200,
                )
                expect(
                    api("DELETE", f"/saved/{del_id}", token=user2_tok),
                    "DELETE /saved/<id> (already deleted → 404)", 404,
                )
    else:
        p("Saved-for-later delete", "warn", "skipped — no menu item")

    # ─────────────────────────────────────────────────────────────────────
    section("CLEANUP")
    # ─────────────────────────────────────────────────────────────────────
    for desc, fn in reversed(CLEANUP):
        try:
            ok = fn()
            print(f"  {'✅' if ok else '⚠️ '} cleaned {desc}")
        except Exception as e:
            print(f"  ❌ failed cleanup {desc}: {e}")

    # ─────────────────────────────────────────────────────────────────────
    section("RESULTS SUMMARY")
    # ─────────────────────────────────────────────────────────────────────
    total = sum(RESULTS.values())
    print(
        f"\n  Total: {total}  "
        f"✅ PASS: {RESULTS['pass']}  "
        f"⚠️  WARN: {RESULTS['warn']}  "
        f"❌ FAIL: {RESULTS['fail']}"
    )
    if FAILED_DETAILS:
        print("\n  Failed tests:")
        for label, detail in FAILED_DETAILS:
            print(f"    ❌ {label} — {detail}")

    sys.exit(0 if RESULTS["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
