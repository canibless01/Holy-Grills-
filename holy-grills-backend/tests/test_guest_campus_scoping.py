"""Guest campus scoping on the delivery fee preview and the leaderboard.

Both of these were reported symptoms of one root cause: guests send their chosen
campus as an `X-Campus-ID` header, and `app/routes/events.py::_get_campus_id` is
the reference reader for it (`?campus_id=` -> header -> signed-in session). Routes
that resolved the campus from the request body and `g.campus_id` alone never saw
that header, so for a guest -- who has no `g.campus_id` -- the campus resolved to
`None`. What `None` then meant differed per route, which is why the two bugs
looked unrelated:

  * `POST /delivery/calculate-fee` -- `is_within_delivery_area()` FAILS OPEN on
    `None` (no radius check at all) and `find_nearest_gate()` drops its campus
    filter, so the "nearest" gate was picked from EVERY campus and the fee was
    priced against a gate the guest does not belong to.
  * `GET /leaderboard` -- `if campus_id:` applied no filter for `None`, so the
    board was silently platform-wide across all campuses. The route also had no
    auth decorator at all, so `g.campus_id` was unset even for a signed-in user.

The clock is frozen (WAT = UTC+1) and the database is a fake, so these pin the
rules without needing a live Supabase project.
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
from unittest import mock

from app import create_app
from app.config import config_map

WAT = timezone(timedelta(hours=1))

# Two campuses, each with its own gate and centre, far enough apart that a pin
# near one is nowhere near the other.
CAMPUS_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CAMPUS_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

# A pin 1 km from A's gate and ~900 km from B's.
PIN = {"lat": 7.3000, "lon": 5.1500}
GATE_A = {"id": "g-a", "name": "South Gate", "campus_id": CAMPUS_A,
          "lat": 7.3005, "lon": 5.1505, "base_fee": 300, "rate_per_km": 100,
          "min_fee": 300, "is_active": "true"}
GATE_B = {"id": "g-b", "name": "Other Campus Gate", "campus_id": CAMPUS_B,
          "lat": 6.5000, "lon": 3.3000, "base_fee": 900, "rate_per_km": 500,
          "min_fee": 900, "is_active": "true"}


# ── fake PostgREST ────────────────────────────────────────────────────────────
class _Chain:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self._single = db, table, {}, False

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def gte(self, key, value):
        self.filters[key] = value
        return self

    def neq(self, key, value):
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
        return (rows[0] if rows else None) if self._single else rows


class FakeDb:
    """Gates for two campuses; campuses carry a centre point each.

    `auth_get_user` and the `profiles` row let the REAL optional_auth run, so the
    signed-in path is exercised through the actual middleware rather than a stub.
    """

    def __init__(self, user_campus=CAMPUS_A):
        self.user_campus = user_campus

    def auth_get_user(self, _token):
        return {"id": "u1"}

    def table(self, name):
        return _Chain(self, name)

    def rows_for(self, table, filters):
        if table == "gates":
            out = [dict(g) for g in (GATE_A, GATE_B) if g["is_active"] == "true"]
            if "campus_id" in filters:
                out = [g for g in out if g["campus_id"] == filters["campus_id"]]
            if "id" in filters:
                out = [g for g in out if g["id"] == filters["id"]]
            return out
        if table == "campuses":
            centres = {
                CAMPUS_A: {"id": CAMPUS_A, "lat": 7.3000, "lon": 5.1500},
                CAMPUS_B: {"id": CAMPUS_B, "lat": 6.5000, "lon": 3.3000},
            }
            cid = filters.get("id")
            return [dict(centres[cid])] if cid in centres else []
        if table == "kitchen_settings":
            return []
        if table == "profiles":
            return [{
                "id": "u1", "full_name": "Tester", "role": "student",
                "is_active": True, "campus_id": self.user_campus,
            }]
        return []


class _FrozenClock(datetime):
    """A fixed WAT instant — 2026-10-06 10:00, well inside a normal window."""

    @classmethod
    def now(cls, tz=None):
        base = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)  # 10:00 WAT
        return base.astimezone(tz) if tz else base.replace(tzinfo=None)


def _patch_db_everywhere(db):
    """Every module did `from app.db import get_db/get_user_client`, so the names
    have to be patched in each namespace, not just in app.db."""
    import sys

    for mod in list(sys.modules.values()):
        if mod is None or not hasattr(mod, "__dict__"):
            continue
        for attr in ("get_db", "get_user_client"):
            if attr in mod.__dict__ and callable(mod.__dict__[attr]):
                try:
                    mock.patch.object(mod, attr, lambda: db).start()
                except Exception:
                    pass


class GuestCampusScopingTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_map["production"])
        self.db = FakeDb()
        self.client = self.app.test_client()
        _patch_db_everywhere(self.db)

    # ── the fee preview ──────────────────────────────────────────────────────
    def test_guest_fee_uses_a_gate_from_the_guests_own_campus(self):
        with self.app.test_request_context():
            r = self.client.post(
                "/api/delivery/calculate-fee",
                json={"delivery_type": "off_campus", "lat": PIN["lat"], "lon": PIN["lon"]},
                headers={"X-Campus-ID": CAMPUS_A},
            )
        body = r.get_json()
        self.assertEqual(200, r.status_code, body)
        # The nearest gate overall is B's only because B is unscoped; with the
        # campus honoured it must be A's.
        self.assertEqual(GATE_A["id"], (body.get("gate") or {}).get("id"), body)

    def test_guest_fee_without_any_campus_is_refused_not_priced(self):
        """An unresolvable campus must not silently fall back to every campus."""
        with self.app.test_request_context():
            r = self.client.post(
                "/api/delivery/calculate-fee",
                json={"delivery_type": "off_campus", "lat": PIN["lat"], "lon": PIN["lon"]},
            )
        self.assertEqual(400, r.status_code, r.get_json())

    # ── the leaderboard ──────────────────────────────────────────────────────
    def test_guest_leaderboard_filters_on_the_header_campus(self):
        """`if campus_id:` applied no filter for None, so the board was platform-wide."""
        seen = []
        original = _Chain.execute

        def spy(self):
            if self.table == "profiles" and self._single is False:
                seen.append(dict(self.filters))
            return original(self)

        with mock.patch.object(_Chain, "execute", spy):
            with self.app.test_request_context():
                r = self.client.get(
                    "/api/leaderboard?period_type=all_time",
                    headers={"X-Campus-ID": CAMPUS_A},
                )
        self.assertEqual(200, r.status_code, r.get_json())
        self.assertTrue(seen, "no profiles query was made")
        self.assertEqual(CAMPUS_A, seen[-1].get("campus_id"), seen[-1])

    def test_guest_leaderboard_without_a_campus_is_refused(self):
        """No campus resolvable: refuse, exactly as /delivery/hostels does.

        An unscoped query here would rank every campus's students together.
        """
        with self.app.test_request_context():
            r = self.client.get("/api/leaderboard?period_type=all_time")
        body = r.get_json()
        self.assertEqual(400, r.status_code, body)
        self.assertEqual("CAMPUS_SELECTION_REQUIRED", body.get("code"), body)

    def test_signed_in_user_needs_no_header(self):
        """The route had NO auth decorator at all, so g.campus_id was never set.

        Driven through the real optional_auth (the fake DB answers auth_get_user
        and profiles), so this proves the decorator wiring rather than a stub.
        """
        seen = []
        original = _Chain.execute

        def spy(self):
            if self.table == "profiles" and self._single is False:
                seen.append(dict(self.filters))
            return original(self)

        with mock.patch.object(_Chain, "execute", spy):
            with self.app.test_request_context():
                r = self.client.get(
                    "/api/leaderboard?period_type=all_time",
                    headers={"Authorization": "Bearer good-token"},
                )
        self.assertEqual(200, r.status_code, r.get_json())
        self.assertTrue(seen, "no profiles query was made")
        self.assertEqual(CAMPUS_A, seen[-1].get("campus_id"), seen[-1])


if __name__ == "__main__":
    unittest.main()
