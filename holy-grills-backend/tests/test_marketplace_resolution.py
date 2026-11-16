"""HTTP boundaries; native SQL proofs cover financial conservation separately."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import marketplace as routes
from app.db import SupabaseError
ACTOR='bc200000-0000-4000-8000-000000000001'
PURCHASE='bc200000-0000-4000-8000-000000000002'
REPORT='bc200000-0000-4000-8000-000000000003'
class MarketplaceResolutionTests(unittest.TestCase):
 def setUp(self):
  self.app=Flask(__name__);self.db=MagicMock()
  self.purchase={'id':PURCHASE,'user_id':ACTOR,'status':'pending','marketplace_listings':{'title':'Owned listing'}}
  self.report={'id':REPORT,'purchase_id':PURCHASE,'user_id':ACTOR,'status':'open'}
  def table(name):
   q=MagicMock();q.select.return_value.eq.return_value.single.return_value.execute.return_value=self.report if name=='marketplace_purchase_reports' else self.purchase
   return q
  self.db.table.side_effect=table
 def test_actor_and_reference_bound_on_server(self):
  self.db.rpc.return_value={'status':'refunded'}
  with self.app.test_request_context(),patch.object(routes,'get_db',return_value=self.db):
   g.user_id=ACTOR
   _,failure=routes._resolve_marketplace_transaction(PURCHASE,'refund',REPORT,'Reviewed')
   self.assertIsNone(failure)
   args=self.db.rpc.call_args.args[1]
   self.assertEqual((args['p_actor_id'],args['p_purchase_id'],args['p_report_id']),(ACTOR,PURCHASE,REPORT))
 def test_expected_database_failure_statuses(self):
  for marker,status in [('marketplace_forbidden',403),('marketplace_conflict',409),('marketplace_no_codes',409),('marketplace_legacy_refund_review',409),('marketplace_not_found',404)]:
   with self.subTest(marker=marker),self.app.test_request_context(),patch.object(routes,'get_db',return_value=self.db):
    g.user_id=ACTOR;self.db.rpc.side_effect=SupabaseError('RPC rejected',details={'message':marker})
    receipt,failure=routes._resolve_marketplace_transaction(PURCHASE,'refunded')
    self.assertIsNone(receipt);self.assertEqual(failure[1],status)
 def test_missing_receipt_is_retryable(self):
  with self.app.test_request_context(),patch.object(routes,'get_db',return_value=self.db):
   g.user_id=ACTOR;self.db.rpc.return_value={}
   self.assertEqual(routes._resolve_marketplace_transaction(PURCHASE,'refunded')[1][1],503)
 def test_invalid_body_never_starts_transaction(self):
  for body in ([],{'status':['refunded']},{'status':'refunded','admin_note':{}},{'status':'refunded','admin_note':'x'*1001}):
   with self.subTest(body_type=type(body).__name__),self.app.test_request_context(method='PATCH',json=body),patch.object(routes,'get_user_client',return_value=self.db),patch.object(routes,'get_db') as svc:
    g.user_id=ACTOR
    self.assertEqual(routes.admin_update_purchase.__wrapped__(PURCHASE)[1],400);svc.assert_not_called()
 def test_refund_replay_does_not_repeat_notification(self):
  self.db.rpc.return_value={'status':'refunded','replayed':True}
  with self.app.test_request_context(method='PATCH',json={'status':'refunded'}),patch.object(routes,'get_user_client',return_value=self.db),patch.object(routes,'get_db',return_value=self.db),patch('app.services.notification_service.send_notification') as notify:
   g.user_id=ACTOR;response,status=routes.admin_update_purchase.__wrapped__(PURCHASE)
   self.assertEqual(status,200);self.assertTrue(response.json['replayed']);notify.assert_not_called()
 def test_closed_report_retry_reaches_atomic_receipt(self):
  self.report['status']='replaced';self.db.rpc.return_value={'status':'replaced','replayed':True}
  with self.app.test_request_context(method='PATCH',json={'action':'replace'}),patch.object(routes,'get_user_client',return_value=self.db),patch.object(routes,'get_db',return_value=self.db),patch('app.services.notification_service.send_notification') as notify:
   g.user_id=ACTOR;response,status=routes.admin_resolve_report.__wrapped__(REPORT)
   self.assertEqual(status,200);self.assertTrue(response.json['replayed']);self.db.rpc.assert_called_once();notify.assert_not_called()
