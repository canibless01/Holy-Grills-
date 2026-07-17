"""
Holy Grills — Orphaned Auth User Cleanup
=========================================
Deletes Supabase Auth users that have no corresponding profile row.

Safe to re-run: it only deletes confirmed orphans.
Run: python scripts/cleanup_orphans.py
"""
import os
import requests
import sys

SB = os.environ["SUPABASE_URL"].rstrip("/")
SRK = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type": "application/json",
}

PASS = "✓"
FAIL = "✗"
INFO = "→"


def get_all_auth_users():
    """Paginate through all Supabase Auth users."""
    users = []
    page = 1
    while True:
        r = requests.get(
            f"{SB}/auth/v1/admin/users?page={page}&per_page=200",
            headers=HEADERS,
            timeout=30,
        )
        if r.status_code != 200:
            print(f"{FAIL} Could not fetch auth users: {r.status_code} {r.text[:200]}")
            sys.exit(1)
        batch = r.json().get("users", [])
        users.extend(batch)
        if len(batch) < 200:
            break
        page += 1
    return users


def get_profile_ids():
    """Return set of user IDs that have a profile row (paginated)."""
    ids = set()
    page_size = 1000
    offset = 0
    while True:
        r = requests.get(
            f"{SB}/rest/v1/profiles?select=id&limit={page_size}&offset={offset}",
            headers=HEADERS,
            timeout=30,
        )
        if r.status_code != 200:
            print(f"{FAIL} Could not fetch profiles: {r.status_code} {r.text[:200]}")
            sys.exit(1)
        batch = r.json()
        for row in batch:
            ids.add(row["id"])
        if len(batch) < page_size:
            break
        offset += page_size
    return ids


def delete_auth_user(user_id: str, email: str) -> bool:
    r = requests.delete(
        f"{SB}/auth/v1/admin/users/{user_id}",
        headers=HEADERS,
        timeout=15,
    )
    if r.status_code in (200, 204):
        print(f"  {PASS} Deleted orphan: {email} ({user_id})")
        return True
    print(f"  {FAIL} Could not delete {email} ({user_id}): {r.status_code} {r.text[:120]}")
    return False


def main():
    print("\n=================================================")
    print("  Holy Grills — Orphaned Auth User Cleanup")
    print("=================================================\n")

    print("Fetching auth users …")
    auth_users = get_all_auth_users()
    print(f"  Found {len(auth_users)} auth user(s)\n")

    print("Fetching profiles …")
    profile_ids = get_profile_ids()
    print(f"  Found {len(profile_ids)} profile(s)\n")

    orphans = [u for u in auth_users if u["id"] not in profile_ids]
    print(f"Orphaned auth users (no profile): {len(orphans)}")
    if not orphans:
        print("  Nothing to delete.")
    else:
        deleted = 0
        for u in orphans:
            if delete_auth_user(u["id"], u.get("email", "??")):
                deleted += 1
        print(f"\n  Deleted {deleted}/{len(orphans)} orphaned user(s).")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
