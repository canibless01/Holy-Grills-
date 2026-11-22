"""Pickup must keep admission, money, role and reward invariants of delivery orders."""
import inspect
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.services import store_pickup as pickup, order_service as orders
from app.routes import delivery
from app.messages import MSG
from tests import test_checkout_quote as quote_fixture
CAMPUS = quote_fixture.CAMPUS

LOCATION = {'name': 'Campus store', 'address': '12 Campus road', 'instructions': 'Bring your order number'}

class StorePickupTests(unittest.TestCase):
    def test_config_validation_and_normalization(self):
        self.assertEqual(pickup.normalize_location({**LOCATION, 'name': ' Campus store '}), LOCATION)
        for value in (None, {}, {'name':'Store'}, {**LOCATION,'extra':True}, {**LOCATION,'address':True}, {**LOCATION,'name':' '*10}, {**LOCATION,'instructions':'a'*501}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'pickup-point'):
                pickup.normalize_location(value)

    def test_release_off_or_missing_campus_never_reads_location(self):
        with patch.object(pickup,'is_feature_enabled',return_value=False), patch.object(pickup,'location_row') as read:
            self.assertEqual(pickup.pickup_option(CAMPUS), {'enabled':False})
            self.assertEqual(pickup.pickup_option(None), {'enabled':False})
        read.assert_not_called()

    def test_campus_location_is_required_and_never_invented(self):
        with patch.object(pickup,'is_feature_enabled',return_value=True), patch.object(pickup,'location_row',return_value=None):
            with self.assertRaisesRegex(ValueError,'not available'):pickup.require_pickup(CAMPUS)
        with patch.object(pickup,'is_feature_enabled',return_value=True), patch.object(pickup,'location_row',return_value={'value':LOCATION}):
            self.assertEqual(pickup.require_pickup(CAMPUS), {'enabled':True, **LOCATION,'fee':0})

    def test_read_failure_is_not_silently_an_enabled_or_free_delivery(self):
        with patch.object(pickup,'is_feature_enabled',return_value=True), patch.object(pickup,'location_row',side_effect=RuntimeError('read failed')):
            with self.assertRaises(RuntimeError):pickup.require_pickup(CAMPUS)

    def test_fee_preview_requires_authoritative_capability(self):
        app=Flask(__name__)
        with app.test_request_context(json={'delivery_type':'store_pickup','delivery_fee':-100,'campus_id':'foreign'}), patch.object(delivery,'get_user_client'), patch('app.routes.events._get_campus_id',return_value=CAMPUS), patch.object(pickup,'require_pickup',return_value={'enabled':True,**LOCATION}) as check:
            response,code=inspect.unwrap(delivery.calculate_fee)()
            self.assertEqual((code,response.json['delivery_fee']),(200,0));check.assert_called_once_with(CAMPUS)

    def test_quote_preserves_food_pricing_and_unused_delivery_credit(self):
        harness=quote_fixture.CheckoutQuoteTests();harness.setUp();harness.db.rows['profiles'][0]['next_order_free_delivery_cap']=100
        with patch.object(pickup,'require_pickup',return_value={'enabled':True,**LOCATION,'fee':0}):
            quote=harness.calculate(payload={**harness.payload,'delivery_type':'store_pickup','delivery_location_id':'foreign','delivery_location_lat':'bad','delivery_fee':9999})
            self.assertEqual((quote['delivery_fee'],quote['subtotal'],quote['total_amount']),(0,2050,1845))
            self.assertEqual(quote['delivery_benefit']['source'],'none')
            self.assertEqual(harness.db.rows['profiles'][0]['next_order_free_delivery_cap'],100)

    def test_disabled_pickup_cannot_quote_or_debit(self):
        harness=quote_fixture.CheckoutQuoteTests();harness.setUp()
        with patch.object(pickup,'require_pickup',side_effect=ValueError(MSG.STORE_PICKUP_UNAVAILABLE)):
            with self.assertRaisesRegex(ValueError,'not available'):harness.calculate(payload={**harness.payload,'delivery_type':'store_pickup'})

    def test_retry_committed_pickup_ignores_new_admission_flag(self):
        harness=quote_fixture.CheckoutQuoteTests();harness.setUp();existing={'id':'pickup','payment_status':'paid','delivery_type':'store_pickup'}
        with patch.object(orders,'_order_for_intent',return_value=existing), patch.object(pickup,'require_pickup') as admission:
            result=harness.calculate(quote_only=False,payload={**harness.payload,'delivery_type':'store_pickup','idempotency_key':'same-intent'})
        self.assertEqual(result['id'],'pickup');admission.assert_not_called()

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.db=MagicMock()
        self.order={'id':'pickup','status':'ready','payment_status':'paid','user_id':'student','campus_id':CAMPUS,'delivery_type':'store_pickup'}
        self.query=self.db.table.return_value
        for name in ('select','eq','single','limit'):getattr(self.query,name).return_value=self.query
        self.query.execute.return_value=self.order
    def call(self,role='kitchen',status='delivered',campus=CAMPUS):
        with self.app.test_request_context(),patch.object(orders,'get_user_client',return_value=self.db), patch.object(orders,'_effective_rider_id',return_value=None):
            g.user_id='staff';g.user_role=role;g.campus_id=campus
            return orders.update_order_status('pickup',status,changed_by='staff')
    def test_unpaid_wrong_campus_rider_student_and_preparing_collection_denied(self):
        for role,campus,state,payment in [('kitchen','other','ready','paid'),('student',CAMPUS,'ready','paid'),('rider',CAMPUS,'ready','paid'),('kitchen',CAMPUS,'ready','pending'),('kitchen',CAMPUS,'preparing','paid')]:
            self.order.update(status=state,payment_status=payment)
            with self.subTest(role=role,campus=campus,state=state,payment=payment),self.assertRaises((orders.OrderForbiddenError,orders.OrderConflictError)):
                self.call(role,campus=campus)
        self.query.update.assert_not_called()
    def test_collection_retry_uses_existing_reward_recovery_without_state_write(self):
        self.order['status']='delivered'
        with patch.object(orders,'_handle_delivery_rewards') as hp,patch('app.services.ambassador_service.attribute_delivered_order') as ambassador:
            result=self.call()
        self.assertTrue(result['unchanged']);hp.assert_called_once_with(self.order);ambassador.assert_called_once_with('pickup');self.query.update.assert_not_called()
    def test_walk_skips_only_rider_states_not_preparation(self):
        self.order['status']='received'
        with self.app.test_request_context(),patch.object(orders,'get_user_client',return_value=self.db),patch.object(orders,'update_order_status',return_value={'status':'delivered'}) as transition:
            g.user_id='staff';g.user_role='admin';g.campus_id=CAMPUS
            result=orders.walk_order_to_status('pickup','delivered',changed_by='staff')
        self.assertEqual(result['steps'],['preparing','ready','delivered']);self.assertEqual(transition.call_count,3)
