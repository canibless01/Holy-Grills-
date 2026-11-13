from unittest.mock import MagicMock
from app.services.tier_service import ensure_initial_student_tier


def test_missing_tier_uses_database_receipt_without_overwriting_points():
    db=MagicMock();db.rpc.return_value={'tier':{'id':'flame'},'changed':True}
    profile={'id':'student','role':'student','current_tier_id':None,'hp_earned_120day':150}
    result=ensure_initial_student_tier(profile,db)
    assert result['current_tier_id']=='flame' and result['hp_earned_120day']==150
    db.rpc.assert_called_once_with('hg_recalculate_tier_atomic',{'p_user':'student'});db.table.assert_not_called()


def test_existing_staff_and_inactive_profiles_are_not_reassigned():
    for changes in [{'current_tier_id':'holy'},{'role':'kitchen'},{'is_active':False}]:
        db=MagicMock();profile={'id':'student','role':'student','current_tier_id':None,**changes}
        assert ensure_initial_student_tier(profile,db)==profile;db.rpc.assert_not_called()


def test_refused_assignment_preserves_missing_profile_for_later_recovery():
    db=MagicMock();db.rpc.return_value={'changed':False,'tier':None,'reason':'excluded'}
    profile={'id':'student','role':'student','current_tier_id':None}
    assert ensure_initial_student_tier(profile,db)==profile
