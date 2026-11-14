from datetime import datetime,timezone
from unittest.mock import MagicMock,patch
from flask import Flask
import pytest
from app.services import cart_recovery,operations_email
from app.services.notification_service import get_notification_channels

APP=Flask(__name__)
C='11111111-1111-4111-8111-111111111111'

def calendar(rows=None,overrides=None,hours=None):
    obj=object.__new__(cart_recovery.CalendarSnapshot)
    obj.rows={'ordering_windows':rows or [],'operating_hour_overrides':overrides or [],'operating_hours':hours or []}
    return obj

def cutoff(active,rows=None,overrides=None,hours=None):
    with APP.app_context():
        return cart_recovery.deadline({'last_active_at':active,'campus_id':C},calendar(rows,overrides,hours))

@pytest.mark.parametrize('active,expected',[
 ('2026-11-10T09:00:00+01:00','2026-11-10T16:00:00+01:00'),
 ('2026-11-10T16:01:00+01:00','2026-11-11T16:00:00+01:00'),
])
def test_reminder_stops_at_configured_first_preparation_cutoff(active,expected):
    rows=[{'campus_id':C,'weekday':day,'date':None,'opens_at':'00:00','closes_at':'16:00','is_closed':False} for day in range(7)]
    assert cutoff(active,rows)==expected

def test_sunday_closed_and_monday_open_use_same_ordering_override_rules():
    rows=[{'campus_id':C,'weekday':day,'date':None,'opens_at':'00:00','closes_at':'16:00','is_closed':day==6} for day in range(7)]
    assert cutoff('2026-11-08T09:00:00+01:00',rows)=='2026-11-09T16:00:00+01:00'
    override=[{'campus_id':C,'date':'2026-11-09','is_closed':False,'opens_at':'09:00','closes_at':'14:30'}]
    assert cutoff('2026-11-08T09:00:00+01:00',rows,override)=='2026-11-09T14:30:00+01:00'

def test_date_window_has_precedence_and_overnight_close_uses_next_day():
    rows=[{'campus_id':C,'date':'2026-11-10','opens_at':'18:00','closes_at':'02:00','is_closed':False}]
    assert cutoff('2026-11-10T19:00:00+01:00',rows)=='2026-11-11T02:00:00+01:00'

def test_email_does_not_depend_on_push_subscription():
    from app.services.notification_preferences import permitted_channels
    channels=get_notification_channels('abandoned_cart')
    assert 'email' in channels
    assert permitted_channels('abandoned_cart',channels,{'push_enabled':False,'email_enabled':True})==['in_app','email']
    assert permitted_channels('abandoned_cart',channels,{'promotions':False})==[]

def test_queued_reminder_is_cancelled_at_deadline_before_any_customer_lookup():
    db=MagicMock();snapshot={'metadata':{'cart_recovery':{'cart_id':'cart','deadline':'2026-11-10T15:00:00Z'}}}
    assert not cart_recovery.notification_still_valid(db,snapshot,datetime(2026,11,10,15,0,tzinfo=timezone.utc))
    db.table.assert_not_called()

def test_capture_survives_queue_wakeup_failure_without_provider_send():
    db=MagicMock();db.rpc.return_value={'saved':True,'notification_ids':['saved-id']}
    with APP.app_context(),patch.object(cart_recovery,'deadline',return_value='2026-11-10T16:00:00+01:00'),patch('app.tasks.scheduled.dispatch_cart_recovery.delay',side_effect=OSError('redis down')):
        result=cart_recovery.capture_cart(db,{'id':'cart','recovery_step':0},None,{'p_initial':30,'p_repeat':1440,'p_hours':48})
    assert result['saved']
    db.rpc.assert_called_once()

