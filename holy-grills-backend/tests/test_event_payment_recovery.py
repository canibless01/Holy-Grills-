"""Provider calls are mocked; these are not live payment receipts."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.routes import events
EVENT = 'bbbb0000-0000-4000-8000-000000000004'
TICKET = 'bbbb0000-0000-4000-8000-000000000005'
class EventPaymentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['PAYSTACK_SECRET_KEY'] = 'test-only'
    def db(self, **details):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {'event_id': EVENT, 'status': 'pending', 'payment_status': 'pending', **details}
        return db
    def test_saved_link_does_not_create_new_intent(self):
        db = self.db(payment_reference='existing', metadata={'card_authorization_url': 'https://checkout.paystack.com/example'})
        with self.app.app_context(), patch('app.services.payment_service.initialize_payment') as initialize:
            result = events._initiate_event_card_payment(db, TICKET, EVENT, 100, 'a@example.invalid')
            self.assertIn('authorization_url', result)
            initialize.assert_not_called()
    def test_retry_preserves_existing_payable_reference_and_answers(self):
        db = self.db(payment_reference='previous-reference', metadata={'registration_answers': {'meal': 'rice'}})
        with self.app.app_context(), patch('app.services.payment_service.initialize_payment', return_value={'authorization_url': 'https://checkout.paystack.com/example'}) as initialize:
            result = events._initiate_event_card_payment(db, TICKET, EVENT, 100, 'a@example.invalid')
            self.assertIn('authorization_url', result)
            self.assertEqual(initialize.call_args.kwargs['reference'], 'previous-reference')
            self.assertEqual(db.table.return_value.eq.return_value.update.call_args.args[0]['metadata']['registration_answers'], {'meal': 'rice'})
    def test_closed_reservation_cannot_initialize(self):
        for details in ({'status': 'cancelled'}, {'payment_status': 'paid'}, {'payment_expires_at': '2000-01-01T00:00:00Z'}):
            with self.app.app_context(), patch('app.services.payment_service.initialize_payment') as initialize:
                self.assertIn('error', events._initiate_event_card_payment(self.db(**details), TICKET, EVENT, 100, 'a@example.invalid'))
                initialize.assert_not_called()
    def test_fresh_reference_is_stable_for_ticket(self):
        with self.app.app_context(), patch('app.services.payment_service.initialize_payment', return_value={'authorization_url': 'https://checkout.paystack.com/example'}) as initialize:
            events._initiate_event_card_payment(self.db(), TICKET, EVENT, 100, 'a@example.invalid')
            first = initialize.call_args.kwargs['reference']
            events._initiate_event_card_payment(self.db(), TICKET, EVENT, 100, 'a@example.invalid')
            self.assertEqual(first, initialize.call_args.kwargs['reference'])
    def test_guest_identity_types_and_formats_reject_before_reservation(self):
        from flask import g
        db = MagicMock()
        event_query = MagicMock()
        event_query.select.return_value.eq.return_value.single.return_value.execute.return_value = {'id': EVENT, 'is_published': True}
        tiers_query = MagicMock()
        tiers_query.select.return_value.eq.return_value.limit.return_value.execute.return_value = []
        db.table.side_effect = lambda name: event_query if name == 'events' else tiers_query
        for invalid in ({'guest_email': ['invalid']}, {'guest_phone': {'bad': True}}, {'guest_email': 'invalid'}, {'guest_phone': '123'}):
            with self.app.test_request_context(method='POST', json={'guest_email': 'a@example.invalid', 'guest_name': 'Audit guest', 'guest_phone': '08012345678', **invalid}), patch.object(events, 'get_user_client', return_value=db), patch.object(events, '_get_campus_id', return_value=None), patch.object(events, 'get_db') as service:
                g.user_id = None
                _, status = events.register_for_event.__wrapped__(EVENT)
                self.assertEqual(status, 400)
                service.assert_not_called()
    def test_existing_pending_authenticated_registration_resumes_card_setup(self):
        from flask import g
        db = MagicMock()
        event_query = MagicMock()
        event_query.select.return_value.eq.return_value.single.return_value.execute.return_value = {'id': EVENT, 'is_published': True}
        tiers_query = MagicMock()
        tiers_query.select.return_value.eq.return_value.limit.return_value.execute.return_value = []
        db.table.side_effect = lambda name: event_query if name == 'events' else tiers_query
        service = MagicMock()
        service.rpc.return_value = {'ticket_id': TICKET, 'already_registered': True, 'status': 'pending', 'payment_status': 'pending', 'card_amount_used': 100}
        with self.app.test_request_context(method='POST', json={}), patch.object(events, 'get_user_client', return_value=db), patch.object(events, '_get_campus_id', return_value=None), patch.object(events, 'get_db', return_value=service), patch.object(events, '_initiate_event_card_payment', return_value={'authorization_url': 'https://checkout.paystack.com/example'}) as initialize:
            g.user_id, g.jwt_payload = TICKET, {'email': 'a@example.invalid'}
            response, status = events.register_for_event.__wrapped__(EVENT)
            self.assertEqual(status, 201)
            self.assertIn('authorization_url', response.json)
            initialize.assert_called_once()
