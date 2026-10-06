"""Saved-address write -> read round trip over real HTTP.

Pins the contract confirmed against the live "test 2" database: `user_addresses`
already has `delivery_type` ('on_campus' | 'off_campus') and
`delivery_location_id` (a hostel id for on_campus, a gate id for off_campus — the
same meaning `orders.delivery_location_id` has). No migration is involved; the
bug was purely that the write side dropped the two fields, so every saved address
had them empty and checkout could not replay it.

Driven through the real `require_auth` (the fake DB answers `auth_get_user` and
`profiles`), so the auth wiring is exercised too.
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

import sys
import unittest
from unittest import mock

from app import create_app
from app.config import config_map

CAMPUS = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_CAMPUS = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER = "22222222-2222-2222-2222-222222222222"
HOSTEL = "44444444-4444-4444-4444-444444444444"
GATE = "33333333-3333-3333-3333-333333333333"
OTHER_HOSTEL = "55555555-5555-5555-5555-555555555555"
INACTIVE_GATE = "66666666-6666-6666-6666-666666666666"

HOSTELS = {
    HOSTEL: {"name": "Block A", "campus_id": CAMPUS, "delivery_fee": 250,
             "is_active": "true", "gate_id": GATE},
    OTHER_HOSTEL: {"name": "Other Campus Hostel", "campus_id": OTHER_CAMPUS,
                   "delivery_fee": 999, "is_active": "true", "gate_id": GATE},
}
GATES = {
    GATE: {"name": "South Gate", "campus_id": CAMPUS, "lat": 7.3005, "lon": 5.1505,
           "base_fee": 300, "rate_per_km": 100, "min_fee": 300, "is_active": "true"},
    INACTIVE_GATE: {"name": "Closed Gate", "campus_id": CAMPUS, "lat": 7.31,
                    "lon": 5.16, "base_fee": 100, "rate_per_km": 50,
                    "min_fee": 100, "is_active": "false"},
}


class _Resp(list):
    """supabase-py returns a list-like from insert()/update(); routes index row[0]."""


class _Chain:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.f, self._in, self._single = {}, {}, False

    def select(self, *_a, **_k):
        return self

    def insert(self, row):
        r = dict(row)
        r.setdefault("id", "addr-%d" % (len(self.db.addresses) + 1))
        self.db.addresses.append(r)
        return _Resp([r])

    def update(self, row):
        r = dict(row)
        for a in self.db.addresses:
            if a.get("id") == self.f.get("id"):
                a.update(r)
                return _Resp([dict(a)])
        return _Resp([])

    def eq(self, key, value):
        self.f[key] = value
        return self

    def gte(self, key, value):
        self.f[key] = value
        return self

    def in_(self, key, values):
        self._in[key] = list(values)
        return self

    def limit(self, _n):
        return self

    def order(self, *_a, **_k):
        return self

    def single(self):
        self._single = True
        return self

    @property
    def not_(self):  # noqa: N802 — mirrors the supabase-py builder name
        return self

    def _filtered(self, rows):
        for key in ("id", "campus_id", "is_active"):
            if key in self.f:
                rows = [r for r in rows if r.get(key) == self.f[key]]
        for key, vals in self._in.items():
            rows = [r for r in rows if r.get(key) in vals]
        return rows

    def execute(self):
        t = self.table
        rows = []
        if t == "user_addresses":
            rows = [dict(a) for a in self.db.addresses]
        elif t == "hostels":
            rows = self._filtered([dict(v, id=k) for k, v in HOSTELS.items()])
        elif t == "gates":
            rows = self._filtered([dict(v, id=k) for k, v in GATES.items()])
        elif t == "profiles":
            rows = [{"id": USER, "full_name": "Tester", "role": "student",
                     "is_active": True, "campus_id": CAMPUS}]
        return (rows[0] if rows else None) if self._single else rows


class FakeDb:
    def __init__(self):
        self.addresses = []

    def table(self, name):
        return _Chain(self, name)

    def auth_get_user(self, _token):
        return {"id": USER}


def _patch_db_everywhere(db):
    """Every module did `from app.db import get_db/get_user_client`, so the names
    have to be patched in each namespace, not just in app.db."""
    for mod in list(sys.modules.values()):
        if mod is None or not hasattr(mod, "__dict__"):
            continue
        for attr in ("get_db", "get_user_client"):
            if attr in mod.__dict__ and callable(mod.__dict__[attr]):
                try:
                    mock.patch.object(mod, attr, lambda: db).start()
                except Exception:
                    pass


class SavedAddressRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_map["production"])
        self.db = FakeDb()
        self.client = self.app.test_client()
        self.headers = {"Authorization": "Bearer good-token"}
        _patch_db_everywhere(self.db)

    def _save(self, body):
        return self.client.post("/api/auth/addresses", json=body, headers=self.headers)

    # ── write side ───────────────────────────────────────────────────────────
    def test_on_campus_address_persists_both_fields(self):
        r = self._save({"label": "Hostel", "line1": "Block A", "city": "Akure",
                        "delivery_type": "on_campus", "delivery_location_id": HOSTEL,
                        "hostel": "Block A"})
        body = r.get_json()
        self.assertEqual(201, r.status_code, body)
        self.assertEqual("on_campus", body.get("delivery_type"))
        self.assertEqual(HOSTEL, body.get("delivery_location_id"))

    def test_off_campus_address_persists_both_fields(self):
        r = self._save({"label": "Home", "line1": "12 Adeyemi St", "city": "Akure",
                        "delivery_type": "off_campus", "delivery_location_id": GATE,
                        "latitude": 7.30, "longitude": 5.15})
        body = r.get_json()
        self.assertEqual(201, r.status_code, body)
        self.assertEqual("off_campus", body.get("delivery_type"))
        self.assertEqual(GATE, body.get("delivery_location_id"))
        self.assertEqual(7.30, body.get("latitude"))
        self.assertEqual(5.15, body.get("longitude"))

    def test_invalid_delivery_type_is_refused(self):
        r = self._save({"label": "X", "line1": "y", "city": "Akure",
                        "delivery_type": "banana"})
        self.assertEqual(400, r.status_code, r.get_json())

    def test_hostel_id_from_another_campus_is_refused(self):
        r = self._save({"label": "X", "line1": "y", "city": "Akure",
                        "delivery_type": "on_campus",
                        "delivery_location_id": OTHER_HOSTEL})
        self.assertEqual(400, r.status_code, r.get_json())

    def test_inactive_gate_is_refused(self):
        r = self._save({"label": "X", "line1": "y", "city": "Akure",
                        "delivery_type": "off_campus",
                        "delivery_location_id": INACTIVE_GATE})
        self.assertEqual(400, r.status_code, r.get_json())

    def test_hostel_id_used_as_a_gate_is_refused(self):
        """The id must match the type, or checkout would replay a hostel as a gate."""
        r = self._save({"label": "X", "line1": "y", "city": "Akure",
                        "delivery_type": "off_campus",
                        "delivery_location_id": HOSTEL})
        self.assertEqual(400, r.status_code, r.get_json())

    def test_malformed_uuid_is_refused(self):
        r = self._save({"label": "X", "line1": "y", "city": "Akure",
                        "delivery_type": "off_campus",
                        "delivery_location_id": "not-a-uuid"})
        self.assertEqual(400, r.status_code, r.get_json())

    def test_old_row_without_the_fields_still_saves(self):
        r = self._save({"label": "Legacy", "line1": "Somewhere", "city": "Akure",
                        "latitude": 7.29, "longitude": 5.14})
        body = r.get_json()
        self.assertEqual(201, r.status_code, body)
        self.assertIsNone(body.get("delivery_type"))
        self.assertIsNone(body.get("delivery_location_id"))

    # ── read side ────────────────────────────────────────────────────────────
    def test_get_returns_the_fields_and_the_location_name(self):
        self._save({"label": "Hostel", "line1": "Block A", "city": "Akure",
                    "delivery_type": "on_campus", "delivery_location_id": HOSTEL,
                    "hostel": "Block A"})
        self._save({"label": "Home", "line1": "12 Adeyemi St", "city": "Akure",
                    "delivery_type": "off_campus", "delivery_location_id": GATE,
                    "latitude": 7.30, "longitude": 5.15})
        rows = self.client.get("/api/auth/addresses", headers=self.headers).get_json()
        by_label = {a["label"]: a for a in rows}
        self.assertEqual("Block A", by_label["Hostel"]["delivery_location_name"])
        self.assertEqual("South Gate", by_label["Home"]["delivery_location_name"])

    # ── update side ──────────────────────────────────────────────────────────
    def test_patch_of_location_only_keeps_the_stored_type(self):
        """A PATCH that changes only the location must not silently drop it."""
        self._save({"label": "Hostel", "line1": "Block A", "city": "Akure",
                    "delivery_type": "on_campus", "delivery_location_id": HOSTEL,
                    "hostel": "Block A"})
        r = self.client.patch("/api/auth/addresses/addr-1",
                              json={"delivery_location_id": HOSTEL},
                              headers=self.headers)
        body = r.get_json()
        self.assertEqual(200, r.status_code, body)
        self.assertEqual(HOSTEL, body.get("delivery_location_id"))

    def test_patch_to_another_campuss_hostel_is_refused(self):
        self._save({"label": "Hostel", "line1": "Block A", "city": "Akure",
                    "delivery_type": "on_campus", "delivery_location_id": HOSTEL,
                    "hostel": "Block A"})
        r = self.client.patch("/api/auth/addresses/addr-1",
                              json={"delivery_type": "on_campus",
                                    "delivery_location_id": OTHER_HOSTEL},
                              headers=self.headers)
        self.assertEqual(400, r.status_code, r.get_json())


if __name__ == "__main__":
    unittest.main()
