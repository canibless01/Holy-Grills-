# Holy Grills — Frontend Integration Guide

> Version: 1.0 | Last updated: July 2026  
> Backend: Flask REST API on port 5000 | Database: Supabase (PostgREST) | Payments: Paystack

---

## 1. Quick Start

### Base URL
```
Development:  http://localhost:5000/api
Production:   https://<your-domain>/api
```

### Required Headers
```http
Content-Type: application/json
Authorization: Bearer <access_token>      # for protected endpoints
```

### Example Request
```javascript
const res = await fetch(`${BASE_URL}/auth/me`, {
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${accessToken}`,
  }
});
const data = await res.json();
```

---

## 2. Authentication & Sessions

### Token Strategy
| Token | Lifetime | Storage | Purpose |
|---|---|---|---|
| `access_token` | Short-lived (minutes/hours) | Memory or SecureStorage | API calls |
| `refresh_token` | Long-lived (days) | SecureStorage / HttpOnly cookie | Rotate access token |

On every 401 response, call `POST /auth/refresh` to get a new access token. On failure (refresh expired), send the user to login.

### Register
```http
POST /api/auth/register
```
```json
{
  "email": "student@futa.edu.ng",
  "password": "SecurePass1!",
  "full_name": "Jane Doe",
  "phone": "08012345678",          // optional, must be 11-digit NG format
  "date_of_birth": "2000-01-15",   // optional, must be 16+ years old
  "referred_by": "JANE123"         // optional referral code
}
```
**Response 201:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": { "id": "uuid", "email": "...", "role": "student" }
}
```
**Errors:** `400` underage, invalid phone, duplicate email, weak password (min 8 chars, 1 uppercase, 1 number, 1 special char).

### Login
```http
POST /api/auth/login
```
```json
{ "email": "...", "password": "..." }
```
**Response 200:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": { "id": "uuid", "email": "...", "role": "student", "full_name": "..." }
}
```
**Errors:** `401` wrong credentials, `429` rate-limited after multiple failures.

### Refresh Token
```http
POST /api/auth/refresh
```
```json
{ "refresh_token": "eyJ...", "access_token": "eyJ..." }
```
**Response 200:** `{ "access_token": "eyJ...", "refresh_token": "eyJ...", "rotated": true }`

### Get Current User
```http
GET /api/auth/me
Authorization: Bearer <token>
```
**Response 200:**
```json
{
  "id": "uuid",
  "email": "student@futa.edu.ng",
  "full_name": "Jane Doe",
  "role": "student",
  "referral_code": "JANE123",
  "profile": {
    "id": "uuid", "full_name": "...", "phone": "...", "date_of_birth": "...",
    "academic_level": 300, "role": "student", "referral_code": "JANE123",
    "push_enabled": true, "email_notifications": true
  },
  "wallet": { "balance": 5000.00, "currency": "NGN" },
  "tier": { "slug": "regular", "name": "Regular", "color": "blue" }
}
```

### Other Auth Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| `PATCH` | `/auth/profile` | Yes | Update full_name, phone, date_of_birth, push_enabled |
| `POST` | `/auth/change-password` | Yes | `{ current_password, new_password }` — logs out all other sessions |
| `POST` | `/auth/reset-password` | No | `{ email }` — sends reset link |
| `POST` | `/auth/verify-email` | No | `{ email }` — resend verification |
| `POST` | `/auth/logout-all-devices` | Yes | Invalidates all tokens |
| `GET`  | `/auth/streak` | Yes | Login streak: `{ streak_count, last_login_date }` |
| `POST` | `/auth/device-token` | Yes | `{ token: "fcm_or_apns_token", platform: "ios"|"android" }` |

### Role System
| Role | Access Level |
|---|---|
| `student` | Default — place orders, manage HP, wallet, events |
| `kitchen` | All student access + kitchen queue management |
| `rider` | All student access + delivery management |
| `admin` | Full access including all management endpoints |

---

## 3. Complete API Reference

### Addresses
```http
GET    /api/auth/addresses          # List user's saved addresses
POST   /api/auth/addresses          # Create address
PATCH  /api/auth/addresses/:id      # Update address
DELETE /api/auth/addresses/:id      # Delete address
```
**Create body:** `{ label, line1, line2?, city, state, is_default? }`

---

### Menu

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/menu/categories` | No | List all categories |
| `POST` | `/api/menu/categories` | Admin | Create category `{ name, slug }` |
| `PATCH` | `/api/menu/categories/:id` | Admin | Update category |
| `DELETE` | `/api/menu/categories/:id` | Admin | Delete category |
| `GET` | `/api/menu/items` | No | List items (query: `category`, `q`, `available_only`, `is_featured`, `limit`, `offset`) |
| `GET` | `/api/menu/items/:id` | No | Get item detail (includes `is_sold_out`, `remaining_today`) |
| `POST` | `/api/menu/items` | Admin | Create item `{ name, price, category_id, hp_earn_value, daily_limit? }` |
| `PATCH` | `/api/menu/items/:id` | Admin | Update item |
| `GET` | `/api/menu/items/:id/addons` | No | Item-specific add-on groups |
| `GET` | `/api/menu/addons` | No | All add-on groups |
| `POST` | `/api/menu/addons` | Admin | Create add-on group `{ name, items, min_select, max_select }` |
| `GET` | `/api/menu/kitchen-capacity` | No | `{ daily_order_capacity, orders_today, remaining }` |
| `PATCH` | `/api/menu/kitchen-capacity` | Kitchen | Set `{ daily_order_capacity }` |

**Menu Item response key fields:** `id`, `name`, `price` (kobo/naira), `hp_earn_value`, `category_id`, `is_available`, `is_featured`, `is_sold_out`, `remaining_today`, `image_url`, `description`, `addons`.

---

### Cart
```http
GET    /api/cart                # Get full cart {items, subtotal}
POST   /api/cart                # Add item {menu_item_id, quantity, notes?, addon_selections?}
PATCH  /api/cart/:item_id       # Update {quantity?, notes?, addon_selections?}
DELETE /api/cart/:item_id       # Remove item
DELETE /api/cart                # Clear entire cart
```
Cart is **persisted server-side** — always fetch from server on load. `subtotal` is in Naira.

---

### Saved For Later
```http
GET    /api/saved                       # List saved items
POST   /api/saved                       # Save item {menu_item_id, quantity, notes?}
PATCH  /api/saved/:id                   # Update saved item {quantity?, notes?}
DELETE /api/saved/:id                   # Remove saved item
POST   /api/saved/:id/move-to-cart      # Move saved item to cart
POST   /api/saved/from-cart/:cart_item_id  # Move cart item to saved
```

---

### Orders — Create & List

**Place an Order**
```http
POST /api/orders
Authorization: Bearer <token>   # Omit for guest checkout
```
```json
{
  "items": [
    { "menu_item_id": "uuid", "quantity": 2, "notes": "No onions", "addon_selections": [] }
  ],
  "payment_method": "card",         // "wallet" | "card" | "split"
  "delivery_type": "on_campus",     // "on_campus" | "off_campus"
  "delivery_location_id": "hostel-uuid",   // hostel UUID (on_campus) or gate UUID (off_campus)
  "delivery_location_lat": 7.302,   // required for off_campus
  "delivery_location_lon": 5.131,   // required for off_campus
  "promo_code": "SAVE10",           // optional
  "is_scheduled": false,            // true for scheduled delivery
  "scheduled_date": "2026-07-20",   // YYYY-MM-DD, required if is_scheduled=true
  "squad_name": "My Squad",         // optional, enables squad order
  "squad_emails": ["friend@futa.edu.ng"], // optional, min 2 more members for squad
  // Guest checkout only (no auth token):
  "guest_name": "Guest User",
  "guest_phone": "08099999999"
}
```

**Key response fields:**
```json
{
  "order": {
    "id": "uuid",
    "status": "received",
    "total_amount": 3500.00,
    "delivery_fee": 400.00,
    "hp_discount": 0,
    "payment_method": "card",
    "is_scheduled": false,
    "is_squad_order": false,
    "squad_name": null,
    "claim_token": "abc123xyz",    // guest orders only — share with user
    "delivery_type": "on_campus"
  }
}
```

> ⚠️ **HP redemption (`hp_points_to_redeem`) is not currently supported on orders — the field is accepted but ignored.**

**List Orders**
```http
GET /api/orders?status=delivered&limit=20&offset=0
```
**Response:** `{ orders: [...], total }`

**Get Order Detail**
```http
GET /api/orders/:id                           # owner or admin
GET /api/orders/:id?claim_token=abc123xyz    # guest (no auth needed)
```

**Scheduled & Active Orders**
```http
GET /api/orders/scheduled     # Authenticated user's scheduled orders
GET /api/orders/active        # User's current active order (if any)
```

**Validate Promo Code**
```http
POST /api/orders/validate-promo
{ "code": "SAVE10", "order_subtotal": 5000 }
```
**Response:** `{ valid: true, calculated_discount: 500, discount_type: "percentage", discount_value: 10 }`

**Delivery Windows**
```http
GET /api/orders/delivery-windows           # Future available windows
GET /api/orders/delivery-windows/status    # Is ordering currently open?
GET /api/orders/delivery-zones             # Configurable delivery zones
```

---

