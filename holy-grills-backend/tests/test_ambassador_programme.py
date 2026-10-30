"""
Campus Ambassador Programme — contract tests.

Covers the fourteen mandated scenario groups end to end against an in-memory
mock of the PostgREST client (the real persistence rules live in the
2026102712* SQL migrations and are separately asserted as migration contracts
at the bottom of this file):

  1.  ambassador tag add / remove / re-tag
  2.  community_manager permission denial (decorator + in-handler guard)
  3.  caption personalization ({{link}} token)
  4.  share fallback + manual Pending/Seen/Shared activity statuses
  5.  new-customer and existing-customer click attribution
  6.  A -> B last-click replacement (RPC/SQL contract)
  7.  profiles.referred_by / referrals never touched
  8.  delivered order counted once; cancelled/refunded excluded
  9.  activity completion rate (7/10 = 70%)
  10. milestone claim dedupe
  11. single + multiple meal-discount grants (duplicate guard / override)
  12. checkout discount math with delivery still payable
  13. independent recurring (biweekly) grants keep separate expiry/redemption
  14. regression: referral HP / free sides / wallet / order hooks stay intact
"""
import inspect
import os
import unittest
import uuid
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

for name in ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY',
             'JWT_SECRET', 'SECRET_KEY'):
    os.environ.setdefault(
        name, 'https://example.supabase.co' if name == 'SUPABASE_URL' else 'test')

from flask import Flask, g  # noqa: E402

from app.constants import (ADMIN_ROLES, COMMUNITY_MANAGER_ROLE,  # noqa: E402
                           VALID_ROLES)
from app.routes import ambassadors as routes  # noqa: E402
from app.services import ambassador_service as svc  # noqa: E402

CAMPUS_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
CAMPUS_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
AMB = '11111111-1111-4111-8111-111111111111'
AMB2 = '22222222-2222-4222-8222-222222222222'
ADMIN_ID = '33333333-3333-4333-8333-333333333333'
MANAGER_ID = '44444444-4444-4444-8444-444444444444'
STUDENT_ID = '55555555-5555-4555-8555-555555555555'
MONTH = '2026-10'

MIGRATIONS = Path(__file__).resolve().parent.parent / 'migrations'
SCHEMA_SQL = (MIGRATIONS / '20261028084136_ambassador_programme_schema.sql').read_text()
TRACKING_SQL = (MIGRATIONS / '20261028084144_ambassador_tracking_rpcs.sql').read_text()
REWARD_SQL = (MIGRATIONS / '20261028084202_ambassador_reward_rpcs.sql').read_text()
SETTINGS_SQL = (MIGRATIONS / '20261028084221_ambassador_programme_settings.sql').read_text()


# ---------------------------------------------------------------------------
# In-memory PostgREST stand-in
# ---------------------------------------------------------------------------
class Query:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = []
        self._single = False
        self._insert = None
        self._patch = None

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters.append(('eq', key, value))
        return self

    def in_(self, key, values):
        self.filters.append(('in', key, set(values)))
        return self

    def is_(self, key, value):
        return self.eq(key, None if value == 'null' else value)

    def order(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def single(self):
        self._single = True
        return self

    def _matches(self, row):
        for kind, key, value in self.filters:
            if kind == 'eq':
                if row.get(key) != value:
                    return False
            elif row.get(key) not in value:
                return False
        return True

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, patch):
        self._patch = patch
        return self

    def execute(self):
        if self._insert is not None:
            payloads = self._insert if isinstance(self._insert, list) else [self._insert]
            out = []
            for payload in payloads:
                row = dict(payload)
                row.setdefault('id', str(uuid.uuid4()))
                self.db.tables.setdefault(self.table, []).append(row)
                self.db.written_tables.add(self.table)
                out.append(row)
            return out
        rows = [dict(r) for r in self.db.tables.get(self.table, []) if self._matches(r)]
        if self._patch is not None:
            for row in self.db.tables.get(self.table, []):
                if self._matches(row):
                    row.update(self._patch)
                    self.db.written_tables.add(self.table)
            rows = [dict(r) for r in self.db.tables.get(self.table, []) if self._matches(r)]
            return rows
        if self._single:
            return rows[0] if rows else None
        return rows


class MockDB:
    def __init__(self):
        self.tables = {}
        self.rpc_calls = []
        self.rpcs = {}
        self.written_tables = set()
        self.tokens = {}

    def table(self, name):
        self.tables.setdefault(name, [])
        return Query(self, name)

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params or {}))
        handler = self.rpcs.get(name)
        if handler is None:
            return {}
        return handler(params or {})

    def auth_get_user(self, token):
        return {'id': self.tokens[token]}

    def seed(self, table, rows):
        self.tables.setdefault(table, []).extend(dict(r) for r in rows)
        return self

    def rows(self, table):
        return self.tables.get(table, [])

    def rpc_names(self):
        return [name for name, _ in self.rpc_calls]


def profile(uid, role='student', campus=CAMPUS_A, code=None):
    return {
        'id': uid, 'full_name': uid[:8], 'nickname': None, 'role': role,
        'is_active': True, 'campus_id': campus, 'referral_code': code,
        'referred_by': None,
        'created_at': '2026-10-02T10:00:00+00:00',
    }


def ambassador_tag(uid, campus=CAMPUS_A, status='active'):
    return {
        'id': str(uuid.uuid4()), 'profile_id': uid, 'campus_id': campus,
        'status': status, 'tagged_by': ADMIN_ID, 'untagged_at': None,
    }


class AmbassadorTestBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(FRONTEND_URL='https://holygrills.example',
                               FREE_SIDE_CREDITS_VALIDITY_DAYS=60)
        self.db = MockDB()
        def grant_contract(params):
            if not params['p_override'] and any(row.get('ambassador_id') == params['p_ambassador_id'] and row.get('month') == params['p_month'] and row.get('reward_category') == params['p_category'] and not row.get('duplicate_override') for row in self.db.rows('ambassador_grants')):
                return {'error':'duplicate_monthly_grant'}
            row = {'id':str(uuid.uuid4()), 'ambassador_id':params['p_ambassador_id'],
                   'month':params['p_month'],'reward_category':params['p_category'],
                   'source':params['p_source'],'milestone_claim_id':params['p_claim_id'],
                   'issued_by':params['p_actor_id'],'uses_count':params['p_uses'],
                   'duplicate_override':params['p_override'],'idempotency_key':params['p_intent']}
            self.db.seed('ambassador_grants',[row])
            return row
        self.db.rpcs['hg_issue_ambassador_grant_atomic'] = grant_contract
        # Patches for every module that imported get_db by name.
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(svc, 'get_db', return_value=self.db))
        self.stack.enter_context(patch.object(routes, 'get_db', return_value=self.db))
        self.stack.enter_context(
            patch('app.middleware.auth.get_db', return_value=self.db))
        self.stack.__enter__()

    def tearDown(self):
        self.stack.close()

    def ctx(self, role='admin', campus=CAMPUS_A, user_id=ADMIN_ID):
        ctx = self.app.app_context()
        ctx.push()
        self.addCleanup(ctx.pop)
        g.user_id = user_id
        g.user_role = role
        g.campus_id = campus
        g.user = {'id': user_id, 'role': role, 'campus_id': campus}
        return ctx

    def seed_ambassador(self, uid=AMB, campus=CAMPUS_A, code='HGAMB1'):
        self.db.seed('profiles', [profile(uid, campus=campus, code=code)])
        self.db.seed('ambassadors', [ambassador_tag(uid, campus)])
        return uid


