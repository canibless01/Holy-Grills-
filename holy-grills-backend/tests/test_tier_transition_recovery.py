from unittest.mock import MagicMock,patch
from flask import Flask
import pytest
from app.services import hp_service,tier_service
from app.tasks import scheduled


def test_recalculate_uses_authoritative_atomic_transition_and_wakes_saved_notice():
    db=MagicMock();db.rpc.return_value={'changed':True,'event':'upgrade','reference_id':'receipt','tier':{'id':'flame'}}
    with patch.object(hp_service,'get_db',return_value=db),patch('app.services.notification_outbox.start_reference_dispatch') as wake:
        assert hp_service.recalculate_tier('student',campus_id='forged')['changed']
    db.rpc.assert_called_once_with('hg_recalculate_tier_atomic',{'p_user':'student'})
    db.table.assert_not_called();wake.assert_called_once_with('tier_upgrade','receipt')


def test_failed_atomic_transition_is_not_reported_as_success():
    db=MagicMock();db.rpc.return_value={'error':'conflict'}
    with patch.object(hp_service,'get_db',return_value=db),pytest.raises(RuntimeError):hp_service.recalculate_tier('student')


def test_batch_pagination_advances_and_releases_existing_lock():
    db=MagicMock();db.table.return_value.select.return_value.eq.return_value.execute.return_value=[{'id':'campus'}]
    replies=iter([{'checked':200,'has_more':True,'next_after':'cursor'},{'checked':17,'has_more':False}])
    db.rpc.side_effect=lambda name,args:next(replies) if name=='hg_tier_maintenance_batch' else True
    with Flask(__name__).app_context(),patch.object(scheduled,'get_db',return_value=db):result=scheduled._run_tier_maintenance('refresh')
    assert result['campus']['updated']==217
    calls=[call.args[1] for call in db.rpc.call_args_list if call.args[0]=='hg_tier_maintenance_batch']
    assert [call['p_after'] for call in calls]==[None,'cursor']
    db.rpc.assert_any_call('release_cron_lock',{'p_job_name':'recalculate_120day_hp'})


def test_batch_errors_request_retry_without_losing_cron_release():
    db=MagicMock();db.table.return_value.select.return_value.eq.return_value.execute.return_value=[{'id':'campus'}]
    db.rpc.side_effect=lambda name,args:{'checked':1,'errors':1,'has_more':False} if name=='hg_tier_maintenance_batch' else True
    with Flask(__name__).app_context(),patch.object(scheduled,'get_db',return_value=db),pytest.raises(RuntimeError,match='configuration review'):scheduled._run_tier_maintenance('grace')
    db.rpc.assert_any_call('release_cron_lock',{'p_job_name':'tier_grace_period_check'})
