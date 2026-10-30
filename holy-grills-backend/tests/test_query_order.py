"""Reward FIFO relies on preserving primary and secondary sort terms."""
import unittest
from app.db import TableQuery

class QueryOrderTest(unittest.TestCase):
    def test_oldest_receipt_precedes_uuid_tie_breaker(self):
        query = TableQuery(None, "exclusive_spin_fulfillments")
        query.order("created_at").order("id", ascending=False)
        self.assertEqual(query._order, "created_at.asc,id.desc")
