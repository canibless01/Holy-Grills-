"""Verify Paystack wallet funding and credit its requested amount once."""
from app.db import get_db
from app.services.order_payments import validate_paystack_amount
from app.services.wallet_service import credit_wallet
from decimal import Decimal


class WalletFundingConflict(ValueError):
    """An earlier credit for this reference needs reconciliation."""


def confirm_paystack_wallet_funding(data, reference, expected_user_id=None):
    metadata = data.get('metadata') or {}
    user_id = metadata.get('user_id') if isinstance(metadata, dict) else None
    if (not user_id or metadata.get('type') != 'wallet_topup'
            or data.get('reference') != reference or data.get('currency') != 'NGN'
            or (expected_user_id is not None and user_id != expected_user_id)):
        raise ValueError('Invalid wallet payment identity')
    profile = get_db().table('profiles').select('id,campus_id').eq('id', user_id).single().execute()
    if not profile or (metadata.get('campus_id') and metadata['campus_id'] != profile.get('campus_id')):
        raise ValueError('Invalid wallet payment campus')
    if data.get('status') != 'success':
        return {'payment_status': 'pending'}

    # New initializations bind the amount server-side. Older Paystack records
    # expose requested_amount when customers bear the gateway fee. Never turn
    # the fee into spendable wallet credit.
    expected = metadata.get('expected_amount_kobo', data.get('requested_amount', data.get('amount')))
    if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0:
        raise ValueError('Invalid wallet payment amount')
    requested = data.get('requested_amount')
    if requested is not None and (isinstance(requested, bool) or not isinstance(requested, int) or requested != expected):
        raise ValueError('Wallet requested amount mismatch')
    breakdown = validate_paystack_amount(expected, data.get('amount'), data.get('fees'))
    amount = expected / 100
    campus_id = profile.get('campus_id')
    transaction = credit_wallet(
        user_id=user_id, amount=amount, payment_reference=reference,
        reference_type='topup', notes=f'Card top-up via Paystack ({reference})',
        provider_response={**data, '_amount_breakdown': breakdown}, campus_id=campus_id,
    )
    if Decimal(str(transaction.get('amount', amount))) != Decimal(expected) / 100:
        raise WalletFundingConflict('Existing wallet credit amount differs from verified requested amount')
    return {'payment_status': 'paid', 'amount': amount, 'campus_id': campus_id,
            'transaction_id': transaction.get('id')}
