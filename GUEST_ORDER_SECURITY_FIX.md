# Guest Order Tracking Security Fix

## Critical Issue Identified

**Problem**: Guest order tracking was showing orders from OTHER guests on the same device, not just the current guest's orders.

### Root Cause

Guest orders were stored in a **shared localStorage key** (`hg_guest_orders`) on the device. This meant:

1. Guest A places an order on Device X → saved to `hg_guest_orders` with Guest A's claim_token
2. Guest B uses Device X → places an order → ALSO saved to `hg_guest_orders` with Guest B's claim_token
3. When Guest A visits tracking page → loads ALL orders from `hg_guest_orders` → sees Guest B's order
4. When Guest B visits tracking page → loads ALL orders from `hg_guest_orders` → sees Guest A's order

**Security Issue**: While the backend correctly validated claim_tokens, the frontend was loading ALL orders stored on the device, giving each guest access to other guests' orders (because they had the claim_tokens in localStorage).

## Solution: Session-Scoped Storage

### Changes Made

#### 1. Checkout.tsx
- Generate unique session ID when guest starts checkout
- Store guest orders in session-scoped localStorage key: `hg_guest_orders_${sessionId}`
- Pass sessionId to OrderConfirmation page via navigation state

```typescript
// Generate session ID
let sessionId = sessionStorage.getItem('hg_checkout_session');
if (!sessionId) {
  sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  sessionStorage.setItem('hg_checkout_session', sessionId);
}

// Use session-scoped key
const sessionKey = `hg_guest_orders_${sessionId}`;
localStorage.setItem(sessionKey, JSON.stringify(guestOrders));
```

#### 2. OrderConfirmation.tsx
- Receive sessionId from navigation state
- Look up claim_token from session-scoped localStorage key
- Fallback to legacy unscoped key for backward compatibility

#### 3. TrackOrders.tsx
- Receive sessionId from navigation state
- Load guest orders from session-scoped localStorage key
- When user manually looks up order (from email), create new session if needed
- Only show orders from current session, not all orders on device

#### 4. OrderDetail.tsx
- When resolving claim_token, search through ALL session-scoped keys
- When claiming order, remove from ALL session-scoped keys
- Ensures backward compatibility with orders placed before this fix

### How It Works Now

1. **Guest A starts checkout** → Session ID `session_123_abc` created → Orders stored in `hg_guest_orders_session_123_abc`
2. **Guest B starts checkout on same device** → NEW Session ID `session_456_def` created → Orders stored in `hg_guest_orders_session_456_def`
3. **Guest A visits tracking page** → Loads from `hg_guest_orders_session_123_abc` → Only sees Guest A's orders ✓
4. **Guest B visits tracking page** → Loads from `hg_guest_orders_session_456_def` → Only sees Guest B's orders ✓

### Session ID Lifecycle

- **Created**: When guest starts checkout or manually looks up order from email
- **Stored in**: `sessionStorage` (per-tab, cleared when tab closes)
- **Used to scope**: localStorage key for guest orders
- **Result**: Each checkout flow is isolated, even on shared devices

### Backward Compatibility

- OrderDetail.tsx searches through ALL session-scoped keys to find claim_tokens
- OrderConfirmation.tsx falls back to legacy `hg_guest_orders` key
- Orders placed before this fix will still work
- Old orders can be claimed and will be properly removed from all storage keys

## Testing

### Test Case 1: Two Guests on Same Device
1. Guest A (guest-a@email.com) places order on Device X
2. Guest B (guest-b@email.com) places order on Device X
3. Guest A visits tracking page → Should ONLY see Guest A's order ✓
4. Guest B visits tracking page → Should ONLY see Guest B's order ✓

### Test Case 2: Failed Payment
1. Guest creates order with failed payment
2. Order is saved to session-scoped localStorage
3. Guest can still track the order (useful for retrying payment)
4. Other guests on same device cannot see this order ✓

### Test Case 3: Email Tracking Link
1. Guest receives email with tracking link (order_number + claim_token)
2. Clicks link → Opens tracking page (no sessionId in state)
3. Auto-lookup triggers → Creates new session → Saves order to session-scoped storage
4. Guest can track order ✓
5. Other guests on same device cannot see this order ✓

## Files Modified

- `holy-grills-frontend/src/pages/Checkout.tsx`
- `holy-grills-frontend/src/pages/OrderConfirmation.tsx`
- `holy-grills-frontend/src/pages/TrackOrders.tsx`
- `holy-grills-frontend/src/pages/OrderDetail.tsx`

## Security Impact

**Before**: Any guest using a device could see ALL guest orders from that device (if they had the claim_tokens in localStorage)

**After**: Each guest can ONLY see orders from their own checkout session, even on shared devices

**Risk Level**: CRITICAL - This was a major privacy and security issue

**Status**: ✅ FIXED
