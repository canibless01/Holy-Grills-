from copy import deepcopy
from unittest.mock import MagicMock, patch
from flask import Flask
import pytest
from app.services import guest_cart_email, notification_outbox
from app.routes.orders import orders_bp

ID='11111111-1111-4111-8111-111111111111'
ORDER='22222222-2222-4222-8222-222222222222'
TOKEN='33333333-3333-4333-8333-333333333333'

@pytest.fixture
def app():
    a=Flask(__name__);a.config.update(SECRET_KEY='test-only',FRONTEND_URL='https://holygrills.online')
    a.register_blueprint(orders_bp,url_prefix='/orders')
    return a

def payload():
    return {'kind':'guest_cart_recovery_email','cart_id':ID,'order_id':ORDER,'step':0,'deadline':'2026-11-12T15:00:00Z',
            'notification':{'user_id':None,'email':'guest@example.invalid','name':'<script>Guest</script>',
                            'type':'guest_checkout_reminder','title':'Your checkout is waiting','body':'Payment is pending'}}

def test_guest_mail_is_not_a_confirmation_and_contains_private_recovery_and_optout(app):
    db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={
        'id':ORDER,'claim_token':TOKEN,'guest_email':'guest@example.invalid'}
    with app.app_context(),patch('app.services.notification_service.get_email_provider',return_value='resend'):
        mail=guest_cart_email.prepare(db,ID,payload())
        assert mail['transactional'] is False
        assert mail['to_email']=='guest@example.invalid'
        assert 'Your order is confirmed only after payment succeeds' in mail['html_body']
        assert 'order_number='+ORDER in mail['html_body'] and 'claim_token='+TOKEN in mail['html_body']
        assert '<script>Guest</script>' not in mail['html_body']
        assert 'Unsubscribe from these emails' in mail['html_body']
        assert mail['headers']['List-Unsubscribe-Post']=='List-Unsubscribe=One-Click'
        assert guest_cart_email.read_token(guest_cart_email.unsubscribe_token(ID))==ID

def test_changed_email_or_missing_private_token_prevents_preparation(app):
    db=MagicMock();query=db.table.return_value.select.return_value.eq.return_value.single.return_value
    with app.app_context():
        for order in [{'id':ORDER,'guest_email':'guest@example.invalid'}, {'id':ORDER,'guest_email':'changed@example.invalid','claim_token':TOKEN}]:
            query.execute.return_value=order
            assert guest_cart_email.prepare(db,ID,payload()) is None

def test_guest_dispatch_rechecks_database_and_never_looks_up_a_synthetic_profile(app):
    db=MagicMock();claim={'state':'claimed','token':TOKEN,'key':ID,'channel':'email','payload':payload()}
    calls=[]
    def rpc(name,params):
        calls.append(name)
        return deepcopy(claim) if name=='hg_claim_notification_dispatch_v2' else True
    db.rpc.side_effect=rpc
    prepared={'to_email':'guest@example.invalid','provider':'resend','transactional':False}
    with app.app_context(),patch.object(notification_outbox,'get_db',return_value=db),patch.object(guest_cart_email,'prepare',return_value=prepared),patch('app.services.notification_service._deliver_email_attempt',return_value={'state':'accepted'}) as send:
        assert notification_outbox.dispatch_notification(ID)['state']=='accepted'
    assert 'hg_guest_cart_recovery_valid' in calls and 'hg_begin_guest_cart_dispatch' in calls
    db.table.assert_not_called();send.assert_called_once_with(prepared)

@pytest.mark.parametrize('failure',['hg_guest_cart_recovery_valid','hg_begin_guest_cart_dispatch'])
def test_recovered_opted_out_or_paid_guest_does_not_reach_provider(app,failure):
    db=MagicMock();claim={'state':'claimed','token':TOKEN,'key':ID,'channel':'email','payload':payload()}
    db.rpc.side_effect=lambda n,p:deepcopy(claim) if n=='hg_claim_notification_dispatch_v2' else n!=failure
    with app.app_context(),patch.object(notification_outbox,'get_db',return_value=db),patch.object(guest_cart_email,'prepare',return_value={'provider':'resend'}),patch('app.services.notification_service._deliver_email_attempt') as send:
        assert notification_outbox.dispatch_notification(ID)['state'] in ('cancelled','lease_lost')
        send.assert_not_called()

def test_unsubscribe_requires_signed_delivery_and_get_is_not_a_write(app):
    with app.app_context():token=guest_cart_email.unsubscribe_token(ID)
    with patch('app.routes.orders.get_db') as db:
        client=app.test_client()
        response=client.get('/orders/guest-reminders/unsubscribe',query_string={'token':token})
        assert response.status_code==200 and b'Stop checkout reminders' in response.data
        assert response.headers['Cache-Control']=='private, no-store';db.assert_not_called()
        assert client.post('/orders/guest-reminders/unsubscribe',query_string={'token':token+'tampered'}).status_code==400
        db.assert_not_called()
        db.return_value.rpc.return_value=True
        assert client.post('/orders/guest-reminders/unsubscribe',query_string={'token':token}).status_code==200
        db.return_value.rpc.assert_called_once_with('hg_unsubscribe_guest_cart_email',{'p_id':ID})

def test_interrupted_guest_provider_send_is_uncertain_not_automatically_retried(app):
    db=MagicMock();claim={'state':'claimed','token':TOKEN,'key':ID,'channel':'email','payload':payload()}
    db.rpc.side_effect=lambda n,p:deepcopy(claim) if n=='hg_claim_notification_dispatch_v2' else True
    with app.app_context(),patch.object(notification_outbox,'get_db',return_value=db),patch.object(guest_cart_email,'prepare',return_value={'provider':'resend'}),patch('app.services.notification_service._deliver_email_attempt',side_effect=TimeoutError):
        assert notification_outbox.dispatch_notification(ID)['state']=='uncertain'


def test_admin_guest_nudge_uses_existing_campus_check_and_same_due_capture(app):
    from flask import g
    from app.routes import admin
    cart={'id':ID,'campus_id':ORDER,'user_id':None,'guest_email':'guest@example.invalid','is_recovered':False}
    db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value=cart
    with app.test_request_context(method='POST'),patch.object(admin,'get_user_client',return_value=db),patch.object(admin,'assert_can_modify') as scope,patch('app.services.cart_recovery.nudge',return_value={'saved':True}) as capture,patch.object(admin,'_audit'):
        g.user_id=TOKEN
        _,status=admin.nudge_cart.__wrapped__(ID)
        assert status==200
        scope.assert_called_once_with(ORDER);capture.assert_called_once_with(cart)
