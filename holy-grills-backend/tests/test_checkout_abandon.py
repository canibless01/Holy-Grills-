import hashlib
from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from app.routes import orders
from app.db import SupabaseError
C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222'
app=Flask(__name__)
@pytest.fixture
def db():
    db=MagicMock();db.rpc.return_value={'state':'closed','order_id':None}
    with patch.object(orders,'get_db',return_value=db):yield db

def call(body,actor=U):
    with app.test_request_context(method='POST',json=body):
        g.user_id=actor;g.campus_id=C
        return orders.abandon_checkout.__wrapped__.__wrapped__()

def test_abandon_uses_verified_actor_and_scoped_key_never_creates_or_initializes_payment(db):
    response,status=call({'idempotency_key':'raw','user_id':'attacker','campus_id':'attacker'})
    assert status==200 and response.json['state']=='closed'
    db.rpc.assert_called_once_with('hg_abandon_checkout',{'p_actor':U,'p_campus':C,'p_key':'v2:'+hashlib.sha256(f'user:{U}:{C}:raw'.encode()).hexdigest(),'p_legacy_key':'raw','p_guest_email':None,'p_guest_phone':None})
    db.table.assert_not_called()

def test_guest_contact_is_canonicalized_exactly_like_checkout(db):
    _,status=call({'idempotency_key':'raw','guest_email':' Example@Example.com ','guest_phone':' 08012345678 '},None)
    assert status==200
    args=db.rpc.call_args.args[1]
    assert args['p_actor'] is None and args['p_guest_email']=='example@example.com' and args['p_guest_phone']=='08012345678'
    assert args['p_key']=='v2:'+hashlib.sha256(f'guest:example@example.com:08012345678:{C}:raw'.encode()).hexdigest()

@pytest.mark.parametrize('body',[None,{},[],{'idempotency_key':{}},{'idempotency_key':'x'*201}])
def test_invalid_intent_never_calls_release(db,body):
    _,status=call(body)
    assert status==400;db.rpc.assert_not_called()

def test_paid_race_returns_existing_order_without_a_second_provider_action(db):
    db.rpc.return_value={'state':'paid','order':{'id':'original','payment_status':'paid'}}
    response,status=call({'idempotency_key':'raw'})
    assert status==200 and response.json['order']['id']=='original'
    assert db.rpc.call_count==1

def test_storage_or_rpc_uncertainty_is_not_reported_as_success(db):
    db.rpc.side_effect=SupabaseError('private diagnostic',500,{'message':'timeout'})
    response,status=call({'idempotency_key':'raw'})
    assert status==503 and 'private' not in response.get_data(as_text=True)

def test_wrong_owner_is_denied(db):
    db.rpc.side_effect=SupabaseError('private diagnostic',403,{'message':'checkout_forbidden'})
    _,status=call({'idempotency_key':'raw'})
    assert status==403
