"""Transfers never contact a payment provider or award top-up HP."""
from unittest.mock import patch, MagicMock
from uuid import uuid4
import pytest
from flask import Flask, g
from app.services import wallet_transfers as service
from app.routes.wallet_transfers import transfers, receipt
from app.db import SupabaseError

@pytest.fixture
def body():
    return {'request_id': str(uuid4()), 'recipient_id': str(uuid4()), 'recipient_code': 'Friend_123', 'amount': '250.25', 'note': ' Dinner '}

@pytest.mark.parametrize('amount', [True, None, 'NaN', 'Infinity', '-Infinity', 0, -1, '0.001', '250.251', '1000000000.01', {}, []])
def test_invalid_amount_never_reaches_money_rpc(body, amount):
    body['amount'] = amount
    with patch.object(service, 'rpc') as rpc, pytest.raises(service.TransferError): service.send(str(uuid4()), body)
    rpc.assert_not_called()

def test_intent_uses_integer_kobo_and_canonical_code(body):
    transfer_id, data = service.intent(body)
    assert transfer_id == body['request_id']
    assert data == {'recipient_id': body['recipient_id'], 'recipient_code': 'FRIEND_123', 'amount_kobo': 25025, 'note': 'Dinner'}

@pytest.mark.parametrize('change', [{'request_id': 'bad'}, {'recipient_id': 'bad'}, {'recipient_code':'friend@example.com'}, {'note':'x'*201}, {'note':None}])
def test_invalid_identity_or_note_is_rejected(body, change):
    with pytest.raises(service.TransferError): service.intent({**body, **change})

def test_committed_transfer_survives_broker_failure(body):
    value={'id':body['request_id'], 'status':'completed'}
    with patch.object(service, 'rpc', return_value=value) as rpc, patch.object(service, 'enqueue_receipt', side_effect=RuntimeError('broker unavailable')):
        assert service.send('server-session-owner', body) == value
    assert rpc.call_args.args[1] == 'server-session-owner'
    assert rpc.call_args.args[3]['amount_kobo'] == 25025

def test_known_db_error_is_typed_but_unknown_error_is_not_echoed():
    db=MagicMock();db.rpc.side_effect=SupabaseError('oops', details={'message':'insufficient_wallet_balance'})
    with patch.object(service,'get_db',return_value=db), pytest.raises(service.TransferError) as error: service.rpc('send')
    assert error.value.code == 'insufficient_wallet_balance'
    db.rpc.side_effect=SupabaseError('private diagnostic')
    app=Flask(__name__)
    with app.test_request_context(method='POST',json={}), patch.object(service,'send',side_effect=db.rpc.side_effect):
        g.user_id='session-owner'; response,status=transfers.__wrapped__.__wrapped__()
        assert status==503 and response.json['code']=='transfer_uncertain'
        assert 'private' not in str(response.json)

def test_owner_comes_only_from_session(body):
    app=Flask(__name__)
    with app.test_request_context(method='POST',json={**body,'sender_id':'attacker'}), patch.object(service,'send',return_value={'id':body['request_id']}) as send:
        g.user_id='real-owner';transfers.__wrapped__.__wrapped__()
    assert send.call_args.args[0]=='real-owner'

def test_receipt_requires_owned_lookup(body):
    app=Flask(__name__)
    with app.test_request_context(), patch.object(service,'rpc',side_effect=service.TransferError('transfer_not_found')) as rpc:
        g.user_id='outsider';response,status=receipt.__wrapped__.__wrapped__(body['request_id'])
    assert status==404 and response.json['code']=='transfer_not_found'
    assert rpc.call_args.args==('get','outsider',body['request_id'])

def test_notification_failure_does_not_mark_outbox_done(body):
    value={'id':body['request_id'],'amount':250.25,'sender_id':'a','recipient_id':'b','sender_name':'Alice','recipient_name':'Bob'}
    with patch('app.services.notification_service.send_notification',side_effect=[None,RuntimeError('interrupted')]) as send, patch.object(service,'rpc') as rpc:
        with pytest.raises(RuntimeError):service.dispatch_receipt(value)
    rpc.assert_not_called()
    assert [call.kwargs['reference_id'] for call in send.call_args_list] == [body['request_id']]*2
    assert all(call.kwargs['strict'] for call in send.call_args_list)

def test_notification_recovery_skips_deleted_party_and_marks_only_after_success(body):
    value={'id':body['request_id'],'amount':250.25,'sender_id':'a','recipient_id':None,'sender_name':'Alice','recipient_name':'Bob'}
    with patch('app.services.notification_service.send_notification') as send, patch.object(service,'rpc') as rpc:
        service.dispatch_receipt(value)
    assert send.call_count==1 and send.call_args.kwargs['action_url']==f"/wallet?transfer={body['request_id']}"
    rpc.assert_called_once_with('notified',transfer_id=body['request_id'])

def test_recovery_is_bounded_and_receipt_only(body):
    row={'id':body['request_id'],'amount_kobo':25025}
    with patch.object(service,'rpc',return_value=[row]) as rpc, patch.object(service,'dispatch_receipt') as dispatch:
        assert service.recover(limit=200)=={'processed':1,'pending':0}
    rpc.assert_called_once_with('due',data={'limit':20})
    assert dispatch.call_args.args[0]['amount']==250.25
