"""A changed settlement snapshot must not be marked paid or undone."""
import copy
import unittest
from unittest.mock import patch
from flask import Flask, g
from app.routes import riders
BATCH='11111111-1111-4111-8111-111111111111'
class Query:
    def __init__(self, db): self.db=db; self.filters=[]
    def select(self,*a): return self
    def eq(self,k,v): self.filters.append((k,v,True)); return self
    def neq(self,k,v): self.filters.append((k,v,False)); return self
    def single(self): return self
    def execute(self): return copy.deepcopy(self.db.snapshot)
    def update(self, values):
        self.db.writes.append((self.filters,values))
        if not all((self.db.current.get(k)==v)==equal for k,v,equal in self.filters): return []
        self.db.current.update(values)
        return [copy.deepcopy(self.db.current)]
class DB:
    def __init__(self, snapshot, current=None):
        self.snapshot=copy.deepcopy(snapshot); self.current=copy.deepcopy(current or snapshot); self.writes=[]
    def table(self,*a): return Query(self)
class RiderSettlementTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.row={'id':BATCH,'status':'completed','rider_pay_total':500,'rider_paid_at':None,'campus_id':'campus'}
    def mark(self,db,paid=True):
        with self.app.test_request_context(json={'batch_ids':[BATCH,BATCH]}),patch.object(riders,'get_user_client',return_value=db),patch.object(riders,'_select_in',return_value=[db.snapshot]),patch.object(riders,'_log_rider_admin_action') as log:
            g.user_id='admin'
            response,status=riders._set_batches_paid_state(paid)
            return response.json,status,log.call_count
    def test_record_retry_and_duplicate_ids_do_not_repeat_settlement(self):
        db=DB(self.row); result,status,count=self.mark(db)
        self.assertEqual((result['updated'],status,count),([BATCH],200,1))
        db.snapshot=copy.deepcopy(db.current);result,_,count=self.mark(db)
        self.assertEqual(result['skipped'],[BATCH]);self.assertEqual(count,0)
    def test_changed_price_or_concurrent_payment_is_skipped(self):
        for values in ({'rider_pay_total':600},{'rider_paid_at':'new-payment'}):
            db=DB(self.row,{**self.row,**values});result,_,count=self.mark(db)
            self.assertEqual(result['updated'],[]);self.assertEqual(count,0)
    def test_stale_undo_cannot_erase_a_newer_payment_record(self):
        db=DB({**self.row,'rider_paid_at':'old-payment'},{**self.row,'rider_paid_at':'new-payment'})
        result,_,count=self.mark(db,False)
        self.assertEqual(result['updated'],[]);self.assertEqual(db.current['rider_paid_at'],'new-payment');self.assertEqual(count,0)
    def test_incomplete_or_unpriced_batch_cannot_be_recorded_paid(self):
        for values in ({'status':'assigned'},{'rider_pay_total':None}):
            db=DB({**self.row,**values});result,_,count=self.mark(db)
            self.assertEqual(result['updated'],[]);self.assertFalse(db.writes);self.assertEqual(count,0)
    def test_cancellation_winning_price_read_prevents_repricing(self):
        db=DB(self.row,{**self.row,'status':'cancelled'})
        with self.app.test_request_context(json={'rider_pay_total':600}),patch.object(riders,'get_user_client',return_value=db):
            _,status=riders.admin_set_batch_pay.__wrapped__(BATCH)
        self.assertEqual(status,409);self.assertEqual(db.current['rider_pay_total'],500)
