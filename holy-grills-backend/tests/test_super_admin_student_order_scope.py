"""A super_admin is first of all a student: the account was registered with a
profile campus_id and only later upgraded. Order placement must therefore keep
using the profile campus no matter what the admin campus switcher
(hg_admin_campus_id / hg_admin_scope_all -> X-Campus-ID / X-Campus-Scope
headers) currently points at. The admin-write scope machinery must never leak
into the customer checkout path.
"""
import os
import unittest
from unittest.mock import patch
from flask import Flask, g

for _name in ('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_ANON_KEY'):
    os.environ.setdefault(_name, 'https://example.supabase.co' if _name == 'SUPABASE_URL' else 'test')

from app.services import order_service as service
from app.messages import MSG

CAMPUS = '11111111-1111-4111-8111-111111111111'
OTHER_CAMPUS = '44444444-4444-4444-8444-444444444444'
MEAL = '22222222-2222-4222-8222-222222222222'
HOSTEL = '33333333-3333-4333-8333-333333333333'


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.one = db, table, [], False

    @property
    def not_(self):
        return self

    def select(self, *a):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def gte(self, *a):
        return self

    def in_(self, *a):
        return self

    def or_(self, *a):
        return self

    def is_(self, key, value):
        self.filters.append((key, None if value == 'null' else value))
        return self

    def order(self, *a):
        return self

    def limit(self, *a):
        return self

    def single(self):
        self.one = True
        return self

    def execute(self):
        rows = [dict(row) for row in self.db.rows.get(self.table, [])
                if all(row.get(k) == v for k, v in self.filters)]
        return (rows[0] if rows else None) if self.one else rows

    def insert(self, *a):
        raise AssertionError('Quote attempted an insert')

    def update(self, *a):
        raise AssertionError('Quote attempted an update')

    def delete(self, *a):
        raise AssertionError('Quote attempted a deletion')


class Db:
    def __init__(self):
        self.rows = {
            'campuses': [
                {'id': CAMPUS, 'is_active': True},
                {'id': OTHER_CAMPUS, 'is_active': True},
            ],
            'profiles': [{
                'id': 'super1', 'phone': '08012345678', 'campus_id': CAMPUS,
                'is_active': True, 'next_order_free_delivery_cap': 0,
            }],
            'menu_items': [{
                'id': MEAL, 'campus_id': CAMPUS, 'name': 'Meal', 'price': 2050,
                'hp_multiplier': 0.5, 'is_available': True,
            }],
            'hostels': [{
                'id': HOSTEL, 'campus_id': CAMPUS,
                'delivery_fee': 250, 'is_active': 'true',
            }],
        }

    def table(self, name):
        return Query(self, name)

    def rpc(self, *a):
        raise AssertionError('Quote called a mutating RPC')


PAYLOAD = {
    'items': [{'menu_item_id': MEAL, 'quantity': 1}],
    'payment_method': 'card',
    'delivery_type': 'on_campus',
    'delivery_location_id': HOSTEL,
}


class SuperAdminStudentCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(HP_PER_NAIRA_FOOD=0.1, SQUAD_ORDER_ENABLED=False)
        self.db = Db()

    def quote(self, headers=None, profile_campus=CAMPUS):
        # g.campus_id is what require_auth sets from the profiles row (the
        # student's registration campus) — never from a request header.
        from app.routes import events
        with self.app.test_request_context(headers=headers or {}), \
                patch.object(service, 'get_db', return_value=self.db), \
                patch.object(service, 'get_user_client', return_value=self.db), \
                patch.object(events, 'get_db', return_value=self.db), \
                patch.object(service.hp_service, 'get_user_tier',
                             return_value={'tier': {'slug': 'ember'}}), \
                patch.object(service.hp_service, 'calculate_delivery_hp',
                             return_value=102):
            g.user_id = 'super1'
            g.user_role = 'super_admin'
            g.campus_id = profile_campus
            return service.create_order('super1', PAYLOAD, quote_only=True)

    def test_global_scope_header_does_not_unscope_the_order(self):
        # Admin switcher on "All Campuses": apiClient sends X-Campus-Scope:
        # global and no X-Campus-ID. The order must still resolve to the
        # profile campus — the header is only read by admin-write helpers.
        quote = self.quote(headers={'X-Campus-Scope': 'global'})
        self.assertEqual(quote['total_amount'], 2300)  # 2050 meal + 250 delivery

    def test_admin_campus_header_cannot_redirect_the_order(self):
        # Admin switcher on a *different* campus: X-Campus-ID names it, but the
        # meal only exists at the profile campus. A successful quote proves the
        # profile campus (g.campus_id) won and the header was ignored.
        quote = self.quote(headers={'X-Campus-ID': OTHER_CAMPUS})
        self.assertEqual(quote['total_amount'], 2300)

    def test_no_campus_anywhere_is_rejected_even_with_global_marker(self):
        # Edge case: no profile campus and no X-Campus-ID (the global marker is
        # not an order concept). Checkout must fail with CAMPUS_REQUIRED rather
        # than creating a campus-less order.
        with self.assertRaises(ValueError) as ctx:
            self.quote(headers={'X-Campus-Scope': 'global'}, profile_campus=None)
        self.assertEqual(str(ctx.exception), MSG.CAMPUS_REQUIRED)

    def test_header_campus_rescues_order_when_profile_campus_missing(self):
        # Same edge case, but the admin switcher names a real campus: the
        # _get_campus_id() fallback accepts it so checkout still works.
        quote = self.quote(
            headers={'X-Campus-ID': CAMPUS}, profile_campus=None)
        self.assertEqual(quote['total_amount'], 2300)


if __name__ == '__main__':
    unittest.main()