@pytest.mark.parametrize('accepted,receipt,state',[(True,{'state':'accepted'},'accepted'),(False,{'state':'unknown'},'uncertain'),(False,{'state':'not_configured'},'failed')])
def test_operator_outbox_preserves_actual_provider_outcomes_without_retries(accepted,receipt,state):
    db=MagicMock();row={'id':'mail','token':'owned','recipient':'ops@example.invalid'}
    db.rpc.side_effect=[[row],row,{'saved':True}]
    def send(*args,**kwargs):kwargs['receipt'].update(receipt);return accepted
    with patch.object(operations_email,'render',return_value=('Subject','HTML')),patch.object(operations_email,'send_email_routed',side_effect=send) as transport,patch.object(operations_email,'get_email_provider',return_value='resend'):
        result=operations_email.dispatch_pending(db)
    assert result[state]==1
    assert transport.call_count==1
    assert db.rpc.call_args.kwargs=={}
    assert db.rpc.call_args.args[1]['p_data']['state']==state

def test_removed_operator_recipient_prevents_transport():
    db=MagicMock();db.rpc.side_effect=[[{'id':'m','token':'t'}],None]
    with patch.object(operations_email,'render',return_value=('Subject','HTML')),patch.object(operations_email,'send_email_routed') as transport:
        operations_email.dispatch_pending(db)
    transport.assert_not_called()

def test_customer_contact_html_is_escaped_and_digest_has_only_core_figures():
    db=MagicMock();q=db.table.return_value
    for method in ('select','eq','single'):getattr(q,method).return_value=q
    q.execute.return_value={'name':'FUTA'}
    keys=('signups','paid_orders','order_value','refunds_on_orders','wallet_funded','auto_funding_setups','auto_funded','event_tickets','marketplace_purchases','abandoned_carts','recovered_carts')
    payload={k:0 for k in keys};payload.update({'from':'2026-11-09','to':'2026-11-09'})
    subject,html=operations_email.render(db,{'campus_id':C,'kind':'daily_report','payload':payload})
    assert 'Daily report' in subject and 'New accounts: 0' in html and 'Phone:' not in html
    assert 'Visitors:' not in html
    fake={'id':'order','payment_status':'paid','profiles':{'full_name':'<script>bad</script>'},'total_amount':123,'order_items':[]}
    with patch.object(operations_email,'_order',return_value=fake):
        _,html=operations_email.render(db,{'campus_id':C,'kind':'paid_order','payload':{'order_id':'order'}})
    assert '<script>bad' not in html and '&lt;script&gt;' in html


def test_daily_report_renders_precise_evening_window_without_internal_test_note():
    db=MagicMock();query=db.table.return_value
    for method in ('select','eq','single'):getattr(query,method).return_value=query
    query.execute.return_value={'name':'FUTA'}
    payload={key:0 for key in ('signups','paid_orders','order_value','refunds_on_orders','wallet_funded','auto_funding_setups','auto_funded','event_tickets','marketplace_purchases','abandoned_carts','recovered_carts')}
    payload.update({'from':'2026-11-09','to':'2026-11-10','period_start':'2026-11-09T20:00:00+00:00','period_end':'2026-11-10T20:00:00+00:00'})
    _,html=operations_email.render(db,{'campus_id':C,'kind':'daily_report','payload':payload})
    assert '09 Nov 2026, 09:00 PM' in html and '10 Nov 2026, 09:00 PM' in html
    assert 'Super-admin' not in html and 'customer tests' not in html


def test_abandoned_cart_mail_contains_contact_details_without_repeated_checkout_warning():
    db=MagicMock();query=db.table.return_value
    for method in ('select','eq','single'):getattr(query,method).return_value=query
    query.execute.side_effect=[{'name':'FUTA'}, {'id':'cart','user_id':None,'is_recovered':False,'guest_email':'guest@example.invalid','cart_payload':{'pending_order_id':'order'}}]
    order={'id':'order','guest_name':'Student','guest_phone':'08012345678','guest_email':'guest@example.invalid','status':'received','payment_status':'pending','total_amount':500,'order_items':[]}
    with patch.object(operations_email,'_order',return_value=order):
        _,html=operations_email.render(db,{'campus_id':C,'kind':'abandoned_cart','payload':{'cart_id':'cart'}})
    assert '08012345678' in html and 'guest@example.invalid' in html
    assert 'before contacting' not in html and 'Super-admin' not in html
