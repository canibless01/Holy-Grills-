"""Ingredient create replay and native-ledger contract; no provider/database calls."""
import unittest
from decimal import Decimal
from unittest.mock import MagicMock,patch
from flask import Flask,g
from app.routes import kitchen
from app.db import SupabaseError
A='11111111-1111-4111-8111-111111111111'; B='22222222-2222-4222-8222-222222222222'; U='33333333-3333-4333-8333-333333333333'; R='44444444-4444-4444-8444-444444444444'

class StockControlsTests(unittest.TestCase):
 def setUp(self):
  self.app=Flask(__name__);self.db=MagicMock();self.q=self.db.table.return_value
  for name in ('select','eq','single','order','limit','offset'):getattr(self.q,name).return_value=self.q
  self.q.execute.return_value=None
  self.q.insert.return_value.execute.return_value=[{'id':R}]
  self.body={'name':'  Flour  ','purchase_unit_id':U,'usage_unit_id':U,'conversion_factor':2,'low_stock_threshold':3,'campus_id':A,'request_id':R}
 def create(self,body=None,role='admin'):
  with self.app.test_request_context(method='POST',json=self.body if body is None else body),patch.object(kitchen,'get_user_client',return_value=self.db):
   g.user_id=U;g.user_role=role;g.campus_id=A
   return kitchen.create_stock_item.__wrapped__()
 def previous(self):return {'id':R,'name':'Flour','purchase_unit_id':U,'usage_unit_id':U,'conversion_factor':2,'low_stock_threshold':3,'campus_id':A,'current_balance':12}
 def test_create_scopes_own_campus_and_uses_intent_as_primary_key(self):
  _,status=self.create();self.assertEqual(status,201)
  saved=self.q.insert.call_args.args[0];self.assertEqual(saved['id'],R);self.assertEqual(saved['campus_id'],A);self.assertEqual(saved['name'],'Flour');self.assertEqual(saved['current_balance'],0)
 def test_super_create_uses_explicit_campus(self):
  _,status=self.create({**self.body,'campus_id':B},role='super_admin');self.assertEqual(status,201);self.assertEqual(self.q.insert.call_args.args[0]['campus_id'],B)
 def test_matching_response_loss_retry_returns_current_balance_without_insert(self):
  self.q.execute.return_value=self.previous();response,status=self.create();self.assertEqual(status,200);self.assertTrue(response.json['idempotent']);self.assertEqual(response.json['current_balance'],12);self.q.insert.assert_not_called()
 def test_conflicting_same_intent_does_not_change_existing_item(self):
  self.q.execute.return_value={**self.previous(),'name':'Different'};_,status=self.create();self.assertEqual(status,409);self.q.insert.assert_not_called()
 def test_concurrent_matching_primary_key_conflict_replays_winner(self):
  self.q.execute.side_effect=[None,self.previous()];self.q.insert.side_effect=SupabaseError('conflict',409,{'code':'23505'})
  response,status=self.create();self.assertEqual(status,200);self.assertTrue(response.json['idempotent'])
 def test_same_campus_name_conflict_is_clear(self):
  self.q.insert.side_effect=SupabaseError('conflict',409,{'code':'23505'});_,status=self.create();self.assertEqual(status,409)
 def test_invalid_create_fields_do_not_insert(self):
  for fields in ({'request_id':'wrong'},{'name':' '},{'conversion_factor':float('inf')},{'low_stock_threshold':-1},{'current_balance':1},{'purchase_unit_id':'bad'}):
   with self.subTest(fields=fields):_,status=self.create({**self.body,**fields});self.assertEqual(status,400)
  self.q.insert.assert_not_called()
 def test_adjustment_rejects_malformed_json_and_oversized_or_nontext_notes(self):
  for route in (kitchen.log_stock_purchase,kitchen.log_stock_usage):
   for body in ([1],True,{'quantity':2,'notes':{}},{'quantity':2,'notes':'x'*1001}):
    with self.subTest(route=route.__name__,body_type=type(body).__name__),self.app.test_request_context(method='POST',json=body),patch.object(kitchen,'get_db',return_value=self.db):
     _,status=route.__wrapped__(R);self.assertEqual(status,400)
  self.db.rpc.assert_not_called()
 def test_ledger_is_bounded_stably_ordered_and_reports_another_page(self):
  self.q.execute.return_value=[{'id':'a'},{'id':'b'},{'id':'c'}]
  with self.app.test_request_context('/?limit=2&offset=4'),patch.object(kitchen,'get_user_client',return_value=self.db),patch.object(kitchen,'fetch_or_403',return_value=({'id':R},None)):
   response,status=kitchen.get_stock_ledger.__wrapped__(R)
  self.assertEqual(status,200);self.assertEqual(response.json['ledger'],[{'id':'a'},{'id':'b'}]);self.assertTrue(response.json['has_more']);self.q.limit.assert_called_once_with(3);self.q.offset.assert_called_once_with(4)
  self.assertEqual(self.q.order.call_args_list,[unittest.mock.call('created_at',ascending=False),unittest.mock.call('id',ascending=False)])
  self.assertNotIn('email',self.q.select.call_args.args[0])
 def test_invalid_ledger_pages_are_rejected(self):
  for query in ('limit=0','limit=201','offset=-1','limit=x'):
   with self.subTest(query=query),self.app.test_request_context('/?'+query),patch.object(kitchen,'get_user_client',return_value=self.db),patch.object(kitchen,'fetch_or_403',return_value=({'id':R},None)):
    _,status=kitchen.get_stock_ledger.__wrapped__(R);self.assertEqual(status,400)

 def test_campus_admin_explicit_foreign_create_is_denied_before_insert(self):
  from werkzeug.exceptions import Forbidden
  with self.assertRaises(Forbidden):self.create({**self.body,'campus_id':B})
  self.q.insert.assert_not_called()

 def test_purchase_conversion_overflow_is_refused_before_rpc(self):
  with self.app.test_request_context(method='POST',json={'quantity':1e308}),patch.object(kitchen,'get_db',return_value=self.db),patch.object(kitchen,'fetch_or_403',return_value=({'campus_id':A,'conversion_factor':1e308,'purchase_unit_id':U},None)):
   g.user_id=U;g.user_role='admin';g.campus_id=A
   _,status=kitchen.log_stock_purchase.__wrapped__(R)
  self.assertEqual(status,400);self.db.rpc.assert_not_called()

 def test_decimal_purchase_uses_exact_numeric_rpc_argument(self):
  with self.app.test_request_context(method='POST',json={'quantity':0.1}),patch.object(kitchen,'get_db',return_value=self.db),patch.object(kitchen,'fetch_or_403',return_value=({'campus_id':A,'conversion_factor':3,'purchase_unit_id':U},None)),patch.object(kitchen,'_stock_adjustment',return_value=([{'new_balance':0.3}],None)) as adjust:
   g.user_id=U;g.user_role='admin';g.campus_id=A
   response,status=kitchen.log_stock_purchase.__wrapped__(R)
  self.assertEqual(status,200);self.assertEqual(Decimal(adjust.call_args.args[1]['p_delta_usage_units']),Decimal('0.3'));self.assertEqual(response.json['added_usage_units'],0.3)

 def edit(self,body=None,row=None,role='admin'):
  body=body if body is not None else {'name':'  Flour renamed  ','low_stock_threshold':5,'expected':{'name':'Flour','low_stock_threshold':3}}
  with self.app.test_request_context(method='PATCH',json=body),patch.object(kitchen,'get_user_client',return_value=self.db),patch.object(kitchen,'fetch_or_403',return_value=(row or self.previous(),None)):
   g.user_id=U;g.user_role=role;g.campus_id=A
   return kitchen.edit_stock_item.__wrapped__(R)

 def test_edit_compares_metadata_in_atomic_update_without_touching_accounting(self):
  self.q.update.return_value=[{**self.previous(),'name':'Flour renamed','low_stock_threshold':5}]
  response,status=self.edit();self.assertEqual(status,200);self.assertEqual(response.json['current_balance'],12)
  self.q.update.assert_called_once_with({'name':'Flour renamed','low_stock_threshold':5})
  self.assertEqual(self.q.eq.call_args_list,[unittest.mock.call('id',R),unittest.mock.call('name','Flour'),unittest.mock.call('low_stock_threshold',3)])

 def test_edit_matching_response_loss_retry_does_not_write_again(self):
  response,status=self.edit(row={**self.previous(),'name':'Flour renamed','low_stock_threshold':5})
  self.assertEqual(status,200);self.assertEqual(response.json['current_balance'],12);self.q.update.assert_not_called()

 def test_edit_stale_snapshot_and_concurrent_loser_are_conflicts(self):
  _,status=self.edit(row={**self.previous(),'name':'Someone else changed it'});self.assertEqual(status,409);self.q.update.assert_not_called()
  self.q.update.return_value=[];_,status=self.edit();self.assertEqual(status,409)

 def test_edit_denies_foreign_campus_but_super_admin_can_edit_it(self):
  from werkzeug.exceptions import Forbidden
  with self.assertRaises(Forbidden):self.edit(row={**self.previous(),'campus_id':B})
  self.q.update.assert_not_called();self.q.update.return_value=[self.previous()]
  _,status=self.edit(row={**self.previous(),'campus_id':B},role='super_admin');self.assertEqual(status,200)

 def test_edit_refuses_accounting_fields_and_invalid_snapshots(self):
  valid={'name':'Flour renamed','low_stock_threshold':5,'expected':{'name':'Flour','low_stock_threshold':3}}
  for body in ([1],{**valid,'conversion_factor':5},{**valid,'current_balance':100},{**valid,'campus_id':B},{**valid,'name':' '},{**valid,'low_stock_threshold':True},{**valid,'low_stock_threshold':float('inf')},{**valid,'low_stock_threshold':-1},{**valid,'low_stock_threshold':'5'},{**valid,'low_stock_threshold':10**400},{**valid,'expected':None},{**valid,'expected':{'name':'Flour'}}):
   with self.subTest(body=body):_,status=self.edit(body);self.assertEqual(status,400)
  self.q.update.assert_not_called()

 def test_edit_duplicate_and_database_failure_are_clear_without_details(self):
  for code,http,expected in [('23505',409,409),('42501',403,403),('XX000',500,503)]:
   with self.subTest(code=code):
    self.q.update.side_effect=SupabaseError('sensitive database detail',http,{'code':code})
    response,status=self.edit();self.assertEqual(status,expected);self.assertNotIn('sensitive',response.json['error'])

 def test_edit_preserves_missing_and_unavailable_lookup_responses(self):
  with self.app.test_request_context(method='PATCH',json={'name':'Flour','low_stock_threshold':5,'expected':{'name':'Flour','low_stock_threshold':3}}),patch.object(kitchen,'get_user_client',return_value=self.db):
   for status in (404,503):
    failure=(self.app.json.response({'error':'controlled'}),status)
    with patch.object(kitchen,'fetch_or_403',return_value=(None,failure)):
     _,actual=kitchen.edit_stock_item.__wrapped__(R);self.assertEqual(actual,status)
  self.q.update.assert_not_called()

 def archive(self,body=None,row=None,role='admin'):
  body=body if body is not None else {'archived':True,'expected_version':A,'request_id':R}
  with self.app.test_request_context(method='POST',json=body),patch.object(kitchen,'get_user_client',return_value=self.db),patch.object(kitchen,'fetch_or_403',return_value=(row or self.previous(),None)),patch.object(kitchen,'get_db',return_value=self.db):
   g.user_id=U;g.user_role=role;g.campus_id=A
   return kitchen.set_stock_archived.__wrapped__(R)

 def test_archive_passes_authenticated_actor_and_expected_version_to_private_rpc(self):
  self.db.rpc.return_value={'id':R,'archived_at':'2026-11-04T00:00:00Z','current_balance':12}
  response,status=self.archive();self.assertEqual(status,200);self.assertEqual(response.json['current_balance'],12)
  self.db.rpc.assert_called_once_with('hg_set_stock_archived',{'p_stock_item_id':R,'p_archived':True,'p_expected_version':A,'p_request_id':R,'p_actor_id':U})
  self.q.update.assert_not_called();self.q.delete.assert_not_called()

 def test_restore_is_explicit_false_not_truthiness(self):
  self.db.rpc.return_value={'id':R,'archived_at':None}
  _,status=self.archive({'archived':False,'expected_version':A,'request_id':R});self.assertEqual(status,200);self.assertIs(self.db.rpc.call_args.args[1]['p_archived'],False)

 def test_archive_denies_foreign_campus_and_accepts_super_admin(self):
  from werkzeug.exceptions import Forbidden
  with self.assertRaises(Forbidden):self.archive(row={**self.previous(),'campus_id':B})
  self.db.rpc.assert_not_called();self.db.rpc.return_value={'id':R}
  _,status=self.archive(row={**self.previous(),'campus_id':B},role='super_admin');self.assertEqual(status,200)

 def test_archive_rejects_malformed_intents_and_client_supplied_actor(self):
  valid={'archived':True,'expected_version':A,'request_id':R}
  for body in ([1],{**valid,'archived':'false'},{**valid,'expected_version':'bad'},{**valid,'request_id':None},{**valid,'p_actor_id':B},{'archived':True}):
   with self.subTest(body=body):_,status=self.archive(body);self.assertEqual(status,400)
  self.db.rpc.assert_not_called()

 def test_archive_rpc_failures_preserve_conflicts_permissions_and_not_found(self):
  for code,expected in [('23505',409),('23514',400),('42501',403),('P0002',404),('XX000',503)]:
   with self.subTest(code=code):
    self.db.rpc.side_effect=SupabaseError('private detail',500,{'code':code});response,status=self.archive();self.assertEqual(status,expected);self.assertNotIn('private',response.json['error'])

 def test_archived_adjustment_has_restore_guidance_and_conflict_status(self):
  self.db.rpc.side_effect=SupabaseError('archived',500,{'code':'55000'})
  with self.app.test_request_context():
   _,error=kitchen._stock_adjustment(self.db,{},None)
  response,status=error;self.assertEqual(status,409);self.assertIn('Restore',response.json['error'])

 def test_list_stock_state_is_explicit_and_scoped(self):
  self.q.is_.return_value=self.q;self.q.not_=self.q;self.q.execute.return_value=[]
  for state in ('active','archived','all','bad'):
   self.q.reset_mock()
   with self.subTest(state=state),self.app.test_request_context('/?state='+state+'&campus_id='+A),patch.object(kitchen,'get_user_client',return_value=self.db):
    g.user_id=U;g.user_role='admin';g.campus_id=A
    _,status=kitchen.list_stock_items.__wrapped__()
   self.assertEqual(status,400 if state=='bad' else 200)
   if state in ('active','archived'):self.q.is_.assert_called_once_with('archived_at','null')
   if state=='all':self.q.is_.assert_not_called()
   if state!='bad':self.q.eq.assert_called_once_with('campus_id',A)
