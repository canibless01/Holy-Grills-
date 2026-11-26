from unittest.mock import MagicMock,patch
from flask import Flask,g
from app.routes import auth

USER='11111111-1111-4111-8111-111111111111'
def call(body):
    db=MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value=None
    with Flask(__name__).test_request_context('/auth/device-token',method='POST',json=body), \
         patch.object(auth,'get_db',return_value=db),patch.object(auth,'get_user_client',return_value=db):
        g.user_id=USER
        response,status=auth.register_device_token.__wrapped__()
        return response.json,status,db

def test_old_player_id_payload_does_not_register_any_device():
    response,status,db=call({'player_id':'controlled-subscription','platform':'web'})
    assert status==400
    db.table.return_value.insert.assert_not_called()

def test_token_contract_stores_only_verified_owner():
    response,status,db=call({'token':'controlled-subscription','platform':'web','device_model':'Controlled Chrome','user_id':'spoofed'})
    assert status==201
    record=db.table.return_value.insert.call_args.args[0]
    assert record['user_id']==USER and record['token']=='controlled-subscription' and record['platform']=='web'

def test_overlong_device_model_is_rejected_before_write():
    _,status,db=call({'token':'controlled-subscription','platform':'web','device_model':'x'*101})
    assert status==400
    db.table.return_value.insert.assert_not_called()


def revoke(body):
    db=MagicMock()
    with Flask(__name__).test_request_context('/auth/device-token',method='DELETE',json=body),patch.object(auth,'get_user_client',return_value=db):
        g.user_id=USER
        response,status=auth.unregister_device_token.__wrapped__()
    return response.json,status,db


def test_revocation_is_owned_scoped_and_idempotent():
    for _ in range(2):
        response,status,db=revoke({'token':'  current-device  '})
        assert status==200
        assert db.table.call_args.args==('device_tokens',)
        assert db.table.return_value.eq.call_args.args==('user_id',USER)
        assert db.table.return_value.eq.return_value.eq.call_args.args==('token','current-device')
        db.table.return_value.eq.return_value.eq.return_value.delete.assert_called_once_with()


def test_revocation_rejects_forged_owner_or_invalid_tokens_before_write():
    for body in ({},{'token':True},{'token':' '},{'token':'x'*513},{'token':'device','user_id':'other'}):
        _,status,db=revoke(body)
        assert status==400
        db.table.assert_not_called()
