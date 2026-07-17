"""
wipe_test_data.py — Wipe ALL data from Holy Grills Supabase (auth + tables).

This deletes every authenticated user and every row in every application table.
Run ONLY in pre-launch / dev — this is irreversible.

Usage:
    python scripts/wipe_test_data.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SRK = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

ADMIN_H = {
    "apikey": SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _delete_table(table: str, filter_qs: str = "id=neq.00000000-0000-0000-0000-000000000000") -> int:
    """Delete all rows from a table. Returns rows deleted or -1 on error."""
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?{filter_qs}",
        headers={**ADMIN_H, "Prefer": "return=minimal"},
        timeout=30,
    )
    if r.status_code in (200, 204):
        return r.status_code
    print(f"  ⚠️  Could not wipe {table}: {r.status_code} {r.text[:120]}")
    return -1


def _delete_all_auth_users():
    """List and delete every Supabase Auth user via the admin API."""
    page = 1
    deleted = 0
    while True:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=ADMIN_H,
            params={"page": page, "per_page": 100},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  ⚠️  Could not list auth users (page {page}): {r.status_code} {r.text[:120]}")
            break
        body = r.json()
        users = body if isinstance(body, list) else body.get("users", [])
        if not users:
            break
        for user in users:
            uid = user.get("id")
            if not uid:
                continue
            dr = requests.delete(
                f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
                headers=ADMIN_H,
                timeout=15,
            )
            if dr.status_code in (200, 204):
                deleted += 1
            else:
                print(f"  ⚠️  Failed to delete auth user {uid}: {dr.status_code} {dr.text[:80]}")
        if len(users) < 100:
            break
        page += 1
    return deleted


def main():
    print("\n🗑️  Holy Grills — Full Database Wipe")
    print("=" * 60)
    print("⚠️  This will permanently delete ALL data including auth users.")
    answer = input("Type 'WIPE' to confirm: ").strip()
    if answer != "WIPE":
        print("Aborted.")
        sys.exit(0)

    # ── 0. Clear FK references to profiles so profiles can be deleted ────────
    print("\n[0/3] Clearing FK references that block profile deletion …")
    for table, col in [
        ("kitchen_settings",     "updated_by"),
        ("system_settings",      "updated_by"),
        ("marketplace_requests", "reviewed_by"),
    ]:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?{col}=not.is.null",
            headers={**ADMIN_H, "Prefer": "return=minimal"},
            json={col: None},
            timeout=20,
        )
        icon = "✅" if r.status_code in (200, 204) else "⚠️"
        print(f"  {icon} {table}.{col} cleared → {r.status_code}")

    # ── 1. Application data tables (order matters for FK integrity) ──────────
    # Child tables first, then parents.
    # Filter strategy:
    #   - Tables with a UUID primary key `id`  → id=neq.00000000-0000-0000-0000-000000000000
    #   - wallets                              → user_id=neq.... (no `id` column)
    #   - cron_locks                           → job_name=neq.__NONE__
    APP_TABLES = [
        # Order-related children
        ("order_addon_selections",   "id"),
        ("order_items",              "id"),
        ("order_status_logs",        "id"),
        ("order_reviews",            "id"),
        ("order_share_events",       "id"),
        ("squad_members",            "id"),
        # Orders
        ("orders",                   "id"),
        # HP & wallet
        ("hp_transactions",          "id"),
        ("wallet_transactions",      "id"),
        ("wallet_withdrawals",       "id"),
        ("wallets",                  "user_id"),   # no `id` column
        # Monthly HP tracker
        ("monthly_hp_tracker",       "id"),
        ("hp_bundle_purchases",      "id"),
        # Notifications
        ("notifications",            "id"),
        ("push_subscriptions",       "id"),
        ("notification_blasts",      "id"),
        ("notification_preferences", "id"),
        # Delivery / batches
        ("delivery_batches",         "id"),
        # Carts & saved
        ("cart_items",               "id"),
        ("saved_for_later",          "id"),
        # Events & marketplace
        ("event_checkins",           "id"),   # was incorrectly "event_registrations"
        ("event_tickets",            "id"),
        ("marketplace_purchases",    "id"),
        ("promo_code_uses",          "id"),
        ("marketplace_requests",     "id"),
        # Order locks
        ("order_locks",              "id"),
        # Login streaks & activity
        ("login_streaks",            "id"),
        # Rewards
        ("reward_redemptions",       "id"),
        # Referrals
        ("referrals",                "id"),
        # Misc user-linked tables
        ("first_order_gifts",        "id"),
        ("device_tokens",            "id"),
        ("device_fingerprints",      "id"),
        ("rider_profiles",           "id"),
        ("flash_redemptions",        "id"),
        ("webhook_events",           "id"),
        ("cron_locks",               "job_name"),  # PK is job_name TEXT
        # Banners (test data)
        ("banners",                  "id"),
        # Profiles (must come AFTER all FK children above)
        ("profiles",                 "id"),
    ]

    _UUID_ZERO = "00000000-0000-0000-0000-000000000000"

    print("\n[1/3] Wiping application tables …")
    for table, pk_col in APP_TABLES:
        if pk_col == "job_name":
            filter_qs = "job_name=neq.__NONE__"
        else:
            filter_qs = f"{pk_col}=neq.{_UUID_ZERO}"
        status = _delete_table(table, filter_qs)
        icon = "✅" if status != -1 else "❌"
        print(f"  {icon} {table}")

    # ── 2. Auth users ─────────────────────────────────────────────────────────
    print("\n[2/3] Deleting all Supabase Auth users …")
    deleted_auth = _delete_all_auth_users()
    print(f"  ✅ Deleted {deleted_auth} auth user(s)")

    # ── 3. Re-seed static reference data (operating hours etc.) ──────────────
    print("\n[3/3] Done.")
    print("\n✅ Wipe complete. Database is clean and ready for fresh sign-ups.")
    print("   Remember to re-run scripts/seed.py if you need menu/settings data back.\n")


if __name__ == "__main__":
    main()