# ---------------------------------------------------------------------------
# 1. Role registration + tag add / remove
# ---------------------------------------------------------------------------
class TagAndRoleTests(AmbassadorTestBase):
    def test_community_manager_is_a_valid_role_but_not_a_financial_admin(self):
        self.assertIn(COMMUNITY_MANAGER_ROLE, VALID_ROLES)
        self.assertNotIn(COMMUNITY_MANAGER_ROLE, ADMIN_ROLES)
        self.assertEqual(ADMIN_ROLES, {'admin', 'super_admin'})

    def test_tag_inserts_then_is_idempotent_then_reactivates(self):
        self.ctx()
        self.db.seed('profiles', [profile(AMB, code='HGAMB1')])
        target = self.db.rows('profiles')[0]

        first = svc.tag_ambassador(ADMIN_ID, target)
        self.assertEqual(first['status'], 'active')
        self.assertEqual(first['profile_id'], AMB)

        # Tagging an active ambassador again must not create a second row.
        again = svc.tag_ambassador(ADMIN_ID, target)
        self.assertTrue(again.get('unchanged'))
        self.assertEqual(len(self.db.rows('ambassadors')), 1)

        # Remove then re-tag flips the same row back to active (no duplicate).
        svc.untag_ambassador(ADMIN_ID, AMB)
        self.assertEqual(self.db.rows('ambassadors')[0]['status'], 'inactive')
        retag = svc.tag_ambassador(ADMIN_ID, target)
        self.assertEqual(retag['status'], 'active')
        self.assertEqual(len(self.db.rows('ambassadors')), 1)
        self.assertIn('admin_audit_logs', self.db.written_tables)

    def test_untag_unknown_ambassador_is_a_404(self):
        self.ctx()
        with self.assertRaises(svc.AmbassadorError) as raised:
            svc.untag_ambassador(ADMIN_ID, AMB)
        self.assertEqual(raised.exception.status, 404)

    def test_tag_route_allows_admin_and_denies_manager_and_student(self):
        self.db.seed('profiles', [
            profile(AMB, campus=CAMPUS_A, code='HGAMB1'),
            profile(ADMIN_ID, role='admin', campus=CAMPUS_A),
            profile(MANAGER_ID, role=COMMUNITY_MANAGER_ROLE, campus=CAMPUS_A),
            profile(STUDENT_ID, role='student', campus=CAMPUS_A),
        ])
        self.db.tokens = {'admin-token': ADMIN_ID, 'manager-token': MANAGER_ID,
                          'student-token': STUDENT_ID}
        app = Flask(__name__)
        app.register_blueprint(routes.ambassadors_bp, url_prefix='/api/ambassadors')
        client = app.test_client()

        ok = client.post('/api/ambassadors/staff/ambassadors',
                         json={'user_id': AMB},
                         headers={'Authorization': 'Bearer admin-token'})
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(self.db.rows('ambassadors')[0]['profile_id'], AMB)

        denied = client.post('/api/ambassadors/staff/ambassadors',
                             json={'user_id': AMB},
                             headers={'Authorization': 'Bearer manager-token'})
        self.assertEqual(denied.status_code, 403)

        student = client.post('/api/ambassadors/staff/ambassadors',
                              json={'user_id': AMB},
                              headers={'Authorization': 'Bearer student-token'})
        self.assertEqual(student.status_code, 403)

    def test_manager_cannot_tag_another_campus_profile(self):
        self.ctx(role='admin', campus=CAMPUS_B)
        self.db.seed('profiles', [profile(AMB, campus=CAMPUS_A)])
        with self.assertRaises(svc.AmbassadorError) as raised:
            # Service-level campus guard reused by every staff route.
            svc.assert_campus_access({'campus_id': CAMPUS_A})
        self.assertEqual(raised.exception.status, 403)
        # The tag route itself rejects the cross-campus body.
        with self.app.test_request_context('/', json={'user_id': AMB}):
            g.user_id = ADMIN_ID
            g.user_role = 'admin'
            g.campus_id = CAMPUS_B
            body, code = inspect.unwrap(routes.staff_tag_ambassador)()
        self.assertEqual(code, 403, body)
        self.assertFalse(self.db.rows('ambassadors'))


# ---------------------------------------------------------------------------
# 2. Financial permission enforcement (defense in depth)
# ---------------------------------------------------------------------------
class FinancialAdminGuardTests(AmbassadorTestBase):
    def test_in_handler_guard_rejects_manager_even_if_decorator_bypassed(self):
        for role in (COMMUNITY_MANAGER_ROLE, 'student', 'kitchen', 'rider'):
            self.ctx(role=role)
            denied = routes._require_financial_admin()
            self.assertIsNotNone(denied)
            self.assertEqual(denied[1], 403)

    def test_financial_admins_pass_the_in_handler_guard(self):
        for role in ('admin', 'super_admin'):
            self.ctx(role=role)
            self.assertIsNone(routes._require_financial_admin())

    def test_grant_milestone_and_decision_routes_403_for_manager(self):
        self.seed_ambassador()
        self.db.seed('profiles', [
            profile(ADMIN_ID, role='admin'),
            profile(MANAGER_ID, role=COMMUNITY_MANAGER_ROLE),
        ])
        self.db.tokens = {'admin-token': ADMIN_ID, 'manager-token': MANAGER_ID}
        app = Flask(__name__)
        app.register_blueprint(routes.ambassadors_bp, url_prefix='/api/ambassadors')
        client = app.test_client()
        manager = {'Authorization': 'Bearer manager-token'}

        grant = client.post('/api/ambassadors/staff/grants',
                            json={'ambassador_id': AMB, 'reward_type': 'hp',
                                  'amount': 50, 'reason': 'review'},
                            headers=manager)
        self.assertEqual(grant.status_code, 403)

        milestone = client.post('/api/ambassadors/staff/milestones',
                                json={'metric': 'orders', 'threshold': 10,
                                      'reward_type': 'hp', 'reward_amount': 50},
                                headers=manager)
        self.assertEqual(milestone.status_code, 403)

        decision = client.post(
            f'/api/ambassadors/staff/reviews/{AMB}/decision',
            json={'decision': 'approved', 'month': MONTH}, headers=manager)
        self.assertEqual(decision.status_code, 403)

        # No financial writes leaked through.
        self.assertNotIn('ambassador_grants', self.db.written_tables)
        self.assertNotIn('ambassador_milestones', self.db.written_tables)

    def test_unwrapped_grant_route_still_denies_manager(self):
        # Even a future decorator regression must not expose the grant writer.
        self.seed_ambassador()
        with self.app.test_request_context(
                '/', json={'ambassador_id': AMB, 'reward_type': 'hp',
                           'amount': 50, 'reason': 'review', 'month': MONTH}):
            g.user_id = MANAGER_ID
            g.user_role = COMMUNITY_MANAGER_ROLE
            g.campus_id = CAMPUS_A
            body, code = inspect.unwrap(routes.staff_create_grant)()
        self.assertEqual(code, 403)
        self.assertNotIn('ambassador_grants', self.db.written_tables)

    def test_manager_keeps_read_and_promo_access(self):
        self.seed_ambassador()
        self.db.seed('profiles', [profile(MANAGER_ID, role=COMMUNITY_MANAGER_ROLE)])
        self.db.tokens = {'manager-token': MANAGER_ID}
        app = Flask(__name__)
        app.register_blueprint(routes.ambassadors_bp, url_prefix='/api/ambassadors')
        client = app.test_client()
        headers = {'Authorization': 'Bearer manager-token'}
        self.assertEqual(client.get(
            '/api/ambassadors/staff/ambassadors', headers=headers).status_code, 200)
        self.assertEqual(client.get(
            '/api/ambassadors/staff/promo-messages', headers=headers).status_code, 200)
        self.assertEqual(client.get(
            '/api/ambassadors/staff/reviews', headers=headers).status_code, 200)


