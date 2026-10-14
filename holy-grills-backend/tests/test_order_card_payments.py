"""A saved order or a callback must never count as proof of payment."""
import copy
import unittest
from unittest.mock import patch, MagicMock
from flask import Flask, g
from app.services import order_payments as service
from app.routes.orders import _order_payment_response

OID='2b808beb-71b2-4c75-96c0-b11af5c9bd88'
CAMPUS='11111111-1111-4111-8111-111111111111'
class Query:
    def __init__(self,db,table):self.db,self.table,self.filters=db,table,[]
    def select(self,*a):return self
    def eq(self,k,v):self.filters.append((k,v));return self
    def single(self):return self
    def execute(self):return next((copy.deepcopy(r) for r in self.db.rows[self.table] if all(r.get(k)==v for k,v in self.filters)),None)
    def insert(self,row):self.db.rows[self.table].append(copy.deepcopy(row));return [copy.deepcopy(row)]
    def update(self,data):
        changed=[]
        for r in self.db.rows[self.table]:
            if all(r.get(k)==v for k,v in self.filters):r.update(copy.deepcopy(data));changed.append(copy.deepcopy(r))
        return changed
class Db:
    def __init__(self,order):self.rows={'orders':[order],'payments':[],'profiles':[{'id':'student','email':'audit@example.com'}]}
    def table(self,t):return Query(self,t)

class CardPaymentTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.app.config.update(PAYSTACK_SECRET_KEY='test-fixture-only',FRONTEND_URL='https://example.com')
        self.order={'id':OID,'user_id':'student','campus_id':CAMPUS,'status':'received','payment_status':'pending','total_amount':2300,'wallet_amount_used':500,'card_amount_used':1800,'claim_token':None}
        self.db=Db(self.order)
    def transaction(self,**overrides):
        r={'status':'success','currency':'NGN','reference':service.reference_for(self.order),'amount':180000,'metadata':{'type':'order_payment','order_id':OID,'user_id':'student','campus_id':CAMPUS}}
        r.update(overrides);return r
    def test_initialize_remainder_and_reuse_provider_reference(self):
        ref=service.reference_for(self.order)
        with self.app.app_context(),patch.object(service,'get_db',return_value=self.db),patch.object(service.payment_service,'initialize_payment',return_value={'authorization_url':'https://checkout.paystack.com/audit','reference':ref}) as init:
            first=service.initialize(self.order);second=service.initialize(self.order)
        self.assertEqual(first,second);self.assertEqual(1,init.call_count)
        self.assertEqual(init.call_args.args[1],1800)
        self.assertEqual(init.call_args.kwargs['metadata']['campus_id'],CAMPUS)
        self.assertEqual(init.call_args.kwargs['callback_url'],f'https://example.com/order-confirmation/{OID}?payment_return=1')
        self.assertEqual(len(self.db.rows['payments']),1);self.assertEqual(self.order['payment_status'],'pending')
    def test_missing_key_is_recoverable_without_payment_write(self):
        self.app.config['PAYSTACK_SECRET_KEY']=''
        with self.app.app_context(),patch.object(service,'get_db',return_value=self.db),self.assertRaises(service.OrderPaymentError) as e:service.initialize(self.order)
        self.assertEqual(e.exception.status,503);self.assertEqual(self.db.rows['payments'],[])
    def test_failed_pending_or_abandoned_provider_result_never_confirms(self):
        for status in ['failed','abandoned','pending','ongoing']:
            with self.subTest(status=status),self.app.app_context(),patch.object(service.payment_service,'verify_payment',return_value=self.transaction(status=status)),patch('app.services.order_service.confirm_order_payment') as confirm:
                self.assertEqual(service.verify(self.order)['payment_status'],'pending');confirm.assert_not_called()
    def test_success_is_verified_before_confirmation(self):
        with self.app.app_context(),patch.object(service.payment_service,'verify_payment',return_value=self.transaction()),patch('app.services.order_service.confirm_order_payment',return_value={**self.order,'payment_status':'paid'}) as confirm:
            self.assertEqual(service.verify(self.order)['payment_status'],'paid');self.assertEqual(confirm.call_count,1)
    def test_mismatched_callback_cannot_confirm(self):
        bad=[{'amount':230000},{'amount':179999},{'amount':'NaN'},{'amount':180000.1},{'currency':'USD'},{'reference':'other'},{'status':'pending'},{'metadata':{}},{'metadata':{'type':'order_payment','order_id':OID,'user_id':'another','campus_id':CAMPUS}},{'metadata':{'type':'order_payment','order_id':OID,'user_id':'student','campus_id':'foreign'}}]
        for changes in bad:
            with self.subTest(changes=changes),self.assertRaises(service.OrderPaymentError):service.validate_provider_payment(self.order,service.reference_for(self.order),self.transaction(**changes))
    def test_owner_and_guest_authorization(self):
        with patch.object(service,'get_db',return_value=self.db):
            self.assertEqual(service.authorized_order(OID,'student')['id'],OID)
            with self.assertRaises(service.OrderPaymentError):service.authorized_order(OID,'foreign','token')
            self.order.update(user_id=None,claim_token='owned-guest-token')
            self.assertEqual(service.authorized_order(OID,None,'owned-guest-token')['id'],OID)
            with self.assertRaises(service.OrderPaymentError):service.authorized_order(OID,'student','bad-token')
    def test_cancelled_order_cannot_initialize_or_verify(self):
        self.order['status']='cancelled'
        with self.app.app_context(),patch.object(service.payment_service,'initialize_payment') as init,patch.object(service.payment_service,'verify_payment') as verify:
            for fn in [service.initialize,service.verify]:
                with self.assertRaises(service.OrderPaymentError):fn(self.order)
            init.assert_not_called();verify.assert_not_called()
    def test_bad_redirect_is_rejected(self):
        with self.app.app_context(),patch.object(service,'get_db',return_value=self.db),patch.object(service.payment_service,'initialize_payment',return_value={'authorization_url':'https://evil.example/checkout','reference':service.reference_for(self.order)}),self.assertRaises(service.OrderPaymentError):service.initialize(self.order)
        for url in ['javascript:alert(1)','https://paystack.com.evil.example/','http://checkout.paystack.com/','https://user:pass@paystack.com/']:
            self.assertFalse(service.allowed_payment_url(url))
    def test_paid_recovery_cannot_initialize_another_charge(self):
        self.order['payment_status']='paid'
        with self.app.app_context(),patch.object(service.payment_service,'initialize_payment') as init:
            self.assertEqual(service.initialize(self.order),{'payment_status':'paid'});init.assert_not_called()
    def test_foreign_order_route_does_not_touch_provider(self):
        with self.app.test_request_context('/payment',method='POST',json={}),patch.object(service,'get_db',return_value=self.db),patch.object(service.payment_service,'initialize_payment') as init:
            g.user_id='foreign';_,status=_order_payment_response(OID)
            self.assertEqual(status,404);init.assert_not_called()
    def test_confirmation_rpc_uses_remainder_and_replay_reads_paid_state(self):
        from app.services import order_service
        db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect=[self.order,{**self.order,'payment_status':'paid'}];db.rpc.return_value=None
        with self.app.app_context(),patch.object(order_service,'get_db',return_value=db),patch.object(order_service,'_on_order_paid'):
            result=order_service.confirm_order_payment(OID,service.reference_for(self.order),self.transaction())
        self.assertEqual(result['payment_status'],'paid');self.assertEqual(db.rpc.call_args.args[1]['p_amount'],1800)
