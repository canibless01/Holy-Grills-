"""Payout outages preserve perks; stale multiplier reads recalculate before credit."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.services import order_service as service
from app.services import delivery_reward_recovery as recovery


class AfterPrimaryAward(Exception):
    pass


class DeliveryMultiplierRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.aux = MagicMock(side_effect=AfterPrimaryAward)
        self.app = Flask(__name__); self.db = MagicMock(); self.profiles = MagicMock(); self.squads = MagicMock()
        self.receipts = MagicMock()
        for method in ('select','eq','or_','is_','order','limit'):
            getattr(self.receipts,method).return_value=self.receipts
        self.receipts.execute.return_value=[]
        self.db.table.side_effect = lambda name: {'profiles': self.profiles, 'squad_members': self.squads,'exclusive_spin_fulfillments':self.receipts,'order_status_logs':self.receipts}[name]
        self.profile_read = self.profiles.select.return_value.eq.return_value.single.return_value.execute
        self.profile_read.return_value = {'next_order_hp_multiplier': 2}
        self.squads.select.return_value.eq.return_value.limit.return_value.execute.return_value = []
        self.order = {'id': 'order', 'user_id': 'owner', 'subtotal': 2050, 'campus_id': 'campus', 'order_items': []}

    def invoke(self):
        with self.app.test_request_context(), patch.object(service, 'get_db', return_value=self.db), \
             patch.object(service.hp_service, 'get_user_tier', return_value={'tier': {'slug': 'ember'}}), \
             patch.object(service.hp_service, 'calculate_delivery_hp', return_value=102), \
             patch.object(service.hp_service, 'unlock_pending_hp'), \
             patch.object(recovery, 'complete_delivery_financial_rewards', self.aux):
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
        self.aux.side_effect = None; self.aux.return_value = {'success': True, 'replayed': True}
        self.invoke()
        self.aux.assert_called_once()
        self.profiles.update.assert_not_called()

    def test_repeated_multiplier_changes_leave_award_pending(self):
        self.db.rpc.return_value = {'error': 'multiplier_changed'}
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual(self.db.rpc.call_count, 3); self.profiles.update.assert_not_called()

    def test_new_order_uses_admitted_food_hp_snapshot_after_config_changes(self):
        self.order['order_items'] = [{'options_snapshot': {'_food_hp_plan': {'version': 2, 'base_award': 150, 'food_spend': 900}}}]
        self.db.rpc.return_value = {'success': True}
        with self.assertRaises(AfterPrimaryAward):
            self.invoke()
        self.assertEqual(self.db.rpc.call_args.args[1]['p_hp_amount'], 300)

    def test_unlock_notice_uses_the_actual_unlock_result(self):
        from contextlib import ExitStack
        self.db.rpc.return_value={'success':True}
        with ExitStack() as stack:
            stack.enter_context(self.app.test_request_context())
            stack.enter_context(patch.object(service,'get_db',return_value=self.db))
            stack.enter_context(patch.object(service,'get_user_client',return_value=self.db))
            stack.enter_context(patch.object(service.hp_service,'get_user_tier',return_value={'tier':{'slug':'ember'}}))
            stack.enter_context(patch.object(service.hp_service,'calculate_delivery_hp',return_value=102))
            stack.enter_context(patch.object(recovery,'complete_delivery_financial_rewards',return_value={'success':True,'unlocked_hp':30,'welcome_hp':0}))
            stack.enter_context(patch.object(service.hp_service,'award_welcome_bonus',return_value={'awarded':0}))
            stack.enter_context(patch.object(service.hp_service,'recalculate_tier',return_value={'changed':False}))
            for target in ('app.services.streak_service.try_reclaim_checkin','app.services.streak_service.process_order_streak','app.services.milestone_service.check_milestone_trigger','app.services.gift_service.maybe_grant_first_order_gift'):
                stack.enter_context(patch(target))
            thread=stack.enter_context(patch('threading.Thread'))
            send=stack.enter_context(patch.object(service,'send_notification'))
            service._handle_delivery_rewards(self.order)
            thread.call_args.kwargs['target']()
            notices={call.kwargs['notif_type']:call.kwargs['template_data'] for call in send.call_args_list}
            self.assertEqual(notices['hp_unlocked']['unlocked_hp'],30)
            self.assertEqual(notices['hp_earned']['hp'],204)
