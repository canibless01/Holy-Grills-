from app.db import get_db
from app.utils.logger import get_logger
from app.utils.settings import get_validated_setting

logger = get_logger(__name__)


def _get_econ_setting(db, key: str, default: float) -> float:
    """Read a GLOBAL (campus_id NULL) economics setting.

    These keys are is_public=false, so RLS hides them from campus admins' user client. Read with the service role
    (the `db` argument is kept only so existing callers do not change). Fall back to `default`, but log why.
    """
    try:
        row = get_db().table("system_settings").select("value").eq(
            "key", key).is_("campus_id", "null").single().execute()
        return float(row.get("value", default)) if row else default
    except Exception:
        logger.warning("economics setting %r unreadable or invalid - using default %s", key, default, exc_info=True)
        return default


def get_hp_value() -> float:
    """Naira value of ONE HP, read from system_settings.hp_liability_value (never a hard-coded number).

    Service role (the key is is_public=false). Raises SettingError (DatabaseUnavailableError / MalformedSettingError)
    if the setting is missing, unreadable or not a positive number, so a wrong price or cost is never produced silently.
    """
    return float(get_validated_setting(get_db(), "hp_liability_value", required=True, minimum=0.0001))


def log_redemption_cost(redemption_id: str, reward_id: str, hp_spent: int, campus_id: str = None, user_id: str = None) -> bool:
    """Write the ONE redemption_cost_log row for a fulfilled reward redemption.

    Service role (the table has no INSERT policy). Never raises - a logging failure must not block fulfilment.
    A second call for the same redemption is rejected by the unique index (Part A, A-01) and returns False.
    Cost = what the business gave up: food = food cost + packaging, merch = production cost + packaging,
    event = hp_spent x HP value (price_hp is discount_naira / HP value, so discount_naira ~= price_hp x HP value).
    """
    try:
        db = get_db()
        reward = db.table("rewards").select(
            "reward_type,food_cost,packaging_cost,production_cost,campus_id"
        ).eq("id", reward_id).single().execute()
        if not reward:
            logger.warning("log_redemption_cost: reward %s not found for redemption %s", reward_id, redemption_id)
            return False
        rtype = reward.get("reward_type")
        packaging = float(reward.get("packaging_cost") or 0)
        if rtype == "food":
            actual_cost = float(reward.get("food_cost") or 0) + packaging
        elif rtype == "merch":
            actual_cost = float(reward.get("production_cost") or 0) + packaging
        elif rtype == "event":
            actual_cost = float(hp_spent or 0) * get_hp_value()
        else:
            actual_cost = 0.0
        db.table("redemption_cost_log").insert({
            "redemption_id": redemption_id,
            "reward_id": reward_id,
            "reward_type": rtype,
            "hp_spent": int(hp_spent or 0),
            "actual_cost": round(actual_cost, 2),
            "campus_id": campus_id or reward.get("campus_id"),
            "user_id": user_id,
        })
        return True
    except Exception:
        logger.warning("log_redemption_cost failed for redemption %s", redemption_id, exc_info=True)
        return False


def log_event_ticket_cost(ticket_id: str, user_id: str, hp_spent: int, discount_naira: float, campus_id: str = None) -> bool:
    """Record what an event ticket bought with HP cost the business: discount_naira = face value - cash price.

    One row per ticket (unique index on event_ticket_id, Part A A-05). Service role. Never raises.
    """
    try:
        if float(discount_naira) <= 0:
            logger.warning("log_event_ticket_cost: ticket %s was paid with HP but has no discount configured "
                           "(price_naira_full - price_naira <= 0)", ticket_id)
            return False
        get_db().table("redemption_cost_log").insert({
            "event_ticket_id": ticket_id,
            "user_id": user_id,
            "reward_type": "event",
            "hp_spent": int(hp_spent or 0),
            "actual_cost": round(float(discount_naira), 2),
            "campus_id": campus_id,
        })
        return True
    except Exception:
        logger.warning("log_event_ticket_cost failed for ticket %s", ticket_id, exc_info=True)
        return False


def calculate_food_reward_value(db, food_cost: float, packaging_cost: float, menu_price: float, margin_share_pct: float = None) -> float:
    margin = margin_share_pct if margin_share_pct is not None else _get_econ_setting(db, "reward_margin_share_food", 0.40)
    return (food_cost + packaging_cost) + margin * (menu_price - food_cost - packaging_cost)


def calculate_merch_reward_value(db, production_cost: float, packaging_cost: float, perceived_value: float, margin_share_pct: float = None) -> float:
    margin = margin_share_pct if margin_share_pct is not None else _get_econ_setting(db, "reward_margin_share_merch", 0.50)
    return (production_cost + packaging_cost) + margin * (perceived_value - production_cost - packaging_cost)


def calculate_hp_price(db, reward_value: float) -> int:
    hp_value = get_hp_value()
    rounding = _get_econ_setting(db, "hp_rounding", 50)
    raw = reward_value / hp_value
    return int(round(raw / rounding) * rounding)


def calculate_hp_liability(db, hp_price: int) -> float:
    hp_value = get_hp_value()
    return round(hp_price * hp_value, 2)


def validate_event_margin(available_margin: float, ticket_face_value: float, max_discount_pct: float = None) -> bool:
    pct = max_discount_pct if max_discount_pct is not None else 0.25
    max_discount = pct * ticket_face_value
    return available_margin >= max_discount











