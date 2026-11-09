"""Same-campus internal transfers. No Paystack or top-up reward calls."""
from decimal import Decimal, InvalidOperation
from time import monotonic
from uuid import UUID
import re
from app.db import get_db, SupabaseError
from app.utils.logger import get_logger
from app.utils.validators import normalize_email

logger = get_logger(__name__)
ERRORS = {
    'account_unavailable': ('Your account is unavailable for transfers.', 403),
    'campus_required': ('Your profile needs a campus before you can transfer money.', 400),
    'transfers_paused': ('Wallet transfers are currently paused.', 403),
    'invalid_recipient_code': ('Enter a valid referral code from your friend’s Referrals page.', 400),
    'invalid_recipient_identifier': ('Enter one complete email address, phone number or referral code.', 400),
    'recipient_ambiguous': ('These details match more than one active account on your campus. Use their email address or referral code instead.', 400),
    'recipient_unavailable': ('No active same-campus account matches those details. Check them or try another lookup option.', 400),
    'self_transfer': ('You cannot transfer wallet money to yourself.', 400),
    'invalid_transfer': ('Enter a valid transfer amount and recipient.', 400),
    'transfer_amount_out_of_range': ('The amount is outside the current transfer limits. Refresh and review it.', 400),
    'transfer_daily_limit': ('This transfer exceeds your remaining daily allowance.', 400),
    'insufficient_wallet_balance': ('Your wallet does not have enough money for this transfer.', 400),
    'wallet_unavailable': ('One of the wallets is unavailable. No money was transferred.', 400),
    'transfer_configuration_unavailable': ('Transfer settings are unavailable. Please try again later.', 503),
    'transfer_not_found': ('This transfer was not found for your account.', 404),
    'transfer_intent_conflict': ('This transfer reference already belongs to different details. Check its receipt.', 409),
}


class TransferError(ValueError):
    def __init__(self, code):
        self.code = code
        self.status = ERRORS.get(code, ('Transfer unavailable.', 503))[1]
        super().__init__(ERRORS.get(code, ('Transfer unavailable.', 503))[0])


def rpc(action, actor=None, transfer_id=None, data=None):
    try:
        return get_db().rpc('hg_wallet_transfer', {'p_action': action, 'p_actor': actor,
            'p_id': transfer_id, 'p_data': data or {}})
    except SupabaseError as exc:
        message = (exc.details or {}).get('message') or str(exc)
        if message in ERRORS:
            raise TransferError(message) from None
        raise


def code(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,80}', value.strip()):
        raise TransferError('invalid_recipient_code')
    return value.strip().upper()


def recipient_lookup(args):
    kinds = [kind for kind in ('code', 'email', 'phone') if kind in args]
    if len(kinds) != 1 or (hasattr(args, 'getlist') and len(args.getlist(kinds[0])) != 1):
        raise TransferError('invalid_recipient_identifier')
    kind = kinds[0]
    value = args[kind]
    if kind == 'code':
        value = code(value)
    elif kind == 'email':
        value = normalize_email(value)
        if not value:
            raise TransferError('invalid_recipient_identifier')
    else:
        if not isinstance(value, str) or not re.fullmatch(r'\+?[0-9() .-]{7,40}', value.strip()):
            raise TransferError('invalid_recipient_identifier')
        value = re.sub(r'[+() .-]', '', value.strip())
        if len(value) == 14 and value.startswith('2340'):
            value = '234' + value[-10:]
        elif len(value) == 11 and value.startswith('0'):
            value = '234' + value[1:]
        elif len(value) == 10:
            value = '234' + value
        if not re.fullmatch(r'[1-9][0-9]{7,14}', value):
            raise TransferError('invalid_recipient_identifier')
    return {'lookup_type': kind, 'value': value}


def intent(body):
    try:
        if not isinstance(body, dict) or isinstance(body.get('amount'), bool):
            raise ValueError()
        transfer_id = str(UUID(str(body.get('request_id', ''))))
        recipient_id = str(UUID(str(body.get('recipient_id', ''))))
        amount = Decimal(str(body.get('amount')))
        if not amount.is_finite() or amount <= 0 or amount > 1000000000 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError()
        note = body.get('note', '')
        if not isinstance(note, str) or len(note.strip()) > 200:
            raise ValueError()
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        raise TransferError('invalid_transfer') from None
    return transfer_id, {'recipient_id': recipient_id, 'recipient_code': code(body.get('recipient_code')),
                         'amount_kobo': int(amount * 100), 'note': note.strip()}


def dispatch_receipt(receipt):
    from app.services.notification_service import send_notification
    amount = f'{float(receipt["amount"]):,.2f}'
    for user_id, kind, title, body in (
        (receipt.get('sender_id'), 'wallet_transfer_sent', 'Wallet transfer sent', f'You sent ₦{amount} to {receipt["recipient_name"]}.'),
        (receipt.get('recipient_id'), 'wallet_transfer_received', 'Money added to your wallet', f'{receipt["sender_name"]} sent you ₦{amount}. It is ready to spend.'),
    ):
        if user_id:
            send_notification(user_id=user_id, notif_type=kind, title=title, body=body,
                reference_id=receipt['id'], reference_type='wallet_transfer',
                action_url=f'/wallet?transfer={receipt["id"]}', strict=True)
    rpc('notified', transfer_id=receipt['id'])


def send(actor, body):
    transfer_id, data = intent(body)
    receipt = rpc('send', actor, transfer_id, data)
    try:
        enqueue_receipt(transfer_id)
    except Exception:
        logger.warning('Wallet transfer receipt needs notification recovery: %s', transfer_id)
    return receipt


def enqueue_receipt(transfer_id):
    from app.tasks.scheduled import notify_wallet_transfer
    # Best-effort queue handoff; the private outbox remains authoritative if
    # publishing fails or the process exits after the cash transaction commits.
    notify_wallet_transfer.apply_async(args=[transfer_id], retry=False, ignore_result=True)


def recover(limit=10, budget_seconds=20):
    deadline = monotonic() + budget_seconds
    result = {'processed': 0, 'pending': 0}
    try:
        rows = rpc('due', data={'limit': min(max(int(limit), 0), 20)}) or []
        for row in rows:
            if monotonic() >= deadline:
                break
            try:
                dispatch_receipt({**row, 'amount': row['amount_kobo'] / 100})
                result['processed'] += 1
            except Exception:
                result['pending'] += 1
    except Exception:
        result['error'] = 'Wallet transfer receipt recovery is unavailable'
    return result
