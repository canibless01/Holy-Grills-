"""Two data-contract regressions found against the live "test 2" database.

  1. Rewards > Challenges listed 10 badges under "Badges Earned" for an account
     with 1 earned badge: the backend put every *definition* in one list, so the
     UI had nothing to split on.
  2. A saved address could not be replayed at checkout — the API's field
     allowlist silently dropped `delivery_type` / `delivery_location_id`, so
     every saved address had them empty, and the coordinates were stored as
     `latitude`/`longitude` while the client read `lat`/`lng`. Both halves are
     pinned here. The two columns already exist on `user_addresses` (confirmed
     against the live database), so no migration is involved.
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
import unittest.mock

from app import create_app
from app.config import config_map
from app.services import milestone_service
from app.routes import auth as auth_routes

USER = "22222222-2222-2222-2222-222222222222"
MILESTONE_FIRST_ORDER = "aaaaaaaa-0000-0000-0000-000000000001"
MILESTONE_BIG_SPENDER = "aaaaaaaa-0000-0000-0000-000000000002"


def _milestone(mid, title, window=None):
    return {
        "id": mid,
        "title": title,
        "description": f"Do the thing: {title}",
        "trigger_type": "order_count",
        "trigger_value": 1,
        "hp_awarded": 50,
        "icon_won": "🏅",
        "icon_locked": "🔒",
        "time_window": window,
        "is_active": True,
        "campus_id": None,
    }


class _Chain:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self._single = False

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        return self

    @property
    def not_(self):  # noqa: N802 — mirrors the supabase-py builder name
        return self

    def in_(self, _key, _values):
        return self

    def is_(self, _key, _value):
        return self

    def or_(self, _expr):
        return self

    def order(self, *_a, **_k):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = self.db.rows_for(self.table)
        return rows[0] if (self._single and rows) else rows


class FakeDb:
    def __init__(self, milestones=(), user_milestones=()):
        self.milestones = list(milestones)
        self.user_milestones = list(user_milestones)

    def table(self, name):
        return _Chain(self, name)

    def rows_for(self, table):
        if table == "milestones":
            return [dict(m) for m in self.milestones]
        if table == "user_milestones":
            return [dict(u) for u in self.user_milestones]
        return []


class BadgeSplitTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_map["production"])
        self.ctx = self.app.test_request_context()
        self.ctx.push()
        self.addCleanup(self.ctx.pop)

    def _run(self, earned_ids):
        db = FakeDb(
            milestones=[
                _milestone(MILESTONE_FIRST_ORDER, "[TEST] FUTA: First Order"),
                _milestone(MILESTONE_BIG_SPENDER, "[TEST] FUTA: Big Spender"),
            ],
            user_milestones=[
                {"milestone_id": mid, "period_key": None, "completed_at": "2026-10-01T10:00:00Z",
                 "hp_awarded": 50}
                for mid in earned_ids
            ],
        )
        with unittest.mock.patch.object(milestone_service, "get_user_client", return_value=db):
            return milestone_service.get_user_milestones(USER)

    def test_earned_only_in_badges_earned(self):
        result = self._run([MILESTONE_FIRST_ORDER])
        self.assertEqual([MILESTONE_FIRST_ORDER], [b["id"] for b in result["badges_earned"]])
        self.assertEqual([MILESTONE_BIG_SPENDER], [b["id"] for b in result["badges_locked"]])
        for badge in result["badges_earned"]:
            self.assertTrue(badge["earned"])
        for badge in result["badges_locked"]:
            self.assertFalse(badge["earned"])

    def test_new_user_earns_nothing(self):
        result = self._run([])
        self.assertEqual([], result["badges_earned"])
        self.assertEqual(2, len(result["badges_locked"]))

    def test_badges_key_kept_for_compatibility(self):
        """The old key still carries every badge with the `earned` flag."""
        result = self._run([MILESTONE_FIRST_ORDER])
        self.assertEqual(2, len(result["badges"]))
        self.assertEqual(
            {MILESTONE_FIRST_ORDER},
            {b["id"] for b in result["badges"] if b["earned"]},
        )


class _RefChain:
    """A `.table(...)` chain that RECORDS its filters, so a test can assert the
    lookup was scoped by campus and is_active rather than answered blindly."""

    def __init__(self, db, table):
        self.db, self.table, self.filters, self._single = db, table, {}, False

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, _n):
        return self

    def in_(self, _key, _values):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        return self.db.rows_for(self.table, self.filters)


class _HostelGateDb:
    """Answers `hostels` / `gates` lookups for the address validator.

    `hostels` / `gates` map id -> campus_id, or id -> (campus_id, is_active) to
    plant an inactive row.
    """

    def __init__(self, hostels=(), gates=()):
        self.hostels, self.gates = dict(hostels), dict(gates)

    def table(self, name):
        return _RefChain(self, name)

    def rows_for(self, table, filters):
        source = self.hostels if table == "hostels" else self.gates if table == "gates" else {}
        out = []
        for rid, val in source.items():
            campus, active = (val if isinstance(val, tuple) else (val, "true"))
            if filters.get("id") not in (None, rid):
                continue
            if filters.get("campus_id") not in (None, campus):
                continue
            if filters.get("is_active") not in (None, active):
                continue
            out.append({"id": rid, "name": f"{table[:-1]}-{rid[:4]}", "campus_id": campus})
        return out


class AddressFieldValidationTest(unittest.TestCase):
    """`_validate_address_fields` is the allowlist that used to drop the delivery
    selection, so a saved address could not be replayed at checkout.

    `user_addresses` stores `delivery_type` ('on_campus' | 'off_campus') and
    `delivery_location_id` (a hostel id for on_campus, a gate id for off_campus —
    the same meaning `orders.delivery_location_id` has). `create_order` re-reads
    both from the saved address, so they have to survive the write.
    """

    CAMPUS = "11111111-1111-1111-1111-111111111111"
    HOSTEL = "44444444-4444-4444-4444-444444444444"
    GATE = "33333333-3333-3333-3333-333333333333"

    def setUp(self):
        self.app = create_app(config_map["production"])
        self.db = _HostelGateDb(hostels={self.HOSTEL: self.CAMPUS},
                                gates={self.GATE: self.CAMPUS})

    def _validate(self, body, db=None):
        return auth_routes._validate_address_fields(
            body, db=db if db is not None else self.db, campus_id=self.CAMPUS)

    # ── the delivery selection survives ──────────────────────────────────────
    def test_delivery_selection_is_kept(self):
        fields, err = self._validate({
            "label": "Home", "line1": "12 Adeyemi St", "city": "Akure",
            "delivery_type": "off_campus",
            "delivery_location_id": self.GATE,
        })
        self.assertIsNone(err)
        self.assertEqual("off_campus", fields["delivery_type"])
        self.assertEqual(self.GATE, fields["delivery_location_id"])

    def test_on_campus_hostel_is_kept(self):
        fields, err = self._validate({
            "delivery_type": "on_campus",
            "delivery_location_id": self.HOSTEL,
            "hostel": "Block A",
        })
        self.assertIsNone(err)
        self.assertEqual("on_campus", fields["delivery_type"])
        self.assertEqual(self.HOSTEL, fields["delivery_location_id"])
        self.assertEqual("Block A", fields["hostel"])

    def test_legacy_type_alias_still_accepted(self):
        """`type` was the field name the address form sent before this was fixed."""
        fields, err = self._validate({
            "type": "on_campus", "delivery_location_id": self.HOSTEL,
        })
        self.assertIsNone(err)
        self.assertEqual("on_campus", fields["delivery_type"])
        self.assertEqual(self.HOSTEL, fields["delivery_location_id"])

    def test_type_without_a_location_is_allowed_but_stores_no_id(self):
        """The form may submit the type before the user picks a hostel/gate."""
        fields, err = self._validate({"delivery_type": "on_campus"})
        self.assertIsNone(err)
        self.assertEqual("on_campus", fields["delivery_type"])
        self.assertIsNone(fields["delivery_location_id"])

    def test_no_type_means_the_id_is_dropped(self):
        """An id with no type has no meaning — hostel? gate? Store it as null."""
        fields, err = self._validate({"delivery_location_id": self.GATE})
        self.assertIsNone(err)
        self.assertIsNone(fields["delivery_location_id"])

    # ── validation ───────────────────────────────────────────────────────────
    def test_bad_delivery_type_rejected(self):
        fields, err = self._validate({"delivery_type": "banana"})
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_malformed_uuid_rejected(self):
        fields, err = self._validate({"delivery_type": "off_campus",
                                      "delivery_location_id": "not-a-uuid"})
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_blank_ref_becomes_null(self):
        fields, err = self._validate({"delivery_type": "off_campus",
                                      "delivery_location_id": ""})
        self.assertIsNone(err)
        self.assertIsNone(fields["delivery_location_id"])

    def test_hostel_id_for_an_off_campus_address_is_rejected(self):
        """The id must match the type, or checkout would replay a hostel as a gate."""
        fields, err = self._validate({"delivery_type": "off_campus",
                                      "delivery_location_id": self.HOSTEL})
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_gate_id_for_an_on_campus_address_is_rejected(self):
        fields, err = self._validate({"delivery_type": "on_campus",
                                      "delivery_location_id": self.GATE})
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_unknown_id_is_rejected(self):
        fields, err = self._validate({"delivery_type": "off_campus",
                                      "delivery_location_id": "99999999-9999-9999-9999-999999999999"})
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_inactive_gate_is_rejected(self):
        db = _HostelGateDb(gates={self.GATE: (self.CAMPUS, "false")})
        fields, err = self._validate({"delivery_type": "off_campus",
                                      "delivery_location_id": self.GATE}, db=db)
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_gate_from_another_campus_is_rejected(self):
        other = "22222222-2222-2222-2222-222222222222"
        db = _HostelGateDb(gates={self.GATE: other})
        fields, err = self._validate({"delivery_type": "off_campus",
                                      "delivery_location_id": self.GATE}, db=db)
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_no_campus_on_the_caller_cannot_be_proven_so_is_rejected(self):
        """Without a campus we cannot prove the row belongs to the caller."""
        fields, err = auth_routes._validate_address_fields(
            {"delivery_type": "off_campus", "delivery_location_id": self.GATE},
            db=self.db, campus_id=None)
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    # ── unchanged behaviour ──────────────────────────────────────────────────
    def test_coordinates_survive(self):
        fields, err = self._validate({"latitude": 7.2954, "longitude": 5.1421})
        self.assertIsNone(err)
        self.assertEqual(7.2954, fields["latitude"])
        self.assertEqual(5.1421, fields["longitude"])

    def test_unknown_keys_still_dropped(self):
        fields, err = self._validate({"label": "Home", "sneaky": "x", "is_admin": True})
        self.assertIsNone(err)
        self.assertNotIn("sneaky", fields)
        self.assertNotIn("is_admin", fields)


if __name__ == "__main__":
    unittest.main()
