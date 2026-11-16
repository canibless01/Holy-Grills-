"""Transactional delivery-day email, including private guest tracking links."""
from urllib.parse import urlencode
from flask import current_app


def valid(db, snapshot):
    meta = snapshot.get('metadata') or {}
    return db.rpc('hg_scheduled_order_reminder_valid', {
        'p_order': meta['order_id'], 'p_user': snapshot.get('user_id'),
        'p_day': meta['scheduled_date'], 'p_email': snapshot.get('email'),
    }) is True


def prepare(db, snapshot):
    from app.utils.email import _build_html
    from app.services.notification_service import get_email_provider
    order = db.table('orders').select('id,user_id,claim_token,guest_email').eq('id', snapshot['metadata']['order_id']).single().execute() or {}
    if not order or order.get('user_id') != snapshot.get('user_id'):
        return None
    frontend = (current_app.config.get('FRONTEND_URL') or 'https://holygrills.online').split(',')[0].strip().rstrip('/')
    if order.get('user_id'):
        tracking = frontend + '/orders/' + order['id']
    else:
        if not order.get('claim_token') or str(order.get('guest_email') or '').strip().lower() != snapshot.get('email'):
            return None
        tracking = frontend + '/track-orders?' + urlencode({'order_number': order['id'], 'claim_token': order['claim_token']})
    return {'to_email': snapshot['email'], 'to_name': snapshot.get('name') or 'there',
            'subject': snapshot['title'], 'html_body': _build_html(snapshot.get('name') or 'there', snapshot['body'],
                cta_buttons=[{'label': 'Track your order', 'url': tracking, 'primary': True}], skip_thank_you=True),
            'provider': get_email_provider(scope='transactional'), 'transactional': True}
