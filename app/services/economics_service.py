"""
HP Economics Service — valuation, liability calculation, and margin checks.
"""
from app.db import get_db


def _get_econ_setting(db, key: str, default: float) -> float:
    try:
        row = db.table("system_settings").select("value").eq(
            "key", key).is_("campus_id", "null").single().execute()
        return float(row.get("value", default)) if row else default
    except Exception:
        return default


def calculate_food_reward_value(db, food_cost: float, packaging_cost: float, menu_price: float, margin_share_pct: float = None) -> float:
    margin = margin_share_pct if margin_share_pct is not None else _get_econ_setting(db, "reward_margin_share_food", 0.40)
    return (food_cost + packaging_cost) + margin * (menu_price - food_cost - packaging_cost)


def calculate_merch_reward_value(db, production_cost: float, packaging_cost: float, perceived_value: float, margin_share_pct: float = None) -> float:
    margin = margin_share_pct if margin_share_pct is not None else _get_econ_setting(db, "reward_margin_share_merch", 0.50)
    return (production_cost + packaging_cost) + margin * (perceived_value - production_cost - packaging_cost)


def calculate_hp_price(db, reward_value: float) -> int:
    hp_value = _get_econ_setting(db, "hp_liability_value", 0.185)
    rounding = _get_econ_setting(db, "hp_rounding", 50)
    raw = reward_value / hp_value
    return int(round(raw / rounding) * rounding)


def calculate_hp_liability(db, hp_price: int) -> float:
    hp_value = _get_econ_setting(db, "hp_liability_value", 0.185)
    return round(hp_price * hp_value, 2)


def validate_event_margin(available_margin: float, ticket_face_value: float, max_discount_pct: float = None) -> bool:
    pct = max_discount_pct if max_discount_pct is not None else 0.25
    max_discount = pct * ticket_face_value
    return available_margin >= max_discount
