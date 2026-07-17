"""
test_simulations.py — Holy Grills targeted user-journey simulations
=====================================================================
Runs the 20 NEW simulations (referral, promo, HP redemption+refund, order
lifecycle, scheduled order, gift, event check-in, marketplace, delivery
attempted, squad order, wallet top-up, HP transfer, reward redemption,
leaderboard reset, HP decay, abandoned cart, order lock, notification
prefs, challenges, settings/storefront) plus the marketplace listing_type
constraint probe — against the LIVE running server + real Supabase.

Does not hardcode expected numeric values; verifies structure, status
codes, and before/after relationships. Skips auth/HP-read/menu/cart/admin
listing flows per instructions (already heavily tested).

Run: python3 test_simulations.py
"""

import os
import sys
import uuid
import time
import requests
from datetime import datetime, timezone, timedelta, date
from dotenv import load_dotenv

load_dotenv()

BASE         = "http://localhost:5000/api"
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SRK          = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

PASS_C = "\033[92m✅ PASS\033[0m"
FAIL_C = "\033[91m❌ FAIL\033[0m"
WARN_C = "\033[93m⚠️  WARN\033[0m"
INFO_C = "\033[94mℹ️  INFO\033[0m"
BOLD, RESET = "\033[1m", "\033[0m"

RESULTS = {"pass": 0, "fail": 0, "warn": 0}
FAILED_DETAILS, GAPS, CLEANUP = [], [], []

ADMIN_H = {"apikey": SRK, "Authorization": f"Bearer {SRK}", "Content-Type": "application/json"}


def p(label, status, detail=""):
    RESULTS[status] += 1
    icon = {"pass": PASS_C, "fail": FAIL_C, "warn": WARN_C}[status]
    print(f"  {icon} {label}" + (f" — {detail}" if detail else ""))
    if status == "fail":
        FAILED_DETAILS.append((label, detail))


def gap(label, detail=""):
    GAPS.append((label, detail))
    print(f"  {INFO_C} GAP: {label}" + (f" — {detail}" if detail else ""))


def section(title):
    print(f"\n{BOLD}{'═'*72}\n  {title}\n{'═'*72}{RESET}")


def api(method, path, token=None, body=None, params=None, timeout=20):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        return requests.request(method, f"{BASE}{path}", headers=h, json=body, params=params, timeout=timeout)
    except Exception as exc:
        print(f"    (request error: {exc})")
        return None


def expect(r, label, expected, warn_on_fail=False):
    codes = expected if isinstance(expected, (list, tuple)) else [expected]
    if r is None:
        p(label, "warn", "no response")
        return False, None
    if r.status_code in codes:
        p(label, "pass", str(r.status_code))
        try:
            return True, r.json()
        except Exception:
            return True, None
    status = "warn" if warn_on_fail else "fail"
    p(label, status, f"expected {codes}, got {r.status_code}: {r.text[:200]}")
    try:
        return False, r.json()
    except Exception:
        return False, None


def sb_get(table, params=""):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=ADMIN_H, timeout=15)
    return r.json() if r.status_code == 200 else []


def sb_insert(table, data):
    h = {**ADMIN_H, "Prefer": "return=representation"}
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data, timeout=15)
    if r.status_code in (200, 201):
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else rows
    print(f"    (sb_insert {table} failed: {r.status_code} {r.text[:250]})")
    return None


def sb_patch(table, qs, data):
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?{qs}", headers={**ADMIN_H, "Prefer": "return=minimal"}, json=data, timeout=15)
    return r.status_code in (200, 204)


def sb_delete(table, qs):
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?{qs}", headers=ADMIN_H, timeout=15)
    return r.status_code in (200, 204)


def sb_delete_auth_user(uid):
    r = requests.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{uid}", headers=ADMIN_H, timeout=15)
    return r.status_code in (200, 204)


def sb_login(email, password="Test1234!"):
    r = requests.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers=ADMIN_H,
                       json={"email": email, "password": password}, timeout=15)
    return r.json().get("access_token") if r.status_code == 200 else None


def create_test_user(suffix, role="student"):
    uid_str = uuid.uuid4().hex[:8]
    email = f"hgsim_{suffix.lower()}_{uid_str}@test.invalid"
    r = requests.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=ADMIN_H,
                       json={"email": email, "password": "Test1234!", "email_confirm": True}, timeout=15)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create_test_user {suffix} failed: {r.text[:200]}")
    uid = r.json()["id"]
    ref_code = f"SIM{uid_str.upper()[:6]}"
    requests.post(f"{SUPABASE_URL}/rest/v1/profiles",
                  headers={**ADMIN_H, "Prefer": "return=minimal,resolution=merge-duplicates"},
                  json={"id": uid, "email": email, "full_name": f"HG Sim {suffix}", "role": role,
                        "referral_code": ref_code, "hp_balance": 0, "wallet_balance": 0,
                        "is_active": True, "preferences": {}}, timeout=15)
    requests.patch(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}",
                   headers={**ADMIN_H, "Prefer": "return=minimal"},
                   json={"role": role, "referral_code": ref_code}, timeout=15)
    requests.post(f"{SUPABASE_URL}/rest/v1/wallets",
                  headers={**ADMIN_H, "Prefer": "return=minimal,resolution=merge-duplicates"},
                  json={"user_id": uid, "balance": 0}, timeout=15)
    tok = sb_login(email)
    if not tok:
        raise RuntimeError(f"Login for {suffix} failed")
    CLEANUP.append((f"user:{suffix}", lambda u=uid: (sb_delete("profiles", f"id=eq.{u}"), sb_delete_auth_user(u))))
    return uid, tok, email, ref_code


