"""Centre/radius scope, input policy and checkout distance enforcement."""
import inspect,unittest
from unittest.mock import MagicMock,patch
from flask import Flask,g
from app.routes import kitchen,admin,delivery
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222'
class DeliveryAreaContractTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.db=MagicMock();self.q=self.db.table.return_value
        for name in ('select','eq','single','upsert'):getattr(self.q,name).return_value=self.q
        self.q.execute.return_value=[]
    def settings(self,body,role='super_admin',campus=B):
        path='/settings'+(('?campus_id='+campus) if campus else '')
        with self.app.test_request_context(path,method='PATCH',json=body),patch.object(kitchen,'get_user_client',return_value=self.db):
            g.user_id='actor';g.user_role=role;g.campus_id=A
            return inspect.unwrap(kitchen.update_kitchen_settings)()
    def test_settings_rejects_non_object_json(self):
        for body in ([1], 'wrong', None):
            self.assertEqual(self.settings(body)[1],400)
        self.q.upsert.assert_not_called()
    def test_super_requires_explicit_valid_settings_campus(self):
        self.assertEqual(self.settings({'settings':{'max_delivery_radius_km':10}},campus=None)[1],400)
        self.assertEqual(self.settings({'settings':{'max_delivery_radius_km':10}},campus='invalid')[1],400)
        self.q.upsert.assert_not_called()
    def test_radius_save_targets_query_campus_not_super_student_campus(self):
        self.settings({'settings':{'max_delivery_radius_km':'2.5'}})
        saved=self.q.upsert.call_args.args[0];self.assertEqual(saved['campus_id'],B);self.assertEqual(saved['value'],'2.5')
    def test_campus_admin_cannot_redirect_radius_save(self):
        self.settings({'settings':{'max_delivery_radius_km':10}},role='admin')
        self.assertEqual(self.q.upsert.call_args.args[0]['campus_id'],A)
    def test_invalid_radius_rejects_whole_request_before_any_write(self):
        for invalid in (0,-1,True,None,'nan','Infinity','-Infinity','not a number',[]):
            with self.subTest(invalid=invalid):self.assertEqual(self.settings({'settings':{'daily_order_capacity':'20','max_delivery_radius_km':invalid}})[1],400)
        self.q.upsert.assert_not_called()
    def centre(self,body,*,campus=B,role='super_admin'):
        with self.app.test_request_context(method='PATCH',json=body),patch.object(admin,'get_db',return_value=self.db),patch.object(admin,'_campus_radius_km',return_value=10),patch.object(admin,'_audit'):
            g.user_id='actor';g.user_role=role;g.campus_id=A
            self.q.execute.return_value={'id':campus,'name':'Controlled campus','campus_id':A,'lat':7.3,'lon':5.14}
            self.q.update.return_value=[{'id':campus,'name':'Controlled campus'}]
            return inspect.unwrap(admin.set_campus_location)(campus)
    def test_centre_save_and_explicit_clear_preserve_target(self):
        self.assertEqual(self.centre({'coordinates':'7.31, 5.15'})[1],200)
        self.assertEqual(self.q.update.call_args.args[0]['lat'],7.31)
        self.assertEqual(self.centre({'lat':None,'lon':None})[1],200);self.assertIsNone(self.q.update.call_args.args[0]['lon'])
    def test_campus_admin_cannot_set_foreign_centre(self):
        self.assertEqual(self.centre({'coordinates':'7.31, 5.15'},role='admin')[1],403);self.q.update.assert_not_called()
    def test_only_outside_country_response_offers_explicit_force(self):
        response,status=self.centre({'coordinates':'40, -74'})
        self.assertEqual(status,400);self.assertEqual(response.json['code'],'CAMPUS_LOCATION_OUTSIDE_NIGERIA');self.q.update.assert_not_called()
        self.assertEqual(self.centre({'coordinates':'40, -74','force':True})[1],200)
    def test_checkout_uses_saved_radius_and_centre(self):
        campus_q=MagicMock();settings_q=MagicMock()
        for q in (campus_q,settings_q):
            for name in ('select','eq','single'):getattr(q,name).return_value=q
        campus_q.execute.return_value={'lat':7.3,'lon':5.14};settings_q.execute.return_value={'value':'1'}
        public_db=MagicMock();public_db.table.return_value=campus_q;service_db=MagicMock();service_db.table.return_value=settings_q
        with patch.object(delivery,'get_db',return_value=service_db):
            self.assertTrue(delivery.is_within_delivery_area(public_db,7.301,5.14,A));self.assertFalse(delivery.is_within_delivery_area(public_db,7.32,5.14,A))
        self.assertIn(unittest.mock.call('campus_id',A),settings_q.eq.call_args_list)
