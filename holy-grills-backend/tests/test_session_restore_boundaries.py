"""Credential rotation must not depend on optional attendance processing."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import auth
from app.services import auth_service
from app.db import SupabaseError

class SessionRestoreBoundaryTests(unittest.TestCase):
    def setUp(self): self.app=Flask(__name__)
    def test_refresh_returns_rotated_credentials_without_streak_queries(self):
        result={'access_token':'new-access','refresh_token':'new-refresh','user':{'id':'verified-user'}}
        with self.app.test_request_context('/api/auth/refresh',method='POST',json={'refresh_token':'old-refresh'}), patch.object(auth.auth_service,'refresh_token',return_value=result) as rotate, patch.object(auth,'_streak_checkin',side_effect=AssertionError('must not wait for loyalty')) as streak:
            response,status=auth.refresh.__wrapped__()
        self.assertEqual(status,200);self.assertEqual(response.json['refresh_token'],'new-refresh');rotate.assert_called_once_with('old-refresh');streak.assert_not_called()
    def test_login_returns_credentials_after_active_profile_without_streak_queries(self):
        db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'is_active':True}
        with self.app.test_request_context('/api/auth/login',method='POST',json={'email':'owned@example.test','password':'Password123!'}), patch.object(auth.auth_service,'login',return_value={'user':{'id':'verified-user'},'access_token':'new-access','refresh_token':'new-refresh'}), patch.object(auth,'get_db',return_value=db), patch.object(auth,'_streak_checkin',side_effect=AssertionError('must not wait for loyalty')) as streak:
            response,status=auth.login.__wrapped__()
        self.assertEqual(status,200);self.assertEqual(response.json['access_token'],'new-access');streak.assert_not_called()
    def test_post_hydration_activity_binds_verified_identity(self):
        with self.app.test_request_context('/api/auth/session-activity',method='POST',json={'user_id':'someone-else'}), patch.object(auth,'_streak_checkin') as checkin:
            g.user_id='verified-user';response,status=auth.recover_session_activity.__wrapped__()
        self.assertEqual(status,200);checkin.assert_called_once_with('verified-user')
    def test_rate_limit_and_provider_outage_are_not_invalid_credentials(self):
        for status in (429,500,503):
            with self.subTest(status=status):
                db=MagicMock();db.auth_refresh.side_effect=SupabaseError('provider unavailable',status,{})
                with patch.object(auth_service,'get_db',return_value=db),self.assertRaises(SupabaseError):auth_service.refresh_token('refresh')
    def test_rejected_refresh_is_explicitly_invalid(self):
        db=MagicMock();db.auth_refresh.side_effect=SupabaseError('invalid refresh',400,{})
        with patch.object(auth_service,'get_db',return_value=db),self.assertRaises(ValueError):auth_service.refresh_token('revoked')
