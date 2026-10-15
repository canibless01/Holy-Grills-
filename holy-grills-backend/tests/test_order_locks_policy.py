"""Pin actual lock policy and exercise writes against changing lock state."""
import copy
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from app.routes.order_locks import _validate_lock_date,reschedule_lock_write,cancel_lock_write

class Query:
    def __init__(self,db):self.db=db;self.filters=[]
    def eq(self,k,v):self.filters.append((k,v));return self
    def update(self,body):
        if any(self.db.row.get(k)!=v for k,v in self.filters):return []
        self.db.row.update(body);return [copy.deepcopy(self.db.row)]
class Db:
    def __init__(self,status='active',count=0):self.row={'id':'lock','user_id':'student','status':status,'reschedule_count':count,'locked_date':'2026-10-14'}
    def table(self,name):return Query(self)

class OrderLockPolicyTests(unittest.TestCase):
    def test_actual_policy_uses_wat_tomorrow_through_seven_days(self):
        today=date(2026,10,13)
        with patch('app.routes.order_locks.today_wat',return_value=today):
            for offset in [-1,0,1,2,3,4,5,6,7,8,30]:
                with self.subTest(offset=offset):self.assertEqual(_validate_lock_date(today+timedelta(days=offset))[0],1<=offset<=7)
    def test_stale_or_foreign_reschedule_preserves_current_row(self):
        for status,owner,count in [('used','student',0),('active','other',0),('active','student',1)]:
            db=Db(status,count);before=copy.deepcopy(db.row)
            self.assertEqual(reschedule_lock_write(db,'lock',owner,0,{'locked_date':'2026-10-20','reschedule_count':1}),[])
            self.assertEqual(db.row,before)
    def test_valid_reschedule_can_only_spend_the_count_once(self):
        db=Db();body={'locked_date':'2026-10-20','reschedule_count':1}
        self.assertTrue(reschedule_lock_write(db,'lock','student',0,body));self.assertFalse(reschedule_lock_write(db,'lock','student',0,body));self.assertEqual(db.row['reschedule_count'],1)
    def test_cancel_cannot_overwrite_used_or_foreign_lock(self):
        for status,owner in [('used','student'),('active','other')]:
            db=Db(status);before=copy.deepcopy(db.row);self.assertFalse(cancel_lock_write(db,'lock',owner));self.assertEqual(db.row,before)
        db=Db();self.assertTrue(cancel_lock_write(db,'lock','student'));self.assertFalse(cancel_lock_write(db,'lock','student'));self.assertEqual(db.row['status'],'cancelled')
