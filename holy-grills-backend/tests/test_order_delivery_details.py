import unittest
from unittest.mock import MagicMock
from app.services.order_delivery_details import order_delivery_details


class DeliveryDetailsTests(unittest.TestCase):
    def test_historical_text_snapshot_and_actual_window_are_normalized(self):
        address, window = order_delivery_details(None, {'delivery_address_snapshot': 'Blue house near gate',
            'delivery_windows': {'label': 'Evening', 'opens_at': '18:00:00', 'closes_at': '21:00:00'}})
        self.assertEqual(address['line1'], 'Blue house near gate')
        self.assertEqual(window['label'], 'Evening · 18:00–21:00')

    def test_old_empty_snapshot_resolves_only_same_campus_location(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {'name': 'Foreign hall', 'campus_id': 'other'}
        address, _ = order_delivery_details(db, {'delivery_location_id': 'hall', 'delivery_type': 'on_campus', 'campus_id': 'own'})
        self.assertFalse(address.get('line1'))

    def test_window_timestamp_uses_lagos_and_missing_window_stays_unassigned(self):
        _, window = order_delivery_details(None, {'delivery_windows': {'starts_at': '2026-10-20T17:00:00Z', 'ends_at': '2026-10-20T20:00:00Z'}})
        self.assertEqual(window['label'], '18:00–21:00')
        self.assertEqual(order_delivery_details(None, {}), ({}, {}))
