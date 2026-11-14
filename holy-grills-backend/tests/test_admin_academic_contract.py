"""Academic setup page contracts: scopes, validation, canonical faculties and outages."""
import inspect
import unittest
from unittest.mock import MagicMock,patch
from flask import Flask,g
from werkzeug.exceptions import Forbidden
from app.routes import departments,academic_levels
from app.db import SupabaseError
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';ID='33333333-3333-4333-8333-333333333333'
class AcademicAdminContractTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.db=MagicMock();self.q=self.db.table.return_value
        for name in ('select','eq','or_','is_','order','single'):getattr(self.q,name).return_value=self.q
        self.q.execute.return_value=[]
    def call(self,module,handler,*,role='admin',path='/',body=None,headers=None,args=()):
        with self.app.test_request_context(path,method='POST' if body is not None else 'GET',json=body,headers=headers),patch.object(module,'get_user_client',return_value=self.db):
            g.user_id='actor';g.user_role=role;g.campus_id=A
            return inspect.unwrap(handler)(*args)
    def test_super_selected_campus_filters_both_lists(self):
        for module,handler in ((departments,departments.admin_list_departments),(academic_levels,academic_levels.admin_list_academic_levels)):
            self.q.reset_mock();self.call(module,handler,role='super_admin',headers={'X-Campus-ID':B})
            self.q.or_.assert_called_once_with(f'campus_id.eq.{B},campus_id.is.null')
    def test_campus_admin_ignores_foreign_read_selector(self):
        self.call(departments,departments.admin_list_departments,path='/?campus_id='+B,headers={'X-Campus-ID':B})
        self.q.or_.assert_called_once_with(f'campus_id.eq.{A},campus_id.is.null')
    def test_all_campuses_super_read_stays_unfiltered(self):
        self.call(departments,departments.admin_list_departments,role='super_admin')
        self.q.or_.assert_not_called();self.q.is_.assert_not_called()
    def test_invalid_list_campus_is_rejected(self):
        self.assertEqual(self.call(departments,departments.admin_list_departments,path='/?campus_id=invalid')[1],400)
        self.q.execute.assert_not_called()
    def test_outage_is_retryable_not_an_empty_list(self):
        self.q.execute.side_effect=SupabaseError('unavailable',503,{})
        for module,handler in ((departments,departments.admin_list_departments),(academic_levels,academic_levels.admin_list_academic_levels)):
            self.assertEqual(self.call(module,handler)[1],503)
    def test_public_faculties_use_the_effective_department_mapping(self):
        self.q.execute.return_value=[{'name':'Computer Science','faculty':'Computing','campus_id':None},{'name':'Computer Science','faculty':'School of Computing','campus_id':A},{'name':'Postgraduate','faculty':'Postgraduate','campus_id':A}]
        response,status=self.call(departments,departments.list_faculties)
        self.assertEqual(status,200);self.assertEqual(response.json['faculties'],['Postgraduate','School of Computing'])
    def test_super_create_follows_header_not_profile_campus(self):
        self.q.insert.return_value=[{'id':ID}]
        self.assertEqual(self.call(departments,departments.admin_create_department,role='super_admin',headers={'X-Campus-ID':B},body={'name':'New','faculty':'School'})[1],201)
        self.assertEqual(self.q.insert.call_args.args[0]['campus_id'],B)
        self.call(academic_levels,academic_levels.admin_create_academic_level,role='super_admin',body={'name':'Postgraduate','value':'PG','rank':0,'sort_order':0})
        body=self.q.insert.call_args.args[0];self.assertIsNone(body['campus_id']);self.assertEqual(body['rank'],0);self.assertEqual(body['sort_order'],0)
    def test_invalid_department_fields_make_no_insert(self):
        for body in ({'name':'New','faculty':' '},{'name':'New','faculty':'School','slug':'bad slug'},{'name':'New','faculty':'School','sort_order':-1}):
            self.assertEqual(self.call(departments,departments.admin_create_department,body=body)[1],400)
        self.q.insert.assert_not_called()
    def test_global_and_other_campus_edits_are_denied(self):
        for module,handler in ((departments,departments.admin_update_department),(academic_levels,academic_levels.admin_update_academic_level)):
            for scope in (None,B):
                self.q.execute.return_value={'id':ID,'campus_id':scope}
                with self.assertRaises(Forbidden):self.call(module,handler,args=(ID,),body={'name':'Changed'})
        self.q.update.assert_not_called()
    def test_edit_cannot_move_a_record_to_another_campus(self):
        self.q.execute.return_value={'id':ID,'campus_id':A}
        self.assertEqual(self.call(departments,departments.admin_update_department,args=(ID,),body={'campus_id':B})[1],400)
        self.q.update.assert_not_called()
