"""Refund retries and invalid money inputs must not bypass the atomic RPC."""
import unittest
from unittest.mock import patch, MagicMock
from flask import Flask, g
from app.routes.orders import _atomic_refund_response


class AtomicRefundRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.order = {'id': 'order', 'user_id': 'customer', 'is_scheduled': True, 'status': 'received'}
        self.user = MagicMock()
        self.user.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = self.order
        self.db = MagicMock()
        self.db.rpc.return_value = {'success': True, 'idempotent': True, 'refund_amount': 100}

    def invoke(self, body, **kwargs):
        with self.app.test_request_context('/refund', method='POST', json=body), \
             patch('app.routes.orders.get_user_client', return_value=self.user), \
             patch('app.routes.orders.get_db', return_value=self.db):
            g.user_id = 'customer'
            return _atomic_refund_response('order', **kwargs)

    def test_nonfinite_and_nonpositive_amounts_never_reach_database(self):
        for amount in ['NaN', 'Infinity', '-Infinity', 0, -1, True, 'invalid']:
            with self.subTest(amount=amount):
                _, status = self.invoke({'reason': 'Return payment', 'idempotency_key': 'intent', 'refund_amount': amount})
                self.assertEqual(status, 400)
        self.user.table.assert_not_called()
        self.db.rpc.assert_not_called()

    def test_admin_refund_requires_retry_identity(self):
        _, status = self.invoke({'reason': 'Return payment', 'refund_amount': 100})
        self.assertEqual(status, 400)
        self.db.rpc.assert_not_called()

    def test_scheduled_and_normal_cancellation_share_same_identity(self):
        for scheduled in [False, True]:
            _, status = self.invoke({'reason': 'Cancel'}, customer_cancel=True, scheduled_only=scheduled)
            self.assertEqual(status, 200)
            args = self.db.rpc.call_args.args
            self.assertEqual(args[0], 'hg_refund_order_atomic')
            self.assertEqual(args[1]['p_request_key'], 'customer-cancel')
            self.assertIsNone(args[1]['p_requested_amount'])

    def test_customer_cannot_cancel_other_customers_order(self):
        self.order['user_id'] = 'someone-else'
        _, status = self.invoke({'reason': 'Cancel'}, customer_cancel=True)
        self.assertEqual(status, 403)
        self.db.rpc.assert_not_called()

    def test_atomic_failure_cannot_be_reported_as_success(self):
        self.db.rpc.return_value = {'success': False, 'error': 'refund_failed'}
        response, status = self.invoke({'reason': 'Return payment', 'idempotency_key': 'intent', 'refund_amount': 100})
        self.assertEqual(status, 503)
        self.assertNotIn('success', response.get_json())

    def test_replay_does_not_repeat_notification(self):
        with patch('app.services.notification_service.send_notification') as notify:
            _, status = self.invoke({'reason': 'Return payment', 'idempotency_key': 'intent', 'refund_amount': 100})
        self.assertEqual(status, 200)
        notify.assert_not_called()

    def test_admin_cannot_omit_amount_and_silently_refund_everything(self):
        _, status = self.invoke({'reason':'Reviewed complaint','idempotency_key':'intent'})
        self.assertEqual(status,400)
        self.db.rpc.assert_not_called()

    def test_delivered_refund_requires_explicit_acknowledgement(self):
        self.order['status']='delivered'
        body={'reason':'Reviewed complaint','refund_amount':25,'idempotency_key':'intent'}
        for value in (None,False,'true'):
            _,status=self.invoke({**body,'acknowledge_delivered':value})
            self.assertEqual(status,400)
        self.db.rpc.assert_not_called()
        _,status=self.invoke({**body,'acknowledge_delivered':True})
        self.assertEqual(status,200)
        self.assertEqual(self.db.rpc.call_args.args[1]['p_requested_amount'],25)
