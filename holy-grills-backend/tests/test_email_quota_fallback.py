import unittest
from unittest.mock import patch,MagicMock
import requests
from app.utils import email
from app.services import notification_service as notifications

class EmailQuotaFallback(unittest.TestCase):
 def reply(self,status,body=None):
  r=MagicMock();r.status_code=status;r.json.return_value=({'id':'controlled-message','recipients':1} if body is None else body);return r
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
 def test_unsubscribe_headers_reach_resend_and_the_fallback_is_marketing(self):
  # A newsletter keeps its List-Unsubscribe headers on the Resend attempt. When
  # Resend is out of quota the message still goes out via OneSignal, but as a
  # marketing send (no include_unsubscribed), so OneSignal's own unsubscribe wins.
  headers={'List-Unsubscribe':'<https://example.invalid/unsubscribe>'}
  ok,first,second=self.run_send([self.reply(429)],[self.reply(202)],headers=headers)
  self.assertTrue(ok);self.assertEqual(first.call_args.kwargs['json']['headers'],headers)
  self.assertNotIn('include_unsubscribed',second.call_args.kwargs['payload'])
 def test_header_less_mail_is_treated_as_transactional(self):
  # send_email_raw leaves the category to the router: no List-Unsubscribe header
  # means transactional, so OneSignal delivers it even to an unsubscribed address.
  with patch.object(email,'send_email_routed',return_value=True) as route:
   email.send_email_raw('a@example.invalid','Audit','Subject','Body')
  self.assertIsNone(route.call_args.kwargs['transactional'])
  ok,first,second=self.run_send([],[self.reply(200,{'id':'message'})],provider='onesignal')
  self.assertTrue(ok);self.assertTrue(second.call_args.kwargs['payload']['include_unsubscribed'])
 def test_raw_guest_and_qr_sender_enters_the_quota_router(self):
  with patch.object(email,'send_email_routed',return_value=True) as route:
   self.assertTrue(email.send_email_raw('audit@example.invalid','Audit','Subject','Body'))
  # provider=None: the configured default decides (OneSignal, falling back to Resend).
  self.assertIsNone(route.call_args.kwargs['provider'])
 def test_notification_override_uses_same_router(self):
  with patch.object(email,'get_user_email_and_name',return_value=('audit@example.invalid','Audit')),patch.object(notifications,'get_email_provider',return_value='onesignal'),patch.object(email,'send_email_routed',return_value=True) as route:
   notifications._dispatch_email_async('user','Subject','Body','receipt');self.assertEqual(route.call_args.kwargs['provider'],'onesignal')
 def test_one_signal_direct_wrapper_uses_router_without_recursion(self):
  with patch.object(email,'send_email_routed',return_value=True) as route:
   self.assertTrue(notifications._dispatch_email_via_onesignal('audit@example.invalid','Audit','Subject','Body'));self.assertEqual(route.call_args.kwargs['provider'],'onesignal')

 def test_zero_recipients_is_a_miss_and_uses_the_other_provider(self):
  # Accepted by OneSignal but delivered to nobody (no email subscription): nothing
  # was sent, so the alternate provider cannot duplicate — it delivers the mail the
  # customer was otherwise never going to get.
  ok,first,second=self.run_send([self.reply(200)],[self.reply(200,{'id':'message','recipients':0})],provider='onesignal')
  self.assertTrue(ok);self.assertEqual((first.call_count,second.call_count),(1,1))
 def test_error_body_on_a_2xx_is_a_miss(self):
  ok,first,second=self.run_send([self.reply(200)],[self.reply(202,{'id':'message','errors':['All included players are not subscribed']})],provider='onesignal')
  self.assertTrue(ok);self.assertEqual((first.call_count,second.call_count),(1,1))
 def test_missing_message_id_stays_ambiguous_and_never_crosses_provider(self):
  for payload in ({'recipients':1},{},{}):
   with self.subTest(payload=payload):
    ok,first,second=self.run_send([],[self.reply(200,payload)],provider='onesignal')
    self.assertFalse(ok);first.assert_not_called();self.assertEqual(second.call_count,1)
 def test_message_id_without_a_recipients_field_is_delivered(self):
  # OneSignal does not always echo `recipients`; requiring it turned a successful
  # send into a silent failure.
  ok,first,second=self.run_send([],[self.reply(200,{'id':'message'})],provider='onesignal')
  self.assertTrue(ok);first.assert_not_called();self.assertEqual(second.call_count,1)
 def test_resend_success_requires_message_id(self):
  ok,first,second=self.run_send([self.reply(200,{})],[])
  self.assertFalse(ok);second.assert_not_called()
