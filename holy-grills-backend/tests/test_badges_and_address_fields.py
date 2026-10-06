"""Two data-contract regressions found against the live "test 2" database.

  1. Rewards > Challenges listed 10 badges under "Badges Earned" for an account
     with 1 earned badge: the backend put every *definition* in one list, so the
     UI had nothing to split on.
  2. A saved address could not be replayed at checkout — the API's field
     allowlist silently dropped `type` / `gate_id` / `location_id`, and the
     coordinates were stored as `latitude`/`longitude` while the client read
     `lat`/`lng`. Both halves are pinned here.
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


class AddressFieldValidationTest(unittest.TestCase):
    """`_validate_address_fields` is the allowlist that used to drop the
    delivery selection, so a saved address could not be replayed."""

    def setUp(self):
        self.app = create_app(config_map["production"])

    def _validate(self, body):
        return auth_routes._validate_address_fields(body)

    def test_delivery_selection_is_kept(self):
        fields, err = self._validate({
            "label": "Home", "line1": "12 Adeyemi St", "city": "Akure",
            "delivery_type": "off_campus",
            "gate_id": "33333333-3333-3333-3333-333333333333",
            "delivery_location_id": "33333333-3333-3333-3333-333333333333",
        })
        self.assertIsNone(err)
        self.assertEqual("off_campus", fields["delivery_type"])
        self.assertEqual("33333333-3333-3333-3333-333333333333", fields["gate_id"])

    def test_legacy_type_alias(self):
        fields, err = self._validate({"type": "on_campus", "location_id": "44444444-4444-4444-4444-444444444444"})
        self.assertIsNone(err)
        self.assertEqual("on_campus", fields["delivery_type"])
        self.assertEqual("44444444-4444-4444-4444-444444444444", fields["location_id"])

    def test_coordinates_survive(self):
        fields, err = self._validate({"latitude": 7.2954, "longitude": 5.1421})
        self.assertIsNone(err)
        self.assertEqual(7.2954, fields["latitude"])
        self.assertEqual(5.1421, fields["longitude"])

    def test_blank_refs_become_null(self):
        fields, err = self._validate({"delivery_type": "off_campus", "gate_id": "", "location_id": None})
        self.assertIsNone(err)
        self.assertIsNone(fields["gate_id"])
        self.assertIsNone(fields["location_id"])

    def test_bad_delivery_type_rejected(self):
        fields, err = self._validate({"delivery_type": "somewhere"})
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_malformed_uuid_rejected(self):
        fields, err = self._validate({"gate_id": "not-a-uuid"})
        self.assertIsNone(fields)
        self.assertIsNotNone(err)

    def test_unknown_keys_still_dropped(self):
        fields, err = self._validate({"label": "Home", "sneaky": "x", "is_admin": True})
        self.assertIsNone(err)
        self.assertNotIn("sneaky", fields)
        self.assertNotIn("is_admin", fields)


if __name__ == "__main__":
    unittest.main()
