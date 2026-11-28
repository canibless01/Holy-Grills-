from unittest.mock import MagicMock, patch
from flask import Flask, g
import pytest
from app.routes import delivery_costs as routes
from app.routes import menu
from app.db import SupabaseError, SupabaseClient, UserSupabaseClient

C='11111111-1111-4111-8111-111111111111'
U='22222222-2222-4222-8222-222222222222'
O='33333333-3333-4333-8333-333333333333'
app=Flask(__name__)

@pytest.fixture
def db():
    value=MagicMock(); value.rpc.return_value={'orders':[]}
    with patch.object(routes,'get_db',return_value=value):yield value


def call(fn, body=None, query='', role='admin', campus=C):
    with app.test_request_context('/?'+query,method='POST',json=body):
        g.user_id=U;g.user_role=role;g.campus_id=campus
        return fn.__wrapped__()


def payload(**updates):
    return dict(request_id=U,entry_id=O,version=0,kind='order',order_ids=[O],date='2026-01-01',total_cost='500.01',**updates)


def test_cost_actor_comes_from_session_and_money_stays_exact(db):
    data=payload();data['p_actor']='attacker';data['campus_id']='attacker'
    response=call(routes.save_cost,data)
    assert response.status_code==200
    name,args=db.rpc.call_args.args
    assert name=='hg_delivery_costs' and args['p_actor']==U and args['p_campus']==C
    assert args['p_data']['total_cost']=='500.01' and 'p_actor' not in args['p_data']

@pytest.mark.parametrize('amount',[None,True,'NaN','Infinity','-1','0.001',{},'1000000000000'])
def test_invalid_money_never_reaches_database(db,amount):
    data=payload();data['total_cost']=amount
    _,status=call(routes.save_cost,data)
    assert status==400;db.rpc.assert_not_called()

@pytest.mark.parametrize('change',[{'version':True},{'version':-1},{'order_ids':[O,O]},{'order_ids':[]},{'order_ids':['bad']},{'kind':'tripx'},{'date':'9999-01-01'},{'request_id':'bad'},{'note':[]},{'note':'x'*501}])
def test_invalid_cost_intent_is_rejected(db,change):
    _,status=call(routes.save_cost,{**payload(),**change})
    assert status==400;db.rpc.assert_not_called()

@pytest.mark.parametrize('code,status',[('42501',403),('40001',409),('22023',400)])
def test_cost_scope_and_conflict_responses(db,code,status):
    db.rpc.side_effect=SupabaseError('Cost changed',400,{'code':code})
    _,actual=call(routes.save_cost,payload())
    assert actual==status


def test_campus_admin_cannot_override_scope(db):
    call(routes.list_costs,query='campus_id='+O)
    assert db.rpc.call_args.args[1]['p_campus']==C


def test_super_admin_can_read_all_but_database_authorizes_each_write(db):
    call(routes.list_costs,role='super_admin',campus=None)
    assert db.rpc.call_args.args[1]['p_campus'] is None


def test_cushion_service_write_requires_explicit_campus_authorization():
    raw=SupabaseClient('https://db.invalid','service','anon');scoped=UserSupabaseClient(raw,'customer-token')
    with app.test_request_context():
        g.user_role='admin';g.campus_id=C
        result={};writer,error=menu._cushion_write(scoped,{'cushion_amount':500},result,C,3500)
        assert writer is raw and error is None and result=={'cushion_amount':500}
        for campus in (None,O):
            with pytest.raises(Exception) as exc:menu._cushion_write(scoped,{'cushion_amount':0},{},campus,3500)
            assert exc.value.code==403

@pytest.mark.parametrize('amount',[True,3501,-1,'NaN','Infinity','0.001'])
def test_cushion_cannot_exceed_inclusive_retail_price(amount):
    with app.test_request_context():
        g.user_role='admin';g.campus_id=C
        target={'price':3500};_,error=menu._cushion_write(MagicMock(),{'cushion_amount':amount},target,C,3500)
        assert error[1]==400 and target=={'price':3500}


def test_no_cushion_lookup_or_write_for_public_customer():
    db=MagicMock()
    with app.test_request_context():
        g.user_role='student'
        rows=[{'id':O,'price':3500}];menu._attach_cushions(db,'menu_items',rows)
        db.table.assert_not_called();assert rows==[{'id':O,'price':3500}]
