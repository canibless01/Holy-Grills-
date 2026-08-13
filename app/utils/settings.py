"""
Settings validation utility — retrieves and validates system settings atomically
without silently masking DB failures.
"""

import json
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SettingError(Exception):
    """Base exception for system settings failures."""
    pass


class DatabaseUnavailableError(SettingError):
    """Database query failed (e.g. timeout, DNS issue)."""
    pass


class MalformedSettingError(SettingError):
    """Setting is present but cannot be parsed or validated within bounds."""
    pass


def get_validated_setting(db, key: str, default=None, minimum=None, maximum=None, required=False):
    """
    Retrieves and validates a setting from the system_settings table.

    - If database query fails, raises DatabaseUnavailableError (fails safely, doesn't silently use default).
    - If setting is missing:
        - If required is True, raises MalformedSettingError.
        - Else, returns default.
    - If setting exists but is malformed (e.g. not numeric when bounds are specified), raises MalformedSettingError.
    - If numeric bounds are supplied, enforces them strictly.
    """
    try:
        # Note: single().execute() might raise Exception on database issues
        res = db.table("system_settings").select("value").eq("key", key).single().execute()
    except Exception as e:
        logger.error("Database query failed while retrieving system setting '%s'", key, exc_info=True)
        raise DatabaseUnavailableError(f"Database unavailable while querying setting: {key}") from e

    if not res:
        if required:
            raise MalformedSettingError(f"Required setting '{key}' is missing from system_settings")
        return default

    raw_val = res.get("value")
    if raw_val is None:
        if required:
            raise MalformedSettingError(f"Required setting '{key}' contains a NULL/None value")
        return default

    # Handle TEXT vs JSONB wrapping
    parsed_val = raw_val
    if isinstance(raw_val, str):
        # Clean potential quotes if stored as a JSON string in a TEXT column
        clean_str = raw_val.strip()
        if (clean_str.startswith('"') and clean_str.endswith('"')) or (clean_str.startswith('{') or clean_str.startswith('[')):
            try:
                parsed_val = json.loads(clean_str)
            except (ValueError, TypeError):
                # Fall back to raw string if it is not valid JSON
                parsed_val = raw_val
        else:
            # Check if it represents a numeric value
            try:
                if "." in clean_str:
                    parsed_val = float(clean_str)
                else:
                    parsed_val = int(clean_str)
            except ValueError:
                parsed_val = raw_val

    # Unpack dictionary structure if any (e.g. {"value": ...})
    if isinstance(parsed_val, dict):
        if "value" in parsed_val:
            parsed_val = parsed_val["value"]
        elif "val" in parsed_val:
            parsed_val = parsed_val["val"]

    # Perform numeric range validations if bounds are provided
    if minimum is not None or maximum is not None:
        try:
            num_val = float(parsed_val)
        except (ValueError, TypeError) as e:
            raise MalformedSettingError(f"Setting '{key}' value '{parsed_val}' is not a valid number") from e

        if minimum is not None and num_val < minimum:
            raise MalformedSettingError(f"Setting '{key}' value {num_val} is less than minimum limit {minimum}")
        if maximum is not None and num_val > maximum:
            raise MalformedSettingError(f"Setting '{key}' value {num_val} is greater than maximum limit {maximum}")

        # Return int if default or bounds are integers
        if isinstance(default, int) or (minimum is not None and isinstance(minimum, int)):
            return int(num_val)
        return num_val

    return parsed_val
