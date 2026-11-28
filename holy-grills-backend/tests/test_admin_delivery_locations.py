"""Delivery location controls and pricing must agree, fail visibly and respect campus ownership."""
import inspect,unittest
from unittest.mock import MagicMock,patch
from flask import Flask,g
from werkzeug.exceptions import Forbidden
from app.routes import delivery
from app.db import SupabaseError
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';ID='33333333-3333-4333-8333-333333333333'
class DeliveryLocationTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.db=MagicMock();self.q=self.db.table.return_value
        for name in ('select','eq','single','order'):getattr(self.q,name).return_value=self.q
        self.q.execute.return_value={'id':ID,'campus_id':A,'lat':7.3,'lon':5.14};self.q.update.return_value=[{'id':ID}];self.q.insert.return_value=[{'id':ID}]
    def call(self,handler,*,body=None,path='/',role='admin',args=(),headers=None):
        with self.app.test_request_context(path,method='POST' if body is not None else 'GET',json=body,headers=headers),patch.object(delivery,'get_user_client',return_value=self.db):
            g.user_id='actor';g.user_role=role;g.campus_id=A
            return inspect.unwrap(handler)(*args)
    def test_no_pin_cannot_bypass_base_fee(self):
        for minimum,expected in ((0,500),(100,500),(800,800)):
            self.assertEqual(delivery.calculate_off_campus_fee({'base_fee':500,'rate_per_km':100,'min_fee':minimum}), (expected,None))
    def test_pin_price_includes_distance_rate_and_minimum(self):
        gate={'lat':7.3,'lon':5.14,'base_fee':500,'rate_per_km':100,'min_fee':700}
        self.assertEqual(delivery.calculate_off_campus_fee(gate,7.3,5.14),(700,0.0))
        price,distance=delivery.calculate_off_campus_fee(gate,7.33,5.14)
        self.assertGreater(price,800);self.assertGreater(distance,3)
    def test_checkout_uses_same_no_pin_base_floor(self):
        from tests.test_checkout_quote import CheckoutQuoteTests,CAMPUS
        h=CheckoutQuoteTests();h.setUp();h.db.rows['gates']=[{'id':ID,'campus_id':CAMPUS,'is_active':'true','name':'Gate','base_fee':500,'min_fee':0,'rate_per_km':100}]
        quote=h.calculate(payload={**h.payload,'delivery_type':'off_campus','delivery_location_id':ID})
        self.assertEqual(quote['delivery_fee'],500)
    def test_gate_create_has_no_fabricated_coordinates(self):
        self.assertEqual(self.call(delivery.admin_create_gate,body={'name':'Gate','base_fee':500,'min_fee':500,'rate_per_km':25})[1],201)
        saved=self.q.insert.call_args.args[0];self.assertNotIn('lat',saved);self.assertNotIn('lon',saved);self.assertEqual(saved['rate_per_km'],25)
    def test_partial_coordinate_update_keeps_other_existing_coordinate(self):
        self.assertEqual(self.call(delivery.admin_update_gate,body={'lat':7.31},args=(ID,))[1],200)
        saved=self.q.update.call_args.args[0];self.assertEqual(saved['lat'],7.31);self.assertEqual(saved['lon'],5.14)
    def test_foreign_global_update_and_hide_are_denied(self):
        for handler in (delivery.admin_update_gate,delivery.admin_update_hostel,delivery.admin_delete_gate,delivery.admin_delete_hostel):
            for scope in (None,B):
                self.q.execute.return_value={'id':ID,'campus_id':scope}
                with self.assertRaises(Forbidden):self.call(handler,args=(ID,),body={'name':'Changed'})
        self.q.update.assert_not_called()
    def test_invalid_ids_and_empty_patches_do_not_write(self):
        for handler in (delivery.admin_update_gate,delivery.admin_update_hostel,delivery.admin_delete_gate,delivery.admin_delete_hostel):
            self.assertEqual(self.call(handler,args=('bad-id',),body={})[1],400)
        self.assertEqual(self.call(delivery.admin_update_gate,args=(ID,),body={})[1],400);self.q.update.assert_not_called()
    def test_own_hostel_can_be_restored_with_existing_patch(self):
        self.assertEqual(self.call(delivery.admin_update_hostel,args=(ID,),body={'is_active':True})[1],200)
        self.assertIs(self.q.update.call_args.args[0]['is_active'],True)
    def test_failed_reads_and_writes_are_not_empty_success(self):
        self.q.execute.side_effect=SupabaseError('private failure',503,{})
        for handler in (delivery.admin_list_gates,delivery.admin_list_hostels):self.assertEqual(self.call(handler)[1],503)
        self.q.execute.side_effect=None;self.q.insert.side_effect=SupabaseError('private failure',503,{})
        response,status=self.call(delivery.admin_create_gate,body={'name':'Gate'})
        self.assertEqual(status,503);self.assertNotIn('private failure',str(response.json))
    def test_duplicate_create_gets_actionable_conflict(self):
        self.q.insert.side_effect=SupabaseError('duplicate private name',409,{'code':'23505'})
        response,status=self.call(delivery.admin_create_gate,body={'name':'Gate'})
        self.assertEqual(status,409);self.assertIn('restore',response.json['error'])
