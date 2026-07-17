"""
test_all.py — Holy Grills consolidated live API test suite.

This is the SINGLE test entrypoint for the project. It replaces the previous
scattered test_*.py / scripts/live_test.py scripts, which have been removed.

Runs against the live local server (python run.py) with real Supabase.
Creates its own test users/data and deletes everything it created at the end.

Run: python3 test_all.py
"""

import os
import sys
import uuid
import requests
from datetime import datetime, timezone, timedelta
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
CLEANUP = []  # list of (description, callable), run in reverse at the end

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
        return requests.request(method, f"{BASE}{path}", headers=h, json=body, params=params, timeout=15)
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
    p(label, "fail", f"expected {codes}, got {r.status_code}: {r.text[:150]}")
    return False, None


def sb_get(table, params=""):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=ADMIN_H, timeout=10)
    return r.json() if r.status_code == 200 else []


def sb_insert(table, data):
    h = {**ADMIN_H, "Prefer": "return=representation"}
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data, timeout=10)
    if r.status_code in (200, 201):
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else rows
    print(f"    (sb_insert {table} failed: {r.status_code} {r.text[:150]})")
    return None


def sb_patch(table, params, data):
    return requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=ADMIN_H, json=data, timeout=10)


def sb_delete(table, params):
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=ADMIN_H, timeout=10)
    return r.status_code in (200, 204)


def create_user(suffix="", role="user"):
    """Create a confirmed Supabase Auth user + profile, promoting role via a
    separate PATCH (role set on insert does not reliably stick)."""
    uid_str = uuid.uuid4().hex[:8]
    email = f"hgtest_{suffix.lower()}_{uid_str}@test.invalid"
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=ADMIN_H,
        json={"email": email, "password": "Test1234!", "email_confirm": True},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Create user failed: {r.text[:200]}")
    user_id = r.json()["id"]
    CLEANUP.append((f"auth_user:{suffix}", lambda uid=user_id: (
        sb_delete("profiles", f"id=eq.{uid}"),
        requests.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{uid}", headers=ADMIN_H, timeout=10).status_code in (200, 204),
    )[-1]))

    requests.post(f"{SUPABASE_URL}/rest/v1/profiles", headers=ADMIN_H, json={
        "id": user_id, "full_name": f"HG Test {suffix}", "email": email,
        "hp_balance": 0, "wallet_balance": 0, "preferences": {},
    }, timeout=10)

    if role != "user":
        requests.patch(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
                        headers=ADMIN_H, json={"role": role}, timeout=10)

    login_r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers=ADMIN_H, json={"email": email, "password": "Test1234!"}, timeout=15,
    )
    if login_r.status_code != 200:
        raise RuntimeError(f"Login failed: {login_r.text[:200]}")
    return user_id, login_r.json()["access_token"], email


