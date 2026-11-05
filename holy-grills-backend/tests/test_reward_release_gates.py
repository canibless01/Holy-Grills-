"""Release-off paths must not advertise benefits or broadcast contradictory promises."""
import inspect
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import rewards, hp, admin_gifts


class RewardReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.db = MagicMock()
        self.q = self.db.table.return_value
        for method in ('select', 'eq', 'is_', 'single', 'or_', 'order'):
            getattr(self.q, method).return_value = self.q

    def detail(self, reward, campus='campus-a', enabled=False, role='student'):
        self.q.execute.return_value = reward
        with self.app.test_request_context(), patch.object(rewards, 'get_user_client', return_value=self.db), \
             patch('app.routes.events._get_campus_id', return_value=campus), \
             patch('app.services.feature_flags.is_feature_enabled', return_value=enabled) as flag, \
             patch.object(rewards, '_active_flash_windows') as windows:
            g.campus_id = campus; g.user_role = role
            response, status = inspect.unwrap(rewards.get_reward)('reward')
        return response, status, flag, windows

    def test_detail_hides_flash_price_while_release_is_off(self):
        response, status, flag, windows = self.detail({'id': 'reward', 'campus_id': 'campus-a', 'hp_cost': 100})
        self.assertEqual(status, 200)
        self.assertFalse(response.json['is_flash_active'])
        self.assertNotIn('flash_hp_cost', response.json)
        flag.assert_called_once_with('flash_redemptions', 'campus-a')
        windows.assert_not_called()

    def test_reward_detail_is_not_visible_across_campuses_or_without_guest_selection(self):
        for campus in ('campus-b', None):
            with self.subTest(campus=campus):
                _, status, flag, windows = self.detail({'id': 'reward', 'campus_id': 'campus-a'}, campus=campus, role=None)
                self.assertEqual(status, 404)
                flag.assert_not_called(); windows.assert_not_called()

    def test_global_reward_stays_available_before_guest_campus_selection(self):
        response, status, _, _ = self.detail({'id': 'reward', 'campus_id': None}, campus=None, role=None)
        self.assertEqual(status, 200)
        self.assertFalse(response.json['is_flash_active'])

    def test_flash_action_uses_verified_campus_and_stops_before_spending(self):
        with self.app.test_request_context(method='POST'), \
             patch('app.services.feature_flags.is_feature_enabled', return_value=False) as flag, \
             patch('app.services.hp_service.process_flash_redeem') as spend:
            g.user_id = 'student'; g.campus_id = 'campus-a'
            _, status = inspect.unwrap(hp.flash_redeem)('reward')
        self.assertEqual(status, 403); spend.assert_not_called()
        flag.assert_called_once_with('flash_redemptions', 'campus-a')

    def test_disabled_or_expired_multiplier_does_not_query_recipients(self):
        for enabled, effective in ((False, 2), (True, 1)):
            with self.subTest(enabled=enabled, effective=effective), self.app.app_context(), \
                 patch('app.services.feature_flags.is_feature_enabled', return_value=enabled), \
                 patch('app.services.hp_service._get_hp_multiplier', return_value=effective), \
                 patch('app.services.notification_service.send_notification') as send:
                admin_gifts._broadcast_multiplier_event(self.db, 2, campus_id='campus-a')
            self.db.table.assert_not_called(); send.assert_not_called()

    def test_global_broadcast_respects_campus_pause_and_effective_override(self):
        self.q.execute.return_value = [
            {'id': 'eligible', 'campus_id': 'campus-a'},
            {'id': 'paused', 'campus_id': 'campus-b'},
            {'id': 'override', 'campus_id': 'campus-c'},
        ]
        with self.app.app_context(), \
             patch('app.services.feature_flags.is_feature_enabled', side_effect=lambda _, campus: campus != 'campus-b'), \
             patch('app.services.hp_service._get_hp_multiplier', side_effect=lambda campus: 1 if campus == 'campus-c' else 2), \
             patch('app.services.notification_service.send_notification') as send:
            admin_gifts._broadcast_multiplier_event(self.db, 2)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.kwargs['user_id'], 'eligible')
        self.q.eq.assert_any_call('role', 'student')


if __name__ == '__main__':
    unittest.main()
