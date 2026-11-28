"""Admin write scope contract.

The campus switcher in the admin panel (localStorage hg_admin_campus_id /
hg_admin_scope_all) must control where WRITES land, not only what is viewed:

  * super_admin + X-Campus-ID header        -> that campus
  * super_admin + X-Campus-Scope: global    -> campus_id NULL (global row)
  * super_admin + body scope="global"       -> campus_id NULL
  * campus admin                            -> always their own campus, every
                                               supplied header/value ignored
  * a duplicate-key 409 names the scope (Global or the campus name) that owns
    the existing row
"""
import copy
import inspect
import unittest
import os
from contextlib import ExitStack
from unittest.mock import patch

from flask import Flask, g

for name in ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'JWT_SECRET', 'SECRET_KEY'):
    os.environ.setdefault(name, 'https://example.supabase.co' if name == 'SUPABASE_URL' else 'test')

from app.routes import storefront, rewards, admin
from app.db import SupabaseError
from app.services import economics_service as econ
from werkzeug.exceptions import Forbidden

CAMPUS_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
CAMPUS_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
IMAGE = 'https://res.cloudinary.com/test-cloud/image/upload/v1/banners/main.png'


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, {}
    def select(self, *_):
        return self
    def eq(self, key, value):
        self.filters[key] = value
        return self
    def order(self, *_, **__):
        return self
    def limit(self, *_):
        return self
    def is_(self, key, value):
        return self.eq(key, None if value == 'null' else value)
    def single(self):
        if self.table == 'campuses':
            return self
        self._one = True
        return self
    def execute(self):
        if self.table == 'campuses':
            return {'id': CAMPUS_A, 'name': 'FUTA Main'}
        rows = self.db.conflict_owners.get(self.table, [])
        rows = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
        return (rows[0] if rows else None) if getattr(self, '_one', False) else rows
    def insert(self, payload):
        self.db.writes.append(copy.deepcopy(payload))
        if self.db.raise_conflict:
            raise SupabaseError('duplicate', 409, {'code': '23505'})
        return [copy.deepcopy(payload)]
    def update(self, data):
        self.db.writes.append(copy.deepcopy(data))
        return [copy.deepcopy(data)]


class DB:
    def __init__(self, conflict_owners=None, raise_conflict=False):
        self.writes = []
        self.conflict_owners = conflict_owners or {}
        self.raise_conflict = raise_conflict
    def table(self, table):
        return Query(self, table)


class WriteCampusIdTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(CLOUDINARY_CLOUD_NAME='test-cloud', CLOUDINARY_API_KEY='k', CLOUDINARY_API_SECRET='s')

    def resolve(self, role='super_admin', campus=CAMPUS_B, headers=None, json=None, explicit=None):
        with self.app.test_request_context('/', method='POST', json=json, headers=headers or {}):
            g.user_role = role
            g.campus_id = campus
            g.user_id = 'actor'
            return storefront._write_campus_id(explicit)

    def test_super_admin_header_campus_is_honoured(self):
        self.assertEqual(self.resolve(headers={'X-Campus-ID': CAMPUS_A}), CAMPUS_A)

    def test_super_admin_global_header_writes_null_even_with_profile_campus(self):
        # The bug: this used to fall back to the profile campus (FUTA Main).
        self.assertIsNone(self.resolve(campus=CAMPUS_B, headers={'X-Campus-Scope': 'global'}))

    def test_super_admin_global_body_scope_writes_null(self):
        self.assertIsNone(self.resolve(campus=CAMPUS_B, json={'scope': 'global'}))
        self.assertIsNone(self.resolve(campus=CAMPUS_B, json={'campus_scope': 'all_campuses'}))

    def test_super_admin_explicit_campus_beats_global_header(self):
        self.assertEqual(
            self.resolve(headers={'X-Campus-Scope': 'global'}, explicit=CAMPUS_A),
            CAMPUS_A,
        )

    def test_super_admin_without_any_signal_keeps_profile_fallback(self):
        self.assertEqual(self.resolve(campus=CAMPUS_B), CAMPUS_B)

    def test_campus_admin_is_pinned_to_own_campus(self):
        self.assertEqual(
            self.resolve(role='admin', campus=CAMPUS_B, headers={'X-Campus-Scope': 'global'}),
            CAMPUS_B,
        )
        self.assertEqual(
            self.resolve(role='admin', campus=CAMPUS_B, headers={'X-Campus-ID': CAMPUS_A}),
            CAMPUS_B,
        )
        self.assertEqual(
            self.resolve(role='admin', campus=CAMPUS_B, json={'scope': 'global'}, explicit=CAMPUS_A),
            CAMPUS_B,
        )


class SectionCreateScopeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(CLOUDINARY_CLOUD_NAME='test-cloud', CLOUDINARY_API_KEY='k', CLOUDINARY_API_SECRET='s')

    def create(self, headers=None, role='super_admin', campus=CAMPUS_B, data=None):
        db = DB()
        body = {'key': 'tier_icon_ember', 'section_type': 'tier_icon',
                'content': {'tier_slug': 'ember', 'image_url': IMAGE}}
        body.update(data or {})
        with ExitStack() as stack:
            stack.enter_context(self.app.test_request_context('/', method='POST', json=body, headers=headers or {}))
            stack.enter_context(patch.object(storefront, 'get_user_client', return_value=db))
            g.user_role = role
            g.campus_id = campus
            g.user_id = 'actor'
            response, status = inspect.unwrap(storefront.create_section)()
        return response, status, db

    def test_global_header_creates_row_without_campus_id(self):
        response, status, db = self.create(headers={'X-Campus-Scope': 'global'})
        self.assertEqual(status, 201, response.json)
        self.assertNotIn('campus_id', db.writes[0])

    def test_campus_header_stamps_selected_campus(self):
        response, status, db = self.create(headers={'X-Campus-ID': CAMPUS_A})
        self.assertEqual(status, 201, response.json)
        self.assertEqual(db.writes[0]['campus_id'], CAMPUS_A)

    def test_campus_admin_cannot_escape_own_campus_with_global_header(self):
        response, status, db = self.create(headers={'X-Campus-Scope': 'global'}, role='admin', campus=CAMPUS_B)
        self.assertEqual(status, 201, response.json)
        self.assertEqual(db.writes[0]['campus_id'], CAMPUS_B)


class KeyConflictScopeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(CLOUDINARY_CLOUD_NAME='test-cloud', CLOUDINARY_API_KEY='k', CLOUDINARY_API_SECRET='s')

    def test_conflict_names_global_scope(self):
        db = DB(conflict_owners={'storefront_sections': [{'key': 'share_template', 'campus_id': None}]})
        with self.app.test_request_context('/'):
            response, status = storefront._key_conflict_response(db, 'storefront_sections', 'share_template')
        self.assertEqual(status, 409)
        self.assertIn('Global', response.json['error'])
        self.assertEqual(response.json['scope'], 'global')
        self.assertIsNone(response.json['campus_id'])

    def test_conflict_names_campus_scope(self):
        db = DB(conflict_owners={'storefront_sections': [{'key': 'tier_icon_ember', 'campus_id': CAMPUS_A}]})
        with self.app.test_request_context('/'):
            response, status = storefront._key_conflict_response(
                db, 'storefront_sections', 'tier_icon_ember')
        self.assertEqual(status, 409)
        self.assertIn('FUTA Main', response.json['error'])
        self.assertEqual(response.json['scope'], 'campus')
        self.assertEqual(response.json['campus_id'], CAMPUS_A)

    def test_insert_conflict_surfaces_scope_through_insert_helper(self):
        db = DB(
            conflict_owners={'storefront_sections': [{'key': 'tier_icon_ember', 'campus_id': CAMPUS_A}]},
            raise_conflict=True,
        )
        with self.app.test_request_context('/', method='POST', json={}):
            g.user_id = 'actor'
            response, status = storefront._insert_cms(
                db, 'storefront_sections',
                {'key': 'tier_icon_ember', 'section_type': 'tier_icon'}, {})
        self.assertEqual(status, 409)
        self.assertIn('FUTA Main', response.json['error'])


class RewardCreateScopeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(CLOUDINARY_CLOUD_NAME='test-cloud', CLOUDINARY_API_KEY='k', CLOUDINARY_API_SECRET='s')
        self.db = DB()

    def food(self, **extras):
        return {'name': 'Meal', 'reward_type': 'food', 'fulfillment_type': 'menu_item',
                'food_cost': 500, 'packaging_cost': 100, 'menu_price': 2000,
                'margin_share_pct': 0.4, **extras}

    def create(self, body, headers=None, role='super_admin', campus=CAMPUS_B):
        with ExitStack() as stack:
            stack.enter_context(self.app.test_request_context('/', method='POST', json=body, headers=headers or {}))
            stack.enter_context(patch.object(rewards, 'get_user_client', return_value=self.db))
            stack.enter_context(patch.object(econ, 'get_hp_value', return_value=0.75))
            stack.enter_context(patch.object(econ, '_get_econ_setting',
                                             side_effect=lambda db, key, default: 1 if key == 'hp_rounding' else default))
            stack.enter_context(patch.object(rewards, 'send_notification'))
            g.user_id = 'admin'
            g.user_role = role
            g.campus_id = campus
            return inspect.unwrap(rewards.create_reward)()

    def test_super_admin_global_header_creates_global_reward(self):
        response, status = self.create(self.food(), headers={'X-Campus-Scope': 'global'})
        self.assertEqual(status, 201, response.json)
        self.assertIsNone(self.db.writes[0]['campus_id'])

    def test_super_admin_campus_header_stamps_reward(self):
        response, status = self.create(self.food(), headers={'X-Campus-ID': CAMPUS_A})
        self.assertEqual(status, 201, response.json)
        self.assertEqual(self.db.writes[0]['campus_id'], CAMPUS_A)

    def test_super_admin_no_signal_uses_profile_campus(self):
        response, status = self.create(self.food())
        self.assertEqual(status, 201, response.json)
        self.assertEqual(self.db.writes[0]['campus_id'], CAMPUS_B)

    def test_campus_admin_ignores_global_header(self):
        response, status = self.create(self.food(), headers={'X-Campus-Scope': 'global'},
                                       role='admin', campus=CAMPUS_B)
        self.assertEqual(status, 201, response.json)
        self.assertEqual(self.db.writes[0]['campus_id'], CAMPUS_B)


class WindowCampusTests(unittest.TestCase):
    """Delivery/ordering windows are campus-required rows with no global variant."""

    def setUp(self):
        self.app = Flask(__name__)

    def resolve(self, data=None, headers=None, role='super_admin', campus=CAMPUS_B):
        with self.app.test_request_context('/', method='POST', json=data or {}, headers=headers or {}):
            g.user_role = role
            g.campus_id = campus
            g.user_id = 'actor'
            return admin._window_campus(data or {})

    def test_super_admin_body_campus_wins(self):
        self.assertEqual(self.resolve(data={'campus_id': CAMPUS_A}), CAMPUS_A)

    def test_super_admin_header_campus_is_honoured(self):
        self.assertEqual(self.resolve(headers={'X-Campus-ID': CAMPUS_A}), CAMPUS_A)

    def test_super_admin_all_campuses_resolves_none(self):
        # The route turns None into a clear CAMPUS_ID_REQUIRED instead of
        # stamping the super admin's profile campus.
        self.assertIsNone(self.resolve(headers={'X-Campus-Scope': 'global'}))

    def test_campus_admin_is_pinned_and_cannot_name_another_campus(self):
        self.assertEqual(self.resolve(role='admin', campus=CAMPUS_B), CAMPUS_B)
        with self.assertRaises(Forbidden):
            self.resolve(data={'campus_id': CAMPUS_A}, role='admin', campus=CAMPUS_B)


if __name__ == '__main__':
    unittest.main()
