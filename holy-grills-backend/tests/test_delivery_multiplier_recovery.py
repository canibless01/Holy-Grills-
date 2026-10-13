"""Payout outages preserve perks; stale multiplier reads recalculate before credit."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.services import order_service as service


class AfterPrimaryAward(Exception):
    pass


class DeliveryMultiplierRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__); self.db = MagicMock(); self.profiles = MagicMock(); self.squads = MagicMock()
        self.db.table.side_effect = lambda name: {'profiles': self.profiles, 'squad_members': self.squads}[name]
        self.profile_read = self.profiles.select.return_value.eq.return_value.single.return_value.execute
        self.profile_read.return_value = {'next_order_hp_multiplier': 2}
        self.squads.select.return_value.eq.return_value.limit.return_value.execute.return_value = []
        self.order = {'id': 'order', 'user_id': 'owner', 'subtotal': 2050, 'campus_id': 'campus', 'order_items': []}

    def invoke(self):
        with self.app.test_request_context(), patch.object(service, 'get_db', return_value=self.db), \
             patch.object(service.hp_service, 'get_user_tier', return_value={'tier': {'slug': 'ember'}}), \
             patch.object(service.hp_service, 'calculate_delivery_hp', return_value=102), \
             patch.object(service.hp_service, 'unlock_pending_hp'), \
             patch.object(service.hp_service, 'award_welcome_bonus', side_effect=AfterPrimaryAward):
            service._handle_delivery_rewards(self.order)

    def test_payout_failure_never_resets_the_profile_before_transaction(self):
        self.db.rpc.side_effect = RuntimeError('award unavailable')
        with self.assertRaisesRegex(RuntimeError, 'HP still needs'):
            self.invoke()
        self.profiles.update.assert_not_called()
        sent = self.db.rpc.call_args.args[1]
        self.assertEqual((sent['p_expected_multiplier'], sent['p_hp_amount'], sent['p_total_hp_amount']), (2, 204, 204))

    def test_competing_delivery_recalculates_without_second_bonus(self):
        self.profile_read.side_effect = [{'next_order_hp_multiplier': 2}, {'next_order_hp_multiplier': 1}]
        self.db.rpc.side_effect = [{'error': 'multiplier_changed'}, {'success': True}]
        with self.assertRaises(AfterPrimaryAward):
            self.invoke()
        calls = self.db.rpc.call_args_list
        self.assertEqual([(c.args[1]['p_expected_multiplier'], c.args[1]['p_hp_amount']) for c in calls], [(2, 204), (1, 102)])
        self.profiles.update.assert_not_called()

    def test_profile_outage_does_not_guess_away_the_bonus(self):
        self.profile_read.side_effect = RuntimeError('profile unavailable')
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.db.rpc.assert_not_called(); self.profiles.update.assert_not_called()

    def test_committed_replay_does_not_consume_a_newly_granted_bonus(self):
        self.db.rpc.return_value = {'already_credited': True}
        self.invoke()
        self.profiles.update.assert_not_called()

    def test_repeated_multiplier_changes_leave_award_pending(self):
        self.db.rpc.return_value = {'error': 'multiplier_changed'}
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual(self.db.rpc.call_count, 3); self.profiles.update.assert_not_called()
