"""Exercise real auth decorators, not unwrapped handlers, on new admin surfaces."""
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask
from app.middleware import auth
from app.routes.delivery_pass import admin_delivery_pass_bp
from app.routes.stores import stores_bp
from app.routes.store_stock import store_stock_bp
C='11111111-1111-4111-8111-111111111111'
U='22222222-2222-4222-8222-222222222222'

@pytest.mark.parametrize('role',['student','community_manager','event_organizer','rider','kitchen','admin','super_admin'])
@pytest.mark.parametrize('endpoint',['/pass','/stores','/stock'])
def test_real_middleware_enforces_role_before_business_rpc(role,endpoint):
    app=Flask(__name__);app.config['TESTING']=True
    app.register_blueprint(admin_delivery_pass_bp,url_prefix='/pass')
    app.register_blueprint(stores_bp,url_prefix='')
    app.register_blueprint(store_stock_bp,url_prefix='/stock')
    db=MagicMock();db.rpc.return_value={};db.auth_get_user.return_value={'id':U}
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':U,'role':role,'campus_id':C,'is_active':True}
    # Empty but valid reports: avoid introducing any synthetic financial state.
    db.table.return_value.select.return_value.order.return_value.order.return_value.eq.return_value.execute.return_value=[]
    allowed=role in ('admin','super_admin') or endpoint=='/stock' and role=='kitchen'
    from app.services import delivery_pass
    with patch.object(auth,'get_db',return_value=db),patch('app.routes.stores.get_db',return_value=db),patch('app.routes.store_stock.get_db',return_value=db),patch.object(delivery_pass,'rpc',return_value={}) as rpc,patch('app.services.feature_flags.is_feature_enabled',return_value=False):
        response=app.test_client().get(endpoint,headers={'Authorization':'Bearer controlled','X-Campus-ID':C})
    if not allowed:
        assert response.status_code==403
        db.rpc.assert_not_called();rpc.assert_not_called()
    else:
        # The report's SQL authorization is covered separately by live rollback fixtures.
        assert response.status_code==200

@pytest.mark.parametrize('endpoint',['/pass','/stores','/stock'])
def test_unauthenticated_access_never_reaches_database(endpoint):
    app=Flask(__name__)
    app.register_blueprint(admin_delivery_pass_bp,url_prefix='/pass');app.register_blueprint(stores_bp,url_prefix='');app.register_blueprint(store_stock_bp,url_prefix='/stock')
    with patch.object(auth,'get_db') as db:
        response=app.test_client().get(endpoint)
    assert response.status_code==401
    db.assert_not_called()