### Orders — Actions

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/orders/:id/cancel` | Owner | `{ reason }` — only `received` status |
| `POST` | `/api/orders/:id/reorder` | Yes | Copy items from past order to cart |
| `POST` | `/api/orders/:id/claim` | Yes | Claim guest order `{ claim_token }` |
| `POST` | `/api/orders/:id/squad-members` | Organizer | Add `{ emails: [], split_hp: true }` |
| `DELETE` | `/api/orders/:id/scheduled` | Owner | Cancel a scheduled order |
| `POST` | `/api/orders/:id/refund` | Admin | `{ reason, refund_amount }` |
| `GET` | `/api/orders/:id/history` | Owner/Admin | Status change log |
| `POST` | `/api/orders/:id/review` | Owner | `{ rating: 1-5, review_text }` — awards HP |

---

### Orders — Status (Kitchen & Rider)

**Kitchen transitions:**
```http
PATCH /api/orders/:id/status
Authorization: Bearer <kitchen_token>
{ "status": "preparing" }   // received → preparing
{ "status": "ready" }       // preparing → ready
```

**Rider transitions:**
```http
POST /api/riders/orders/:id/pickup    # ready/assigned → out_for_delivery
POST /api/riders/orders/:id/deliver   # out_for_delivery → delivered
```

**Full state machine:**
```
received → preparing → ready → (assigned) → out_for_delivery → delivered
         ↘          ↘       ↘                               ↘
          cancelled   cancelled  cancelled               refunded
```
- `received`: Kitchen hasn't started. Customer can cancel.
- `preparing`: Kitchen is working. No cancellation.
- `ready`: Waiting for rider. Rider can pick up.
- `assigned`: Order in a delivery batch assigned to a rider.
- `out_for_delivery`: Rider has picked up. In transit.
- `delivered`: Delivered. HP released, welcome/referral bonuses triggered.
- `cancelled` / `refunded`: Terminal states.

---

### Delivery

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/delivery/hostels` | No | List on-campus hostels `[{ id, name, delivery_fee }]` |
| `GET` | `/api/delivery/gates` | No | List off-campus gates `[{ id, name, base_fee }]` |
| `POST` | `/api/delivery/calculate-fee` | No | Calculate fee before ordering |
| `POST` | `/api/delivery/admin/gates` | Admin | Create gate |
| `PATCH` | `/api/delivery/admin/gates/:id` | Admin | Update gate |
| `POST` | `/api/delivery/admin/hostels` | Admin | Create hostel |
| `PATCH` | `/api/delivery/admin/hostels/:id` | Admin | Update hostel |

**Calculate fee:**
```json
{
  "delivery_type": "on_campus",
  "delivery_location_id": "hostel-uuid"
}
// off_campus also accepts lat/lon for distance-based pricing:
{
  "delivery_type": "off_campus",
  "delivery_location_id": "gate-uuid",
  "lat": 7.302, "lon": 5.131
}
```
**Response:** `{ delivery_fee: 400, distance_km: 0.5 }`

---

### HP Balance & Transactions

```http
GET /api/hp/balance               # {active, pending, tier: {slug, name}}
GET /api/hp/transactions          # List, query: type=earn|spend, limit, offset
GET /api/hp/transactions?type=earn
GET /api/hp/tiers                 # All HP tiers and thresholds
GET /api/hp/unlock-history        # When pending HP became active
```

**Balance response:**
```json
{
  "active": 1250,
  "pending": 350,
  "tier": { "slug": "regular", "name": "Regular", "color": "#3B82F6", "min_hp": 500, "max_hp": 1999 }
}
```

> ⚠️ **Display `active` and `pending` separately in the UI.** Never add them — pending HP has not yet been released.

**HP Transaction types:** `earn`, `spend`, `unlock`, `expire`, `transfer_in`, `transfer_out`, `admin_grant`

---

### HP Spending

**Spin Wheel**
```http
POST /api/hp/spin            # First spin of the day is free; subsequent spins cost HP
GET  /api/hp/spin/history    # User's spin history
```
**Response:** `{ prize: "50 HP", hp_awarded: 50, spin_cost_hp: 0, message: "Free spin!" }`

**HP Transfer (P2P)**
```http
POST /api/hp/transfer
{ "recipient_id": "uuid", "amount": 50, "notes": "Happy birthday!" }
```
Requires: minimum 10 HP, sender ≠ recipient, sender must have ≥ 3 completed delivered orders.  
**Errors:** `400` below minimum, self-transfer, insufficient active HP, insufficient completed orders.

**HP Bundles (Purchase HP for Cash)**
```http
GET  /api/hp/bundles           # List available bundle tiers with naira prices
POST /api/hp/bundles/purchase  # { hp_amount: 500, paystack_reference: "ref_abc" }
```

**Flash Redemption**
```http
POST /api/hp/flash-redeem/:reward_id   # Redeem during an active flash sale window
```

---

### Rewards & Redemptions

```http
GET  /api/rewards                       # List all rewards (query: category, limit, offset)
GET  /api/rewards/:id                   # Reward detail {name, hp_cost, stock_quantity, reward_type}
POST /api/rewards/:id/redeem            # Redeem with HP
GET  /api/rewards/redemptions           # My redemption history
PATCH /api/rewards/:id                  # Admin: update reward
GET  /api/rewards/admin/redemptions     # Admin: all redemptions
```

**Reward types:** `voucher`, `free_item`, `discount`, `experience`, `product`

---

### Events

```http
GET  /api/events                         # List upcoming published events
GET  /api/events/:id                     # Event detail
POST /api/events/:id/register            # Register (get ticket) — auth required
POST /api/events/:id/checkin             # Check in with QR {qr_token: "ticket_id"}
POST /api/events/:id/qr                  # Admin: generate event QR
POST /api/events                         # Admin: create event
PATCH /api/events/:id                    # Admin: update event
DELETE /api/events/:id                   # Admin: delete event
POST /api/events/catering-requests       # Public: submit catering inquiry
```

**Register response:**
```json
{
  "ticket_id": "uuid",
  "qr_token": "uuid",          // same as ticket_id — use this for check-in
  "event_id": "uuid",
  "event_title": "FUTA Coding Night",
  "status": "confirmed",
  "message": "Registration successful. Use ticket_id as qr_token to check in."
}
```

---

### Marketplace

```http
GET  /api/marketplace                        # List listings (query: q, category, limit, offset)
GET  /api/marketplace/:id                    # Listing detail {codes_remaining, hp_price, price}
POST /api/marketplace/:id/purchase           # Purchase with HP or wallet
GET  /api/marketplace/purchases              # My purchase history
POST /api/marketplace/requests               # Submit vendor request
POST /api/marketplace/admin/listings         # Admin: create listing
PATCH /api/marketplace/admin/listings/:id    # Admin: update listing
POST /api/marketplace/admin/codes/:id        # Admin: add codes to listing {codes: ["CODE1", "CODE2"]}
GET  /api/marketplace/admin/purchases        # Admin: all purchases
GET  /api/marketplace/admin/requests         # Admin: all vendor requests
PATCH /api/marketplace/admin/requests/:id    # Admin: approve/reject {status: "approved"|"rejected"}
```

---

### Kitchen (Role: kitchen or admin)

```http
GET  /api/kitchen/queue              # Active orders to prepare
GET  /api/kitchen/scheduled          # Scheduled orders for today/tomorrow
GET  /api/kitchen/windows            # Delivery windows with order counts
GET  /api/kitchen/batch-summary/:id  # Batch totals for a window
GET  /api/kitchen/metrics            # Today's throughput stats
GET  /api/kitchen/settings           # Kitchen configuration
PATCH /api/kitchen/settings          # Update kitchen config
```

**Queue item fields:** `id`, `status`, `items[{name, quantity, notes, addons}]`, `customer_name`, `delivery_type`, `created_at`.

---

### Riders (Role: rider or admin)

```http
GET  /api/riders/my-batch                    # Current assigned delivery batch
PATCH /api/riders/availability               # {is_available: bool, location_lat?, location_lng?}
POST /api/riders/orders/:id/pickup           # Confirm pickup (ready → out_for_delivery)
POST /api/riders/orders/:id/deliver          # Confirm delivery (out_for_delivery → delivered)
GET  /api/riders/history                     # Completed deliveries
GET  /api/riders/stats                       # Totals and performance
GET  /api/riders/earnings?period=week|month|all  # Earnings breakdown
GET  /api/riders/call/:order_id              # Secure call link (tel: URI)
```

---

### Leaderboard

```http
GET /api/leaderboard?period_type=monthly|weekly|all_time&limit=10
GET /api/leaderboard/my-rank
GET /api/leaderboard/squad?period_type=monthly
GET /api/leaderboard/squad/my-rank
GET /api/leaderboard/hall-of-fame/inductees   # Top 4 in 4+ different months
```

**Entry fields:** `rank`, `user_id`, `full_name`, `hp_earned`, `tier_slug`

---

### Notifications & Push

```http
GET   /api/notifications?unread_only=true&limit=20&offset=0
POST  /api/notifications/:id/read       # Mark one read
POST  /api/notifications/read-all       # Mark all read
GET   /api/notifications/preferences    # {push_enabled, email_notifications}
PATCH /api/notifications/preferences    # {push_enabled: false}
POST  /api/push/subscribe               # Web push subscription object
```

