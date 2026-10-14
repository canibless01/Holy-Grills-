"""Identity boundary regressions; these do not prove provider delivery."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import graduation
from app.services import auth_service
USER = 'bbbb0000-0000-4000-8000-000000000099'
class IdentityCompletionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(MINIMUM_AGE=16, GRADUATION_HP=1000)
    def test_graduation_award_has_stable_per_user_receipt(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {'id': USER, 'academic_level': '400L', 'graduation_claimed': False, 'full_name': 'Audit Graduate'}
        db.table.return_value.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = {'value': '400'}
        db.table.return_value.eq.return_value.eq.return_value.update.return_value = [{'id': USER}]
        with self.app.test_request_context(method='POST'), patch.object(graduation, 'get_user_client', return_value=db), patch.object(graduation, 'get_db', return_value=db), patch.object(graduation, 'resolve_level', return_value={'rank': 400}), patch.object(graduation, 'award_active_hp', return_value={'awarded': 1000}) as award, patch('app.services.milestone_service.check_milestone_trigger'), patch('app.services.notification_service.send_notification'):
            g.user_id, g.campus_id = USER, None
            _, status = graduation.claim_graduation.__wrapped__()
            self.assertEqual(status, 200)
            self.assertEqual(award.call_args.kwargs['reference_id'], USER)
            self.assertEqual(award.call_args.kwargs['reference_type'], 'graduation')
    def test_invalid_dob_rejected_before_account_creation(self):
        for dob in ('2000-01-01garbage', '2000-01-01T00:00:00', 'not-a-date'):
            db = MagicMock()
            with self.app.app_context(), patch.object(auth_service, 'get_db', return_value=db):
                with self.assertRaises(ValueError):
                    auth_service.register('audit@example.invalid', 'LongPassword!1', 'Audit', date_of_birth=dob)
                db.auth_sign_up.assert_not_called()
    def test_login_never_returns_issued_tokens_when_profile_lookup_fails(self):
        from app.routes import auth
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = RuntimeError('unavailable')
        with self.app.test_request_context(method='POST', json={'email': 'audit@example.invalid', 'password': 'LongPassword!1'}), patch.object(auth.auth_service, 'login', return_value={'user': {'id': USER}, 'access_token': 'issued'}), patch.object(auth, 'get_db', return_value=db):
            response, status = auth.login.__wrapped__()
            self.assertEqual(status, 503)
            self.assertNotIn('access_token', response.json)
            db.auth_sign_out.assert_called_once_with('issued', scope='local')
    def test_reset_revokes_own_token_and_reports_revocation_failure_truthfully(self):
        from app.routes import auth
        for revoked in (True, False):
            db = MagicMock()
            db.auth_update_user.return_value = {'id': USER}
            with self.app.test_request_context(method='POST', json={'access_token': 'recovery-jwt', 'new_password': 'LongPassword!1'}), patch.object(auth, 'get_db', return_value=db), patch.object(auth, '_revoke_own_sessions', return_value=revoked) as revoke, patch.object(auth, '_notify_security'):
                response, status = auth.reset_password_confirm.__wrapped__()
                self.assertEqual(status, 200)
                self.assertEqual(response.json['sessions_revoked'], revoked)
                revoke.assert_called_once_with('recovery-jwt')
