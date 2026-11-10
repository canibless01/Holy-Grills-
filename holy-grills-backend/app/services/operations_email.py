"""Campus operator mail. SQL captures intent; one claimed send, no blind timeout retry."""
from decimal import Decimal
from app.db import get_db
from app.utils.email import _build_html, send_email_routed
from app.services.notification_service import get_email_provider
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _amount(value):
    return f'₦{Decimal(str(value or 0)):,.2f}'


def _customer(order):
    address = order.get('delivery_address_snapshot') or {}
    profile = order.get('profiles') or {}
    return [f"Customer: {profile.get('full_name') or order.get('guest_name') or 'Guest'}",
            f"Phone: {address.get('contact_phone') or profile.get('phone') or order.get('guest_phone') or 'Not supplied'}",
            f"Email: {profile.get('email') or order.get('guest_email') or 'Not supplied'}",
            'Location: ' + ', '.join(str(address[k]) for k in ('location_name', 'line1', 'landmark') if address.get(k))]


def _order(db, order_id):
    return db.table('reporting_orders').select('*,profiles(full_name,email,phone),order_items(name_snapshot,quantity,order_addon_selections(name_snapshot,quantity))').eq('id', order_id).single().execute()


def _order_lines(order):
    lines = _customer(order)
    for item in order.get('order_items') or []:
        lines.append(f"{item.get('quantity', 1)} × {item.get('name_snapshot') or 'Meal'}")
        for extra in item.get('order_addon_selections') or []:
            lines.append(f"  + {extra.get('quantity', 1)} × {extra.get('name_snapshot') or 'Extra'}")
    lines.append('Order total: ' + _amount(order.get('total_amount')))
    return lines


def render(db, row):
    campus = db.table('campuses').select('name').eq('id', row['campus_id']).single().execute() or {}
    prefix = 'Holy Grills · ' + (campus.get('name') or 'Campus')
    kind = row['kind']
    payload = row.get('payload') or {}
    if kind in ('daily_report', 'weekly_report'):
        labels = [('signups', 'New accounts'), ('paid_orders', 'Paid orders'),
                  ('order_value', 'Order value'), ('refunds_on_orders', 'Refunds on these orders'),
                  ('wallet_funded', 'Wallet funding'), ('auto_funding_setups', 'New confirmed auto-funding setups'),
                  ('auto_funded', 'Automatic funding received (included in wallet funding)'),
                  ('event_tickets', 'Confirmed event admissions'), ('marketplace_purchases', 'Marketplace purchases'),
                  ('abandoned_carts', 'Abandoned carts recorded'), ('recovered_carts', 'Carts recovered with payment')]
        money = {'order_value', 'refunds_on_orders', 'wallet_funded', 'auto_funded'}
        lines = [f"Period: {payload['from']} to {payload['to']} (Nigeria time)"]
        lines += [f"{label}: {_amount(payload[key]) if key in money else payload[key]}" for key, label in labels]
        subject = prefix + (' · Daily report' if kind == 'daily_report' else ' · Weekly report')
    elif kind == 'paid_order':
        order = _order(db, payload.get('order_id'))
        if not order or order.get('payment_status') not in ('paid', 'partially_refunded') or order.get('status') in ('cancelled', 'refunded'):
            return None
        subject = prefix + ' · Paid order #' + order['id'][:8].upper()
        lines = _order_lines(order)
    else:
        cart = db.table('reporting_abandoned_carts').select('*,profiles(full_name,email,phone)').eq('id', payload.get('cart_id')).single().execute()
        if not cart or cart.get('is_recovered'):
            return None
        profile = cart.get('profiles') or {}
        if cart.get('user_id'):
            owner = db.table('profiles').select('is_active,role').eq('id', cart['user_id']).single().execute()
            if not owner or owner.get('role') == 'super_admin' or not owner.get('is_active'):
                return None
            latest = db.table('cart_items').select('updated_at').eq('user_id', cart['user_id']).eq('campus_id', row['campus_id']).order('updated_at', ascending=False).limit(1).execute() or []
            if latest and latest[0]['updated_at'] > cart['last_active_at']:
                return None
        snapshot = cart.get('cart_payload') or {}
        pending = _order(db, snapshot['pending_order_id']) if snapshot.get('pending_order_id') else None
        if not pending and cart.get('user_id') and not latest:
            return None
        if pending:
            if pending.get('payment_status') != 'pending' or pending.get('status') in ('cancelled', 'refunded'):
                return None
            lines = _order_lines(pending)
        else:
            lines = [f"Customer: {profile.get('full_name') or 'Guest'}",
                     f"Phone: {profile.get('phone') or cart.get('guest_phone') or 'Not supplied'}",
                     f"Email: {profile.get('email') or cart.get('guest_email') or 'Not supplied'}"]
            items = snapshot.get('items') or []
            lines += [f"{item.get('quantity', 1)} × {item.get('name') or item.get('name_snapshot') or 'Meal'}" for item in items]
            lines.append('Final price and delivery location: available after checkout details are entered.')
        subject = prefix + ' · Cart awaiting payment'
        lines.append('Please check the current cart/payment status before contacting the customer.')
    lines += ['', 'Super-admin customer tests are excluded.', 'Manage: https://holygrills.online/admin']
    return subject, _build_html('Campus team', '\n'.join(lines))


def dispatch_pending(db=None):
    db = db or get_db()
    rows = db.rpc('hg_operations_email_outbox', {'p_action': 'claim'}) or []
    result = {'accepted': 0, 'failed': 0, 'uncertain': 0, 'cancelled': 0}
    for row in rows:
        params = {'p_id': row['id'], 'p_token': row['token']}
        # Prepare before marking "sending": a crash during reads can safely be reclaimed.
        try:
            message = render(db, row)
        except Exception:
            logger.exception('Operations email could not be prepared: %s', row['id'])
            continue
        if not db.rpc('hg_operations_email_outbox', {'p_action': 'begin', **params}):
            continue
        receipt = {}
        state = 'cancelled'
        if message:
            try:
                accepted = send_email_routed(row['recipient'], 'Campus team', *message,
                                             provider=get_email_provider(), receipt=receipt, transactional=True)
                state = 'accepted' if accepted else ('failed' if receipt.get('state') in ('not_configured', 'skipped') else 'uncertain')
            except Exception as exc:
                state = 'uncertain'
                receipt = {'error': type(exc).__name__}
        db.rpc('hg_operations_email_outbox', {'p_action': 'finish', **params,
                                             'p_data': {'state': state, 'receipt': receipt}})
        result[state] += 1
    return result


def capture_and_dispatch():
    db = get_db()
    captured = db.rpc('hg_capture_operations_emails')
    return {'capture': captured, 'mail': dispatch_pending(db)}
