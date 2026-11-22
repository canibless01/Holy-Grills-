from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask
from app.services import automatic_preparation as auto, order_service as orders
from app.utils.schedule import resolve_date_override
from app.tasks import scheduled
from app.tasks.celery_app import celery_app
NOW = datetime(2026,11,22,11,0,tzinfo=auto.WAT)

def test_cutoff_uses_wat_and_keeps_manual_closure_and_overnight_out():
    rows=[{'id':'closed','opens_at':'09:00:00','closes_at':'11:00:00'}, {'id':'open','opens_at':'09:00','closes_at':'12:00'}, {'id':'manual','opens_at':'09:00','closes_at':'10:00','is_closed':True}, {'id':'overnight','opens_at':'21:00','closes_at':'08:00'}]
    with patch.object(auto,'effective_windows_with_config',return_value=(rows,'date')) as windows:
        assert auto.closed_windows(None,'campus',NOW)==['closed']
    assert windows.call_args.kwargs=={'strict':True}

def test_override_read_failure_must_block_automatic_actions():
    db=MagicMock();db.table.return_value.select.return_value.eq.return_value.execute.side_effect=RuntimeError('offline')
    with pytest.raises(RuntimeError):resolve_date_override(db,'campus','2026-11-22',strict=True)

def fixture():
    db=MagicMock();campuses=MagicMock();campuses.select.return_value.eq.return_value.execute.return_value=[{'id':'campus'}]
    query=MagicMock()
    for method in ('select','eq','in_','or_','is_','order','limit'):getattr(query,method).return_value=query
    db.table.side_effect=lambda name:campuses if name=='campuses' else query
    query.execute.return_value=[{'id':'one'},{'id':'two'}]
    return db,query

def test_release_off_does_not_read_orders_or_windows():
    db,_=fixture()
    with patch.object(auto,'get_db',return_value=db),patch.object(auto,'is_feature_enabled',return_value=False),patch.object(auto,'closed_windows') as windows:
        assert auto.prepare_closed_windows()=={}
    windows.assert_not_called();assert [c.args[0] for c in db.table.call_args_list]==['campuses']

def test_scan_scopes_paid_day_window_and_uses_existing_status_path():
    db,query=fixture()
    with patch.object(auto,'get_db',return_value=db),patch.object(auto,'is_feature_enabled',return_value=True),patch.object(auto,'closed_windows',return_value=['window']),patch.object(orders,'update_order_status',side_effect=[{'status':'preparing'},orders.OrderConflictError('Already moved')]) as move:
        result=auto.prepare_closed_windows()
    assert result['campus']=={'prepared':1,'skipped':1,'failed':0}
    assert ('campus_id','campus') in [c.args for c in query.eq.call_args_list]
    assert ('is_test',False) in [c.args for c in query.eq.call_args_list]
    assert ('payment_status',['paid','partially_refunded']) in [c.args for c in query.in_.call_args_list]
    assert ('ordering_window_id',['window']) in [c.args for c in query.in_.call_args_list]
    assert 'scheduled_for.gte.' in query.or_.call_args.args[0] and 'created_at.lt.' in query.or_.call_args.args[0]
    assert all(c.args[1]=='preparing' and c.kwargs['_system_task'] for c in move.call_args_list)

def test_schedule_error_does_not_start_orders_and_failed_transitions_are_retryable():
    db,_=fixture()
    with patch.object(auto,'get_db',return_value=db),patch.object(auto,'is_feature_enabled',return_value=True),patch.object(auto,'closed_windows',side_effect=RuntimeError('offline')),patch.object(orders,'update_order_status') as move:
        assert auto.prepare_closed_windows()['campus']['error']=='preparation_scan_failed'
    move.assert_not_called()
    with patch.object(auto,'get_db',return_value=db),patch.object(auto,'is_feature_enabled',return_value=True),patch.object(auto,'closed_windows',return_value=['window']),patch.object(orders,'update_order_status',side_effect=RuntimeError('offline')):
        result=auto.prepare_closed_windows()['campus'];assert result['failed']==2 and result['error']=='preparation_retry_pending'

def test_background_service_access_is_not_available_to_http_or_staff_impersonation():
    with Flask(__name__).test_request_context(),patch.object(orders,'get_db') as db:
        with pytest.raises(orders.OrderForbiddenError):orders.update_order_status('order','preparing',_system_task=True)
    db.assert_not_called()
    with pytest.raises(orders.OrderForbiddenError):orders.update_order_status('order','preparing',changed_by='staff',_system_task=True)

def test_worker_lock_release_and_existing_beat_registration():
    db=MagicMock();db.rpc.return_value=True
    with patch.object(scheduled,'get_db',return_value=db),patch.object(auto,'prepare_closed_windows',return_value={'campus':{'prepared':2}}):
        assert scheduled.auto_prepare_closed_windows.run()['campus']['prepared']==2
    assert db.rpc.call_args.args==('release_cron_lock',{'p_job_name':'auto_prepare_closed_windows'})
    job=celery_app.conf.beat_schedule['auto-prepare-closed-windows'];assert job['task']=='app.tasks.scheduled.auto_prepare_closed_windows'
