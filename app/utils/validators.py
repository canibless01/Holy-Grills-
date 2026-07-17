"""Input validation helpers shared across routes."""

import re
from datetime import datetime

_FALLBACK_PHONE_PATTERN = r'^(\+?234|0)[789]\d{9}$'


def validate_email(email: str) -> bool:
    return bool(re.match(r'^[\w.+\-]+@[\w.-]+\.[a-zA-Z]{2,}$', email))


def validate_phone(phone: str, pattern: str = None) -> bool:
    """
    Validate a Nigerian phone number.

    If *pattern* is provided it is used directly.  Otherwise the function
    tries to read PHONE_REGEX_PATTERN from the current Flask app config.
    Falls back to the built-in default only when running outside an
    application context (tests, CLI).
    """
    cleaned = re.sub(r'[\s\-\(\)+]', '', phone)
    if pattern is None:
        try:
            from flask import current_app
            pattern = current_app.config["PHONE_REGEX_PATTERN"]
        except RuntimeError:
            # Outside application context — use built-in default
            pattern = _FALLBACK_PHONE_PATTERN
    return bool(re.match(pattern, cleaned))


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


def validate_password(pw: str) -> tuple:
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


def validate_positive_number(value, field_name: str = 'value') -> tuple:
    try:
        n = float(value)
        if n <= 0:
            return False, f'{field_name} must be greater than 0'
        return True, ''
    except (TypeError, ValueError):
        return False, f'{field_name} must be a number'


def validate_hp_amount(amount) -> tuple:
    try:
        n = int(amount)
        if n <= 0:
            return False, 'HP amount must be a positive integer'
        if n > 100_000:
            return False, 'HP amount exceeds maximum single transaction limit'
        return True, ''
    except (TypeError, ValueError):
        return False, 'HP amount must be an integer'


def validate_choice(value, choices, field_name: str = 'value') -> tuple:
    """Validate that value is one of an explicit set of allowed choices
    (e.g. an enum-like status column). Used by admin update endpoints to
    reject arbitrary status/type strings before they hit the database."""
    if value not in choices:
        allowed = ', '.join(str(c) for c in choices)
        return False, f"{field_name} must be one of: {allowed}"
    return True, ''


def validate_non_negative_number(value, field_name: str = 'value') -> tuple:
    try:
        n = float(value)
        if n < 0:
            return False, f'{field_name} must not be negative'
        return True, ''
    except (TypeError, ValueError):
        return False, f'{field_name} must be a number'


def validate_datetime_order(starts_at: str, ends_at: str) -> tuple:
    """Validate ISO-8601 datetime strings and that starts_at < ends_at."""
    try:
        start = datetime.fromisoformat(str(starts_at).replace('Z', '+00:00'))
        end = datetime.fromisoformat(str(ends_at).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return False, 'starts_at/ends_at must be valid ISO-8601 datetimes'
    if start >= end:
        return False, 'starts_at must be before ends_at'
    return True, ''


def validate_order_items(items: list) -> tuple:
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
