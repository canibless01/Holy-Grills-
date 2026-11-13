from unittest.mock import MagicMock, patch
import pytest
from app.services import squad_service


@pytest.fixture(autouse=True)
def isolate_tier_refresh():
    with patch('app.services.hp_service.recalculate_tier'):
        yield


def database(rows):
    db = MagicMock(); q = db.table.return_value
    for key in ('select', 'eq', 'is_', 'single'):
        getattr(q, key).return_value = q
    q.execute.side_effect = rows
    return db, q


def test_signup_uses_atomic_claim_and_own_campus():
    db, q = database([[{'id': 'pending'}]])
    db.rpc.return_value = {'success': True, 'order_id': 'order', 'awarded': 12}
    with patch.object(squad_service, 'get_db', return_value=db), patch('app.services.notification_outbox.start_reference_dispatch') as wake:
        assert squad_service.claim_pending_for_user(' Student@Example.com ', 'user', 'campus') == {'claimed': 1}
    q.eq.assert_any_call('campus_id', 'campus'); q.eq.assert_any_call('email', 'student@example.com')
    db.rpc.assert_called_once_with('hg_claim_pending_squad_hp', {'p_pending': 'pending', 'p_user': 'user'})
    wake.assert_called_once_with('squad_hp_share', 'order')
    q.update.assert_not_called()


def test_missing_campus_never_guesses_global_claim():
    with patch.object(squad_service, 'get_db') as get_db:
        assert squad_service.claim_pending_for_user('a@b.com', 'user') == {'claimed': 0}
        get_db.assert_not_called()


@pytest.mark.parametrize('reply', [{'error': 'squad_recipient_unavailable'}, None, []])
def test_refused_or_uncertain_claim_never_wakes_notification(reply):
    db, _ = database([[{'id': 'pending'}]]); db.rpc.return_value = reply
    with patch.object(squad_service, 'get_db', return_value=db), patch('app.services.notification_outbox.start_reference_dispatch') as wake:
        assert squad_service.claim_pending_for_user('a@b.com', 'user', 'campus')['claimed'] == 0
    wake.assert_not_called()


def test_response_loss_keeps_row_for_later_retry_and_other_rows_continue():
    db, _ = database([[{'id': 'lost'}, {'id': 'next'}]])
    db.rpc.side_effect = [TimeoutError('response lost'), {'success': True, 'order_id': 'order'}]
    with patch.object(squad_service, 'get_db', return_value=db), patch('app.services.notification_outbox.start_reference_dispatch'):
        assert squad_service.claim_pending_for_user('a@b.com', 'user', 'campus')['claimed'] == 1
    assert db.rpc.call_count == 2


def test_daily_sweep_filters_active_recipient_by_same_campus():
    db, q = database([[{'id': 'pending', 'email': 'a@b.com', 'campus_id': 'campus'}], {'id': 'user'}])
    db.rpc.return_value = {'success': True, 'order_id': 'order'}
    with patch.object(squad_service, 'get_db', return_value=db), patch('app.services.notification_outbox.start_reference_dispatch'):
        assert squad_service.sweep_pending_squad_hp('campus')['claimed'] == 1
    q.eq.assert_any_call('is_active', True); q.eq.assert_any_call('campus_id', 'campus')


def test_global_sweep_only_reads_legacy_null_campus_and_never_claims_them():
    db, q = database([[{'id': 'legacy', 'campus_id': None}]])
    with patch.object(squad_service, 'get_db', return_value=db):
        assert squad_service.sweep_pending_squad_hp()['claimed'] == 0
    q.is_.assert_called_once_with('campus_id', 'null'); db.rpc.assert_not_called()
