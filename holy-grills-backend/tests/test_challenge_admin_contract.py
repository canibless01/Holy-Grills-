"""Challenge configuration must be valid and reflect actual persistence."""
import inspect
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from werkzeug.exceptions import Forbidden
from app.routes import challenges

CAMPUS = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'

class ChallengeAdminContractTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.db=MagicMock();self.q=self.db.table.return_value
        for method in ('select','eq','single','limit'):getattr(self.q,method).return_value=self.q
        self.body={'title':'Three deliveries','trigger_type':'order_count','trigger_value':3,'hp_awarded':50,'time_window':'weekly','is_active':True}
    def call(self,handler,body,*,role='admin',campus=CAMPUS,args=()):
        with self.app.test_request_context(method='POST',json=body),patch.object(challenges,'get_user_client',return_value=self.db):
            g.user_id='admin';g.user_role=role;g.campus_id=campus
            return inspect.unwrap(handler)(*args)
    def test_lifetime_and_optional_fields_need_no_badge_artwork(self):
        with self.app.app_context():safe=challenges._milestone_fields({**self.body,'time_window':None,'description':None,'social_link':None},creating=True)
        self.assertNotIn('icon_won',safe);self.assertIsNone(safe['time_window'])
    def test_invalid_create_and_patch_stop_before_database(self):
        for bad in ({'title':''},{'title':{}},{'hp_awarded':True},{'hp_awarded':-1},{'hp_awarded':1.5},{'trigger_value':0},{'trigger_value':'3'},{'time_window':'daily'},{'is_active':'false'},{'social_link':'javascript:alert(1)'},{'social_link':'https://name@valid.test/x'},{'description':[]}):
            for handler,args in ((challenges.admin_create_milestone,()),(challenges.admin_update_milestone,('challenge',))):
                with self.subTest(bad=bad,handler=handler.__name__):self.assertEqual(self.call(handler,{**self.body,**bad},args=args)[1],400)
        self.db.table.assert_not_called()
    def test_create_pins_campus_and_reports_refused_insert(self):
        self.q.insert.return_value=[]
        self.assertEqual(self.call(challenges.admin_create_milestone,self.body)[1],403)
        self.assertEqual(self.q.insert.call_args.args[0]['campus_id'],CAMPUS)
        with self.assertRaises(Forbidden):self.call(challenges.admin_create_milestone,{**self.body,'campus_id':OTHER})
    def test_update_cannot_move_history_or_report_zero_rows_as_saved(self):
        self.q.execute.return_value={'id':'challenge','campus_id':CAMPUS}
        self.assertEqual(self.call(challenges.admin_update_milestone,{'campus_id':OTHER},args=('challenge',))[1],400)
        self.q.update.assert_not_called();self.q.update.return_value=[]
        self.assertEqual(self.call(challenges.admin_update_milestone,{'title':'Changed'},args=('challenge',))[1],403)
    def test_campus_admin_cannot_edit_global_or_foreign_definition(self):
        for campus in (None,OTHER):
            self.q.execute.return_value={'id':'challenge','campus_id':campus}
            with self.subTest(campus=campus),self.assertRaises(Forbidden):self.call(challenges.admin_update_milestone,{'title':'Changed'},args=('challenge',))
        self.q.update.assert_not_called()
    def test_super_admin_global_create_and_patch_are_supported(self):
        saved={**self.body,'id':'challenge','campus_id':None};self.q.insert.return_value=[saved]
        response,status=self.call(challenges.admin_create_milestone,self.body,role='super_admin',campus=None)
        self.assertEqual(status,201);self.assertEqual(response.json['id'],'challenge');self.assertIsNone(self.q.insert.call_args.args[0]['campus_id'])
        self.q.execute.return_value=saved;self.q.update.return_value=[{**saved,'title':'Changed'}]
        response,status=self.call(challenges.admin_update_milestone,{'title':'Changed'},role='super_admin',campus=None,args=('challenge',))
        self.assertEqual(status,200);self.assertEqual(response.json['title'],'Changed')
    def test_write_exception_returns_safe_unavailable(self):
        self.q.insert.side_effect=RuntimeError('private schema details')
        response,status=self.call(challenges.admin_create_milestone,self.body)
        self.assertEqual(status,503);self.assertNotIn('private schema',response.json['error'])


class ChallengeProgressTests(unittest.TestCase):
    def test_available_recurring_progress_comes_from_current_period_data(self):
        from tests.test_badges_and_address_fields import FakeDb, _milestone
        from app.services import milestone_service
        db=FakeDb(milestones=[dict(_milestone('weekly','Weekly target',window='weekly'),trigger_value=3)])
        with Flask(__name__).app_context(),patch.object(milestone_service,'get_user_client',return_value=db),patch.object(milestone_service,'_compute_trigger_progress',return_value=2) as compute:
            result=milestone_service.get_user_milestones('student')
        self.assertEqual(result['challenges_available'][0]['progress'],2)
        self.assertEqual(compute.call_args.args[4],'weekly')
