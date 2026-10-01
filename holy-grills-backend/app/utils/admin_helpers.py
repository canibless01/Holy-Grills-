"""Strict input parsing and clean DB-error mapping for admin JSON endpoints."""
from datetime import datetime, timezone

from flask import request, jsonify

from app.db import SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger
from app.utils.tz import WAT_OFFSET

logger = get_logger(__name__)


def get_json_object():
    """Return the JSON body if it is an object, otherwise None."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def as_bool(value):
    """Real booleans and the strings 'true'/'false' only (bool('false') is True in Python)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ValueError("must be a boolean")


def as_int(value, minimum=None, maximum=None):
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise ValueError("must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("must be an integer")
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise ValueError("out of range")
    return number


def as_text(value, max_len=255):
    if not isinstance(value, str):
        raise ValueError("must be text")
    text = value.strip()
    if not text or len(text) > max_len:
        raise ValueError("must be 1-%d characters" % max_len)
    return text


def as_date(value):
    """'YYYY-MM-DD' -> date. Raises ValueError otherwise."""
    if not isinstance(value, str):
        raise ValueError("must be a date")
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("must be a date")


def as_time(value):
    """'HH:MM' or 'HH:MM:SS' -> time. Raises ValueError otherwise."""
    if not isinstance(value, str):
        raise ValueError("must be a time")
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).time()
        except ValueError:
            pass
    raise ValueError("must be a time")


def as_uuid(value):
    """None or '' -> None. A valid UUID string -> lowercase. Anything else raises ValueError."""
    if value is None or value == "":
        return None
    from app.utils.validators import validate_uuid
    if not isinstance(value, str) or not validate_uuid(value):
        raise ValueError("must be a UUID")
    return value.lower()


def as_instant(value):
    """ISO-8601 datetime -> timezone-aware ISO string. A value with no offset is read as WAT (UTC+1)."""
    if not isinstance(value, str):
        raise ValueError("must be a datetime")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("must be a datetime")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(WAT_OFFSET))
    return parsed.isoformat()


def as_number(value, minimum=None, maximum=None):
    """A finite number (numeric strings accepted), rounded to 2 decimals. Raises ValueError otherwise."""
    if isinstance(value, bool):
        raise ValueError("must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("must be a number")
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("must be a number")
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise ValueError("out of range")
    return round(number, 2)


def page_args(default_limit=50, max_limit=200):
    """(limit, offset) from the query string. limit is clamped to max_limit; non-integers or negatives raise ValueError."""
    limit = min(as_int(request.args.get("limit", default_limit), 1), max_limit)
    offset = as_int(request.args.get("offset", 0), 0)
    return limit, offset


def db_error_response(exc, action, conflict_message=None):
    """Map a Supabase/network failure to a clean JSON response. Never returns a fake success."""
    if isinstance(exc, SupabaseError):
        details = exc.details if isinstance(exc.details, dict) else {}
        code = str(details.get("code") or "")
        if code == "23505" and conflict_message:
            return jsonify({"error": conflict_message}), 409
        if exc.status_code == 401:
            return jsonify({"error": MSG.SESSION_INVALID}), 401
        if code == "42501" or exc.status_code == 403:
            return jsonify({"error": MSG.RESOURCE_ACCESS_DENIED}), 403
        if code[:2] in ("22", "23"):
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        logger.error("%s failed: %s", action, exc)
        if exc.status_code in (502, 503, 504):
            return jsonify({"error": MSG.SERVICE_UNAVAILABLE}), 503
        return jsonify({"error": MSG.REQUEST_FAILED_RETRY}), 500
    logger.error("%s unreachable: %s", action, exc)
    return jsonify({"error": MSG.SERVICE_UNAVAILABLE}), 503
