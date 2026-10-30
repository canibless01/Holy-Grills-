"""Graduation HTTP boundaries; real transaction gates are verified separately in SQL."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import graduation

USER = 'bbbb0000-0000-4000-8000-000000000099'


class GraduationRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['GRADUATION_HP'] = 1000
        self.db = MagicMock()

    def call(self, result, *, eligibility=False, body=None):
        self.db.rpc.return_value = result
        with self.app.test_request_context(method='GET' if eligibility else 'POST', json=body), \
             patch.object(graduation, 'get_db', return_value=self.db), \
             patch('app.services.notification_service.send_notification'), \
             patch('app.services.milestone_service.check_milestone_trigger'):
            g.user_id = USER
            return (graduation.graduation_eligibility if eligibility else graduation.claim_graduation).__wrapped__()

    def test_eligibility_is_read_only_and_uses_authenticated_identity(self):
        response, status = self.call({'eligible': True, 'claimed': False, 'minimum_orders': 3,
                                      'delivered_orders': 3, 'in_period': True}, eligibility=True,
                                     body={'user_id': 'someone-else'})
        self.assertEqual(status, 200)
        self.assertTrue(response.json['eligible'])
        self.assertEqual(response.json['hp_amount'], 1000)
        self.db.rpc.assert_called_once_with('hg_graduation_eligibility', {'p_user_id': USER})
        self.db.table.assert_not_called()

    def test_claim_never_accepts_client_level_hp_or_identity(self):
        response, status = self.call({'success': True, 'hp_awarded': 1000, 'academic_level': '400L'},
                                    body={'user_id': 'someone-else', 'academic_level': '900L', 'hp_amount': 999999})
        self.assertEqual(status, 200)
        self.db.rpc.assert_called_once_with('hg_claim_graduation_atomic',
                                            {'p_user_id': USER, 'p_hp_amount': 1000})

    def test_missing_orders_period_or_level_never_becomes_success(self):
        for reason in ('orders', 'period', 'level', 'campus_required'):
            with self.subTest(reason=reason):
                response, status = self.call({'eligible': False, 'error': reason, 'reason': reason})
                self.assertEqual(status, 400)
                self.assertNotIn('hp_awarded', response.json)

    def test_database_unavailable_fails_closed_without_claiming(self):
        with self.app.test_request_context(method='POST'), patch.object(graduation, 'get_db', return_value=self.db):
            g.user_id = USER
            self.db.rpc.side_effect = RuntimeError('network failed')
            response, status = graduation.claim_graduation.__wrapped__()
        self.assertEqual(status, 503)
        self.assertNotIn('hp_awarded', response.json)

    def test_nonpositive_or_malformed_configuration_hides_claim(self):
        for value in (0, -1, True, 1.5, 'invalid', 2147483648):
            with self.subTest(value=value):
                self.app.config['GRADUATION_HP'] = value
                response, status = self.call({'eligible': True, 'claimed': False}, eligibility=True)
                self.assertEqual(status, 200)
                self.assertFalse(response.json['eligible'])
                self.assertEqual(response.json['reason'], 'configuration')

    def test_legacy_receipt_repair_and_expired_receipt_replay_survive_config_change(self):
        self.app.config['GRADUATION_HP'] = 0
        response, status = self.call({'success': True, 'replayed': True, 'hp_awarded': 0,
                                      'academic_level': '400L'})
        self.assertEqual(status, 200)
        self.assertTrue(response.json['replayed'])
        self.assertEqual(response.json['hp_awarded'], 0)
        self.db.rpc.assert_called_once_with('hg_claim_graduation_atomic', {'p_user_id': USER, 'p_hp_amount': 0})
        self.db.table.assert_not_called()

    def test_marker_counter_or_award_failure_is_not_a_saved_success(self):
        response, status = self.call({'error': 'claim_unavailable', 'debug_code': '23514'})
        self.assertEqual(status, 503)
        self.assertNotIn('debug_code', response.json)
        self.assertNotIn('hp_awarded', response.json)

    def test_postcommit_notification_failure_does_not_invent_failed_claim(self):
        self.db.rpc.return_value = {'success': True, 'hp_awarded': 1000}
        with self.app.test_request_context(method='POST'), patch.object(graduation, 'get_db', return_value=self.db), \
             patch('app.services.notification_service.send_notification', side_effect=RuntimeError('offline')), \
             patch('app.services.milestone_service.check_milestone_trigger', side_effect=RuntimeError('offline')):
            g.user_id = USER
            response, status = graduation.claim_graduation.__wrapped__()
        self.assertEqual(status, 200)
        self.assertEqual(response.json['hp_awarded'], 1000)
