from datetime import date
from unittest.mock import MagicMock, patch
from flask import Flask
import pytest
from app.tasks import scheduled


@pytest.fixture(autouse=True)
def isolate_tier_refresh():
    with patch('app.services.hp_service.recalculate_tier'):
        yield


def setup_db(created='2026-08-10T23:30:00Z', enabled=True):
    db = MagicMock(); q = db.table.return_value
    for method in ('select', 'eq', 'is_'):
        getattr(q, method).return_value = q
    q.execute.side_effect = [[{'id': 'campus'}], [{'months': 3, 'is_active': enabled}], [{'id': 'student', 'created_at': created}]]
    db.rpc.side_effect = lambda name, args: {'success': True, 'awarded': 70, 'reference_id': 'receipt'} if name == 'hg_award_membership_anniversary' else True
    return db


def run_job(db, day=date(2026, 11, 13)):
    with Flask(__name__).app_context(), patch.object(scheduled, 'get_db', return_value=db), patch.object(scheduled, 'today_wat', return_value=day), patch('app.services.notification_outbox.start_reference_dispatch') as wake:
        result = scheduled.membership_anniversary_awards.run()
        return result, wake.call_args_list


def test_due_milestone_catches_up_after_missed_run_with_atomic_receipt():
    db = setup_db(); result, notices = run_job(db)
    assert result['campus']['awarded'] == 1
    db.rpc.assert_any_call('hg_award_membership_anniversary', {'p_user': 'student'})
    assert notices[0].args == ('membership_anniversary', 'receipt')


@pytest.mark.parametrize('created', ['2026-08-13T23:30:00Z', '2026-09-10T00:00:00Z'])
def test_future_wat_anniversary_and_nonmilestone_avoid_reward_reads(created):
    db = setup_db(created); result, notices = run_job(db)
    assert result['campus']['awarded'] == 0 and not notices
    assert all(call.args[0] != 'hg_award_membership_anniversary' for call in db.rpc.call_args_list)


def test_inactive_configuration_avoids_profile_sweep():
    db = setup_db(enabled=False); result, _ = run_job(db)
    assert result['campus']['awarded'] == 0
    assert db.table.return_value.execute.call_count == 2


def test_one_failed_recipient_preserves_others_and_requests_safe_retry():
    db = setup_db(); db.rpc.side_effect = lambda name, args: {'error': 'uncertain'} if name == 'hg_award_membership_anniversary' else True
    with pytest.raises(RuntimeError, match='incomplete'):
        run_job(db)
    db.rpc.assert_any_call('release_cron_lock', {'p_job_name': 'membership_anniversary_awards'})


def test_month_end_is_due_on_last_day():
    db = setup_db('2026-01-31T00:00:00Z'); result, _ = run_job(db, date(2026, 4, 30))
    assert result['campus']['awarded'] == 1
