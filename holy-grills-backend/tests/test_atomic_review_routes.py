"""Review inputs must not silently clamp, and the displayed award is the real one."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes.orders import submit_review


class AtomicReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['REVIEW_HP'] = 20
        self.db = MagicMock()
        self.db.table.return_value.select.return_value.in_.return_value.is_.return_value.execute.return_value = []
        self.db.rpc.return_value = {'success': True, 'review': {'rating': 4}, 'hp_awarded': 5, 'hp_capped': True}

    def invoke(self, body):
        with self.app.test_request_context(method='POST', json=body), \
             patch('app.routes.orders.get_db', return_value=self.db), \
             patch('app.services.hp_service._get_hp_multiplier', return_value=1):
            g.user_id = 'student'
            g.campus_id = 'campus'
            return submit_review.__wrapped__('order')

    def test_invalid_ratings_are_rejected_instead_of_clamped(self):
        for key in ['rating', 'kitchen_rating', 'rider_rating']:
            for value in [0, 6, True, 1.5, 'Infinity', 'bad']:
                with self.subTest(key=key, value=value):
                    _, status = self.invoke({'rating': 4, key: value})
                    self.assertEqual(status, 400)
        self.db.rpc.assert_not_called()

    def test_missing_rating_and_non_object_body_are_rejected(self):
        for body in [{}, ['invalid']]:
            _, status = self.invoke(body)
            self.assertEqual(status, 400)
        self.db.rpc.assert_not_called()

    def test_client_cannot_choose_award_and_response_uses_capped_award(self):
        response, status = self.invoke({'rating': 4, 'hp_awarded': 1000000})
        self.assertEqual(status, 201)
        self.assertEqual(response.get_json()['hp_awarded'], 5)
        self.assertEqual(self.db.rpc.call_args.args[1]['p_hp_amount'], 20)

    def test_atomic_failure_is_not_presented_as_review_success(self):
        self.db.rpc.return_value = {'success': False, 'error': 'review_failed'}
        response, status = self.invoke({'rating': 4})
        self.assertEqual(status, 503)
        self.assertNotIn('review', response.get_json())
