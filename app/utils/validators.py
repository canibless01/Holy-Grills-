"""Input validation helpers shared across routes."""

import re
from datetime import datetime


def validate_email(email: str) -> bool:
    return bool(re.match(r'^[\w.+\-]+@[\w.-]+\.[a-zA-Z]{2,}$', email))


def validate_phone(phone: str) -> bool:
    cleaned = re.sub(r'[\s\-\(\)+]', '', phone)
    return bool(re.match(r'^(\+?234|0)[789]\d{9}$', cleaned))


def validate_uuid(value: str) -> bool:
    return bool(re.match(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        str(value).lower()
    ))


def validate_date(value: str) -> bool:
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False


def validate_password(pw: str) -> tuple[bool, str]:
    if len(pw) < 8:
        return False, 'Password must be at least 8 characters'
    if not re.search(r'[A-Za-z]', pw):
        return False, 'Password must contain at least one letter'
    if not re.search(r'\d', pw):
        return False, 'Password must contain at least one number'
    return True, ''


def sanitize_string(value: str, max_len: int = 500) -> str:
    if not isinstance(value, str):
        return ''
    return value.strip()[:max_len]


def validate_positive_number(value, field_name: str = 'value') -> tuple[bool, str]:
    try:
        n = float(value)
        if n <= 0:
            return False, f'{field_name} must be greater than 0'
        return True, ''
    except (TypeError, ValueError):
        return False, f'{field_name} must be a number'


def validate_hp_amount(amount) -> tuple[bool, str]:
    try:
        n = int(amount)
        if n <= 0:
            return False, 'HP amount must be a positive integer'
        if n > 100_000:
            return False, 'HP amount exceeds maximum single transaction limit'
        return True, ''
    except (TypeError, ValueError):
        return False, 'HP amount must be an integer'


def validate_order_items(items: list) -> tuple[bool, str]:
    if not items or not isinstance(items, list):
        return False, 'items must be a non-empty list'
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            return False, f'items[{i}] must be an object'
        if not item.get('menu_item_id'):
            return False, f'items[{i}].menu_item_id is required'
        if not validate_uuid(item['menu_item_id']):
            return False, f'items[{i}].menu_item_id is not a valid UUID'
        qty = item.get('quantity', 1)
        try:
            if int(qty) < 1 or int(qty) > 50:
                return False, f'items[{i}].quantity must be between 1 and 50'
        except (TypeError, ValueError):
            return False, f'items[{i}].quantity must be an integer'
    return True, ''
