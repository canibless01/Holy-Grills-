"""Kitchen stock controls read the same scoped availability override they write."""
import unittest
from unittest.mock import MagicMock
from app.routes.kitchen import _attach_campus_availability

class KitchenStockSnapshotTests(unittest.TestCase):
    def test_one_scoped_lookup_rehydrates_all_tickets_and_defaults_absent_override(self):
        db=MagicMock();q=db.table.return_value
        for method in ('select','eq','in_'):getattr(q,method).return_value=q
        q.execute.return_value=[{'menu_item_id':'meal-a','is_available':False}]
        orders=[{'order_items':[{'menu_item_id':'meal-a'},{'menu_item_id':'meal-b'}]}, {'order_items':[{'menu_item_id':'meal-a'},{'name_snapshot':'Legacy item'}]}]
        rows=_attach_campus_availability(db,orders,'campus-b')
        self.assertFalse(rows[0]['order_items'][0]['campus_is_available'])
        self.assertFalse(rows[1]['order_items'][0]['campus_is_available'])
        self.assertTrue(rows[0]['order_items'][1]['campus_is_available'])
        db.table.assert_called_once_with('menu_item_availability');q.eq.assert_called_once_with('campus_id','campus-b')
        q.in_.assert_called_once_with('menu_item_id',['meal-a','meal-b'])
    def test_empty_queue_does_not_request_unbounded_availability(self):
        db=MagicMock();self.assertEqual(_attach_campus_availability(db,[],'campus'),[]);db.table.assert_not_called()
    def test_unknown_campus_does_not_request_other_campuses(self):
        db=MagicMock();orders=[{'order_items':[{'menu_item_id':'meal'}]}]
        self.assertEqual(_attach_campus_availability(db,orders,None),orders);db.table.assert_not_called()


class KitchenStockWriteContractTests(unittest.TestCase):
    A='11111111-1111-4111-8111-111111111111'
    B='22222222-2222-4222-8222-222222222222'
    def call(self,body,role='kitchen',parent_campus=None):
        from flask import Flask,g
        from unittest.mock import patch
        from app.routes import menu
        db=MagicMock();db.table.return_value.upsert.return_value=[{'is_available':False}]
        with Flask(__name__).test_request_context(method='PATCH',json=body),patch.object(menu,'get_user_client',return_value=db),patch.object(menu,'fetch_or_403',return_value=({'id':'meal','campus_id':parent_campus},None)),patch.object(menu,'_notify_sellout'):
            g.user_id='actor';g.user_role=role;g.campus_id=self.A
            response,status=menu.update_item_availability.__wrapped__('44444444-4444-4444-8444-444444444444')
        return response,status,db
    def test_kitchen_uses_own_campus_and_changes_only_availability(self):
        _,status,db=self.call({'campus_id':self.B,'is_available':False})
        self.assertEqual(status,200);saved=db.table.return_value.upsert.call_args.args[0]
        self.assertEqual(saved['campus_id'],self.A);self.assertFalse(saved['is_available'])
        self.assertEqual(set(saved),{'menu_item_id','campus_id','is_available','updated_at'})
    def test_super_admin_targets_explicit_campus(self):
        _,status,db=self.call({'campus_id':self.B,'is_available':False},role='super_admin')
        self.assertEqual(status,200);self.assertEqual(db.table.return_value.upsert.call_args.args[0]['campus_id'],self.B)
    def test_foreign_campus_menu_parent_cannot_be_changed(self):
        _,status,db=self.call({'is_available':False},parent_campus=self.B)
        self.assertEqual(status,404);db.table.return_value.upsert.assert_not_called()
    def test_malformed_json_boolean_and_scope_are_explicit_errors(self):
        for body,role in [([1],'kitchen'),(True,'kitchen'),({'is_available':'false'},'kitchen'),({'campus_id':'invalid','is_available':False},'super_admin')]:
            with self.subTest(body=body):
                response,status,db=self.call(body,role)
                self.assertEqual(status,400);self.assertTrue(response.json['error']);db.table.return_value.upsert.assert_not_called()
