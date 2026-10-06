"""Ordering-window status, the next bookable slot, and the badge split.

These three were reported as live bugs:

  1. `GET /orders/delivery-windows/status` decided `is_open` from the schedule
     alone, so a kitchen that opens at 08:00 read as "open" at 01:00 — the
     closed popup never appeared and Place Order was refused instead.
  2. Scheduling always searched from TOMORROW, so a kitchen that had not opened
     yet today could never offer today's slot.
  3. `GET /challenges/my` returned every badge definition in one list, which the
     UI rendered under "Badges Earned".

The clock is frozen per test (WAT = UTC+1) and the database is a fake, so the
tests pin the rules without needing a live Supabase project.
"""

import os

for _k, _v in (
    ("SUPABASE_URL", "https://example.supabase.co"),
    ("SUPABASE_ANON_KEY", "test-anon"),
    ("SUPABASE_SERVICE_ROLE_KEY", "test-service"),
    ("SUPABASE_JWT_SECRET", "test-jwt"),
    ("SESSION_SECRET", "test-session"),
    ("JWT_SECRET", "test-jwt-secret"),
):
    os.environ.setdefault(_k, _v)

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from app.config import config_map
from app.services import order_service
from app.services.order_service import (
    OrderingWindowUnavailable,
    ORDERING_WINDOW_CLOSED,
    ORDERING_WINDOW_AT_CAPACITY,
)

WAT = timezone(timedelta(hours=1))
CAMPUS = "11111111-1111-1111-1111-111111111111"


# ── fake PostgREST ────────────────────────────────────────────────────────────
class _Chain:
    """One `.table(...)` chain: records the filters, answers with canned rows."""

    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = {}
        self._single = False

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def gte(self, key, value):
        self.filters[key] = value
        return self

    @property
    def not_(self):  # noqa: N802 — mirrors the supabase-py builder name
        return self

    def in_(self, _key, _values):
        return self

    def limit(self, _n):
        return self

    def order(self, *_a, **_k):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = self.db.rows_for(self.table, self.filters)
        if self._single:
            return rows[0] if rows else None
        return rows


class FakeDb:
    """Rows keyed by table name; `ordering_windows` and overrides are settable."""

    def __init__(self, ordering_windows=(), overrides=(), orders=()):
        self.ordering_windows = list(ordering_windows)
        self.overrides = list(overrides)
        self.orders = list(orders)

    def table(self, name):
        return _Chain(self, name)

    def rows_for(self, table, filters):
        if table == "ordering_windows":
            out = []
            for row in self.ordering_windows:
                if "date" in filters and row.get("date") != filters["date"]:
                    continue
                if "weekday" in filters and row.get("weekday") != filters["weekday"]:
                    continue
                if "campus_id" in filters and row.get("campus_id") != filters["campus_id"]:
                    continue
                out.append(dict(row))
            return out
        if table == "operating_hour_overrides":
            return [dict(r) for r in self.overrides if r.get("date") == filters.get("date")]
        if table == "delivery_windows":
            return [dict(r) for r in () ]  # no linked windows in these tests
        if table == "orders":
            # capacity counter: everything the fake holds counts against capacity
            return [dict(o) for o in self.orders]
        return []


def _window(wid, opens, closes, weekday=None, capacity=None, is_closed=False, date=None):
    return {
        "id": wid,
        "opens_at": opens,
        "closes_at": closes,
        "is_closed": is_closed,
        "capacity": capacity,
        "linked_delivery_window_id": None,
        "weekday": weekday,
        "date": date,
        "campus_id": CAMPUS,
    }


class _FrozenClock(datetime):
    """`datetime` stand-in whose `now()` is whatever the test pins."""

    fixed = None

    @classmethod
    def now(cls, tz=None):
        value = cls.fixed
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def _at(hour, minute=0):
    """A frozen UTC instant that reads as `hour:minute` on the WAT wall clock."""
    return datetime(2026, 10, 6, hour, minute, tzinfo=WAT).astimezone(timezone.utc)


