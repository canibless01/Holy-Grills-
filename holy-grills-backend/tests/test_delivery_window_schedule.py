import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from app.services.delivery_window_schedule import upcoming_delivery_windows, delivery_clock, bind_ordering_delivery

class DeliveryScheduleTests(unittest.TestCase):
    def setUp(self):
        self.row={'id':'slot','campus_id':'campus','weekday':0,'date':None,'opens_at':'19:30:00','closes_at':'20:30:00','is_active':True,'is_closed':False,'status':'open'}
        self.now=datetime(2026,10,26,10,tzinfo=timezone.utc)
    def test_weekly_slot_materializes_in_wat_not_utc(self):
        row=upcoming_delivery_windows([self.row],self.now)[0]
        self.assertEqual(row['starts_at'],'2026-10-26T18:30:00+00:00')
        self.assertEqual(row['ends_at'],'2026-10-26T19:30:00+00:00')
        self.assertEqual(row['delivery_starts_at'],'19:30')
    def test_finished_weekday_moves_to_next_week(self):
        row=upcoming_delivery_windows([self.row],datetime(2026,10,26,20,tzinfo=timezone.utc))[0]
        self.assertTrue(row['starts_at'].startswith('2026-11-02'))
    def test_dated_closure_overrides_weekly_rule(self):
        closed={**self.row,'id':'closed','date':'2026-10-26','weekday':None,'is_closed':True}
        self.assertEqual(upcoming_delivery_windows([self.row,closed],self.now,days=1),[])
    def test_inactive_cancelled_and_invalid_rules_not_bookable(self):
        for override in ({'is_active':False},{'status':'cancelled'},{'closes_at':'18:00'},{'opens_at':None}):
            self.assertEqual(upcoming_delivery_windows([{**self.row,**override}],self.now),[])
    def test_instant_window_clock_converts_to_wat(self):
        self.assertEqual(delivery_clock({'starts_at':'2026-10-26T18:30:00Z'}),'19:30')
    def test_configuration_only_ordering_links_delivery_and_limits_cutoff(self):
        db=MagicMock();db.table.return_value.select.return_value.eq.return_value.execute.return_value=[self.row]
        row=bind_ordering_delivery(db,{'opens_at':'10:00:00','closes_at':'22:00:00'},'campus','2026-10-26')
        self.assertEqual(row['linked_delivery_window_id'],'slot')
        self.assertEqual(row['closes_at'],'20:30:00')
