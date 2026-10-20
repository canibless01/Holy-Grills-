"""Allocate actual food spend across paid food and add-ons, excluding delivery."""
from decimal import Decimal, ROUND_DOWN


def food_hp_lines(items, rate, *, include_addons=False, net_food_spend=None):
    paid = [item for item in items if (include_addons or not item.get('is_addon'))
            and Decimal(str(item.get('price_snapshot') or 0)) > 0]
    gross = sum((Decimal(str(i['price_snapshot'])) * int(i.get('quantity') or 1) for i in paid), Decimal(0))
    net = gross if net_food_spend is None else min(gross, max(Decimal(0), Decimal(str(net_food_spend))))
    result = []
    for item in paid:
        value = Decimal(str(item['price_snapshot'])) * int(item.get('quantity') or 1)
        spend = value * net / gross if gross else Decimal(0)
        multiplier = 1.0 if item.get('is_addon') else float(item.get('hp_multiplier_snapshot') or 1)
        if multiplier not in (0.5, 1, 2):
            multiplier = 1.0
        base = int((spend * Decimal(str(rate))).to_integral_value(rounding=ROUND_DOWN))
        result.append({'menu_item_id': item.get('menu_item_id'), 'addon_id': item.get('addon_id'),
                       'quantity': int(item.get('quantity') or 1), 'hp_multiplier': multiplier,
                       'eligible_spend': float(spend), 'base_hp': base, 'hp': round(base * multiplier)})
    return result
