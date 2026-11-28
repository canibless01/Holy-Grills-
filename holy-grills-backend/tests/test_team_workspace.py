import unittest
from unittest.mock import MagicMock,patch
from flask import Flask,g
from app.services.team_workspace import metric_status,capture_due,decorate
from app.routes.team_workspace import team_workspace_bp

class TeamMetricTests(unittest.TestCase):
    def test_zero_is_reported_and_zero_target_does_not_divide(self):
        t={'direction':'lower','target':0,'tolerance':1}
        self.assertEqual(metric_status(t,{'actual':0})['status'],'on_track')
        self.assertEqual(metric_status(t,{'actual':1})['status'],'watch')
        self.assertEqual(metric_status(t,{'actual':2})['status'],'below_target')
        self.assertEqual(metric_status(t,{})['status'],'not_reported')
    def test_rate_tolerance_is_in_percentage_points(self):
        t={'direction':'lower','target':5,'tolerance':1}
        self.assertEqual(metric_status(t,{'actual':6})['status'],'watch')
        self.assertEqual(metric_status(t,{'actual':7})['status'],'below_target')
    def test_on_track_is_not_identical_to_target_met(self):
        t={'direction':'higher','target':100,'tolerance':1}
        self.assertEqual(metric_status(t,{'actual':90}),{'status':'on_track','attainment':90,'target_met':False})
        self.assertEqual(metric_status(t,{'actual':80})['status'],'watch')
        self.assertEqual(metric_status(t,{'actual':79})['status'],'below_target')
    def test_decorate_does_not_invent_results(self):
        d=decorate({'entries':[{'targets':[{'id':'t','direction':'higher','target':3}],'results':{}}]})
        self.assertEqual(d['entries'][0]['scores']['t']['status'],'not_reported')

class TeamNoticeTests(unittest.TestCase):
    def test_safe_digest_whitelists_counts(self):
        db=MagicMock();db.rpc.side_effect=[[{'nickname':'Nick','responsibility':'Designer','due_at':'2026-12-03T20:00:00+00:00','kind':'digest','member_id':'m','week_id':'w','week_version':1,'user_id':'u','notice_key':'digest:day','counts':{'members':4,'submitted':2,'approved':1,'signups':3,'revenue':99999,'email':'private'}}],{'duplicate':True}]
        self.assertEqual(capture_due(db),{'queued':0,'duplicates':1,'skipped':0})
        payload=db.rpc.call_args.args[1]
        self.assertNotIn('99999',payload['p_body']);self.assertNotIn('private',payload['p_body'])
        self.assertIn('Nick',payload['p_body']);self.assertIn('expires_at',payload['p_metadata'])
    def test_custom_copy_only_replaces_known_fields(self):
        db=MagicMock();db.rpc.side_effect=[[{'nickname':'Zee','responsibility':'WhatsApp Manager','due_at':'2026-12-03T20:00:00+00:00','kind':'reminder','member_id':'m','week_id':'w','week_version':1,'rule_id':'r','rule_version':1,'user_id':'u','notice_key':'key','title':'Hi {nickname}','body':'{responsibility}: bring {unknown}'}],{'queued':True}]
        self.assertEqual(capture_due(db)['queued'],1)
        payload=db.rpc.call_args.args[1];self.assertEqual(payload['p_title'],'Hi Zee');self.assertIn('{unknown}',payload['p_body'])
    def test_missing_read_is_not_success(self):
        db=MagicMock();db.rpc.return_value=None
        with self.assertRaises(ValueError):capture_due(db)

class TeamRouteTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.app.register_blueprint(team_workspace_bp,url_prefix='/api/team');self.client=self.app.test_client()
    def test_unauthenticated_cannot_access(self):
        self.assertEqual(self.client.get('/api/team').status_code,401)
    def test_actor_binding_and_request_reference(self):
        from app.routes.team_workspace import mutate
        with self.app.test_request_context('/api/team/member',method='POST',json={'request_id':'20000001-0000-0000-0000-000000000001','p_actor':'foreign','profile_id':'new'}):
            g.user_id='actor';g.user_role='admin';g.campus_id='campus'
            with patch('app.routes.team_workspace.get_db') as getter:
                getter.return_value.rpc.return_value={'saved':True}
                result=mutate.__wrapped__('member');self.assertEqual(result[1],200)
                args=getter.return_value.rpc.call_args.args[1]
                self.assertEqual(args['p_actor'],'actor');self.assertEqual(args['p_scope'],'campus')
    def test_missing_reference_and_deadline_error(self):
        from app.routes.team_workspace import mutate,response
        with self.app.test_request_context('/',method='POST',json={}):
            self.assertEqual(mutate.__wrapped__('save')[1],400)
            self.assertEqual(response({'error':'closed'})[1],409)
