import unittest
from unittest.mock import patch
from flask import Flask,g
from app.routes import leaderboard

class Query:
 def __init__(self,db,table):self.db=db;self.table=table;self.filters=[];self.skip=0;self.count=1000;self.one=False
 def select(self,*_):return self
 def eq(self,k,v):self.filters.append(lambda r:r.get(k)==v);return self
 def neq(self,k,v):self.filters.append(lambda r:r.get(k)!=v);return self
 def gte(self,k,v):self.filters.append(lambda r:r.get(k,'')>=v);return self
 def order(self,*_,**__):return self
 def offset(self,n):self.skip=n;return self
 def limit(self,n):self.count=n;return self
 def single(self):self.one=True;return self
 def execute(self):
  rows=[r for r in self.db.rows[self.table] if all(f(r) for f in self.filters)][self.skip:self.skip+self.count]
  return (rows[0] if rows else None) if self.one else rows
class DB:
 def __init__(self,rows):self.rows=rows;self.tables=[]
 def table(self,t):self.tables.append(t);return Query(self,t)
class LivePersonalRank(unittest.TestCase):
 def setUp(self):self.app=Flask(__name__)
 def result(self,db,period='monthly'):
  with self.app.test_request_context('/?period_type='+period),patch.object(leaderboard,'get_db',return_value=db),patch.object(leaderboard,'resolve_scoped_campus_id',return_value='campus'),patch.object(leaderboard,'_period_start_utc_iso',return_value='2026-10-01'):
   g.user_id='me';g.user_role='student';return leaderboard.my_rank.__wrapped__()[0].json
 def fixture(self):
  return DB({'profiles':[{'id':uid,'role':'student','campus_id':'campus','is_active':True,'hp_balance':hp} for uid,hp in [('me',100),('other',200)]], 'hp_transactions':[{'id':'1','user_id':'me','amount':100,'type':'earn','reference_type':'order','campus_id':'campus','created_at':'2026-10-02'},{'id':'2','user_id':'other','amount':200,'type':'earn','reference_type':'order','campus_id':'campus','created_at':'2026-10-02'}]})
 def test_current_month_without_snapshot_has_rank(self):
  db=self.fixture();r=self.result(db);self.assertEqual(r['rank'],2);self.assertEqual(r['rank_entry']['hp_total'],100);self.assertNotIn('leaderboard_snapshots',db.tables);self.assertTrue(r['computed_live'])
 def test_transfers_foreign_campus_inactive_and_old_earnings_do_not_inflate_rank(self):
  db=self.fixture();base=dict(db.rows['hp_transactions'][0]);db.rows['hp_transactions'] += [dict(base,id='3',amount=9999,reference_type='hp_transfer'),dict(base,id='4',amount=9999,campus_id='foreign'),dict(base,id='5',amount=9999,created_at='2026-09-01')];r=self.result(db);self.assertEqual(r['rank_entry']['hp_total'],100)
 def test_all_time_uses_current_balances(self):
  db=self.fixture();r=self.result(db,'all_time');self.assertEqual(r['rank'],2);self.assertNotIn('hp_transactions',db.tables)
 def test_page_limit_does_not_hide_later_earnings(self):
  db=self.fixture();base=db.rows['hp_transactions'][0];db.rows['hp_transactions']=[dict(base,id=str(i),amount=1) for i in range(1002)];r=self.result(db);self.assertEqual(r['rank_entry']['hp_total'],1002)
 def test_no_current_earnings_has_no_fabricated_rank(self):
  db=self.fixture();db.rows['hp_transactions']=[];self.assertIsNone(self.result(db)['rank'])
