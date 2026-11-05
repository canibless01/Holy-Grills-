"""Failed provider deliveries can recover; in-flight events are not false success."""
import unittest
from unittest.mock import MagicMock, patch
from app.db import SupabaseError
from app.routes.webhooks import _claim_provider_event

class WebhookRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock();self.query=MagicMock();self.db.table.return_value=self.query
        self.query.eq.return_value=self.query;self.query.select.return_value=self.query;self.query.single.return_value=self.query
        self.query.insert.side_effect=SupabaseError('duplicate reference 23505',409,{})
        self.query.update.return_value=[]
    def claim(self):
        with patch('app.routes.webhooks.get_db',return_value=self.db):return _claim_provider_event('paystack','charge.success','ref',{'event':'charge.success'})
    def test_processed_replay_does_not_reapply(self):
        self.query.execute.return_value={'status':'processed'}
        self.assertEqual(self.claim(),'processed')
    def test_failed_event_is_reclaimed_with_compare_and_set(self):
        self.query.update.return_value=[{'status':'processing'}]
        self.assertEqual(self.claim(),'claimed')
        self.query.eq.assert_any_call('status','failed')
    def test_inflight_event_is_not_reported_as_processed(self):
        self.query.execute.return_value={'status':'processing'}
        self.assertEqual(self.claim(),'busy')
    def test_database_failure_does_not_acknowledge_payment(self):
        self.query.insert.side_effect=SupabaseError('database unavailable',503,{})
        with self.assertRaises(SupabaseError):self.claim()
