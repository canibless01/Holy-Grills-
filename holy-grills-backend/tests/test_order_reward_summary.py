import unittest
from unittest.mock import MagicMock
from app.services.order_reward_summary import food_hp_reward_summary


class OrderRewardSummaryTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.order = {'id': 'order', 'user_id': 'owner'}
        self.logs = self.db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value
        self.logs.execute.return_value = [{'metadata': {'hp_bonus_plan': {'source': 'spin', 'receipt_id': 'receipt', 'multiplier': 3}}}]
        self.receipt = self.db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value

    def test_guest_does_not_read_privileged_receipts(self):
        self.assertIsNone(food_hp_reward_summary(self.db, {'id': 'order', 'user_id': None}))
        self.db.table.assert_not_called()

    def test_reserved_and_paid_states_are_distinct(self):
        for stored, expected in [('pending', 'reserved'), ('fulfilled', 'applied')]:
            self.receipt.execute.return_value = {'prize_name': 'Triple', 'status': stored, 'applied_order_id': 'order'}
            self.assertEqual(food_hp_reward_summary(self.db, self.order), {'name': 'Triple', 'multiplier': 3, 'status': expected})
        self.db.table.return_value.select.return_value.eq.return_value.eq.assert_called_with('user_id', 'owner')

    def test_released_reward_is_not_advertised_as_still_reserved(self):
        self.receipt.execute.return_value = {'status': 'pending', 'applied_order_id': 'another-order'}
        self.assertEqual(food_hp_reward_summary(self.db, self.order)['status'], 'released')

    def test_absent_or_failed_receipt_does_not_claim_reward_was_released(self):
        self.receipt.execute.return_value = None
        self.assertEqual(food_hp_reward_summary(self.db, self.order), {'status': 'unavailable'})
        self.logs.execute.side_effect = RuntimeError('read outage')
        self.assertEqual(food_hp_reward_summary(self.db, self.order), {'status': 'unavailable'})

    def test_opt_out_and_legacy_orders_do_not_invent_reward_receipts(self):
        for rows in ([], [{'metadata': {'hp_bonus_plan': {'source': 'none', 'multiplier': 1}}}]):
            self.logs.execute.return_value = rows
            self.assertIsNone(food_hp_reward_summary(self.db, self.order))


class OrderRewardReadAuthorizationTests(unittest.TestCase):
    def test_foreign_owner_and_wrong_guest_token_do_not_read_reward_metadata(self):
        from flask import Flask, g
        from unittest.mock import patch
        from app.routes.orders import get_order
        app = Flask(__name__)
        oid = '704ad6ca-4dc9-4e98-aec1-d750139217e5'
        for user, order, token in [('attacker', {'id': oid, 'user_id': 'owner'}, ''),
                                   (None, {'id': oid, 'user_id': None, 'claim_token': 'correct'}, '?claim_token=wrong')]:
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = order
            with app.test_request_context('/api/orders/' + oid + token), \
                    patch('app.routes.orders.get_user_client', return_value=db), \
                    patch('app.routes.orders.get_db', return_value=db), \
                    patch('app.services.order_reward_summary.food_hp_reward_summary') as summary:
                g.user_id = user
                response, status = get_order.__wrapped__(oid)
                self.assertEqual(status, 403)
                summary.assert_not_called()