**Notification object:**
```json
{
  "id": "uuid",
  "type": "order_ready",
  "title": "Order Ready!",
  "body": "Your order is ready for pickup.",
  "reference_id": "order-uuid",
  "reference_type": "order",
  "read": false,
  "created_at": "2026-07-16T14:00:00Z"
}
```

**Notification types:** `order_received`, `order_preparing`, `order_ready`, `order_delivered`, `order_cancelled`, `hp_earned`, `hp_received`, `event_registered`, `event_checkin`, `review_hp`, `referral_hp`, `birthday_hp`, `streak_bonus`, `challenge_completed`, `badge_unlocked`, `leaderboard_rank`.

---

### Order Locks

```http
POST  /api/order-locks                       # Create lock
GET   /api/order-locks                       # List my locks
GET   /api/order-locks/:id                   # Detail
PATCH /api/order-locks/:id/reschedule        # Change date (once only)
DELETE /api/order-locks/:id                  # Cancel lock
```

**Create lock:**
```json
{
  "locked_date": "2026-07-25",          // must be future
  "reward_type": "discount",            // "discount" | "hp"
  "discount_pct": 15,                   // required if reward_type=discount (1–50)
  "reward_hp_amount": 50                // required if reward_type=hp
}
```
Placing an order on the `locked_date` applies the discount or awards the HP automatically.

---

### Wallet

```http
GET  /api/wallet                                 # {balance, currency}
GET  /api/wallet/transactions?type=topup&limit=20
POST /api/wallet/fund/card                       # {amount (min 500 NGN), callback_url}
POST /api/wallet/fund/bank                       # Provision virtual account (Paystack NUBAN)
```

**Fund via card response:**
```json
{
  "authorization_url": "https://checkout.paystack.com/...",
  "reference": "pay_xxx",
  "access_code": "xxx"
}
```
Redirect user to `authorization_url`. Paystack calls your webhook on completion.

> ⚠️ **Wallet withdrawal is not available.** The withdraw endpoint has been removed. Do not display any withdrawal UI.

---

### Admin

#### Users
```http
GET   /api/admin/users?q=name&role=student&limit=20&offset=0
GET   /api/admin/users/:id
GET   /api/admin/users/:id/hp
GET   /api/admin/users/:id/wallet
GET   /api/admin/users/:id/orders
```

#### Orders
```http
GET  /api/admin/orders?status=delivered&from_date=2026-01-01
```

#### Delivery
```http
GET   /api/admin/delivery-windows
POST  /api/admin/delivery-windows             # {label, starts_at, ends_at, capacity}
POST  /api/admin/delivery-windows/:id/close
POST  /api/admin/delivery-windows/:id/reopen
GET   /api/admin/delivery-batches
```

#### Promo Codes
```http
GET   /api/admin/promo-codes
POST  /api/admin/promo-codes      # {code, discount_type, discount_value, min_order_amount, max_uses, expires_at}
PATCH /api/admin/promo-codes/:id
GET   /api/admin/promo-codes/:id/uses
```

#### HP Management
```http
GET  /api/admin/hp/report
POST /api/admin/hp/bulk-grant   # {amount, reason, dry_run?, user_ids?}
POST /api/hp/admin/:user_id/grant    # Manual grant to user
```

#### System Settings
```http
GET   /api/admin/settings
POST  /api/admin/settings          # {key, value, description}
PATCH /api/admin/settings/:key     # {value}
```

Key system setting keys:
| Key | Description | Default |
|---|---|---|
| `monthly_pending_cap` | Max pending HP per user per month | 800 |
| `min_topup_amount` | Min wallet top-up (NGN) | 500 |
| `min_withdrawal_amount` | Min withdrawal (NGN) | 1000 |
| `signup_bonus_hp` | HP on registration | env: `SIGNUP_BONUS_HP` |
| `welcome_bonus_hp` | HP on first delivery | env: `WELCOME_BONUS_HP` |
| `referral_hp` | HP for referrer on referee's first order | env: `REFERRAL_HP` |
| `birthday_hp` | HP on user's birthday | env: `BIRTHDAY_HP` |
| `review_hp` | HP per order review | env: `REVIEW_HP` |
| `social_share_hp` | HP per social share (daily) | env: `SOCIAL_SHARE_HP` |
| `hp_transfer_min_orders` | Min completed orders to transfer HP | 3 |
| `graduation_min_level` | Min academic_level to claim graduation HP | 400 |
| `order_lock_max_discount` | Max % for order locks | 50 |
| `notification_gap_minutes` | Min minutes between push notifications | 30 |

#### Other Admin
```http
GET  /api/admin/abandoned-carts
GET  /api/admin/audit-log
GET  /api/admin/cron/status
GET  /api/admin/first-order-gifts
PATCH /api/admin/first-order-gifts/:id   # {status: "fulfilled"|"cancelled"}
```

---

### Analytics (Admin)

```http
GET /api/analytics/dashboard
GET /api/analytics/sales?from_date=2026-01-01&to_date=2026-07-16
GET /api/analytics/orders?from_date=...&to_date=...
GET /api/analytics/hp
GET /api/analytics/referrals
GET /api/analytics/items?from_date=...&to_date=...
GET /api/analytics/users
GET /api/analytics/retention
GET /api/analytics/abandoned-carts
GET /api/analytics/gifts
GET /api/analytics/marketplace
GET /api/analytics/export?type=orders|hp_transactions|wallet_transactions|users&from_date=...&to_date=...
```

---

### Storefront

```http
GET  /api/storefront/sections              # Homepage sections (hero, featured items, etc.)
GET  /api/storefront/operating-hours       # Opening hours per day of week
GET  /api/storefront/banners               # Promotional banners
POST /api/storefront/banners               # Admin: {title, image_url, placement, link_url?}
PATCH /api/storefront/banners/:id          # Admin
DELETE /api/storefront/banners/:id         # Admin
GET  /api/storefront/early-supporters      # Early supporters list
POST /api/storefront/early-supporters      # Admin: {name, photo_url?, social_links?, note?}
POST /api/storefront/newsletter            # {email, full_name, source?}
POST /api/storefront/newsletter/unsubscribe # {email}
GET  /api/storefront/newsletter            # Admin: subscriber list
```

---

### Challenges & Badges

```http
GET  /api/challenges               # Active challenges (time-boxed milestones)
GET  /api/challenges/badges        # Badges (permanent milestones, no time_window)
GET  /api/challenges/my            # My progress on all milestones
POST /api/challenges/:id/complete  # Claim a completed challenge
POST /api/challenges/social-follow # Self-declare social media follow (once)
GET  /api/challenges/admin         # Admin: all milestones
POST /api/challenges/admin         # Admin: {title, trigger_type, trigger_value, hp_awarded, time_window?}
PATCH /api/challenges/admin/:id    # Admin: update milestone
DELETE /api/challenges/admin/:id   # Admin: deactivate
POST /api/challenges/admin/:id/grant  # Admin: {user_id} — manually grant
```

**Trigger types:** `orders_count`, `hp_earned`, `referrals_count`, `reviews_count`, `social_share`, `social_follow`, `streak_days`, `wallet_topup_count`, `order_streak_weeks`

**Time windows:** `weekly`, `monthly`, or omit for permanent badge.

---

### Graduation

```http
POST /api/graduation/claim
Authorization: Bearer <student_token>
```
Claims HP reward for reaching graduation-level `academic_level`. Requires `academic_level >= graduation_min_level` (system setting, default 400). One-time per user.

---

### Health & Webhooks

```http
GET  /api/health              # {api: "Holy Grills", status: "ok", checks: {supabase: "connected"}}
POST /api/webhooks/paystack   # Paystack payment events — requires x-paystack-signature header
POST /api/webhooks/flutterwave # Flutterwave events — requires verif-hash header
```

---

## 4. Error Handling

### Standard Error Response
```json
{ "error": "Human-readable error message" }
```
Some endpoints include extra fields:
```json
{
  "error": "Insufficient active HP. Have 50, need 100",
  "have": 50,
  "need": 100
}
```

### HTTP Status Codes
| Code | Meaning | UI Action |
|---|---|---|
| `200` | OK | Use response data |
| `201` | Created | Show success, update UI |
| `400` | Bad Request / Validation error | Show `error` field to user |
| `401` | Unauthenticated / Token expired | Refresh token or redirect to login |
| `403` | Forbidden / Wrong role | Show "access denied" |
| `404` | Not Found | Show "item not found" |
| `409` | Conflict (already exists, wrong state) | Show specific error message |
| `429` | Rate limited | Back off and retry |
| `500` | Server error | Show generic error, log to monitoring |
| `502` | External service unavailable | Show "service temporarily unavailable" |

### Common Error Strings (display directly to users)
- `"Minimum HP transfer is 10 HP"` → show validation error
- `"Insufficient active HP. Have X, need Y"` → show balance info
- `"Order cannot be cancelled at this stage"` → order already processing
- `"This promo code is not valid"` → code expired or invalid
- `"The kitchen has reached its daily order capacity. Please try again tomorrow"` → sold out for day
- `"Event is at full capacity"` → event full
- `"Monthly free-activity HP cap reached"` → inform user to wait

---

## 5. HP (Holy Points) System

