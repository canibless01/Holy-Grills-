from copy import deepcopy
from unittest.mock import MagicMock, patch
from flask import Flask
import pytest
from app.services import scheduled_order_reminders as reminders, notification_outbox as outbox

ORDER='11111111-1111-4111-8111-111111111111';NOTICE='22222222-2222-4222-8222-222222222222'

def snapshot(user=None):
    return {'user_id':user,'email':'guest@example.invalid','name':'Guest','type':'scheduled_order_reminder','title':'Your order is coming today','body':'Keep your phone available.', 'metadata':{'order_id':ORDER,'scheduled_date':'2026-11-13'}}


def test_guest_tracking_link_is_private_and_email_is_transactional():
    db=MagicMock();q=db.table.return_value
    for method in ('select','eq','single'):getattr(q,method).return_value=q
    q.execute.return_value={'id':ORDER,'user_id':None,'guest_email':'guest@example.invalid','claim_token':'private-proof'}
    app=Flask(__name__);app.config['FRONTEND_URL']='https://holygrills.online'
    with app.app_context(),patch('app.services.notification_service.get_email_provider',return_value='resend'):
        result=reminders.prepare(db,snapshot())
    assert result['transactional'] is True and 'claim_token=private-proof' in result['html_body'] and 'order_number='+ORDER in result['html_body']
    q.execute.return_value['guest_email']='different@example.invalid'
    with app.app_context():assert reminders.prepare(db,snapshot()) is None


@pytest.mark.parametrize('eligible',[True,False])
def test_guest_reminder_checks_current_order_before_provider(eligible):
    db=MagicMock();claim={'state':'claimed','token':NOTICE,'key':NOTICE,'channel':'email','payload':{'notification':snapshot()}}
    db.rpc.side_effect=lambda name,args:deepcopy(claim) if name=='hg_claim_notification_dispatch_v2' else eligible if name=='hg_scheduled_order_reminder_valid' else True
    prepared={'provider':'resend','transactional':True}
    with Flask(__name__).app_context(),patch.object(outbox,'get_db',return_value=db),patch.object(reminders,'prepare',return_value=prepared),patch('app.services.notification_service._deliver_email_attempt',return_value={'state':'accepted'}) as send:
        result=outbox.dispatch_notification(NOTICE)
    assert result['state']==('accepted' if eligible else 'cancelled')
    assert send.call_count==int(eligible);db.table.assert_not_called()
