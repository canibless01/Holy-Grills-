"""Exercise real report aggregators with filtering datasets, not copied formulas."""
from copy import deepcopy
from unittest.mock import MagicMock,patch,call
import pytest
from flask import Flask,g
from app.services import economics_dashboard_service as econ
from app.routes import admin,menu

A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222'
app=Flask(__name__)
class Query:
 def __init__(self,rows):self.rows=deepcopy(rows)
 def select(self,*a,**k):return self
 def order(self,*a,**k):return self
 def eq(self,k,v):self.rows=[r for r in self.rows if r.get(k)==v];return self
 def in_(self,k,v):self.rows=[r for r in self.rows if r.get(k) in v];return self
 def gte(self,k,v):self.rows=[r for r in self.rows if r.get(k,'')>=v];return self
 def lt(self,k,v):self.rows=[r for r in self.rows if r.get(k,'')<v];return self
 def execute(self):return self.rows
class DB:
 def __init__(self):
  base={'user_id':'u','campus_id':A,'created_at':'2026-11-05T12:00:00+00:00'}
  self.data={'hp_tiers':[{'id':'gold','name':'Gold','sort_order':1}], 'profiles':[{'id':'u','campus_id':A,'current_tier_id':'gold','hp_balance':70}],
   'orders':[{**base,'status':'delivered','subtotal':1000},{**base,'campus_id':B,'status':'delivered','subtotal':9000},{**base,'status':'cancelled','subtotal':99999}],
   'hp_transactions':[{**base,'amount':100,'type':'earn','source':'food_order','status':'confirmed'},{**base,'amount':20,'type':'earn','source':'tier_monthly_hp','status':'confirmed'},{**base,'amount':30,'type':'spend','source':'reward_redemption'},{**base,'amount':25,'type':'earn','source':'hp_transfer_received'},{**base,'amount':10,'type':'spend','source':'hp_transfer_sent'},{**base,'amount':7,'type':'earn','source':'other_bonus','status':'pending'},{**base,'campus_id':B,'amount':1000,'type':'earn','source':'food_order'}],
   'redemption_cost_log':[{**base,'actual_cost':15.5,'reward_type':'food','hp_spent':20},{**base,'actual_cost':4.5,'reward_type':'merch','hp_spent':10},{**base,'campus_id':B,'actual_cost':100,'reward_type':'food','hp_spent':100}]}
 def table(self,name):return Query(self.data[name])

def test_real_overview_and_redemption_arithmetic_exclude_other_campus_and_transfers():
 db=DB()
 with patch.object(econ,'get_hp_value',return_value=2.5),patch.object(econ,'_get_econ_setting',return_value=.025):
  r=econ.get_economics_overview(db,'2026-11-05','2026-11-06',A)
 assert (r['food_revenue'],r['hp_issued'],r['hp_redeemed'])==(1000,120,30)
 assert (r['hp_transfer_received'],r['hp_transfer_sent'])==(25,10)
 assert (r['pending_hp'],r['active_hp'],r['hp_outstanding'],r['theoretical_liability'])==(7,70,77,192.5)
 assert (r['actual_redemption_cost'],r['actual_programme_cost_pct'],r['variance_from_target'])==(20,.02,-.005)
 assert econ.get_redemption_analytics(db,'2026-11-05','2026-11-06',A)=={'cost_by_type':{'food':15.5,'merch':4.5},'total_actual_cost':20,'actual_cost_per_redeemed_hp':.6667}

def test_tier_report_scopes_activity_even_when_same_student_has_foreign_campus_history():
 db=DB();row=econ.get_tier_breakdown(db,'2026-11-05','2026-11-06',A)[0]
 assert row=={'tier':'Gold','revenue':1000,'hp_issued':120,'hp_redeemed':30,'actual_cost':20,'effective_pct':.02}
 global_row=econ.get_tier_breakdown(db,'2026-11-05','2026-11-06')[0]
 assert (global_row['revenue'],global_row['hp_issued'],global_row['actual_cost'])==(10000,1120,120)

def test_tier_report_processes_more_than_one_user_chunk():
 db=DB();db.data['profiles']=[{'id':str(i),'campus_id':A,'current_tier_id':'gold'} for i in range(205)]
 db.data['orders']=[{'user_id':str(i),'campus_id':A,'status':'delivered','subtotal':1} for i in range(205)]
 db.data['hp_transactions']=[];db.data['redemption_cost_log']=[]
 assert econ.get_tier_breakdown(db,campus_id=A)[0]['revenue']==205

@pytest.mark.parametrize('role,requested,expected',[('admin',B,A),('super_admin',B,B),('super_admin','',None)])
def test_reviews_handler_preserves_filters_scope_counts_and_stable_paging(role,requested,expected):
 db=MagicMock();q=db.table.return_value
 for name in ('select','eq','order','limit','offset'):getattr(q,name).return_value=q
 q.execute.return_value={'data':[{'id':'review','rating':5}],'count':51}
 with app.test_request_context('/?campus_id='+requested+'&rating=5&is_flagged=false&limit=25&offset=25'),patch.object(admin,'get_user_client',return_value=db):
  g.user_role=role;g.campus_id=A
  response,status=admin.list_reviews.__wrapped__()
 assert status==200 and response.json['total']==51 and response.json['offset']==25
 expected_calls=([call('campus_id',expected)] if expected else [])+[call('rating',5),call('is_flagged',False)]
 assert q.eq.call_args_list==expected_calls
 assert q.order.call_args_list==[call('created_at',ascending=False),call('id',ascending=False)]
 q.limit.assert_called_once_with(25);q.offset.assert_called_once_with(25)

def test_menu_review_fallback_counts_each_review_once_for_repeated_item_lines():
 db=MagicMock();db.rpc.side_effect=RuntimeError('controlled missing RPC');item_query=MagicMock();orders_query=MagicMock();reviews_query=MagicMock()
 for q in (item_query,orders_query,reviews_query):
  for method in ('select','in_','eq','is_'):getattr(q,method).return_value=q
  q.not_=q
 db.table.side_effect=lambda table:{'order_items':item_query,'orders':orders_query,'order_reviews':reviews_query}[table]
 item_query.execute.return_value=[{'menu_item_id':'meal','order_id':'one'},{'menu_item_id':'meal','order_id':'one'},{'menu_item_id':'meal','order_id':'two'}]
 orders_query.execute.return_value=[{'id':'one'},{'id':'two'}]
 reviews_query.execute.return_value=[{'id':'r1','order_id':'one','rating':1},{'id':'r2','order_id':'two','rating':5}]
 with app.app_context(),patch.object(menu,'get_db',return_value=db):summary=menu._review_stats(db,['meal'])
 assert summary=={'meal':{'avg_rating':3,'review_count':2}}
 assert menu._attach_review_stats([{'id':'meal'},{'id':'unreviewed'}],summary)==[{'id':'meal','avg_rating':3,'review_count':2},{'id':'unreviewed','avg_rating':0,'review_count':0}]
