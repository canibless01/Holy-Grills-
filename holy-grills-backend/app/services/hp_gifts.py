"""Read a completed owned intent before applying today's transfer eligibility again."""
from decimal import Decimal, InvalidOperation
from uuid import UUID
from app.db import get_db
from app.services.wallet_transfers import gift_options, TransferError


def replay(body, actor):
    if 'request_id' not in body:
        return None
    try:
        request_id = str(UUID(str(body['request_id'])))
        recipient = str(UUID(str(body.get('recipient_id'))))
        amount = Decimal(str(body.get('amount')))
        if isinstance(body.get('amount'), bool) or not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value() or amount > 2147483647:
            raise ValueError()
        note = body.get('notes') or ''
        if not isinstance(note, str) or len(note.strip()) > 200:
            raise ValueError()
        options = gift_options(body)
    except (ValueError, TypeError, InvalidOperation, TransferError):
        raise TransferError('invalid_transfer') from None
    receipt = get_db().rpc('hg_hp_gift_receipt', {'p_actor': actor, 'p_request': request_id})
    if not receipt:
        return None
    if (receipt.get('direction') != 'sent' or receipt.get('recipient_id') != recipient
            or int(receipt.get('amount') or 0) != int(amount) or (receipt.get('note') or '') != note.strip()
            or bool(receipt.get('anonymous')) != options.get('anonymous', False)
            or bool(receipt.get('share_contact')) != options.get('share_contact', False)):
        raise TransferError('transfer_intent_conflict')
    return {'message': 'HP gift sent', 'amount': int(amount), 'recipient_id': recipient,
            'recipient_name': receipt.get('recipient_name'), 'transfer_id': request_id,
            'new_balance': receipt.get('balance_after'), 'replayed': True}
