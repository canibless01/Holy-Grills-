"""Exercise the real checkout calculator without allowing any database writes."""
import copy
import unittest
from unittest.mock import patch
from flask import Flask, g
from app.services import order_service as service
from app.utils.tz import today_wat

CAMPUS='11111111-1111-4111-8111-111111111111'
MEAL='22222222-2222-4222-8222-222222222222'
HOSTEL='33333333-3333-4333-8333-333333333333'

class Query:
    def __init__(self,db,table):self.db,self.table,self.filters,self.one=db,table,[],False
    @property
    def not_(self):return self
    def select(self,*a):return self
    def eq(self,key,value):self.filters.append((key,value));return self
    def gte(self,*a):return self
    def in_(self,*a):return self
    def or_(self,*a):return self
    def is_(self,key,value):self.filters.append((key,None if value=='null' else value));return self
    def order(self,*a):return self
    def limit(self,*a):return self
    def single(self):self.one=True;return self
    def execute(self):
        if self.table in self.db.fail:raise RuntimeError('database unavailable')
        rows=[copy.deepcopy(row) for row in self.db.rows.get(self.table,[]) if all((row.get(k.split('->>')[0],{}).get(k.split('->>')[1]) if '->>' in k else row.get(k))==v for k,v in self.filters)]
        return (rows[0] if rows else None) if self.one else rows
    def insert(self,*a):raise AssertionError('Quote attempted an insert')
    def update(self,*a):raise AssertionError('Quote attempted an update')
    def delete(self,*a):raise AssertionError('Quote attempted a deletion')
class Db:
    def __init__(self):
        self.fail=set()
        self.rows={'profiles':[{'id':'student','phone':'08012345678','campus_id':CAMPUS,'is_active':True,'next_order_free_delivery_cap':0}], 'menu_items':[{'id':MEAL,'campus_id':CAMPUS,'name':'Meal','price':2050,'hp_multiplier':0.5,'is_available':True}],
                   'hostels':[{'id':HOSTEL,'campus_id':CAMPUS,'delivery_fee':250,'is_active':'true'}],
                   'order_locks':[{'id':'lock','user_id':'student','campus_id':CAMPUS,'status':'active','locked_date':today_wat().isoformat(),'reward_type':'discount','discount_pct':10}]}
    def table(self,name):return Query(self,name)
    def rpc(self,*a):raise AssertionError('Quote called a mutating RPC')

class CheckoutQuoteTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.app.config.update(HP_PER_NAIRA_FOOD=0.1,SQUAD_ORDER_ENABLED=False)
        self.db=Db();self.payload={'items':[{'menu_item_id':MEAL,'quantity':1}],'payment_method':'card','delivery_type':'on_campus','delivery_location_id':HOSTEL}
    def calculate(self,guest=False,quote_only=True,payload=None,base_hp=102):
        with self.app.test_request_context(),patch.object(service,'get_db',return_value=self.db),patch.object(service,'get_user_client',return_value=self.db),patch.object(service.hp_service,'get_user_tier',return_value={'tier':{'slug':'ember'}}),patch.object(service.hp_service,'calculate_delivery_hp',return_value=base_hp):
            g.campus_id=CAMPUS
            return service.create_order(None if guest else 'student',payload or self.payload,quote_only=quote_only)
    def test_delivery_credit_reduces_fee_and_total_without_writes(self):
        self.db.rows['profiles'][0]['next_order_free_delivery_cap']=100
        q=self.calculate()
        self.assertEqual((q['delivery_fee'],q['total_amount']),(150,1995))
        self.assertEqual(q['delivery_benefit']['discount'],100)
        self.assertEqual(self.db.rows['profiles'][0]['next_order_free_delivery_cap'],100)
    def test_monthly_free_delivery_preserves_spin_credit(self):
        self.db.rows['profiles'][0]['next_order_free_delivery_cap']=100
        self.db.rows['system_settings']=[{'key':'tier_perk_ember_monthly_free_delivery','campus_id':None,'value':True}]
        q=self.calculate()
        self.assertEqual((q['delivery_fee'],q['total_amount']),(0,1845))
        self.assertEqual(q['delivery_benefit']['source'],'monthly')
        self.assertEqual(self.db.rows['profiles'][0]['next_order_free_delivery_cap'],100)
    def test_used_monthly_perk_falls_back_to_credit(self):
        self.db.rows['system_settings']=[{'key':'tier_perk_ember_monthly_free_delivery','campus_id':None,'value':True}]
        self.db.rows['tier_monthly_perk_usage']=[{'id':'used','user_id':'student','month':today_wat().strftime('%Y-%m'),'perk_key':'monthly_free_delivery'}]
        self.db.rows['profiles'][0]['next_order_free_delivery_cap']=100
        self.assertEqual(self.calculate()['delivery_benefit']['source'],'legacy_spin')
    def test_benefit_read_failure_blocks_pricing_instead_of_charging_full_fee(self):
        for table in ('profiles','exclusive_spin_fulfillments','system_settings'):
            self.db.fail={table}
            with self.subTest(table=table),self.assertRaisesRegex(ValueError,'could not be verified'):
                self.calculate()

    def test_quote_applies_lock_once_and_never_writes(self):
        q=self.calculate();self.assertEqual((q['subtotal'],q['discount_amount'],q['total_amount']),(2050,205,2095));self.assertEqual(q['hp_preview']['total_hp'],102)
    def test_guest_quote_has_no_user_lock_or_hp_promise(self):
        q=self.calculate(guest=True);self.assertEqual(q['total_amount'],2300);self.assertEqual(q['hp_preview']['total_hp'],0)
    def test_promotions_cannot_discount_delivery_or_waste_lock(self):
        with patch.object(service,'_apply_promo',return_value={'discount':3000,'promo_code_id':'promo'}):
            body={**self.payload,'promo_code':'PROMO'};q=self.calculate(payload=body)
        self.assertEqual((q['discount_amount'],q['order_lock_discount'],q['total_amount']),(2050,0,250))
    def test_unknown_or_other_campus_hostel_is_rejected(self):
        for campus in [None,'other-campus']:
            if campus is None:self.db.rows['hostels']=[]
            else:self.db.rows['hostels']=[{'id':HOSTEL,'campus_id':campus,'delivery_fee':1,'is_active':'true'}]
            with self.subTest(campus=campus),self.assertRaises(ValueError):self.calculate(guest=True)
    def test_fee_or_availability_outage_does_not_become_free(self):
        for table in ['hostels','menu_item_availability','user_addresses']:
            self.db.fail={table}
            with self.subTest(table=table),self.assertRaisesRegex(ValueError,'could not be verified'):self.calculate(payload={**self.payload,'delivery_address_id':HOSTEL} if table=='user_addresses' else None)
    def test_malformed_quantities_and_payment_methods_are_validation_errors(self):
        for quantity in [None,True,0,-1,1.5,{},[],'Infinity']:
            body=copy.deepcopy(self.payload);body['items'][0]['quantity']=quantity
            with self.subTest(quantity=quantity),self.assertRaises(ValueError):self.calculate(payload=body)
        for payment in [None,True,{},'free']:
            with self.subTest(payment=payment),self.assertRaises(ValueError):self.calculate(payload={**self.payload,'payment_method':payment})
    def test_missing_delivery_type_cannot_remove_delivery_fee(self):
        body=copy.deepcopy(self.payload);body.pop('delivery_type')
        with self.assertRaises(ValueError):self.calculate(payload=body)
    def test_changed_price_is_reported_before_stale_wallet_balance(self):
        self.db.fail={'wallets'}
        with patch.object(service,'_order_for_intent',return_value=None),patch.object(service,'resolve_ordering_window',return_value={}),patch.object(service,'_check_kitchen_capacity'):
            with self.assertRaises(service.OrderPriceChanged) as raised:
                self.calculate(quote_only=False,payload={**self.payload,'payment_method':'wallet','expected_total':2300})
        self.assertEqual(raised.exception.quote['total_amount'],2095)
    def test_lock_claim_race_returns_fresh_price_without_another_charge(self):
        self.db.rows['wallets']=[{'user_id':'student','balance':5000}]
        def lost_lock(*args):
            self.db.rows['order_locks'][0]['status']='cancelled'
            return {'error':'ORDER_LOCK_UNAVAILABLE'}
        with patch.object(service,'_order_for_intent',return_value=None),patch.object(service,'resolve_ordering_window',return_value={}),patch.object(service,'_check_kitchen_capacity'),patch.object(self.db,'rpc',side_effect=lost_lock) as rpc:
            with self.assertRaises(service.OrderPriceChanged) as raised:
                self.calculate(quote_only=False,payload={**self.payload,'payment_method':'wallet','expected_total':2095})
        self.assertEqual(raised.exception.quote['total_amount'],2300);self.assertEqual(rpc.call_count,1);self.assertEqual(self.db.rows['wallets'][0]['balance'],5000)
    def test_changed_free_side_requests_review_before_order_or_debit(self):
        plan={'enabled':True,'items':[{'selection_id':'new','free_side_item_id':'side','name':'Slaw'}]}
        with patch('app.services.free_side_checkout.quote_free_sides',return_value=plan),patch.object(service,'_order_for_intent',return_value=None),patch.object(service,'resolve_ordering_window',return_value={}),patch.object(service,'_check_kitchen_capacity'):
            with self.assertRaises(service.OrderPriceChanged) as raised:
                self.calculate(quote_only=False,payload={**self.payload,'expected_free_sides':[]})
        self.assertEqual(raised.exception.quote['free_sides'],plan['items'])

    def test_committed_intent_replays_before_repricing_or_balance_checks(self):
        order={'id':'committed','total_amount':2095}
        with patch.object(service,'_order_for_intent',return_value=order):
            self.assertEqual(self.calculate(quote_only=False,payload={**self.payload,'expected_total':2300,'payment_method':'wallet'}),order)

    def test_delivery_reward_can_be_saved_for_later(self):
        self.db.rows['profiles'][0]['next_order_free_delivery_cap']=100
        q=self.calculate(payload={**self.payload,'delivery_reward_id':'none'})
        self.assertEqual((q['delivery_fee'],q['total_amount']),(250,2095))
        self.assertEqual(q['available_delivery_rewards'][0]['id'],'legacy')
        self.assertEqual(self.db.rows['profiles'][0]['next_order_free_delivery_cap'],100)
    def test_choose_a_specific_delivery_win_instead_of_monthly_or_legacy(self):
        self.db.rows['profiles'][0]['next_order_free_delivery_cap']=100
        self.db.rows['system_settings']=[{'key':'tier_perk_ember_monthly_free_delivery','campus_id':None,'value':True}]
        self.db.rows['exclusive_spin_fulfillments']=[{'id':'second','user_id':'student','campus_id':CAMPUS,'status':'pending','prize_name':'Saved delivery','result_snapshot':{'prize_type':'free_delivery','reward_config':{'cap':200}}}]
        q=self.calculate(payload={**self.payload,'delivery_reward_id':'second'})
        self.assertEqual((q['delivery_fee'],q['total_amount']),(50,1895))
        self.assertEqual(q['delivery_benefit']['receipt_id'],'second')
        self.assertEqual(len(q['available_delivery_rewards']),3)
    def test_hp_bonus_can_be_saved_without_a_promise_to_apply_it(self):
        self.db.rows['profiles'][0]['next_order_hp_multiplier']=3
        q=self.calculate(payload={**self.payload,'hp_reward_id':'none'})
        self.assertEqual(q['hp_preview']['total_hp'],102)
        self.assertEqual(q['hp_bonus_plan'],{'source':'none','multiplier':1})
        self.assertEqual(q['available_hp_rewards'][0]['multiplier'],3)
    def test_customer_can_choose_a_specific_hp_win(self):
        self.db.rows['profiles'][0]['next_order_hp_multiplier']=2
        self.db.rows['exclusive_spin_fulfillments']=[{'id':'second','user_id':'student','campus_id':CAMPUS,'status':'pending','prize_name':'Triple','result_snapshot':{'prize_type':'hp_multiplier','reward_config':{'multiplier':3}}}]
        q=self.calculate(payload={**self.payload,'hp_reward_id':'second'})
        self.assertEqual(q['hp_preview']['total_hp'],306)
        self.assertEqual(q['hp_bonus_plan']['receipt_id'],'second')
        self.assertEqual(self.db.rows['profiles'][0]['next_order_hp_multiplier'],2)
    def test_missing_reward_does_not_silently_fall_back_to_auto(self):
        for field in ('hp_reward_id','delivery_reward_id'):
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'no longer available'):
                self.calculate(payload={**self.payload,field:'missing'})
    def test_changed_legacy_bonus_requires_review_before_admission(self):
        self.db.rows['profiles'][0]['next_order_hp_multiplier']=3
        with patch.object(service,'_order_for_intent',return_value=None),patch.object(service,'resolve_ordering_window',return_value={}),patch.object(service,'_check_kitchen_capacity'),self.assertRaises(service.OrderPriceChanged):
            self.calculate(quote_only=False,payload={**self.payload,'hp_reward_id':'legacy','expected_hp_bonus_plan':{'source':'legacy','multiplier':2}})
    def test_zero_hp_preserves_the_selected_bonus_for_later(self):
        self.db.rows['profiles'][0]['next_order_hp_multiplier']=2
        q=self.calculate(payload={**self.payload,'hp_reward_id':'legacy'},base_hp=0)
        self.assertEqual(q['hp_bonus_plan']['source'],'none')
        self.assertEqual(q['hp_preview']['total_hp'],0)
        self.assertEqual(self.db.rows['profiles'][0]['next_order_hp_multiplier'],2)

if __name__=='__main__':unittest.main()
