import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.services import wallet_payments as service
from app.routes.wallet import verify_card_funding


class WalletCardVerificationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.db = MagicMock()
        self.db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {'id': 'audit', 'campus_id': 'campus'}
        self.data = {'status': 'success', 'reference': 'ref', 'currency': 'NGN',
                     'amount': 10153, 'fees': 153, 'requested_amount': 10000,
                     'metadata': {'type': 'wallet_topup', 'user_id': 'audit', 'campus_id': 'campus', 'expected_amount_kobo': 10000}}

    def test_customer_fee_is_not_wallet_credit(self):
        with patch.object(service, 'get_db', return_value=self.db), patch.object(service, 'credit_wallet', return_value={'id': 'txn'}) as credit:
            result = service.confirm_paystack_wallet_funding(self.data, 'ref', 'audit')
        self.assertEqual(result['amount'], 100)
        self.assertEqual(credit.call_args.kwargs['amount'], 100)
        self.assertEqual(credit.call_args.kwargs['provider_response']['_amount_breakdown']['net'], 10000)

    def test_legacy_initialized_payment_uses_provider_requested_amount(self):
        self.data['metadata'].pop('expected_amount_kobo')
        with patch.object(service, 'get_db', return_value=self.db), patch.object(service, 'credit_wallet', return_value={}) as credit:
            service.confirm_paystack_wallet_funding(self.data, 'ref', 'audit')
        self.assertEqual(credit.call_args.kwargs['amount'], 100)

    def test_unpaid_payment_does_not_credit(self):
        self.data['status'] = 'abandoned'
        with patch.object(service, 'get_db', return_value=self.db), patch.object(service, 'credit_wallet') as credit:
            self.assertEqual(service.confirm_paystack_wallet_funding(self.data, 'ref', 'audit')['payment_status'], 'pending')
        credit.assert_not_called()

    def test_earlier_fee_inclusive_credit_requires_review(self):
        with patch.object(service, 'get_db', return_value=self.db), patch.object(service, 'credit_wallet', return_value={'amount': 101.53}):
            with self.assertRaises(service.WalletFundingConflict):
                service.confirm_paystack_wallet_funding(self.data, 'ref', 'audit')

    def test_identity_currency_amount_and_campus_mismatch_never_credit(self):
        variants = [{'reference': 'foreign'}, {'currency': 'USD'}, {'amount': 9999},
                    {'requested_amount': 10001}, {'requested_amount': True},
                    {'metadata': {**self.data['metadata'], 'user_id': 'foreign'}},
                    {'metadata': {**self.data['metadata'], 'campus_id': 'foreign'}},
                    {'metadata': {**self.data['metadata'], 'type': 'order_payment'}}]
        for change in variants:
            with self.subTest(change=change), patch.object(service, 'get_db', return_value=self.db), patch.object(service, 'credit_wallet') as credit:
                with self.assertRaises(ValueError):
                    service.confirm_paystack_wallet_funding({**self.data, **change}, 'ref', 'audit')
                credit.assert_not_called()

    def test_callback_uses_authenticated_owner_and_real_verifier_contract(self):
        with self.app.test_request_context(json={'reference': 'ref'}), patch('app.services.payment_service.verify_payment', return_value=self.data) as verify, patch.object(service, 'confirm_paystack_wallet_funding', return_value={'payment_status': 'paid'}) as confirm:
            g.user_id = 'audit'
            response, status = verify_card_funding.__wrapped__()
        self.assertEqual(status, 200)
        self.assertEqual(response.json['payment_status'], 'paid')
        verify.assert_called_once_with('ref')
        confirm.assert_called_once_with(self.data, 'ref', 'audit')

    def test_callback_outage_returns_retryable_failure(self):
        with self.app.test_request_context(json={'reference': 'ref'}), patch('app.services.payment_service.verify_payment', side_effect=ConnectionError):
            g.user_id = 'audit'
            _, status = verify_card_funding.__wrapped__()
        self.assertEqual(status, 503)
