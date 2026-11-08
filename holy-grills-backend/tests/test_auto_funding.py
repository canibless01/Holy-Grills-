"""No provider calls: the custom cadence must never retry an uncertain debit."""
import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from flask import Flask, g
from app.services import auto_funding as service
from app.routes.auto_funding import plans, manage

SEND_ATTENTION_NOTICES = service.send_attention_notices


class AutomaticFundingTests(unittest.TestCase):
    def setUp(self):
        self.notices = patch.object(service, "send_attention_notices").start()
        self.addCleanup(patch.stopall)
        self.app = Flask(__name__)
        self.app.config.update(PAYSTACK_SECRET_KEY="test-only", FRONTEND_URL="https://holygrills.online")
        self.uid, self.pid = str(uuid4()), str(uuid4())
        self.reference = "HG-AUTO-" + self.pid.replace("-", "") + "-1"
        self.terms = {"request_id": self.pid, "amount": 200, "interval_days": 2,
                      "stop_after": 30, "consent": True, "consent_version": service.CONSENT_VERSION}
        self.plan = {"id": self.pid, "setup_reference": self.reference, "authorization_email": "original@example.invalid", "amount_kobo": 20000}

    def test_terms_require_explicit_consent_exact_cents_and_bounded_integer_schedule(self):
        _, result = service.validate_terms(self.terms, 100)
        self.assertEqual(result["amount_kobo"], 20000)
        self.assertEqual(result["interval_days"], 2)
        variants = [{"amount": value} for value in (True, "NaN", "Infinity", -1, 99, "200.001", 1000001)]
        variants += [{"interval_days": value} for value in (True, 0, 366, 2.1, "2")]
        variants += [{"stop_after": value} for value in (True, 0, 3651, 1.1)]
        variants += [{"consent": False}, {"consent_version": "old"}, {"request_id": "bad"},
                     {"end_date": "2020-01-01", "stop_after": None}, {"end_date": "2026-99-99"}]
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(service.FundingError):
                service.validate_terms({**self.terms, **variant}, 100)

    def test_end_date_and_count_are_mutually_exclusive(self):
        with self.assertRaises(service.FundingError):
            service.validate_terms({**self.terms, "end_date": "2027-01-01"}, 100)
        _, result = service.validate_terms({**self.terms, "stop_after": None, "end_date": "2027-01-01"}, 100)
        self.assertEqual(result["end_at"], "2027-01-02T00:00:00+01:00")

    def test_setup_charges_exact_amount_card_only_trusted_callback_original_email(self):
        with self.app.app_context(), patch.object(service, "limits", return_value={"minimum_amount": 100}), \
             patch.object(service, "rpc", side_effect=[{"created": True, "plan": self.plan}, {**self.plan, "checkout_url": "https://checkout.paystack.com/test"}]), \
             patch.object(service, "_provider", return_value={"reference": self.reference, "authorization_url": "https://checkout.paystack.com/test"}) as provider:
            result = service.create_plan(self.uid, {**self.terms, "callback_url": "https://evil.invalid"})
        payload = provider.call_args.args[2]
        self.assertEqual(payload["amount"], 20000)  # Holy Grills absorbs fees.
        self.assertEqual(payload["channels"], ["card"])
        self.assertEqual(payload["email"], "original@example.invalid")
        self.assertTrue(payload["callback_url"].startswith("https://holygrills.online/wallet?auto_funding="))
        self.assertNotIn("authorization_email", result)

    def test_repeated_setup_intent_returns_existing_checkout_without_provider_call(self):
        with self.app.app_context(), patch.object(service, "limits", return_value={"minimum_amount": 100}), \
             patch.object(service, "rpc", return_value={"created": False, "plan": self.plan}), patch.object(service, "_provider") as provider:
            service.create_plan(self.uid, self.terms)
        provider.assert_not_called()

    def test_create_route_returns_standard_authorization_url_and_reference(self):
        checkout = {**self.plan, "checkout_url": "https://checkout.paystack.com/test"}
        with self.app.test_request_context(method="POST", json=self.terms), \
             patch.object(service, "create_plan", return_value=service.public_plan(checkout)):
            g.user_id = self.uid
            response = plans.__wrapped__()
        self.assertEqual(response.json["authorization_url"], checkout["checkout_url"])
        self.assertEqual(response.json["reference"], self.reference)
        self.assertEqual(response.json["plan"]["checkout_url"], checkout["checkout_url"])
        self.assertNotIn("authorization_email", response.json["plan"])

    def test_provider_json_error_is_not_replaced_by_an_http_exception(self):
        response = MagicMock(status_code=400)
        response.json.return_value = {"status": False, "message": "  Clinic   not found\n" }
        with self.app.app_context(), patch.object(service.requests, "request", return_value=response), \
             self.assertRaises(service.FundingError) as caught:
            service._provider("POST", "/transaction/initialize", {})
        self.assertEqual(str(caught.exception), "Clinic not found")

    def test_charge_error_never_echoes_reusable_authorization_to_response_or_logs(self):
        response = MagicMock(status_code=400)
        response.json.return_value = {"status": False, "message": "Rejected AUTH_TEST_PRIVATE"}
        with self.app.app_context(), patch.object(service.requests, "request", return_value=response), \
             self.assertLogs(self.app.logger, level="WARNING") as logs, \
             self.assertRaises(service.FundingError) as caught:
            service._provider("POST", "/transaction/charge_authorization", {"authorization_code": "AUTH_TEST_PRIVATE"})
        self.assertNotIn("AUTH_TEST_PRIVATE", str(caught.exception))
        self.assertNotIn("AUTH_TEST_PRIVATE", "\n".join(logs.output))

    def test_initialization_preserves_provider_error_and_marks_only_setup_failed(self):
        with self.app.app_context(), patch.object(service, "limits", return_value={"minimum_amount": 100}), \
             patch.object(service, "rpc", side_effect=[{"created": True, "plan": self.plan}, {}]) as rpc, \
             patch.object(service, "_provider", side_effect=service.FundingError("Paystack test initialization failed")):
            with self.assertRaisesRegex(service.FundingError, "Paystack test initialization failed"):
                service.create_plan(self.uid, self.terms)
        self.assertEqual(rpc.call_args_list[-1].args[0], "setup_failed")

    def test_failed_return_is_recorded_without_activating_or_crediting(self):
        failed_plan = {**self.plan, "state": "attention", "last_issue": "payment_failed"}
        with self.app.app_context(), patch.object(service, "rpc", side_effect=[self.plan, {}, failed_plan]) as rpc, \
             patch.object(service, "_provider", return_value={"reference": self.reference, "status": "abandoned"}), \
             patch.object(service, "confirm_payment") as confirm:
            result = service.verify_setup(self.uid, self.pid, self.reference)
        self.assertEqual(result["payment_status"], "failed")
        self.assertEqual(result["plan"]["state"], "attention")
        confirm.assert_not_called()
        self.assertEqual([call.args[0] for call in rpc.call_args_list], ["get", "failed", "get"])

    def test_provider_money_post_is_single_attempt_on_timeout(self):
        with self.app.app_context(), patch.object(service.requests, "request", side_effect=TimeoutError) as request:
            with self.assertRaises(TimeoutError):
                service._provider("POST", "/transaction/charge_authorization", {"reference": self.reference})
        request.assert_called_once()

    def test_dispatch_timeout_never_invents_new_reference_or_retries_charge(self):
        items = [{"action": "dispatch", "id": self.pid}]
        dispatch = {"authorization_code": "private-auth", "authorization_email": "original@example.invalid", "amount_kobo": 20000, "reference": self.reference}
        with self.app.app_context(), patch.object(service, "rpc", side_effect=[items, dispatch]) as rpc, \
             patch.object(service, "_provider", side_effect=TimeoutError) as provider:
            result = service.sweep()
        self.assertEqual(result["dispatched"], 1)
        self.assertEqual(result["unavailable"], 1)
        provider.assert_called_once()
        self.assertEqual(provider.call_args.args[2]["reference"], self.reference)
        self.assertEqual([call.args[0] for call in rpc.call_args_list], ["due", "dispatch"])

    def test_recovery_verifies_only_existing_reference(self):
        with self.app.app_context(), patch.object(service, "rpc", return_value=[{"action": "verify", "reference": self.reference}]), \
             patch.object(service, "_provider", return_value={"status": "pending"}) as provider:
            service.sweep()
        self.assertEqual(provider.call_args.args, ("GET", f"/transaction/verify/{self.reference}"))

    def test_provider_post_success_alone_does_not_credit_cash(self):
        dispatch = {"authorization_code": "private", "authorization_email": "original@example.invalid", "amount_kobo": 20000, "reference": self.reference}
        with self.app.app_context(), patch.object(service, "rpc", side_effect=[[{"action": "dispatch", "id": self.pid}], dispatch]), \
             patch.object(service, "_provider", return_value={"status": "success", "reference": self.reference}), patch.object(service, "confirm_payment") as confirm:
            service.sweep()
        confirm.assert_not_called()

    def test_bad_amount_currency_or_reference_never_commits(self):
        data = {"reference": self.reference, "status": "success", "currency": "NGN", "amount": 20000}
        for variant in ({"reference": "HG-WALLET-else"}, {"amount": True}, {"amount": -1}, {"currency": "USD"}, {"requested_amount": 19999}):
            with self.subTest(variant=variant), patch.object(service, "rpc") as rpc, self.assertRaises(service.FundingError):
                service.confirm_payment({**data, **variant})
            rpc.assert_not_called()

    def test_authorization_is_private_and_payment_survives_effects_failure(self):
        data = {"reference": self.reference, "status": "success", "currency": "NGN", "amount": 20000,
                "authorization": {"authorization_code": "private", "reusable": True, "channel": "card", "pan": "DO-NOT-STORE"}}
        receipt = {"plan": {**self.plan, "authorization": data["authorization"]}, "attempt_id": str(uuid4())}
        with self.app.app_context(), patch.object(service, "rpc", return_value=receipt) as rpc, \
             patch.object(service, "complete_effects", side_effect=ConnectionError):
            result = service.confirm_payment(data, expected_user_id=self.uid, plan_id=self.pid)
        self.assertEqual(result["payment_status"], "paid")
        self.assertNotIn("authorization", result["plan"])
        self.assertNotIn("pan", rpc.call_args.kwargs["data"]["authorization"])
        self.assertEqual(rpc.call_args.kwargs["user_id"], self.uid)

    def test_owner_checked_before_return_verification(self):
        with patch.object(service, "rpc", return_value=self.plan), patch.object(service, "_provider") as provider:
            with self.assertRaises(service.FundingError):
                service.verify_setup(self.uid, self.pid, "HG-AUTO-foreign")
        provider.assert_not_called()

    def test_duplicate_or_stopped_dispatch_does_not_call_provider(self):
        with self.app.app_context(), patch.object(service, "rpc", side_effect=[[{"action": "dispatch", "id": self.pid}], {}]), \
             patch.object(service, "_provider") as provider:
            service.sweep()
        provider.assert_not_called()

    def test_emergency_pause_prevents_new_debits_but_still_verifies_paid_money(self):
        self.app.config["WALLET_AUTO_FUNDING_ENABLED"] = False
        with self.app.app_context(), patch.object(service, "rpc", return_value=[{"action": "dispatch", "id": self.pid}, {"action": "verify", "reference": self.reference}]), \
             patch.object(service, "_provider", return_value={"status": "pending"}) as provider:
            service.sweep()
        provider.assert_called_once_with("GET", f"/transaction/verify/{self.reference}")

    def test_missing_worker_key_never_claims_charge_authority(self):
        self.app.config["PAYSTACK_SECRET_KEY"] = ""
        with self.app.app_context(), patch.object(service, "rpc", return_value=[{"action": "dispatch", "id": self.pid}]) as rpc, \
             patch.object(service, "_provider") as provider:
            service.sweep()
        rpc.assert_called_once_with("due", data={"limit": 20})
        provider.assert_not_called()

    def test_stop_route_uses_authenticated_owner(self):
        with self.app.test_request_context(json={"user_id": "someone-else"}), patch.object(service, "rpc", return_value={"id": self.pid, "state": "stopped"}) as rpc:
            g.user_id = self.uid
            response = manage.__wrapped__(self.pid, "stop")
        self.assertEqual(response.json["plan"]["state"], "stopped")
        rpc.assert_called_once_with("stop", user_id=self.uid, plan_id=self.pid)

    def test_list_response_never_exposes_reusable_credentials(self):
        with self.app.test_request_context(), patch.object(service, "limits", return_value={}), \
             patch.object(service, "rpc", return_value=[{**self.plan, "authorization": {"authorization_code": "private"}}]):
            g.user_id = self.uid
            response = plans.__wrapped__()
        self.assertNotIn("authorization", response.json["plans"][0])
        self.assertNotIn("authorization_email", response.json["plans"][0])

    def test_receipt_effects_follow_ledger_campus_and_remain_recoverable(self):
        receipt = {"user_id": self.uid, "amount_kobo": 20000, "transaction_id": str(uuid4()),
                   "attempt_id": str(uuid4()), "reference": self.reference, "campus_id": "old-campus"}
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "user_id": self.uid, "provider_reference": self.reference, "campus_id": "ledger-campus"}
        with self.app.app_context(), patch.object(service, "get_db", return_value=db), \
             patch('app.services.wallet_service.apply_wallet_funding_rewards') as reward, \
             patch('app.services.notification_service.send_notification', side_effect=ConnectionError), patch.object(service, "rpc") as rpc:
            with self.assertRaises(ConnectionError):
                service.complete_effects(receipt)
        self.assertEqual(reward.call_args.args[4], "ledger-campus")
        rpc.assert_not_called()  # Retry after failure; do not mark receipt complete.

    def test_attention_notices_use_stable_plan_identity_and_retry_on_failure(self):
        db = MagicMock()
        db.rpc.return_value = [{"id": self.pid, "user_id": self.uid}]
        with self.app.app_context(), patch.object(service, "get_db", return_value=db), \
             patch('app.services.notification_service.send_notification', side_effect=ConnectionError) as send:
            SEND_ATTENTION_NOTICES()
        self.assertEqual(db.rpc.call_count, 1)  # No done receipt on failure.
        self.assertEqual(send.call_args.kwargs["reference_id"], self.pid)
        self.assertEqual(send.call_args.kwargs["action_url"], "/wallet?auto_funding=1")
        self.assertTrue(send.call_args.kwargs["strict"])


if __name__ == "__main__":
    unittest.main()