# ---------------------------------------------------------------------------
# 3 + 4. Promo personalization, distribution and manual activity statuses
# ---------------------------------------------------------------------------
class PromoDistributionTests(AmbassadorTestBase):
    def test_caption_personalization_replaces_every_placeholder_form(self):
        link = 'https://holygrills.example?ref=HGAMB1'
        self.assertEqual(
            svc.personalize_caption('Grab a bite {{link}} today', link),
            'Grab a bite https://holygrills.example?ref=HGAMB1 today')
        self.assertEqual(svc.personalize_caption('Use {link}', link),
                         f'Use {link}')
        self.assertEqual(svc.personalize_caption('See {{LINK}} now', link),
                         f'See {link} now')
        self.assertEqual(svc.personalize_caption('No token here', link),
                         'No token here')

    def test_create_promo_requires_caption_and_link_placeholder(self):
        self.ctx()
        self.seed_ambassador()
        actor = {'id': ADMIN_ID, 'role': 'admin', 'campus_id': CAMPUS_A}
        with self.assertRaises(svc.AmbassadorError):
            svc.create_promo_message(self.db, actor, image_url=None, caption='  ',
                                     target_all=True, ambassador_ids=[], month=MONTH)
        with self.assertRaises(svc.AmbassadorError):
            svc.create_promo_message(self.db, actor, image_url=None,
                                     caption='No link in this caption',
                                     target_all=True, ambassador_ids=[], month=MONTH)

    def test_target_all_and_selected_targeting_build_assignments_and_personal_links(self):
        self.ctx()
        self.seed_ambassador(AMB)
        self.db.seed('profiles', [profile(AMB2, campus=CAMPUS_A, code='HGAMB2')])
        self.db.seed('ambassadors', [ambassador_tag(AMB2, CAMPUS_A)])
        actor = {'id': ADMIN_ID, 'role': 'admin', 'campus_id': CAMPUS_A}

        result = svc.create_promo_message(
            self.db, actor, image_url='https://img.example/p.jpg',
            caption='Order with {{link}}', target_all=True,
            ambassador_ids=[], month=MONTH)
        self.assertEqual(result['recipient_count'], 2)
        self.assertEqual(len(self.db.rows('ambassador_promo_assignments')), 2)
        self.assertTrue(all(a['status'] == 'pending'
                            for a in self.db.rows('ambassador_promo_assignments')))
        message_id = result['message']['id']

        # Per-ambassador personalization for the Share action.
        assignments = svc.promo_assignments(self.db, message_id)
        links = {a['ambassador_id']:
                 svc.personalize_caption('Order with {{link}}',
                                         f"https://holygrills.example?ref={a['profile']['referral_code']}")
                 for a in assignments}
        self.assertIn('ref=HGAMB1', links[AMB])
        self.assertIn('ref=HGAMB2', links[AMB2])

        # Selected targeting on a second message only hits the chosen ambassador.
        picked = svc.create_promo_message(
            self.db, actor, image_url=None, caption='Try {link}',
            target_all=False, ambassador_ids=[AMB2], month=MONTH)
        self.assertEqual(picked['recipient_count'], 1)
        self.assertEqual(picked['ambassador_ids'], [AMB2])

    def test_campus_manager_distribution_never_leaves_their_campus(self):
        self.ctx(role=COMMUNITY_MANAGER_ROLE, campus=CAMPUS_A)
        self.seed_ambassador(AMB, CAMPUS_A, 'HGA')
        self.db.seed('profiles', [profile(AMB2, campus=CAMPUS_B, code='HGB')])
        self.db.seed('ambassadors', [ambassador_tag(AMB2, CAMPUS_B)])
        actor = {'id': MANAGER_ID, 'role': COMMUNITY_MANAGER_ROLE,
                 'campus_id': CAMPUS_A}
        result = svc.create_promo_message(
            self.db, actor, image_url=None, caption='See {{link}}',
            target_all=True, ambassador_ids=[], month=MONTH)
        self.assertEqual(result['recipient_count'], 1)
        self.assertEqual(result['ambassador_ids'], [AMB])

    def test_manual_status_transitions_and_invalid_status_rejected(self):
        self.ctx()
        self.seed_ambassador()
        actor = {'id': ADMIN_ID, 'role': 'admin', 'campus_id': CAMPUS_A}
        svc.create_promo_message(
            self.db, actor, image_url=None, caption='Go {{link}}',
            target_all=True, ambassador_ids=[], month=MONTH)
        assignment_id = self.db.rows('ambassador_promo_assignments')[0]['id']

        for status in ('seen', 'shared'):
            row = svc.set_assignment_status(
                self.db, ADMIN_ID, assignment_id, status, 'manual note')
            self.assertEqual(row['status'], status)
        with self.assertRaises(svc.AmbassadorError):
            svc.set_assignment_status(self.db, ADMIN_ID, assignment_id,
                                      'auto_read_receipt', None)
        with self.assertRaises(svc.AmbassadorError) as raised:
            svc.set_assignment_status(self.db, ADMIN_ID, str(uuid.uuid4()),
                                      'shared', None)
        self.assertEqual(raised.exception.status, 404)

    def test_completion_rate_seven_of_ten_is_seventy_percent(self):
        self.ctx()
        self.seed_ambassador()
        assignments = [{'id': str(uuid.uuid4()), 'ambassador_id': AMB,
                        'message_id': str(uuid.uuid4()), 'month': MONTH,
                        'status': 'shared' if i < 7 else
                        ('seen' if i < 9 else 'pending')}
                       for i in range(10)]
        self.db.seed('ambassador_promo_assignments', assignments)
        metrics = svc.assignment_metrics(self.db, AMB, MONTH)
        self.assertEqual(metrics['assigned_count'], 10)
        self.assertEqual(metrics['shared_count'], 7)
        self.assertEqual(metrics['seen_count'], 9)  # seen includes shared
        self.assertEqual(metrics['completion_rate'], 70.0)
        # 4 shares/week expectation scaled to the month's weeks.
        self.assertEqual(metrics['weekly_share_target'], 4)
        self.assertGreaterEqual(metrics['monthly_share_target'], 16)
        self.assertGreater(metrics['share_target_progress'], 0)

    def test_no_assignments_yields_zero_rate_not_a_divide_by_zero(self):
        self.ctx()
        self.seed_ambassador()
        metrics = svc.assignment_metrics(self.db, AMB, MONTH)
        self.assertEqual(metrics['completion_rate'], 0.0)
        self.assertEqual(metrics['share_target_progress'], 0.0)


