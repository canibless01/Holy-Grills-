"""Creating a duplicate flag must never behave like editing the existing switch."""
import unittest
from unittest.mock import MagicMock,patch
from flask import Flask,g
from app.routes.admin_feature_flags import _upsert_feature_flag,create_feature_flag

class FeatureFlagMutationTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.db=MagicMock();self.row={'feature_name':'hp_transfer','is_active':False,'description':'Saved description'}
        self.db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value=self.row
    def test_duplicate_create_returns_conflict_without_writing(self):
        with self.app.test_request_context(),patch('app.routes.admin_feature_flags.get_user_client',return_value=self.db):
            g.user_id='super';response,status=_upsert_feature_flag('hp_transfer',{'is_active':True,'description':'Overwrite'},create_status=201)
        self.assertEqual(status,409);self.assertIn('already exists',response.get_json()['error']);self.db.table.return_value.update.assert_not_called();self.db.table.return_value.insert.assert_not_called()
    def test_matching_create_is_a_readonly_retry(self):
        with self.app.test_request_context(),patch('app.routes.admin_feature_flags.get_user_client',return_value=self.db):
            _,status=_upsert_feature_flag('hp_transfer',{'is_active':False,'description':'Saved description'},create_status=201)
        self.assertEqual(status,200);self.db.table.return_value.update.assert_not_called();self.db.table.return_value.insert.assert_not_called()
    def test_non_global_scope_is_rejected_before_database_access(self):
        with self.app.test_request_context(),patch('app.routes.admin_feature_flags.get_user_client',return_value=self.db):
            response,status=_upsert_feature_flag('hp_transfer',{'is_active':False,'campus_id':'campus'})
        self.assertEqual(status,400);self.db.table.assert_not_called()
    def test_invalid_boolean_or_description_is_rejected_before_lookup(self):
        for body in [{'is_active':'false'},{'is_active':1},{'description':True},{'description':'a'*501}]:
            with self.subTest(body=body),self.app.test_request_context(),patch('app.routes.admin_feature_flags.get_user_client',return_value=self.db):
                _,status=_upsert_feature_flag('hp_transfer',body)
            self.assertEqual(status,400)
        self.db.table.assert_not_called()
    def test_non_text_name_is_a_validation_error(self):
        for name in [True,1,[],{}]:
            with self.subTest(name=name),self.app.test_request_context(method='POST',json={'feature_name':name}):
                _,status=create_feature_flag.__wrapped__()
            self.assertEqual(status,400)
