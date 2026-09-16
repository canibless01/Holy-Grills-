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
