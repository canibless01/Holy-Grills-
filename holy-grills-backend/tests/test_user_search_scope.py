"""Email punctuation must survive search while the campus boundary stays explicit."""
import inspect
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes.auth import search_users


class UserSearchScopeTests(unittest.TestCase):
    def test_email_search_preserves_dots_and_limits_matches_to_active_campus_students(self):
        app = Flask(__name__); db = MagicMock(); query = MagicMock()
        query.neq.return_value = query; query.eq.return_value = query
        query.or_.return_value = query; query.limit.return_value = query
        query.execute.return_value = []
        db.table.return_value.select.return_value = query
        with app.test_request_context('/?q=student.name%40example.com'), patch('app.routes.auth.get_db', return_value=db):
            g.user_id = 'requester'; g.user_role = 'admin'; g.campus_id = 'campus-a'
            _, status = inspect.unwrap(search_users)()
        self.assertEqual(status, 200)
        self.assertIn('email.ilike.*student.name@example.com*', query.or_.call_args.args[0])
        query.eq.assert_any_call('campus_id', 'campus-a')
        query.eq.assert_any_call('role', 'student'); query.eq.assert_any_call('is_active', True)
        query.neq.assert_called_once_with('id', 'requester')

    def test_user_without_campus_cannot_search(self):
        app = Flask(__name__)
        with app.test_request_context('/?q=student%40example.com'), patch('app.routes.auth.get_db') as db:
            g.user_id = 'requester'; g.user_role = 'student'; g.campus_id = None
            response, status = inspect.unwrap(search_users)()
        self.assertEqual(status, 200); self.assertEqual(response.get_json()['results'], [])
        db.return_value.table.assert_not_called()
