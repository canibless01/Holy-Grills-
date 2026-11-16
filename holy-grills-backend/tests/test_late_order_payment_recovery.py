import copy
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.services import order_service, order_payments
from app.messages import MSG

OID='2b808beb-71b2-4c75-96c0-b11af5c9bd88'
CAMPUS='11111111-1111-4111-8111-111111111111'


class LatePaymentTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.order={'id':OID,'user_id':'student','campus_id':CAMPUS,'status':'cancelled',
                    'payment_status':'failed','wallet_amount_used':500,'card_amount_used':1800,'total_amount':2300}
        self.ref=order_payments.reference_for(self.order)
        self.transaction={'status':'success','reference':self.ref,'amount':180000,'currency':'NGN',
                          'metadata':{'type':'order_payment','order_id':OID,'user_id':'student','campus_id':CAMPUS}}
        self.db=MagicMock()
        self.db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect=[self.order,{**self.order,'payment_status':'refunded'}]
        self.db.rpc.return_value={'success':True,'resolution':'wallet_credited','amount':1800,'idempotent':False}

    def run_payment(self):
        with self.app.app_context(),patch.object(order_service,'get_db',return_value=self.db), \
             patch.object(order_service,'_on_order_paid') as confirm,patch.object(order_service,'send_notification') as notify:
            result=order_service.confirm_order_payment(OID,self.ref,copy.deepcopy(self.transaction))
            confirm.assert_not_called()
            return result,notify

    def test_verified_late_payment_keeps_order_cancelled_and_returns_wallet_credit(self):
        result,notify=self.run_payment()
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(self.db.rpc.call_args.args[0],'hg_reconcile_late_order_payment')
        self.assertEqual(self.db.rpc.call_args.args[1]['p_amount'],1800)
        self.assertIn('1800.00',notify.call_args.kwargs['body'])

    def test_bad_provider_proof_never_reaches_reconciliation(self):
        self.transaction['amount']=100
        with self.assertRaises(order_payments.OrderPaymentError):self.run_payment()
        self.db.rpc.assert_not_called()

    def test_replayed_payment_does_not_repeat_refund_notification(self):
        self.db.rpc.return_value={'success':True,'resolution':'wallet_credited','idempotent':True}
        _,notify=self.run_payment();notify.assert_not_called()

    def test_cancellation_winning_after_initial_read_reconciles_same_verified_event(self):
        self.db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect=[
            {**self.order,'status':'received','payment_status':'pending'},self.order,{**self.order,'payment_status':'refunded'}]
        self.db.rpc.side_effect=[{'error':'order_payment_closed'},
            {'success':True,'resolution':'wallet_credited','amount':1800,'idempotent':False}]
        result,_=self.run_payment()
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual([call.args[0] for call in self.db.rpc.call_args_list],
                         ['hg_mark_order_paid','hg_reconcile_late_order_payment'])

    def test_guest_manual_review_is_explicit_and_not_order_confirmation(self):
        self.order['user_id']=None
        self.transaction['metadata']['user_id']=None
        self.db.rpc.return_value={'success':True,'manual_review':True,'resolution':'manual_refund_required'}
        with self.assertRaisesRegex(ValueError,MSG.ORDER_LATE_GUEST_PAYMENT_REVIEW):self.run_payment()

    def test_failed_reconciliation_is_not_acknowledged_as_success(self):
        self.db.rpc.return_value={'error':'late_payment_reconciliation_failed'}
        with self.assertRaisesRegex(ValueError,MSG.ORDER_PAYMENT_RECONCILIATION_UNAVAILABLE):self.run_payment()
