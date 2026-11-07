"""Campus admins manage community-manager activation in their own campus."""
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask,g
from werkzeug.exceptions import Forbidden
from app.routes import admin
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';ACTOR='33333333-3333-4333-8333-333333333333';TARGET='44444444-4444-4444-8444-444444444444'
app=Flask(__name__)
def invoke(action,role='community_manager',campus=A,caller='admin'):
 db=MagicMock();q=db.table.return_value
 for method in ('select','eq','single','in_','limit','delete'):getattr(q,method).return_value=q
 q.not_=q
 target={'id':TARGET,'role':role,'campus_id':campus,'is_active':action=='deactivate','full_name':'Controlled manager','email':'controlled@example.invalid'}
 q.execute.side_effect=[target,[],[]] if action=='deactivate' else [target]
 q.update.return_value=[{**target,'is_active':action=='activate'}]
 with app.test_request_context(method='POST'),patch.object(admin,'get_user_client',return_value=db),patch.object(admin,'get_db',return_value=db),patch.object(admin,'send_notification') as notify,patch.object(admin,'_revoke_supabase_sessions',return_value=SimpleNamespace(status_code=200)),patch.object(admin,'_audit',return_value=True):
  g.user_id=ACTOR;g.user_role=caller;g.campus_id=A
  response,status=(admin.deactivate_user if action=='deactivate' else admin.activate_user).__wrapped__(TARGET)
 return response,status,q,notify

@pytest.mark.parametrize('action',['activate','deactivate'])
def test_campus_admin_can_change_own_community_manager_status(action):
 response,status,q,notify=invoke(action)
 assert status==200 and response.json['user_id']==TARGET
 assert q.update.call_args.args[0]['is_active'] is (action=='activate')
 notify.assert_called_once()

@pytest.mark.parametrize('action',['activate','deactivate'])
def test_other_campus_stays_forbidden(action):
 with pytest.raises(Forbidden):invoke(action,campus=B)

@pytest.mark.parametrize('action',['activate','deactivate'])
@pytest.mark.parametrize('target_role',['admin','super_admin'])
def test_admin_accounts_stay_super_admin_only(action,target_role):
 _,status,q,notify=invoke(action,role=target_role);assert status==403;q.update.assert_not_called();notify.assert_not_called()

@pytest.mark.parametrize('action',['activate','deactivate'])
def test_super_admin_can_manage_a_manager_from_another_campus(action):
 assert invoke(action,campus=B,caller='super_admin')[1]==200
