"""
Seed / upsert system_settings — standalone, retry-safe.
Run: python scripts/seed_settings.py
"""
import os, requests, time, sys

SB = os.environ["SUPABASE_URL"].rstrip("/")
SRK = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
H = {
    "apikey": SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}

SETTINGS = [
    ("platform_name",            "Holy Grills FUTA"),
    ("currency_code",            "NGN"),
    ("currency_symbol",          "₦"),
    ("hp_redeem_rate",           "100"),
    ("min_hp_redeem",            "100"),
    ("welcome_bonus_hp",         "50"),
    ("referral_hp_reward",       "75"),
    ("free_delivery_threshold",  "3000"),
    ("first_order_gift_enabled", "true"),
    ("launch_window_end_date",   "2026-12-31"),
    ("monthly_hp_cap",           "800"),
    ("decay_onset_days",         "120"),
    ("decay_rate_monthly",       "0.10"),
    ("login_streak_hp",          "2"),
    ("share_prompt_hp",          "25"),
    ("order_lock_max_discount",  "50"),
]

ok = err = 0
for key, val in SETTINGS:
    for attempt in range(3):
        try:
            r = requests.post(
                f"{SB}/rest/v1/system_settings",
                headers=H,
                json={"key": key, "value": val},
                timeout=20,
            )
            if r.status_code in (200, 201, 204):
                print(f"  ✓ {key}")
                ok += 1
                break
            else:
                print(f"  ✗ {key}: HTTP {r.status_code} — {r.text[:120]}")
                err += 1
                break
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  ✗ {key}: {e}")
                err += 1

print(f"\nDone: {ok} ok, {err} errors")
