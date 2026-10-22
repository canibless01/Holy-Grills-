import unittest
from unittest.mock import patch,MagicMock
import requests
from app.utils import email
from app.services import notification_service as notifications

class EmailQuotaFallback(unittest.TestCase):
 def reply(self,status,body=None):
  r=MagicMock();r.status_code=status;r.json.return_value=body or {};return r
 def run_send(self,resend,onesignal,*,provider='resend',headers=None):
  with patch.object(email,'_resend_api_key',return_value='test-resend'),patch.object(notifications,'_get_onesignal_creds',return_value=('test-app','test-key')),patch.object(email.requests,'post',side_effect=resend) as first,patch.object(notifications,'_onesignal_email_post',side_effect=onesignal) as second:
   result=email.send_email_routed('audit@example.invalid','Audit','Subject','<p>Body</p>',provider=provider,headers=headers)
   return result,first,second
 def test_resend_success_never_uses_other_provider(self):
  ok,first,second=self.run_send([self.reply(200)],[]);self.assertTrue(ok);self.assertEqual(first.call_count,1);second.assert_not_called()
 def test_resend_quota_falls_back_once_with_same_message(self):
  ok,first,second=self.run_send([self.reply(429)],[self.reply(202)]);self.assertTrue(ok);self.assertEqual((first.call_count,second.call_count),(1,1));self.assertEqual(first.call_args.kwargs['json']['html'],second.call_args.kwargs['payload']['email_body'])
 def test_structured_quota_rejection_falls_back(self):
  ok,_,second=self.run_send([self.reply(403,{'name':'daily_quota_exceeded'})],[self.reply(200)]);self.assertTrue(ok);self.assertEqual(second.call_count,1)
 def test_onesignal_monthly_quota_uses_resend(self):
  ok,first,second=self.run_send([self.reply(201)],[self.reply(400,{'errors':['You have exceeded your monthly email limit']})],provider='onesignal');self.assertTrue(ok);self.assertEqual((first.call_count,second.call_count),(1,1))
 def test_timeout_or_unknown_failure_never_crosses_provider(self):
  for failure in (requests.Timeout('unknown'),self.reply(500),self.reply(401),self.reply(422),self.reply(403,{'name':'validation_error'})):
   with self.subTest(failure=type(failure).__name__):
    ok,first,second=self.run_send([failure],[]);self.assertFalse(ok);self.assertEqual(first.call_count,1);second.assert_not_called()
 def test_onesignal_timeout_does_not_fallback_or_retry(self):
  ok,first,second=self.run_send([],[requests.Timeout('unknown')],provider='onesignal');self.assertFalse(ok);first.assert_not_called();self.assertEqual(second.call_count,1)
 def test_both_quotas_fail_without_loop(self):
  ok,first,second=self.run_send([self.reply(429)],[self.reply(429)]);self.assertFalse(ok);self.assertEqual((first.call_count,second.call_count),(1,1))
 def test_unsubscribe_headers_are_preserved_not_silently_dropped(self):
  headers={'List-Unsubscribe':'<https://example.invalid/unsubscribe>'}
  ok,first,second=self.run_send([self.reply(429)],[],headers=headers);self.assertFalse(ok);second.assert_not_called();self.assertEqual(first.call_args.kwargs['json']['headers'],headers)
 def test_raw_guest_and_qr_sender_enters_quota_router(self):
  with patch.object(email,'send_email_routed',return_value=True) as route:
   self.assertTrue(email.send_email_raw('audit@example.invalid','Audit','Subject','Body'));self.assertEqual(route.call_args.kwargs['provider'],'resend')
 def test_notification_override_uses_same_router(self):
  with patch.object(email,'get_user_email_and_name',return_value=('audit@example.invalid','Audit')),patch.object(notifications,'get_email_provider',return_value='onesignal'),patch.object(email,'send_email_routed',return_value=True) as route:
   notifications._dispatch_email_async('user','Subject','Body','receipt');self.assertEqual(route.call_args.kwargs['provider'],'onesignal')
 def test_one_signal_direct_wrapper_uses_router_without_recursion(self):
  with patch.object(email,'send_email_routed',return_value=True) as route:
   self.assertTrue(notifications._dispatch_email_via_onesignal('audit@example.invalid','Audit','Subject','Body'));self.assertEqual(route.call_args.kwargs['provider'],'onesignal')
