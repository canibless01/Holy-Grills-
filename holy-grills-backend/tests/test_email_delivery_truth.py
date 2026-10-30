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
    def _route(self, onesignal_reply, resend_reply, provider="onesignal", counts=None):
        counts = counts or {"resend": 0, "onesignal": 0}
        with patch.object(notifications, "_get_onesignal_creds", return_value=("app", "key")), \
             patch.object(email, "_resend_api_key", return_value="key"), \
             patch.object(notifications, "_onesignal_email_post", return_value=onesignal_reply) as os_post, \
             patch.object(email.requests, "post", return_value=resend_reply) as resend_post, \
             patch.object(email_usage, "sent_today", side_effect=lambda p: counts.get(p)), \
             patch.object(email_usage, "record_send") as record:
            receipt = {}
            result = email.send_email_routed("a@example.invalid", "Audit", "Subject", "<p>Body</p>",
                                             provider=provider, receipt=receipt)
        return result, receipt, os_post, resend_post, record

    def test_undelivered_onesignal_email_is_delivered_by_resend(self):
        result, receipt, _, resend_post, record = self._route(
            _reply(200, {"id": "m", "recipients": 0}), _reply(200))
        self.assertTrue(result)
        self.assertEqual(resend_post.call_count, 1)
        self.assertEqual(receipt["delivered_by"], "resend")
        record.assert_called_once_with("resend")

    def test_no_duplicate_when_the_first_provider_accepted(self):
        result, _, _, resend_post, _ = self._route(_reply(200), _reply(200))
        self.assertTrue(result)
        resend_post.assert_not_called()

    def test_ambiguous_failure_never_crosses_provider(self):
        result, _, _, resend_post, _ = self._route(_reply(503, {}), _reply(200))
        self.assertFalse(result)
        resend_post.assert_not_called()

    def test_used_up_provider_is_bypassed_before_sending(self):
        # The whole point of the counter: Resend is at 100/100 today, so a
        # transactional send starts on OneSignal instead of failing 101st.
        result, receipt, os_post, resend_post, _ = self._route(
            _reply(200), _reply(200), provider="resend", counts={"resend": 100, "onesignal": 0})
        self.assertTrue(result)
        self.assertEqual(os_post.call_count, 1)
        resend_post.assert_not_called()
        self.assertEqual(receipt["preempted"], "resend")

    def test_under_the_limit_still_uses_the_preferred_provider(self):
        result, _, os_post, resend_post, _ = self._route(
            _reply(200), _reply(200), provider="resend", counts={"resend": 99, "onesignal": 0})
        self.assertTrue(result)
        resend_post.assert_called_once()
        os_post.assert_not_called()

    def test_unreadable_counter_does_not_change_routing(self):
        with patch.object(email_usage, "daily_limit", return_value=100), \
             patch.object(email_usage, "sent_today", return_value=None):
            self.assertEqual(email_usage.choose_provider("resend"), "resend")


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
            self.assertFalse(email_usage.exhausted("resend"))

    def test_both_providers_used_up_keeps_the_preferred_one(self):
        with patch.object(email_usage, "sent_today", return_value=500):
            with patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "100", "EMAIL_DAILY_LIMIT_ONESIGNAL": "100"}):
                self.assertEqual(email_usage.choose_provider("resend"), "resend")

    def test_counter_failure_never_raises(self):
        db = MagicMock()
        db.rpc.side_effect = RuntimeError("table missing")
        with patch.object(email_usage, "get_db", return_value=db):
            self.assertIsNone(email_usage.record_send("resend"))
            self.assertIsNone(email_usage.sent_today("resend"))
            self.assertFalse(email_usage.exhausted("resend"))

    def test_record_send_posts_provider_and_day(self):
        db = MagicMock()
        db.rpc.return_value = 7
        with patch.object(email_usage, "get_db", return_value=db):
            self.assertEqual(email_usage.record_send("resend"), 7)
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
    def test_email_or_promotions_opt_out_disables_the_subscription(self):
        self.assertTrue(onesignal_email.enabled_from_preferences({}))
        self.assertFalse(onesignal_email.enabled_from_preferences({"email_enabled": False}))
        self.assertFalse(onesignal_email.enabled_from_preferences({"promotions": False}))
        self.assertTrue(onesignal_email.enabled_from_preferences({"email_enabled": True, "promotions": True}))


class SubscriptionBackfillTests(unittest.TestCase):
    def _run(self, rows, linked=True):
        db = MagicMock()
        db.table.return_value.select.return_value.range.return_value.execute.return_value = rows
        with patch("app.db.get_db", return_value=db), \
             patch.object(onesignal_email, "ensure_email_subscription", return_value=linked) as ensure:
            return onesignal_email.backfill_email_subscriptions(limit=10), ensure

    def test_active_accounts_are_linked(self):
        summary, ensure = self._run([{"id": "u1", "email": "a@example.invalid", "is_active": True},
                                     {"id": "u2", "email": "b@example.invalid"}])
        self.assertEqual((summary["linked"], summary["failed"]), (2, 0))
        self.assertEqual(ensure.call_count, 2)

    def test_deactivated_and_addressless_profiles_are_skipped(self):
        summary, ensure = self._run([{"id": "u1", "email": "a@example.invalid", "is_active": False},
                                     {"id": "u2", "email": None}])
        self.assertEqual((summary["skipped"], summary["linked"]), (2, 0))
        ensure.assert_not_called()

    def test_a_failed_link_is_counted_not_raised(self):
        summary, _ = self._run([{"id": "u1", "email": "a@example.invalid"}], linked=False)
        self.assertEqual((summary["failed"], summary["linked"]), (1, 0))

    def test_opted_out_accounts_are_registered_but_not_subscribed(self):
        summary, ensure = self._run([
            {"id": "u1", "email": "a@example.invalid",
             "notification_preferences": [{"promotions": False, "email_enabled": True}]},
            {"id": "u2", "email": "b@example.invalid", "email_notifications": False},
        ])
        self.assertEqual(summary["linked"], 2)
        self.assertEqual([call.kwargs["enabled"] for call in ensure.call_args_list], [False, False])

    def test_unchanged_preferences_stay_subscribed(self):
        _, ensure = self._run([{"id": "u1", "email": "a@example.invalid",
                                "notification_preferences": {"promotions": True}}])
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