class OrderingWindowStatusTest(unittest.TestCase):
    """Tuesday 2026-10-06, kitchen 08:00-21:00."""

    def setUp(self):
        self.app = create_app(config_map["production"])
        self.ctx = self.app.test_request_context()
        self.ctx.push()
        self.addCleanup(self.ctx.pop)
        self.db = FakeDb(ordering_windows=[_window("w1", "08:00", "21:00", weekday=1)])
        self._patch_clock(_at(1, 0))          # 01:00 WAT — the reported moment

    def _patch_clock(self, utc_dt):
        _FrozenClock.fixed = utc_dt
        patcher = unittest.mock.patch.object(order_service, "datetime", _FrozenClock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _status(self, for_date=None):
        return order_service.get_ordering_window_status(self.db, CAMPUS, for_date=for_date)

    # ── the reported bug ────────────────────────────────────────────────────
    def test_before_opening_is_not_open(self):
        """01:00 against a window that opens at 08:00 must NOT read as open."""
        status = self._status()
        self.assertFalse(status["is_open"])
        self.assertEqual("before_opening", status["reason"])

    def test_inside_window_is_open(self):
        self._patch_clock(_at(12, 30))
        status = self._status()
        self.assertTrue(status["is_open"])
        self.assertEqual("open", status["reason"])
        self.assertTrue(status["windows"][0]["is_open_now"])

    def test_after_closing_is_not_open(self):
        self._patch_clock(_at(22, 0))
        status = self._status()
        self.assertFalse(status["is_open"])
        self.assertEqual("after_closing", status["reason"])

    def test_closed_today(self):
        self.db = FakeDb(ordering_windows=[_window("w1", "08:00", "21:00", weekday=1, is_closed=True)])
        self._patch_clock(_at(12, 0))
        status = self._status()
        self.assertFalse(status["is_open"])
        self.assertEqual("closed_today", status["reason"])

    def test_full_window(self):
        self.db = FakeDb(
            ordering_windows=[_window("w1", "08:00", "21:00", weekday=1, capacity=5)],
            orders=[{"id": str(i), "is_squad_order": False, "squad_item_count": 1} for i in range(5)],
        )
        self._patch_clock(_at(12, 0))
        status = self._status()
        self.assertFalse(status["is_open"])
        self.assertEqual("full", status["reason"])
        self.assertFalse(status["any_capacity_remaining"])

    def test_capacity_left_but_clock_closed(self):
        """A window with room to spare is still closed outside its hours."""
        self.db = FakeDb(
            ordering_windows=[_window("w1", "08:00", "21:00", weekday=1, capacity=50)],
            orders=[{"id": "1", "is_squad_order": False, "squad_item_count": 1}],
        )
        self._patch_clock(_at(3, 0))
        status = self._status()
        self.assertTrue(status["any_capacity_remaining"])
        self.assertFalse(status["is_open"])

    def test_no_campus_is_unknown_not_closed(self):
        """The contract is tri-state. A guest who has not picked a campus must
        not be told a kitchen is shut — that is what opened the closed popup at
        guests with no campus selected."""
        status = order_service.get_ordering_window_status(self.db, None)
        self.assertIsNone(status["is_open"])
        self.assertEqual("no_campus", status["reason"])
        self.assertEqual([], status["windows"])

    # ── config fallback ─────────────────────────────────────────────────────
    def test_config_only_campus_uses_configured_hours(self):
        """No ordering_windows rows at all — the configured 08:00-16:00 applies,
        on the status endpoint exactly as it does at checkout."""
        self.db = FakeDb(ordering_windows=[])
        self._patch_clock(_at(9, 0))
        self.assertTrue(self._status()["is_open"], "09:00 is inside 08:00-16:00")
        self._patch_clock(_at(17, 0))
        self.assertFalse(self._status()["is_open"], "17:00 is outside 08:00-16:00")
        self.assertEqual("after_closing", self._status()["reason"])

    # ── next bookable slot ──────────────────────────────────────────────────
    def test_before_opening_schedules_for_today(self):
        slot = order_service.find_next_available_ordering_slot(
            self.db, CAMPUS, start_date=datetime(2026, 10, 6, tzinfo=WAT).date())
        self.assertEqual("2026-10-06", slot["date"], "01:00 must offer today's 08:00 opening")

    def test_after_closing_schedules_for_next_open_day(self):
        self._patch_clock(_at(22, 0))
        slot = order_service.find_next_available_ordering_slot(
            self.db, CAMPUS, start_date=datetime(2026, 10, 6, tzinfo=WAT).date())
        self.assertEqual("2026-10-07", slot["date"])

    def test_future_dates_ignore_the_clock(self):
        """The 7-day calendar asks about future days; capacity alone decides."""
        self._patch_clock(_at(1, 0))
        tomorrow = datetime(2026, 10, 7, tzinfo=WAT).date()
        self.assertTrue(self._status(for_date=tomorrow)["is_open"])

    # ── the refusal the frontend reads ──────────────────────────────────────
    def test_closed_refusal_carries_code_and_next_slot(self):
        with self.assertRaises(OrderingWindowUnavailable) as caught:
            order_service.resolve_ordering_window(self.db, CAMPUS)
        err = caught.exception
        self.assertEqual(ORDERING_WINDOW_CLOSED, err.code)
        self.assertEqual("2026-10-06", err.next_available_date)
        self.assertEqual("08:00", err.next_opens_at)

    def test_capacity_refusal_carries_capacity_code(self):
        self.db = FakeDb(
            ordering_windows=[_window("w1", "08:00", "21:00", weekday=1, capacity=1)],
            orders=[{"id": "1", "is_squad_order": False, "squad_item_count": 1}],
        )
        self._patch_clock(_at(12, 0))
        with self.assertRaises(OrderingWindowUnavailable) as caught:
            order_service.resolve_ordering_window(self.db, CAMPUS)
        self.assertEqual(ORDERING_WINDOW_AT_CAPACITY, caught.exception.code)
        self.assertEqual("2026-10-07", caught.exception.next_available_date)

    def test_open_window_resolves(self):
        self._patch_clock(_at(9, 0))
        window = order_service.resolve_ordering_window(self.db, CAMPUS)
        self.assertEqual("w1", window["id"])

    def test_raising_a_closed_refusal_does_not_search_for_the_next_slot(self):
        """The next-slot lookup is a day-by-day search, so it must be lazy.

        Every refused order raises this exception — including the ones the caller
        re-raises untouched because the client never asked to schedule. Eagerly
        working out the next slot would add that search to every closed attempt.
        """
        calls = []
        original = order_service.find_next_available_ordering_slot

        def counting(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        with unittest.mock.patch.object(order_service, "find_next_available_ordering_slot", counting):
            with self.assertRaises(OrderingWindowUnavailable):
                order_service.resolve_ordering_window(self.db, CAMPUS)
        self.assertEqual([], calls, "raising must not search for the next slot")

        # ...and reading the value does search, exactly once, then caches.
        with unittest.mock.patch.object(order_service, "find_next_available_ordering_slot", counting):
            with self.assertRaises(OrderingWindowUnavailable) as caught:
                order_service.resolve_ordering_window(self.db, CAMPUS)
            err = caught.exception
            self.assertEqual("2026-10-06", err.next_available_date)
            self.assertEqual("2026-10-06", err.next_available_date, "cached — not searched twice")
            self.assertEqual(1, len(calls))

    def test_resolver_failure_degrades_to_no_hint(self):
        """A backend that cannot answer the next-slot question must not turn a
        clean refusal into a 500."""
        def boom():
            raise RuntimeError("db down")

        err = OrderingWindowUnavailable("closed", code=ORDERING_WINDOW_CLOSED, next_slot_resolver=boom)
        self.assertIsNone(err.next_available_date)
        self.assertIsNone(err.next_opens_at)


import unittest.mock  # noqa: E402  (used by _patch_clock above)

if __name__ == "__main__":
    unittest.main()
