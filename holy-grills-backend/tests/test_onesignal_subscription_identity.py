"""The subscription bug that wasted a day: identity, staleness, and defaults.

Three findings from production, each with a test here:

1. **Invalid identifier.** OneSignal keys an Email subscription by its token, so
   `grillthevibe@gmail.com ` (trailing space) or `a@b.com,` (pasted list) is a
   *different* address. The dashboard showed a subscription OneSignal flagged as
   invalid, and every send to the clean form was refused. Addresses are now
   normalised at every boundary.
2. **Stale unsubscribed subscriptions.** An earlier build created them with
   `enabled=False` for accounts that had promotions off; later sign-ins never fixed
   it, so OneSignal refused every send and Resend delivered instead. Creating again
   now flips the subscription back on.
3. **OneSignal is the default transport.** Resend's 100/day is the scarce resource,
   so it should be the fallback, not the starting point.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

for _name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "JWT_SECRET", "SECRET_KEY"):
    os.environ.setdefault(_name, "https://example.supabase.co" if _name == "SUPABASE_URL" else "test")

from app.services import notification_service as notifications
from app.services import onesignal_email, email_usage
from app.utils import email
from app.utils.validators import normalize_email


def _reply(status, body=None):
    response = MagicMock()
    response.status_code = status
    response.text = "body"
    response.content = b"{}"
    response.ok = 200 <= status < 300
    response.json.return_value = body if body is not None else {}
    return response


class NormalisationTests(unittest.TestCase):
    def test_surrounding_junk_is_trimmed(self):
        for raw in (" GrillTheVibe@Gmail.com ", "grillthevibe@gmail.com,", '"grillthevibe@gmail.com"',
                    "<grillthevibe@gmail.com>"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_email(raw), "grillthevibe@gmail.com")

    def test_a_list_or_a_typo_is_not_an_address(self):
        for raw in ("a@b.com;c@d.com", "a@b.com c@d.com", "bad", "", None, "a@@b.com", "a@b"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_email(raw))

    def test_the_payload_carries_the_canonical_token(self):
        payload = email._onesignal_email_payload("app", "  GrillTheVibe@Gmail.com ",
                                                 "Subject", "<p>x</p>", True)
        self.assertEqual(payload["include_email_tokens"], ["grillthevibe@gmail.com"])

    def test_the_transport_refuses_a_malformed_address(self):
        receipt = {}
        accepted, _, _ = email._email_attempt("onesignal", "a@b.com;c@d.com", "N", "S", "<p>x</p>",
                                              receipt=receipt)
        self.assertFalse(accepted)
        self.assertEqual(receipt["state"], "skipped")
        self.assertEqual(receipt["error"], "invalid_email_address")

    def test_a_subscription_is_never_created_for_a_malformed_address(self):
        details = {}
        created = {"subscription": {"id": "sub-1", "type": "Email", "enabled": True}}
        with patch.object(onesignal_email, "_creds", return_value=("app", "key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(201), _reply(200, created)]) as post:
            linked = onesignal_email.ensure_email_subscription("u1", "a@b.com ", details=details)
        self.assertTrue(linked)                                  # trailing space is trimmed, not fatal
        self.assertEqual(post.call_args_list[1].kwargs["json"]["subscription"]["token"], "a@b.com")
        details = {}
        with patch.object(onesignal_email, "_creds", return_value=("app", "key")), \
             patch.object(onesignal_email.requests, "post") as post:
            self.assertFalse(onesignal_email.ensure_email_subscription("u1", "a@b.com;c@d.com",
                                                                       details=details))
        post.assert_not_called()
        self.assertEqual(details["reason"], "missing_user_or_invalid_email")


class StaleSubscriptionTests(unittest.TestCase):
    def test_an_existing_unsubscribed_subscription_is_switched_back_on(self):
        details = {}
        created = {"subscription": {"id": "sub-1", "type": "Email", "enabled": False,
                                    "token": "a@example.invalid"}}
        with patch.object(onesignal_email, "_creds", return_value=("app", "key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(201), _reply(200, created)]) as post, \
             patch.object(onesignal_email.requests, "patch",
                          return_value=_reply(200, {})) as patch_request:
            linked = onesignal_email.ensure_email_subscription("u1", "a@example.invalid",
                                                               enabled=True, details=details)
        self.assertTrue(linked)
        self.assertTrue(details["repaired"])
        patch_request.assert_called_once()
        url = patch_request.call_args.args[0]
        self.assertTrue(url.endswith("/apps/app/subscriptions/sub-1"))
        self.assertEqual(patch_request.call_args.kwargs["json"], {"subscription": {"enabled": True}})

    def test_an_explicit_opt_out_is_not_repaired(self):
        details = {}
        created = {"subscription": {"id": "sub-1", "type": "Email", "enabled": False}}
        with patch.object(onesignal_email, "_creds", return_value=("app", "key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(201), _reply(200, created)]), \
             patch.object(onesignal_email.requests, "patch") as patch_request:
            onesignal_email.ensure_email_subscription("u1", "a@example.invalid",
                                                      enabled=False, details=details)
        patch_request.assert_not_called()

    def test_an_already_exists_409_finds_the_subscription_and_enables_it(self):
        details = {}
        existing = {"subscriptions": [{"id": "sub-9", "type": "Email", "token": "a@example.invalid",
                                       "enabled": False}]}
        with patch.object(onesignal_email, "_creds", return_value=("app", "key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(201), _reply(409, {})]), \
             patch.object(onesignal_email.requests, "get", return_value=_reply(200, existing)), \
             patch.object(onesignal_email.requests, "patch", return_value=_reply(200, {})) as patch_request:
            linked = onesignal_email.ensure_email_subscription("u1", "a@example.invalid",
                                                               details=details)
        self.assertTrue(linked)
        self.assertEqual(details["subscription_id"], "sub-9")
        patch_request.assert_called_once()

    def test_a_healthy_subscription_costs_no_extra_call(self):
        created = {"subscription": {"id": "sub-1", "type": "Email", "enabled": True}}
        with patch.object(onesignal_email, "_creds", return_value=("app", "key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(201), _reply(200, created)]), \
             patch.object(onesignal_email.requests, "patch") as patch_request:
            self.assertTrue(onesignal_email.ensure_email_subscription("u1", "a@example.invalid"))
        patch_request.assert_not_called()


class DefaultProviderTests(unittest.TestCase):
    def test_onesignal_is_the_default_when_it_is_configured(self):
        with patch.object(notifications, "_get_onesignal_creds", return_value=("app", "key")):
            self.assertEqual(notifications._configured_default_provider(), "onesignal")

    def test_resend_is_the_default_when_onesignal_is_not_configured(self):
        with patch.object(notifications, "_get_onesignal_creds", return_value=("", "")):
            self.assertEqual(notifications._configured_default_provider(), "resend")

    def test_an_explicit_setting_still_wins(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = {
            "value": "resend"}
        with patch.object(notifications, "get_db", return_value=db), \
             patch.object(notifications, "_get_onesignal_creds", return_value=("app", "key")):
            self.assertEqual(notifications.get_email_provider(scope="blast"), "resend")

    def test_the_router_uses_the_default_when_no_provider_is_named(self):
        with patch.object(email, "_default_provider", return_value="onesignal"), \
             patch.object(email_usage, "reserve", return_value=1), \
             patch.object(email, "_email_attempt", return_value=(True, False, False)) as attempt:
            email.send_email_routed("a@example.invalid", "A", "S", "<p>b</p>")
        self.assertEqual(attempt.call_args.args[0], "onesignal")


class UnsubscribeComplianceTests(unittest.TestCase):
    """A fallback must never deliver marketing mail to someone who unsubscribed."""

    def _route(self, onesignal_reply, resend_reply, transactional):
        with patch.object(notifications, "_get_onesignal_creds", return_value=("app", "key")), \
             patch.object(email, "_resend_api_key", return_value="key"), \
             patch.object(notifications, "_onesignal_email_post", return_value=onesignal_reply) as os_post, \
             patch.object(email.requests, "post", return_value=resend_reply) as resend_post, \
             patch.object(email_usage, "reserve", return_value=1), \
             patch.object(email_usage, "release"), \
             patch.object(email, "_heal_missing_subscription", return_value=False):
            receipt = {}
            result = email.send_email_routed("a@example.invalid", "A", "S", "<p>b</p>",
                                             provider="onesignal", receipt=receipt,
                                             transactional=transactional)
        return result, receipt, os_post, resend_post

    def test_marketing_mail_is_skipped_not_re_routed(self):
        result, receipt, _, resend_post = self._route(
            _reply(200, {"errors": ["All included players are not subscribed"]}), _reply(200),
            transactional=False)
        self.assertFalse(result)
        resend_post.assert_not_called()
        self.assertEqual(receipt["state"], "skipped")
        self.assertEqual(receipt["skipped_reason"], "unsubscribed")

    def test_transactional_mail_still_uses_the_fallback(self):
        result, _, _, resend_post = self._route(
            _reply(200, {"errors": ["All included players are not subscribed"]}),
            _reply(200, {"id": "m-1", "recipients": 1}),
            transactional=True)
        self.assertTrue(result)
        resend_post.assert_called_once()


class DeliveringProviderRecordTests(unittest.TestCase):
    def _record(self, receipt, columns_available=True):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = []
        if not columns_available:
            def insert(payload):
                if "provider" in payload:
                    raise RuntimeError("column notification_deliveries.provider does not exist")
                return None
            db.table.return_value.insert.return_value.execute.side_effect = insert
        with patch.object(notifications, "get_db", return_value=db):
            notifications._record_delivery("n1", "email", receipt, blast_id="b1", user_id="u1")
        return db

    def test_the_provider_is_recorded(self):
        db = self._record({"state": "accepted", "provider": "onesignal"})
        self.assertEqual(db.table.return_value.insert.call_args.args[0]["provider"], "onesignal")

    def test_a_fallback_is_explained(self):
        db = self._record({"state": "accepted_fallback", "provider": "onesignal",
                           "delivered_by": "resend", "preempted": "onesignal"})
        row = db.table.return_value.insert.call_args.args[0]
        self.assertEqual(row["status"], "sent")
        self.assertEqual(row["provider"], "resend")
        self.assertIn("delivered by resend after onesignal refused", row["status_detail"])

    def test_a_missing_column_does_not_lose_the_record(self):
        db = self._record({"state": "accepted", "provider": "onesignal"}, columns_available=False)
        row = db.table.return_value.insert.call_args.args[0]
        self.assertNotIn("provider", row)
        self.assertEqual(row["status"], "sent")

    def test_the_blast_summary_counts_who_delivered(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.execute.return_value = [
            {"channel": "email", "status": "sent", "provider": "onesignal"},
            {"channel": "email", "status": "sent", "provider": "resend"},
            {"channel": "email", "status": "failed", "provider": "onesignal"},
        ]
        with patch.object(notifications, "get_db", return_value=db):
            summary = notifications.summarize_blast_deliveries("b1")
        self.assertEqual(summary["email"]["sent"], 2)
        self.assertEqual(summary["email"]["failed"], 1)
        self.assertEqual(summary["email"]["sent_by"], {"onesignal": 1, "resend": 1})


if __name__ == "__main__":
    unittest.main()
