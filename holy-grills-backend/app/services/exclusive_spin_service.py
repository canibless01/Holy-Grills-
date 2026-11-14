"""Typed spin-prize configuration; labels never determine an award's effect."""
import math
from app.messages import MSG


def validate_spin_prize(data, *, partial=False):
    if not isinstance(data, dict):
        raise ValueError(MSG.JSON_OBJECT_REQUIRED)
    safe = {}
    if 'name' in data or not partial:
        name = data.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError(MSG.SPIN_POOL_NAME_INVALID)
        safe['name'] = name.strip()
    if 'weight' in data or not partial:
        weight = data.get('weight', 1)
        if type(weight) is not int or not 1 <= weight <= 100000:
            raise ValueError(MSG.SPIN_POOL_WEIGHT_INVALID)
        safe['weight'] = weight
    if 'is_active' in data:
        if not isinstance(data['is_active'], bool):
            raise ValueError(MSG.SPIN_POOL_ACTIVE_INVALID)
        safe['is_active'] = data['is_active']
    if 'reward_config' in data or not partial:
        config = data.get('reward_config')
        if not isinstance(config, dict):
            raise ValueError(MSG.SPIN_POOL_CONFIG_INVALID)
        kind = config.get('kind')
        fields = {'physical': None, 'hp': 'amount', 'free_delivery': 'cap', 'hp_multiplier': 'multiplier'}
        if not isinstance(kind, str) or kind not in fields:
            raise ValueError(MSG.SPIN_POOL_CONFIG_INVALID)
        field = fields[kind]
        if set(config) != ({'kind', field} if field else {'kind'}):
            raise ValueError(MSG.SPIN_POOL_CONFIG_INVALID)
        normalized = {'kind': kind}
        if field:
            value = config.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(MSG.SPIN_POOL_CONFIG_INVALID)
            if kind == 'hp':
                valid = type(value) is int and 1 <= value <= 100000
            elif kind == 'free_delivery':
                valid = 1 <= value <= 100000
            else:
                valid = 1.01 <= value <= 10
            if not valid:
                raise ValueError(MSG.SPIN_POOL_CONFIG_INVALID)
            normalized[field] = value
        safe['reward_config'] = normalized
    if not safe:
        raise ValueError(MSG.SPIN_POOL_NO_VALID_FIELDS)
    return safe
