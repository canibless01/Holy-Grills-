"""Guest checkout reminders share the existing durable notification transport."""
from urllib.parse import urlencode
from uuid import UUID
from flask import current_app
from itsdangerous import URLSafeSerializer, BadData


def _serializer():
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='hg-guest-cart-unsubscribe-v1')


def unsubscribe_token(delivery_id):
    return _serializer().dumps(str(UUID(delivery_id)))


def read_token(token):
    try:
        value = _serializer().loads(token)
        return str(UUID(value))
    except (BadData, ValueError, TypeError, AttributeError):
        return None


def eligible(db, payload):
    return db.rpc('hg_guest_cart_recovery_valid', {
        'p_cart': payload['cart_id'], 'p_step': payload['step'],
        'p_deadline': payload['deadline'], 'p_email': payload['notification']['email'],
        'p_order': payload['order_id'],
    }) is True


def prepare(db, delivery_id, payload):
    from app.utils.email import _build_html, public_api_base
    from app.services.notification_service import get_email_provider
    order = db.table('orders').select('id,claim_token,guest_email').eq('id', payload['order_id']).single().execute() or {}
    person = payload['notification']
    if not order.get('claim_token') or str(order.get('guest_email') or '').strip().lower() != person['email']:
        return None
    frontend = (current_app.config.get('FRONTEND_URL') or 'https://holygrills.online').split(',')[0].strip().rstrip('/')
    resume = frontend + '/track-orders?' + urlencode({'order_number': order['id'], 'claim_token': order['claim_token']})
    unsubscribe = public_api_base() + '/orders/guest-reminders/unsubscribe?' + urlencode({'token': unsubscribe_token(delivery_id)})
    body = "Your checkout is still waiting for payment. If you'd like to carry on, open it below. Your order is confirmed only after payment succeeds.\n\nChanged your mind? You can leave it here, or stop these checkout reminders below."
    html = _build_html(person.get('name') or 'there', body,
        cta_buttons=[{'label': 'Continue checkout', 'url': resume, 'primary': True}],
        unsubscribe_url=unsubscribe, skip_thank_you=True)
    return {'to_email': person['email'], 'to_name': person.get('name') or 'there',
            'subject': 'Your Holy Grills checkout is waiting', 'html_body': html,
            'provider': get_email_provider(scope='transactional'), 'transactional': False,
            'headers': {'List-Unsubscribe': '<' + unsubscribe + '>', 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}}
