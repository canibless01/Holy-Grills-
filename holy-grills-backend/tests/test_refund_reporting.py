"""Actual report handlers with financial fixtures; no copied aggregators or live writes."""
import csv
import io
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch
from flask import Flask,g
from app.routes import analytics
from app.services import economics_dashboard_service as econ
from app.services.reporting_money import retained_food_amount,retained_payment_channels

C='11111111-1111-4111-8111-111111111111'
app=Flask(__name__)
class Query:
    def __init__(self,rows):self.rows=deepcopy(rows)
    def select(self,*a,**k):return self
    def order(self,*a,**k):return self
    def eq(self,k,v):self.rows=[r for r in self.rows if r.get(k)==v];return self
    def or_(self,expression):
        campus=expression.split('campus_id.eq.')[1].split(',')[0]
        self.rows=[r for r in self.rows if r.get('campus_id') in (None,campus)];return self
    def neq(self,k,v):self.rows=[r for r in self.rows if r.get(k)!=v];return self
    def in_(self,k,v):self.rows=[r for r in self.rows if r.get(k) in v];return self
    def gte(self,k,v):self.rows=[r for r in self.rows if r.get(k,'')>=v];return self
    def lt(self,k,v):self.rows=[r for r in self.rows if r.get(k,'')<v];return self
    def limit(self,n):self.rows=self.rows[:n];return self
    def execute(self):return self.rows
class DB:
    def __init__(self):
        common={'campus_id':C,'user_id':'u','created_at':'2026-11-12T12:00:00+00:00','order_source':'website','delivered_at':'2026-11-12T13:00:00+00:00','status':'delivered','payment_status':'paid','delivery_fee':500,'subtotal':3500,'total_amount':3500,'wallet_amount_used':0,'card_amount_used':3500,'wallet_refund_total':0,'card_refund_total':0}
        self.rows={'orders':[dict(common,id='partial',payment_status='partially_refunded',wallet_refund_total=700),dict(common,id='full',payment_status='refunded',card_refund_total=3500),dict(common,id='unpaid',status='received',payment_status='pending'),dict(common,id='paid-prep',status='preparing'),dict(common,id='cancel',status='cancelled',payment_status='refunded',wallet_refund_total=3500)],
          'academic_calendar':[{'id':'term','name':'Term','is_active':True,'campus_id':C,'start_date':'2026-11-12','end_date':'2026-11-12'}],
          'profiles':[{'id':'u','campus_id':C,'hp_balance':0,'current_tier_id':'tier'}],'hp_tiers':[{'id':'tier','name':'Ember'}],'hp_transactions':[],'redemption_cost_log':[]}
    def table(self,name):return Query(self.rows.get(name,[]))


def invoke(handler,db,query='from_date=2026-11-12&to_date=2026-11-12'):
    with app.test_request_context('/?'+query),patch.object(analytics,'get_user_client',return_value=db):
        g.user_role='admin';g.campus_id=C
        return handler.__wrapped__()


def test_economics_discounted_food_and_refunds_agree_across_overview_and_tiers():
    db=DB()
    with patch.object(econ,'get_hp_value',return_value=1),patch.object(econ,'_get_econ_setting',return_value=.025):
        report=econ.get_economics_overview(db,campus_id=C)
        tiers=econ.get_tier_breakdown(db,campus_id=C)
    # 3500 charged including delivery: 3000 food; 20% refunded -> 2400 food retained.
    assert report['food_revenue']==2400 and tiers[0]['revenue']==2400


def test_card_payment_refunded_to_wallet_reduces_card_origin_revenue():
    response,status=invoke(analytics.sales_analytics,DB())
    assert status==200
    assert response.json['total_revenue']==2800
    assert response.json['card_revenue']==2800 and response.json['wallet_revenue']==0


def test_split_refund_rounding_conserves_retained_revenue():
    row={'payment_status':'partially_refunded','total_amount':1000,'wallet_amount_used':333.33,'card_amount_used':666.67,'wallet_refund_total':100}
    assert retained_payment_channels(row)==(Decimal('300.00'),Decimal('600.00'))
    row['wallet_refund_total']=1000
    assert retained_payment_channels(row)==(0,0)


def test_source_and_calendar_charts_do_not_call_unpaid_preparation_or_refunded_totals_revenue():
    db=DB()
    response,status=invoke(analytics.order_sources_analytics,db)
    assert status==200 and response.json['order_sources'][0]['revenue']==2800
    response,status=invoke(analytics.academic_calendar_analytics,db)
    assert status==200 and response.json['academic_periods'][0]['total_revenue']==2800


def test_csv_keeps_charged_amount_and_adds_refund_and_net_columns():
    response=invoke(analytics.export_csv,DB(),'type=orders&from_date=2026-11-12&to_date=2026-11-12')
    rows={r['id']:r for r in csv.DictReader(io.StringIO(response.get_data(as_text=True)))}
    assert rows['partial']['total_amount']=='3500' and rows['partial']['wallet_refund_total']=='700'
    assert rows['partial']['retained_paid_amount']=='2800.0' and rows['partial']['retained_food_amount']=='2400.0'
    assert rows['partial']['delivered_order_revenue']=='2800.0'
    assert rows['unpaid']['retained_paid_amount']=='0.0' and rows['paid-prep']['delivered_order_revenue']=='0.0'
    assert rows['full']['retained_paid_amount']=='0.0'


def test_free_reward_and_over_refund_never_create_negative_food_revenue():
    assert retained_food_amount({'payment_status':'paid','total_amount':0,'delivery_fee':0})==0
    assert retained_food_amount({'payment_status':'refunded','total_amount':500,'delivery_fee':500,'wallet_refund_total':900})==0


def test_item_revenue_allocates_discount_and_refund_exactly_once():
    db=DB(); db.rows['orders']=db.rows['orders'][:1]
    db.rows['order_items']=[{'id':'a','order_id':'partial','name_snapshot':'Wings','quantity':1,'price_snapshot':1000,'line_total':1000}, {'id':'b','order_id':'partial','name_snapshot':'Plate','quantity':1,'price_snapshot':2500,'line_total':2500}, {'id':'c','order_id':'partial','name_snapshot':'Earned side','quantity':1,'price_snapshot':0,'line_total':0}]
    response,status=invoke(analytics.items_analytics,db)
    rows={row['item_name']:row for row in response.json['items']}
    assert status==200 and rows['Wings']['revenue']==685.71 and rows['Plate']['revenue']==1714.29
    assert rows['Earned side']['revenue']==0 and sum(row['revenue'] for row in rows.values())==2400


def test_location_report_retains_demand_counts_but_subtracts_refunds_from_revenue():
    response,status=invoke(analytics.delivery_location_analytics,DB())
    assert status==200 and sum(row['revenue'] for row in response.json['locations'])==2800
