"""Tier service: per-tier perks, resource access checks, and monthly perk claims."""
import json
from datetime import datetime, timezone
from flask import current_app
from app.db import get_db, get_user_client


DEFAULT_TIER_PERKS = {
    "ember": {
        "earn_multiplier": 1.00,
        "monthly_free_delivery": False,
        "birthday_hp": 0,
        "free_side_credits_monthly": 0,
        "exclusive_spins_monthly": 0,
    },
    "flame": {
        "earn_multiplier": 1.08,
        "monthly_free_delivery": False,
        "birthday_hp": 0,
        "free_side_credits_monthly": 0,
        "exclusive_spins_monthly": 0,
    },
    "blaze": {
        "earn_multiplier": 1.15,
        "monthly_free_delivery": True,
        "birthday_hp": 0,
        "free_side_credits_monthly": 0,
        "exclusive_spins_monthly": 0,
    },
    "holy": {
        "earn_multiplier": 1.25,
        "monthly_free_delivery": True,
        "birthday_hp": 0,
        "free_side_credits_monthly": 0,
        "exclusive_spins_monthly": 0,
    },
}


def get_tier_perks(tier_slug: str) -> dict:
    slug = str(tier_slug).lower()
    config_perks = current_app.config.get("TIER_PERKS", {})
    if slug in config_perks:
        return config_perks[slug]
    return DEFAULT_TIER_PERKS.get(slug, {})


def can_access_tier_resource(user_id: str, min_tier_id: str) -> bool:
    if not min_tier_id:
        return True
    db = get_user_client()
    try:
        user_prof = db.table("profiles").select("current_tier_id").eq("id", user_id).single().execute()
        if not user_prof or not user_prof.get("current_tier_id"):
            return False
        user_tier_id = user_prof["current_tier_id"]
        tiers = db.table("hp_tiers").select("id,sort_order").in_("id", [user_tier_id, min_tier_id]).execute() or []
        tier_map = {t["id"]: t.get("sort_order", 0) for t in tiers}
        return tier_map.get(user_tier_id, 0) >= tier_map.get(min_tier_id, 0)
    except Exception:
        return False


def resolve_perk(user_id: str, perk_key: str):
    db = get_db()
    slug = "ember"
    try:
        prof = db.table("profiles").select("current_tier_id").eq("id", user_id).single().execute()
        if prof and prof.get("current_tier_id"):
            t_row = db.table("hp_tiers").select("slug").eq("id", prof["current_tier_id"]).single().execute()
            if t_row and t_row.get("slug"):
                slug = str(t_row["slug"]).lower()
    except Exception:
        pass

    sys_key = f"tier_perk_{slug}_{perk_key}"
    try:
        row = db.table("system_settings").select("value").eq("key", sys_key).is_("campus_id", "null").single().execute()
        if row and row.get("value") is not None:
            val = row["value"]
            if isinstance(val, str) and val.startswith('"') and val.endswith('"'):
                try:
                    val = json.loads(val)
                except Exception:
                    pass
            if str(val).lower() in ("true", "false"):
                return str(val).lower() == "true"
            try:
                return float(val) if "." in str(val) else int(val)
            except Exception:
                return val
    except Exception:
        pass

    default_perks = get_tier_perks(slug)
    return default_perks.get(perk_key, False if perk_key == "monthly_free_delivery" else 0)


def try_claim_monthly_free_delivery(user_id: str, order_id: str = None) -> bool:
    if not resolve_perk(user_id, "monthly_free_delivery"):
        return False
    db = get_db()
    curr_month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        res = db.rpc("hg_claim_tier_monthly_perk", {
            "p_user_id": user_id,
            "p_month": curr_month,
            "p_perk_key": "monthly_free_delivery",
            "p_order_id": order_id,
        }).execute()
        if isinstance(res, dict):
            return bool(res.get("claimed"))
        return False
    except Exception:
        return False
