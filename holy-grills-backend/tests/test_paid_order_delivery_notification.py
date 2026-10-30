import unittest
from unittest.mock import patch
from app.services import order_service
from app.db import SupabaseError


class Query:
    def __init__(self, db, table): self.db, self.table = db, table
    def select(self, *_): return self
    def eq(self, *_): return self
    def single(self): return self
    def execute(self):
        if self.table == 'delivery_windows':
            if self.db.error: raise SupabaseError('Unavailable', 503)
            return self.db.window
        return []


class DB:
    error = False
    window = {'opens_at': '19:30:00', 'closes_at': '20:30:00'}
    def table(self, name): return Query(self, name)


class PaidOrderDeliveryNotificationTests(unittest.TestCase):
    def test_guest_confirmation_requires_verified_paid_state(self):
        guest={'id':'order','user_id':None,'guest_email':'owner@example.invalid','guest_name':'Owner','claim_token':'private'}
        with patch('app.utils.email.send_email') as email:
            order_service._on_order_paid({**guest,'payment_status':'pending'})
            email.assert_not_called()
            order_service._on_order_paid({**guest,'payment_status':'paid'})
            email.assert_called_once_with('owner@example.invalid','Owner','guest_order_confirmed',{'order_id':'order','claim_token':'private'})

    def notify(self, db=None, **changes):
        order = {'id': '11111111-1111-4111-8111-111111111111', 'user_id': 'owner',
                 'delivery_window_id': 'window', 'created_at': '2026-10-27T23:30:00Z'}
        order.update(changes)
        with patch.object(order_service, 'get_db', return_value=db or DB()), \
             patch.object(order_service, 'send_notification') as send:
            order_service._on_order_paid(order)
            return send.call_args.kwargs

    def test_confirmation_uses_persisted_window_and_lagos_date(self):
        data = self.notify()['template_data']
        self.assertEqual(data['delivery_window_start'], '19:30')
        self.assertEqual(data['delivery_window_end'], '20:30')
        self.assertEqual(data['delivery_date'], '2026-10-28')

    def test_scheduled_confirmation_uses_delivery_date_instead_of_booking_date(self):
        data = self.notify(is_scheduled=True, scheduled_for='2026-11-03T08:00:00+01:00')['template_data']
        self.assertEqual(data['delivery_date'], '2026-11-03')

    def test_missing_or_unreadable_window_has_honest_non_dash_copy(self):
        for error in (False, True):
            db = DB(); db.error = error; db.window = {}
            data = self.notify(db)
            self.assertIsNone(data['template_data'])
            self.assertIn('order tracking', data['body'])
            self.assertNotIn('–', data['body'])

    def test_legacy_timestamp_window_is_converted_to_lagos_time(self):
        db = DB(); db.window = {'starts_at': '2026-10-27T18:30:00Z', 'ends_at': '2026-10-27T19:30:00Z'}
        self.assertEqual(self.notify(db)['template_data']['delivery_window_start'], '19:30')
