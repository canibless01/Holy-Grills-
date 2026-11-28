"""Real reporting handler/middleware, controlled authentication/database only."""
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask,g
from app.routes import analytics
from app.middleware import auth
from app.db import SupabaseError
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333'
app=Flask(__name__)
app.register_blueprint(analytics.analytics_bp,url_prefix='/api/analytics')

@pytest.fixture
def db():
    client=MagicMock();query=client.table.return_value
    for name in ('select','eq','single'):getattr(query,name).return_value=query
    query.execute.return_value={'id':U,'role':'admin','is_active':True,'campus_id':A}
    client.auth_get_user.return_value={'id':U}
    client.rpc.return_value={'as_of':'2026-11-10T10:00:00+00:00','balances':{'outstanding':123}}
    with patch.object(auth,'get_db',return_value=client),patch.object(analytics,'get_db',return_value=client):yield client

@pytest.mark.parametrize('role',['student','community_manager','rider','kitchen','event_organizer'])
def test_nonfinancial_roles_cannot_request_customer_money_totals(db,role):
    db.table.return_value.execute.return_value['role']=role
    response=app.test_client().get('/api/analytics/wallet',headers={'Authorization':'Bearer controlled'})
    assert response.status_code==403;db.rpc.assert_not_called()

def test_inactive_admin_is_denied_before_aggregation(db):
    db.table.return_value.execute.return_value['is_active']=False
    assert app.test_client().get('/api/analytics/wallet',headers={'Authorization':'Bearer controlled'}).status_code==403
    db.rpc.assert_not_called()

def test_missing_authentication_is_denied(db):
    assert app.test_client().get('/api/analytics/wallet').status_code==401
    db.rpc.assert_not_called()

@pytest.mark.parametrize('role,query,headers,scope',[
 ('admin','&campus_id='+B,{},A),('super_admin','&campus_id='+B,{},B),
 ('super_admin','',{'X-Campus-ID':B},B),('super_admin','',{'X-Campus-Scope':'global'},None),
])
def test_scope_and_actor_come_from_verified_context(db,role,query,headers,scope):
    db.table.return_value.execute.return_value['role']=role
    response=app.test_client().get('/api/analytics/wallet?from_date=2026-11-01&to_date=2026-11-10&actor=attacker'+query,headers={'Authorization':'Bearer controlled',**headers})
    assert response.status_code==200 and response.json['balances']['outstanding']==123
    db.rpc.assert_called_once_with('hg_wallet_funding_analytics',{'p_actor':U,'p_campus':scope,'p_from':'2026-11-01','p_to':'2026-11-10'})

@pytest.mark.parametrize('query',[
 'from_date=2026-11-10&to_date=2026-11-09','from_date=2026-02-30&to_date=2026-03-01',
 'from_date=2025-01-01&to_date=2026-11-10','from_date=0001-01-01&to_date=0001-01-01',
 'from_date=9999-12-31&to_date=9999-12-31','campus_id=invalid',
])
def test_invalid_scope_dates_and_oversized_windows_do_not_query_financial_tables(db,query):
    db.table.return_value.execute.return_value['role']='super_admin'
    response=app.test_client().get('/api/analytics/wallet?'+query,headers={'Authorization':'Bearer controlled'})
    assert response.status_code==400;db.rpc.assert_not_called()

@pytest.mark.parametrize('code,status',[('wallet_analytics_forbidden',403),('wallet_analytics_date_invalid',400),('wallet_analytics_campus_invalid',400),('private internal diagnostic',503)])
def test_database_denials_are_clear_and_internal_errors_private(db,code,status):
    db.rpc.side_effect=SupabaseError('private diagnostic',500,{'message':code})
    response=app.test_client().get('/api/analytics/wallet',headers={'Authorization':'Bearer controlled'})
    assert response.status_code==status
    assert 'private' not in response.get_data(as_text=True)

@pytest.mark.parametrize('value',[None,[],{},'invalid'])
def test_missing_report_is_failure_instead_of_fabricated_zero(db,value):
    db.rpc.return_value=value
    response=app.test_client().get('/api/analytics/wallet',headers={'Authorization':'Bearer controlled'})
    assert response.status_code==503
