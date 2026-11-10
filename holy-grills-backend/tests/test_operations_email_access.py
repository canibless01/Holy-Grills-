from unittest.mock import MagicMock,patch
from flask import Flask
import pytest
from app.routes import admin
from app.middleware import auth
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333'
app=Flask(__name__);app.register_blueprint(admin.admin_bp,url_prefix='/api/admin')
@pytest.fixture
def db():
    client=MagicMock();q=client.table.return_value
    for name in ('select','eq','single'):getattr(q,name).return_value=q
    q.execute.return_value={'id':U,'role':'admin','is_active':True,'campus_id':A}
    client.auth_get_user.return_value={'id':U};client.rpc.return_value={'counts':{},'recent':[]}
    with patch.object(auth,'get_db',return_value=client),patch.object(admin,'get_db',return_value=client):yield client
@pytest.mark.parametrize('role',['student','rider','kitchen','community_manager','event_organizer'])
def test_communications_status_requires_admin(db,role):
    db.table.return_value.execute.return_value['role']=role
    assert app.test_client().get('/api/admin/operations-emails?campus_id='+A,headers={'Authorization':'Bearer controlled'}).status_code==403
    db.rpc.assert_not_called()
def test_campus_admin_cannot_redirect_status_or_retry_to_another_campus(db):
    response=app.test_client().get('/api/admin/operations-emails?campus_id='+B+'&actor=spoof',headers={'Authorization':'Bearer controlled'})
    assert response.status_code==200
    db.rpc.assert_called_once_with('hg_operations_email_status',{'p_actor':U,'p_campus':A,'p_retry':None})
def test_super_admin_uses_explicit_target_for_status(db):
    db.table.return_value.execute.return_value['role']='super_admin'
    assert app.test_client().get('/api/admin/operations-emails?campus_id='+B,headers={'Authorization':'Bearer controlled'}).status_code==200
    assert db.rpc.call_args.args[1]['p_campus']==B
def test_invalid_retry_id_is_refused_before_outbox_call(db):
    assert app.test_client().post('/api/admin/operations-emails/invalid/retry?campus_id='+A,headers={'Authorization':'Bearer controlled'}).status_code==400
    db.rpc.assert_not_called()
