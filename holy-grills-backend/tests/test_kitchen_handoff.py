import unittest
from datetime import date
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import kitchen, admin
from app.services import order_service

BATCH='11111111-1111-4111-8111-111111111111'
RIDER='22222222-2222-4222-8222-222222222222'


class KitchenHandoffTests(unittest.TestCase):
    def setUp(self): self.app=Flask(__name__)

    def test_assignment_accepts_only_rider_selection_and_omits_financial_fields(self):
        receipt={'id':BATCH,'status':'assigned','rider_id':RIDER,'rider_pay_total':500}
        with self.app.test_request_context(method='POST',json={'rider_id':RIDER}), \
             patch.object(admin,'_batch_transaction',return_value=(receipt,None)) as transaction, \
             patch.object(admin,'_batch_saved_effects'):
            g.user_id='kitchen'
            response,status=kitchen.assign_handoff_rider.__wrapped__(BATCH)
        self.assertEqual(status,200)
        self.assertNotIn('rider_pay_total',response.json)
        transaction.assert_called_once_with('update',BATCH,{'rider_id':RIDER})

    def test_kitchen_transport_cannot_set_status_zone_money_or_actor(self):
        for key in ('status','zone','rider_pay_total','p_actor_id'):
            with self.subTest(key=key),self.app.test_request_context(method='POST',json={'rider_id':RIDER,key:'forged'}), \
                 patch.object(admin,'_batch_transaction') as transaction:
                _,status=kitchen.assign_handoff_rider.__wrapped__(BATCH)
                self.assertEqual(status,400);transaction.assert_not_called()

    def test_due_filter_uses_end_of_day_instead_of_delivery_hour(self):
        query=MagicMock();query.in_.return_value=query;query.or_.return_value=query
        with patch.object(kitchen,'today_wat',return_value=date(2026,10,27)):
            kitchen._due_preparation(query)
        query.in_.assert_called_once_with('payment_status',['paid','partially_refunded'])
        self.assertIn('scheduled_for.lt.2026-10-28T00:00:00+01:00',query.or_.call_args.args[0])

    def test_future_preparation_refused_before_any_update(self):
        db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={
            'id':BATCH,'campus_id':'campus','status':'received','payment_status':'paid',
            'is_scheduled':True,'scheduled_for':'2099-01-01T19:30:00+01:00'}
        with self.app.test_request_context(),patch.object(order_service,'get_user_client',return_value=db):
            g.user_id='kitchen';g.user_role='kitchen';g.campus_id='campus'
            with self.assertRaises(order_service.OrderConflictError):
                order_service.update_order_status(BATCH,'preparing','kitchen')
        db.table.return_value.update.assert_not_called()
