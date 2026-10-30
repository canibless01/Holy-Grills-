"""The worker must not expire a lock redeemed/rescheduled since its queue read."""
import copy
import unittest
from datetime import date
from unittest.mock import patch
from app.tasks.scheduled import check_order_locks

class Query:
    def __init__(self,db,name):self.db,self.name,self.filters=db,name,[]
    def select(self,*a):return self
    def eq(self,k,v):self.filters.append((k,v));return self
    def execute(self):
        if self.name=='campuses':return [{'id':'campus'}]
        return [copy.deepcopy(self.db.snapshot)]
    def update(self,body):
        if any(self.db.row.get(k)!=v for k,v in self.filters):return []
        self.db.row.update(body);return [copy.deepcopy(self.db.row)]
class Db:
    def __init__(self):
        self.snapshot={'id':'lock','user_id':'student','campus_id':'campus','status':'active','locked_date':'2026-10-12'};self.row=copy.deepcopy(self.snapshot)
    def table(self,name):return Query(self,name)
    def rpc(self,*a):return True
class OrderLockExpiryRaceTests(unittest.TestCase):
    def test_changed_state_or_date_is_preserved(self):
        for change in [{'status':'used'},{'locked_date':'2026-10-20'}]:
            db=Db();db.row.update(change);before=copy.deepcopy(db.row)
            with patch('app.tasks.scheduled.get_db',return_value=db),patch('app.tasks.scheduled.today_wat',return_value=date(2026,10,13)):
                result=check_order_locks.run.__wrapped__(None)
            self.assertEqual(db.row,before);self.assertEqual(result['campus']['expired'],0)
    def test_unchanged_missed_lock_expires(self):
        db=Db()
        with patch('app.tasks.scheduled.get_db',return_value=db),patch('app.tasks.scheduled.today_wat',return_value=date(2026,10,13)):
            result=check_order_locks.run.__wrapped__(None)
        self.assertEqual(db.row['status'],'expired');self.assertEqual(result['campus']['expired'],1)