### Tier System
| Tier | Slug | HP Range | Perks |
|---|---|---|---|
| Newbie | `newbie` | 0 – 499 | Basic access |
| Scout | `scout` | 500 – 999 | Priority queue |
| Regular | `regular` | 1000 – 2499 | Exclusive rewards |
| Champion | `champion` | 2500 – 4999 | Premium events |
| Legend | `legend` | 5000+ | Hall of Fame eligible |

Tier thresholds are configurable via env: `HP_TIER_SCOUT_MIN`, `HP_TIER_REGULAR_MIN`, etc.

### HP Earning Paths
| Source | Trigger | Amount |
|---|---|---|
| Food Order | On delivery | `hp_earn_value` per item |
| Order Review | Submit review | `review_hp` (default 20) |
| Referral | Referee's first order delivered | `referral_hp` (default 75) |
| Welcome Bonus | First order delivered | `welcome_bonus_hp` (default 50) |
| Birthday | On birthday (via cron) | `birthday_hp` (default 150) |
| Social Share | Share order link (once/day) | `social_share_hp` (default 25) |
| Event Check-In | Attend event | `hp_reward` set per event |
| Challenges | Complete milestone | `hp_awarded` set per challenge |
| Login Streak | Daily login (week completion) | 25 / 40 / 60 / 80 HP |
| Spin Wheel | Lucky spin | Prize varies |
| Admin Grant | Manual | Any amount |
| Graduation | Claim at academic_level 400+ | Configured HP |
| Anniversary | Monthly milestones | Configured HP |

### Pending vs Active HP
- **Pending HP**: Awarded immediately on order placement but **locked**. Unlocks at delivery.
- **Active HP**: Can be spent on rewards, transfers, spin wheel.
- **Monthly Cap**: Free-activity HP (non-food-order) is capped at ~800/month. `MONTHLY_HP_CAP` env var.

### HP UI Recommendations
```
Active HP:  1,250  ✅ (spendable)
Pending HP:   350  🕐 (releases on delivery)
Total:      1,600
```
Always show both separately. Never merge them.

---

## 6. Order Lifecycle

### Guest Checkout Flow
1. POST `/api/orders` without `Authorization` header, include `guest_name` + `guest_phone`
2. Only `payment_method: "card"` allowed for guests
3. Response includes `claim_token`
4. Guest can view order via `GET /api/orders/:id?claim_token=<token>`
5. Authenticated user can claim via `POST /api/orders/:id/claim { claim_token }`

### Squad Order Flow
1. Create order with `squad_emails` (at least 2 additional emails) and `squad_name`
2. Server notifies squad members via email/push
3. Add more members later via `POST /api/orders/:id/squad-members`
4. HP earned is split among all squad members (if `split_hp: true`)

### Scheduled Order Flow
1. Set `is_scheduled: true` and `scheduled_date: "YYYY-MM-DD"` in order payload
2. Order stays in "scheduled" state until the scheduled date
3. Cancel via `DELETE /api/orders/:id/scheduled`
4. List via `GET /api/orders/scheduled`

### Payment Methods
| Method | How it works |
|---|---|
| `card` | Returns Paystack checkout URL — redirect user, Paystack webhook confirms payment |
| `wallet` | Deducted immediately from wallet balance |
| `split` | Wallet covers part, card covers the rest |

---

## 7. Wallet & Payments

### Fund via Card (Paystack Flow)
```
1. POST /api/wallet/fund/card { amount: 5000, callback_url: "https://yourapp.com/wallet/return" }
2. Receive: { authorization_url, reference, access_code }
3. Redirect user to authorization_url (or embed in WebView)
4. Paystack redirects to callback_url with ?reference=xxx
5. Paystack webhook (POST /api/webhooks/paystack) automatically credits wallet
```

### Fund via Bank (Virtual Account)
```
POST /api/wallet/fund/bank
```
Returns NUBAN virtual account number. User transfers from any bank. Webhook credits wallet.
> Note: Requires Paystack dedicated NUBAN feature (may not be available in sandbox).

### Withdraw

> ⚠️ **Wallet withdrawal has been removed.** Do not implement or display withdrawal UI. The `/wallet/withdraw` endpoint returns 404.

---

## 8. Notification System

### Web Push Subscription
```javascript
// After getting user permission:
const sub = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: vapidKey });
await fetch('/api/push/subscribe', {
  method: 'POST', headers: { ..., Authorization: `Bearer ${token}` },
  body: JSON.stringify({ subscription: sub })
});
```

### Mobile Push (FCM/APNs)
```http
POST /api/auth/device-token
{ "token": "device-fcm-or-apns-token", "platform": "ios" }
```

### In-App Inbox
Poll `GET /api/notifications?unread_only=true&limit=5` every 30 seconds when app is in foreground. Show badge count from `unread_count` field.

### Throttling
Push notifications are throttled server-side:
- `notification_gap_minutes` (default 30): Min gap between pushes per user
- `notification_daily_cap` (default 10): Max pushes per user per day

---

## 9. Polling & State Management

### No WebSockets — Use Polling

| Screen | Endpoint | Interval |
|---|---|---|
| Active order tracking (student) | `GET /api/orders/:id` | 15s |
| Kitchen queue | `GET /api/kitchen/queue` | 10s |
| Rider batch | `GET /api/riders/my-batch` | 15s |
| Notification badge | `GET /api/notifications?unread_only=true&limit=1` | 30s |
| HP balance | `GET /api/hp/balance` | 60s |

### Local Storage Strategy
| Data | Storage | Notes |
|---|---|---|
| `access_token` | Memory (or SecureStorage) | Short-lived; refresh on 401 |
| `refresh_token` | SecureStorage / HttpOnly Cookie | Persist across sessions |
| Cart | **Do NOT cache** — backend is source of truth | Always fetch from `GET /api/cart` |
| HP balance | Can cache 60s | Show cached, refresh in background |
| Menu items | Cache up to 5 min | Rarely changes |
| User profile | Cache until logout | Refresh on app open |

### Optimistic UI
Safe for: cart operations, notification mark-read.  
Avoid for: order status, HP balance, wallet balance — always confirm with server before showing final state.

---

## 10. Role-Gated UI Flows

### Student App
- Home → Storefront sections, featured items, HP balance banner
- Menu → Browse, filter by category, search, add to cart
- Cart → Review items, select hostel/gate, apply promo, choose payment
- Orders → Active order tracking, order history, reorder
- HP Wallet → Balance (active/pending), transactions, tier progress
- Rewards → Browse, redeem with HP
- Leaderboard → Rankings, my rank, squad
- Events → List, register, QR ticket display
- Marketplace → Browse, purchase
- Challenges → Active challenges, badges, progress
- Notifications → Inbox, preferences
- Profile → Settings, addresses, referral code, logout

### Kitchen Display
- Queue → Active orders, mark preparing / ready
- Batch Summary → Items needed per delivery window
- Scheduled → Upcoming scheduled orders
- Metrics → Daily throughput

### Rider App
- Batch → Assigned orders for pickup
- Pickup → Confirm pickup, navigate to customer
- Deliver → Confirm delivery
- Earnings → Daily/weekly earnings and stats
- Availability → Toggle online/offline with location

### Admin Panel
- Users → Search, view history, adjust HP, manage roles
- Orders → All orders, status, refunds
- Menu → Categories, items, add-ons, availability
- Delivery → Windows (create/close/reopen), batches, fees
- Promo Codes → Create, edit, usage analytics
- Analytics → Revenue, HP, retention, cohorts
- Events → Create/edit, check-in monitoring
- Marketplace → Listings, codes, vendor requests
- Settings → System settings, HP amounts, feature flags
- Rewards → Manage catalog, redemptions

---

## 11. Key Config & Feature Flags

All HP amounts, spin costs, and feature toggles are configured via environment variables and `system_settings` (DB table). Admins can override DB values via `PATCH /api/admin/settings/:key`.

### Environment Variables (HP Economy)
| Env Var | Description | Default |
|---|---|---|
| `SIGNUP_BONUS_HP` | HP on registration | 0 |
| `WELCOME_BONUS_HP` | HP on first delivery | 50 |
| `REFERRAL_HP` | Referrer bonus per referee | 75 |
| `BIRTHDAY_HP` | Birthday HP grant | 150 |
| `REVIEW_HP` | HP per review | 20 |
| `SOCIAL_SHARE_HP` | HP per social share | 25 |
| `EVENT_CHECKIN_HP` | Default event check-in HP | 40 |
| `WALLET_TOPUP_HP` | HP per wallet top-up | 5 |
| `MONTHLY_HP_CAP` | Monthly free-activity HP cap | 800 |
| `SPIN_COST_HP` | HP cost for non-first spins | 10 |
| `HP_TRANSFER_MIN_AMOUNT` | Min HP in P2P transfer | 10 |
| `HP_BUNDLE_MIN_PURCHASE` | Min HP in bundle purchase | 100 |
| `HP_BUNDLE_PRICE_PER_HP` | NGN per HP bundle | 5.0 |

### Login Streak Weekly Bonuses
| Week | Env Var | Default HP |
|---|---|---|
| Week 1 | `LOGIN_STREAK_WEEK1_HP` | 25 |
| Week 2 | `LOGIN_STREAK_WEEK2_HP` | 40 |
| Week 3 | `LOGIN_STREAK_WEEK3_HP` | 60 |
| Week 4 | `LOGIN_STREAK_WEEK4_HP` | 80 |

