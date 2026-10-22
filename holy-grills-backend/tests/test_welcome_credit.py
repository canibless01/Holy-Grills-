"""Welcome-credit configuration boundaries and retry hooks, without remote writes."""
import copy
import unittest
from unittest.mock import patch
from flask import Flask, g
from app.services import welcome_credit_service as service
from app.routes.admin_gifts import welcome_credit_settings

CAMPUS = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
DEFAULT = {'enabled': True, 'credits': 1, 'validity_days': 60}


class Query:
    def __init__(self, db, table): self.db, self.table, self.filters = db, table, []
    def select(self, *_): return self
    def eq(self, key, value): self.filters.append((key, value)); return self
    def is_(self, key, value): assert value == 'null'; return self.eq(key, None)
    def single(self): return self
    def matching(self): return [row for row in self.db.rows if all(row.get(k) == v for k, v in self.filters)]
    def execute(self):
        found = self.matching()
        return copy.deepcopy(found[0]) if found else None
    def update(self, values):
        found = self.matching()
        for row in found: row.update(values)
        return copy.deepcopy(found) if not self.db.refuse_write else []
    def insert(self, values):
        if self.db.failure: raise self.db.failure
        if self.db.refuse_write: return []
        self.db.rows.append(copy.deepcopy(values)); return [copy.deepcopy(values)]


class DB:
    def __init__(self, rows=None): self.rows, self.refuse_write, self.failure = rows or [], False, None
    def table(self, table): assert table == 'system_settings'; return Query(self, table)


