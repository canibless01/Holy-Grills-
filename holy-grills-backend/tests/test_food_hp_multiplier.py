import copy,unittest
from app.services.food_hp_multiplier import next_food_hp_multiplier

class Query:
 def __init__(self,db,table):self.db,self.table,self.one=db,table,False
 def select(self,*a):return self
 def eq(self,*a):return self
 def or_(self,*a):return self
 def is_(self,*a):return self
 def order(self,*a):return self
 def limit(self,*a):return self
 def single(self):self.one=True;return self
 def execute(self):
  if self.table in self.db.fail:raise RuntimeError('unavailable')
  rows=copy.deepcopy(self.db.rows.get(self.table,[]));return (rows[0] if rows else None) if self.one else rows
class Db:
 def __init__(self):self.fail=set();self.rows={'profiles':[{'next_order_hp_multiplier':1}],'exclusive_spin_fulfillments':[{'id':'first','result_snapshot':{'reward_config':{'multiplier':2}}},{'id':'second','result_snapshot':{'reward_config':{'multiplier':3}}}]}
 def table(self,t):return Query(self,t)
class FoodMultiplierTests(unittest.TestCase):
 def setUp(self):self.db=Db()
 def test_guest_has_no_award_reads(self):self.assertEqual(next_food_hp_multiplier(None,None,'campus')['multiplier'],1)
 def test_legacy_award_precedes_the_new_queue(self):
  self.db.rows['profiles'][0]['next_order_hp_multiplier']=1.5;self.db.fail={'exclusive_spin_fulfillments'}
  self.assertEqual(next_food_hp_multiplier(self.db,'user','campus'),{'multiplier':1.5,'source':'legacy','receipt_id':None})
 def test_oldest_queue_receipt_is_read_without_consuming_it(self):
  before=copy.deepcopy(self.db.rows)
  self.assertEqual(next_food_hp_multiplier(self.db,'user','campus'),{'multiplier':2,'source':'spin','receipt_id':'first'})
  self.assertEqual(before,self.db.rows)
 def test_empty_queue_has_no_bonus(self):
  self.db.rows['exclusive_spin_fulfillments']=[];self.assertEqual(next_food_hp_multiplier(self.db,'user','campus')['multiplier'],1)
 def test_invalid_or_unreadable_award_is_not_silently_lost(self):
  for value in (True,None,0,100,float('nan')):
   self.db=Db();self.db.rows['exclusive_spin_fulfillments'][0]['result_snapshot']['reward_config']['multiplier']=value
   with self.subTest(value=value),self.assertRaises((ValueError,TypeError)):next_food_hp_multiplier(self.db,'user','campus')
  self.db.fail={'exclusive_spin_fulfillments'}
  with self.assertRaises(RuntimeError):next_food_hp_multiplier(self.db,'user','campus')
