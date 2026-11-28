from unittest.mock import MagicMock, patch
from flask import Flask, g
import pytest
from app.routes import store_stock
from app.db import SupabaseError

C = '11111111-1111-4111-8111-111111111111'
S = '22222222-2222-4222-8222-222222222222'
I = '33333333-3333-4333-8333-333333333333'


def call(body, role='admin'):
    app = Flask(__name__)
    db = MagicMock()
    db.rpc.return_value = {'saved': True}
    with app.test_request_context(method='POST', json=body), patch.object(store_stock, 'get_db', return_value=db), patch.object(store_stock, 'resolve_scoped_campus_id', return_value=C):
        g.user_id=I; g.user_role=role; g.campus_id=C
        result=store_stock.inventory.__wrapped__.__wrapped__()
    return result, db


@pytest.mark.parametrize('change', [{'quantity':True}, {'quantity':'NaN'}, {'quantity':-2}, {'notes':''}, {'request_id':'bad'}, {'item_id':None}, {'actor_id':S}])
def test_invalid_store_stock_movements_never_call_database(change):
    result, db=call({'action':'usage','store_id':S,'item_id':I,'quantity':1,'notes':'Served','request_id':I,**change})
    assert result[1]==400
    db.rpc.assert_not_called()


def test_campus_and_actor_are_server_bound_and_decimal_preserved():
    result, db=call({'campus_id':S,'action':'usage','store_id':S,'item_id':I,'quantity':'0.125','notes':'  Served  ','request_id':I})
    assert result[1]==200
    params=db.rpc.call_args.args[1]
    assert params['p_actor']==I and params['p_campus']==C
    assert params['p_data']['quantity']=='0.125' and params['p_data']['notes']=='Served'


@pytest.mark.parametrize('value',[None,'false',0,[],{}])
def test_classification_requires_a_real_boolean(value):
    result, db=call({'action':'classify','item_id':I,'distributable':value})
    assert result[1]==400
    db.rpc.assert_not_called()


def test_changed_intent_conflict_is_explained_without_another_write():
    app=Flask(__name__);db=MagicMock();db.rpc.side_effect=SupabaseError('store_stock_conflict',400,{})
    with app.test_request_context(method='POST',json={'action':'usage','store_id':S,'item_id':I,'quantity':1,'notes':'Served','request_id':I}),patch.object(store_stock,'get_db',return_value=db),patch.object(store_stock,'resolve_scoped_campus_id',return_value=C):
        g.user_id=I
        response,status=store_stock.inventory.__wrapped__.__wrapped__()
    assert status==409 and 'store_stock_conflict' not in response.json['error']
    assert db.rpc.call_count==1
