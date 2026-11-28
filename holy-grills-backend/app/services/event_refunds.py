"""Ticket refunds: one financial intent; never repeat an uncertain gateway POST."""
from decimal import Decimal, InvalidOperation
from time import monotonic
from flask import current_app
from app.db import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _validate_charge(charge, claim):
    expected = int(Decimal(str(claim['amount'])) * 100)
    if (not isinstance(charge, dict) or charge.get('reference') != claim['reference']
            or charge.get('status') not in (('success','reversed') if claim.get('provider_refund_id') else ('success',)) or charge.get('currency') != 'NGN'
            or not charge.get('id') or int(charge.get('amount') or 0) < expected):
        raise ValueError('Original payment could not be verified')
    return expected


def _refund_result(response, claim, charge, *, lookup=False):
    """Confirm amount, currency and original transaction before accepting an ID."""
    body = response.json()
    data = body.get('data') if isinstance(body, dict) else None
    if response.status_code not in (200, 201) or not isinstance(data, dict) or body.get('status') is not True:
        return {'state': 'uncertain' if response.status_code >= 500 or response.status_code == 409 else 'failed',
                'error': 'gateway_request_not_accepted'}
    transaction = data.get('transaction')
    transaction_id = transaction.get('id') if isinstance(transaction, dict) else transaction
    transaction_reference = transaction.get('reference') if isinstance(transaction, dict) else None
    expected = int(Decimal(str(claim['amount'])) * 100)
    provider_id = str(data.get('id') or '')
    try:
        reported_amount = Decimal(str(data.get('amount')))
    except (InvalidOperation, ValueError, TypeError):
        return {'state':'uncertain','error':'gateway_refund_receipt_invalid'}
    if (not provider_id.isdigit() or str(transaction_id) != str(charge['id'])
            or (transaction_reference is not None and transaction_reference != claim['reference'])
            or data.get('currency') != 'NGN' or reported_amount != expected
            or (lookup and provider_id != str(claim['provider_refund_id']))):
        return {'state': 'uncertain', 'error': 'gateway_refund_receipt_mismatch'}
    status = data.get('status')
    if status == 'processed':
        state = 'completed'
    elif status in ('pending', 'processing'):
        state = 'processing'
    else:
        state = 'failed'
    return {'state': state, 'provider_id': provider_id,
            'error': None if state in ('completed', 'processing') else 'gateway_refund_' + str(status)[:80]}


def _member_notice(db, claim):
    if not claim.get('notified') and claim.get('user_id'):
        from app.services.notification_service import send_notification
        parts=[]
        if Decimal(str(claim['amount']))>0:
            parts.append(f"₦{Decimal(str(claim['amount'])):,.2f} has been returned to your Holy Grills wallet.")
        if int(claim['hp_amount'])>0:
            parts.append(f"{int(claim['hp_amount'])} spent HP has also been returned.")
        send_notification(claim['user_id'], 'event_ticket_refunded', title='Your event ticket refund',
            body=" ".join(parts) or "Your event ticket has been cancelled. No money or HP was charged for it.",
            reference_id=claim['id'], reference_type='event_ticket_refund',
            action_url='/wallet', channels=['email','push','in_app'], strict=True)
        db.rpc('hg_ack_event_refund_notice', {'p_id':claim['id']})
    return {'state':'completed'}


def process_event_refund(refund_id):
    db = get_db()
    claim = db.rpc('hg_claim_event_refund', {'p_id':refund_id})
    if not isinstance(claim, dict):
        return {'state':'unavailable'}
    if claim.get('state') == 'completed':
        return _member_notice(db, claim)
    if claim.get('state') not in ('claimed', 'checking'):
        return claim
    started = False
    provider_id = claim.get('provider_refund_id')
    def finish(outcome):
        result = db.rpc('hg_finish_event_refund', {'p_id':refund_id,'p_token':claim['token'],
            'p_state':outcome['state'],'p_provider_id':outcome.get('provider_id') or provider_id,'p_error':outcome.get('error')})
        return outcome if result is True else {'state':'lease_lost'}
    try:
        from app.services import payment_service as payment
        if not current_app.config.get('PAYSTACK_SECRET_KEY'):
            return finish({'state':'processing' if provider_id else 'queued','error':'gateway_not_configured'})
        charge = payment.verify_payment(claim['reference'])
        amount_kobo = _validate_charge(charge, claim)
        if provider_id:
            response = payment._paystack_get(f'{payment.PAYSTACK_BASE}/refund/{provider_id}', headers=payment._paystack_headers())
        else:
            if db.rpc('hg_begin_event_refund', {'p_id':refund_id,'p_token':claim['token']}) is not True:
                return {'state':'lease_lost'}
            started = True
            # Deliberately bypass the generic retry decorator for this money POST.
            response = payment.http_requests.post(f'{payment.PAYSTACK_BASE}/refund', headers=payment._paystack_headers(),
                json={'transaction':claim['reference'],'amount':amount_kobo,'currency':'NGN',
                      'reference':'hgticket_' + str(refund_id).replace('-',''),
                      'merchant_note':'Holy Grills ticket refund ' + str(refund_id)}, timeout=15)
        outcome = _refund_result(response, claim, charge, lookup=bool(provider_id))
        provider_id = outcome.get('provider_id') or provider_id
        return finish(outcome)
    except Exception as exc:
        logger.warning('Ticket refund %s incomplete: %s', refund_id, type(exc).__name__)
        outcome = {'state':'processing' if provider_id else ('uncertain' if started else 'queued'), 'error':type(exc).__name__}
        try:
            return finish(outcome)
        except Exception:
            # Expired sending leases become uncertain; pre-handoff/GET leases recover.
            return outcome


def recover_due_event_refunds(limit=10):
    try:
        ids = get_db().rpc('hg_due_event_refunds', {'p_limit':limit})
        if not isinstance(ids, list):
            raise RuntimeError('Invalid refund recovery result')
        result = {'due':len(ids),'checked':0}; deadline = monotonic() + 40
        for refund_id in ids:
            if monotonic() >= deadline:
                break
            try:
                outcome = process_event_refund(refund_id)
                state = str(outcome.get('state') or 'unknown')
            except Exception as exc:
                logger.warning('Refund recovery deferred: %s',type(exc).__name__)
                state = 'deferred'
            result['checked'] += 1; result[state] = result.get(state,0)+1
        return result
    except Exception as exc:
        logger.warning('Refund scan unavailable: %s',type(exc).__name__)
        return {'error':'event_refund_recovery_unavailable'}


def wake_event_refund(refund_id):
    """Immediate best-effort wake; the durable scan recovers a lost thread."""
    import threading
    app = current_app._get_current_object()
    def run():
        with app.app_context():
            try:
                process_event_refund(refund_id)
            except Exception as exc:
                logger.warning('Immediate ticket refund wake deferred: %s',type(exc).__name__)
    threading.Thread(target=run,daemon=True).start()
