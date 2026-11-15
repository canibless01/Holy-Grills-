"""Actual admin cart handler selection/metrics boundaries; no customer writes."""
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask,g
from app.routes import admin
A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
@pytest.mark.parametrize('status,recovered',[('',False),('pending',False),('recovered',True),('all',None)])
@pytest.mark.parametrize('role,requested,expected',[('admin',B,A),('super_admin',B,B),('super_admin','',None)])
def test_cart_filters_use_real_recovery_state_and_effective_campus(status,recovered,role,requested,expected):
 db=MagicMock();q=db.table.return_value
 for name in ('select','eq','order','limit','offset'):getattr(q,name).return_value=q
 q.execute.return_value=[{'id':'cart','is_recovered':bool(recovered)}]
 service=MagicMock();service.rpc.return_value={'cart':{'saved_nudges':2}}
 url='/?campus_id='+requested+('&status='+status if status else '')
 with Flask(__name__).test_request_context(url),patch.object(admin,'get_user_client',return_value=db),patch.object(admin,'get_db',return_value=service):
  g.user_role=role;g.campus_id=A
  response,code=admin.abandoned_carts.__wrapped__()
 assert code==200 and response.json[0]['saved_nudges']==2
 filters=[c.args for c in q.eq.call_args_list]
 if recovered is None:assert not any(c[0]=='is_recovered' for c in filters)
 else:assert ('is_recovered',recovered) in filters
 if expected:assert ('campus_id',expected) in filters
 else:assert not any(c[0]=='campus_id' for c in filters)
 service.rpc.assert_called_once_with('hg_cart_recovery_metrics',{'p_ids':['cart']})
@pytest.mark.parametrize('status',['exhausted','cleared','invalid'])
def test_unknown_cart_status_fails_before_table_query(status):
 db=MagicMock()
 with Flask(__name__).test_request_context('/?status='+status),patch.object(admin,'get_user_client',return_value=db):
  g.user_role='admin';g.campus_id=A
  _,code=admin.abandoned_carts.__wrapped__()
 assert code==400;db.table.assert_not_called()