# ---------------------------------------------------------------------------
# 5 + 6 + 7. Click attribution: guests, existing customers, last-click,
#             and the referral tables staying untouched
# ---------------------------------------------------------------------------
class ClickAttributionTests(AmbassadorTestBase):
    def test_guest_click_is_persisted_with_an_anonymous_id(self):
        self.ctx(role=None, campus=None)
        result = svc.record_click('HGAMB1', anonymous_id='anon-123')
        name, params = self.db.rpc_calls[-1]
        self.assertEqual(name, 'hg_ambassador_record_click')
        self.assertEqual(params['p_ref_code'], 'HGAMB1')
        self.assertEqual(params['p_anonymous_id'], 'anon-123')
        self.assertIsNone(params['p_visitor_user_id'])
        self.assertIsInstance(result, dict)

    def test_logged_in_existing_customer_click_carries_user_id(self):
        self.ctx(role='student', campus=CAMPUS_A, user_id=STUDENT_ID)
        svc.record_click('HGAMB1', anonymous_id='anon-123',
                         visitor_user_id=STUDENT_ID, campus_id=CAMPUS_A)
        _, params = self.db.rpc_calls[-1]
        self.assertEqual(params['p_visitor_user_id'], STUDENT_ID)
        self.assertEqual(params['p_campus_id'], CAMPUS_A)

    def test_blank_code_short_circuits_without_an_rpc(self):
        result = svc.record_click('   ')
        self.assertFalse(result['attributed'])
        self.assertEqual(self.db.rpc_calls, [])

    def test_visitor_merge_on_later_login_uses_merge_rpc(self):
        svc.merge_visitor('anon-123', STUDENT_ID)
        name, params = self.db.rpc_calls[-1]
        self.assertEqual(name, 'hg_ambassador_merge_visitor')
        self.assertEqual(params, {'p_anonymous_id': 'anon-123',
                                  'p_user_id': STUDENT_ID})

    def test_track_click_route_works_for_guests_and_returns_stable_anon_id(self):
        app = Flask(__name__)
        app.register_blueprint(routes.ambassadors_bp, url_prefix='/api/ambassadors')
        client = app.test_client()
        resp = client.post('/api/ambassadors/track-click',
                           json={'ref_code': 'HGAMB1', 'anonymous_id': 'anon-xyz'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['anonymous_id'], 'anon-xyz')

        # Missing code is a clean 400, not a server error.
        bad = client.post('/api/ambassadors/track-click', json={})
        self.assertEqual(bad.status_code, 400)

    def test_last_click_replacement_and_seven_day_window_are_in_sql(self):
        # Scenario 6 (A -> B): the UPSERT replaces the ambassador on a newer
        # click and slides the window forward from the LATEST click.
        self.assertIn('ON CONFLICT (customer_user_id) DO UPDATE', TRACKING_SQL)
        self.assertIn(
            'WHEN EXCLUDED.last_click_at > att.last_click_at '
            'THEN EXCLUDED.ambassador_id', TRACKING_SQL)
        self.assertIn('make_interval(days => v_window)', TRACKING_SQL)
        # The configurable window defaults to seven days (settings seed).
        self.assertIn("'ambassador_attribution_window_days'", SETTINGS_SQL)
        self.assertRegex(SETTINGS_SQL,
                         r"ambassador_attribution_window_days'[\s\S]{0,40}'7'")
        # Order attribution must require a live window and honour last click.
        self.assertIn('att.expires_at >= v_order.created_at', TRACKING_SQL)
        self.assertIn('ORDER BY att.last_click_at DESC', TRACKING_SQL)

    def test_attribution_flows_never_write_referral_tables(self):
        self.ctx()
        self.seed_ambassador()
        # A click, a promo round, a milestone evaluation, and dashboard read.
        svc.record_click('HGAMB1', anonymous_id='anon-1', visitor_user_id=STUDENT_ID)
        svc.merge_visitor('anon-1', STUDENT_ID)
        actor = {'id': ADMIN_ID, 'role': 'admin', 'campus_id': CAMPUS_A}
        svc.create_promo_message(self.db, actor, image_url=None,
                                 caption='Share {{link}}', target_all=True,
                                 ambassador_ids=[], month=MONTH)
        self.db.seed('ambassador_milestones', [{
            'id': 'ms-1', 'campus_id': None, 'metric': 'orders', 'threshold': 1,
            'reward_type': 'hp', 'reward_amount': 10, 'reward_uses': 1,
            'validity_days': 14, 'auto_issue': False, 'is_active': True}])
        svc.evaluate_milestones(self.db, AMB, MONTH)
        svc.ambassador_dashboard(self.db, AMB, 'https://holygrills.example')

        self.assertNotIn('referrals', self.db.written_tables)
        # profiles rows are only ever read; referred_by stays exactly as seeded.
        self.assertNotIn('profiles', self.db.written_tables)
        self.assertIsNone(self.db.rows('profiles')[0]['referred_by'])

    def test_order_attribution_and_reversal_are_thin_idempotent_rpc_wrappers(self):
        svc.attribute_delivered_order('order-1')
        self.assertEqual(self.db.rpc_calls[-1][0],
                         'hg_ambassador_attribute_order')
        self.assertEqual(self.db.rpc_calls[-1][1], {'p_order_id': 'order-1'})

        # An RPC failure must never break the order status transition.
        def boom(_):
            raise RuntimeError('supabase down')
        self.db.rpcs['hg_ambassador_attribute_order'] = boom
        self.assertEqual(svc.attribute_delivered_order('order-2'),
                         {'attributed': False, 'error': 'attribution_failed'})

        del self.db.rpcs['hg_ambassador_attribute_order']
        svc.reverse_attributed_order('order-1', 'order_refunded')
        name, params = self.db.rpc_calls[-1]
        self.assertEqual(name, 'hg_ambassador_reverse_order')
        self.assertEqual(params['p_reason'], 'order_refunded')

    def test_delivery_and_refund_eligibility_rules_are_in_sql(self):
        # Scenario 8: delivered AND not fully refunded; unique per order.
        self.assertIn("v_order.status <> 'delivered'", TRACKING_SQL)
        self.assertIn("COALESCE(v_order.payment_status, '') = 'refunded'",
                      TRACKING_SQL)
        self.assertIn('ON CONFLICT (order_id) DO UPDATE', TRACKING_SQL)
        # Full refund / cancellation flips eligibility; partial refunds stay.
        self.assertIn("SET eligibility = 'excluded'", TRACKING_SQL)
        # The primary key itself makes a double-count impossible.
        self.assertIn('order_id          uuid PRIMARY KEY REFERENCES public.orders',
                      SCHEMA_SQL)
        # Reversal is idempotent (only eligible rows move).
        self.assertIn(
            'WHERE order_id = p_order_id AND eligibility =', TRACKING_SQL)

    def test_order_lifecycle_hooks_are_wired_into_existing_services(self):
        # Scenario 8/14: the existing order pipeline, not a parallel engine,
        # drives attribution and meal-discount redemption/restoration.
        order_service = inspect.getsource(
            __import__('app.services.order_service', fromlist=['x']))
        orders_route = inspect.getsource(
            __import__('app.routes.orders', fromlist=['x']))
        self.assertIn('resolve_discount_for_checkout', order_service)
        self.assertIn('compute_discount_amount', order_service)
        self.assertIn("['_ambassador_meal_discount']", order_service)
        self.assertIn('restore_discount_for_order', order_service)
        self.assertIn('attribute_delivered_order', order_service)
        self.assertIn('reverse_attributed_order', orders_route)


# ---------------------------------------------------------------------------
# 9/10. Milestone evaluation and claim dedupe
# ---------------------------------------------------------------------------
class MilestoneTests(AmbassadorTestBase):
    def _milestone(self, ms_id='ms-1', metric='orders', threshold=3):
        return {'id': ms_id, 'campus_id': None, 'metric': metric,
                'threshold': threshold, 'reward_type': 'meal_discount',
                'reward_amount': 3000, 'reward_uses': 1, 'validity_days': 14,
                'auto_issue': False, 'is_active': True}

    def test_reaching_threshold_creates_one_pending_claim_ever(self):
        self.ctx()
        self.seed_ambassador()
        self.db.seed('ambassador_milestones', [self._milestone()])
        # Three attributed eligible orders this month satisfy threshold 3.
        self.db.seed('ambassador_order_attributions', [
            {'order_id': f'ord-{i}', 'ambassador_id': AMB,
             'eligibility': 'eligible',
             'order_total': 4000,
             'attributed_at': f'2026-10-0{i+1}T10:00:00+00:00'}
            for i in range(3)])

        first = svc.evaluate_milestones(self.db, AMB, MONTH)
        self.assertTrue(first[0]['reached'])
        self.assertEqual(first[0]['claim']['status'], 'pending_approval')
        # Re-evaluation (review page reload, monthly sweep) must not duplicate.
        second = svc.evaluate_milestones(self.db, AMB, MONTH)
        self.assertEqual(len(self.db.rows('ambassador_milestone_claims')), 1)
        self.assertEqual(second[0]['claim']['id'], first[0]['claim']['id'])
        # The SQL unique constraint is the hard backstop.
        self.assertIn('UNIQUE (milestone_id, ambassador_id, period_month)',
                      SCHEMA_SQL)

    def test_below_threshold_creates_no_claim(self):
        self.ctx()
        self.seed_ambassador()
        self.db.seed('ambassador_milestones',
                     [self._milestone(metric='signups', threshold=5)])
        out = svc.evaluate_milestones(self.db, AMB, MONTH)
        self.assertFalse(out[0]['reached'])
        self.assertIsNone(out[0]['claim'])
        self.assertEqual(self.db.rows('ambassador_milestone_claims'), [])

    def test_invalid_month_is_rejected(self):
        self.ctx()
        self.seed_ambassador()
        with self.assertRaises(svc.AmbassadorError):
            svc.evaluate_milestones(self.db, AMB, 'not-a-month')


class AutoIssueMilestoneTests(AmbassadorTestBase):
    """auto_issue milestones grant their reward without an admin clicking
    anything — but only via a real configured admin profile, and never at the
    expense of the duplicate guard or dashboard stability."""

    def _auto_milestone(self, **over):
        row = {'id': 'ms-auto', 'campus_id': None, 'metric': 'orders',
               'threshold': 1, 'reward_type': 'meal_discount',
               'reward_amount': 3000, 'reward_uses': 2, 'validity_days': 14,
               'auto_issue': True, 'is_active': True}
        row.update(over)
        return row

    def _seed_reached(self, milestone):
        self.seed_ambassador()
        self.db.seed('ambassador_milestones', [milestone])
        self.db.seed('ambassador_order_attributions', [{
            'order_id': 'ord-1', 'ambassador_id': AMB, 'eligibility': 'eligible',
            'order_total': 4000,
            'attributed_at': '2026-10-01T10:00:00+00:00'}])

    def test_auto_milestone_grants_immediately_and_links_claim_to_grant(self):
        self.ctx()
        self.app.config['AMBASSADOR_SYSTEM_ACTOR_ID'] = ADMIN_ID
        self.db.seed('profiles', [profile(ADMIN_ID, role='admin')])
        self._seed_reached(self._auto_milestone())
        self.db.rpcs['hg_grant_ambassador_meal_discount'] = (
            lambda p: {'id': 'disc-auto', **p})
        with patch('app.utils.settings.setting_or_config', return_value=14):
            out = svc.evaluate_milestones(self.db, AMB, MONTH)

        claim = out[0]['claim']
        self.assertEqual(claim['status'], 'issued')
        grant = self.db.rows('ambassador_grants')[0]
        self.assertEqual(claim['grant_id'], grant['id'])
        self.assertEqual(grant['source'], 'milestone')
        self.assertEqual(grant['milestone_claim_id'], claim['id'])
        self.assertEqual(grant['issued_by'], ADMIN_ID)
        self.assertEqual(grant['uses_count'], 2)
        # Re-evaluation must not double-issue: the claim already exists.
        with patch('app.utils.settings.setting_or_config', return_value=14):
            svc.evaluate_milestones(self.db, AMB, MONTH)
        self.assertEqual(len(self.db.rows('ambassador_grants')), 1)
        self.assertEqual(len(self.db.rows('ambassador_milestone_claims')), 1)

    def test_auto_milestone_without_system_actor_stays_manual_pending(self):
        self.ctx()  # AMBASSADOR_SYSTEM_ACTOR_ID unset
        self._seed_reached(self._auto_milestone())
        out = svc.evaluate_milestones(self.db, AMB, MONTH)
        self.assertEqual(out[0]['claim']['status'], 'pending_approval')
        self.assertEqual(self.db.rows('ambassador_grants'), [])
        self.assertNotIn('hg_grant_ambassador_meal_discount',
                         self.db.rpc_names())

    def test_unknown_or_non_admin_system_actor_disables_auto_issue(self):
        self.ctx()
        self.app.config['AMBASSADOR_SYSTEM_ACTOR_ID'] = STUDENT_ID
        self.db.seed('profiles', [profile(STUDENT_ID, role='student')])
        self._seed_reached(self._auto_milestone())
        out = svc.evaluate_milestones(self.db, AMB, MONTH)
        self.assertEqual(out[0]['claim']['status'], 'pending_approval')
        self.assertEqual(self.db.rows('ambassador_grants'), [])

    def test_existing_monthly_grant_makes_auto_issue_degrade_to_pending(self):
        self.ctx()
        self.app.config['AMBASSADOR_SYSTEM_ACTOR_ID'] = ADMIN_ID
        self.db.seed('profiles', [profile(ADMIN_ID, role='admin')])
        self._seed_reached(self._auto_milestone())
        # A manual meal_discount grant already exists for this month/category.
        self.db.seed('ambassador_grants', [{
            'id': 'grant-existing', 'ambassador_id': AMB, 'month': MONTH,
            'reward_category': 'meal_discount', 'amount': 3000,
            'duplicate_override': False, 'reason': 'manual review reward'}])
        out = svc.evaluate_milestones(self.db, AMB, MONTH)
        self.assertEqual(out[0]['claim']['status'], 'pending_approval')
        # No second grant row and no reward RPC attempted.
        self.assertEqual(len(self.db.rows('ambassador_grants')), 1)
        self.assertNotIn('hg_grant_ambassador_meal_discount',
                         self.db.rpc_names())

    def test_hp_auto_milestone_uses_existing_award_service(self):
        self.ctx()
        self.app.config['AMBASSADOR_SYSTEM_ACTOR_ID'] = ADMIN_ID
        self.db.seed('profiles', [profile(ADMIN_ID, role='super_admin')])
        self._seed_reached(self._auto_milestone(
            reward_type='hp', reward_amount=25, reward_uses=1))
        out = svc.evaluate_milestones(self.db, AMB, MONTH)
        self.assertEqual(out[0]['claim']['status'], 'issued')
        params = next(params for name,params in self.db.rpc_calls if name=='hg_issue_ambassador_grant_atomic')
        self.assertEqual(params['p_amount'],25)
        self.assertEqual(params['p_category'],'hp')



# ---------------------------------------------------------------------------
# 11/13. Grants: HP, free sides, meal discounts, dedupe, recurring grants
# ---------------------------------------------------------------------------
class GrantTests(AmbassadorTestBase):
    def _actor(self): return {'id':ADMIN_ID,'role':'admin','campus_id':CAMPUS_A}

    def test_three_categories_pass_one_atomic_contract(self):
        for category,amount in [('hp',50),('free_side',2),('meal_discount',3000)]:
            with self.subTest(category=category):
                self.ctx();self.seed_ambassador()
                grant=svc.issue_grant(self.db,self._actor(),ambassador_id=AMB,category=category,
                    amount=amount,reason='October review',month=MONTH)
                name,params=self.db.rpc_calls[-1]
                self.assertEqual(name,'hg_issue_ambassador_grant_atomic')
                self.assertEqual(params['p_category'],category)
                self.assertEqual(params['p_amount'],amount)
                self.assertEqual(params['p_actor_id'],ADMIN_ID)
                self.assertTrue(grant['id'])
                self.assertNotIn('wallet_transactions',self.db.written_tables)

    def test_failed_atomic_response_never_records_a_local_grant(self):
        self.ctx();self.seed_ambassador()
        self.db.rpcs['hg_issue_ambassador_grant_atomic']=lambda _: {'error':'unavailable'}
        with self.assertRaises(svc.AmbassadorError):
            svc.issue_grant(self.db,self._actor(),ambassador_id=AMB,category='free_side',amount=1,reason='test',month=MONTH)
        self.assertEqual(self.db.rows('ambassador_grants'),[])

    def test_duplicate_month_category_grant_is_409_until_explicit_override(self):
        self.ctx();self.seed_ambassador()
        kwargs=dict(ambassador_id=AMB,category='meal_discount',amount=3000,reason='first',month=MONTH)
        svc.issue_grant(self.db,self._actor(),**kwargs)
        with self.assertRaises(svc.DuplicateGrant):svc.issue_grant(self.db,self._actor(),**kwargs)
        extra=svc.issue_grant(self.db,self._actor(),**{**kwargs,'reason':'second'},override=True)
        self.assertTrue(extra['duplicate_override'])

    def test_issued_replay_does_not_send_another_notification(self):
        self.ctx();self.seed_ambassador()
        self.db.rpcs['hg_issue_ambassador_grant_atomic']=lambda _: {'id':'receipt','idempotent':True}
        with patch('app.services.notification_service.send_notification') as notify:
            svc.issue_grant(self.db,self._actor(),ambassador_id=AMB,category='hp',amount=50,reason='test',month=MONTH)
            notify.assert_not_called()

    def test_unsafe_amounts_never_reach_award_rpc(self):
        self.ctx();self.seed_ambassador()
        for amount in (float('nan'),float('inf'),0,-1,0.5):
            with self.subTest(amount=amount),self.assertRaises(svc.AmbassadorError):
                svc.issue_grant(self.db,self._actor(),ambassador_id=AMB,category='hp',amount=amount,reason='test',month=MONTH)
        self.assertNotIn('hg_issue_ambassador_grant_atomic',self.db.rpc_names())

    def test_recurring_override_includes_terms_in_intent(self):
        self.ctx();self.seed_ambassador()
        kwargs=dict(ambassador_id=AMB,category='meal_discount',amount=3000,month=MONTH,override=True)
        one=svc.issue_grant(self.db,self._actor(),reason='biweekly one',**kwargs)
        two=svc.issue_grant(self.db,self._actor(),reason='biweekly two',**kwargs)
        self.assertNotEqual(one['idempotency_key'],two['idempotency_key'])

    def test_grant_route_returns_409_body_with_duplicate_code(self):
        self.db.rpcs['hg_issue_ambassador_grant_atomic']=lambda _: {'error':'duplicate_monthly_grant'}
        self.seed_ambassador()
        with self.app.test_request_context('/',json={'ambassador_id':AMB,'reward_type':'hp','amount':50,'reason':'test','month':MONTH}):
            g.user_id,g.user_role,g.campus_id=ADMIN_ID,'admin',CAMPUS_A
            body,code=inspect.unwrap(routes.staff_create_grant)()
            self.assertEqual(code,409);self.assertEqual(body.json['code'],'DUPLICATE_MONTHLY_GRANT')


# ---------------------------------------------------------------------------
# 12. Meal discounts at checkout — math, validation, redemption, restore
# ---------------------------------------------------------------------------
class MealDiscountCheckoutTests(AmbassadorTestBase):
    def discount(self, **over):
        row = {
            'id': 'disc-1', 'ambassador_id': AMB, 'code': 'MEAL-1',
            'status': 'active', 'max_meal_value': 3000,
            'uses_total': 2, 'uses_remaining': 2,
            'expires_at': '2026-11-10T23:59:59+00:00',
        }
        row.update(over)
        return row

    def items(self, *prices):
        return [{'menu_item_id': f'item-{i}', 'price_snapshot': p}
                for i, p in enumerate(prices)]

    def test_resolve_rejects_foreign_expired_voided_and_spent_discounts(self):
        self.ctx()
        self.db.seed('ambassador_meal_discounts', [self.discount()])
        ok = svc.resolve_discount_for_checkout(self.db, AMB, 'disc-1')
        self.assertEqual(ok['id'], 'disc-1')

        with self.assertRaises(svc.AmbassadorError) as raised:
            svc.resolve_discount_for_checkout(self.db, AMB2, 'disc-1')
        self.assertEqual(raised.exception.status, 404)

        self.db.tables['ambassador_meal_discounts'][0]['status'] = 'voided'
        with self.assertRaises(svc.AmbassadorError):
            svc.resolve_discount_for_checkout(self.db, AMB, 'disc-1')

        self.db.tables['ambassador_meal_discounts'][0].update(
            {'status': 'active', 'uses_remaining': 0})
        with self.assertRaises(svc.AmbassadorError):
            svc.resolve_discount_for_checkout(self.db, AMB, 'disc-1')

        self.db.tables['ambassador_meal_discounts'][0].update(
            {'uses_remaining': 2, 'status': 'expired'})
        with self.assertRaises(svc.AmbassadorError):
            svc.resolve_discount_for_checkout(self.db, AMB, 'disc-1')

    def test_discount_covers_one_meal_up_to_the_cap(self):
        d = self.discount()
        # Piciest meal below the cap: the meal is fully covered.
        amount = svc.compute_discount_amount(
            d, self.items(2500, 1200), Decimal('3700'), Decimal('0'))
        self.assertEqual(amount, Decimal('2500.00'))
        # Piciest meal above the cap: the cap wins.
        amount = svc.compute_discount_amount(
            d, self.items(4500, 1200), Decimal('5700'), Decimal('0'))
        self.assertEqual(amount, Decimal('3000.00'))

    def test_discount_respects_existing_food_discount_headroom(self):
        d = self.discount(max_meal_value=3000)
        # Another food discount already removed most of the subtotal: never
        # push the food total below zero.
        amount = svc.compute_discount_amount(
            d, self.items(3000, 2000), Decimal('5000'), Decimal('4500'))
        self.assertEqual(amount, Decimal('500.00'))
        # Fully discounted basket contributes nothing more.
        amount = svc.compute_discount_amount(
            d, self.items(3000), Decimal('3000'), Decimal('3000'))
        self.assertEqual(amount, Decimal('0.00'))

    def test_delivery_fee_is_never_part_of_the_discount(self):
        # The function signature only receives food subtotal and food
        # discounts — delivery is priced separately and stays payable.
        sig = inspect.signature(svc.compute_discount_amount)
        self.assertNotIn('delivery_fee', sig.parameters)
        order_service = inspect.getsource(
            __import__('app.services.order_service', fromlist=['x']))
        self.assertIn('total_dec = (subtotal_dec-total_discount_dec+delivery_fee_dec)',
                      order_service)

    def test_redeem_consumes_a_use_and_restore_returns_it(self):
        self.ctx()
        svc.redeem_discount(self.db, 'disc-1', 'order-9', AMB,
                            Decimal('2500.00'), 'item-0')
        name, params = self.db.rpc_calls[-1]
        self.assertEqual(name, 'hg_redeem_ambassador_meal_discount')
        self.assertEqual(params['p_discount_id'], 'disc-1')
        self.assertEqual(params['p_order_id'], 'order-9')
        self.assertEqual(params['p_amount'], 2500.0)
        self.assertEqual(params['p_meal_item_id'], 'item-0')

        self.db.rpcs['hg_redeem_ambassador_meal_discount'] = (
            lambda _: {'error': 'already redeemed'})
        with self.assertRaises(svc.AmbassadorError):
            svc.redeem_discount(self.db, 'disc-1', 'order-10', AMB,
                                Decimal('10'), None)

        svc.restore_discount_for_order(self.db, 'order-9')
        self.assertEqual(self.db.rpc_calls[-1][0],
                         'hg_restore_ambassador_meal_discount')
        # SQL: restore never exceeds the original total and targets one order.
        self.assertIn('LEAST(uses_total, uses_remaining + 1)', REWARD_SQL)
        self.assertIn('p_order_id', REWARD_SQL)

    def test_reward_rpcs_are_locked_to_service_role(self):
        # No anon/authenticated direct invocation — the API is the only path.
        for rpc in ('hg_grant_ambassador_meal_discount',
                    'hg_redeem_ambassador_meal_discount',
                    'hg_restore_ambassador_meal_discount',
                    'hg_expire_ambassador_discounts'):
            self.assertRegex(
                REWARD_SQL,
                rf'REVOKE ALL ON FUNCTION public\.{rpc}[^;]*FROM PUBLIC')

    def test_my_discounts_are_scoped_to_the_ambassador_and_sorted(self):
        self.ctx()
        self.db.seed('ambassador_meal_discounts', [
            self.discount(id='d-1', ambassador_id=AMB,
                          expires_at='2026-11-01T00:00:00+00:00'),
            self.discount(id='d-2', ambassador_id=AMB2,
                          expires_at='2026-11-02T00:00:00+00:00'),
        ])
        rows = svc.list_my_discounts(self.db, AMB)
        self.assertEqual([r['id'] for r in rows], ['d-1'])
        # The expiry sweep runs on every read.
        self.assertIn('hg_expire_ambassador_discounts', self.db.rpc_names())


# ---------------------------------------------------------------------------
# Dashboard + monthly review payloads
# ---------------------------------------------------------------------------
class DashboardAndReviewTests(AmbassadorTestBase):
    def test_dashboard_is_none_for_non_ambassadors(self):
        self.ctx()
        self.db.seed('profiles', [profile(STUDENT_ID, code='HGSTU')])
        self.assertIsNone(
            svc.ambassador_dashboard(self.db, STUDENT_ID,
                                     'https://holygrills.example'))

    def test_dashboard_payload_keeps_referral_hp_read_only(self):
        self.ctx()
        self.seed_ambassador()
        self.db.seed('referrals', [
            {'referrer_id': AMB, 'hp_awarded': 75, 'status': 'paid'},
            {'referrer_id': AMB, 'hp_awarded': 25, 'status': 'paid'},
        ])
        payload = svc.ambassador_dashboard(
            self.db, AMB, 'https://holygrills.example')
        self.assertTrue(payload['is_ambassador'])
        self.assertEqual(payload['referral_code'], 'HGAMB1')
        self.assertEqual(payload['tracking_link'],
                         'https://holygrills.example?ref=HGAMB1')
        self.assertEqual(payload['referral_hp_earned'], 100)
        self.assertIn('meal_discounts', payload)
        self.assertIn('month_activity', payload)
        # referrals is read-only here.
        self.assertNotIn('referrals', self.db.written_tables)

    def test_monthly_review_persists_metrics_and_carries_recommendation_then_decision(self):
        self.ctx()
        self.seed_ambassador()
        self.db.seed('ambassador_promo_assignments', [
            {'id': str(uuid.uuid4()), 'ambassador_id': AMB, 'month': MONTH,
             'status': 'shared'}])
        data = svc.persist_review_metrics(self.db, AMB, MONTH)
        self.assertEqual(data['shared_count'], 1)
        self.assertEqual(data['orders_count'], 0)

        review = svc.submit_recommendation(
            self.db, MANAGER_ID, AMB, MONTH, 'recommend', 'Strong month')
        self.assertEqual(review['recommendation'], 'recommend')
        with self.assertRaises(svc.AmbassadorError):
            svc.submit_recommendation(self.db, MANAGER_ID, AMB, MONTH,
                                      'maybe', None)

        decided = svc.record_decision(
            self.db, ADMIN_ID, AMB, MONTH, 'approved', 'Issue reward')
        self.assertEqual(decided['decision'], 'approved')
        with self.assertRaises(svc.AmbassadorError):
            svc.record_decision(self.db, ADMIN_ID, AMB, MONTH, 'unsure', None)
        # One review row, upserted — not one per action.
        self.assertEqual(len(self.db.rows('ambassador_monthly_reviews')), 1)

    def test_me_route_uses_the_service_client_scoped_to_the_jwt_user(self):
        # RLS gives authenticated users SELECT only; the dashboard also reads
        # staff-only tables and may write claims/grants, so the route must use
        # the service client while hard-scoping every row to g.user_id.
        captured = {}

        def fake_dashboard(db, user_id, frontend_url):
            captured.update(db=db, user_id=user_id)
            return {'is_ambassador': True}

        with self.app.test_request_context('/'):
            g.user_id = STUDENT_ID
            g.user_role = 'student'
            with patch.object(svc, 'ambassador_dashboard', side_effect=fake_dashboard):
                body, code = inspect.unwrap(routes.my_ambassador_programme)()
        self.assertEqual(code, 200, body)
        self.assertEqual(captured['user_id'], STUDENT_ID)
        self.assertIs(captured['db'], self.db)

    def test_meal_discounts_route_uses_service_client_and_jwt_scope(self):
        with self.app.test_request_context('/'):
            g.user_id = STUDENT_ID
            with patch.object(svc, 'list_my_discounts', return_value=[]) as mocked:
                body, code = inspect.unwrap(routes.my_meal_discounts)()
        self.assertEqual(code, 200, body)
        self.assertEqual(mocked.call_args.args, (self.db, STUDENT_ID))

    def test_activity_alone_never_issues_a_grant(self):
        self.ctx()
        self.seed_ambassador()
        self.db.seed('ambassador_promo_assignments', [
            {'id': str(uuid.uuid4()), 'ambassador_id': AMB, 'month': MONTH,
             'status': 'shared'} for _ in range(10)])
        svc.persist_review_metrics(self.db, AMB, MONTH)
        svc.submit_recommendation(self.db, MANAGER_ID, AMB, MONTH,
                                  'recommend', None)
        self.assertEqual(self.db.rows('ambassador_grants'), [])
        self.assertNotIn('hg_grant_ambassador_meal_discount',
                         self.db.rpc_names())


# ---------------------------------------------------------------------------
# 14. Migration-level regression / security contract
# ---------------------------------------------------------------------------
class MigrationContractTests(unittest.TestCase):
    def test_all_four_migrations_are_versioned_and_ordered(self):
        names = sorted(p.name for p in MIGRATIONS.glob('20261028084*_ambassador_*.sql'))
        self.assertEqual(names, [
            '20261028084136_ambassador_programme_schema.sql',
            '20261028084144_ambassador_tracking_rpcs.sql',
            '20261028084202_ambassador_reward_rpcs.sql',
            '20261028084221_ambassador_programme_settings.sql',
        ])

    def test_rls_is_enabled_and_ambassador_tables_exist(self):
        for table in ('ambassadors', 'ambassador_link_clicks',
                      'ambassador_attributions', 'ambassador_order_attributions',
                      'ambassador_promo_messages', 'ambassador_promo_assignments',
                      'ambassador_milestones', 'ambassador_milestone_claims',
                      'ambassador_monthly_reviews', 'ambassador_grants',
                      'ambassador_meal_discounts'):
            self.assertIn(f'CREATE TABLE IF NOT EXISTS public.{table}', SCHEMA_SQL)
        self.assertIn('ENABLE ROW LEVEL SECURITY', SCHEMA_SQL)

    def test_settings_seed_contains_window_share_and_discount_defaults(self):
        for key in ('ambassador_attribution_window_days',
                    'ambassador_expected_weekly_shares',
                    'ambassador_meal_discount_default_max',
                    'ambassador_meal_discount_default_validity'):
            self.assertIn(f"'{key}'", SETTINGS_SQL)

    def test_blueprint_registers_all_twenty_routes(self):
        app = Flask(__name__)
        app.register_blueprint(routes.ambassadors_bp, url_prefix='/api/ambassadors')
        rules = [r.rule for r in app.url_map.iter_rules()
                 if r.endpoint.startswith('ambassadors.')]
        self.assertEqual(len(rules), 20)
        self.assertIn('/api/ambassadors/track-click', rules)
        self.assertIn('/api/ambassadors/me', rules)

    def test_module_does_not_import_wallet_or_referral_write_services(self):
        source = inspect.getsource(svc)
        # Strip the module docstring/comments: those legitimately *describe*
        # the non-goals (e.g. "never rewrites referred_by"); the executable
        # code below must never actually perform those writes.
        code_lines = [
            line for line in source.splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]
        code = '\n'.join(line for line in code_lines
                         if not line.strip().startswith(('"""', "'''")))
        # No parallel wallet, no profile/referral mutation path.
        self.assertNotIn('wallet_service', code)
        self.assertNotIn('.table("wallet', code)
        self.assertNotIn('"referred_by"', code)
        self.assertNotIn('.table("referrals").insert', code)
        self.assertNotIn('.table("referrals").update', code)
        # Reward issuance is funnelled through the existing services.
        self.assertIn('hg_issue_ambassador_grant_atomic', code)


if __name__ == '__main__':
    unittest.main()

class ProgrammeRegressionTests(AmbassadorTestBase):
    def test_campus_admin_cannot_patch_global_or_other_campus_rule(self):
        rule='99999999-9999-4999-8999-999999999999'
        for campus in (None,CAMPUS_B):
            self.db.tables['ambassador_milestones']=[{'id':rule,'campus_id':campus}]
            with self.app.test_request_context('/',method='PATCH',json={'is_active':False}):
                g.user_id,g.user_role,g.campus_id=ADMIN_ID,'admin',CAMPUS_A
                response,status=inspect.unwrap(routes.staff_update_milestone)(rule)
                self.assertEqual(status,403)
                self.assertNotIn('ambassador_milestones',self.db.written_tables)

    def test_malformed_rule_values_are_not_coerced_into_rewards(self):
        base={'metric':'orders','threshold':2,'reward_type':'free_side','reward_amount':1}
        for change in ({'threshold':True},{'threshold':1.5},{'auto_issue':'false'},
                       {'reward_amount':float('nan')},{'reward_amount':0.5},
                       {'validity_days':366},{'reward_uses':101}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                routes._milestone_values({**base,**change})

    def test_auto_issue_uses_rule_creator_and_recovers_pending_claim(self):
        self.ctx();self.seed_ambassador()
        self.db.seed('profiles',[profile(ADMIN_ID,role='admin')])
        self.db.seed('ambassador_milestones',[{'id':'rule','created_by':ADMIN_ID,'metric':'shares','threshold':1,
            'reward_type':'hp','reward_amount':25,'auto_issue':True,'is_active':True,'campus_id':CAMPUS_A}])
        self.db.seed('ambassador_promo_assignments',[{'ambassador_id':AMB,'month':MONTH,'status':'shared'}])
        self.db.seed('ambassador_milestone_claims',[{'id':'claim','ambassador_id':AMB,'milestone_id':'rule','period_month':MONTH,'status':'pending_approval'}])
        out=svc.evaluate_milestones(self.db,AMB,MONTH)
        self.assertEqual(out[0]['claim']['status'],'issued')
        self.assertEqual(self.db.rows('ambassador_grants')[0]['issued_by'],ADMIN_ID)

    def test_meal_discount_never_selects_a_standalone_addon(self):
        amount=svc.compute_discount_amount({'max_meal_value':1000},[
            {'menu_item_id':'meal','price_snapshot':100,'is_addon':False},
            {'price_snapshot':500,'is_addon':True}],Decimal('600'),Decimal('0'))
        self.assertEqual(amount,Decimal('100.00'))

class SignupAttributionRegressionTests(AmbassadorTestBase):
    def test_existing_customer_click_is_not_a_new_signup(self):
        self.ctx();self.seed_ambassador()
        self.db.seed('profiles',[profile(STUDENT_ID)])
        self.db.seed('ambassador_link_clicks',[{'id':'click','ambassador_id':AMB,'visitor_user_id':STUDENT_ID,'created_at':'2026-10-03T10:00:00Z'}])
        self.assertEqual(svc.attributed_signups(self.db,AMB,MONTH),[])

    def test_first_pre_signup_click_counts_once_across_ambassadors(self):
        self.ctx();self.seed_ambassador()
        self.db.seed('profiles',[profile(STUDENT_ID)])
        self.db.seed('ambassador_link_clicks',[
            {'id':'one','ambassador_id':AMB,'visitor_user_id':STUDENT_ID,'created_at':'2026-10-01T10:00:00Z'},
            {'id':'two','ambassador_id':AMB2,'visitor_user_id':STUDENT_ID,'created_at':'2026-10-01T11:00:00Z'}])
        self.assertEqual(len(svc.attributed_signups(self.db,AMB,MONTH)),1)
        self.assertEqual(svc.attributed_signups(self.db,AMB2,MONTH),[])
