"""Guest proof, account boundaries and committed ownership recovery."""
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from flask import Flask,g
from app.routes import orders

OID='bbbb0000-0000-4000-8000-000000000099'
TOKEN='cccc0000-0000-4000-8000-000000000099'
USER='aaaa0000-0000-4000-8000-000000000099'

class GuestClaimTests(unittest.TestCase):
 def setUp(self):
  self.app=Flask(__name__);self.db=MagicMock()
  self.db.rpc.return_value={'success':True,'order_id':OID,'replayed':False}
  self.row={'id':OID,'user_id':USER,'status':'received','payment_status':'paid'}
  self.db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value=self.row
 def call(self,body=None,role='student'):
  with self.app.test_request_context(method='POST',json=body),patch.object(orders,'get_db',return_value=self.db):
   g.user_id=USER;g.user_role=role;g.campus_id='campus'
   return inspect.unwrap(orders.claim_guest_order)(OID)
 def test_verified_caller_not_body_supplied_identity(self):
  response,status=self.call({'claim_token':TOKEN,'user_id':'other'})
  self.assertEqual(status,200)
  self.db.rpc.assert_called_once_with('claim_guest_order',{'p_order_id':OID,'p_user_id':USER,'p_claim_token':TOKEN})
 def test_staff_cannot_claim_customer_guest_orders(self):
  for role in ('admin','super_admin','kitchen','rider'):
   with self.subTest(role=role):self.assertEqual(self.call({'claim_token':TOKEN},role)[1],403)
  self.db.rpc.assert_not_called()
 def test_malformed_json_or_token_never_calls_database(self):
  for body in (None,[],{}, {'claim_token':True},{'claim_token':'not-a-token'}):
   with self.subTest(body=body):self.assertEqual(self.call(body)[1],400)
  self.db.rpc.assert_not_called()
 def test_conflicts_and_restrictions_do_not_become_success(self):
  for code,status in [('invalid_claim',403),('already_claimed',409),('campus_mismatch',403),('payment_pending',409),('forbidden',403),('order_not_found',404)]:
   with self.subTest(code=code):
    self.db.rpc.return_value={'error':code};response,actual=self.call({'claim_token':TOKEN});self.assertEqual(actual,status);self.assertNotIn('success',response.json)
 def test_own_replay_succeeds(self):
  self.db.rpc.return_value={'success':True,'order_id':OID,'replayed':True}
  response,status=self.call({'claim_token':TOKEN});self.assertEqual(status,200);self.assertTrue(response.json['replayed'])
 def test_database_failure_returns_unavailable_without_raw_detail(self):
  self.db.rpc.side_effect=RuntimeError('private DB detail')
  response,status=self.call({'claim_token':TOKEN});self.assertEqual(status,503);self.assertNotIn('private',response.json['error'])
 def test_committed_claim_survives_reward_recovery_outage(self):
  self.row.update(status='delivered',hp_credited_at=None)
  with patch('app.services.order_service._handle_delivery_rewards',side_effect=RuntimeError('offline')):
   response,status=self.call({'claim_token':TOKEN})
  self.assertEqual(status,200);self.assertTrue(response.json['success']);self.assertTrue(response.json['rewards_pending'])
 def test_delivered_retry_invokes_idempotent_reward_recovery(self):
  self.row.update(status='delivered',hp_credited_at=None)
  with patch('app.services.order_service._handle_delivery_rewards') as recover:
   response,status=self.call({'claim_token':TOKEN})
  self.assertEqual(status,200);recover.assert_called_once_with(self.row)

class GuestTrackingLookupTests(unittest.TestCase):
 def setUp(self):self.app=Flask(__name__);self.db=MagicMock()
 def call(self,number,token=TOKEN,row=None):
  self.db.table.return_value.select.return_value.ilike.return_value.limit.return_value.single.return_value.execute.return_value=row
  detail=MagicMock(return_value=('detail',200))
  with self.app.test_request_context('/?order_number='+number+'&claim_token='+str(token)),patch.object(orders,'get_db',return_value=self.db),patch.object(orders,'get_order',SimpleNamespace(__wrapped__=detail)):
   g.user_id=None
   result=inspect.unwrap(orders.track_guest_order)()
  return result,detail
 def test_displayed_number_resolves_only_with_matching_guest_proof(self):
  result,detail=self.call('HG-123',row={'id':OID,'user_id':None,'claim_token':TOKEN})
  self.assertEqual(result,('detail',200));detail.assert_called_once_with(OID)
 def test_wrong_token_owned_order_and_missing_number_are_indistinguishable(self):
  for row in (None,{'id':OID,'user_id':None,'claim_token':'wrong'},{'id':OID,'user_id':USER,'claim_token':TOKEN}):
   result,detail=self.call('HG-123',row=row);self.assertEqual(result[1],404);detail.assert_not_called()
 def test_full_uuid_delegates_to_existing_owner_or_token_guards(self):
  result,detail=self.call(OID);detail.assert_called_once_with(OID)
 def test_malformed_numbers_do_not_become_wildcard_queries(self):
  for number in ('HG%25','HG_1',''):
   result,detail=self.call(number);self.assertEqual(result[1],404);detail.assert_not_called()
 def test_invalid_token_cannot_lookup_number(self):
  result,detail=self.call('HG-123',token='invalid');self.assertEqual(result[1],403);detail.assert_not_called()
