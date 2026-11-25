"""The pass uses the established Paystack transport, with isolated owned receipts."""
from unittest.mock import patch
from uuid import uuid4
from flask import Flask
from app.services import auto_funding, delivery_pass


def test_pass_reuses_the_existing_provider_client():
    assert delivery_pass._provider is auto_funding._provider


def test_pass_initialization_matches_shared_amount_and_callback_contract():
    app=Flask(__name__)
    app.config.update(PAYSTACK_SECRET_KEY='controlled-test',FRONTEND_URL='https://holygrills.online')
    identity=str(uuid4());reference='HG-PASS-'+identity
    receipt={'id':identity,'created':True,'status':'pending','reference':reference,'amount_kobo':100000,'authorization_email':'fixture@example.invalid'}
    saved={**receipt,'checkout_url':'https://checkout.paystack.com/controlled'}
    with app.app_context(),patch.object(delivery_pass,'rpc',side_effect=[receipt,saved]),patch.object(delivery_pass,'_provider',return_value={'reference':reference,'authorization_url':saved['checkout_url']}) as provider:
        result=delivery_pass.buy('owner',{'request_id':identity,'price':1000,'method':'card','auto_renew':False})
    method,path,payload=provider.call_args.args
    assert method=='POST' and path=='/transaction/initialize'
    assert payload['amount']==100000 and payload['currency']=='NGN'
    assert payload['reference']==reference
    assert payload['metadata']['expected_amount_kobo']==100000
    assert payload['callback_url']=='https://holygrills.online/wallet?delivery_pass='+identity
    assert result['receipt']['status']=='pending'
    assert 'authorization_email' not in result['receipt']


def test_pass_verification_reads_original_reference_before_grant():
    app=Flask(__name__);app.config['PAYSTACK_SECRET_KEY']='controlled-test'
    identity=str(uuid4());reference='HG-PASS-'+identity
    receipt={'id':identity,'method':'card','status':'pending','reference':reference}
    charge={'reference':reference,'status':'success','amount':100000,'currency':'NGN'}
    with app.app_context(),patch.object(delivery_pass,'rpc',return_value=receipt) as rpc,patch.object(delivery_pass,'_provider',return_value=charge) as provider,patch.object(delivery_pass,'confirm',return_value={'id':identity,'status':'paid'}) as confirm:
        result=delivery_pass.verify('owner',identity)
    rpc.assert_called_once_with('receipt','owner',identity)
    provider.assert_called_once_with('GET','/transaction/verify/'+reference)
    confirm.assert_called_once_with(charge,actor='owner',receipt_id=identity)
    assert result['status']=='paid'
