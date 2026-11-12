from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from app.routes import kitchen
from app.services import feature_flags
from app.services.notification_preferences import permitted_channels

C='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222'
app=Flask(__name__)

def flag_rows(campus_value=False,global_value=True):
    db=MagicMock();q=db.table.return_value
    for name in ('select','eq','is_','single'):getattr(q,name).return_value=q
    q.execute.side_effect=[{'is_active':campus_value},{'is_active':global_value}]
    return db,q

@pytest.mark.parametrize('name',['hp_transfer','free_side_credits','exclusive_spin','hall_of_fame','scheduled_orders'])
def test_implicit_student_gate_honors_own_campus_pause(name):
    db,q=flag_rows()
    with app.test_request_context(headers={'X-Campus-ID':B}),patch.object(feature_flags,'get_db',return_value=db):
        g.user_id='student';g.user_role='student';g.campus_id=C
        assert feature_flags.is_feature_enabled(name) is False
    q.eq.assert_any_call('campus_id',C);assert q.execute.call_count==1


def test_super_admin_flag_uses_selected_campus_not_profile_campus():
    db,q=flag_rows()
    with app.test_request_context(headers={'X-Campus-ID':B}),patch.object(feature_flags,'get_db',return_value=db):
        g.user_id='super';g.user_role='super_admin';g.campus_id=C
        assert feature_flags.is_feature_enabled('hp_transfer') is False
    q.eq.assert_any_call('campus_id',B)


def test_worker_without_request_keeps_global_lookup_and_db_failure_fails_closed():
    db,q=flag_rows(campus_value=True)
    with app.app_context(),patch.object(feature_flags,'get_db',return_value=db):
        assert feature_flags.is_feature_enabled('hp_transfer') is True
    q.is_.assert_called_once_with('campus_id','null')
    q.execute.side_effect=RuntimeError('controlled')
    with app.app_context(),patch.object(feature_flags,'get_db',return_value=db):assert feature_flags.is_feature_enabled('hp_transfer',C) is False


def test_absent_campus_override_falls_back_global():
    db,q=flag_rows();q.execute.side_effect=[None,{'is_active':True}]
    with app.test_request_context(),patch.object(feature_flags,'get_db',return_value=db):
        g.user_id='student';g.user_role='student';g.campus_id=C
        assert feature_flags.is_feature_enabled('hp_transfer') is True
    assert q.execute.call_count==2


def test_stock_alert_is_operational_not_marketing_and_respects_channel_opt_out():
    prefs={'promotions':False,'push_enabled':True}
    assert permitted_channels('low_stock_ingredient',['in_app','push'],prefs)==['in_app','push']
    prefs['push_enabled']=False
    assert permitted_channels('low_stock_ingredient',['in_app','push'],prefs)==['in_app']


def test_stock_report_scopes_verified_actor_and_date_range():
    db=MagicMock();db.rpc.return_value={'items':[]}
    with app.test_request_context('/?campus_id='+B+'&from_date=2026-11-01&to_date=2026-11-02'),patch.object(kitchen,'get_db',return_value=db):
        g.user_id='verified';g.user_role='admin';g.campus_id=C
        response,status=kitchen.stock_report.__wrapped__()
    assert status==200 and response.json=={'items':[]}
    db.rpc.assert_called_once_with('hg_stock_report',{'p_actor':'verified','p_campus':C,'p_from':'2026-11-01','p_to':'2026-11-02'})

@pytest.mark.parametrize('query',['from_date=no','from_date=2026-11-02&to_date=2026-11-01','from_date=2020-01-01&to_date=2026-01-01','to_date=2099-01-01'])
def test_invalid_stock_report_never_queries_database(query):
    db=MagicMock()
    with app.test_request_context('/?'+query),patch.object(kitchen,'get_db',return_value=db):
        _,status=kitchen.stock_report.__wrapped__()
    assert status==400;db.rpc.assert_not_called()


@pytest.mark.parametrize('module_name,function_name',[
 ('free_sides','my_free_sides'),('exclusive_spin','my_spins'),('hp','transfer_hp'),('leaderboard','hall_of_fame')])
def test_real_customer_endpoints_stop_before_rewards_or_transfers_when_campus_paused(module_name,function_name):
    import inspect,importlib
    module=importlib.import_module('app.routes.'+module_name)
    db,q=flag_rows();business=MagicMock()
    with app.test_request_context(method='POST',json={}),patch.object(feature_flags,'get_db',return_value=db),patch.object(module,'get_user_client',return_value=business):
        g.user_id='student';g.user_role='student';g.campus_id=C
        response,status=inspect.unwrap(getattr(module,function_name))()
    assert status==403
    business.table.assert_not_called();business.rpc.assert_not_called()
    q.eq.assert_any_call('campus_id',C)


def test_real_order_admission_rejects_paused_scheduling_before_calendar_or_money():
    from tests import test_checkout_quote as fixture
    from app.services import order_service
    case=fixture.CheckoutQuoteTests();case.setUp()
    case.db.rows['feature_flags']=[{'feature_name':'scheduled_orders','campus_id':fixture.CAMPUS,'is_active':False},{'feature_name':'scheduled_orders','campus_id':None,'is_active':True}]
    with patch.object(feature_flags,'get_db',return_value=case.db),patch.object(order_service,'_order_for_intent',return_value=None),patch.object(order_service,'resolve_ordering_window',side_effect=AssertionError('Paused scheduling reached admission')):
        with pytest.raises(ValueError,match='Scheduled ordering is not available'):
            case.calculate(quote_only=False,payload={**case.payload,'is_scheduled':True})
