"""Weekly payout API and notice recovery; real financial proofs use rollback SQL."""
from datetime import date,datetime,timezone
from unittest.mock import MagicMock,patch
from flask import Flask
import pytest
from app.services import streak_service as s
from app.services.notification_templates import render_notification_template

USER='10101010-1010-4010-8010-101010101010'
REF='20202020-2020-4020-8020-202020202020'
OLD={'id':'streak','current_week_start':'2026-10-26','cycle_week_number':1,
     'week_state':{str(i):'checked' for i in range(5)}}
NOTICE={'reference_id':REF,'week_start':'2026-10-26','previous_week_completed':True,
        'missed_days':2,'cycle_week':1,'hp_awarded':25,'notified':False}


def result(replayed=False):
    return {'success':True,'replayed':replayed,'hp_awarded':0 if replayed else 25,
        'today':'2026-11-04','receipt':dict(NOTICE),'streak':{'current_week_start':'2026-11-02',
        'cycle_week_number':2,'consecutive_weeks':1,'week_state':{'2':'checked'}}}


@pytest.mark.parametrize('replayed',[False,True])
def test_weekly_service_uses_committed_receipt_and_actual_new_award(replayed):
    db=MagicMock();db.rpc.return_value=result(replayed)
    with Flask(__name__).app_context(),patch.object(s,'_deliver_login_week_notice') as notice,patch.object(s,'_touch_last_activity'):
        response=s._process_login_streak_checkin(db,USER,OLD,datetime(2026,11,4,tzinfo=timezone.utc),date(2026,11,4))
    assert response['previous_week_completed']
    assert response['hp_awarded']==(0 if replayed else 25)
    db.rpc.assert_called_once_with('hg_rollover_login_week',{'p_user_id':USER})
    db.table.assert_not_called()
    notice.assert_called_once_with(db,USER,NOTICE)


@pytest.mark.parametrize('failure',[{'error':'ledger failure'},None,{},RuntimeError('pending ceiling')])
def test_failed_payout_cannot_advance_week_or_send_success(failure):
    db=MagicMock()
    if isinstance(failure,Exception):db.rpc.side_effect=failure
    else:db.rpc.return_value=failure
    with Flask(__name__).app_context(),patch.object(s,'_deliver_login_week_notice') as notice:
        response=s._process_login_streak_checkin(db,USER,OLD,datetime(2026,11,4,tzinfo=timezone.utc),date(2026,11,4))
    assert response['action']=='failed'
    db.table.assert_not_called();notice.assert_not_called()


def test_notice_persistence_failure_leaves_outcome_unacknowledged_for_next_login():
    db=MagicMock()
    with patch('app.services.notification_service.send_notification',side_effect=RuntimeError('storage unavailable')):
        s._deliver_login_week_notice(db,USER,NOTICE)
    db.rpc.assert_not_called()


def test_notice_retry_uses_original_amount_week_and_dedup_reference():
    db=MagicMock()
    with patch('app.services.notification_service.send_notification',return_value=[{'id':'saved'}]) as send:
        s._deliver_login_week_notice(db,USER,NOTICE)
    kwargs=send.call_args.kwargs
    assert kwargs['template_data']=={'week':1,'hp':25,'missed_days':2,'week_start':'2026-10-26','capped':False}
    assert kwargs['reference_id']==REF and kwargs['reference_type']=='login_week' and kwargs['strict']
    db.rpc.assert_called_once_with('hg_ack_login_week_notice',{'p_user_id':USER,'p_reference_id':REF})


def test_acknowledged_outcome_does_not_repeat_work():
    db=MagicMock()
    with patch('app.services.notification_service.send_notification') as send:
        s._deliver_login_week_notice(db,USER,{**NOTICE,'notified':True})
    send.assert_not_called();db.rpc.assert_not_called()


def test_monthly_cap_message_explains_zero_or_partial_award():
    _,body,_,_=render_notification_template('checkin_streak_week',{'week':1,'hp':0,'missed_days':2,'week_start':'2026-10-26','capped':True})
    assert '0 pending' in body and 'monthly pending HP cap' in body and '2 missed days' in body


def test_notice_retries_deduplicate_per_week_and_allow_later_week():
    from tests.test_notification_preferences_delivery import Db
    from app.services import notification_service as ns
    db=Db()
    with Flask(__name__).app_context(),patch.object(ns,'get_db',return_value=db),patch.object(ns,'_is_throttled',return_value=False),patch.object(ns.threading,'Thread') as dispatch:
        for ref in (REF,REF,'30303030-3030-4030-8030-303030303030'):
            ns.send_notification('user','checkin_streak_week',title='Week complete',body='25 pending HP',reference_id=ref,reference_type='login_week',channels=['push','in_app'])
    assert len(db.rows['notifications'])==4 and dispatch.call_count==2


def test_next_login_recovers_unacknowledged_notice_even_when_today_is_already_checked():
    db=MagicMock();profile=MagicMock();login=MagicMock()
    for q in (profile,login):
        for method in ('select','eq','single'):getattr(q,method).return_value=q
    profile.execute.return_value={'is_active':True,'is_fraud_flagged':False}
    login.execute.return_value={'id':'streak','current_week_start':'2026-11-02',
        'cycle_week_number':2,'week_state':{'2':'checked'},'last_week_receipt':NOTICE}
    db.table.side_effect=lambda name:profile if name=='profiles' else login
    with patch.object(s,'get_db',return_value=db),patch.object(s,'today_wat',return_value=date(2026,11,4)),patch.object(s,'_deliver_login_week_notice') as notify,patch.object(s,'_touch_last_activity'):
        outcome=s.process_login_streak(USER)
    assert outcome['action']=='same_day' and outcome['hp_awarded']==0
    notify.assert_called_once_with(db,USER,NOTICE)
    db.rpc.assert_not_called()
