"""
Tier service: per-tier perks, resource access checks, and monthly perk claims."""
import json
from datetime import datetime, timezone
from flask import current_app
from app.db import get_db, get_user_client

from app.utils.logger import get_logger

logger = get_logger(__name__)


# Finalized Holy Grills Loyalty & Rewards System spec (scope item 6c), values taken as-is from the
# scope map's own spec table. Multipliers were already correct; birthday_hp was 0 for every tier, so
# the birthday job fell back to the flat 150 default for everyone. Monthly perks are restructured per
# the spec: Flame gains a flat monthly HP bonus (new perk key, no prior grant path existed for it —
# see coupled-changes doc for the tasks/scheduled.py side needed to actually pay it out), Blaze drops
# free delivery in favor of 1 free side, Holy keeps free delivery and gains 1 free side.
DEFAULT_TIER_PERKS = {
    "ember": {
        "earn_multiplier": 1.00,
        "monthly_free_delivery": False,
        "birthday_hp": 100,
        "free_side_credits_monthly": 0,
        "exclusive_spins_monthly": 0,
        "monthly_bonus_hp": 0,
    },
    "flame": {
        "earn_multiplier": 1.08,
        "monthly_free_delivery": False,
        "birthday_hp": 150,
        "free_side_credits_monthly": 0,
        "exclusive_spins_monthly": 0,
        "monthly_bonus_hp": 50,
    },
    "blaze": {
        "earn_multiplier": 1.15,
        "monthly_free_delivery": False,
        "birthday_hp": 200,
        "free_side_credits_monthly": 1,
        "exclusive_spins_monthly": 0,
        "monthly_bonus_hp": 0,
    },
    "holy": {
        "earn_multiplier": 1.25,
        "monthly_free_delivery": True,
        "birthday_hp": 250,
        "free_side_credits_monthly": 1,
        "exclusive_spins_monthly": 0,
        "monthly_bonus_hp": 0,
    },
}


def get_tier_perks(tier_slug: str) -> dict:
    """
    hp_service.calculate_delivery_hp (order_service's no-user-id path) reads
    get_tier_perks(slug)["earn_multiplier"] directly, with no .get()/try-except of its own on this call.
    A wholesale config_perks[slug] replacement meant a TIER_PERKS env override for one tier that didn't
    happen to repeat every key (e.g. only overriding monthly_free_delivery) would silently drop
    earn_multiplier and every other key for that tier -> KeyError there. Merge onto the defaults instead,
    so any known slug always carries every key regardless of how partial an override is.
    An unknown slug still correctly returns {} -- there is no default to merge onto.
    """
    slug = str(tier_slug).lower()
    defaults = DEFAULT_TIER_PERKS.get(slug, {})
    config_perks = current_app.config.get("TIER_PERKS", {})
    if slug in config_perks:
        merged = dict(defaults)
        merged.update(config_perks[slug])
        return merged
    return defaults


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
    except Exception as exc:
        logger.warning("resolve_perk: could not resolve the tier for %s — falling back to the default perk: %s",
                        user_id, exc)

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
    """
    hg_claim_tier_monthly_perk is service_role-only (no EXECUTE grant for authenticated/anon -- confirmed
    live) and carries no per-caller ownership check, matching every other atomic RPC in this schema
    (credit_wallet_atomic, debit_wallet_atomic, hg_adjust_stock_balance): the trust boundary is the GRANT
    plus this function's own resolve_perk() eligibility check, not a client-supplied user id. Call it via
    get_db() -- get_user_client() would carry no EXECUTE privilege at all and every claim would fail with
    "permission denied for function" (confirmed live).
    """
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
