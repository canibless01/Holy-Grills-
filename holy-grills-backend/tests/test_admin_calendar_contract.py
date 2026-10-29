"""Calendar page scopes, date validation and customer current-period selection."""
import inspect,unittest
from unittest.mock import MagicMock,patch
from flask import Flask,g
from werkzeug.exceptions import Forbidden
from app.routes import academic_calendar as calendar
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';ID='33333333-3333-4333-8333-333333333333'
class CalendarAdminContractTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.db=MagicMock();self.q=self.db.table.return_value
        for name in ('select','eq','or_','is_','order','single','lte','gte','limit'):getattr(self.q,name).return_value=self.q
        self.q.execute.return_value=[];self.q.insert.return_value=[{'id':ID}];self.q.update.return_value=[{'id':ID}]
        self.body={'period_type':'semester','name':'Controlled semester','start_date':'2026-10-26','end_date':'2026-12-31','academic_year':'2026-2027','description':'Controlled details'}
    def call(self,handler,*,role='admin',path='/',body=None,headers=None,args=()):
        with self.app.test_request_context(path,method='POST' if body is not None else 'GET',json=body,headers=headers),patch.object(calendar,'get_user_client',return_value=self.db):
            g.user_id='actor';g.user_role=role;g.campus_id=A
            return inspect.unwrap(handler)(*args)
    def test_all_campuses_does_not_inherit_super_student_campus(self):
        self.call(calendar.list_academic_calendar_entries,role='super_admin',headers={'X-Campus-Scope':'global'})
        self.q.or_.assert_not_called();self.q.is_.assert_not_called()
    def test_selected_campus_filters_super_but_cannot_redirect_campus_admin(self):
        self.call(calendar.list_academic_calendar_entries,role='super_admin',headers={'X-Campus-ID':B})
        self.q.or_.assert_called_once_with(f'campus_id.eq.{B},campus_id.is.null');self.q.reset_mock()
        self.call(calendar.list_academic_calendar_entries,path='/?campus_id='+B,headers={'X-Campus-ID':B})
        self.q.or_.assert_called_once_with(f'campus_id.eq.{A},campus_id.is.null')
    def test_current_period_prefers_campus_over_newer_global(self):
        self.q.execute.return_value=[{'id':'global','campus_id':None,'start_date':'2026-10-28'},{'id':'campus','campus_id':A,'start_date':'2026-10-26'}]
        response,status=self.call(calendar.get_current_academic_period)
        self.assertEqual(status,200);self.assertEqual(response.json['current_period']['id'],'campus')
    def test_invalid_create_never_inserts(self):
        for invalid in ({'name':''},{'academic_year':''},{'end_date':'2026-10-25'},{'start_date':'not-a-date'},{'period_type':'unsupported'},{'is_active':'invalid'},{'description':{}},{'campus_id':'invalid'}):
            with self.subTest(invalid=invalid):self.assertEqual(self.call(calendar.create_academic_calendar_entry,body={**self.body,**invalid})[1],400)
        self.q.insert.assert_not_called()
    def test_campus_create_and_explicit_super_global_are_distinct(self):
        self.assertEqual(self.call(calendar.create_academic_calendar_entry,body=self.body)[1],201)
        self.assertEqual(self.q.insert.call_args.args[0]['campus_id'],A)
        self.assertEqual(self.call(calendar.create_academic_calendar_entry,role='super_admin',headers={'X-Campus-ID':B},body={**self.body,'campus_id':None})[1],201)
        self.assertIsNone(self.q.insert.call_args.args[0]['campus_id'])
    def test_foreign_or_global_edit_is_denied_to_campus_admin(self):
        for scope in (None,B):
            self.q.execute.return_value={'id':ID,'campus_id':scope,'start_date':'2026-10-26','end_date':'2026-12-31'}
            with self.assertRaises(Forbidden):self.call(calendar.update_academic_calendar_entry,args=(ID,),body={'name':'Changed'})
        self.q.update.assert_not_called()
    def test_partial_date_edit_checks_retained_other_boundary(self):
        self.q.execute.return_value={'id':ID,'campus_id':A,'start_date':'2026-10-26','end_date':'2026-12-31'}
        self.assertEqual(self.call(calendar.update_academic_calendar_entry,args=(ID,),body={'end_date':'2026-10-25'})[1],400)
        self.q.update.assert_not_called()
    def test_retire_preserves_dates_and_record(self):
        self.q.execute.return_value={'id':ID,'campus_id':A,'start_date':'2026-10-26','end_date':'2026-12-31'}
        self.assertEqual(self.call(calendar.update_academic_calendar_entry,args=(ID,),body={'is_active':False})[1],200)
        saved=self.q.update.call_args.args[0];self.assertIs(saved['is_active'],False);self.assertNotIn('start_date',saved);self.assertNotIn('campus_id',saved)
