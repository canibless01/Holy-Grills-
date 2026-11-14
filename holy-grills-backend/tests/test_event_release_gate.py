import unittest
from unittest.mock import patch,MagicMock
from flask import Flask,g
from app.routes import events

class EventReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.app.register_blueprint(events.events_bp,url_prefix='/api/events')
    def test_off_blocks_public_routes_before_reads_or_admission(self):
        with patch.object(events,'is_feature_enabled',return_value=False),patch.object(events,'get_user_client',side_effect=AssertionError('no event access')):
            client=self.app.test_client()
            for method,path in [('get',''),('get','/an-event'),('get','/an-event/tiers'),('get','/tiers/a-tier/detail'),('post','/an-event/register'),('post','/an-event/checkin')]:
                with self.subTest(path=path):self.assertEqual(getattr(client,method)('/api/events'+path).status_code,403)
    def test_on_delegates_without_changing_handler_arguments(self):
        handler=MagicMock(return_value='allowed')
        with self.app.test_request_context('/'),patch.object(events,'_get_campus_id',return_value='campus'),patch.object(events,'is_feature_enabled',return_value=True) as enabled:
            g.user_role='student';self.assertEqual(events.require_event_release(handler)('event'),'allowed');handler.assert_called_once_with('event');enabled.assert_called_once_with('events','campus')
    def test_staff_preview_does_not_enable_admission(self):
        for method in ('GET','POST'):
            with self.app.test_request_context('/',method=method),patch.object(events,'_get_campus_id',return_value='campus'),patch.object(events,'is_feature_enabled',return_value=False):
                g.user_role='super_admin';handler=MagicMock(return_value='preview');result=events.require_event_release(handler)()
                if method=='GET':self.assertEqual(result,'preview')
                else:self.assertEqual(result[1],403);handler.assert_not_called()
