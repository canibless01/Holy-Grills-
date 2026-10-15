"""Prize effects are explicit; failures and replays preserve the transaction result."""
import unittest
from unittest.mock import patch, MagicMock
from flask import Flask, g
from app.routes.exclusive_spin import do_spin, my_spins
from app.services.exclusive_spin_service import validate_spin_prize


class SpinContractTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_renaming_does_not_change_the_reward_category(self):
        for name in ['HP Jackpot', 'Lunch celebration', 'Renamed prize']:
            self.assertEqual(validate_spin_prize({'name': name, 'weight': 5,
                'reward_config': {'kind': 'hp', 'amount': 43}})['reward_config'],
                {'kind': 'hp', 'amount': 43})
        self.assertEqual(validate_spin_prize({'name': 'Replacement label'}, partial=True),
                         {'name': 'Replacement label'})

    def test_invalid_configuration_does_not_infer_from_a_name(self):
        for config in [None, [], {}, {'kind': []}, {'kind': 'hp'}, {'kind': 'hp', 'amount': True},
                       {'kind': 'hp', 'amount': 1.5}, {'kind': 'hp', 'amount': -1},
                       {'kind': 'physical', 'amount': 750}, {'kind': 'free_delivery', 'cap': float('inf')},
                       {'kind': 'hp_multiplier', 'multiplier': 0.5}]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_spin_prize({'name': '+750 HP', 'weight': 1, 'reward_config': config})

    def test_invalid_pool_fields(self):
        for body in [{'name': []}, {'name': ' '}, {'name': 'a'*121}, {'weight': True},
                     {'weight': 1.5}, {'weight': 0}, {'is_active': 'false'}]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_spin_prize(body, partial=True)

    def test_transaction_outage_returns_retryable_error(self):
        with self.app.test_request_context(json={'intent_key': '00000000-0000-4000-8000-000000000001'}), \
             patch('app.routes.exclusive_spin.get_db') as db:
            g.user_id = 'owner'; db.return_value.rpc.side_effect = RuntimeError('award rejected')
            _, status = do_spin.__wrapped__()
        self.assertEqual(status, 503)

    def test_replay_returns_same_reward_without_another_notice(self):
        result = {'prize': 'Original prize', 'prize_type': 'hp', 'hp_won': 43,
                  'spins_remaining': 2, 'idempotent': True}
        with self.app.test_request_context(json={'intent_key': '00000000-0000-4000-8000-000000000001'}), \
             patch('app.routes.exclusive_spin.get_db') as db, \
             patch('app.services.notification_service.send_notification') as notify:
            g.user_id = 'owner'; db.return_value.rpc.return_value = result
            response, status = do_spin.__wrapped__()
        self.assertEqual(status, 200); self.assertEqual(response.get_json()['hp_won'], 43)
        self.assertEqual(db.return_value.rpc.call_args.args[1]['p_user_id'], 'owner')
        notify.assert_not_called()

    def test_release_denial_comes_from_atomic_transaction(self):
        with self.app.test_request_context(json={'intent_key': '00000000-0000-4000-8000-000000000001'}), \
             patch('app.routes.exclusive_spin.get_db') as db:
            g.user_id = 'owner'; db.return_value.rpc.return_value = {'error': 'feature_disabled'}
            _, status = do_spin.__wrapped__()
        self.assertEqual(status, 403)

    def test_missing_intent_never_reaches_database(self):
        for body in [None, {}, [], {'intent_key': []}, {'intent_key': 'bad'}]:
            with self.subTest(body=body), self.app.test_request_context(json=body), \
                 patch('app.routes.exclusive_spin.get_db') as db:
                _, status = do_spin.__wrapped__()
            self.assertEqual(status, 400); db.assert_not_called()

    def test_unreadable_pool_returns_error_without_mock_prizes(self):
        with self.app.test_request_context(), \
             patch('app.routes.exclusive_spin.is_feature_enabled', return_value=True), \
             patch('app.routes.exclusive_spin.get_user_client', return_value=MagicMock()), \
             patch('app.routes.exclusive_spin._available_spins', return_value=[]), \
             patch('app.routes.exclusive_spin._spin_prizes', side_effect=RuntimeError('DB down')):
            g.user_id = 'owner'; response, status = my_spins.__wrapped__()
        self.assertEqual(status, 503); self.assertNotIn('prizes', response.get_json())
