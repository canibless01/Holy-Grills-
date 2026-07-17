#!/usr/bin/env python3
"""
scripts/cleanup_test_data.py
Delete every test user (and all their DB rows) from Supabase.
Run: python scripts/cleanup_test_data.py
"""

import os, sys, requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SRK          = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

H = {
    "apikey":        SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}
HD = {**H, "Prefer": ""}   # deletes — no body needed

GREEN  = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
BOLD   = "\033[1m";  RESET = "\033[0m"

def ok(msg):   print(f"  \033[92m✅\033[0m {msg}")
def fail(msg): print(f"  \033[91m❌\033[0m {msg}")
def info(msg): print(f"  \033[93mℹ️ \033[0m {msg}")
def section(t): print(f"\n{BOLD}{'─'*60}\n  {t}\n{'─'*60}{RESET}")


# ── 1. Fetch all auth users ────────────────────────────────────────────────
section("1 · Fetching all Supabase auth users")

page, per_page, all_users = 1, 1000, []
while True:
    r = requests.get(
        f"{SUPABASE_URL}/auth/v1/admin/users?page={page}&per_page={per_page}",
        headers=H,
    )
    data = r.json()
    batch = data.get("users", [])
    all_users.extend(batch)
    if len(batch) < per_page:
        break
    page += 1

info(f"Total auth users found: {len(all_users)}")


# ── 2. Identify test users ─────────────────────────────────────────────────
TEST_DOMAINS  = ("@holygrills-test.ng", "@test.holygrills.ng", "@test.invalid")
TEST_PREFIXES = (
    "testuser_", "flowtest_", "newapi_", "smoke_", "squad_",
    "user_a_", "user_b_", "bday_", "flow_", "guest_",
    "hgtest_", "hgnf_",
)

def is_test(u):
    email = (u.get("email") or "").lower()
    if any(email.endswith(d) for d in TEST_DOMAINS):
        return True
    local = email.split("@")[0]
    return any(local.startswith(p) for p in TEST_PREFIXES)

test_users = [u for u in all_users if is_test(u)]
real_users  = [u for u in all_users if not is_test(u)]

info(f"Test users to delete : {len(test_users)}")
info(f"Real users kept      : {len(real_users)}")

if not test_users:
    print(f"\n{GREEN}Nothing to clean — no test users found.{RESET}")
    sys.exit(0)

for u in test_users:
    print(f"    → {u.get('email','?')}  ({u['id'][:8]})")


# ── 3. Helper ──────────────────────────────────────────────────────────────
def id_in(ids):
    return "(" + ",".join(ids) + ")"

def db_delete(table, qs):
    """DELETE from table using the given query-string filter."""
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}{qs}", headers=HD)
    if r.status_code in (200, 204):
        ok(f"{table}")
    elif r.status_code == 404:
        info(f"{table} — not found (skip)")
    else:
        info(f"{table}: HTTP {r.status_code}  {r.text[:120]}")


test_ids    = [u["id"] for u in test_users]
test_emails = [u["email"] for u in test_users if u.get("email")]
uid_filter  = "?user_id=in." + id_in(test_ids)


# ── 4. Collect order IDs so we can delete child rows first ─────────────────
section("2 · Resolving test order IDs")

r = requests.get(
    f"{SUPABASE_URL}/rest/v1/orders?user_id=in.{id_in(test_ids)}&select=id",
    headers=H,
)
order_ids = [row["id"] for row in (r.json() if r.status_code == 200 else [])]
info(f"Orders found: {len(order_ids)}")


# ── 5. Delete rows in FK-safe order ───────────────────────────────────────
section("3 · Deleting dependent rows")

# Order children first
if order_ids:
    oid_qs = "?order_id=in." + id_in(order_ids)
    db_delete("order_items",          oid_qs)
    db_delete("order_status_history", oid_qs)
    db_delete("payment_transactions", oid_qs)
    db_delete("squad_members",        oid_qs)
    db_delete("first_order_gifts",    oid_qs)
    db_delete("order_share_events",   oid_qs)

# user_id-keyed tables
USER_TABLES = [
    "payment_transactions",
    "wallet_transactions",
    "hp_transactions",
    "notifications",
    "device_tokens",
    "notification_preferences",
    "notification_blasts",
    "abandoned_carts",
    "hp_redemptions",
    "reward_redemptions",
    "challenge_completions",
    "event_checkins",
    "event_tickets",
    "catering_requests",
    "marketplace_purchases",
    "spin_history",
    "rider_batches",
    "wallet_withdrawals",
    "virtual_accounts",
    "addresses",
    # New-features tables (user_id-keyed)
    "login_streaks",
    "monthly_hp_tracker",
    "saved_for_later",
    "order_locks",
    "orders",                # after children are gone
]
for tbl in USER_TABLES:
    db_delete(tbl, uid_filter)

# Referrals — keyed by referrer_id AND referred_id
for col in ("referrer_id", "referred_id"):
    db_delete("referrals", f"?{col}=in.{id_in(test_ids)}")

# rider_profiles (user_id)
db_delete("rider_profiles", uid_filter)

# Newsletter subscribers — keyed by email, not user_id
if test_emails:
    emails_in = "(" + ",".join(test_emails) + ")"
    db_delete("newsletter_subscribers", f"?email=in.{emails_in}")


# ── 5b. Null FK columns that reference profiles (block deletion otherwise) ──
section("3b · Nulling FK references that point at test profiles")

FK_NULL_COLUMNS = [
    # (table, column)
    ("marketplace_listings",  "vendor_id"),
    ("events",                "assigned_to"),
    ("delivery_batches",      "rider_id"),
    ("kitchen_settings",      "updated_by"),
    ("system_settings",       "updated_by"),
]

uid_in_pg = id_in(test_ids)   # e.g.  (uuid1,uuid2,...)

for tbl, col in FK_NULL_COLUMNS:
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{tbl}?{col}=in.{uid_in_pg}",
        headers={**H, "Prefer": "return=minimal"},
        json={col: None},
    )
    if r.status_code in (200, 204):
        ok(f"Nulled {tbl}.{col}")
    elif r.status_code == 404:
        info(f"{tbl}.{col} — not found (skip)")
    else:
        info(f"{tbl}.{col}: HTTP {r.status_code}  {r.text[:120]}")


# ── 6. Delete profiles ────────────────────────────────────────────────────
section("4 · Deleting profiles")
db_delete("profiles", "?id=in." + id_in(test_ids))


# ── 7. Delete auth users ──────────────────────────────────────────────────
section("5 · Deleting auth users")
deleted = failed = 0
for u in test_users:
    uid   = u["id"]
    email = u.get("email", uid[:8])
    r = requests.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{uid}", headers=H)
    if r.status_code in (200, 204):
        ok(f"{email}")
        deleted += 1
    else:
        fail(f"{email} — {r.status_code} {r.text[:80]}")
        failed += 1


# ── 8. Summary ────────────────────────────────────────────────────────────
section("Summary")
print(f"  Auth users deleted : {GREEN}{deleted}{RESET}")
if failed:
    print(f"  Auth delete errors : {RED}{failed}{RESET}")
print(f"  Real users kept    : {len(real_users)}")
print()
if failed:
    print(f"  {YELLOW}⚠️  Done with {failed} error(s){RESET}")
else:
    print(f"  {GREEN}✅ All test data removed{RESET}")
