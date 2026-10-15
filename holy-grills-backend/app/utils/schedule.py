"""Per-date overrides of the recurring hours — one implementation, two readers.

An `operating_hour_overrides` row applies to ONE date, either for one campus or
globally (`campus_id` NULL); the campus-specific row wins over the global one.
After that date the recurring schedule applies again automatically — an override
is a dated exception, not a mode, so there is nothing to clean up or switch off.

Both readers go through this module, so a closed day means the same thing
everywhere:

  * the ordering gate — `app/services/order_service.py` (`resolve_ordering_window`,
    `get_ordering_window_status`, and through the latter,
    `find_next_available_ordering_slot` and the 7-day calendar);
  * the storefront — `app/routes/storefront.py` (`GET /api/storefront/operating-hours`).

Precedence for campus C on date D (WAT, UTC+1), highest first:

  1. an `ordering_windows` row for (D, C)              — unchanged behaviour
  2. an `operating_hour_overrides` row for (D, C), else (D, global):
       is_closed = true   -> closed all day, even if weekday windows exist
       is_closed = false  -> one effective window at the override's times;
                             NULL times mean 00:00-23:59
  3. the recurring `ordering_windows` rows for D's weekday
  4. the `ORDERING_WINDOW_OPEN_TIME`/`CLOSE_TIME` config fallback

Note the asymmetry in (2): a closed override beats the weekday rows entirely,
while an open override *replaces* them for that day and inherits nothing but the
identity of the day's window (see `effective_ordering_windows`).
"""
from app.utils.logger import get_logger

logger = get_logger(__name__)

ORDERING_WINDOW_FIELDS = "id,opens_at,closes_at,is_closed,capacity,linked_delivery_window_id"

# What NULL times mean on an open override: the whole day, not "closed" and not
# "fall back to the weekly schedule".
FULL_DAY_OPEN, FULL_DAY_CLOSE = "00:00", "23:59"


def resolve_date_override(db, campus_id, date_iso):
    """The date's override row for this campus, or None. Campus row beats global.

    Returns None when no override applies — including when the table cannot be
    read at all, so an un-migrated database keeps its current behaviour rather
    than failing every ordering request.
    """
    try:
        rows = (
            db.table("operating_hour_overrides").select("*")
            .eq("date", date_iso).execute()
        ) or []
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("schedule: operating_hour_overrides unreadable for %s: %s", date_iso, exc)
        return None

    if campus_id:
        for row in rows:
            if row.get("campus_id") and str(row["campus_id"]) == str(campus_id):
                return row
    for row in rows:
        if not row.get("campus_id"):
            return row
    return None


def override_window(override):
    """(opens_at, closes_at) for an open override. NULL times mean all day."""
    if not override:
        return None
    return (override.get("opens_at") or FULL_DAY_OPEN,
            override.get("closes_at") or FULL_DAY_CLOSE)


def effective_ordering_windows(db, campus_id, date_iso, weekday):
    """The ordering windows in force for one campus on one date (WAT).

    Returns `(rows, source)`:

      rows   — `ordering_windows`-shaped dicts. An override contributes exactly
               one row; a closed override contributes one closed row, which is
               what makes the day read as closed rather than as "no windows, try
               the next rule".
      source — 'date' | 'override' | 'override_closed' | 'weekly' | 'config'.

    `[] with 'config'` is the only case where the caller falls back to the
    configured open/close times; an empty list never means "closed" on its own.
    """
    rows = (
        db.table("ordering_windows").select(ORDERING_WINDOW_FIELDS)
        .eq("date", date_iso).eq("campus_id", campus_id).execute()
    ) or []
    if rows:
        return rows, "date"

    weekly = (
        db.table("ordering_windows").select(ORDERING_WINDOW_FIELDS)
        .eq("weekday", weekday).eq("campus_id", campus_id).execute()
    ) or []

    override = resolve_date_override(db, campus_id, date_iso)
    if override is not None:
        if override.get("is_closed"):
            # Closed all day: the weekday rows must not open it.
            return [{
                "id": None, "opens_at": None, "closes_at": None,
                "is_closed": True, "capacity": None, "linked_delivery_window_id": None,
            }], "override_closed"

        opens, closes = override_window(override)
        # Inherit the recurring window's identity and capacity only when the day
        # has exactly one recurring row. With several, there is no single window
        # for the capacity counter (and the delivery link) to belong to, so the
        # override's own times stand alone with no capacity cap.
        inherit = weekly[0] if len(weekly) == 1 else {}
        return [{
            "id": inherit.get("id"),
            "opens_at": opens,
            "closes_at": closes,
            "is_closed": False,
            "capacity": inherit.get("capacity"),
            "linked_delivery_window_id": inherit.get("linked_delivery_window_id"),
        }], "override"

    if weekly:
        return weekly, "weekly"
    return [], "config"


def config_default_window() -> tuple:
    """(opens_at, closes_at) from config — the step-4 fallback.

    A campus with no `ordering_windows` rows at all still has ordering hours:
    `ORDERING_WINDOW_OPEN_TIME`/`ORDERING_WINDOW_CLOSE_TIME`. Reading them here
    (rather than inline in each caller) is what keeps the ordering gate
    (`resolve_ordering_window`) and the status endpoint
    (`get_ordering_window_status`) agreeing about the same campus.
    """
    from flask import current_app
    return (
        current_app.config.get("ORDERING_WINDOW_OPEN_TIME", "08:00"),
        current_app.config.get("ORDERING_WINDOW_CLOSE_TIME", "16:00"),
    )


def effective_windows_with_config(db, campus_id, date_iso, weekday):
    """`effective_ordering_windows`, with the config fallback materialised.

    Identical precedence, except that step 4 — "no rows at all" — now returns
    ONE synthetic open window at the configured times instead of an empty list.
    `resolve_ordering_window` and `get_ordering_window_status` must see the same
    thing: without this, a config-only campus is reported as permanently closed
    by the status endpoint while checkout happily accepts orders inside the
    configured hours.
    """
    rows, source = effective_ordering_windows(db, campus_id, date_iso, weekday)
    if rows or source != "config":
        return rows, source
    opens, closes = config_default_window()
    return [{
        "id": None,
        "opens_at": opens,
        "closes_at": closes,
        "is_closed": False,
        "capacity": None,
        "linked_delivery_window_id": None,
    }], "config"
