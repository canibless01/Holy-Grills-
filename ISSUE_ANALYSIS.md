# Critical Issues Analysis

## Issue 1: Guest Order Tracking Security Vulnerability

**Root Cause Identified:**
In `holy-grills-backend/app/routes/orders.py`, the `track_guest_order()` function (line 263-286) has a critical security flaw:

```python
try:
    oid = str(_uuid.UUID(number))
except ValueError:
    # Only validates token for non-UUID order numbers
    row = (get_db().table('orders').select('id,user_id,claim_token')
           .ilike('order_number',number).limit(1).single().execute())
    if not row or row.get('user_id') or not hmac.compare_digest(...):
        return jsonify({'error': MSG.ORDER_NOT_FOUND}), 404
    oid = row['id']
return get_order.__wrapped__(oid)  # ← No token validation for UUID!
```

When the order_number is already a UUID, the code skips token validation entirely and calls `get_order` directly. This allows anyone with a UUID to access any guest order.

**Security Impact:**
- Guest orders can be accessed without valid claim tokens
- Order details, items, totals, and customer information exposed
- Violates guest privacy and security

**Fix Required:**
Always validate the claim_token, regardless of whether the order_number is a UUID or display format.

## Issue 2: Tracking Form Error

**Root Cause:**
The tracking form expects the order_number to match either:
1. A UUID format (order ID)
2. A display format (order_number field)

But the error "We couldn't find an order with that number" suggests the lookup is failing. This could be because:
- The order_number format doesn't match what's stored
- The claim_token validation is failing
- The order has already been claimed by a registered user

## Issue 3: Paystack Redirect Issues

**Root Cause Analysis Needed:**
- Check callback URL configuration
- Verify transaction verification logic
- Handle async payment methods properly
- Ensure proper state management during redirect

## Issue 4: Cart Persistence

**Root Cause Analysis Needed:**
- Check when cart is cleared in checkout flow
- Verify cart state during payment redirect
- Ensure order data is persisted before cart clearing

## Issue 5: Phone Number Popup

**Current Issue:**
Awkward wording: "available offline"
**Fix:** Clear, direct messaging about phone number requirements