### Feature Flags via System Settings
- `squad_order_enabled` → `SQUAD_ORDER_ENABLED`
- `spin_prizes` → JSON array of spin wheel prizes
- `hp_multiplier_active` → Live HP multiplier (1x, 2x, 3x)
- `ordering_window_open_time` → `HH:MM` (WAT) when ordering opens
- `ordering_window_close_time` → `HH:MM` (WAT) when ordering closes

---

## 12. Deployment Configuration

### Required Environment Variables
```bash
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# Auth
JWT_SECRET=your-secret-key-here
JWT_ALGORITHM=HS256
SECRET_KEY=flask-secret-key

# Payments
PAYSTACK_PUBLIC_KEY=pk_live_xxx
PAYSTACK_SECRET_KEY=sk_live_xxx
PAYSTACK_WEBHOOK_SECRET=whsec_xxx

# Redis (for Celery background tasks)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# HP Economy (all optional, have defaults)
SIGNUP_BONUS_HP=0
WELCOME_BONUS_HP=50
REFERRAL_HP=75
...
```

### CORS
Development: All origins allowed.  
Production: Set `CORS_ORIGINS` env var to comma-separated allowed origins.

### Health Check Endpoint
Monitor: `GET /api/health`
```json
{
  "api": "Holy Grills",
  "status": "ok",
  "checks": { "supabase": "connected" },
  "timestamp": "2026-07-16T14:00:00Z"
}
```
Alert if `supabase` is not `"connected"` or status code is not `200`.

---

## Appendix: Guest vs Authenticated Order Comparison

| Feature | Guest | Authenticated |
|---|---|---|
| Payment | `card` only | `wallet`, `card`, `split` |
| HP earned | No | Yes (food HP, welcome bonus) |
| Order history | Via `claim_token` only | Full history |
| Squad orders | No | Yes |
| Scheduled orders | No | Yes |
| Promo codes | Yes | Yes |
| Claim order later | — | `POST /orders/:id/claim` with `claim_token` |

---

## 13. Database Schema Reference

### Key Entity Relationships

```
profiles ──< orders >── order_items >── menu_items >── menu_categories
profiles ──< hp_transactions
profiles ──< wallet_transactions
profiles ──< cart_items >── menu_items
profiles ──< notifications
profiles ──< event_registrations >── events
profiles ──< reward_redemptions >── rewards
profiles ──< marketplace_purchases >── marketplace_listings
profiles ──< milestones (challenges/badges)
profiles ──< order_locks
orders   ──< squad_members >── profiles
orders    ── delivery_batches >── riders
```

### Order Statuses — with UI Display & Colour

| Value | Display Text | Suggested Colour | Notes |
|---|---|---|---|
| `received` | Received | `#F97316` Orange | Kitchen hasn't started |
| `preparing` | Preparing | `#3B82F6` Blue | Kitchen working — no cancellation |
| `ready` | Ready | `#10B981` Green | Waiting for rider |
| `assigned` | Assigned | `#8B5CF6` Purple | Rider batch assigned |
| `out_for_delivery` | Out for Delivery | `#06B6D4` Teal | Rider in transit |
| `delivered` | Delivered | `#16A34A` Dark Green | Terminal — happy path |
| `delivery_attempted` | Delivery Attempted | `#EF4444` Red | **urgency: high** — show modal |
| `unclaimed` | Unclaimed | `#9CA3AF` Gray | Order not collected |
| `cancelled` | Cancelled | `#EF4444` Red | Terminal |
| `refunded` | Refunded | `#6B7280` Gray | Terminal |

### HP Transaction Types — with UI Display

| Type | Display Text | Notes |
|---|---|---|
| `earned` | HP Earned | From food orders, reviews, bonuses |
| `spent` | HP Spent | Rewards, spin wheel, transfers out |
| `expired` | HP Expired | After 120 days inactivity |
| `transferred_in` | HP Received | P2P transfer received |
| `transferred_out` | HP Sent | P2P transfer sent |
| `pending` | HP Pending | Locked until order delivered |
| `unlocked` | HP Unlocked | Pending released to active |

### User Roles — with Access

| Role | Display | Access |
|---|---|---|
| `student` | Student | Normal user — orders, HP, wallet, events |
| `kitchen` | Kitchen Staff | + Kitchen queue management |
| `rider` | Rider | + Delivery batch management |
| `admin` | Admin | Full access including all management |
| `super_admin` | Super Admin | Same as admin + role management |

### Payment Methods

| Value | Display | How It Works |
|---|---|---|
| `wallet` | Wallet | Deducted immediately from wallet balance |
| `card` | Card | Paystack checkout → webhook confirms |
| `split` | Wallet + Card | Wallet covers part; card covers the rest |

### Delivery Types

| Value | Display | Notes |
|---|---|---|
| `on_campus` | On Campus | Delivery to a hostel by UUID |
| `off_campus` | Off Campus | Delivery to a gate; lat/lon used for fee |

### Event Funding Sources

| Value | Notes |
|---|---|
| `host-funded` | Event host pays for catering |
| `hg-funded` | Holy Grills subsidises the event |

### Marketplace Listing Types

| Value | Display | Notes |
|---|---|---|
| `code` | Access Code | Delivers a digital code from inventory |
| `service` | Service | Student-offered service |
| `product` | Product | Physical product |
| `experience` | Experience | Event / activity |

### Reward Types

| Value | Display | Notes |
|---|---|---|
| `voucher` | Voucher | Redeemable voucher code |
| `free_item` | Free Item | Free menu item |
| `discount` | Discount | % or flat discount on next order |
| `experience` | Experience | Event / activity access |
| `product` | Product | Physical product |

### Challenge Time Windows

| Value | Notes |
|---|---|
| `null` / absent | Permanent badge — earned once, never resets |
| `weekly` | Resets every week |
| `monthly` | Resets every month |

### Enum Values — Complete Reference

| Field | Values | Notes |
|---|---|---|
| `role` | `student` `admin` `kitchen` `rider` `super_admin` | — |
| `order_status` | `received` `preparing` `ready` `assigned` `out_for_delivery` `delivered` `delivery_attempted` `unclaimed` `cancelled` `refunded` | See state machine in §6 |
| `payment_method` | `wallet` `card` `split` | `split` = part wallet, rest card |
| `delivery_type` | `on_campus` `off_campus` | — |
| `listing_type` | `code` `service` `product` `experience` | Marketplace |
| `listing_status` | `pending` `approved` `rejected` `draft` `active` `archived` | — |
| `discount_type` | `percentage` `flat` | Promo codes |
| `promo_scope` | `cart` `item` | Cart = whole order; item = per item |
| `reward_type` (rewards) | `voucher` `free_item` `discount` `experience` `product` | — |
| `reward_type` (order_locks) | `discount` `hp` | What the lock redeems |
| `redemption_status` | `pending` `fulfilled` `rejected` | — |
| `lock_status` | `active` `cancelled` `used` | — |
| `hp_transaction_type` | `earned` `spent` `expired` `transferred_in` `transferred_out` `pending` `unlocked` | — |
| `notification_channel` | `push` `in_app` `email` | — |
| `batch_status` | `pending` `active` `completed` `cancelled` | Delivery batches |
| `catering_status` | `pending` `reviewed` `confirmed` `rejected` | — |
| `gift_status` | `pending` `claimed` `returned` | First-order gifts |
| `challenge_type` | `one_time` `recurring` `daily` `weekly` `monthly` | Milestones |
| `trigger_type` (milestones) | `orders_count` `hp_earned` `referrals_count` `reviews_count` `social_share` `social_follow` `streak_days` `wallet_topup_count` `order_streak_weeks` | — |
| `time_window` (milestones) | `weekly` `monthly` or `null` | null = permanent badge |
| `section_type` (storefront) | `hero` `banner` `promo` `faq` + any string | Not constrained by DB |
| `platform` (push tokens) | `ios` `android` `web` | — |

### TypeScript Interface Reference

