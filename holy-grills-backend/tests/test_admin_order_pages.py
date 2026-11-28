from unittest.mock import MagicMock, patch
from flask import Flask, g
import pytest
from app.routes import admin

C='11111111-1111-4111-8111-111111111111'


@pytest.mark.parametrize('search',['x','ab','abc%','order','bad id','a'*33])
def test_invalid_order_search_does_not_run_an_order_query(search):
    app=Flask(__name__);db=MagicMock()
    with app.test_request_context(query_string={'search':search}),patch.object(admin,'get_user_client',return_value=db):
        g.user_role='admin';g.campus_id=C
        response,status=admin.list_all_orders.__wrapped__()
    assert status==400
    db.table.assert_not_called()


def test_scoped_order_page_gets_one_extra_row_and_joins_only_contact_fields():
    app=Flask(__name__);db=MagicMock();query=MagicMock()
    db.table.return_value=query
    for name in ('select','in_','neq','eq','gte','lte','order','limit','offset'):
        getattr(query,name).return_value=query
    query.execute.return_value=[{'id':str(i),'customer':{'full_name':'Known customer'},'delivery_address_snapshot':{'contact_phone':'08099999999'}} for i in range(3)]
    with app.test_request_context(query_string={'search':'AB-C','limit':'2','offset':'50'}),patch.object(admin,'get_user_client',return_value=db):
        g.user_role='admin';g.campus_id=C
        response,status=admin.list_all_orders.__wrapped__()
    assert status==200
    assert response.json['has_more'] is True and response.json['count']==2 and response.json['offset']==50
    assert response.json['orders'][0]['customer_phone']=='08099999999'
    query.limit.assert_called_once_with(3)
    query.gte.assert_called_once_with('id','abc00000-0000-0000-0000-000000000000')
    query.lte.assert_called_once_with('id','abcfffff-ffff-ffff-ffff-ffffffffffff')
    query.eq.assert_any_call('campus_id',C)
    assert 'customer:profiles!orders_user_id_fkey(id,full_name,phone)' in query.select.call_args.args[0]
    assert db.table.call_count==1
