from unittest.mock import MagicMock
from flask import Flask,g,jsonify
import pytest
from app.db import SupabaseClient
from app.services.cushion_privacy import PUBLIC_COLUMNS,public_projection,strip_internal,install_response_privacy


def client():
    db=SupabaseClient('https://db.invalid','service','anon')
    db._session=MagicMock()
    for method in ('get','post','patch','delete'):
        r=getattr(db._session,method).return_value;r.status_code=200;r.content=b'[]';r.json.return_value=[]
    return db


def test_nested_aliases_and_existing_public_fields_are_preserved():
    selected=public_projection('orders','*,lines:order_items!inner(*,extras:order_addon_selections(*)),profiles(full_name)')
    assert selected=='*,lines:order_items!inner('+PUBLIC_COLUMNS['order_items']+',extras:order_addon_selections('+PUBLIC_COLUMNS['order_addon_selections']+')),profiles(full_name)'
    assert public_projection('profiles','id,email')=='id,email'
    assert public_projection('menu_items','id,name,price')=='id,name,price'


@pytest.mark.parametrize('table',PUBLIC_COLUMNS)
def test_rls_reads_keep_existing_fields_without_private_columns(table):
    db=client();db.table(table).with_jwt('customer').select('*').execute()
    assert db._session.get.call_args.kwargs['params']['select']==PUBLIC_COLUMNS[table]
    db.table(table).select('*').execute()
    assert db._session.get.call_args.kwargs['params']['select']=='*'


@pytest.mark.parametrize('method',['insert','update','delete','upsert'])
def test_scoped_write_receipts_do_not_require_access_to_new_private_columns(method):
    db=client();q=db.table('menu_items').with_jwt('admin').eq('id','item')
    getattr(q,method)(*(() if method=='delete' else ({'name':'Meal'},)))
    transport={'insert':'post','upsert':'post','update':'patch','delete':'delete'}[method]
    args=getattr(db._session,transport).call_args.kwargs
    assert args['params']['select']==PUBLIC_COLUMNS['menu_items']
    if method in ('update','delete'):assert args['params']['id']=='eq.item'


def test_guest_and_student_responses_hide_nested_allocations_without_mutating_sources():
    source={'price':3500,'cushion_amount':500,'items':[{'quantity':2,'cushion_snapshot':100,'options_snapshot':{'notes':'cushion is a word','_cushion_plan':{'amount':1}}}]}
    result,changed=strip_internal(source)
    assert changed and result=={'price':3500,'items':[{'quantity':2,'options_snapshot':{'notes':'cushion is a word'}}]}
    assert source['cushion_amount']==500
    clean={'name':'Meal','price':3500};assert strip_internal(clean)==(clean,False)


@pytest.mark.parametrize('role',[None,'student','kitchen','rider','community_manager','admin','super_admin'])
def test_only_admin_api_responses_retain_cushion_fields(role):
    app=Flask(__name__);install_response_privacy(app)
    @app.get('/')
    def route():
        g.user_role=role
        return jsonify({'price':3500,'cushion_amount':500,'items':[{'cushion_snapshot':50}]}),201
    response=app.test_client().get('/')
    assert response.status_code==201
    assert ('cushion_amount' in response.json)==(role in ('admin','super_admin'))
    assert ('cushion_snapshot' in response.json['items'][0])==(role in ('admin','super_admin'))
