import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.routes import menu


class MenuSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.db = MagicMock()
        self.db.table.return_value.select.return_value.or_.return_value.in_.return_value.not_.in_.return_value.eq.return_value.limit.return_value.execute.return_value = [{'id': 'order'}]

    def test_only_same_request_same_campus_shares_snapshot(self):
        with patch.object(menu, 'get_db', return_value=self.db):
            with self.app.test_request_context(method='GET'):
                menu._today_paid_orders('a')
                menu._today_paid_orders('a')
                self.assertEqual(self.db.table.call_count, 1)
                menu._today_paid_orders('b')
                self.assertEqual(self.db.table.call_count, 2)
            with self.app.test_request_context(method='GET'):
                menu._today_paid_orders('a')
                self.assertEqual(self.db.table.call_count, 3)

    def test_financial_writes_never_reuse_availability_snapshot(self):
        with self.app.test_request_context(method='POST'), patch.object(menu, 'get_db', return_value=self.db):
            menu._today_paid_orders('a')
            menu._today_paid_orders('a')
            self.assertEqual(self.db.table.call_count, 2)
