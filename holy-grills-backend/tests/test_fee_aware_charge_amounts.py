"""A successful provider charge must never be rejected just because the customer bore the fee.

Regression: event tickets, marketplace purchases and HP bundles compared the settled
gross amount to the price with `<= 0.01`, so any card charge where Paystack added its
fee failed the webhook ("Amount mismatch") after the money had been taken. The event
registrant then stayed on `payment_status = pending` — charged, but absent from the
host's registrant list and from the registrant email.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

# app.config refuses to import without these; the tests below never reach a live project.
for _name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "JWT_SECRET", "SECRET_KEY"):
    os.environ.setdefault(_name, "https://example.supabase.co" if _name == "SUPABASE_URL" else "test")

from app.routes import webhooks as webhooks_module
from app.services.payment_amounts import ChargeAmountError, validate_charge_amount

TICKET = "bbbb0000-0000-4000-8000-000000000005"


class ChargeAmountTests(unittest.TestCase):
    def test_customer_bearing_fee_is_accepted(self):
        """₦3,000 ticket, customer charged ₦3,150 (₦150 fee)."""
        data = {"amount": 315000, "fees": 15000, "status": "success", "currency": "NGN"}
        result = validate_charge_amount(data, 3000, "paystack")
        self.assertEqual(result["expected_kobo"], 300000)
        self.assertEqual(result["net"], 300000)
        self.assertEqual(result["fee_bearer"], "customer")

    def test_merchant_bearing_fee_is_accepted(self):
        data = {"amount": 300000, "fees": 4500, "status": "success", "currency": "NGN"}
        result = validate_charge_amount(data, 3000, "paystack")
        self.assertEqual(result["paid"], 300000)
        self.assertEqual(result["fee_bearer"], "merchant")

    def test_echoed_requested_amount_is_authoritative(self):
        data = {"amount": 319500, "fees": 19500, "requested_amount": 300000,
                "status": "success", "currency": "NGN"}
        result = validate_charge_amount(data, 3000, "paystack")
        self.assertEqual(result["source"], "requested_amount")

    def test_unknown_fees_use_the_documented_tolerance(self):
        data = {"amount": 315000, "status": "success", "currency": "NGN"}
        result = validate_charge_amount(data, 3000, "paystack")
        self.assertIsNone(result["net"])
        self.assertEqual(result["source"], "tolerance")

    def test_wrong_amount_still_fails(self):
        data = {"amount": 500000, "fees": 7500, "status": "success", "currency": "NGN"}
        with self.assertRaises(ChargeAmountError):
            validate_charge_amount(data, 3000, "paystack")

    def test_underpayment_fails(self):
        data = {"amount": 250000, "fees": 3750, "status": "success", "currency": "NGN"}
        with self.assertRaises(ChargeAmountError):
            validate_charge_amount(data, 3000, "paystack")

    def test_non_ngn_charge_fails(self):
        data = {"amount": 300000, "fees": 0, "status": "success", "currency": "USD"}
        with self.assertRaises(ChargeAmountError):
            validate_charge_amount(data, 3000, "paystack")

    def test_flutterwave_amount_is_major_units(self):
        data = {"amount": 3150, "app_fee": 150, "currency": "NGN"}
        result = validate_charge_amount(data, 3000, "flutterwave")
        self.assertEqual(result["net"], 300000)


class EventTicketWebhookTests(unittest.TestCase):
    def _db(self, ticket):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = ticket
        return db

    def test_fee_bearing_ticket_charge_confirms_the_ticket(self):
        ticket = {"id": TICKET, "user_id": "user-1", "card_amount_used": 3000,
                  "status": "confirmed", "payment_status": "pending", "campus_id": "campus-1"}
        data = {"amount": 315000, "fees": 15000, "status": "success", "currency": "NGN",
                "reference": "HG-EVTKT-1"}
        metadata = {"type": "event_ticket_payment", "ticket_id": TICKET, "user_id": "user-1"}
        with patch("app.routes.events.confirm_event_ticket_payment") as confirm:
            campus = webhooks_module._confirm_event_ticket_charge(
                self._db(ticket), metadata, "HG-EVTKT-1", data, "paystack")
        self.assertEqual(campus, "campus-1")
        confirm.assert_called_once()
        breakdown = confirm.call_args.kwargs["provider_response"]["_amount_breakdown"]
        self.assertEqual(breakdown["net"], 300000)

    def test_an_already_paid_ticket_is_not_confirmed_twice(self):
        ticket = {"id": TICKET, "user_id": "user-1", "card_amount_used": 3000,
                  "status": "confirmed", "payment_status": "paid", "campus_id": "campus-1"}
        with patch("app.routes.events.confirm_event_ticket_payment") as confirm:
            webhooks_module._confirm_event_ticket_charge(
                self._db(ticket), {"ticket_id": TICKET}, "ref",
                {"amount": 300000, "currency": "NGN"}, "paystack")
        confirm.assert_not_called()

    def test_a_ticket_for_another_user_is_refused(self):
        ticket = {"id": TICKET, "user_id": "user-1", "card_amount_used": 3000,
                  "status": "confirmed", "payment_status": "pending", "campus_id": "campus-1"}
        with self.assertRaises(ValueError):
            webhooks_module._confirm_event_ticket_charge(
                self._db(ticket),
                {"ticket_id": TICKET, "user_id": "someone-else"}, "ref",
                {"amount": 300000, "currency": "NGN"}, "paystack")


class MarketplaceWebhookTests(unittest.TestCase):
    def test_purchase_is_completed_for_the_expected_amount_not_the_gross_charge(self):
        metadata = {"user_id": "user-1", "listing_id": "listing-1", "expected_amount_kobo": 200000}
        data = {"amount": 209800, "fees": 9800, "status": "success", "currency": "NGN"}
        with patch("app.routes.marketplace.complete_marketplace_card_purchase",
                   return_value=({"id": "purchase-1", "campus_id": "campus-7"}, None, 0)) as complete:
            campus = webhooks_module._complete_marketplace_charge(
                MagicMock(), metadata, "MKT-ref", data, "paystack")
        self.assertEqual(campus, "campus-7")
        self.assertEqual(complete.call_args.kwargs["amount_paid"], 2000)
        self.assertEqual(complete.call_args.kwargs["refund_amount"], 2000)

    def test_a_charge_that_cannot_be_reconciled_is_refused(self):
        metadata = {"user_id": "user-1", "listing_id": "listing-1", "expected_amount_kobo": 200000}
        data = {"amount": 900000, "fees": 13500, "status": "success", "currency": "NGN"}
        with patch("app.routes.marketplace.complete_marketplace_card_purchase") as complete:
            with self.assertRaises(ChargeAmountError):
                webhooks_module._complete_marketplace_charge(
                    MagicMock(), metadata, "MKT-ref", data, "paystack")
        complete.assert_not_called()


class FailedDeliveryVisibilityTests(unittest.TestCase):
    def test_failure_records_the_campus_so_it_shows_in_a_campus_scoped_log(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "campus_id": "campus-3"}
        payload = {"data": {"reference": "ref", "metadata": {"user_id": "user-1"}}}
        with patch("app.routes.webhooks.get_db", return_value=db):
            campus = webhooks_module._record_event_failure(
                "paystack", "charge.success", "ref", payload, ValueError("Amount mismatch"))
        self.assertEqual(campus, "campus-3")
        update = db.table.return_value.eq.return_value.eq.return_value.eq.return_value.update
        fields = update.call_args.args[0]
        self.assertEqual(fields["status"], "failed")
        self.assertEqual(fields["campus_id"], "campus-3")
        self.assertIn("Amount mismatch", fields["error"])

    def test_a_successful_delivery_clears_a_previous_error(self):
        db = MagicMock()
        with patch("app.routes.webhooks.get_db", return_value=db):
            webhooks_module._mark_event("paystack", "charge.success", "ref",
                                        {"status": "processed", "error": None})
        fields = db.table.return_value.eq.return_value.eq.return_value.eq.return_value.update.call_args.args[0]
        self.assertEqual(fields["status"], "processed")
        self.assertIsNone(fields["error"])


if __name__ == "__main__":
    unittest.main()


class WebhookReplayTests(unittest.TestCase):
    """The admin log's retry action replays the stored payload through normal routing."""

    def test_payload_without_a_data_object_is_refused(self):
        with self.assertRaises(ValueError):
            webhooks_module.reprocess_stored_event("paystack", "charge.success", {"event": "charge.success"})
        with self.assertRaises(ValueError):
            webhooks_module.reprocess_stored_event("paystack", "charge.success", None)

    def test_replay_reaches_the_charge_handler(self):
        payload = {"event": "charge.success", "data": {"reference": "ref", "amount": 300000}}
        with patch.object(webhooks_module, "_handle_charge_success", return_value="campus-1") as handler:
            self.assertEqual(
                webhooks_module.reprocess_stored_event("paystack", "charge.success", payload),
                "campus-1",
            )
        self.assertEqual(handler.call_args.args[0]["reference"], "ref")

    def test_a_replayed_event_with_no_handler_falls_back_to_the_payload_campus(self):
        payload = {"event": "transfer.success", "data": {"reference": "ref", "metadata": {"campus_id": "campus-2"}}}
        self.assertEqual(
            webhooks_module.reprocess_stored_event("paystack", "customeridentification.success", payload),
            "campus-2",
        )
