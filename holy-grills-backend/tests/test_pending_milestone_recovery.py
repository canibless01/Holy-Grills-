from unittest.mock import MagicMock, patch
import pytest
from app.services import milestone_service as service

@pytest.mark.parametrize('replayed,awarded,recorded',[(False,25,25),(True,0,25),(True,0,0)])
def test_pending_receipt_keeps_destination_actual_notice_amount_and_completion_reference(replayed,awarded,recorded):
    db=MagicMock();db.rpc.return_value={'completed':True,'completion_id':'completion','recorded_hp_awarded':recorded,'hp_awarded':awarded,'hp_destination':'pending','replayed':replayed}
    with patch('app.services.hp_service._get_hp_multiplier',return_value=2),patch.object(service,'notify_milestone_achieved') as notify:
        result=service._complete_pending_milestone(db,'user',{'id':'milestone'},25,None,campus_id='campus')
    assert result['hp_destination']=='pending' and result['already_completed']==replayed
    assert db.rpc.call_args.args==('hg_complete_pending_milestone',{'p_user_id':'user','p_milestone_id':'milestone','p_period_key':None,'p_hp_amount':50})
    notify.assert_called_once_with('user','milestone',hp_awarded=recorded,completion_id='completion')
    db.table.assert_not_called()

@pytest.mark.parametrize('receipt',[None,{}, {'completed':False,'legacy_review_required':True}, {'error':'uncredited'}])
def test_uncredited_pending_reward_never_reports_completion_or_sends_success(receipt):
    db=MagicMock();db.rpc.return_value=receipt
    with patch.object(service,'notify_milestone_achieved') as notify,pytest.raises(RuntimeError):
        service._complete_pending_milestone(db,'user',{'id':'milestone'},0,None,campus_id='campus')
    notify.assert_not_called()


def test_previously_completed_social_claim_reenters_receipt_recovery():
    user_db=MagicMock();user_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value={'id':'milestone','trigger_type':'social_follow','hp_awarded':50}
    expected={'already_completed':True,'hp_awarded':0}
    with patch.object(service,'get_user_client',return_value=user_db),patch.object(service,'get_db') as db,patch.object(service,'_is_already_completed',return_value=True),patch.object(service,'_complete_pending_milestone',return_value=expected) as recover:
        assert service.check_and_award_milestone('user','milestone')==expected
    recover.assert_called_once_with(db.return_value,'user',{'id':'milestone','trigger_type':'social_follow','hp_awarded':50},50,None)
