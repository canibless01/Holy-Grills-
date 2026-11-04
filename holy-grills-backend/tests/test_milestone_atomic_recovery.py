"""Milestone service preserves eligibility gates and reports atomic failures."""
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask
from app.services import milestone_service as ms


def receipt(**extra):
    return {'completed':True,'completion_id':'receipt','recorded_hp_awarded':20,
            'hp_awarded':20,'replayed':False,**extra}


@pytest.mark.parametrize('replayed', [False, True])
def test_active_grant_uses_durable_completion_id_for_notification(replayed):
    db=MagicMock();db.rpc.return_value=receipt(replayed=replayed,hp_awarded=0 if replayed else 20)
    with Flask(__name__).app_context(),patch('app.services.hp_service._get_hp_multiplier',return_value=2),patch.object(ms,'notify_milestone_achieved') as notify:
        result=ms._complete_active_milestone(db,'student',{'id':'milestone'},10,None,campus_id='campus')
    assert result['already_completed']==replayed
    assert result['hp_awarded']==(0 if replayed else 20)
    assert db.rpc.call_args.args[1]['p_hp_amount']==20
    notify.assert_called_once_with('student','milestone',hp_awarded=20,completion_id='receipt')


def test_manual_grant_keeps_flat_amount_and_passes_issuer():
    db=MagicMock();db.rpc.return_value=receipt()
    with Flask(__name__).app_context(),patch('app.services.hp_service._get_hp_multiplier') as multiplier,patch.object(ms,'notify_milestone_achieved'):
        ms._complete_active_milestone(db,'student',{'id':'milestone'},20,None,campus_id='campus',admin_id='admin')
    multiplier.assert_not_called()
    assert db.rpc.call_args.args[1]['p_admin_id']=='admin'
    assert db.rpc.call_args.args[1]['p_hp_amount']==20


@pytest.mark.parametrize('outcome',[None,{}, {'error':'offline'}, {'completed':False,'legacy_review_required':True}])
def test_no_phantom_success_or_notification_on_failed_award(outcome):
    db=MagicMock();db.rpc.return_value=outcome
    with Flask(__name__).app_context(),patch.object(ms,'notify_milestone_achieved') as notify:
        with pytest.raises(RuntimeError):
            ms._complete_active_milestone(db,'student',{'id':'milestone'},0,None,campus_id='campus')
    notify.assert_not_called()


def test_previously_completed_active_claim_reads_saved_receipt_before_rechecking_eligibility():
    db=MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value={
        'id':'milestone','trigger_type':'order_count','time_window':'monthly','hp_awarded':999}
    with Flask(__name__).app_context(),patch.object(ms,'get_user_client',return_value=db),patch.object(ms,'get_db',return_value=db),patch.object(ms,'_is_already_completed',return_value=True),patch.object(ms,'_complete_active_milestone',return_value=receipt(replayed=True,hp_awarded=0)) as complete,patch.object(ms,'_compute_trigger_progress') as progress:
        result=ms.check_and_award_milestone('student','milestone')
    assert result['replayed']
    complete.assert_called_once()
    progress.assert_not_called()


def test_milestone_notifications_deduplicate_retries_but_allow_next_period():
    from tests.test_notification_preferences_delivery import Db
    from app.services import notification_service as ns
    db=Db()
    with Flask(__name__).app_context(),patch.object(ns,'get_db',return_value=db),patch.object(ns,'_is_throttled',return_value=False),patch.object(ns.threading,'Thread') as dispatch:
        for completion in ('month-one','month-one','month-two'):
            rows=ns.send_notification('user','milestone_achieved',title='Milestone',body='20 HP',
                reference_id=completion,reference_type='milestone_completion',channels=['push','in_app'])
            assert len(rows)==2
    assert len(db.rows['notifications'])==4
    assert dispatch.call_count==2


def test_one_failed_automatic_milestone_does_not_block_other_earned_grants():
    db=MagicMock();q=db.table.return_value
    for method in ('select','eq','or_','is_'):getattr(q,method).return_value=q
    q.execute.return_value=[{'id':'first','trigger_value':1,'hp_awarded':10},
                            {'id':'second','trigger_value':1,'hp_awarded':20}]
    with Flask(__name__).app_context(),patch.object(ms,'get_db',return_value=db),patch.object(ms,'_get_user_campus_id',return_value='campus'),patch.object(ms,'_complete_active_milestone',side_effect=[RuntimeError('retry later'),receipt()]) as complete:
        ms.check_milestone_trigger('student','first_order',1)
    assert complete.call_count==2
    assert complete.call_args_list[1].args[2]['id']=='second'
