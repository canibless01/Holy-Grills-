import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.services.order_contact import normalize_order_phone, resolve_order_phone, order_call_phone
from app.routes import riders

class OrderContactTests(unittest.TestCase):
    def test_nigerian_mobile_normalization_and_malformed_rejection(self):
        for phone in ('08012345678', '+2348012345678', '2348012345678', '(080) 1234-5678'):
            self.assertEqual(normalize_order_phone(phone), '+2348012345678')
        for phone in ('123', '+23470123456789', '02012345678', '08012345678;alert()', None, {}, True):
            with self.subTest(phone=phone), self.assertRaises(ValueError):normalize_order_phone(phone)

    def test_account_override_never_reads_or_updates_profile(self):
        db=MagicMock()
        self.assertEqual(resolve_order_phone(db,'account',{'contact_phone':'09012345678'}),'+2349012345678')
        db.table.assert_not_called()

    def test_legacy_profile_fallback_and_guest_override(self):
        db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'phone':'08012345678'}
        self.assertEqual(resolve_order_phone(db,'account',{}),'+2348012345678')
        self.assertEqual(resolve_order_phone(db,None,{'guest_phone':'08012345678','contact_phone':'09012345678'}),'+2349012345678')

    def test_quote_does_not_require_unfinished_confirmation(self):
        db=MagicMock();self.assertIsNone(resolve_order_phone(db,None,{'contact_phone':''},quote_only=True));db.table.assert_not_called()
        with self.assertRaises(ValueError):resolve_order_phone(db,None,{'contact_phone':''})

    def test_snapshot_precedes_profile_after_account_phone_changes(self):
        order={'delivery_address_snapshot':{'contact_phone':'+2349012345678'},'guest_phone':'08012345678'}
        self.assertEqual(order_call_phone(order,'07012345678'),'+2349012345678')
        self.assertEqual(order_call_phone({'guest_phone':'08012345678'},None),'08012345678')

    def test_secure_call_uses_authorized_order_snapshot_without_profile_dependency(self):
        app=Flask(__name__);db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'user_id':'account','status':'assigned','delivery_address_snapshot':{'contact_phone':'+2349012345678'}}
        with app.test_request_context(),patch.object(riders,'get_user_client',return_value=db),patch.object(riders,'get_db',side_effect=RuntimeError('optional profile outage')):
            g.user_id='rider';g.user_role='rider';g.campus_id='campus'
            response,status=riders.get_customer_call_link.__wrapped__('11111111-1111-4111-8111-111111111111')
        self.assertEqual(status,200);self.assertEqual(response.json,{'call_link':'tel:+2349012345678'})

class OrderContactAdmissionTests(unittest.TestCase):
    def setUp(self):
        from tests.test_checkout_quote import CheckoutQuoteTests
        self.harness=CheckoutQuoteTests();self.harness.setUp()

    def guards(self):
        from contextlib import ExitStack
        from app.services import order_service as service
        stack=ExitStack();stack.enter_context(patch.object(service,'_order_for_intent',return_value=None));stack.enter_context(patch.object(service,'resolve_ordering_window',return_value={}));stack.enter_context(patch.object(service,'_check_kitchen_capacity'));return stack

    def test_real_calculator_snapshots_override_and_canonical_saved_address(self):
        from tests.test_checkout_quote import CAMPUS, HOSTEL
        h=self.harness;h.db.rows['user_addresses']=[{'id':'saved','user_id':'student','campus_id':CAMPUS,'delivery_type':'on_campus','delivery_location_id':HOSTEL,'line1':'Saved door 12','landmark':'Blue stair'}]
        payload={**h.payload,'delivery_address_id':'saved','delivery_address':'Forged text','contact_phone':'09012345678'}
        with self.guards(),patch.object(h.db,'rpc',side_effect=RuntimeError('captured before write')) as rpc:
            with self.assertRaisesRegex(ValueError,'captured before write'):h.calculate(quote_only=False,payload=payload)
        snapshot=rpc.call_args.args[1]['p_delivery_address_snapshot'];self.assertEqual(snapshot['contact_phone'],'+2349012345678');self.assertEqual(snapshot['line1'],'Saved door 12, Blue stair');self.assertEqual(snapshot['landmark'],'Blue stair');self.assertEqual(h.db.rows['profiles'][0]['phone'],'08012345678')

    def test_final_offcampus_admission_needs_readable_text_before_rpc(self):
        from tests.test_checkout_quote import CAMPUS
        h=self.harness;gate='55555555-5555-4555-8555-555555555555';h.db.rows['gates']=[{'id':gate,'name':'Gate','campus_id':CAMPUS,'is_active':'true','base_fee':250,'rate_per_km':0,'min_fee':0}]
        payload={**h.payload,'delivery_type':'off_campus','delivery_location_id':gate,'contact_phone':'09012345678','delivery_address':{'line1':'','landmark':'A landmark alone'}}
        with self.guards(),patch.object(h.db,'rpc') as rpc:
            with self.assertRaisesRegex(ValueError,'street, junction'):h.calculate(quote_only=False,payload=payload)
        rpc.assert_not_called()
