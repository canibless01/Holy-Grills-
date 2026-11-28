"""A saved order is not a payment: initialize and verify its card remainder."""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from uuid import UUID
import hmac

from flask import current_app
from app.db import get_db, SupabaseError
from app.messages import MSG
from app.services import payment_service


class OrderPaymentError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal('0.01')):
            raise ValueError()
        return amount
    except (InvalidOperation, ValueError, TypeError):
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)


def card_due(order):
    total = money(order.get('total_amount'))
    wallet = money(order.get('wallet_amount_used') or 0)
    card = money(order.get('card_amount_used') or 0)
    if wallet + card != total:
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    return card


def reference_for(order):
    return order.get('payment_reference') or 'HG-ORDER-' + UUID(order['id']).hex


def authorized_order(order_id, user_id, claim_token=None):
    try:
        UUID(str(order_id))
    except (ValueError, TypeError):
        raise OrderPaymentError(MSG.ORDER_NOT_FOUND, 404)
    order = get_db().table('orders').select('*').eq('id', order_id).single().execute()
    if not order:
        raise OrderPaymentError(MSG.ORDER_NOT_FOUND, 404)
    if order.get('user_id'):
        allowed = bool(user_id) and order['user_id'] == user_id
    else:
        allowed = bool(claim_token) and bool(order.get('claim_token')) and hmac.compare_digest(str(claim_token), str(order['claim_token']))
    if not allowed:
        raise OrderPaymentError(MSG.ORDER_NOT_FOUND, 404)
    return order


def _payable(order):
    if order.get('status') in ('cancelled', 'refunded') or order.get('payment_status') in ('refunded', 'partially_refunded'):
        raise OrderPaymentError(MSG.ORDER_PAYMENT_CLOSED)
    if order.get('payment_status') != 'paid' and (order.get('status') not in ('received', 'paid') or card_due(order) <= 0):
        raise OrderPaymentError(MSG.ORDER_PAYMENT_CLOSED)


def allowed_payment_url(raw):
    try:
        url = urlparse(raw)
        return url.scheme == 'https' and not url.username and not url.password and (url.hostname == 'paystack.com' or url.hostname.endswith('.paystack.com'))
    except (AttributeError, TypeError, ValueError):
        return False


def validate_paystack_amount(expected_kobo, paid_kobo, fees):
    """
    Validate Paystack payment amount whether customer or merchant bears the fee.
    
    Rules (all in kobo integers):
    - Accept if paid == expected (merchant bears fee)
    - Accept if paid - fees == expected (customer bears fee)
    - If fees is null: accept if expected <= paid <= expected + max(15000, expected * 0.02)
    
    Returns dict with paid, fees, net if valid.
    Raises OrderPaymentError if invalid.
    """
    if not isinstance(expected_kobo, int) or expected_kobo <= 0:
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    if not isinstance(paid_kobo, int) or paid_kobo < 0:
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    
    # Convert fees to int or None
    if fees is not None:
        try:
            fees = int(fees)
            if fees < 0:
                raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
        except (TypeError, ValueError):
            raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    
    # Case 1: Merchant bears fee (paid == expected)
    if paid_kobo == expected_kobo:
        return {'paid': paid_kobo, 'fees': fees or 0, 'net': paid_kobo - (fees or 0)}
    
    # Case 2: Customer bears fee (paid - fees == expected)
    if fees is not None and paid_kobo - fees == expected_kobo:
        return {'paid': paid_kobo, 'fees': fees, 'net': expected_kobo}
    
    # Case 3: Fees unknown — accept within tolerance
    if fees is None:
        # Tolerance: max(15000 kobo = ₦150, 2% of expected)
        tolerance = max(15000, int(expected_kobo * 0.02))
        max_acceptable = expected_kobo + tolerance
        if expected_kobo <= paid_kobo <= max_acceptable:
            # Accept but fees unknown (will be re-read via verify endpoint)
            return {'paid': paid_kobo, 'fees': None, 'net': None}
    
    # Rejected
    raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)


def validate_provider_payment(order, reference, data, provider='paystack'):
    """Called only on server-verified data or authenticated provider webhooks."""
    if not isinstance(data, dict) or not reference:
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    meta = data.get('metadata' if provider == 'paystack' else 'meta')
    expected_status = 'success' if provider == 'paystack' else 'successful'
    actual_reference = data.get('reference' if provider == 'paystack' else 'tx_ref')
    if provider not in ('paystack', 'flutterwave') or data.get('status') != expected_status or str(data.get('currency', '')).upper() != 'NGN':
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    if not isinstance(meta, dict) or meta.get('type') != 'order_payment' or str(meta.get('order_id')) != str(order['id']):
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    if str(meta.get('user_id') or '') != str(order.get('user_id') or '') or str(meta.get('campus_id') or '') != str(order.get('campus_id') or ''):
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    if actual_reference != reference or (provider == 'paystack' and reference != reference_for(order)):
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    expected = card_due(order)
    # Provider amounts have different units; reject fractions of a kobo.
    amount = money(data.get('amount'))
    if provider == 'paystack':
        if amount != amount.to_integral_value():
            raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
        # Use the shared Paystack amount validation helper
        paid_kobo = int(amount)
        fees = data.get('fees')
        expected_kobo = int(expected * 100)
        result = validate_paystack_amount(expected_kobo, paid_kobo, fees)
        # Attach the amount breakdown to data so callers can store it
        data['_amount_breakdown'] = result
        return result
    if expected <= 0 or amount != expected:
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    return None


