# Paystack Payment Amount Validation Fix

## Problem

The Paystack payment validation only accepted exact amount matches (`paid == expected`), which failed when:
- Customer bears the fee: `paid - fees == expected`
- Fees were unknown/null but payment was within acceptable tolerance

This caused legitimate payments to be rejected during webhook processing or return-page verification.

## Solution

Created a **shared validation helper** `validate_paystack_amount()` that handles all three cases:

### Validation Rules (all in kobo integers)

1. **Merchant bears fee**: `paid == expected` → Accept
2. **Customer bears fee**: `paid - fees == expected` → Accept  
3. **Fees unknown (null)**: Accept if `expected <= paid <= expected + max(15000, expected * 0.02)`
   - Tolerance: max of ₦150 (15000 kobo) or 2% of expected amount
   - For small orders: ₦150 cap applies
   - For large orders: 2% applies (e.g., ₦100,000 order → ₦2,000 tolerance)

### Rejection Cases

- `paid < expected` (underpayment)
- `paid > expected + tolerance` (overpayment beyond cap)
- Wrong currency (not NGN)
- Wrong reference (doesn't match order)
- Status != success
- Invalid amounts (negative, NaN, non-integer kobo)

## Files Changed

### 1. `holy-grills-backend/app/services/order_payments.py`

**Added** `validate_paystack_amount(expected_kobo, paid_kobo, fees)`:
- Shared helper for Paystack amount validation
- Returns dict: `{paid, fees, net}` if valid
- Raises `OrderPaymentError` if invalid
- Used by both webhook handler and return-page verify

**Modified** `validate_provider_payment()`:
- Now calls `validate_paystack_amount()` for Paystack payments
- Attaches `_amount_breakdown` to the data dict
- Returns the breakdown for storage

### 2. `holy-grills-backend/app/services/order_service.py`

**Modified** `confirm_order_payment()`:
- Extracts amount breakdown from validation result
- Merges into payment metadata as `amount_breakdown`
- Stored in payments table for reconciliation

### 3. `holy-grills-backend/tests/test_order_card_payments.py`

**Added 11 new test cases**:
1. `test_exact_amount_merchant_bears_fee` - paid == expected
2. `test_amount_plus_fee_customer_bears_fee` - paid - fees == expected
3. `test_underpayment_rejected` - paid < expected
4. `test_overpayment_beyond_cap_rejected` - paid > expected + tolerance
5. `test_missing_fees_within_tolerance` - fees null, within tolerance
6. `test_missing_fees_exact_amount` - fees null, paid == expected
7. `test_missing_fees_at_tolerance_boundary` - fees null, at exact boundary
8. `test_missing_fees_just_over_tolerance_rejected` - fees null, over boundary
9. `test_tolerance_scales_with_amount` - 2% vs fixed cap
10. `test_negative_fees_rejected` - negative fees
11. `test_zero_expected_rejected` - zero/negative expected
12. `test_provider_payment_with_fee_breakdown_stored` - breakdown attached to data

## Data Flow

### Webhook Path
```
Paystack webhook → _handle_charge_success() 
  → confirm_order_payment() 
    → validate_provider_payment() 
      → validate_paystack_amount() 
        → Returns {paid, fees, net}
    → Stores amount_breakdown in payments.metadata
```

### Return-Page Verify Path
```
Customer clicks "I paid" → order_payments.verify()
  → payment_service.verify_payment() 
    → validate_provider_payment() 
      → validate_paystack_amount() 
        → Returns {paid, fees, net}
  → confirm_order_payment()
    → Stores amount_breakdown in payments.metadata
```

## Storage

The amount breakdown is stored in the `payments` table's `metadata` JSONB column:

```json
{
  "type": "order_payment",
  "order_id": "...",
  "user_id": "...",
  "campus_id": "...",
  "amount_breakdown": {
    "paid": 182000,    // Total paid in kobo
    "fees": 2000,      // Paystack fee in kobo (or null)
    "net": 180000      // Net amount in kobo (or null)
  },
  // ... other Paystack response fields
}
```

This enables:
- Reconciliation reports showing paid vs net
- Audit trails for fee disputes
- Analytics on payment fees

## Backward Compatibility

✅ **No breaking changes**:
- Existing exact-match payments still work (Case 1)
- Schema unchanged (uses existing `metadata` JSONB column)
- Signature verification unchanged
- Idempotency unchanged
- All existing tests pass

## Testing

Run the new tests:
```bash
cd holy-grills-backend
python -m pytest tests/test_order_card_payments.py -v
```

Expected output: 12 new tests for amount validation, all passing.

## Examples

### Example 1: Merchant Bears Fee
```
Order total: ₦1,800 (180,000 kobo)
Customer pays: ₦1,800 (180,000 kobo)
Paystack fee: ₦0 (merchant absorbs)
Result: ✅ Accepted (paid == expected)
```

### Example 2: Customer Bears Fee
```
Order total: ₦1,800 (180,000 kobo)
Customer pays: ₦1,820 (182,000 kobo)
Paystack fee: ₦20 (2,000 kobo)
Net: ₦1,800 (180,000 kobo)
Result: ✅ Accepted (paid - fees == expected)
```

### Example 3: Fees Unknown, Within Tolerance
```
Order total: ₦1,800 (180,000 kobo)
Customer pays: ₦1,900 (190,000 kobo)
Fees: null (not provided by Paystack)
Tolerance: max(15,000, 180,000 * 0.02) = 15,000 kobo
Max acceptable: 180,000 + 15,000 = 195,000 kobo
Result: ✅ Accepted (within tolerance, fees=null stored)
```

### Example 4: Overpayment Beyond Cap
```
Order total: ₦1,800 (180,000 kobo)
Customer pays: ₦2,000 (200,000 kobo)
Fees: null
Tolerance: 15,000 kobo
Max acceptable: 195,000 kobo
Result: ❌ Rejected (200,000 > 195,000)
```

## Future Enhancements

1. **Auto-reconcile fees**: When `fees=null`, call Paystack's verify endpoint to fetch actual fees
2. **Fee analytics dashboard**: Show fee trends by order size, payment method, etc.
3. **Fee dispute automation**: Auto-create support tickets when fees exceed tolerance

## Related Files

- `holy-grills-backend/app/routes/webhooks.py` - Webhook handler (uses shared validation)
- `holy-grills-backend/app/services/order_payments.py` - Shared validation helper
- `holy-grills-backend/app/services/order_service.py` - Payment confirmation
- `docs/ORDER_CARD_PAYMENT_RECOVERY_FIX.sql` - Payment schema (unchanged)
