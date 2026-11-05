"""Reconcile the amount a provider actually charged against the amount we asked for.

Paystack (and Flutterwave) do not always send us the number we initialized. If the
customer bears the gateway fee — the default on the hosted checkout, and the norm for
card charges — the settled `amount` is *our* amount **plus** the fee, and `fees` /
`requested_amount` describe the split. Orders and wallet top-ups have always allowed
for that (see `order_payments.validate_paystack_amount`). Event tickets, marketplace
purchases and HP bundles compared the gross amount with `> 0.01`, so every
fee-bearing charge failed with "Amount mismatch" even though Paystack had taken the
money — the customer was charged, the order/ticket stayed pending, and (for events)
the registrant never appeared on the host list.

This module is the single place that decides whether a charge may be accepted, so a
new payment type cannot reintroduce an exact-match comparison.

The rule is deliberately *not* "accept anything close": we accept

  1. paid == expected                     — merchant bears the fee
  2. paid - fees == expected              — customer bears the fee
  3. requested_amount == expected         — provider tells us the requested amount
                                            explicitly (newer Paystack payloads)
  4. fees not reported, and paid within the documented tolerance of expected
     (max(₦150, 2%)) — the charge is accepted, flagged `fees_unknown` so the
     reconciliation report can re-read it via /transaction/verify.

Anything else still raises, because a genuinely wrong amount must never be booked as
a paid order/ticket.
"""

from decimal import Decimal, InvalidOperation

from app.services.order_payments import validate_paystack_amount

# Currencies whose major unit is the naira. Both providers quote NGN in naira
# (Flutterwave) or kobo (Paystack); everything downstream is naira.
_SUPPORTED_CURRENCY = "NGN"


class ChargeAmountError(ValueError):
    """The charge cannot be reconciled with the amount we requested."""


def _decimal(value, *, field="amount"):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ChargeAmountError(f"Invalid payment {field}")
    if not amount.is_finite() or amount < 0:
        raise ChargeAmountError(f"Invalid payment {field}")
    return amount


def to_kobo(value, *, field="amount"):
    """Naira (major units) -> integer kobo. Rejects sub-kobo fractions."""
    kobo = _decimal(value, field=field) * 100
    if kobo != kobo.to_integral_value():
        raise ChargeAmountError(f"Invalid payment {field}")
    return int(kobo)


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _provider_amounts(data, provider):
    """(paid_kobo, fees_kobo_or_None, requested_kobo_or_None) for a provider payload."""
    if provider == "paystack":
        # Paystack reports kobo ints. Anything non-integer is a malformed payload.
        paid = _as_int(data.get("amount"))
        if paid is None:
            paid = to_kobo(data.get("amount"))
        fees = _as_int(data.get("fees"))
        requested = _as_int(data.get("requested_amount"))
        return paid, fees, requested
    if provider == "flutterwave":
        paid = to_kobo(data.get("amount"))
        fee_raw = data.get("app_fee")
        if fee_raw in (None, ""):
            fee_raw = data.get("merchant_fee") or data.get("fee")
        fees = to_kobo(fee_raw) if fee_raw not in (None, "") else None
        return paid, fees, None
    raise ChargeAmountError(f"Unsupported payment provider: {provider}")


def validate_charge_amount(data, expected_naira, provider="paystack", *, label="payment"):
    """Return a reconciliation breakdown, or raise `ChargeAmountError`.

    `expected_naira` is what our own record says the customer owes (the card portion
    after wallet/HP), never anything supplied by the client.
    """
    if not isinstance(data, dict):
        raise ChargeAmountError(f"Missing {label} payload")

    currency = data.get("currency")
    if currency and str(currency).upper() != _SUPPORTED_CURRENCY:
        raise ChargeAmountError(f"Invalid currency for {label}: {currency}")

    expected_kobo = to_kobo(expected_naira, field="expected amount")
    if expected_kobo <= 0:
        raise ChargeAmountError(f"Invalid expected amount for {label}")

    paid_kobo, fees_kobo, requested_kobo = _provider_amounts(data, provider)
    if paid_kobo is None or paid_kobo <= 0:
        raise ChargeAmountError(f"Invalid paid amount for {label}")

    # The provider's own "requested amount" is the strongest signal available: it is
    # the figure we initialized, echoed back, independent of how the fee was applied.
    if requested_kobo is not None and requested_kobo == expected_kobo:
        return {
            "paid_kobo": paid_kobo,
            "fees_kobo": fees_kobo or 0,
            "net_kobo": expected_kobo,
            "expected_kobo": expected_kobo,
            "source": "requested_amount",
            "fee_bearer": "customer" if paid_kobo != expected_kobo else "merchant",
        }

    if fees_kobo is not None and fees_kobo < 0:
        raise ChargeAmountError(f"Invalid fees for {label}")

    try:
        breakdown = validate_paystack_amount(expected_kobo, paid_kobo, fees_kobo)
    except ValueError as exc:
        raise ChargeAmountError(
            f"{label} amount mismatch: expected ₦{expected_kobo / 100:,.2f}, "
            f"received ₦{paid_kobo / 100:,.2f}"
            + (f" (fees ₦{fees_kobo / 100:,.2f})" if fees_kobo else "")
        ) from exc

    result = dict(breakdown)
    result["expected_kobo"] = expected_kobo
    # Case 3 of validate_paystack_amount (fees unknown) returns net None; make it explicit
    # so callers/reporting know the fee still has to be re-read from the provider.
    result["source"] = "tolerance" if breakdown.get("net") is None else "amount"
    result["fee_bearer"] = (
        "customer" if breakdown.get("net") == expected_kobo and paid_kobo != expected_kobo
        else "merchant"
    )
    return result


def expected_from_metadata(metadata, data, provider="paystack"):
    """Best-effort recovery of the expected amount when no local record stores it.

    Prefers the server-written `expected_amount_kobo` in the payment metadata, then the
    provider's echoed `requested_amount`, and only then the gross paid amount (a legacy
    payment that never had an expected amount recorded; it can no longer be verified,
    so it is accepted as-is and logged by the caller).
    """
    meta = metadata if isinstance(metadata, dict) else {}
    expected_kobo = meta.get("expected_amount_kobo")
    expected_kobo = _as_int(expected_kobo)
    if expected_kobo and expected_kobo > 0:
        return expected_kobo / 100
    if provider == "paystack":
        requested = _as_int(data.get("requested_amount"))
        if requested and requested > 0:
            return requested / 100
    return None
