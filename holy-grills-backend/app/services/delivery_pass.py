"""Paid campus-wide delivery coverage; recurring charges debit the wallet only."""
from decimal import Decimal, InvalidOperation
from time import monotonic
from uuid import UUID, uuid5, NAMESPACE_URL
import requests
from flask import current_app
from app.db import get_db, SupabaseError
from app.messages import MSG
from app.services.auto_funding import _provider

CONSENT = 'delivery-pass-wallet-v1'
PUBLIC_RECEIPT = ('id', 'membership_id', 'amount_kobo', 'method', 'status', 'reference', 'checkout_url',
                  'expires_at', 'auto_renew', 'period_from', 'period_until', 'created_at', 'replayed')
ERRORS = {
    'pass_denied': ('RESOURCE_ACCESS_DENIED', 403),
    'pass_not_found': ('PASS_NOT_FOUND', 404),
    'pass_invalid': ('PASS_INVALID', 400),
    'pass_conflict': ('PASS_CONFLICT', 409),
    'pass_unavailable': ('PASS_UNAVAILABLE', 409),
    'pass_price_changed': ('PASS_PRICE_CHANGED', 409),
    'pass_already_active': ('PASS_ALREADY_ACTIVE', 409),
    'pass_payment_pending': ('PASS_PAYMENT_PENDING', 409),
    'pass_wallet_insufficient': ('PASS_WALLET_INSUFFICIENT', 409),
    'pass_renewal_unavailable': ('PASS_RENEWAL_UNAVAILABLE', 409),
    'pass_payment_mismatch': ('PASS_PAYMENT_MISMATCH', 409),
}


class PassError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def rpc(action, actor=None, receipt_id=None, data=None, *, db=None):
    try:
        return (db if db is not None else get_db()).rpc('hg_delivery_pass', {'p_actor': actor, 'p_action': action,
                           'p_id': receipt_id, 'p_data': data or {}})
    except SupabaseError as exc:
        for marker, (key, status_code) in ERRORS.items():
            if marker in str(exc):
                raise PassError(getattr(MSG, key), status_code) from exc
        raise


def public_receipt(value):
    return {key: value[key] for key in PUBLIC_RECEIPT if key in value}


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise PassError(MSG.PASS_INVALID) from None


def kobo(value):
    try:
        amount = Decimal(str(value))
        if isinstance(value, bool) or not amount.is_finite() or not 100 <= amount <= 1000000 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError()
        return int(amount * 100)
    except (ValueError, InvalidOperation, OverflowError):
        raise PassError(MSG.PASS_PRICE_INVALID) from None


def status(actor):
    value = rpc('status', actor)
    return {**value, 'card_available': bool(current_app.config.get('PAYSTACK_SECRET_KEY')),
            'consent_version': CONSENT}


def buy(actor, body):
    if not isinstance(body, dict) or set(body) - {'request_id', 'method', 'price', 'auto_renew', 'consent_version'}:
        raise PassError(MSG.PASS_INVALID)
    request_id = identifier(body.get('request_id'))
    method = body.get('method')
    renew = body.get('auto_renew', False)
    if method not in ('wallet', 'card') or not isinstance(renew, bool) or (renew and body.get('consent_version') != CONSENT):
        raise PassError(MSG.PASS_INVALID)
    if method == 'card' and not current_app.config.get('PAYSTACK_SECRET_KEY'):
        raise PassError(MSG.PASS_CARD_UNAVAILABLE, 503)
    value = rpc('buy', actor, request_id, {'method': method, 'price_kobo': kobo(body.get('price')),
                'auto_renew': renew, 'consent_version': CONSENT if renew else None,
                'ledger_reason': MSG.PASS_WALLET_REASON})
    setup_pending = False
    if value.get('created') and method == 'card':
        try:
            root = current_app.config['FRONTEND_URL'].split(',')[0].rstrip('/')
            charge = _provider('POST', '/transaction/initialize', {'email': value['authorization_email'],
                'amount': value['amount_kobo'], 'currency': 'NGN', 'reference': value['reference'],
                'callback_url': f'{root}/wallet?delivery_pass={request_id}',
                'metadata': {'type': 'delivery_pass', 'receipt_id': request_id, 'expected_amount_kobo': value['amount_kobo']}})
            url = charge.get('authorization_url')
            if charge.get('reference') != value['reference'] or not isinstance(url, str) or not url.startswith('https://checkout.paystack.com/'):
                raise PassError(MSG.PASS_SETUP_PENDING)
            value = rpc('checkout', actor, request_id, {'url': url})
        except Exception:
            # The pending intent is already durable. Never retry a money POST,
            # create another receipt or tell the customer it has been paid.
            current_app.logger.warning('Delivery pass setup unresolved for receipt %s; original reference retained.', request_id)
            setup_pending = True
    return {'receipt': public_receipt(value), 'setup_pending': setup_pending}


