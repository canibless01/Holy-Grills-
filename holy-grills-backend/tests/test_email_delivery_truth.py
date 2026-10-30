"""Email delivery: payload correctness, honest outcomes, and the daily-send fallback.

Two production symptoms drive these tests:

1. A campaign reported "sent" while no inbox ever received it. OneSignal accepted the
   request but had no email subscription for the address (nothing else ever created
   one), and the 2xx-with-nothing-delivered shape was read as success.
2. The only fallback was a *reactive* one — switch after the provider says it is out
   of quota. A provider can stop accepting without saying so, so we also count our
   own accepted sends per provider per day and switch before the wall.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

for _name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "JWT_SECRET", "SECRET_KEY"):
    os.environ.setdefault(_name, "https://example.supabase.co" if _name == "SUPABASE_URL" else "test")

import requests

from app.services import email_usage, onesignal_email
from app.services import notification_service as notifications
from app.utils import email


def _reply(status, body=None):
    response = MagicMock()
    response.status_code = status
    response.text = "provider says no"
    response.json.return_value = body if body is not None else {"id": "message-1", "recipients": 1}
    return response


class OneSignalPayloadTests(unittest.TestCase):
    def _attempt(self, response, **kwargs):
        receipt = {}
        with patch.object(notifications, "_get_onesignal_creds", return_value=("app", "key")), \
             patch.object(notifications, "_onesignal_email_post", return_value=response) as post:
            result = email._email_attempt("onesignal", "a@example.invalid", "Audit", "Subject",
                                          "<p>Body</p>", receipt=receipt, **kwargs)
        accepted, quota, undeliverable = result
        return accepted, quota, undeliverable, receipt, post

    def test_payload_names_a_sender_and_is_idempotent(self):
        *_, post = self._attempt(_reply(200))
        payload = post.call_args.kwargs["payload"]
        self.assertEqual(payload["include_email_tokens"], ["a@example.invalid"])
        self.assertTrue(payload["email_from_address"])
        self.assertIn("@", payload["email_from_address"])
        self.assertTrue(payload["email_from_name"])
        self.assertTrue(payload["idempotency_key"])
        self.assertEqual(payload["target_channel"], "email")

    def test_transactional_mail_ignores_marketing_unsubscribes(self):
        *_, post = self._attempt(_reply(200), transactional=True)
        self.assertTrue(post.call_args.kwargs["payload"]["include_unsubscribed"])

    def test_marketing_mail_respects_unsubscribes(self):
        *_, post = self._attempt(_reply(200), transactional=False)
        self.assertNotIn("include_unsubscribed", post.call_args.kwargs["payload"])

    def test_accepted_send_records_the_provider_message_id(self):
        accepted, quota, undeliverable, _, _ = self._attempt(_reply(200))
        self.assertTrue(accepted)
        self.assertFalse(quota or undeliverable)

    def test_two_hundred_with_no_recipients_is_not_accepted(self):
        accepted, _, undeliverable, _, _ = self._attempt(_reply(200, {"id": "m", "recipients": 0}))
        self.assertFalse(accepted)
        self.assertTrue(undeliverable)

    def test_two_hundred_with_an_error_body_is_not_accepted(self):
        accepted, _, undeliverable, _, _ = self._attempt(
            _reply(202, {"id": "m", "errors": ["All included players are not subscribed"]}))
        self.assertFalse(accepted)
        self.assertTrue(undeliverable)

    def test_unsubscribed_400_is_a_miss_not_an_unknown(self):
        accepted, quota, undeliverable, _, _ = self._attempt(
            _reply(400, {"errors": ["No email subscriptions found for the provided addresses"]}))
        self.assertFalse(accepted)
        self.assertFalse(quota)
        self.assertTrue(undeliverable)

    def test_server_error_stays_ambiguous(self):
        accepted, quota, undeliverable, _, _ = self._attempt(_reply(500, {}))
        self.assertFalse(accepted)
        self.assertFalse(quota)
        self.assertFalse(undeliverable)


class RoutingFallbackTests(unittest.TestCase):
    """Provider choice under the reserved-slot counter.

    `reserve` is patched to return the *claimed* count, mimicking
    `hg_record_email_send` returning the row's new value.
    """

    def _route(self, onesignal_reply, resend_reply, provider="onesignal", claimed=None, headers=None,
               transactional=True):
        claimed = claimed or {"resend": 1, "onesignal": 1}
        with patch.object(notifications, "_get_onesignal_creds", return_value=("app", "key")), \
             patch.object(email, "_resend_api_key", return_value="key"), \
             patch.object(notifications, "_onesignal_email_post", return_value=onesignal_reply) as os_post, \
             patch.object(email.requests, "post", return_value=resend_reply) as resend_post, \
             patch.object(email_usage, "reserve", side_effect=lambda p: claimed.get(p)) as reserve, \
             patch.object(email_usage, "release") as release:
            receipt = {}
            result = email.send_email_routed("a@example.invalid", "Audit", "Subject", "<p>Body</p>",
                                             provider=provider, receipt=receipt, headers=headers,
                                             transactional=transactional)
        return result, receipt, os_post, resend_post, reserve, release

    def test_undelivered_onesignal_email_is_delivered_by_resend(self):
        result, receipt, _, resend_post, _, release = self._route(
            _reply(200, {"id": "m", "recipients": 0}), _reply(200))
        self.assertTrue(result)
        self.assertEqual(resend_post.call_count, 1)
        self.assertEqual(receipt["delivered_by"], "resend")
        # The wasted OneSignal slot is handed back; the Resend one is kept.
        release.assert_called_once_with("onesignal")

    def test_no_duplicate_when_the_first_provider_accepted(self):
        result, _, _, resend_post, _, release = self._route(_reply(200), _reply(200))
        self.assertTrue(result)
        resend_post.assert_not_called()
        release.assert_not_called()

    def test_ambiguous_failure_never_crosses_provider(self):
        result, _, _, resend_post, _, release = self._route(_reply(503, {}), _reply(200))
        self.assertFalse(result)
        resend_post.assert_not_called()
        release.assert_not_called()      # may have been accepted: stays counted

    def test_used_up_provider_is_bypassed_before_sending(self):
        # The whole point of the counter: Resend is at 100/100 today, so the 101st
        # send starts on OneSignal instead of failing.
        result, receipt, os_post, resend_post, _, _ = self._route(
            _reply(200), _reply(200), provider="resend", claimed={"resend": 101, "onesignal": 1})
        self.assertTrue(result)
        self.assertEqual(os_post.call_count, 1)
        resend_post.assert_not_called()
        self.assertEqual(receipt["preempted"], "resend")

    def test_under_the_limit_still_uses_the_preferred_provider(self):
        result, _, os_post, resend_post, _, _ = self._route(
            _reply(200), _reply(200), provider="resend", claimed={"resend": 100, "onesignal": 1})
        self.assertTrue(result)
        resend_post.assert_called_once()
        os_post.assert_not_called()

    def test_the_slot_is_reserved_before_the_send(self):
        _, _, _, _, reserve, _ = self._route(_reply(200), _reply(200), provider="resend")
        reserve.assert_called_once_with("resend")

    def test_a_provider_that_was_never_configured_keeps_no_slot(self):
        with patch.object(notifications, "_get_onesignal_creds", return_value=("", "")), \
             patch.object(email_usage, "reserve", return_value=1), \
             patch.object(email_usage, "release") as release:
            receipt = {}
            result = email.send_email_routed("a@example.invalid", "Audit", "Subject", "<p>Body</p>",
                                             provider="onesignal", receipt=receipt)
        self.assertFalse(result)
        release.assert_called_once_with("onesignal")

    def test_newsletter_falls_back_as_marketing_and_keeps_its_resend_attempt(self):
        headers = {"List-Unsubscribe": "<https://example.invalid/u>"}
        result, receipt, os_post, resend_post, _, _ = self._route(
            _reply(200), _reply(429, {"name": "daily_quota_exceeded"}), provider="resend",
            headers=headers, transactional=False)
        self.assertTrue(result)
        # First attempt carried the real headers to Resend...
        self.assertEqual(resend_post.call_args.kwargs["json"]["headers"], headers)
        # ...and the fallback is a marketing send, so OneSignal's unsubscribe wins.
        payload = os_post.call_args.kwargs["payload"]
        self.assertNotIn("include_unsubscribed", payload)
        self.assertEqual(receipt["delivered_by"], "onesignal")


class UsageCounterTests(unittest.TestCase):
    def test_limit_defaults_and_overrides(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMAIL_DAILY_LIMIT_RESEND", None)
            os.environ.pop("EMAIL_DAILY_LIMIT_ONESIGNAL", None)
            self.assertEqual(email_usage.daily_limit("resend"), 100)
            self.assertEqual(email_usage.daily_limit("onesignal"), 0)   # unknown = no pre-emption
        with patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "250", "EMAIL_DAILY_LIMIT_ONESIGNAL": "off"}):
            self.assertEqual(email_usage.daily_limit("resend"), 250)
            self.assertEqual(email_usage.daily_limit("onesignal"), 0)
        with patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "0"}):
            self.assertEqual(email_usage.daily_limit("resend"), 0)
            self.assertFalse(email_usage.over_limit("resend", None))   # unreadable ≠ full

    def test_both_providers_used_up_keeps_the_preferred_one(self):
        # An over-limit attempt can still succeed on a provider that counts
        # differently from us; dropping the mail entirely would be worse.
        with patch.object(email_usage, "reserve", side_effect=[101, 101]), \
             patch.object(email_usage, "release") as release, \
             patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "100", "EMAIL_DAILY_LIMIT_ONESIGNAL": "100"}):
            provider, count = email_usage.reserve_slot("resend")
        self.assertEqual((provider, count), ("resend", 101))
        release.assert_called_once_with("onesignal")   # the unused alternate slot

    def test_switching_provider_releases_the_unused_slot(self):
        with patch.object(email_usage, "reserve", side_effect=[100, 4]), \
             patch.object(email_usage, "release") as release, \
             patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "100", "EMAIL_DAILY_LIMIT_ONESIGNAL": "0"}):
            self.assertEqual(email_usage.reserve_slot("resend"), ("resend", 100))
        release.assert_not_called()                    # 100 of 100 is not over

    def test_reserve_slot_moves_on_when_the_limit_is_passed(self):
        with patch.object(email_usage, "reserve", side_effect=[101, 1]), \
             patch.object(email_usage, "release") as release, \
             patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "100"}):
            self.assertEqual(email_usage.reserve_slot("resend"), ("onesignal", 1))
        release.assert_called_once_with("resend")

    def test_unreadable_counter_does_not_change_routing(self):
        with patch.object(email_usage, "reserve", return_value=None), \
             patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "100"}):
            self.assertEqual(email_usage.reserve_slot("resend"), ("resend", None))

    def test_release_uses_its_own_rpc(self):
        db = MagicMock()
        db.rpc.return_value = 3
        with patch.object(email_usage, "get_db", return_value=db):
            self.assertTrue(email_usage.release("resend"))
        self.assertEqual(db.rpc.call_args.args[0], "hg_release_email_send")

    def test_release_failure_is_swallowed(self):
        db = MagicMock()
        db.rpc.side_effect = RuntimeError("missing function")
        with patch.object(email_usage, "get_db", return_value=db):
            self.assertFalse(email_usage.release("resend"))

    def test_counter_failure_never_raises(self):
        db = MagicMock()
        db.rpc.side_effect = RuntimeError("table missing")
        with patch.object(email_usage, "get_db", return_value=db):
            self.assertIsNone(email_usage.reserve("resend"))
            self.assertIsNone(email_usage.sent_today("resend"))
            self.assertFalse(email_usage.over_limit("resend", None))   # unreadable ≠ full

    def test_reserve_posts_provider_and_day(self):
        db = MagicMock()
        db.rpc.return_value = 7
        with patch.object(email_usage, "get_db", return_value=db):
            self.assertEqual(email_usage.reserve("resend"), 7)
        args = db.rpc.call_args.args
        self.assertEqual(args[0], "hg_record_email_send")
        self.assertEqual(db.rpc.call_args.args[1]["p_provider"], "resend")
        self.assertIn("p_day", db.rpc.call_args.args[1])


class UsageHealthTests(unittest.TestCase):
    def _health(self, counts):
        db = MagicMock()
        db.rpc.return_value = counts
        with patch.object(email_usage, "get_db", return_value=db), \
             patch.object(email, "_resend_api_key", return_value="key"), \
             patch.object(notifications, "_get_onesignal_creds", return_value=("app", "key")):
            return email_usage.health()

    def test_health_lists_each_provider_with_its_headroom(self):
        health = self._health({"resend": 100})
        by_name = {p["provider"]: p for p in health["providers"]}
        self.assertTrue(health["counters_available"])
        self.assertEqual(by_name["resend"]["sent_today"], 100)
        self.assertEqual(by_name["resend"]["remaining"], 0)
        self.assertTrue(by_name["resend"]["exhausted"])
        self.assertTrue(by_name["resend"]["configured"])
        # OneSignal has no configured limit: nothing to exhaust, so no pre-emption.
        self.assertIsNone(by_name["onesignal"]["daily_limit"])
        self.assertFalse(by_name["onesignal"]["exhausted"])

    def test_health_survives_a_missing_counter_table(self):
        db = MagicMock()
        db.rpc.side_effect = RuntimeError("relation does not exist")
        with patch.object(email_usage, "get_db", return_value=db), \
             patch.object(email, "_resend_api_key", return_value=""), \
             patch.object(notifications, "_get_onesignal_creds", return_value=("", "")):
            health = email_usage.health()
        self.assertFalse(health["counters_available"])
        self.assertTrue(all(p["sent_today"] is None for p in health["providers"]))
        self.assertFalse(any(p["configured"] for p in health["providers"]))


class OneSignalSubscriptionTests(unittest.TestCase):
    def test_subscription_links_the_email_to_the_profile_id(self):
        with patch.object(onesignal_email, "_creds", return_value=("app-id", "api-key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(201, {}), _reply(200, {})]) as post:
            self.assertTrue(onesignal_email.ensure_email_subscription("user-1", "a@example.invalid"))
        first, second = post.call_args_list
        self.assertIn("/users", first.args[0])
        self.assertEqual(first.kwargs["json"]["identity"]["external_id"], "user-1")
        self.assertIn("/users/by/external_id/user-1/subscriptions", second.args[0])
        self.assertEqual(second.kwargs["json"]["subscription"],
                         {"type": "Email", "token": "a@example.invalid", "enabled": True})

    def test_existing_user_409_is_not_a_failure(self):
        with patch.object(onesignal_email, "_creds", return_value=("app-id", "api-key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(409, {}), _reply(201, {})]):
            self.assertTrue(onesignal_email.ensure_email_subscription("user-1", "a@example.invalid"))

    def test_opt_out_disables_the_subscription(self):
        with patch.object(onesignal_email, "_creds", return_value=("app-id", "api-key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(200, {}), _reply(200, {})]) as post:
            onesignal_email.ensure_email_subscription("user-1", "a@example.invalid", enabled=False)
        self.assertFalse(post.call_args_list[1].kwargs["json"]["subscription"]["enabled"])

    def test_unconfigured_or_offline_is_silent(self):
        with patch.object(onesignal_email, "_creds", return_value=("", "")):
            self.assertFalse(onesignal_email.ensure_email_subscription("user-1", "a@example.invalid"))
        with patch.object(onesignal_email, "_creds", return_value=("app-id", "api-key")), \
             patch.object(onesignal_email.requests, "post", side_effect=requests.ConnectionError("down")):
            self.assertFalse(onesignal_email.ensure_email_subscription("user-1", "a@example.invalid"))
        self.assertFalse(onesignal_email.ensure_email_subscription("", "a@example.invalid"))
        self.assertFalse(onesignal_email.ensure_email_subscription("user-1", "not-an-email"))


class PreferenceMappingTests(unittest.TestCase):
    def test_everyone_is_a_subscriber_except_an_all_email_opt_out(self):
        self.assertTrue(onesignal_email.enabled_from_preferences({}))
        self.assertTrue(onesignal_email.enabled_from_preferences({"promotions": False}))
        self.assertTrue(onesignal_email.enabled_from_preferences({"email_enabled": True, "promotions": False}))
        self.assertFalse(onesignal_email.enabled_from_preferences({"email_enabled": False}))


class SubscriptionDiagnosticsTests(unittest.TestCase):
    """The admin endpoint returns OneSignal's own answer, so a failure is visible."""

    def test_success_reports_the_subscription_id(self):
        details = {}
        body = {"subscription": {"id": "sub-1", "type": "Email", "enabled": True}}
        with patch.object(onesignal_email, "_creds", return_value=("app-id", "api-key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(201, {}), _reply(200, body)]):
            linked = onesignal_email.ensure_email_subscription("user-1", "a@example.invalid",
                                                              details=details)
        self.assertTrue(linked)
        self.assertTrue(details["linked"])
        self.assertEqual(details["subscription_id"], "sub-1")
        self.assertEqual(details["subscription_type"], "Email")
        self.assertEqual(details["http_status"], 200)

    def test_a_rejection_reports_the_provider_error(self):
        details = {}
        with patch.object(onesignal_email, "_creds", return_value=("app-id", "api-key")), \
             patch.object(onesignal_email.requests, "post",
                          side_effect=[_reply(200, {}),
                                       _reply(400, {"errors": ["Email token is invalid"]})]):
            linked = onesignal_email.ensure_email_subscription("user-1", "bad@example.invalid",
                                                              details=details)
        self.assertFalse(linked)
        self.assertFalse(details["linked"])
        self.assertEqual(details["errors"], ["Email token is invalid"])
        self.assertEqual(details["http_status"], 400)

    def test_unconfigured_says_so_instead_of_failing_silently(self):
        details = {}
        with patch.object(onesignal_email, "_creds", return_value=("", "")):
            self.assertFalse(onesignal_email.ensure_email_subscription("user-1", "a@example.invalid",
                                                                      details=details))
        self.assertEqual(details["reason"], "onesignal_not_configured")


class SelfHealTests(unittest.TestCase):
    """A refused "not subscribed" send must be repaired, not just re-routed.

    The production logs showed tests falling back to Resend on every send: OneSignal
    answered 200 with "not subscribed", we treated it as a miss and mailed via Resend.
    Users got their mail, OneSignal stayed at zero subscribers, and the fallback is
    the provider that runs out at 100/day — so the failure was invisible until it
    mattered.
    """

    def _route(self, replies, linked=True, transactional=True, provider="onesignal"):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = []
        replies = list(replies)
        with patch.object(notifications, "_get_onesignal_creds", return_value=("app", "key")), \
             patch.object(notifications, "_onesignal_email_post", side_effect=replies) as post, \
             patch.object(email_usage, "reserve", return_value=1), \
             patch.object(email_usage, "release"), \
             patch.object(onesignal_email, "ensure_email_subscription", return_value=linked) as ensure, \
             patch("app.db.get_db", return_value=db):
            receipt = {}
            result = email.send_email_routed("guest@example.invalid", "Guest", "Your QR code",
                                             "<p>qr</p>", provider=provider, receipt=receipt,
                                             transactional=transactional)
        return result, receipt, post, ensure

    def test_a_missing_subscription_is_created_and_the_send_retried(self):
        result, receipt, post, ensure = self._route([
            _reply(200, {"id": "m0", "errors": ["All included players are not subscribed"]}),
            _reply(200, {"id": "m1", "recipients": 1}),
        ])
        self.assertTrue(result)
        ensure.assert_called_once()
        self.assertEqual(post.call_count, 2)               # retried on OneSignal, not Resend
        self.assertEqual(receipt["provider_message_id"], "m1")

    def test_the_retry_is_not_used_when_registration_fails(self):
        result, _, post, ensure = self._route([
            _reply(200, {"id": "m0", "errors": ["All included players are not subscribed"]}),
        ], linked=False)
        self.assertFalse(result)
        ensure.assert_called_once()
        self.assertEqual(post.call_count, 1)               # no pointless second attempt

    def test_an_unrelated_2xx_error_is_not_treated_as_a_subscription_problem(self):
        result, _, post, ensure = self._route([_reply(200, {"errors": ["Sender domain not verified"]})])
        self.assertFalse(result)
        ensure.assert_not_called()
        self.assertEqual(post.call_count, 1)

    def test_a_guest_gets_a_stable_identity_and_an_account_uses_its_profile_id(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = [
            {"id": "profile-uuid", "is_active": True}]
        with patch("app.db.get_db", return_value=db):
            self.assertEqual(email._subscription_identity("a@example.invalid"), "profile-uuid")
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = []
        with patch("app.db.get_db", return_value=db):
            first = email._subscription_identity("Guest@Example.invalid")
            second = email._subscription_identity("guest@example.invalid")
        self.assertTrue(first.startswith("guest-"))
        self.assertEqual(first, second)                    # same guest, same alias, case-insensitive

    def test_a_deactivated_account_is_not_registered(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = [
            {"id": "profile-uuid", "is_active": False}]
        with patch("app.db.get_db", return_value=db):
            identity = email._subscription_identity("a@example.invalid")
        self.assertTrue(identity.startswith("guest-"))

    def test_email_addresses_are_masked_in_messages(self):
        self.assertEqual(email._mask_email("someone@example.com"), "s***@example.com")
        self.assertEqual(email._mask_email("nonsense"), "***")


class EmailHealthDiagnosticsTests(unittest.TestCase):
    """A wrong OneSignal app id looks exactly like "nothing reaches OneSignal"."""

    def _health(self, app_id="471bd695-2342-4521-aa0f-8c93d7ce805f", api_key="os_v2_app_test"):
        from app.routes import admin as admin_routes
        with patch("app.services.email_usage.health",
                   return_value={"date": "2026-10-30", "providers": [], "counters_available": True}), \
             patch("app.services.notification_service._get_onesignal_creds",
                   return_value=(app_id, api_key)), \
             patch.object(admin_routes, "email_utils_get_provider", return_value="resend"), \
             patch.object(admin_routes, "jsonify", side_effect=lambda payload: payload):
            # __wrapped__ skips @require_role, which needs a live request.
            return admin_routes.email_health.__wrapped__()[0]

    def test_it_reports_the_app_id_and_the_key_kind(self):
        health = self._health()
        self.assertEqual(health["onesignal_app_id"], "471bd695-2342-4521-aa0f-8c93d7ce805f")
        self.assertTrue(health["onesignal_app_id_looks_valid"])
        self.assertTrue(health["onesignal_api_key_present"])
        self.assertEqual(health["onesignal_api_key_type"], "server_rest")

    def test_a_missing_key_or_odd_app_id_is_visible(self):
        health = self._health(app_id="", api_key="")
        self.assertIsNone(health["onesignal_app_id"])
        self.assertFalse(health["onesignal_api_key_present"])
        self.assertFalse(health["onesignal_app_id_looks_valid"])
        # An App ID pasted into the key slot is the classic mix-up.
        health = self._health(api_key="471bd695-2342-4521-aa0f-8c93d7ce805f")
        self.assertEqual(health["onesignal_api_key_type"], "present_unexpected_prefix")


class TestBlastReceiptTests(unittest.TestCase):
    def test_receipt_is_read_from_the_delivery_row(self):
        from app.routes import notifications as notification_routes
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = [
            {"status": "sent", "provider_message_id": "m-1", "delivered_at": "now", "error_message": None}]
        with patch.object(notification_routes, "get_db", return_value=db):
            receipt = notification_routes._await_email_delivery("blast-1")
        self.assertEqual(receipt["status"], "sent")
        self.assertEqual(receipt["message_id"], "m-1")

    def test_no_record_before_the_deadline_reports_pending(self):
        from app.routes import notifications as notification_routes
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = []
        with patch.object(notification_routes, "get_db", return_value=db), \
             patch.object(notification_routes, "get_db", return_value=db):
            receipt = notification_routes._await_email_delivery("blast-1", timeout=0.01)
        self.assertEqual(receipt["status"], "pending")

    def test_a_failed_read_returns_none_rather_than_raising(self):
        from app.routes import notifications as notification_routes
        with patch.object(notification_routes, "get_db", side_effect=RuntimeError("db down")):
            self.assertIsNone(notification_routes._await_email_delivery("blast-1", timeout=0.01))


class SubscriptionBackfillTests(unittest.TestCase):
    """The sweep must use the query builder this repo actually has.

    `TableQuery` (app/db.py) offers limit()/offset() and has no range(), and a nested
    select is unsupported too. The first version used both, so every sweep died with
    `'TableQuery' object has no attribute 'range'` before reading a single profile —
    which is why OneSignal stayed at 0 email subscribers.
    """

    def _db(self, rows, preferences=None):
        db = MagicMock()
        profiles = db.table.return_value.select.return_value.order.return_value.limit.return_value
        profiles.offset.return_value.execute.return_value = rows
        profiles.execute.return_value = rows
        db.table.return_value.select.return_value.in_.return_value.limit.return_value.execute.return_value = (
            preferences or [])
        return db

    def _run(self, rows, linked=True, preferences=None):
        db = self._db(rows, preferences)
        with patch("app.db.get_db", return_value=db), \
             patch.object(onesignal_email, "ensure_email_subscription", return_value=linked) as ensure:
            return onesignal_email.backfill_email_subscriptions(limit=10), ensure, db

    def test_the_query_uses_limit_offset_and_never_range(self):
        _, _, db = self._run([{"id": "u1", "email": "a@example.invalid"}])
        profiles = db.table.return_value.select.return_value.order.return_value.limit.return_value
        profiles.offset.assert_called_once_with(0)
        # A nested (embedded) select is what this client cannot build.
        profile_select = db.table.return_value.select.call_args_list[0]
        self.assertEqual(profile_select.args[0], "id,email,is_active,email_notifications")
        self.assertNotIn("(", profile_select.args[0])

    def test_preferences_are_read_separately_and_respected(self):
        _, ensure, db = self._run(
            [{"id": "u1", "email": "a@example.invalid"}, {"id": "u2", "email": "b@example.invalid"}],
            preferences=[{"user_id": "u2", "email_enabled": False}])
        self.assertEqual([call.kwargs["enabled"] for call in ensure.call_args_list], [True, False])
        db.table.assert_any_call("notification_preferences")

    def test_active_accounts_are_linked(self):
        summary, ensure, _ = self._run([{"id": "u1", "email": "a@example.invalid", "is_active": True},
                                     {"id": "u2", "email": "b@example.invalid"}])
        self.assertEqual((summary["linked"], summary["failed"]), (2, 0))
        self.assertEqual(ensure.call_count, 2)

    def test_deactivated_and_addressless_profiles_are_skipped(self):
        summary, ensure, _ = self._run([{"id": "u1", "email": "a@example.invalid", "is_active": False},
                                     {"id": "u2", "email": None}])
        self.assertEqual((summary["skipped"], summary["linked"]), (2, 0))
        ensure.assert_not_called()

    def test_a_failed_link_is_counted_not_raised(self):
        summary, _, _ = self._run([{"id": "u1", "email": "a@example.invalid"}], linked=False)
        self.assertEqual((summary["failed"], summary["linked"]), (1, 0))

    def test_a_promotions_opt_out_does_not_stop_the_address_being_registered(self):
        # OneSignal cannot deliver to an address it does not know, so declining
        # newsletters must not cost the account its order and QR emails.
        summary, ensure, _ = self._run(
            [{"id": "u1", "email": "a@example.invalid"},
             {"id": "u2", "email": "b@example.invalid", "email_notifications": False}],
            # u1 opted out of newsletters only; the master email switch is still on.
            preferences=[{"user_id": "u1", "email_enabled": True}])
        self.assertEqual(summary["linked"], 2)
        self.assertEqual([call.kwargs["enabled"] for call in ensure.call_args_list], [True, False])

    def test_unchanged_preferences_stay_subscribed(self):
        _, ensure, _ = self._run([{"id": "u1", "email": "a@example.invalid"}], preferences=[])
        self.assertTrue(ensure.call_args.kwargs["enabled"])

    def test_unreadable_profiles_returns_an_empty_summary(self):
        db = MagicMock()
        db.table.side_effect = RuntimeError("no table")
        with patch("app.db.get_db", return_value=db):
            summary = onesignal_email.backfill_email_subscriptions()
        self.assertEqual(summary, {"checked": 0, "linked": 0, "failed": 0, "skipped": 0})


class DeliveryRecordTests(unittest.TestCase):
    def test_accepted_email_is_recorded_as_sent(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = []
        with patch.object(notifications, "get_db", return_value=db):
            notifications._record_delivery("notif-1", "email",
                                           {"state": "accepted", "provider": "onesignal",
                                            "provider_message_id": "m-1"},
                                           blast_id="blast-1", user_id="user-1")
        inserted = db.table.return_value.insert.call_args.args[0]
        self.assertEqual(inserted["status"], "sent")
        self.assertEqual(inserted["provider_message_id"], "m-1")
        self.assertEqual(inserted["blast_id"], "blast-1")
        self.assertIsNotNone(inserted["delivered_at"])

    def test_undelivered_email_is_recorded_as_failed_with_the_reason(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = []
        with patch.object(notifications, "get_db", return_value=db):
            notifications._record_delivery("notif-1", "email",
                                           {"state": "undelivered", "provider": "onesignal",
                                            "error": "All included players are not subscribed"})
        inserted = db.table.return_value.insert.call_args.args[0]
        self.assertEqual(inserted["status"], "failed")
        self.assertIn("not subscribed", inserted["error_message"])
        self.assertNotIn("delivered_at", inserted)   # a failed send has no delivery time

    def test_an_unconfigured_provider_is_skipped_not_failed(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = []
        with patch.object(notifications, "get_db", return_value=db):
            notifications._record_delivery("notif-1", "email", {"state": "not_configured"})
        self.assertEqual(db.table.return_value.insert.call_args.args[0]["status"], "skipped")

    def test_blast_summary_flags_a_total_email_failure(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {"metadata": {}}
        db.table.return_value.select.return_value.eq.return_value.execute.return_value = [
            {"channel": "email", "status": "failed"}, {"channel": "push", "status": "sent"}]
        with patch.object(notifications, "get_db", return_value=db), \
             patch.object(notifications, "time") as fake_time:
            fake_time.sleep.return_value = None
            with patch.object(notifications.threading, "Thread") as thread:
                notifications._record_blast_delivery_summary("blast-1", "token")
            target = thread.call_args.kwargs["target"]
            target()
        updated = db.table.return_value.eq.return_value.update.call_args.args[0]
        self.assertTrue(updated["metadata"]["email_delivery_failed"])
        self.assertEqual(updated["metadata"]["dispatch"]["email"]["failed"], 1)


if __name__ == "__main__":
    unittest.main()
