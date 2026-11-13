"""Receipt-backed attendance; provider calls and database writes are mocked here.
The corresponding SQL file exercises the real transactional boundary with rollback.
"""
from datetime import datetime,date,timezone
from unittest.mock import MagicMock,patch
from flask import Flask
import pytest
from app.services import streak_service as s, wallet_service as wallet, order_service as orders

RECEIPT='10101010-1010-4010-8010-101010101010'
REFERENCE='20202020-2020-4020-8020-202020202020'


@pytest.mark.parametrize('ref',[None,'', 'not-a-receipt'])
def test_missing_or_invalid_receipt_never_claims_today(ref):
    with patch.object(s,'get_db') as db:
        result=s.try_reclaim_checkin('owner',reference_id=ref)
    assert not result['reclaimed']
    db.assert_not_called()


@pytest.mark.parametrize('replayed',[False,True])
def test_claim_and_replay_use_saved_day_reference_for_notification(replayed):
    app=Flask(__name__);app.config['STREAK_RECLAIM_MIN_TOPUP']=1500
    db=MagicMock();db.rpc.return_value={'reclaimed':not replayed,'already_reclaimed':replayed,
        'day_offset':1,'source_date':'2026-11-03','reference_id':REFERENCE}
    with app.app_context(),patch.object(s,'get_db',return_value=db),patch('app.services.notification_outbox.start_reference_dispatch') as notify:
        result=s.try_reclaim_checkin('owner','wallet_topup',RECEIPT)
    db.rpc.assert_called_once_with('hg_reclaim_login_checkin',{'p_user_id':'owner','p_source_type':'wallet_topup','p_source_id':RECEIPT,'p_min_topup':1500})
    assert result['day_offset']==1
    notify.assert_called_once_with('checkin_reclaimed', REFERENCE)


def test_unqualified_receipt_does_not_notify():
    db=MagicMock();db.rpc.return_value={'reclaimed':False,'reason':'unqualified_source'}
    with Flask(__name__).app_context(),patch.object(s,'get_db',return_value=db),patch('app.services.notification_outbox.start_reference_dispatch') as notify:
        assert not s.try_reclaim_checkin('owner','order',RECEIPT)['reclaimed']
    notify.assert_not_called()


def test_checkin_uses_merged_row_instead_of_writing_stale_week_json():
    db=MagicMock();login=MagicMock();profile=MagicMock()
    db.table.side_effect=lambda name:login if name=='login_streaks' else profile
    db.rpc.return_value={'success':True,'action':'checked_in','streak':{
        'current_week_start':'2026-11-02','cycle_week_number':2,
        'week_state':{'0':'checked','1':'reclaimed','2':'checked'}}}
    with patch.object(s,'_touch_last_activity'):
        result=s._process_login_streak_checkin(db,'owner',{
            'id':'streak','current_week_start':'2026-11-02','cycle_week_number':2,
            'week_state':{'0':'checked'}},datetime(2026,11,4,tzinfo=timezone.utc),date(2026,11,4))
    assert result['week_progress']['days']['Tue']=='reclaimed'
    login.update.assert_not_called()
    db.rpc.assert_called_once_with('hg_mark_current_login_checkin',{'p_user_id':'owner'})


def test_receipted_topup_below_hp_bonus_threshold_can_still_reclaim():
    app=Flask(__name__);app.config.update(STREAK_RECLAIM_MIN_TOPUP=1000,WALLET_TOPUP_MIN=3000)
    db=MagicMock();db.rpc.return_value={'transaction_id':RECEIPT,'new_balance':1000}
    with app.app_context(),patch.object(wallet,'get_db',return_value=db),patch.object(wallet,'setting_or_config',return_value=3000),patch.object(s,'try_reclaim_checkin') as reclaim:
        wallet.credit_wallet('owner',1000,reference_type='topup',payment_reference='provider-ref')
    reclaim.assert_called_once_with('owner',reclaim_type='wallet_topup',reference_id=RECEIPT)


def test_delivery_recovery_passes_its_original_order_receipt():
    with patch.object(s,'try_reclaim_checkin',return_value={'reclaimed':False}) as reclaim:
        orders._recover_delivery_checkin({'id':RECEIPT,'user_id':'owner'})
    reclaim.assert_called_once_with('owner',reference_id=RECEIPT)


def test_reclaim_notifications_deduplicate_same_day_receipt_replays():
    from tests.test_notification_preferences_delivery import Db
    from app.services import notification_service as ns
    db=Db()
    with Flask(__name__).app_context(),patch.object(ns,'get_db',return_value=db),patch.object(ns,'_is_throttled',return_value=False),patch.object(ns.threading,'Thread') as dispatch:
        for _ in range(2):
            ns.send_notification('user','checkin_reclaimed',title='Reclaimed',body='Attendance saved',reference_id=REFERENCE,reference_type='streak_reclaim',channels=['push','in_app'])
    assert len(db.rows['notifications'])==2
    assert dispatch.call_count==1