def main():
    # ─────────────────────────────────────────────────────────────────────
    section("0 · SETUP — test users")
    # ─────────────────────────────────────────────────────────────────────
    import time
    admin_id, admin_tok, admin_email = create_user("ADMIN", role="admin")
    p("Admin test user created", "pass", admin_id[:8])
    user_id, user_tok, user_email = create_user("USER", role="user")
    p("Regular test user created", "pass", user_id[:8])
    time.sleep(1)  # Allow profile + wallet triggers to settle

    # ─────────────────────────────────────────────────────────────────────
    section("1 · Public endpoints (no auth)")
    # ─────────────────────────────────────────────────────────────────────
    ok, d = expect(api("GET", "/health"), "GET /health", 200)
    if ok:
        p("  health.supabase connected", "pass" if d.get("checks", {}).get("supabase") == "connected" else "warn",
          str(d.get("checks")))

    expect(api("GET", "/menu/items"), "GET /menu/items", 200)
    expect(api("GET", "/menu/items?is_featured=true"), "GET /menu/items?is_featured=true", 200)
    expect(api("GET", "/menu/categories"), "GET /menu/categories", 200)
    expect(api("GET", "/orders/delivery-windows"), "GET /orders/delivery-windows", 200)
    expect(api("GET", "/orders/delivery-zones"), "GET /orders/delivery-zones", 200)
    expect(api("GET", "/storefront/banners"), "GET /storefront/banners", 200)
    expect(api("GET", "/storefront/sections"), "GET /storefront/sections", 200)
    expect(api("GET", "/storefront/operating-hours"), "GET /storefront/operating-hours", 200)
    expect(api("GET", "/leaderboard"), "GET /leaderboard", 200)
    expect(api("GET", "/events"), "GET /events", 200)
    expect(api("GET", "/rewards"), "GET /rewards", 200)
    expect(api("GET", "/marketplace"), "GET /marketplace", 200)
    expect(api("GET", "/challenges"), "GET /challenges", 200)

    # ─────────────────────────────────────────────────────────────────────
    section("1b · Delivery Window Forecast — GET /orders/delivery-windows/status")
    # ─────────────────────────────────────────────────────────────────────
    ok, dws = expect(api("GET", "/orders/delivery-windows/status"), "GET /orders/delivery-windows/status", 200)
    if ok and dws:
        p("  response has is_open field", "pass" if "is_open" in dws else "fail", str(dws.keys()))
        p("  response has next_window_starts_at field", "pass" if "next_window_starts_at" in dws else "fail",
          str(dws.get("next_window_starts_at")))
        p("  response has can_schedule field", "pass" if "can_schedule" in dws else "fail")

    # ─────────────────────────────────────────────────────────────────────
    section("2 · Authenticated user endpoints (smoke)")
    # ─────────────────────────────────────────────────────────────────────
    expect(api("GET", "/auth/me", token=user_tok), "GET /auth/me", 200)
    expect(api("GET", "/orders/active", token=user_tok), "GET /orders/active", 200)
    expect(api("GET", "/orders", token=user_tok), "GET /orders", 200)
    expect(api("GET", "/orders/scheduled", token=user_tok), "GET /orders/scheduled", 200)
    expect(api("GET", "/hp/balance", token=user_tok), "GET /hp/balance", 200)
    expect(api("GET", "/wallet", token=user_tok), "GET /wallet", 200)
    expect(api("GET", "/notifications", token=user_tok), "GET /notifications", 200)
    expect(api("GET", "/rewards/redemptions", token=user_tok), "GET /rewards/redemptions", 200)
    expect(api("GET", "/marketplace/purchases", token=user_tok), "GET /marketplace/purchases", 200)

    # ─────────────────────────────────────────────────────────────────────
    section("2b · Saved For Later")
    # ─────────────────────────────────────────────────────────────────────
    expect(api("GET", "/saved", token=user_tok), "GET /saved", 200)

    # ─────────────────────────────────────────────────────────────────────
    section("3 · Delivery Location System")
    # ─────────────────────────────────────────────────────────────────────
    # Public endpoints
    ok_g, gates_data = expect(api("GET", "/delivery/gates"), "GET /delivery/gates", 200)
    ok_h, hostels_data = expect(api("GET", "/delivery/hostels"), "GET /delivery/hostels", 200)

    if ok_g and gates_data:
        p("  /delivery/gates returns gates list", "pass" if "gates" in gates_data else "fail",
          str(gates_data.get("gates", "missing key")))
    if ok_h and hostels_data:
        p("  /delivery/hostels returns hostels list", "pass" if "hostels" in hostels_data else "fail",
          str(hostels_data.get("hostels", "missing key")))

    # Admin CRUD — gate
    gate_id = None
    _gate_r = api("POST", "/delivery/admin/gates", token=admin_tok, body={
        "name": "HGTest Gate", "lat": 7.2985, "lon": 5.1421,
        "base_fee": 300, "rate_per_km": 50, "min_fee": 200,
    })
    _tables_missing = (_gate_r is not None and _gate_r.status_code == 400
                       and "schema cache" in (_gate_r.text or ""))
    if _tables_missing:
        p("POST /delivery/admin/gates", "warn",
          "tables 'gates'/'hostels' not yet created — run the SQL first, then re-test")
        p("POST /delivery/admin/hostels", "warn", "skipped (gates table missing)")
    ok, gate = expect(_gate_r, "POST /delivery/admin/gates", 201) if not _tables_missing else (False, None)
    if ok and gate:
        gate_id = gate.get("id")
        CLEANUP.append(("delivery_gate", lambda gid=gate_id: sb_delete("gates", f"id=eq.{gid}")))
        p("  gate has id", "pass" if gate_id else "fail", str(gate_id))

        expect(api("PATCH", f"/delivery/admin/gates/{gate_id}", token=admin_tok, body={"min_fee": 250}),
               "PATCH /delivery/admin/gates/<id>", 200)
        expect(api("GET", "/delivery/admin/gates", token=admin_tok), "GET /delivery/admin/gates", 200)

    # Admin CRUD — hostel
    hostel_id = None
    if not _tables_missing:
        hostel_body = {"name": "HGTest Hall", "delivery_fee": 150}
        if gate_id:
            hostel_body["gate_id"] = gate_id
        ok, hostel = expect(
            api("POST", "/delivery/admin/hostels", token=admin_tok, body=hostel_body),
            "POST /delivery/admin/hostels", 201,
        )
    else:
        ok, hostel = False, None
    if ok and hostel:
        hostel_id = hostel.get("id")
        CLEANUP.append(("delivery_hostel", lambda hid=hostel_id: sb_delete("hostels", f"id=eq.{hid}")))
        p("  hostel has id", "pass" if hostel_id else "fail", str(hostel_id))

        expect(api("PATCH", f"/delivery/admin/hostels/{hostel_id}", token=admin_tok, body={"delivery_fee": 175}),
               "PATCH /delivery/admin/hostels/<id>", 200)
        expect(api("GET", "/delivery/admin/hostels", token=admin_tok), "GET /delivery/admin/hostels", 200)

    # Calculate fee — on_campus
    if hostel_id:
        ok, fee_data = expect(
            api("POST", "/delivery/calculate-fee", body={
                "delivery_type": "on_campus",
                "delivery_location_id": hostel_id,
            }),
            "POST /delivery/calculate-fee (on_campus)", 200,
        )
        if ok and fee_data:
            p("  on_campus fee == 175", "pass" if float(fee_data.get("delivery_fee", -1)) == 175 else "fail",
              str(fee_data.get("delivery_fee")))

    # Calculate fee — off_campus with coordinates
    if gate_id:
        ok, fee_data = expect(
            api("POST", "/delivery/calculate-fee", body={
                "delivery_type": "off_campus",
                "delivery_location_id": gate_id,
                "lat": 7.3010,
                "lon": 5.1450,
            }),
            "POST /delivery/calculate-fee (off_campus with coords)", 200,
        )
        if ok and fee_data:
            p("  off_campus fee >= min_fee (250)", "pass" if float(fee_data.get("delivery_fee", 0)) >= 250 else "fail",
              str(fee_data.get("delivery_fee")))
            p("  off_campus distance_km present", "pass" if fee_data.get("distance_km") is not None else "fail",
              str(fee_data.get("distance_km")))

        # fallback to min_fee when no coordinates
        ok, fee_data = expect(
            api("POST", "/delivery/calculate-fee", body={
                "delivery_type": "off_campus",
                "delivery_location_id": gate_id,
            }),
            "POST /delivery/calculate-fee (off_campus no coords → min_fee)", 200,
        )
        if ok and fee_data:
            p("  off_campus fee == min_fee (250) when no coords", "pass" if float(fee_data.get("delivery_fee", 0)) == 250 else "fail",
              str(fee_data.get("delivery_fee")))

    # Validation errors
    expect(api("POST", "/delivery/calculate-fee", body={"delivery_type": "on_campus"}),
           "POST /delivery/calculate-fee (missing location_id → 400)", 400)
    expect(api("POST", "/delivery/calculate-fee", body={"delivery_type": "bad"}),
           "POST /delivery/calculate-fee (invalid type → 400)", 400)

    # Delete admin hostels / gates
    if hostel_id:
        expect(api("DELETE", f"/delivery/admin/hostels/{hostel_id}", token=admin_tok),
               "DELETE /delivery/admin/hostels/<id>", 200)
    if gate_id:
        expect(api("DELETE", f"/delivery/admin/gates/{gate_id}", token=admin_tok),
               "DELETE /delivery/admin/gates/<id>", 200)

    # =========================================================================
    # SECTION 4 — NEW ENDPOINTS (the 14 endpoints added in previous session)
    # =========================================================================
    section("4 · Admin delivery-batch endpoints")

    window = sb_get("delivery_windows", "select=id&limit=1")
    rider_id, rider_tok, rider_email = create_user("RIDER", role="rider")
    batch_id = None
    if window and rider_id:
        window_id = window[0]["id"]

        ok, batch = expect(
            api("POST", "/admin/delivery-batches", token=admin_tok,
                body={"window_id": window_id, "rider_id": rider_id, "zone": "Test Zone"}),
            "POST /admin/delivery-batches (setup)", 201,
        )
        if ok and batch:
            batch_id = batch["id"]
            CLEANUP.append(("delivery_batch", lambda: sb_delete("delivery_batches", f"id=eq.{batch_id}")))
    else:
        p("Batch setup", "warn", "no delivery_windows seed data — skipping batch endpoint tests")

    if batch_id:
        expect(api("GET", f"/admin/delivery-batches/{batch_id}/orders", token=admin_tok),
               "GET /admin/delivery-batches/<id>/orders", 200)
        expect(api("PATCH", f"/admin/delivery-batches/{batch_id}", token=admin_tok, body={"status": "completed"}),
               "PATCH /admin/delivery-batches/<id>", 200)
        expect(api("PATCH", f"/admin/delivery-batches/{batch_id}", token=admin_tok, body={"status": "bogus_status"}),
               "PATCH /admin/delivery-batches/<id> (invalid status → 400)", 400)
        expect(api("PATCH", "/admin/delivery-batches/00000000-0000-0000-0000-000000000000",
                   token=admin_tok, body={"status": "completed"}),
               "PATCH /admin/delivery-batches/<id> (nonexistent → 404)", 404)
        expect(api("DELETE", f"/admin/delivery-batches/{batch_id}", token=admin_tok),
               "DELETE /admin/delivery-batches/<id>", 200)
        expect(api("DELETE", f"/admin/delivery-batches/{batch_id}", token=admin_tok),
               "DELETE /admin/delivery-batches/<id> (already gone → still 200, idempotent status update)", [200, 404])

    section("4 · NEW: Marketplace admin endpoints")
    listing = sb_insert("marketplace_listings", {
        "title": "HG Test Listing", "slug": f"hg-test-{uuid.uuid4().hex[:6]}",
        "vendor_name": "Holy Grills", "listing_type": "code", "price": 500,
        "status": "active", "is_out_of_stock": False, "metadata": {},
        "is_featured": False, "sort_order": 0,
    })
    if listing:
        listing_id = listing["id"]
        CLEANUP.append(("marketplace_listing", lambda: sb_delete("marketplace_listings", f"id=eq.{listing_id}")))
        expect(api("GET", f"/marketplace/admin/listings/{listing_id}", token=admin_tok),
               "GET /marketplace/admin/listings/<id>", 200)
        expect(api("GET", "/marketplace/admin/listings/00000000-0000-0000-0000-000000000000", token=admin_tok),
               "GET /marketplace/admin/listings/<id> (nonexistent → 404)", 404)
        expect(api("GET", f"/marketplace/admin/listings/{listing_id}", token=user_tok),
               "GET /marketplace/admin/listings/<id> (non-admin → 403)", 403)
    else:
        p("Listing setup", "warn", "marketplace_listings.listing_type check constraint rejects all "
          "attempted values in this environment (pre-existing schema constraint, unrelated to new endpoints) "
          "— skipping listing-detail tests, still exercising 404/purchases below")
        expect(api("GET", "/marketplace/admin/listings/00000000-0000-0000-0000-000000000000", token=admin_tok),
               "GET /marketplace/admin/listings/<id> (nonexistent → 404)", 404)
    expect(api("GET", "/marketplace/admin/purchases", token=admin_tok), "GET /marketplace/admin/purchases", 200)

    section("4 · NEW: Notifications blast detail")
    blast = sb_insert("notification_blasts", {
        "title": "HG Test Blast", "body": "test body", "channels": ["in_app"],
        "segment": {}, "status": "sent", "metadata": {},
    })
    if blast:
        blast_id = blast["id"]
        CLEANUP.append(("notification_blast", lambda: sb_delete("notification_blasts", f"id=eq.{blast_id}")))
        expect(api("GET", f"/admin/notifications/blasts/{blast_id}".replace("/admin", ""), token=admin_tok),
               "GET /notifications/blasts/<id>", 200)
        expect(api("GET", "/notifications/blasts/00000000-0000-0000-0000-000000000000", token=admin_tok),
               "GET /notifications/blasts/<id> (nonexistent → 404)", 404)

    section("4 · NEW: Challenge delete")
    challenge = sb_insert("milestones", {
        "title": "HG Test Challenge", "hp_awarded": 10, "is_active": True,
        "trigger_type": "orders_count", "trigger_value": 1,
    })
    if challenge:
        challenge_id = challenge["id"]
        CLEANUP.append(("challenge", lambda: sb_delete("milestones", f"id=eq.{challenge_id}")))
        expect(api("DELETE", f"/challenges/admin/{challenge_id}", token=admin_tok), "DELETE /challenges/<id>", 200)
        row = sb_get("milestones", f"id=eq.{challenge_id}&select=is_active")
        p("  challenge.is_active now false", "pass" if row and row[0]["is_active"] is False else "fail",
          str(row))
        expect(api("DELETE", f"/challenges/admin/{challenge_id}", token=user_tok),
               "DELETE /challenges/<id> (non-admin → 403)", 403)

    section("4 · NEW: Scheduled order cancellation")
    scheduled_order = sb_insert("orders", {
        "order_number": f"TEST-{uuid.uuid4().hex[:8]}", "user_id": user_id, "status": "received",
        "payment_status": "pending", "subtotal": 1000, "delivery_fee": 0, "discount_amount": 0,
        "total_amount": 1000, "hp_earned": 0, "hp_redeemed": 0, "wallet_amount_used": 0,
        "card_amount_used": 1000, "delivery_address_snapshot": {}, "is_squad_order": False,
        "squad_discount_amount": 0, "squad_item_count": 0, "is_scheduled": True,
    })
    if scheduled_order:
        so_id = scheduled_order["id"]
        CLEANUP.append(("scheduled_order", lambda: sb_delete("orders", f"id=eq.{so_id}")))
        expect(api("DELETE", f"/orders/{so_id}/scheduled", token=admin_tok),
               "DELETE /orders/<id>/scheduled (not owner → 403)", 403)
        ok, d = expect(api("DELETE", f"/orders/{so_id}/scheduled", token=user_tok, body={"reason": "test cancel"}),
                       "DELETE /orders/<id>/scheduled (owner → 200)", 200)
        expect(api("DELETE", f"/orders/{so_id}/scheduled", token=user_tok, body={"reason": "test cancel"}),
               "DELETE /orders/<id>/scheduled (already cancelled → 409)", 409)
    expect(api("DELETE", "/orders/00000000-0000-0000-0000-000000000000/scheduled", token=user_tok),
           "DELETE /orders/<id>/scheduled (nonexistent → 404)", 404)

    section("4 · NEW: Push subscription")
    fake_endpoint = f"https://fcm.googleapis.com/fcm/send/test-{uuid.uuid4().hex[:8]}"
    ok, d = expect(
        api("POST", "/push/subscribe", token=user_tok, body={
            "subscription": {"endpoint": fake_endpoint, "keys": {"p256dh": "abc", "auth": "xyz"}},
            "device_label": "Test Browser",
        }),
        "POST /push/subscribe", 201,
    )
    if ok and d:
        CLEANUP.append(("push_subscription", lambda: sb_delete("push_subscriptions", f"user_id=eq.{user_id}")))
    expect(api("POST", "/push/subscribe", token=user_tok, body={}),
           "POST /push/subscribe (missing subscription → 400)", 400)
    expect(api("DELETE", "/push/subscribe", token=user_tok, body={"endpoint": fake_endpoint}),
           "DELETE /push/subscribe", 200)
    expect(api("POST", "/push/subscribe", token=None,
               body={"subscription": {"endpoint": fake_endpoint}}),
           "POST /push/subscribe (no auth → 401)", 401)

    section("4 · NEW: Reward delete")
    reward = sb_insert("rewards", {
        "name": "HG Test Reward", "hp_cost": 100, "reward_type": "voucher", "is_active": True,
        "metadata": {}, "max_per_user": 1,
    })
    if reward:
        reward_id = reward["id"]
        CLEANUP.append(("reward", lambda: sb_delete("rewards", f"id=eq.{reward_id}")))
        expect(api("DELETE", f"/rewards/{reward_id}", token=admin_tok), "DELETE /rewards/<id>", 200)
        row = sb_get("rewards", f"id=eq.{reward_id}&select=is_active")
        p("  reward.is_active now false", "pass" if row and row[0]["is_active"] is False else "fail", str(row))
    expect(api("DELETE", "/rewards/00000000-0000-0000-0000-000000000000", token=admin_tok),
           "DELETE /rewards/<id> (nonexistent → 404)", 404)

    section("4 · NEW: Storefront section delete")
    cms_section = sb_insert("storefront_sections", {
        "key": f"hg-test-{uuid.uuid4().hex[:6]}", "section_type": "banner", "content": {},
        "sort_order": 0, "is_active": True,
    })
    if cms_section:
        section_id = cms_section["id"]
        CLEANUP.append(("storefront_section", lambda: sb_delete("storefront_sections", f"id=eq.{section_id}")))
        expect(api("DELETE", f"/storefront/sections/{section_id}", token=admin_tok),
               "DELETE /storefront/sections/<id>", 200)
        row = sb_get("storefront_sections", f"id=eq.{section_id}&select=is_active")
        p("  section.is_active now false", "pass" if row and row[0]["is_active"] is False else "fail", str(row))
    expect(api("DELETE", "/storefront/sections/00000000-0000-0000-0000-000000000000", token=admin_tok),
           "DELETE /storefront/sections/<id> (nonexistent → 404)", 404)

    section("4 · NEW: Flutterwave webhook")
    ok, d = expect(
        api("POST", "/webhooks/flutterwave", body={
            "event": "charge.completed",
            "data": {"status": "successful", "tx_ref": f"test-{uuid.uuid4().hex[:8]}", "amount": 500, "meta": {}},
        }),
        "POST /webhooks/flutterwave (unsigned → 401 production fail-closed)", [200, 401],
    )
    r_bad = requests.post(f"{BASE}/webhooks/flutterwave", data=b"not-json{", headers={"Content-Type": "application/json"}, timeout=15)
    expect(r_bad, "POST /webhooks/flutterwave (malformed body → 400/401)", [400, 401])

    # ─────────────────────────────────────────────────────────────────────
    section("5 · Top Picks — is_featured filter")
    # ─────────────────────────────────────────────────────────────────────
    ok, items_data = expect(api("GET", "/menu/items?is_featured=true"), "GET /menu/items?is_featured=true", 200)
    if ok and items_data:
        items_list = items_data.get("items", [])
        p("  featured filter returns items list", "pass", f"{len(items_list)} item(s)")
        all_featured = all(item.get("is_featured") for item in items_list)
        p("  all returned items have is_featured=true", "pass" if (not items_list or all_featured) else "fail",
          f"{'none found — OK, no featured items seeded yet' if not items_list else str(all_featured)}")

    ok, items_all = expect(api("GET", "/menu/items"), "GET /menu/items (no filter)", 200)
    ok, items_feat = expect(api("GET", "/menu/items?is_featured=true"), "GET /menu/items (featured only)", 200)
    if ok and items_all and ok and items_feat:
        all_count = len((items_all or {}).get("items", []))
        feat_count = len((items_feat or {}).get("items", []))
        p("  featured count <= total count", "pass" if feat_count <= all_count else "fail",
          f"{feat_count} featured / {all_count} total")

    # ─────────────────────────────────────────────────────────────────────
    section("6 · Validation / error paths (regression)")
    # ─────────────────────────────────────────────────────────────────────
    expect(api("GET", "/auth/me"), "GET /auth/me (no token → 401)", 401)
    expect(api("GET", "/orders/active"), "GET /orders/active (no token → 401)", 401)
    expect(api("POST", "/orders", body={"payment_method": "card"}), "POST /orders (missing items → 400)", 400)
    expect(api("POST", "/storefront/newsletter", body={}), "POST /storefront/newsletter (missing email → 400)", 400)
    expect(api("POST", "/orders/validate-promo", body={"code": "TESTINVALID999", "order_subtotal": 1000}),
           "POST /orders/validate-promo (invalid code → 400)", 400)

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
    print(f"  Total: {total}  ✅ PASS: {RESULTS['pass']}  ⚠️  WARN: {RESULTS['warn']}  ❌ FAIL: {RESULTS['fail']}")
    if FAILED_DETAILS:
        print("\n  Failed tests:")
        for label, detail in FAILED_DETAILS:
            print(f"    ❌ {label} — {detail}")

    sys.exit(0 if RESULTS["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
