"""Transport policy tests; external providers are stubbed, not delivery evidence."""
import unittest
from unittest.mock import patch
from flask import Flask
from app.services import notification_service as service
from tests.test_platform_boundaries import DB, USER, A


class NotificationPreferenceTransportTests(unittest.TestCase):
    def send(self, kind, preferences, profile=None):
        db = DB({'profiles': [{'id': USER, 'campus_id': A, **(profile or {})}],
                 'notification_preferences': [{'user_id': USER, **preferences}]})
        with Flask(__name__).app_context(), patch.object(service, 'get_db', return_value=db), patch.object(service, '_is_throttled', return_value=False), patch.object(service, '_log_notification'), patch.object(service.threading, 'Thread'):
            service.send_notification(USER, kind, title='Synthetic notification', body='Synthetic body', channels=['in_app', 'email', 'push'])
        return [row['channel'] for table, row in db.writes if table == 'notifications']

    def test_channel_preferences_suppress_external_alerts(self):
        self.assertEqual(self.send('hp_earned', {'email_enabled': False, 'push_enabled': False}), ['in_app'])

    def test_order_and_delivery_opt_out_keep_mandatory_inbox_only(self):
        for kind, key in [('order_confirmed', 'order_updates'), ('order_out_for_delivery', 'delivery_updates')]:
            self.assertEqual(self.send(kind, {key: False}), ['in_app'])

    def test_hp_and_promotional_categories_can_be_disabled(self):
        for kind, key in [('tier_upgrade', 'hp_updates'), ('blast_synthetic', 'promotions'), ('event_announcement', 'promotions')]:
            self.assertEqual(self.send(kind, {key: False}), [])

    def test_legacy_profile_channel_opt_out_is_preserved(self):
        self.assertEqual(self.send('marketplace_purchase', {}, {'push_enabled': False, 'email_notifications': False}), ['in_app'])

    def test_security_notices_remain_mandatory(self):
        self.assertEqual(self.send('password_changed', {'push_enabled': False, 'email_enabled': False}), ['in_app', 'email', 'push'])
