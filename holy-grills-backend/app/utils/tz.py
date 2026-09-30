"""
Single source of truth for 'what calendar day is it' in this app's business
timezone. WAT (Africa/Lagos) is UTC+1 with no DST, so a fixed 1-hour offset
is exact — matches the one place in this codebase that already did this
correctly ad-hoc (the operating-hours check in create_order).

Use this only for day/week/month-boundary business logic: streaks, caps,
period keys, order-lock dates, launch windows, "today" in admin reports.
Do NOT use this for created_at/updated_at/last_updated timestamps — those
stay real UTC, unchanged everywhere in this fix.
"""
from datetime import datetime, timezone, timedelta, date

WAT_OFFSET = timedelta(hours=1)


def today_wat() -> date:
    return (datetime.now(timezone.utc) + WAT_OFFSET).date()


from datetime import time as _dt_time


def is_within_availability_window(opens_at, closes_at) -> bool:
    if not opens_at or not closes_at:
        return True
    def _hm(s):
        parts = str(s).split(":")
        return _dt_time(int(parts[0]), int(parts[1]))
    now_wat = (datetime.now(timezone.utc) + WAT_OFFSET).time()
    open_t, close_t = _hm(opens_at), _hm(closes_at)
    if open_t <= close_t:
        return open_t <= now_wat <= close_t
    return now_wat >= open_t or now_wat <= close_t  # window crosses midnight


def wat_day_bounds_utc(day: date) -> tuple:
    """(start, end) of a WAT calendar day as UTC ISO strings. `end` is exclusive (start of the next WAT day)."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - WAT_OFFSET
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def wat_iso(day: str, clock: str) -> str:
    """('2026-09-21', '18:00:00') -> '2026-09-21T18:00:00+01:00': a WAT wall-clock time as an absolute instant."""
    clock = (clock or "18:00")[:8]
    if len(clock) == 5:
        clock += ":00"
    return f"{day}T{clock}+01:00"


def wat_month_start_utc(now=None) -> str:
    """Start of the current WAT calendar month, as a UTC ISO string."""
    wall = (now or datetime.now(timezone.utc)) + WAT_OFFSET
    return (datetime(wall.year, wall.month, 1) - WAT_OFFSET).replace(tzinfo=timezone.utc).isoformat()
