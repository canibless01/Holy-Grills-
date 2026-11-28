"""Preview and writes share real economics, without touching live catalogue rows."""
import copy,inspect,unittest
from contextlib import ExitStack
from unittest.mock import patch,MagicMock
from flask import Flask,g
from app.routes import rewards
from app.services import economics_service as econ

class Query:
    def __init__(self,db,table):self.db,self.table,self.filters=db,table,{}
    def select(self,*args):return self
    def eq(self,k,v):self.filters[k]=v;return self
    def single(self):return self
    def execute(self):return copy.deepcopy(self.db.row) if self.table=='rewards' else []
    def update(self,data):
        if any(self.db.row.get(key)!=value for key,value in self.filters.items()):return []
        self.db.writes.append(copy.deepcopy(data));self.db.row.update(data);return [copy.deepcopy(self.db.row)]
    def insert(self,data):self.db.writes.append(copy.deepcopy(data));return [copy.deepcopy(data)]
class DB:
    def __init__(self):
        self.row={'id':'reward','name':'Existing meal','campus_id':'campus','reward_type':'food','food_cost':500,'packaging_cost':100,'menu_price':2000,'margin_share_pct':.4,'hp_cost':1234,'updated_at':'stamp-1'}
        self.writes=[]
    def table(self,table):return Query(self,table)
class RewardEconomicsTests(unittest.TestCase):
    def setUp(self):self.app=Flask(__name__);self.db=DB()
    def call(self,fn,data,*args):
        with ExitStack() as stack:
            stack.enter_context(self.app.test_request_context('/',method='POST',json=data))
            stack.enter_context(patch.object(rewards,'get_user_client',return_value=self.db))
            stack.enter_context(patch.object(econ,'get_hp_value',return_value=.75))
            stack.enter_context(patch.object(econ,'_get_econ_setting',side_effect=lambda db,key,default:1 if key=='hp_rounding' else default))
            stack.enter_context(patch.object(rewards,'send_notification'))
            g.user_id='admin';g.user_role='admin';g.campus_id='campus'
            return inspect.unwrap(fn)(*args)
    def food(self,**extras):return {'reward_type':'food','food_cost':500,'packaging_cost':100,'menu_price':2000,'margin_share_pct':.4,**extras}
    def test_preview_matches_create_price_and_naira_liability(self):
        preview,status=self.call(rewards.preview_reward_economics,self.food(hp_cost=1));self.assertEqual(status,200);self.assertEqual(preview.json['hp_cost'],1547);self.assertEqual(self.db.writes,[])
        created,status=self.call(rewards.create_reward,self.food(name='New meal',fulfillment_type='menu_item'));self.assertEqual(status,201)
        for key in ('hp_cost','reward_value','hp_liability'):self.assertEqual(created.json[key],preview.json[key])
    def test_partial_cost_update_uses_retained_basis_and_reprices(self):
        result,status=self.call(rewards.update_reward,{'food_cost':600},'reward');self.assertEqual(status,200);self.assertEqual(result.json['hp_cost'],1627);self.assertEqual(result.json['hp_liability'],1220.25)
    def test_name_or_equivalent_cost_edit_keeps_saved_price(self):
        for data in ({'name':'Renamed'},{'food_cost':'500'}):
            result,status=self.call(rewards.update_reward,data,'reward');self.assertEqual(status,200);self.assertEqual(result.json['hp_cost'],1234)
    def test_merch_type_uses_merch_cost_even_if_old_food_cost_remains(self):
        body=self.food(reward_type='merch',production_cost=400,perceived_value=2000,margin_share_pct=.5)
        result,status=self.call(rewards.preview_reward_economics,body);self.assertEqual(status,200);self.assertEqual(result.json['reward_value'],1250)
    def test_missing_inputs_are_not_a_zero_price(self):
        result,status=self.call(rewards.preview_reward_economics,{'reward_type':'food'});self.assertEqual(status,200);self.assertEqual(result.json,{'complete':False})
    def test_invalid_costs_refuse_before_writes(self):
        for fields in ({'food_cost':True},{'food_cost':-1},{'margin_share_pct':40},{'food_cost':'NaN'}):
            result,status=self.call(rewards.preview_reward_economics,self.food(**fields));self.assertEqual(status,400);self.assertEqual(self.db.writes,[])
    def test_invalid_partial_edit_never_saves(self):
        for fields in ({'food_cost':True},{'menu_price':'NaN'},{'food_cost':-1}):
            result,status=self.call(rewards.update_reward,fields,'reward');self.assertEqual(status,400);self.assertFalse(self.db.writes)
    def test_configuration_outage_refuses_preview(self):
        with patch.object(rewards,'_apply_reward_economics',side_effect=RuntimeError('config offline')):
            result,status=self.call(rewards.preview_reward_economics,self.food())
        self.assertEqual(status,503);self.assertNotIn('offline',result.json['error']);self.assertFalse(self.db.writes)
    def test_public_preview_is_not_an_unauthenticated_pricing_api(self):
        self.app.register_blueprint(rewards.rewards_bp,url_prefix='/api/rewards')
        response=self.app.test_client().post('/api/rewards/admin/economics-preview',json=self.food());self.assertEqual(response.status_code,401)

    def test_invalid_form_fields_never_write(self):
        for values in ({'name':''},{'stock_quantity':-1},{'stock_quantity':True},{'hp_cost':0},{'hp_cost':float('inf')},{'reward_type':'free_item'}):
            result,status=self.call(rewards.update_reward,values,'reward');self.assertEqual(status,400);self.assertFalse(self.db.writes)
    def test_create_pricing_outage_is_retryable_without_insert(self):
        with patch.object(rewards,'_apply_reward_economics',side_effect=RuntimeError('offline')):
            result,status=self.call(rewards.create_reward,self.food(name='Meal'))
        self.assertEqual(status,503);self.assertFalse(self.db.writes)

    def test_clearing_optional_packaging_matches_preview_and_update(self):
        expected,status=self.call(rewards.preview_reward_economics,self.food(packaging_cost=None));self.assertEqual(status,200)
        actual,status=self.call(rewards.update_reward,{'packaging_cost':None},'reward');self.assertEqual(status,200)
        self.assertEqual(actual.json['hp_cost'],expected.json['hp_cost']);self.assertEqual(actual.json['hp_cost'],1467)

    def test_stale_editor_is_rejected_before_price_or_write(self):
        result,status=self.call(rewards.update_reward,{'food_cost':600,'expected_updated_at':'older-version'},'reward')
        self.assertEqual(status,409);self.assertFalse(self.db.writes)
    def test_concurrent_change_after_read_refuses_stale_derived_price(self):
        original=rewards._apply_reward_economics
        def race(db,data):
            result=original(db,data);self.db.row['updated_at']='other-admin-version';return result
        with patch.object(rewards,'_apply_reward_economics',side_effect=race):
            result,status=self.call(rewards.update_reward,{'food_cost':600},'reward')
        self.assertEqual(status,409);self.assertFalse(self.db.writes)
