"""Read-only revenue allocation. Never changes charges, refunds or wallet balances."""
from decimal import Decimal, ROUND_HALF_UP

ORDER_MONEY_COLUMNS = 'total_amount,delivery_fee,payment_status,card_refund_total,wallet_refund_total'
PAID_STATES = frozenset(('paid', 'partially_refunded', 'refunded'))


def _amount(value):
    return Decimal(str(value or 0))


def retained_order_amount(order):
    """Paid amount retained after completed refunds; unpaid intents are not revenue."""
    if order.get('payment_status') not in PAID_STATES:
        return Decimal(0)
    return max(Decimal(0), _amount(order.get('total_amount')) - _amount(order.get('card_refund_total')) - _amount(order.get('wallet_refund_total')))


def retained_food_amount(order):
    """Discounted food revenue, with unitemized refunds allocated proportionately.

    This uses the same proportional allocation as the delivery subsidy ledger.
    Delivery fees are excluded; the included cushion remains part of retail food revenue.
    """
    total = _amount(order.get('total_amount'))
    if total <= 0:
        return Decimal(0)
    food = max(Decimal(0), total - _amount(order.get('delivery_fee')))
    return (food * min(Decimal(1), retained_order_amount(order) / total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def delivered_revenue(order):
    return retained_order_amount(order) if order.get('status') == 'delivered' else Decimal(0)


def retained_payment_channels(order):
    """Attribute retained revenue to its original funding channels, not refund destination.

    A card payment refunded into a member wallet still reduces card-origin revenue.
    Split payments allocate unitemized refunds proportionately; card takes rounding remainder.
    """
    retained = retained_order_amount(order)
    wallet = max(Decimal(0), _amount(order.get('wallet_amount_used')))
    card = max(Decimal(0), _amount(order.get('card_amount_used')))
    if wallet + card <= 0:
        return Decimal(0), Decimal(0)
    wallet_net = (retained * wallet / (wallet + card)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return wallet_net, retained - wallet_net


def allocate_food_revenue(order, items):
    """Allocate retained food cents across frozen lines with deterministic remainders."""
    weights = [max(Decimal(0), _amount(item.get('line_total') if item.get('line_total') is not None else _amount(item.get('price_snapshot')) * int(item.get('quantity') or 0))) for item in items]
    gross = sum(weights)
    if gross <= 0:
        return [(item, Decimal(0)) for item in items]
    cents = int(retained_food_amount(order) * 100)
    exact = [Decimal(cents) * weight / gross for weight in weights]
    shares = [int(value) for value in exact]
    remainder = cents - sum(shares)
    priority = sorted(range(len(items)), key=lambda i: (-(exact[i] - shares[i]), str(items[i].get('id') or i)))
    for i in priority[:remainder]:
        shares[i] += 1
    return [(item, Decimal(share) / 100) for item, share in zip(items, shares)]