```typescript
// Core entities — use as a starting point; extend with extra fields from the API
interface User {
  id: string;                    // UUID
  email: string;
  full_name: string;
  phone?: string;
  date_of_birth?: string;        // YYYY-MM-DD
  role: 'student' | 'admin' | 'kitchen' | 'rider' | 'super_admin';
  referral_code: string;
  is_active: boolean;
  hp_balance: { active: number; pending: number; total: number };
  tier: { name: string; slug: string; multiplier: number };
  wallet: { balance: number; virtual_account?: VirtualAccount };
}

interface VirtualAccount {
  account_number: string;
  bank_name: string;
  account_name: string;
}

interface Order {
  id: string;
  status: OrderStatus;
  total_amount: number;
  delivery_fee: number;
  hp_discount: number;
  payment_method: 'wallet' | 'card' | 'split';
  delivery_type: 'on_campus' | 'off_campus';
  is_scheduled: boolean;
  is_squad_order: boolean;
  squad_name?: string;
  claim_token?: string;          // guest orders only
  items: OrderItem[];
  created_at: string;            // ISO 8601
}

type OrderStatus =
  | 'received' | 'preparing' | 'ready' | 'assigned'
  | 'out_for_delivery' | 'delivered' | 'delivery_attempted'
  | 'unclaimed' | 'cancelled' | 'refunded';

interface OrderItem {
  menu_item_id: string;
  name: string;
  quantity: number;
  unit_price: number;
  notes?: string;
  addons: AddonOption[];
}

interface MenuItem {
  id: string;
  name: string;
  description?: string;
  price: number;                 // NGN
  hp_earn_value: number;
  is_available: boolean;
  is_featured: boolean;
  is_sold_out: boolean;
  remaining_today?: number;      // null = unlimited
  image_url?: string;
  category_id: string;
  addon_groups: AddonGroup[];
}

interface AddonGroup {
  id: string;
  name: string;
  min_select: number;
  max_select: number;
  is_required: boolean;          // min_select > 0
  options: AddonOption[];
}

interface AddonOption {
  id: string;
  name: string;
  price_delta: number;           // extra cost in NGN
}

interface HPBalance {
  active: number;
  pending: number;
  total: number;
  pending_ceiling: number;
  tier: { name: string; multiplier: number };
}

interface Notification {
  id: string;
  type: string;                  // see §15
  channel: 'push' | 'in_app' | 'email';
  title: string;
  body: string;
  is_read: boolean;
  action_url?: string;           // deep-link
  metadata: {
    reference_id?: string;       // UUID of the related entity
    reference_type?: string;     // e.g. 'order', 'hp', 'event'
    urgency?: 'high';            // only set for delivery_attempted
  };
  created_at: string;
}

interface MarketplaceListing {
  id: string;
  title: string;
  description?: string;
  listing_type: 'code' | 'service' | 'product' | 'experience';
  price: number;
  hp_price?: number;
  image_url?: string;
  is_active: boolean;
  codes_remaining?: number;      // for listing_type = 'code'
}

interface Reward {
  id: string;
  title: string;
  description?: string;
  reward_type: 'voucher' | 'free_item' | 'discount' | 'experience' | 'product';
  hp_cost: number;
  stock?: number;                // null = unlimited
  image_url?: string;
  is_active: boolean;
}

interface OrderLock {
  id: string;
  locked_date: string;           // YYYY-MM-DD
  reward_type: 'discount' | 'hp';
  discount_pct?: number;
  reward_hp_amount?: number;
  status: 'active' | 'cancelled' | 'used';
  reschedule_count: number;      // max 1 reschedule
}
```

---

## 14. UI/UX Flow Diagrams

### 14.1 Ordering Flow — Gated Checks

```
User opens app
  │
  ├─ GET /storefront/operating-hours
  │    └─ Kitchen closed? → Show "Ordering is closed" banner; hide Add-to-Cart
  │
  ├─ GET /menu/kitchen-capacity
  │    └─ remaining = 0? → Show "Sold out for today" state; disable checkout
  │
  ├─ GET /menu/items (check each item's is_sold_out / is_available)
  │    └─ is_sold_out=true → grey card + "Sold out" badge; block add-to-cart
  │    └─ is_available=false → same treatment (admin-disabled)
  │
  └─ Checkout → GET /orders/delivery-windows/status
       └─ Not open → block place-order button with reason string
```

### 14.2 Payment Flow (Card / Wallet / Split)

```
[Checkout]
  │
  ├─ payment_method = "wallet"
  │    └─ POST /orders → immediate debit; go to order tracking
  │
  ├─ payment_method = "card"
  │    └─ POST /wallet/fund/card { amount, callback_url } (for wallet top-up)
  │    │   OR pass paystack_reference directly on POST /orders
  │    └─ Redirect → Paystack checkout URL
  │         └─ Paystack webhook fires → wallet credited / order confirmed
  │         └─ App polls GET /orders/:id until status ≠ 'received'
  │
  └─ payment_method = "split"
       ├─ wallet_amount = partial amount from wallet
       ├─ rest charged via Paystack (paystack_reference required)
       └─ Both verified server-side before order confirmed
```

### 14.3 Guest Checkout Flow

```
[No auth token in request]
  │
  ├─ Include: guest_name, guest_phone
  ├─ payment_method must be "card" (wallet/split not allowed for guests)
  ├─ Response includes claim_token
  │
  ├─ Guest tracks order: GET /orders/:id?claim_token=<token>
  │
  └─ Later (logged-in user wants history):
       POST /orders/:id/claim { claim_token }
       → order transferred to authenticated account
```

### 14.4 Squad Order Flow

```
POST /orders { squad_name, squad_emails: ["a@futa.edu.ng", "b@futa.edu.ng"] }
  │
  ├─ Server notifies each email (push if registered, email invite if not)
  ├─ squad_members can be added later via POST /orders/:id/squad-members
  │
  ├─ When order delivered:
  │    └─ POST /orders/:id/share-hp → HP split equally among squad members
  │
  └─ Show "Squad Order" badge on order card
       └─ Trigger squad popup prompt when user has ≥2 friends registered
```

### 14.5 Squad Popup Trigger Logic

Show squad order promotional popup when **all** of the following are true:
1. User has placed ≥1 order before
2. User has ≥2 contacts who are also registered (check referral count)
3. Current cart has ≥3 items (squad discount eligible)
4. User has not dismissed the popup in the last 7 days (client-side flag)

### 14.6 HP Unlock Flow (Pending → Active)

```
Order placed → HP earned lands in "pending" pool
  │
  ├─ Order status = "delivered" → HP automatically unlocked to "active"
  │
  ├─ HP expiry warning at day 70, 95, 118 of inactivity
  │    └─ Push type: "winback" / "hp_decay_warning"
  │
  └─ HP expired (120 days inactivity) → type: "hp_decay_applied"
       └─ 10%/month decay applied; user notified
```

### 14.7 Order Lock Flow

```
User picks a future date (locked_date)
  │
  ├─ reward_type = "discount": choose discount_pct (1–50%)
  ├─ reward_type = "hp": choose reward_hp_amount
  │
  ├─ POST /order-locks → lock created, status = "active"
  │
  ├─ On locked_date:
  │    └─ User places order → discount/HP applied automatically
  │    └─ Lock status → "used"
  │
  ├─ Reschedule (once only):
  │    └─ PATCH /order-locks/:id/reschedule { locked_date: "new-date" }
  │    └─ reschedule_count becomes 1; further reschedules blocked
  │
  └─ Cancel: DELETE /order-locks/:id → status = "cancelled"
```

### 14.8 Kitchen Closed State

Show a full-screen or sticky "Kitchen Closed" state when any of these is true:
- `GET /storefront/operating-hours` → today's entry shows `is_open: false`
- `GET /orders/delivery-windows/status` → `{ is_open: false, reason: "..." }`
- `GET /menu/kitchen-capacity` → `{ remaining: 0 }`

```
Kitchen Closed UI:
  ┌─────────────────────────────────┐
  │  🍽️  We're closed right now     │
  │                                 │
  │  Ordering opens Mon–Fri 8am–4pm │
  │                                 │
  │  [ Set a scheduled order ]      │  ← link to scheduled order flow
  │  [ Browse the menu ]            │  ← still show read-only menu
  └─────────────────────────────────┘
```

---

## 15. Notification Payload Structures

### Notification Object Shape

```json
{
  "id": "uuid",
  "type": "order_ready",
  "channel": "in_app",
  "title": "Order Ready 🎉",
  "body": "Your order is ready for collection.",
  "is_read": false,
  "action_url": "/orders/uuid",
  "metadata": {
    "reference_id": "order-uuid",
    "reference_type": "order",
    "urgency": null
  },
  "created_at": "2026-07-16T14:00:00Z"
}
```

### `action_url` → Screen Mapping

| `type` | `action_url` example | Target screen |
|---|---|---|
| `order_confirmed` `order_preparing` `order_ready` `order_assigned` `order_out_for_delivery` `order_delivered` `order_cancelled` `order_refunded` | `/orders/:order_id` | Order tracking |
| `order_delivery_attempted` | `/orders/:order_id` | **urgency: high** — show immediately as modal |
| `order_unclaimed` | `/orders/:order_id` | Order detail |
| `hp_earned` `hp_unlocked` `hp_earned_*` | `/hp` | HP wallet |
| `tier_upgrade` `tier_downgrade` `tier_grace_period` | `/hp/tier` | Tier progress |
| `wallet_funded_card` `wallet_funded_bank` `wallet_funded` | `/wallet` | Wallet screen |
| `birthday_bonus` | `/hp` | HP wallet |
| `referral_hp_earned` `referral_milestone` | `/referrals` | Referrals screen |
| `leaderboard_rank` `hall_of_fame` | `/leaderboard` | Leaderboard |
| `squad_order` `squad_hp_split` `squad_order_ready` | `/orders/:order_id` | Squad order |
| `event_registered` `event_checkin` | `/events/:event_id` | Event detail |
| `challenge_complete` `challenge_progress` `badge_earned` | `/challenges` | Challenges |
| `marketplace_purchase` `marketplace_access_code` | `/marketplace/purchases` | Marketplace purchases |
| `reward_redeemed` `reward_fulfilled` | `/rewards/redemptions` | Redemptions |
| `abandoned_cart` `abandoned_cart_nudge` | `/cart` | Cart |
| `order_lock_reminder` `order_lock_redeemed_*` | `/order-locks` | Order locks |
| `hp_decay_warning` `hp_decay_applied` | `/hp` | HP wallet |
| `winback` | `/menu` | Menu (re-engagement) |
| `first_order_gift` | `/orders/:order_id` | Order detail |
| `review_request` | `/orders/:order_id/review` | Review screen |
| `share_prompt` | `/orders/:order_id` | Share sheet |
| `system_announcement` `blast` | `/` | Home |

