"""Payment boundaries; real financial conservation is exercised by SQL rollback tests."""
from uuid import uuid4
from unittest.mock import patch, MagicMock
import pytest
from flask import Flask, g
from app.services import delivery_pass as service
from app.routes.delivery_pass import refund, renewal

@pytest.fixture
def app():
    value=Flask(__name__)
    value.config.update(PAYSTACK_SECRET_KEY='controlled-test',FRONTEND_URL='https://holygrills.online')
    with value.app_context(): yield value

@pytest.fixture
def purchase():
    return dict(request_id=str(uuid4()),method='card',price=100,auto_renew=False)

@pytest.mark.parametrize('price',[True,None,'NaN','Infinity',99,-1,1000001,'100.001'])
def test_invalid_prices_fail_before_money_rpc(app,purchase,price):
    with patch.object(service,'rpc') as rpc, pytest.raises(service.PassError): service.buy(str(uuid4()),{**purchase,'price':price})
    rpc.assert_not_called()

@pytest.mark.parametrize('changes',[{'auto_renew':'true'},{'auto_renew':True},{'request_id':'bad'},{'user_id':'other'},{'method':'bank'}])
def test_identity_and_consent_fail_before_provider(app,purchase,changes):
    with patch.object(service,'_provider') as provider,pytest.raises(service.PassError): service.buy(str(uuid4()),{**purchase,**changes})
    provider.assert_not_called()

def test_pending_initialization_failure_retains_original_and_never_retries_post(app,purchase):
    receipt={'id':purchase['request_id'],'reference':'HG-PASS-'+purchase['request_id'],'amount_kobo':10000,'status':'pending','created':True,'authorization_email':'controlled@example.invalid'}
    with patch.object(service,'rpc',return_value=receipt) as rpc,patch.object(service,'_provider',side_effect=TimeoutError) as provider:
        result=service.buy(str(uuid4()),purchase)
    assert result['setup_pending'] and result['receipt']['id']==receipt['id']
    assert provider.call_count==1 and rpc.call_count==1
    assert 'authorization_email' not in result['receipt']

def test_replayed_card_intent_does_not_initialize_again(app,purchase):
    with patch.object(service,'rpc',return_value={'id':purchase['request_id'],'status':'pending','created':False}),patch.object(service,'_provider') as provider:
        service.buy(str(uuid4()),purchase)
    provider.assert_not_called()

def test_verified_callback_uses_server_reference_owner_and_amount(app,purchase):
    reference='HG-PASS-'+purchase['request_id']
    charge={'reference':reference,'status':'success','amount':10000,'currency':'NGN'}
    with patch.object(service,'rpc',return_value={'id':purchase['request_id'],'status':'paid'}) as rpc:
        service.confirm(charge,actor='owner',receipt_id=purchase['request_id'])
    assert rpc.call_args.args[:3]==('confirm','owner',purchase['request_id'])
    assert rpc.call_args.args[3]['amount_kobo']==10000
    with pytest.raises(service.PassError):service.confirm(charge,actor='owner',receipt_id=str(uuid4()))

@pytest.mark.parametrize('changes',[{'currency':'USD'},{'amount':True},{'fees':True},{'requested_amount':-1},{'reference':'HG-WALLET-other'}])
def test_unbound_provider_result_never_reaches_financial_rpc(app,purchase,changes):
    charge={'reference':'HG-PASS-'+purchase['request_id'],'status':'success','amount':10000,'currency':'NGN',**changes}
    with patch.object(service,'rpc') as rpc,pytest.raises(service.PassError): service.confirm(charge)
    rpc.assert_not_called()

def test_foreign_receipt_denied_before_provider_read(app,purchase):
    with patch.object(service,'rpc',side_effect=service.PassError('denied',403)),patch.object(service,'_provider') as provider,pytest.raises(service.PassError): service.verify('wrong-owner',purchase['request_id'])
    provider.assert_not_called()

def test_pass_quote_preserves_other_rewards_and_fails_closed(app):
    from app.services.delivery_benefits import quote_delivery_benefit
    db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':'u','is_active':True,'campus_id':'c'}
    db.rpc.return_value={'id':'pass','paid_until':'2026-12-25T12:00:00Z'}
    with patch('app.services.delivery_benefits.resolve_perk') as perks:
        result=quote_delivery_benefit('u','c',500,False,db=db,choice='none')
    assert result['source']=='delivery_pass' and result['discount']==500 and result['choices']==[]
    perks.assert_not_called()
    db.rpc.return_value=None
    with pytest.raises(service.PassError):quote_delivery_benefit('u','c',500,False,db=db)

def test_refund_requires_reason_and_ack_before_money_mutation(app,purchase):
    for body in ({},{'reason':'Reason'},{'reason':' ','acknowledge':True}):
        with app.test_request_context(method='POST',json=body),patch.object(service,'rpc') as rpc:
            g.user_id='admin';response,code=refund.__wrapped__(purchase['request_id'])
            assert code==400
        rpc.assert_not_called()

def test_disable_wallet_renewal_needs_no_new_consent_or_price(app):
    with app.test_request_context(method='POST',json={'enabled':False}),patch.object(service,'rpc',return_value={'auto_renew':False}) as rpc:
        g.user_id='owner';response,code=renewal.__wrapped__()
        assert code==200 and not response.json['membership']['auto_renew']
    assert rpc.call_args.kwargs['data']['enabled'] is False

def test_pass_webhook_does_not_fall_through_to_wallet_funding(app,purchase):
    from app.routes.webhooks import _handle_charge_success
    charge={'reference':'HG-PASS-'+purchase['request_id'],'status':'success','amount':10000,'currency':'NGN'}
    with patch.object(service,'confirm',return_value={'campus_id':'c'}) as confirm,patch('app.routes.webhooks.get_db') as db:
        assert _handle_charge_success(charge)=='c'
    confirm.assert_called_once_with(charge);db.assert_not_called()