def seed_wallet(user_id, naira):
    sb_patch("profiles", f"id=eq.{user_id}", {"wallet_balance": naira})
    sb_patch("wallets", f"user_id=eq.{user_id}", {"balance": naira})


def seed_hp(user_id, hp):
    ok = sb_patch("profiles", f"id=eq.{user_id}", {"hp_balance": hp})
    if not ok:
        print(f"    (seed_hp failed for {user_id})")


def get_hp_balance(token):
    r = api("GET", "/hp/balance", token=token)
    if r and r.status_code == 200:
        return r.json()
    return None


def wallet_balance_db(user_id):
    rows = sb_get("profiles", f"id=eq.{user_id}&select=wallet_balance")
    return float(rows[0]["wallet_balance"]) if rows else None


def get_or_create_delivery_window():
    rows = sb_get("delivery_windows", "status=eq.open&select=id&limit=1")
    if rows:
        return rows[0]["id"]
    rows = sb_get("delivery_windows", "select=id&order=created_at.desc&limit=1")
    if rows:
        return rows[0]["id"]
    return None


def get_menu_item():
    rows = sb_get("menu_items", "is_available=eq.true&select=id,price&limit=1")
    if rows:
        return rows[0]
    rows = sb_get("menu_items", "select=id,price&limit=1")
    return rows[0] if rows else None


