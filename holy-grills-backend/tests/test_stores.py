"""Store configuration validation and role/campus isolation before operational cutover."""
from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from app.routes import stores
from app.db import SupabaseError
from app.messages import MSG
A='11111111-1111-4111-8111-111111111111';C='22222222-2222-4222-8222-222222222222';S='33333333-3333-4333-8333-333333333333'
BASE={'name':'Main store','slug':'main-store','address':'West gate road','instructions':'Collect at counter','lat':7.3,'lon':5.2,'is_active':True,'pickup_enabled':True,'delivery_enabled':True}

@pytest.mark.parametrize('patch_value',[{'name':''},{'slug':'BAD SLUG'},{'address':''},{'instructions':'a'*501},{'lat':True},{'lat':float('nan')},{'lon':181},{'lat':None},{'is_active':'false'},{'pickup_enabled':False,'delivery_enabled':False}])
def test_invalid_store_settings_fail_before_a_write(patch_value):
 with pytest.raises(ValueError):stores.normalized({**BASE,**patch_value})


def test_store_coordinates_optional_but_pair_required():
 assert stores.normalized({**BASE,'lat':None,'lon':None})['lat'] is None
 assert stores.normalized({**BASE,'is_active':False,'pickup_enabled':False,'delivery_enabled':False})['is_active'] is False


def test_campus_admin_cannot_select_another_campus_for_creation():
 app=Flask(__name__)
 db=MagicMock();db.rpc.return_value={'id':S,'campus_id':C}
 with app.test_request_context(method='POST',json={**BASE,'request_id':S,'campus_id':A}),patch.object(stores,'get_db',return_value=db):
  g.user_id=A;g.user_role='admin';g.campus_id=C
  response,status=stores.create_store.__wrapped__()
 assert status==201 and db.rpc.call_args.args[1]['p_campus']==C


def test_super_admin_must_choose_concrete_campus_for_store():
 app=Flask(__name__)
 with app.test_request_context(method='POST',json={**BASE,'request_id':S}),patch.object(stores,'get_db') as db:
  g.user_id=A;g.user_role='super_admin';g.campus_id=C
  response,status=stores.create_store.__wrapped__()
 assert status==400 and response.json['error']==MSG.STORE_CAMPUS_REQUIRED
 db.return_value.rpc.assert_not_called()


def test_cross_campus_store_update_denied_before_write():
 from werkzeug.exceptions import Forbidden
 app=Flask(__name__);db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':S,'campus_id':A}
 with app.test_request_context(method='PATCH',json={**BASE,'expected_updated_at':'2026-11-23T10:00:00Z'}),patch.object(stores,'get_db',return_value=db):
  g.user_id=A;g.user_role='admin';g.campus_id=C
  with pytest.raises(Forbidden):stores.update_store.__wrapped__(S)
 db.rpc.assert_not_called()


@pytest.mark.parametrize('code,status',[('HG_STORE_CONFLICT',409),('HG_STORE_ACCESS',403),('HG_STORE_STAFF_INVALID',400)])
def test_database_decision_is_not_reported_as_generic_error(code,status):
 app=Flask(__name__);db=MagicMock();db.rpc.side_effect=SupabaseError(code,400,{})
 with app.test_request_context(method='POST',json={**BASE,'request_id':S,'campus_id':C}),patch.object(stores,'get_db',return_value=db):
  g.user_id=A;g.user_role='admin';g.campus_id=C
  response,actual=stores.create_store.__wrapped__()
 assert actual==status and code not in response.json['error']


def test_store_id_cannot_be_smuggled_in_as_a_transfer_or_order_configuration():
 app=Flask(__name__)
 with app.test_request_context(method='POST',json={**BASE,'request_id':S,'campus_id':C,'university_id':A}),patch.object(stores,'get_db') as db:
  g.user_id=A;g.user_role='admin';g.campus_id=C
  response,status=stores.create_store.__wrapped__()
 assert status==400;db.return_value.rpc.assert_not_called()
