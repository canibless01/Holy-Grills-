"""Preparation cannot be used to bypass assignment or financial exits."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.services import order_service
from app.routes.riders import _rider_order_view


class OrderRoleBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.db = MagicMock()
        self.order = {'id': 'order', 'status': 'ready', 'payment_status': 'paid',
                      'user_id': 'student', 'campus_id': 'campus'}
        self.db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = self.order

    def call_as(self, role, fn, **kwargs):
        with self.app.test_request_context(), patch('app.services.order_service.get_user_client', return_value=self.db):
            g.user_id = 'actor'
            g.user_role = role
            g.campus_id = 'campus'
            return fn('order', changed_by='actor', **kwargs)

    def test_kitchen_cannot_assign_or_deliver(self):
        for status in ['assigned', 'out_for_delivery', 'delivered']:
            with self.subTest(status=status), self.assertRaises(order_service.OrderForbiddenError):
                self.call_as('kitchen', order_service.update_order_status, new_status=status)
        self.db.table.return_value.update.assert_not_called()

    def test_kitchen_walk_rejects_target_before_any_partial_steps(self):
        self.order['status'] = 'received'
        with patch('app.services.order_service.update_order_status') as change:
            with self.assertRaises(order_service.OrderForbiddenError):
                self.call_as('kitchen', order_service.walk_order_to_status, target_status='delivered')
        change.assert_not_called()

    def test_financial_exit_requires_atomic_endpoint(self):
        for status in ['cancelled', 'refunded']:
            with self.subTest(status=status), self.assertRaises(order_service.OrderConflictError):
                self.call_as('admin', order_service.update_order_status, new_status=status)
        self.db.table.assert_not_called()

    def test_delivery_retry_preserves_pending_rewards_without_repeating_transition(self):
        self.order['status'] = 'delivered'
        with patch('app.services.order_service._handle_delivery_rewards', side_effect=RuntimeError('RPC unavailable')) as recovery:
            result = self.call_as('admin', order_service.update_order_status, new_status='delivered')
        recovery.assert_called_once_with(self.order)
        self.assertTrue(result['unchanged'])
        self.assertTrue(result['rewards_pending'])
        self.db.table.return_value.update.assert_not_called()

    def test_rider_receives_pending_indicator_without_customer_financials(self):
        result = _rider_order_view({**self.order, 'rewards_pending': True, 'total_amount': 4350, 'claim_token': 'private'})
        self.assertTrue(result['rewards_pending'])
        self.assertNotIn('total_amount', result)
        self.assertNotIn('user_id', result)
        self.assertNotIn('claim_token', result)