def main():  # noqa: C901
    section("SETUP")
    print("  Creating admin, kitchen, rider …")
    admin_id, admin_tok, _, _ = create_test_user("ADMIN", role="admin")
    kitchen_id, kitchen_tok, _, _ = create_test_user("KITCHEN", role="kitchen")
    rider_id, rider_tok, _, _ = create_test_user("RIDER", role="rider")
    p("Admin/Kitchen/Rider created", "pass")

    window_id = get_or_create_delivery_window()
    if not window_id:
        window_id = sb_insert("delivery_windows", {
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "start_time": "12:00", "end_time": "14:00", "status": "open", "capacity": 100,
        })
        window_id = window_id["id"] if window_id else None
    p("Delivery window available", "pass" if window_id else "fail", str(window_id))

    menu_item = get_menu_item()
    p("Menu item available", "pass" if menu_item else "fail", str(menu_item))

    def order_body(user_extra=None, **overrides):
        body = {
            "items": [{"menu_item_id": menu_item["id"], "quantity": 4}],
            "delivery_window_id": window_id,
            "payment_method": "wallet",
            "delivery_address": {"address_line": "1 Test Close", "landmark": "Gate", "zone": "campus"},
        }
        body.update(overrides)
        return body

    # ═════════════════════════════════════════════════════════════════
    section("SIM 1 · REFERRAL FLOW")
    # ═════════════════════════════════════════════════════════════════
    ua_email = f"hgsim_usera_{uuid.uuid4().hex[:8]}@test.invalid"
    r = api("POST", "/auth/register", body={"email": ua_email, "password": "Test1234!", "full_name": "Sim UserA"})
    ok, d = expect(r, "Register user_A", 201)
    user_a_id = (d.get("user") or {}).get("id") if ok else None
    user_a_tok = d.get("access_token") if ok else None
    if user_a_id:
        CLEANUP.append(("user:A", lambda u=user_a_id: (sb_delete("profiles", f"id=eq.{u}"), sb_delete_auth_user(u))))
        ua_prof = sb_get("profiles", f"id=eq.{user_a_id}&select=referral_code")
        ua_ref = ua_prof[0]["referral_code"] if ua_prof else None
        p("user_A referral code issued", "pass" if ua_ref else "fail", str(ua_ref))
        seed_wallet(user_a_id, 10000)

        ub_email = f"hgsim_userb_{uuid.uuid4().hex[:8]}@test.invalid"
        r = api("POST", "/auth/register", body={"email": ub_email, "password": "Test1234!",
                                                 "full_name": "Sim UserB", "referred_by_code": ua_ref})
        ok, d = expect(r, "Register user_B with referral code", 201)
        user_b_id = (d.get("user") or {}).get("id") if ok else None
        user_b_tok = d.get("access_token") if ok else None
        if user_b_id:
            CLEANUP.append(("user:B", lambda u=user_b_id: (sb_delete("profiles", f"id=eq.{u}"), sb_delete_auth_user(u))))
            ub_prof = sb_get("profiles", f"id=eq.{user_b_id}&select=referred_by")
            p("user_B.referred_by == user_A", "pass" if ub_prof and ub_prof[0].get("referred_by") == user_a_id else "fail", str(ub_prof))
            seed_wallet(user_b_id, 10000)

            hp_before = get_hp_balance(user_a_tok)
            before_total = (hp_before or {}).get("active")

            r = api("POST", "/orders", token=user_b_tok, body=order_body(payment_method="wallet"))
            ok, order = expect(r, "user_B places first order", 201)
            if ok:
                order_id = order.get("id") or order.get("order_id")
                r = api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "preparing"})
                expect(r, "  -> preparing", [200], warn_on_fail=True)
                r = api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "ready"})
                expect(r, "  -> ready", [200], warn_on_fail=True)
                r = api("PATCH", f"/orders/{order_id}/status", token=admin_tok, body={"status": "assigned"})
                expect(r, "  -> assigned", [200], warn_on_fail=True)
                r = api("PATCH", f"/orders/{order_id}/status", token=rider_tok, body={"status": "out_for_delivery"})
                expect(r, "  -> out_for_delivery", [200], warn_on_fail=True)
                r = api("PATCH", f"/orders/{order_id}/status", token=rider_tok, body={"status": "delivered"})
                ok_del, _ = expect(r, "  -> delivered", [200], warn_on_fail=True)

                time.sleep(2)
                hp_after = get_hp_balance(user_a_tok)
                after_total = (hp_after or {}).get("active")
                if before_total is not None and after_total is not None:
                    p("user_A HP increased after referred user's first delivered order",
                      "pass" if after_total > before_total else "fail",
                      f"{before_total} -> {after_total}")
                else:
                    gap("Could not compare user_A HP before/after (balance field shape)", str(hp_after))

                notifs = sb_get("notifications", f"user_id=eq.{user_a_id}&order=created_at.desc&limit=5")
                ref_notif = any("referr" in (n.get("title", "") + n.get("body", "")).lower() for n in notifs)
                p("user_A received a referral notification (DB)", "pass" if ref_notif else "warn", str(notifs[:2]))
            else:
                gap("Could not place user_B's first order — referral HP step untestable")

    # ═════════════════════════════════════════════════════════════════
    section("SIM 2 · PROMO CODE FLOW")
    # ═════════════════════════════════════════════════════════════════
    promo_code = f"SIMPROMO{uuid.uuid4().hex[:5].upper()}"
    r = api("POST", "/admin/promo-codes", token=admin_tok,
            body={"code": promo_code, "discount_type": "flat", "discount_value": 200, "min_order_value": 0})
    ok, promo = expect(r, "Admin creates flat promo code", 201)
    if ok:
        u_id, u_tok, _, _ = create_test_user("PROMOUSER")
        seed_wallet(u_id, 10000)
        r = api("GET", "/orders", token=u_tok)  # warm auth
        r = api("POST", "/orders", token=u_tok, body=order_body(promo_code=promo_code))
        ok2, order = expect(r, "Order created with promo_code applied", 201)
        if ok2:
            order_id = order.get("id") or order.get("order_id")
            discount = order.get("discount_amount") or order.get("promo_discount")
            p("Order total reflects a discount", "pass" if discount and float(discount) > 0 else "warn", str(discount))
            uses = sb_get("promo_code_uses", f"promo_code_id=eq.{promo.get('id')}")
            p("promo_code_uses has a new entry", "pass" if uses else "fail", str(len(uses)))
            promo_after = sb_get("promo_codes", f"id=eq.{promo.get('id')}&select=used_count")
            used_count = promo_after[0]["used_count"] if promo_after else None
            p("promo_codes.used_count incremented", "pass" if used_count and used_count >= 1 else "fail", str(used_count))
        else:
            gap("Could not create order with promo_code — see error above", str(order))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 3 · HP REDEMPTION + REFUND ON CANCEL")
    # ═════════════════════════════════════════════════════════════════
    u3_id, u3_tok, _, _ = create_test_user("HPUSER")
    seed_wallet(u3_id, 10000)
    seed_hp(u3_id, 2000)
    hp_before = get_hp_balance(u3_tok)
    r = api("POST", "/orders", token=u3_tok, body=order_body(payment_method="wallet", hp_points_to_redeem=500))
    ok, order = expect(r, "Order created redeeming 500 HP", 201)
    if ok:
        order_id = order.get("id") or order.get("order_id")
        hp_redeemed = order.get("hp_redeemed") or order.get("hp_discount_amount") or order.get("hp_discount")
        p("Order has hp_redeemed field > 0", "pass" if hp_redeemed and float(hp_redeemed) > 0 else "warn", str(hp_redeemed))
        total_amount = order.get("total_amount")
        p("Order total_amount present", "pass" if total_amount is not None else "warn", str(total_amount))
        time.sleep(1)
        hp_after = get_hp_balance(u3_tok)
        bt = (hp_before or {}).get("active")
        at = (hp_after or {}).get("active")
        p("HP balance decreased by ~500 (deducted on wallet-paid orders at placement)", "pass" if bt is not None and at is not None and (bt - at) >= 400 else "warn", f"{bt} -> {at} (may deduct at payment confirmation)")

        wallet_before_cancel = wallet_balance_db(u3_id)
        r = api("POST", f"/orders/{order_id}/cancel", token=u3_tok)
        ok_c, _ = expect(r, "Student cancels order before window closes", [200], warn_on_fail=True)
        if ok_c:
            time.sleep(1)
            wallet_after_cancel = wallet_balance_db(u3_id)
            p("Wallet refunded on cancel", "pass" if wallet_after_cancel is not None and wallet_after_cancel > wallet_before_cancel else "warn",
              f"{wallet_before_cancel} -> {wallet_after_cancel}")
            hp_after_cancel = get_hp_balance(u3_tok)
            act = (hp_after_cancel or {}).get("active")
            p("HP refunded back on cancel (500 restored)", "pass" if act is not None and at is not None and act >= at + 400 else "warn", f"{at} -> {act}")
        else:
            gap("Order could not be cancelled (may be outside cancel window) — refund path unverified", str(_))
    else:
        gap("Could not create HP-redemption order", str(order))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 4 · FULL ORDER LIFECYCLE + HP AWARD")
    # ═════════════════════════════════════════════════════════════════
    u4_id, u4_tok, _, _ = create_test_user("LIFECYCLE")
    seed_wallet(u4_id, 10000)
    hp_before4 = get_hp_balance(u4_tok)
    r = api("POST", "/orders", token=u4_tok, body=order_body(payment_method="wallet"))
    ok, order = expect(r, "Student places order (wallet)", 201)
    if ok:
        order_id = order.get("id") or order.get("order_id")
        r = api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "preparing"})
        expect(r, "Kitchen -> preparing", [200], warn_on_fail=True)
        r = api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "ready"})
        expect(r, "Kitchen -> ready", [200], warn_on_fail=True)
        batch = sb_insert("delivery_batches", {"window_id": window_id, "rider_id": rider_id, "zone": "campus", "status": "assigned"})
        r = api("PATCH", f"/orders/{order_id}/status", token=admin_tok, body={"status": "assigned"})
        expect(r, "Admin -> assigned", [200], warn_on_fail=True)
        r = api("POST", f"/riders/orders/{order_id}/pickup", token=rider_tok)
        expect(r, "Rider pickup", [200], warn_on_fail=True)
        r = api("POST", f"/riders/orders/{order_id}/deliver", token=rider_tok)
        ok_del, _ = expect(r, "Rider deliver", [200], warn_on_fail=True)
        time.sleep(2)
        hp_after4 = get_hp_balance(u4_tok)
        bt4 = (hp_before4 or {}).get("active")
        at4 = (hp_after4 or {}).get("active")
        p("HP awarded after delivery", "pass" if bt4 is not None and at4 is not None and at4 > bt4 else "warn", f"{bt4} -> {at4}")
        pending_unlocked = (hp_after4 or {}).get("pending_balance")
        p("HP breakdown (pending/active) present in balance response", "pass" if "pending_balance" in (hp_after4 or {}) or "pending" in str(hp_after4) else "warn", str(hp_after4))
        notifs = sb_get("notifications", f"user_id=eq.{u4_id}&order=created_at.desc&limit=10")
        p("Notifications recorded across status changes", "pass" if len(notifs) >= 2 else "warn", str(len(notifs)))
    else:
        gap("Could not place lifecycle order", str(order))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 5 · SCHEDULED ORDER FLOW")
    # ═════════════════════════════════════════════════════════════════
    u5_id, u5_tok, _, _ = create_test_user("SCHEDULED")
    seed_wallet(u5_id, 10000)
    r = api("POST", "/orders", token=u5_tok, body=order_body(payment_method="wallet", is_scheduled=True, scheduled_for_window_id=window_id))
    ok, order = expect(r, "Order created with is_scheduled=True", [200, 201], warn_on_fail=True)
    if ok:
        p("order.is_scheduled == True", "pass" if order.get("is_scheduled") else "warn", str(order.get("is_scheduled")))
        r = api("GET", "/orders/scheduled", token=u5_tok)
        expect(r, "GET /orders/scheduled shows it for user", [200], warn_on_fail=True)
        r = api("GET", "/kitchen/scheduled", token=kitchen_tok)
        expect(r, "GET /kitchen/scheduled shows it for kitchen", [200], warn_on_fail=True)
    else:
        gap("Scheduled order creation failed/unsupported field combo", str(order))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 6 · FIRST-ORDER GIFT FLOW")
    # ═════════════════════════════════════════════════════════════════
    u6_id, u6_tok, _, _ = create_test_user("GIFTUSER")
    seed_wallet(u6_id, 10000)
    r = api("POST", "/orders", token=u6_tok, body=order_body(payment_method="wallet", items=[{"menu_item_id": menu_item["id"], "quantity": 1}]))
    ok, order = expect(r, "First order placed", 201)
    if ok:
        order_id = order.get("id") or order.get("order_id")
        # Gift grant is wired to happen when the order reaches 'delivered'
        # (see gift_service.py docstring), not at order placement — walk the
        # order through its full lifecycle before checking gift state.
        r = api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "preparing"})
        r = api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "ready"})
        r = api("PATCH", f"/orders/{order_id}/status", token=admin_tok, body={"status": "assigned"})
        expect(r, "Order assigned to rider (gift notify trigger)", [200], warn_on_fail=True)
        r = api("PATCH", f"/orders/{order_id}/status", token=admin_tok, body={"status": "out_for_delivery"})
        r = api("PATCH", f"/orders/{order_id}/status", token=admin_tok, body={"status": "delivered"})
        ok_del = expect(r, "Order marked delivered (gift grant trigger)", [200], warn_on_fail=True)[0]
        time.sleep(2)  # gift grant runs async in a background thread
        order_after = sb_get("orders", f"id=eq.{order_id}")
        order_after = order_after[0] if order_after else {}
        p("order.gift_included == True", "pass" if order_after.get("gift_included") else "warn", str(order_after.get("gift_included")))
        items = sb_get("order_items", f"order_id=eq.{order_id}&options_snapshot->>is_gift=eq.true")
        p("order_items has a gift row (options_snapshot.is_gift, price_snapshot=0)", "pass" if items and float(items[0].get("price_snapshot", 1)) == 0 else "warn", str(items))
        gifts = sb_get("first_order_gifts", f"order_id=eq.{order_id}")
        if gifts:
            gift_id = gifts[0]["id"]
            p("first_order_gifts row created for order", "pass", str(gifts[0].get("status")))
            time.sleep(1)
            gift_notifs = sb_get("notifications", f"user_id=eq.{u6_id}&order=created_at.desc&limit=10")
            gift_notif_found = any("gift" in (n.get("title", "") + n.get("body", "")).lower() for n in gift_notifs)
            p("User receives gift notification on delivery", "pass" if gift_notif_found else "warn", str(len(gift_notifs)))
        else:
            gap("No first_order_gifts row created for first order", str(order_after))
    else:
        gap("Could not place first order for gift test", str(order))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 7 · EVENT CHECK-IN FLOW")
    # ═════════════════════════════════════════════════════════════════
    r = api("POST", "/events", token=admin_tok, body={
        "title": f"Sim Event {uuid.uuid4().hex[:5]}", "location": "Main Hall",
        "starts_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "ends_at": (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).isoformat(),
        "hp_reward": 40, "capacity": 100, "is_published": True,
    })
    ok, event = expect(r, "Admin creates event", 201)
    if ok:
        event_id = event.get("id")
        u7_id, u7_tok, _, _ = create_test_user("EVENTUSER")
        r = api("POST", f"/events/{event_id}/register", token=u7_tok)
        ok_reg, ticket = expect(r, "Student registers for event", [200, 201])
        if ok_reg:
            qr_token = ticket.get("qr_token") or ticket.get("ticket_id")
            hp_before7 = get_hp_balance(u7_tok)
            r = api("POST", f"/events/{event_id}/checkin", token=u7_tok, body={"qr_token": qr_token})
            ok_ci, _ = expect(r, "Student checks in with QR token", [200], warn_on_fail=True)
            if ok_ci:
                time.sleep(1)
                hp_after7 = get_hp_balance(u7_tok)
                bt7 = (hp_before7 or {}).get("pending") or 0
                at7 = (hp_after7 or {}).get("pending") or 0
                p("Pending HP increased after check-in (40 HP)", "pass" if at7 > bt7 else "warn", f"{bt7} -> {at7}")
            else:
                gap("Event check-in failed", str(_))
        else:
            gap("Event registration failed", str(ticket))
    else:
        gap("Admin could not create event", str(event))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 8 · MARKETPLACE PURCHASE FLOW")
    # ═════════════════════════════════════════════════════════════════
    r = api("POST", "/marketplace/admin/listings", token=admin_tok, body={
        "title": f"Sim Listing {uuid.uuid4().hex[:5]}", "listing_type": "code", "price": 500, "hp_price": 200,
    })
    ok, listing = expect(r, "Admin creates code-based marketplace listing", 201)
    if ok:
        listing_id = listing.get("id")
        code_val = f"CODE{uuid.uuid4().hex[:6].upper()}"
        r = api("POST", f"/marketplace/admin/codes/{listing_id}", token=admin_tok, body={"codes": [code_val]})
        expect(r, "Admin uploads access code", [200, 201], warn_on_fail=True)
        u8_id, u8_tok, _, _ = create_test_user("MKTUSER")
        seed_wallet(u8_id, 10000)
        seed_hp(u8_id, 1000)
        hp_before8 = get_hp_balance(u8_tok)
        r = api("POST", f"/marketplace/{listing_id}/purchase", token=u8_tok, body={"payment_method": "hp", "use_hp_pricing": True})
        ok_purch, purchase = expect(r, "Student purchases listing with HP pricing", [200, 201], warn_on_fail=True)
        if ok_purch:
            time.sleep(1)
            hp_after8 = get_hp_balance(u8_tok)
            bt8 = (hp_before8 or {}).get("active")
            at8 = (hp_after8 or {}).get("active")
            p("HP spent on marketplace purchase", "pass" if bt8 is not None and at8 is not None and at8 < bt8 else "warn", f"{bt8} -> {at8}")
            codes_after = sb_get("marketplace_access_codes", f"listing_id=eq.{listing_id}")
            assigned = any(c.get("status") == "assigned" for c in codes_after)
            p("Access code assigned to student", "pass" if assigned else "warn", str(codes_after))
            r = api("GET", "/marketplace/purchases", token=u8_tok)
            expect(r, "Purchase appears in student's history", [200], warn_on_fail=True)
        else:
            gap("Marketplace HP-priced purchase failed", str(purchase))
    else:
        gap("Admin could not create marketplace listing", str(listing))

    # -- listing_type constraint probe --
    section("SIM 8b · MARKETPLACE listing_type CONSTRAINT PROBE")
    for lt in ["code", "service", "product", "experience", "ticket"]:
        r = api("POST", "/marketplace/admin/listings", token=admin_tok,
                body={"title": f"Probe {lt} {uuid.uuid4().hex[:4]}", "listing_type": lt, "price": 100})
        if r is None:
            p(f"listing_type='{lt}'", "warn", "no response")
            continue
        if r.status_code == 201:
            p(f"listing_type='{lt}' accepted", "pass", "201")
            lid = r.json().get("id")
            if lid:
                sb_delete("marketplace_listings", f"id=eq.{lid}")
        else:
            try:
                err_detail = r.json()
            except Exception:
                err_detail = r.text[:300]
            gap(f"listing_type='{lt}' REJECTED", f"{r.status_code}: {err_detail}")

    # ═════════════════════════════════════════════════════════════════
    section("SIM 9 · DELIVERY ATTEMPTED + URGENT NOTIFICATION")
    # ═════════════════════════════════════════════════════════════════
    u9_id, u9_tok, _, _ = create_test_user("ATTEMPTUSER")
    seed_wallet(u9_id, 10000)
    r = api("POST", "/orders", token=u9_tok, body=order_body(payment_method="wallet"))
    ok, order = expect(r, "Order placed for delivery-attempt test", 201)
    if ok:
        order_id = order.get("id") or order.get("order_id")
        api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "preparing"})
        api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "ready"})
        api("PATCH", f"/orders/{order_id}/status", token=admin_tok, body={"status": "assigned"})
        # pickup transitions to out_for_delivery — no separate PATCH needed
        r_pickup = api("POST", f"/riders/orders/{order_id}/pickup", token=rider_tok)
        expect(r_pickup, "Order out_for_delivery (via rider pickup)", [200], warn_on_fail=True)
        r = api("POST", f"/riders/orders/{order_id}/attempt", token=rider_tok, body={"notes": "customer unreachable"})
        ok_att, _ = expect(r, "Rider marks delivery attempted", [200], warn_on_fail=True)
        if ok_att:
            row = sb_get("orders", f"id=eq.{order_id}&select=status")
            p("order.status == delivery_attempted", "pass" if row and row[0]["status"] == "delivery_attempted" else "fail", str(row))
            time.sleep(1)
            notifs = sb_get("notifications", f"user_id=eq.{u9_id}&order=created_at.desc&limit=5")
            urgent = [n for n in notifs if "attempt" in (n.get("title", "") + n.get("body", "")).lower()]
            p("Delivery-attempted notification sent", "pass" if urgent else "warn", str(notifs[:3]))
            has_urgency_flag = any(
                n.get("urgency") == "high" or
                (n.get("metadata") or {}).get("urgency") == "high"
                for n in notifs
            )
            p("Notification carries explicit urgency=high flag (metadata.urgency)",
              "pass" if has_urgency_flag else "fail",
              "check metadata.urgency on delivery_attempted rows" if not has_urgency_flag else "")
        else:
            gap("Delivery-attempt endpoint failed", str(_))
    else:
        gap("Could not set up order for delivery-attempt test", str(order))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 10 · SQUAD ORDER FLOW")
    # ═════════════════════════════════════════════════════════════════
    u10_id, u10_tok, _, _ = create_test_user("SQUADLEAD")
    seed_wallet(u10_id, 20000)
    squad_body = order_body(payment_method="wallet", is_squad_order=True)
    squad_body["items"] = [{"menu_item_id": menu_item["id"], "quantity": 6}]
    r = api("POST", "/orders", token=u10_tok, body=squad_body)
    ok, order = expect(r, "Squad order placed (6 items)", 201)
    if ok:
        order_id = order.get("id") or order.get("order_id")
        p("order.is_squad_order == True", "pass" if order.get("is_squad_order") else "warn", str(order.get("is_squad_order")))
        squad_email = f"hgsim_squadmember_{uuid.uuid4().hex[:6]}@test.invalid"
        r = api("POST", f"/orders/{order_id}/squad-members", token=u10_tok, body={"emails": [squad_email]})
        expect(r, "Add squad member by email", [200, 201], warn_on_fail=True)
    else:
        gap("Could not place squad order", str(order))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 11 · WALLET TOP-UP + HP BONUS")
    # ═════════════════════════════════════════════════════════════════
    u11_id, u11_tok, _, _ = create_test_user("TOPUPUSER")
    r = api("POST", "/wallet/fund/bank", token=u11_tok)
    expect(r, "Request virtual account", [200, 201], warn_on_fail=True)
    r = api("POST", "/wallet/fund/card", token=u11_tok, body={"amount": 5000, "callback_url": "https://example.com/cb"})
    ok, resp = expect(r, "Initialize card top-up (>= 3000)", [200, 201], warn_on_fail=True)
    if ok:
        has_url = bool(resp.get("authorization_url") or resp.get("data", {}).get("authorization_url"))
        p("Paystack authorization_url returned", "pass" if has_url else "warn", str(resp)[:150])
        gap("Cannot verify real card payment webhook in a live-but-unattended test (needs Paystack test-mode callback)")
    else:
        gap("Card top-up initialization failed", str(resp))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 12 · HP TRANSFER")
    # ═════════════════════════════════════════════════════════════════
    u12a_id, u12a_tok, _, _ = create_test_user("HPXFER_A")
    u12b_id, u12b_tok, _, _ = create_test_user("HPXFER_B")
    seed_hp(u12a_id, 1000)
    seed_hp(u12b_id, 100)
    hp_a_before = get_hp_balance(u12a_tok)
    hp_b_before = get_hp_balance(u12b_tok)
    r = api("POST", "/hp/transfer", token=u12a_tok, body={"recipient_id": u12b_id, "amount": 100})
    ok, _ = expect(r, "User A transfers 100 HP to User B", [200, 201], warn_on_fail=True)
    if ok:
        time.sleep(1)
        hp_a_after = get_hp_balance(u12a_tok)
        hp_b_after = get_hp_balance(u12b_tok)
        ab = (hp_a_before or {}).get("active")
        aa = (hp_a_after or {}).get("active")
        bb = (hp_b_before or {}).get("active")
        ba = (hp_b_after or {}).get("active")
        p("User A HP decreased by ~100", "pass" if ab is not None and aa is not None and (ab - aa) >= 90 else "warn", f"{ab} -> {aa}")
        p("User B HP increased by ~100", "pass" if bb is not None and ba is not None and (ba - bb) >= 90 else "warn", f"{bb} -> {ba}")
        tx_a = sb_get("hp_transactions", f"user_id=eq.{u12a_id}&order=created_at.desc&limit=3")
        tx_b = sb_get("hp_transactions", f"user_id=eq.{u12b_id}&order=created_at.desc&limit=3")
        p("Transaction recorded in both users' HP histories", "pass" if tx_a and tx_b else "warn", f"A:{len(tx_a)} B:{len(tx_b)}")
    else:
        gap("HP transfer endpoint failed", str(_))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 13 · REWARD REDEMPTION")
    # ═════════════════════════════════════════════════════════════════
    rewards = sb_get("rewards", "is_active=eq.true&select=id,hp_cost&limit=1")
    if not rewards:
        rewards = sb_get("rewards", "select=id,hp_cost&limit=1")
    if rewards:
        reward = rewards[0]
        u13_id, u13_tok, _, _ = create_test_user("REWARDUSER")
        seed_hp(u13_id, int(reward.get("hp_cost", 500)) + 200)
        hp_before13 = get_hp_balance(u13_tok)
        r = api("POST", f"/rewards/{reward['id']}/redeem", token=u13_tok)
        ok, redemption = expect(r, "Student redeems reward", [200, 201], warn_on_fail=True)
        if ok:
            # Response shape: {"redemption": {...}, "hp_spent": N}
            redemption_obj = redemption.get("redemption") or redemption
            p("Redemption status == pending", "pass" if redemption_obj.get("status") == "pending" else "warn", str(redemption_obj.get("status")))
            time.sleep(1)
            hp_after13 = get_hp_balance(u13_tok)
            bt13 = (hp_before13 or {}).get("active")
            at13 = (hp_after13 or {}).get("active")
            p("Active HP balance decreased", "pass" if bt13 is not None and at13 is not None and at13 < bt13 else "warn", f"{bt13} -> {at13}")
            redemption_id = redemption_obj.get("id") or redemption.get("redemption_id")
            r = api("PATCH", f"/rewards/admin/redemptions/{redemption_id}", token=admin_tok, body={"status": "fulfilled"})
            expect(r, "Admin fulfills redemption", [200], warn_on_fail=True)
        else:
            gap("Reward redemption failed", str(redemption))
    else:
        gap("No rewards exist in DB — cannot test redemption flow")

    # ═════════════════════════════════════════════════════════════════
    section("SIM 14 · LEADERBOARD RESET + WINNER NOTIFICATION")
    # ═════════════════════════════════════════════════════════════════
    r = api("POST", "/admin/cron/reset-monthly-leaderboard", token=admin_tok)
    ok, resp = expect(r, "Admin triggers monthly leaderboard reset", [200, 202], warn_on_fail=True)
    if ok:
        time.sleep(4)
        snaps = sb_get("leaderboard_snapshots", "order=created_at.desc&limit=15")
        p("leaderboard_snapshots populated", "pass" if snaps else "warn", str(len(snaps)))
        r = api("GET", "/leaderboard/hall-of-fame")
        expect(r, "GET /leaderboard/hall-of-fame", [200], warn_on_fail=True)
    else:
        gap("Could not trigger leaderboard reset cron", str(resp))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 15 · HP DECAY (120-DAY MODEL)")
    # ═════════════════════════════════════════════════════════════════
    r = api("POST", "/admin/cron/hp-decay-check", token=admin_tok)
    ok, resp = expect(r, "Admin triggers hp-decay-check cron", [200, 202], warn_on_fail=True)
    if not ok:
        gap("POST /admin/cron/hp-decay-check not triggerable — check task_map registration", str(resp))
    else:
        time.sleep(3)
        status_r = api("GET", "/admin/cron/status", token=admin_tok)
        expect(status_r, "GET /admin/cron/status reflects hp_decay_check run", [200], warn_on_fail=True)

    # ═════════════════════════════════════════════════════════════════
    section("SIM 16 · ABANDONED CART RECOVERY")
    # ═════════════════════════════════════════════════════════════════
    u16_id, u16_tok, _, _ = create_test_user("CARTUSER")
    r = api("POST", "/cart", token=u16_tok, body={"menu_item_id": menu_item["id"], "quantity": 2})
    expect(r, "Add item to cart", [200, 201], warn_on_fail=True)
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
    sb_patch("carts", f"user_id=eq.{u16_id}", {"updated_at": old_ts})
    r = api("POST", "/admin/cron/scan-abandoned-carts", token=admin_tok)
    ok, resp = expect(r, "Admin triggers scan-abandoned-carts cron", [200, 202], warn_on_fail=True)
    if ok:
        time.sleep(4)
        carts = sb_get("abandoned_carts", f"user_id=eq.{u16_id}")
        p("Cart marked abandoned in abandoned_carts table", "pass" if carts else "warn", str(carts))
        r = api("GET", "/admin/abandoned-carts", token=admin_tok)
        expect(r, "Admin views abandoned carts list", [200], warn_on_fail=True)
        if carts:
            cart_id = carts[0]["id"]
            r = api("POST", f"/admin/abandoned-carts/{cart_id}/nudge", token=admin_tok)
            ok_nudge, _ = expect(r, "Admin sends recovery nudge", [200], warn_on_fail=True)
            if ok_nudge:
                after = sb_get("abandoned_carts", f"id=eq.{cart_id}")
                attempts = after[0].get("recovery_attempts") if after else None
                p("recovery_attempts incremented", "pass" if attempts and attempts >= 1 else "warn", str(attempts))
    else:
        gap("Could not trigger scan-abandoned-carts cron", str(resp))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 17 · ORDER LOCK FLOW")
    # ═════════════════════════════════════════════════════════════════
    u17_id, u17_tok, _, _ = create_test_user("LOCKUSER")
    locked_date = (date.today() + timedelta(days=14)).isoformat()
    r = api("POST", "/order-locks", token=u17_tok, body={"locked_date": locked_date, "discount_pct": 15})
    ok, lock_resp = expect(r, "Student creates order lock", 201)
    if ok:
        lock = lock_resp.get("lock") or lock_resp
        p("lock.status == active", "pass" if lock.get("status") == "active" else "warn", str(lock.get("status")))
        lock_id = lock.get("id")
        new_date = (date.today() + timedelta(days=21)).isoformat()
        r = api("PATCH", f"/order-locks/{lock_id}/reschedule", token=u17_tok, body={"locked_date": new_date})
        ok_re, reslock_resp = expect(r, "Student reschedules lock", [200], warn_on_fail=True)
        if ok_re:
            reslock = reslock_resp.get("lock") or reslock_resp
            p("reschedule_count == 1", "pass" if reslock.get("reschedule_count") == 1 else "warn", str(reslock.get("reschedule_count")))
        r = api("DELETE", f"/order-locks/{lock_id}", token=u17_tok)
        ok_del, dellock = expect(r, "Student cancels lock", [200], warn_on_fail=True)
        if ok_del:
            row = sb_get("order_locks", f"id=eq.{lock_id}&select=status")
            p("lock.status == cancelled (DB)", "pass" if row and row[0]["status"] == "cancelled" else "warn", str(row))
    else:
        gap("Could not create order lock", str(lock))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 18 · NOTIFICATION PREFERENCES + PUSH")
    # ═════════════════════════════════════════════════════════════════
    u18_id, u18_tok, _, _ = create_test_user("PUSHUSER")
    r = api("PATCH", "/notifications/preferences", token=u18_tok, body={"push_enabled": True})
    expect(r, "Update notification preferences", [200], warn_on_fail=True)
    r = api("POST", "/push/subscribe", token=u18_tok, body={
        "subscription": {"endpoint": "https://fcm.example.com/send/sim-token",
                          "keys": {"p256dh": "simkey", "auth": "simauth"}},
    })
    ok, sub = expect(r, "Register push subscription", [200, 201], warn_on_fail=True)
    if ok:
        r = api("DELETE", "/push/subscribe", token=u18_tok, body={"endpoint": "https://fcm.example.com/send/sim-token"})
        expect(r, "Unsubscribe from push", [200, 204], warn_on_fail=True)
    else:
        gap("Push subscribe endpoint failed", str(sub))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 19 · CHALLENGE COMPLETION")
    # ═════════════════════════════════════════════════════════════════
    r = api("POST", "/challenges/admin", token=admin_tok, body={
        "title": f"Sim Challenge {uuid.uuid4().hex[:5]}", "hp_awarded": 50,
        "trigger_type": "orders_count", "trigger_value": 1,
        "time_window": "monthly", "is_active": True,
    })
    ok, challenge = expect(r, "Admin creates challenge", 201)
    if ok:
        challenge_id = challenge.get("id")
        u19_id, u19_tok, _, _ = create_test_user("CHALLENGEUSER")
        r = api("POST", f"/challenges/{challenge_id}/complete", token=u19_tok)
        ok_c, _ = expect(r, "Student completes challenge", [200, 201], warn_on_fail=True)
        if ok_c:
            comp = sb_get("challenge_completions", f"user_id=eq.{u19_id}&challenge_id=eq.{challenge_id}")
            p("challenge_completion record created", "pass" if comp else "warn", str(comp))
        r = api("GET", "/challenges/admin", token=admin_tok)
        expect(r, "Challenge appears in admin list", [200], warn_on_fail=True)
    else:
        gap("Admin could not create challenge", str(challenge))

    # ═════════════════════════════════════════════════════════════════
    section("SIM 20 · SYSTEM SETTINGS + STOREFRONT SECTIONS")
    # ═════════════════════════════════════════════════════════════════
    # Find an existing setting key to update; fall back gracefully if none exist
    existing_settings = sb_get("system_settings", "select=key&limit=1")
    update_key = existing_settings[0]["key"] if existing_settings else None
    if update_key:
        r = api("PATCH", f"/admin/settings/{update_key}", token=admin_tok, body={"value": "sim_updated_value"})
        expect(r, f"Admin updates existing setting ('{update_key}')", [200], warn_on_fail=True)
    else:
        gap("No existing system_settings rows to update — skipping update test")
    r = api("GET", "/admin/settings", token=admin_tok)
    expect(r, "GET /admin/settings", [200], warn_on_fail=True)
    new_key = f"sim_setting_{uuid.uuid4().hex[:5]}"
    r = api("POST", "/admin/settings", token=admin_tok, body={"key": new_key, "value": "sim_value"})
    ok, _ = expect(r, "Admin creates new setting", [200, 201], warn_on_fail=True)
    if ok:
        r = api("GET", "/admin/settings", token=admin_tok)
        ok_list, settings_list = expect(r, "New setting appears in list", [200], warn_on_fail=True)
        if ok_list:
            found = any((s.get("key") == new_key) for s in (settings_list if isinstance(settings_list, list) else settings_list.get("settings", [])))
            p(f"'{new_key}' present in GET /admin/settings", "pass" if found else "warn")

    r = api("POST", "/storefront/sections", token=admin_tok, body={
        "key": f"sim_section_{uuid.uuid4().hex[:5]}", "title": "Sim Section", "section_type": "banner",
    })
    ok, section_row = expect(r, "Admin creates storefront section", [200, 201], warn_on_fail=True)
    if ok:
        section_id = section_row.get("id")
        r = api("DELETE", f"/storefront/sections/{section_id}", token=admin_tok)
        ok_del, _ = expect(r, "Admin deactivates section", [200, 204], warn_on_fail=True)
        r = api("GET", "/storefront/sections")
        ok_sec, sections = expect(r, "GET /storefront/sections excludes deactivated", [200], warn_on_fail=True)
        if ok_sec:
            still_present = any(s.get("id") == section_id for s in (sections if isinstance(sections, list) else sections.get("sections", [])))
            p("Deactivated section no longer in public list", "pass" if not still_present else "warn")

    # ═════════════════════════════════════════════════════════════════
    section("CLEANUP")
    # ═════════════════════════════════════════════════════════════════
    for label, fn in CLEANUP:
        try:
            fn()
        except Exception as exc:
            print(f"    (cleanup {label} failed: {exc})")
    print(f"  Cleaned {len(CLEANUP)} test users")

    # ═════════════════════════════════════════════════════════════════
    section("RESULTS SUMMARY")
    # ═════════════════════════════════════════════════════════════════
    total = sum(RESULTS.values())
    print(f"  Total: {total}  {PASS_C}: {RESULTS['pass']}  {WARN_C}: {RESULTS['warn']}  {FAIL_C}: {RESULTS['fail']}")
    if FAILED_DETAILS:
        print(f"\n{BOLD}  FAILURES:{RESET}")
        for label, detail in FAILED_DETAILS:
            print(f"    ❌ {label} — {detail}")
    if GAPS:
        print(f"\n{BOLD}  GAPS / NEEDS ATTENTION:{RESET}")
        for label, detail in GAPS:
            print(f"    ℹ️  {label} — {detail}")

    sys.exit(1 if RESULTS["fail"] else 0)


if __name__ == "__main__":
    main()