class WelcomeCreditTests(unittest.TestCase):
    def call(self, db, *, role='admin', campus=CAMPUS, method='GET', body=None, query=''):
        with Flask(__name__).test_request_context('/welcome-credit'+query, method=method, json=body), \
             patch('app.routes.admin_gifts.get_db', return_value=db), \
             patch('app.routes.admin_gifts.get_user_client', return_value=db):
            g.user_id, g.user_role, g.campus_id = 'actor', role, campus
            return welcome_credit_settings.__wrapped__()

    def test_config_rejects_fractional_boolean_unknown_and_out_of_range_values(self):
        for change in ({'credits': True}, {'credits': 1.5}, {'credits': 0}, {'credits': 11},
                       {'validity_days': 0}, {'validity_days': 366}, {'enabled': 'true'}, {'extra': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                service.validate_config({**DEFAULT, **change})
        self.assertEqual(service.validate_config(DEFAULT), DEFAULT)

    def test_campus_reads_override_or_explicit_global_fallback(self):
        db = DB([{'key': service.CONFIG_KEY, 'campus_id': None, 'value': DEFAULT}])
        response, status = self.call(db)
        self.assertEqual(status, 200); self.assertTrue(response.json['inherited'])
        db.rows.append({'key': service.CONFIG_KEY, 'campus_id': CAMPUS, 'value': {**DEFAULT, 'enabled': False}})
        response, _ = self.call(db)
        self.assertFalse(response.json['config']['enabled']); self.assertFalse(response.json['inherited'])

    def test_admin_cannot_write_global_or_another_campus(self):
        db = DB()
        _, status = self.call(db, method='PATCH', body={'scope': 'global', 'config': DEFAULT})
        self.assertEqual(status, 403); self.assertEqual(db.rows, [])
        response, status = self.call(db, method='PATCH', body={'campus_id': OTHER, 'config': DEFAULT})
        self.assertEqual(status, 200); self.assertEqual(response.json['campus_id'], CAMPUS)
        self.assertEqual(db.rows[0]['campus_id'], CAMPUS)

    def test_super_admin_global_save_is_read_back_as_one_scoped_configuration(self):
        db = DB()
        for enabled in (True, False):
            response, status = self.call(db, role='super_admin', campus=None, method='PATCH',
                                        body={'scope': 'global', 'config': {**DEFAULT, 'enabled': enabled}})
            self.assertEqual(status, 200); self.assertIsNone(response.json['campus_id'])
        self.assertEqual(len(db.rows), 1); self.assertFalse(db.rows[0]['value']['enabled'])

    def test_generic_settings_cannot_bypass_welcome_config_validation(self):
        from app.routes.admin_gifts import update_setting, create_setting
        for handler in (update_setting, create_setting):
            db = DB([{'key':service.CONFIG_KEY, 'campus_id':CAMPUS, 'value':DEFAULT}])
            with self.subTest(handler=handler), Flask(__name__).test_request_context(method='PATCH', json={
                'key':service.CONFIG_KEY, 'campus_id':CAMPUS, 'value':{**DEFAULT, 'credits':True}}), \
                 patch('app.routes.admin_gifts.get_user_client',return_value=db):
                g.user_role, g.user_id, g.campus_id = 'admin', 'actor', CAMPUS
                _, status = handler.__wrapped__(service.CONFIG_KEY) if handler is update_setting else handler.__wrapped__()
                self.assertEqual(status,400)
                self.assertEqual(db.rows[0]['value'],DEFAULT)

    def test_competing_initial_save_is_a_conflict_instead_of_a_false_success(self):
        from app.db import SupabaseError
        db = DB(); db.failure = SupabaseError('duplicate configuration', 409, {'code':'23505'})
        _, status = self.call(db, method='PATCH', body={'config': DEFAULT})
        self.assertEqual(status, 409)
        self.assertEqual(db.rows, [])

    def test_empty_write_result_does_not_report_saved(self):
        db = DB(); db.refuse_write = True
        _, status = self.call(db, method='PATCH', body={'config': DEFAULT})
        self.assertEqual(status, 403)

    def test_config_unavailable_fails_closed_instead_of_showing_enabled_defaults(self):
        db = DB([{'key': service.CONFIG_KEY, 'campus_id': CAMPUS, 'value': {'enabled': True}}])
        _, status = self.call(db)
        self.assertEqual(status, 503)

    def test_grant_uses_only_server_identity_and_requires_a_valid_receipt(self):
        class RPC:
            def rpc(self, name, args):
                self.called = (name, args)
                return {'granted': False, 'idempotent': True, 'credit_id': 'saved'}
        db = RPC()
        with patch.object(service, 'get_db', return_value=db):
            result = service.grant_signup_credit('new-account')
        self.assertTrue(result['idempotent'])
        self.assertEqual(db.called, ('hg_grant_signup_free_side_atomic', {'p_user_id': 'new-account'}))
        with patch.object(service, 'get_db', return_value=type('Fail', (), {'rpc': lambda *args: {'error': 'configuration'}})()):
            with self.assertRaises(RuntimeError): service.grant_signup_credit('new-account')


class WelcomeRecoveryHookTests(unittest.TestCase):
    def test_auth_me_retries_only_for_an_active_existing_profile_and_keeps_auth_success(self):
        from unittest.mock import MagicMock
        from app.services import auth_service
        app = Flask(__name__)
        for profile, expected_calls in (({'id':'saved-user','is_active':True},1),
                                        ({'id':'saved-user','is_active':False},0), (None,0)):
            db = MagicMock(); db.auth_get_user.return_value={'id':'saved-user','email':'audit@example.invalid'}
            db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect=[profile,{'balance':0,'currency':'NGN'}]
            with self.subTest(profile=profile), app.app_context(), \
                 patch.object(auth_service,'get_user_client',return_value=db), \
                 patch.object(auth_service,'_get_tier',return_value=None), \
                 patch.object(service,'grant_signup_credit',side_effect=RuntimeError('temporarily unavailable')) as grant:
                result=auth_service.get_current_user('opaque-token')
                self.assertEqual(result['id'],'saved-user')
                self.assertEqual(grant.call_count,expected_calls)
                if expected_calls: grant.assert_called_once_with('saved-user')

    def test_registration_calls_welcome_after_profile_save_without_turning_recovery_failure_into_signup_failure(self):
        from unittest.mock import MagicMock
        from app.services import auth_service
        app = Flask(__name__); app.config.update(MINIMUM_AGE=16)
        db = MagicMock(); db.auth_sign_up.return_value={'user':{'id':'saved-user'}}
        db.table.return_value.select.return_value.eq.return_value.execute.side_effect=[[],[{'id':'saved-user'}]]
        with app.app_context(), patch.object(auth_service,'get_db',return_value=db), \
             patch.object(auth_service.hp_service,'award_signup_bonus'), \
             patch.object(service,'grant_signup_credit',side_effect=RuntimeError('temporarily unavailable')) as grant:
            result=auth_service.register('audit@example.invalid','LongPassword!1','Audit')
        self.assertEqual(result['user']['id'],'saved-user')
        grant.assert_called_once_with('saved-user')
        self.assertTrue(db.table.return_value.eq.return_value.update.called)


class SessionHydrationBoundaryTests(unittest.TestCase):
    def test_me_reuses_verified_identity_and_does_not_wait_for_welcome_recovery(self):
        from flask import g
        from app.routes import auth
        app = Flask(__name__)
        with app.test_request_context('/api/auth/me?session=1'), patch.object(auth.auth_service, 'get_current_user', return_value={'id':'saved-user'}) as get_user:
            g.jwt_token='opaque';g.jwt_payload={'id':'saved-user'};g.user_id='saved-user'
            response,status=auth.me.__wrapped__()
        self.assertEqual(status,200)
        get_user.assert_called_once_with('opaque',verified_auth_user={'id':'saved-user'},recover_welcome=False,include_balances=False)

    def test_lightweight_session_skips_optional_wallet_tier_and_welcome_work(self):
        from unittest.mock import MagicMock
        from app.services import auth_service
        db=MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':'saved-user','role':'student'}
        with Flask(__name__).app_context(), patch.object(auth_service,'get_user_client',return_value=db), patch.object(auth_service,'_get_tier') as tier, patch.object(service,'grant_signup_credit') as grant:
            result=auth_service.get_current_user('opaque',verified_auth_user={'id':'saved-user'},recover_welcome=False,include_balances=False)
        self.assertEqual(result['role'],'student');self.assertIsNone(result['wallet']);self.assertIsNone(result['tier'])
        db.table.assert_called_once_with('profiles');db.auth_get_user.assert_not_called();tier.assert_not_called();grant.assert_not_called()

    def test_optional_wallet_outage_does_not_reject_verified_profile(self):
        from unittest.mock import MagicMock
        from app.services import auth_service
        db=MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect=[{'id':'saved-user','role':'student','is_active':True},RuntimeError('wallet outage')]
        with Flask(__name__).app_context(), patch.object(auth_service,'get_user_client',return_value=db), patch.object(auth_service,'_get_tier',return_value=None), patch.object(service,'grant_signup_credit') as grant:
            result=auth_service.get_current_user('opaque',verified_auth_user={'id':'saved-user'},recover_welcome=False)
        self.assertEqual(result['role'],'student');self.assertIsNone(result['wallet'])
        db.auth_get_user.assert_not_called();grant.assert_not_called()

    def test_separate_recovery_uses_verified_caller_and_surfaces_retryable_failure(self):
        from flask import g
        from app.routes import auth
        app = Flask(__name__)
        with app.test_request_context('/api/auth/welcome-credit',method='POST',json={'user_id':'someone-else'}), patch.object(service,'grant_signup_credit',return_value={'granted':False,'idempotent':True}) as grant:
            g.user_id='saved-user'
            response,status=auth.recover_welcome_credit.__wrapped__()
            self.assertEqual(status,200)
            grant.assert_called_once_with('saved-user')
        with app.test_request_context('/api/auth/welcome-credit',method='POST'), patch.object(service,'grant_signup_credit',side_effect=RuntimeError('outage')):
            g.user_id='saved-user'
            response,status=auth.recover_welcome_credit.__wrapped__()
            self.assertEqual(status,503)


class LegacyGiftBoundaryTests(unittest.TestCase):
    def test_malformed_legacy_launch_date_fails_before_any_gift_write(self):
        from unittest.mock import MagicMock
        from app.services import gift_service
        for end_date in ('2035-01-01garbage','not-a-date','2035-02-30'):
            db=MagicMock()
            with self.subTest(end_date=end_date), patch.object(gift_service,'get_db',return_value=db), \
                 patch.object(gift_service,'_get_setting',side_effect=lambda _db,key,_default:'true' if key=='first_order_gift_enabled' else end_date):
                result=gift_service.maybe_grant_first_order_gift('user','order')
            self.assertFalse(result['granted'])
            self.assertEqual(result['reason'],'launch_window_invalid')
            db.table.assert_not_called()