### Priority Levels

| Priority | Types | UI behaviour |
|---|---|---|
| **Critical / high** | `order_delivery_attempted` | Show as modal/overlay immediately; do not suppress |
| **Normal** | All order lifecycle, HP, wallet | Standard banner / badge |
| **Low / background** | `abandoned_cart`, `winback`, `share_prompt` | Badge only; no banner |

> Push notifications are throttled: min `notification_gap_minutes` (default 30) between pushes, max `notification_daily_cap` (default 10) per user per day. This is server-controlled — no client logic needed.

### In-App Inbox Polling

```javascript
// Poll every 30s while app is in foreground
const POLL_MS = 30_000;
const pollNotifications = () =>
  fetch('/api/notifications?unread_only=true&limit=1', { headers: authHeaders })
    .then(r => r.json())
    .then(({ total }) => updateBadge(total));
```

---

## 16. Image Upload Strategy

### How it works

The backend stores **only URLs** in `image_url` fields. It does **not** accept binary file uploads. The frontend is responsible for uploading images to a CDN (Cloudinary recommended) and then saving the resulting URL via the relevant API call.

```
Frontend flow:
  1. User selects image file
  2. Frontend uploads directly to Cloudinary (unsigned upload or signed preset)
  3. Cloudinary returns { secure_url, public_id }
  4. Frontend sends secure_url in the API request body (e.g. PATCH /menu/items/:id { image_url })
```

### Cloudinary Configuration (recommended)

```javascript
// Unsigned upload to a preset
const uploadToCloudinary = async (file: File): Promise<string> => {
  const form = new FormData();
  form.append('file', file);
  form.append('upload_preset', 'holy_grills_unsigned');  // create in Cloudinary dashboard
  form.append('folder', 'holy_grills');

  const res = await fetch(
    `https://api.cloudinary.com/v1_1/${CLOUDINARY_CLOUD_NAME}/image/upload`,
    { method: 'POST', body: form }
  );
  const data = await res.json();
  return data.secure_url;  // pass this to the API
};
```

### Supported `image_url` fields per entity

| Entity | Field | API endpoint to update |
|---|---|---|
| Menu item | `image_url` | `PATCH /api/menu/items/:id` |
| Menu category | `image_url` | `PATCH /api/menu/categories/:id` |
| Reward | `image_url` | `PATCH /api/rewards/:id` |
| Marketplace listing | `image_url` | `PATCH /api/marketplace/admin/listings/:id` |
| Event | `image_url` | `PATCH /api/events/:id` |
| Storefront banner | `image_url` | `PATCH /api/storefront/banners/:id` |
| Early supporter | `photo_url` | `POST /api/storefront/early-supporters` |
| User avatar | — | Not yet implemented; store in Cloudinary and reference via profile |

### Recommended formats & limits

| Constraint | Value |
|---|---|
| Accepted formats | JPEG, PNG, WebP |
| Max file size (client-side enforce) | 5 MB |
| Recommended dimensions | Square 1:1 for items/rewards; 16:9 for banners/events |
| Delivery | Always use Cloudinary transformation URL for resizing: `c_fill,w_400,h_400,q_auto,f_auto` |

---

## 17. Accessibility Requirements

### Core Requirements (WCAG 2.1 AA)

| Requirement | Implementation note |
|---|---|
| **Colour contrast** | Minimum 4.5:1 for body text, 3:1 for large text and UI components |
| **Touch targets** | Minimum 44×44 pt (iOS) / 48×48 dp (Android) |
| **Focus management** | After opening a modal/sheet, move focus to it; restore on close |
| **Screen-reader labels** | Every icon-only button needs `accessibilityLabel` / `aria-label` |
| **Dynamic type** | Support OS font size scaling; avoid fixed `px` font sizes |
| **Loading states** | Announce loading start/end to screen readers (`aria-live="polite"`) |
| **Error messages** | Associate errors with inputs (`aria-describedby` / `accessibilityHint`) |

### HP & Wallet Displays

```
// BAD: screen reader reads "1250" with no context
<Text>{hpBalance.active}</Text>

// GOOD
<Text accessibilityLabel={`${hpBalance.active} Holy Points active`}>
  {hpBalance.active.toLocaleString()} HP
