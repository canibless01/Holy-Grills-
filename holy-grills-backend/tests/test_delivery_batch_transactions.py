"""Transport boundaries; the isolated live harness proves transaction conservation."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import admin
from app.db import SupabaseError

ACTOR = 'ba210000-0000-4000-8000-000000000001'
BATCH = 'ba210000-0000-4000-8000-000000000002'
ORDER = 'ba210000-0000-4000-8000-000000000003'
RIDER = 'ba210000-0000-4000-8000-000000000004'
WINDOW = 'ba210000-0000-4000-8000-000000000005'
INTENT = 'ba210000-0000-4000-8000-000000000006'


class BatchTransactionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.db = MagicMock()
        self.db.rpc.return_value = {'id': BATCH, 'rider_id': RIDER, 'status': 'assigned'}

    def create(self, body):
        with self.app.test_request_context(method='POST', json=body), \
             patch.object(admin, 'get_db', return_value=self.db), \
             patch.object(admin, '_batch_saved_effects'):
            g.user_id = ACTOR
            return admin.create_batch.__wrapped__()

    def test_actor_bound_by_server_and_retry_intent_retained(self):
        response, status = self.create({'rider_id': RIDER, 'window_id': WINDOW,
                                        'order_ids': [ORDER], 'idempotency_key': INTENT})
        self.assertEqual(status, 201)
        self.assertEqual(response.json['id'], BATCH)
        self.db.rpc.assert_called_once_with('hg_manage_delivery_batch_atomic', {
            'p_actor_id': ACTOR, 'p_action': 'create', 'p_batch_id': None,
            'p_body': {'rider_id': RIDER, 'window_id': WINDOW,
                       'order_ids': [ORDER], 'idempotency_key': INTENT},
        })
        self.db.table.assert_not_called()

    def test_invalid_bulk_input_never_starts_mutation(self):
        good = {'rider_id': RIDER, 'window_id': WINDOW, 'order_ids': [ORDER]}
        for body in ([], {**good, 'order_ids': []}, {**good, 'order_ids': [ORDER, ORDER]},
                     {**good, 'order_ids': ['foreign']}, {**good, 'rider_id': None},
                     {**good, 'actor_id': 'spoofed'}, {**good, 'zone': ['invalid']}):
            with self.subTest(body=body):
                self.assertEqual(self.create(body)[1], 400)
                self.db.rpc.assert_not_called()

    def test_expected_transaction_refusals_are_not_server_success(self):
        for marker, status in [('batch_forbidden', 403), ('batch_not_found', 404),
                               ('batch_conflict', 409), ('batch_rider_invalid', 400),
                               ('batch_invalid', 400), ('unknown', 503)]:
            with self.subTest(marker=marker), self.app.test_request_context(), \
                 patch.object(admin, 'get_db', return_value=self.db):
                g.user_id = ACTOR
                self.db.rpc.side_effect = SupabaseError('RPC refused', details={'message': marker})
                receipt, failure = admin._batch_transaction('create', None, {})
                self.assertIsNone(receipt)
                self.assertEqual(failure[1], status)

    def test_split_uses_source_batch_and_atomic_rpc(self):
        with self.app.test_request_context(method='POST', json={'rider_id': RIDER,
                'order_ids': [ORDER], 'idempotency_key': INTENT}), \
             patch.object(admin, 'get_db', return_value=self.db), \
             patch.object(admin, '_batch_saved_effects'):
            g.user_id = ACTOR
            response, status = admin.split_batch.__wrapped__(BATCH)
        self.assertEqual(status, 201)
        args = self.db.rpc.call_args.args[1]
        self.assertEqual((args['p_action'], args['p_batch_id']), ('split', BATCH))
        self.db.table.assert_not_called()

    def test_cancellation_does_not_release_orders_in_a_python_loop(self):
        with self.app.test_request_context(method='DELETE'), \
             patch.object(admin, 'get_db', return_value=self.db), \
             patch.object(admin, '_batch_saved_effects'):
            g.user_id = ACTOR
            response, status = admin.cancel_batch.__wrapped__(BATCH)
        self.assertEqual(status, 200)
        self.assertEqual(self.db.rpc.call_args.args[1]['p_action'], 'cancel')
        self.db.table.assert_not_called()

    def test_saved_replay_does_not_repeat_followup_side_effects(self):
        with self.app.test_request_context(), patch.object(admin, '_audit') as audit, \
             patch.object(admin.threading, 'Thread') as thread:
            g.user_id = ACTOR
            admin._batch_saved_effects('split', {'id': BATCH, 'replayed': True}, {})
        audit.assert_not_called()
        thread.assert_not_called()
