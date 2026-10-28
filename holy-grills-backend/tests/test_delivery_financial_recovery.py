"""Recovery uses saved terms and never treats a financial refusal as completion."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.services import delivery_reward_recovery as recovery, order_service, squad_service, hp_service

class DeliveryFinancialRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.db=MagicMock();self.query=MagicMock()
        for name in ('select','eq','order'):getattr(self.query,name).return_value=self.query
        self.db.table.return_value=self.query
        self.plan={'members':[],'unlock_amount':15,'welcome_amount':100,'squad_bonus':0}
        self.receipt={'total_hp':100,'owner_hp':100,'plan':self.plan}
        self.query.execute.return_value=[{'metadata':{'delivery_reward_recovery':self.receipt}}]
        self.db.rpc.return_value={'success':True,'unlocked_hp':15,'welcome_hp':100}
        self.order={'id':'order','user_id':'owner','subtotal':2000,'delivery_fee':500,'campus_id':'campus'}
    def run_recovery(self):
        with self.app.app_context(),patch.object(recovery,'get_db',return_value=self.db):
            return recovery.complete_delivery_financial_rewards(self.order)
    def test_saved_plan_reused_without_repricing_or_resplitting(self):
        with patch.object(squad_service,'squad_share_plan') as split,patch.object(hp_service,'get_food_earn_rate') as rate:
            result=self.run_recovery()
        self.assertTrue(result['success']);split.assert_not_called();rate.assert_not_called()
        self.assertEqual(self.db.rpc.call_args.args[1]['p_plan'],self.plan)
    def test_missing_legacy_receipt_does_not_guess_or_issue(self):
        self.query.execute.return_value=[]
        with self.assertRaisesRegex(RuntimeError,'older order'):self.run_recovery()
        self.db.rpc.assert_not_called()
    def test_atomic_refusal_does_not_report_success(self):
        self.db.rpc.return_value={'error':'delivery_reward_financial_pending'}
        with self.assertRaisesRegex(RuntimeError,'HP still needs'):self.run_recovery()
    def test_completed_replay_is_preserved(self):
        self.db.rpc.return_value={'success':True,'replayed':True,'unlocked_hp':15}
        self.assertTrue(self.run_recovery()['replayed'])
    def test_first_plan_uses_food_snapshot_not_delivery_fee(self):
        self.receipt.pop('plan')
        self.order['order_items']=[{'options_snapshot':{'_food_hp_plan':{'food_spend':1000}}}]
        with patch.object(squad_service,'squad_share_plan',return_value={'owner_share':100,'all_members':[],'registered':[]}),patch.object(hp_service,'get_food_earn_rate',return_value=.05),patch.object(hp_service,'_get_unlock_rate',return_value=.3),patch.object(hp_service,'_get_hp_multiplier',return_value=2),patch.object(recovery,'get_validated_setting',side_effect=lambda db,key,**kwargs:100 if key=='welcome_bonus_hp' else 30):
            self.run_recovery()
        plan=self.db.rpc.call_args.args[1]['p_plan']
        self.assertEqual(plan,{'members':[],'unlock_amount':15,'welcome_amount':200,'squad_bonus':0})
    def test_changed_owner_share_refuses_before_issue(self):
        self.receipt.pop('plan')
        with patch.object(squad_service,'squad_share_plan',return_value={'owner_share':50,'all_members':[],'share':50}),self.assertRaisesRegex(RuntimeError,'saved squad'):
            self.run_recovery()
        self.db.rpc.assert_not_called()
    def test_already_credited_order_goes_straight_to_financial_recovery(self):
        with self.app.test_request_context(),patch.object(recovery,'complete_delivery_financial_rewards',return_value={'success':True,'replayed':True}) as complete,patch.object(order_service.hp_service,'get_user_tier') as tier,patch.object(order_service,'get_db') as db:
            order_service._handle_delivery_rewards({**self.order,'hp_credited_at':'saved','hp_earned':100})
        complete.assert_called_once();tier.assert_not_called();db.assert_not_called()
    def test_squad_member_read_failure_does_not_give_full_award_to_owner(self):
        self.query.execute.side_effect=RuntimeError('unavailable')
        with patch.object(squad_service,'get_db',return_value=self.db),self.assertRaises(RuntimeError):squad_service.squad_share_plan('order',100,'owner')
    def test_duplicate_resolved_profile_does_not_dilute_owner_share(self):
        self.query.execute.return_value=[{'id':'one','email':'one@example.invalid','user_id':'friend','is_registered':True},{'id':'two','email':'two@example.invalid','user_id':'friend','is_registered':True}]
        with patch.object(squad_service,'get_db',return_value=self.db):result=squad_service.squad_share_plan('order',101,'owner')
        self.assertEqual(result['owner_share'],51);self.assertEqual(len(result['registered']),1)

    def test_status_enrichment_excludes_durable_reward_receipts(self):
        query=MagicMock()
        for name in ('eq','gte'):getattr(query,name).return_value=query
        query.update.return_value=[{'id':'ordinary-status-log'}]
        db=MagicMock();db.table.return_value=query
        with patch.object(order_service,'get_db',return_value=db):
            order_service._log_status_change('order','out_for_delivery','delivered','admin','Reason','campus')
        conditions=[call.args for call in query.eq.call_args_list]
        for key in ('delivery_reward_recovery','pending_hp_unlock','hp_bonus_plan'):
            self.assertIn(('metadata->'+key,None),conditions)