def confirm(charge, *, actor=None, receipt_id=None):
    reference = charge.get('reference')
    if not isinstance(reference, str) or not reference.startswith('HG-PASS-'):
        raise PassError(MSG.PASS_PAYMENT_MISMATCH, 409)
    parsed = identifier(reference[len('HG-PASS-'):])
    if receipt_id is not None and parsed != identifier(receipt_id):
        raise PassError(MSG.PASS_PAYMENT_MISMATCH, 409)
    if charge.get('status') != 'success':
        return {'pending': True}
    amount = charge.get('amount')
    fee = charge.get('fees')
    requested = charge.get('requested_amount')
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0 or charge.get('currency') != 'NGN':
        raise PassError(MSG.PASS_PAYMENT_MISMATCH, 409)
    for value in (fee, requested):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise PassError(MSG.PASS_PAYMENT_MISMATCH, 409)
    result = rpc('confirm', actor, parsed, {'reference': reference, 'amount_kobo': amount,
        'fees_kobo': fee, 'requested_amount_kobo': requested, 'currency': 'NGN',
        'ledger_reason': MSG.PASS_RECOVERY_REASON})
    return {**public_receipt(result), 'campus_id': result.get('campus_id')}


def verify(actor, receipt_id):
    receipt_id = identifier(receipt_id)
    receipt = rpc('receipt', actor, receipt_id)
    if receipt['method'] != 'card' or receipt['status'] in ('paid', 'credited', 'refunded'):
        return public_receipt(receipt)
    if not current_app.config.get('PAYSTACK_SECRET_KEY'):
        raise PassError(MSG.PASS_VERIFY_UNAVAILABLE, 503)
    from urllib.parse import quote
    try:
        charge = _provider('GET', '/transaction/verify/' + quote(receipt['reference'], safe=''))
    except (ValueError, requests.RequestException):
        raise PassError(MSG.PASS_VERIFY_UNAVAILABLE, 503) from None
    if charge.get('status') in ('failed', 'abandoned'):
        rpc('checked', receipt_id=receipt_id, data={'terminal': True})
        return {'id': receipt_id, 'status': 'failed'}
    if charge.get('status') != 'success':
        rpc('checked', receipt_id=receipt_id)
        return {**public_receipt(receipt), 'pending': True}
    return confirm(charge, actor=actor, receipt_id=receipt_id)


def benefit(actor, campus, *, db=None):
    value = rpc('benefit', actor, data={'campus_id': campus}, db=db)
    if not isinstance(value, dict):
        raise PassError(MSG.ORDER_PRICE_UNVERIFIED, 503)
    return value if value.get('id') else None


def notify_receipt(receipt_id):
    from app.services.notification_service import send_notification
    row = rpc('receipt', receipt_id=receipt_id)
    state = row.get('status')
    if state not in ('paid', 'credited', 'refunded') or row.get('notified_status') == state:
        return
    copy = {'paid': (MSG.PASS_NOTICE_ACTIVE, MSG.PASS_NOTICE_ACTIVE_BODY),
            'credited': (MSG.PASS_NOTICE_RECOVERY, MSG.PASS_NOTICE_RECOVERY_BODY),
            'refunded': (MSG.PASS_NOTICE_REFUND, MSG.PASS_NOTICE_REFUND_BODY)}
    title, body = copy[state]
    from datetime import datetime, timezone
    from app.utils.tz import WAT_OFFSET
    until = datetime.fromisoformat(row['period_until'].replace('Z', '+00:00')).astimezone(timezone(WAT_OFFSET)).strftime('%d %b %Y, %H:%M WAT') if row.get('period_until') else ''
    body = body.format(amount=f"{row['amount_kobo']/100:,.2f}", until=until)
    send_notification(row['user_id'], f'delivery_pass_{state}', title=title, body=body,
        reference_id=row['id'], reference_type='delivery_pass', action_url='/wallet?delivery_pass=manage',
        campus_id=row['campus_id'], channels=['in_app', 'push', 'email'], strict=True)
    rpc('notice_done', receipt_id=row['id'], data={'status': state})


def sweep():
    """One shared hourly scan; no external recurring charge and no per-user cron."""
    started = monotonic()
    work = rpc('scan')
    result = {'renewed': 0, 'verified': 0, 'notified': 0, 'issues': 0, 'retryable': 0}
    for row in work.get('due', []):
        if monotonic() - started > 20: break
        try:
            value = rpc('renew', receipt_id=row['id'], data={'ledger_reason': MSG.PASS_RENEWAL_REASON})
            result['renewed'] += int(value.get('status') == 'paid')
        except Exception:
            result['retryable'] += 1
    for row in work.get('pending', []):
        if monotonic() - started > 20: break
        try:
            value = verify(None, row['id'])
            result['verified'] += int(value.get('status') in ('paid', 'credited'))
        except Exception:
            rpc('checked', receipt_id=row['id'])
            result['retryable'] += 1
    for row in work.get('notices', []):
        if monotonic() - started > 20: break
        try:
            notify_receipt(row['id']); result['notified'] += 1
        except Exception:
            result['retryable'] += 1
    from app.services.notification_service import send_notification
    for row in work.get('issues', []):
        if monotonic() - started > 20: break
        try:
            ref = str(uuid5(NAMESPACE_URL, f"delivery-pass-issue:{row['id']}:{row['paid_until']}:{row['renewal_issue']}"))
            send_notification(row['user_id'], 'delivery_pass_attention', title=MSG.PASS_NOTICE_ATTENTION,
                body=MSG.PASS_NOTICE_ATTENTION_BODY, reference_id=ref, reference_type='delivery_pass',
                action_url='/wallet?delivery_pass=manage', campus_id=row['campus_id'], channels=['in_app', 'push', 'email'], strict=True)
            rpc('issue_done', receipt_id=row['id'], data={'issue': row['renewal_issue'], 'paid_until': row['paid_until']})
            result['issues'] += 1
        except Exception:
            result['retryable'] += 1
    return result