def initialize(order):
    _payable(order)
    if order.get('payment_status') == 'paid':
        return {'payment_status': 'paid'}
    if not current_app.config.get('PAYSTACK_SECRET_KEY'):
        raise OrderPaymentError(MSG.CARD_PAYMENTS_NOT_CONFIGURED, 503)
    db = get_db()
    reference = reference_for(order)
    due = card_due(order)
    row = db.table('payments').select('*').eq('reference', reference).single().execute()
    if not row:
        try:
            result = db.table('payments').insert({'order_id': order['id'], 'user_id': order.get('user_id'),
                'campus_id': order.get('campus_id'), 'provider': 'paystack', 'reference': reference,
                'amount': float(due), 'status': 'pending', 'metadata': {'type': 'order_payment'}})
            row = result[0] if isinstance(result, list) else result
        except SupabaseError as exc:
            if '23505' not in str(exc) and 'duplicate' not in str(exc).lower():
                raise
            row = db.table('payments').select('*').eq('reference', reference).single().execute()
    if not row or row.get('order_id') != order['id'] or row.get('provider') != 'paystack' or money(row.get('amount')) != due:
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID)
    metadata = row.get('metadata') or {}
    url = metadata.get('authorization_url')
    if allowed_payment_url(url):
        return {'authorization_url': url, 'reference': reference, 'card_amount_due': float(due), 'payment_status': 'pending'}
    email = order.get('guest_email')
    if order.get('user_id'):
        profile = db.table('profiles').select('email').eq('id', order['user_id']).single().execute() or {}
        email = profile.get('email')
    if not email:
        raise OrderPaymentError(MSG.ORDER_PAYMENT_EMAIL_REQUIRED)
    callback = current_app.config['FRONTEND_URL'].split(',')[0].rstrip('/') + '/order-confirmation/' + order['id'] + '?payment_return=1'
    if not order.get('user_id') and order.get('claim_token'):
        # Fragment stays out of HTTP requests/referrers; new browser contexts
        # still need proof for this specific order after payment.
        from urllib.parse import urlencode
        callback += '#' + urlencode({'claim_token': order['claim_token']})
    try:
        result = payment_service.initialize_payment(email, float(due), reference,
            metadata={'type': 'order_payment', 'order_id': order['id'], 'user_id': order.get('user_id'), 'campus_id': order.get('campus_id')},
            callback_url=callback)
    except Exception:
        # A concurrent initializer or a lost response can already have saved it.
        latest = db.table('payments').select('metadata').eq('reference', reference).single().execute() or {}
        cached = (latest.get('metadata') or {}).get('authorization_url')
        if allowed_payment_url(cached):
            return {'authorization_url': cached, 'reference': reference, 'card_amount_due': float(due), 'payment_status': 'pending'}
        raise
    url = result.get('authorization_url')
    if not allowed_payment_url(url) or result.get('reference') != reference:
        raise OrderPaymentError(MSG.ORDER_PAYMENT_INVALID, 503)
    db.table('payments').eq('reference', reference).eq('order_id', order['id']).update({'metadata': {**metadata, 'authorization_url': url}})
    return {'authorization_url': url, 'reference': reference, 'card_amount_due': float(due), 'payment_status': 'pending'}


def verify(order):
    _payable(order)
    if order.get('payment_status') == 'paid':
        return {'payment_status': 'paid'}
    if not current_app.config.get('PAYSTACK_SECRET_KEY'):
        raise OrderPaymentError(MSG.CARD_PAYMENTS_NOT_CONFIGURED, 503)
    reference = reference_for(order)
    data = payment_service.verify_payment(reference)
    if data.get('status') != 'success':
        return {'payment_status': 'pending', 'message': MSG.ORDER_PAYMENT_PENDING}
    validate_provider_payment(order, reference, data)
    from app.services.order_service import confirm_order_payment
    confirmed = confirm_order_payment(order['id'], reference, provider_response=data)
    if not confirmed or confirmed.get('payment_status') != 'paid':
        raise OrderPaymentError(MSG.ORDER_PAYMENT_UNAVAILABLE, 503)
    return {'payment_status': 'paid'}
