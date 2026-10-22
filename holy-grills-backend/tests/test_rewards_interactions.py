"""Controlled fixtures for explicit reward claims and campus search privacy."""
import inspect
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import challenges, auth, hp
from app.services import milestone_service as milestones


class RewardsInteractionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.db = MagicMock()
        self.query = MagicMock()
        for method in ('select', 'eq', 'neq', 'in_', 'is_', 'limit', 'or_', 'single'):
            getattr(self.query, method).return_value = self.query
        self.db.table.return_value = self.query
        self.definitions = [{'id': trigger, 'trigger_type': trigger} for trigger in
                            ('pwa_install', 'push_subscribe', 'pwa_push_bonus')]
        self.query.execute.return_value = self.definitions

    def bonus(self, completed, award=False):
        with patch.object(milestones, 'get_user_client', return_value=self.db), \
             patch.object(milestones, '_is_already_completed',
                          side_effect=lambda _db, _user, mid, _period: mid in completed):
            return milestones.check_and_award_pwa_push_bonus('fixture-user', award=award)

    def test_status_with_both_actions_does_not_award(self):
        with patch.object(milestones, 'check_and_award_milestone') as claim:
            result = self.bonus({'pwa_install', 'push_subscribe'})
        self.assertTrue(result['eligible'])
        self.assertFalse(result['bonus_completed'])
        claim.assert_not_called()
        self.query.insert.assert_not_called()

    def test_explicit_claim_requires_both_actions(self):
        with patch.object(milestones, 'check_and_award_milestone') as claim:
            result = self.bonus({'pwa_install'}, award=True)
        self.assertFalse(result['eligible'])
        claim.assert_not_called()

    def test_explicit_claim_then_retry_is_idempotent(self):
        completed = {'pwa_install', 'push_subscribe'}
        def award(_user, milestone_id):
            completed.add(milestone_id)
            return {'hp_awarded': 75}
        with patch.object(milestones, 'check_and_award_milestone', side_effect=award) as claim:
            first = self.bonus(completed, award=True)
            second = self.bonus(completed, award=True)
        self.assertTrue(first['bonus_completed'])
        self.assertTrue(second['bonus_completed'])
        claim.assert_called_once_with('fixture-user', 'pwa_push_bonus')

    def test_generic_bonus_completion_cannot_skip_prerequisites(self):
        self.query.execute.return_value = {'id': 'bonus', 'trigger_type': 'pwa_push_bonus'}
        with patch.object(milestones, 'get_user_client', return_value=self.db), \
             patch.object(milestones, 'get_db', return_value=self.db), \
             patch.object(milestones, '_is_already_completed', return_value=False), \
             patch.object(milestones, 'check_and_award_pwa_push_bonus', return_value={'eligible': False}):
            with self.assertRaises(ValueError):
                milestones.check_and_award_milestone('fixture-user', 'bonus')
        self.query.insert.assert_not_called()

    def test_generic_push_completion_requires_registered_device(self):
        self.query.execute.side_effect = [{'id': 'push', 'trigger_type': 'push_subscribe'}, []]
        with patch.object(milestones, 'get_user_client', return_value=self.db), \
             patch.object(milestones, 'get_db', return_value=self.db), \
             patch.object(milestones, '_is_already_completed', return_value=False):
            with self.assertRaises(ValueError):
                milestones.check_and_award_milestone('fixture-user', 'push')
        self.query.insert.assert_not_called()

    def test_claim_route_reports_unavailable_instead_of_success(self):
        with self.app.test_request_context('/pwa-push-bonus', method='POST'), \
             patch.object(milestones, 'check_and_award_pwa_push_bonus',
                          return_value={'eligible': True, 'bonus_completed': False}):
            g.user_id = 'fixture-user'
            _, status = inspect.unwrap(challenges.claim_pwa_push_bonus)()
        self.assertEqual(status, 503)

    def test_search_hides_email_from_students_and_retains_admin_gmail_suggestions(self):
        self.query.execute.return_value = [{'id': 'fixture-peer', 'full_name': 'Fixture Peer',
                                            'nickname': 'Peer', 'email': 'fixture@gmail.com'}]
        for role, term in [('student', 'fixture@gmail.com'), ('admin', 'gmail')]:
            with self.subTest(role=role), self.app.test_request_context('/?q=' + term), \
                 patch.object(auth, 'get_db', return_value=self.db):
                g.user_id = 'fixture-user'; g.user_role = role; g.campus_id = 'fixture-campus'
                response, status = inspect.unwrap(auth.search_users)()
                self.assertEqual(status, 200)
                row = response.get_json()['results'][0]
                self.assertEqual('email' in row, role == 'admin')
                self.assertIn('email.ilike.', self.query.or_.call_args.args[0])
                self.query.eq.assert_any_call('campus_id', 'fixture-campus')

    def test_transfer_threshold_counts_only_delivered_orders(self):
        self.query.execute.side_effect = [{'value': 3}, [{'id': 'one'}, {'id': 'two'}]]
        with self.app.app_context():
            minimum, delivered = hp._transfer_order_eligibility(self.db, 'fixture-user')
        self.assertEqual((minimum, delivered), (3, 2))
        self.query.eq.assert_any_call('status', 'delivered')
        self.query.eq.assert_any_call('user_id', 'fixture-user')

    def test_plain_hp_milestones_keep_progress_and_exclude_browser_artwork(self):
        from tests.test_badges_and_address_fields import FakeDb, _milestone
        db = FakeDb(milestones=[_milestone("orders", "Three orders"),
                               dict(_milestone("pwa", "Install"), trigger_type="pwa_install")])
        with self.app.app_context(), patch.object(milestones, 'get_user_client', return_value=db), \
             patch.object(milestones, '_compute_trigger_progress', return_value=1) as progress:
            result = milestones.get_user_milestones('fixture-user')
        self.assertEqual([row['id'] for row in result['milestones_available']], ['orders'])
        row = result['milestones_available'][0]
        self.assertEqual(row['progress'], 1)
        self.assertEqual(row['hp_awarded'], 50)
        self.assertNotIn('icon_locked', row)
        self.assertNotIn('icon_won', row)
        self.assertIs(progress.call_args.args[0], db)