</Text>
```

### Order Status Announcements

When order status changes (detected via polling), announce it via `AccessibilityInfo.announceForAccessibility('Your order is now being prepared.')` (React Native) or an `aria-live` region (web).

### Colour Usage

Do not convey meaning through colour alone. Always pair colour with an icon or text label:
- Order status chips: colour + status text
- HP tier badge: colour + tier name
- Pending vs active HP: never distinguish by colour alone — use labels

---

## 18. Analytics & Tracking

### Recommended Screen Views

Track these events in your analytics tool (Mixpanel, Amplitude, Firebase, etc.):

| Event name | Trigger | Key properties |
|---|---|---|
| `screen_home` | Home tab focused | `user_tier`, `hp_balance` |
| `screen_menu` | Menu opened | — |
| `screen_menu_item` | Item detail viewed | `item_id`, `item_name`, `price` |
| `screen_cart` | Cart opened | `item_count`, `subtotal` |
| `screen_checkout` | Checkout started | `payment_method`, `delivery_type` |
| `screen_order_tracking` | Tracking screen opened | `order_status` |
| `screen_hp_wallet` | HP wallet opened | `active_hp`, `pending_hp`, `tier_slug` |
| `screen_rewards` | Rewards browser opened | — |
| `screen_leaderboard` | Leaderboard opened | `period_type` |
| `screen_events` | Events list opened | — |
| `screen_marketplace` | Marketplace opened | — |
| `screen_challenges` | Challenges opened | — |

### Recommended Conversion Events

| Event name | Trigger |
|---|---|
| `order_started` | User taps "Place Order" |
| `order_completed` | API returns `201` on `POST /orders` |
| `payment_failed` | API returns error on card payment |
| `promo_applied` | Promo code validated successfully |
| `hp_earned` | `hp_earned` notification received |
| `reward_redeemed` | `POST /rewards/:id/redeem` → 200 |
| `spin_wheel_spun` | `POST /hp/spin` → 200 |
| `event_registered` | `POST /events/:id/register` → 200 |
| `referral_shared` | User copies/shares referral link |
| `squad_created` | Order created with `squad_emails` |
| `challenge_completed` | `POST /challenges/:id/complete` → 200 |

### User Properties to Set

```javascript
analytics.identify(userId, {
  role:          user.role,
  tier:          user.tier.slug,
  hp_active:     user.hp_balance.active,
  hp_pending:    user.hp_balance.pending,
  wallet_bal:    user.wallet.balance,
  referral_code: user.referral_code,
  created_at:    user.created_at,
});
```

### Conversion Funnels to Monitor

1. **Checkout funnel:** Menu → Item detail → Add to Cart → Checkout → Order confirmed
2. **HP engagement:** HP balance viewed → Reward browsed → Reward redeemed
3. **Referral funnel:** Referral link copied → New user registered → First order delivered

---

## 19. Local Storage & Caching Strategy

### Extended Reference

| Data | Storage location | TTL / Invalidation |
|---|---|---|
| `access_token` | Memory (in-app state) | Clear on 401 refresh failure |
| `refresh_token` | SecureStorage / HttpOnly cookie | Clear on logout / logout-all-devices |
| User profile | SecureStorage or app cache | Refresh on app resume; clear on logout |
| HP balance | App state / memory | Cache 60s; refresh in background |
| Menu items | App cache | 5 min TTL; invalidate on admin update |
| Menu categories | App cache | 10 min TTL |
| Delivery hostels/gates | App cache | 30 min TTL |
| Notification badge count | App state | Poll every 30s; clear on mark-read-all |
| Active order status | App state | Poll every 15s while tracking screen open |
| Cart | **No caching** | Always fetch from `GET /api/cart` |
| HP transactions | On-demand | Do not cache; always fetch fresh |
| Leaderboard | App cache | 2 min TTL |
| Squad popup dismissed | SecureStorage | 7-day expiry |
| Ordering hours | App cache | 5 min TTL |

### Token Rotation Pattern

```javascript
const apiFetch = async (url: string, opts: RequestInit = {}) => {
  let res = await fetch(url, withAuth(opts, accessToken));
  if (res.status === 401) {
    const { access_token, refresh_token } = await rotateTokens(refreshToken);
    saveTokens(access_token, refresh_token);
    res = await fetch(url, withAuth(opts, access_token));  // retry once
  }
  return res;
};
```

### What NOT to Cache

- **Cart contents** — the backend is the source of truth; concurrent sessions can modify it.
- **HP balance for spend decisions** — always re-fetch before showing a "Redeem" button to avoid showing spendable balance that has already been used.
- **Order status** — never display a cached status as final; always confirm with server.
- **Wallet balance before payment** — fetch fresh at checkout to prevent over-spend errors.

---

## 20. Feature Flags

### How Feature Flags Work

Feature flags live in two places:
1. **Environment variables** — set at deploy time; require restart to change.
2. **`system_settings` DB table** — live-editable via `PATCH /api/admin/settings/:key` without restart.

DB settings override env vars at runtime.

### Current Flags (Admin-Configurable)

| Setting key | Effect when false/0 | Default | DB override |
|---|---|---|---|
| `ordering_window_open_time` | — | `08:00` (WAT) | Yes |
| `ordering_window_close_time` | — | `16:00` (WAT) | Yes |
| `squad_order_enabled` | Squad order fields ignored | `true` | Yes |
| `hp_multiplier_active` | HP earn rate at 1× | `1` | Yes |
| `spin_prizes` | JSON array of wheel prizes | Built-in defaults | Yes |
| `monthly_pending_cap` | Monthly free-activity HP cap | `800` | Yes |
| `min_topup_amount` | Minimum wallet top-up | `500` NGN | Yes |
| `hp_transfer_min_orders` | Min completed orders to send HP | `3` | Yes |
| `order_lock_max_discount` | Max % discount on order locks | `50` | Yes |
| `notification_gap_minutes` | Min minutes between pushes | `30` | Yes |
| `graduation_min_level` | Min academic level for graduation HP | `400` | Yes |

### Checking Flag State (Frontend)

Call `GET /api/admin/settings` (admin only) or check the relevant API response for the flag. Non-admin screens should derive state from API behaviour:
- If `POST /orders` returns `400` with `"Squad orders are disabled"` → squad feature is off.
- If ordering window is closed → `GET /orders/delivery-windows/status` returns `{ is_open: false }`.
- If HP multiplier is active → `GET /hp/balance` tier object includes `multiplier > 1`.

---

## 21. Testing Requirements

### API Contract Tests (Frontend)

Before shipping any screen, verify these contracts locally against the staging API:

| Check | How |
|---|---|
| 401 token expiry triggers refresh | Manually expire token in SecureStorage; confirm 401 → refresh → retry |
| 429 rate limit displays user-friendly message | Rapid repeated requests to `/auth/login` |
| Kitchen closed state shows on Home | Call `PATCH /api/admin/settings/ordering_window_close_time` → `00:00` |
| Sold-out item blocks add-to-cart | Set a menu item `is_available: false` via `PATCH /api/menu/items/:id` |
| Guest checkout claim flow | Full guest → login → claim flow end-to-end |
| HP pending never shows as spendable | Place order, check HP screen before delivery |
| Optimistic UI rollback on error | Network fail after cart add; confirm rollback |

### End-to-End Smoke Tests (CI)

The backend ships with `scripts/test_e2e.py`. Run it against staging after each deploy:

```bash
python scripts/test_e2e.py
```

All 9 sections (register, menu, cart, order, HP, wallet, events, marketplace, admin) should pass before a frontend release.

### Accessibility Audit

Before each major release, run an accessibility audit:
1. Enable TalkBack (Android) / VoiceOver (iOS) and navigate each screen by swipe only.
2. Verify every interactive element is reachable and labelled.
3. Run Lighthouse accessibility audit (score ≥ 90) on the web version.

---

## 22. Dependency Versions

### Backend (for frontend team awareness)

| Component | Version |
|---|---|
| Python | 3.11+ |
| Flask | 3.x |
| Supabase | PostgREST v12 (via `supabase-py`) |
| Paystack | REST API v2 |
| Redis | 7.x (Celery broker) |
| JWT | HS256 (access + refresh tokens) |

### Frontend Recommendations

| Library | Purpose | Notes |
|---|---|---|
| `react-query` / `@tanstack/query` | Server state, polling, caching | Set `staleTime: 60_000` for menu/HP |
| `axios` / native `fetch` | HTTP client | Intercept 401 for token refresh |
| `zustand` / `redux-toolkit` | Auth/cart state | Do not put cart in store — always from server |
| `react-native-push-notification` | FCM/APNs device token | Register on login; send to `/auth/device-token` |
| `@notifee/react-native` | Local notification display | Handle foreground push payloads |
| `cloudinary-react` / `cloudinary-react-native` | Image upload | Direct upload to Cloudinary before saving URL |
| `react-native-secure-storage` | Token persistence | Use for refresh_token storage |

### API Versioning

The current API has no version prefix — all routes are `/api/...`. A breaking change will be communicated via a new base path (`/api/v2/...`). Monitor the `CHANGELOG.md` (backend repo) before each frontend release.

---

## 23. Theme & Brand Guidelines

### Brand Identity

| Element | Value |
|---|---|
| **App name** | Holy Grills |
| **Tagline** | Holy Grills FUTA |
| **Target audience** | FUTA students and staff |
| **Tone** | Energetic, warm, campus-culture aware |
| **Currency** | Nigerian Naira (₦) — display with ₦ symbol, not "NGN" |
| **Language** | English (Nigerian informal register acceptable in copy) |

### Colour Palette

#### Primary
#### Order Status Colours

| Status | Hex | Tailwind / equivalent |
|---|---|---|
| `received` | `#F97316` | `orange-500` |
| `preparing` | `#3B82F6` | `blue-500` |
| `ready` | `#10B981` | `emerald-500` |
| `assigned` | `#8B5CF6` | `violet-500` |
| `out_for_delivery` | `#06B6D4` | `cyan-500` |
| `delivered` | `#16A34A` | `green-700` |
| `delivery_attempted` | `#EF4444` | `red-500` — **high urgency** |
| `unclaimed` | `#9CA3AF` | `gray-400` |
| `cancelled` | `#EF4444` | `red-500` |
| `refunded` | `#6B7280` | `gray-500` |

#### HP Tier Colours

| Tier | Slug | Hex | Suggested gradient |
|---|---|---|---|
| Newbie | `newbie` | `#6B7280` | — |
| Scout | `scout` | `#3B82F6` | `from-blue-400 to-blue-600` |
| Regular | `regular` | `#10B981` | `from-emerald-400 to-emerald-600` |
| Champion | `champion` | `#F59E0B` | `from-amber-400 to-orange-500` |
| Legend | `legend` | `#8B5CF6` | `from-violet-400 to-purple-600` |

### Typography

| Usage | Weight | Notes |
|---|---|---|
| Screen titles | Bold (700) | — |
| Section headers | SemiBold (600) | — |
| Body text | Regular (400) | — |
| Captions / labels | Regular (400) | Reduce opacity to 60% for secondary labels |
| HP amounts | Bold (700) | Always show with "HP" suffix |
| Currency amounts | SemiBold (600) | Prefix with ₦ symbol — e.g. `₦3,500` |

> The backend does not prescribe a font family. Choose a clean sans-serif that renders well on Nigerian Android devices (Roboto or Inter are safe defaults).

### Spacing & Touch Targets

| Element | Minimum size |
|---|---|
| Touch targets | 44 × 44 pt (iOS) / 48 × 48 dp (Android) |
| Card padding | 16 dp |
| Section margin | 24 dp |
| Bottom nav height | 56 dp |

### Icons & Imagery

- Use the **🌟** or **⚡** emoji sparingly in notification copy — already handled server-side.
- Menu item images: display as **square 1:1**, rounded corners (8 dp), `c_fill,w_400,h_400,q_auto,f_auto` Cloudinary transformation.
- Event banners: **16:9**, `c_fill,w_800,h_450,q_auto,f_auto`.
- User avatars: circular crop, 48 × 48 dp thumbnail.

### HP (Holy Points) Display Rules

```
✅  Active: 1,250 HP         (show in green / brand colour)
🕐  Pending:   350 HP        (show in muted / amber — not yet spendable)

Never show: Total: 1,600 HP  (misleading — pending isn't spendable)
```

- **Active HP** → spendable. Show prominently.
- **Pending HP** → locked. Show separately with a lock icon or "unlocks on delivery" tooltip.
- **Never merge** active + pending into a single balance figure.
- HP amounts are always integers — no decimals.

### Notification Visual Priority

| Priority | Visual treatment |
|---|---|
| **Critical** (`order_delivery_attempted`) | Full-screen modal, red accent, cannot be dismissed without action |
| **Normal** (order lifecycle, HP, wallet) | Standard push banner + in-app badge |
| **Low** (`abandoned_cart`, `winback`, share prompts) | In-app badge only — no push banner |

### Localisation Notes

- All prices in **Nigerian Naira (₦)** — use `toLocaleString('en-NG')` or format manually.
- Phone numbers displayed in `0XX XXXX XXXX` format.
- Dates displayed in `DD MMM YYYY` format (e.g. "16 Jul 2026").
- Times displayed in **WAT** (UTC+1) — the API returns UTC ISO-8601; convert on the client.
- No multi-language requirement — English only for now.

---

## Appendix B: Useful cURL Examples

```bash
BASE=http://localhost:5000/api
TOKEN=eyJ...   # replace with your token

# Register
curl -X POST $BASE/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@futa.edu.ng","password":"Test123!","full_name":"Test User"}'

# Get menu
curl $BASE/menu/items

# Place order (wallet payment)
curl -X POST $BASE/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"menu_item_id":"uuid","quantity":1}],"payment_method":"wallet","delivery_type":"on_campus","delivery_location_id":"hostel-uuid"}'

# Check HP balance
curl $BASE/hp/balance -H "Authorization: Bearer $TOKEN"

# Spin wheel
curl -X POST $BASE/hp/spin -H "Authorization: Bearer $TOKEN"

# Health check
curl $BASE/health
```
