# Session Backend Changes & Frontend Integration Reference

This document captures **all backend additions, modifications, endpoints, business logic, data types, and API response contracts** implemented in this session (Stages 1–16). Use this guide to wire frontend features accordingly.

---

## 1. Stage 1 — Display Name & Nickname Resolution

### Endpoints / Modifications
- `PATCH /api/auth/profile` (`update_profile`)
  - **Payload**:
    ```json
    {
      "nickname": "Speedy", // string | null (2-20 chars: letters, numbers, underscores, spaces)
      "leaderboard_show_full_name": true // boolean
    }
    ```
  - **Logic**: Validates nickname format; nullable to clear nickname. `leaderboard_show_full_name` controls whether the user's real name or nickname represents them on public leaderboards.
- `POST /api/auth/register` (`register`)
  - **Payload additions**:
    ```json
    {
      "nickname": "Speedy" // optional string
    }
    ```

### Name Resolution Logic (`app/services/squad_service.py`)
- `resolve_display_name(profile)`: `nickname` -> `full_name` -> `email prefix` -> `"Guest"`.
  - **Deduplication**: If another profile on the same campus shares the exact nickname, returns `"Nickname (Department)"`.
- `resolve_leaderboard_name(profile)`:
  - If `leaderboard_show_full_name` is true and `full_name` is non-empty: returns `full_name`.
  - Otherwise falls back to `resolve_display_name(profile)`.

---

## 2. Stage 2 — Persistent Squad Entities & Squad Orders

### Squad Routes (`app/routes/squads.py` - Prefix `/api/squads`)

1. `POST /api/squads`
   - **Request**: `{"name": "Coders Squad", "emails": ["m1@ex.com", "m2@ex.com"]}`
   - **Response (201)**:
     ```json
     {
       "id": "uuid",
       "name": "Coders Squad",
       "creator_id": "uuid",
       "campus_id": "uuid",
       "created_at": "ISO-8601"
     }
     ```
   - **Error (400)**: If invited email belongs to a profile on a different campus (`MSG.SQUAD_CROSS_CAMPUS_BLOCKED`).

2. `GET /api/squads`
   - **Response (200)**: List of squads created by or joined by the user (`Array<Squad>`).

3. `GET /api/squads/<squad_id>`
   - **Response (200)**:
     ```json
     {
       "id": "uuid",
       "name": "Coders Squad",
       "creator_id": "uuid",
       "campus_id": "uuid",
       "roster": [
         {
           "id": "uuid",
           "email": "m1@ex.com",
           "user_id": "uuid|null",
           "display_name": "Speedy",
           "is_active": true,
           "cumulative_hp": 450
         }
       ]
     }
     ```

4. `GET /api/squads/<squad_id>/orders`
   - **Response (200)**: Array of squad order history summaries.

5. `POST /api/squads/<squad_id>/members`
   - **Request**: `{"email": "member@ex.com"}`
   - **Response (201)**: Created roster row. Cross-campus blocked (400) if campus mismatch.

6. `DELETE /api/squads/<squad_id>/members/<member_id>`
   - **Response (200)**: `{"message": "Member removed"}` (Soft remove: sets `is_active = false`).

### Order Squad Member Routes (`app/routes/orders.py`)

1. `GET /api/orders/<order_id>/squad-members`
   - **Response (200)**: Array of `squad_members` rows for the order.

2. `DELETE /api/orders/<order_id>/squad-members/<member_id>`
   - **Response (200)**: `{"message": "Removed from this order"}` (Blocked if status is `delivered`).

3. `POST /api/orders/<order_id>/squad-members/<member_id>/resend`
   - **Response (200)**: `{"message": "Invite resent"}`. Re-sends squad invite email.

### Squad Order Checkout & Delivery Logic
- `POST /api/orders`
  - Pass `"squad_id": "uuid"` in order payload.
  - Snapshot member roster into `squad_member_snapshot` on `orders`.
- **Delivery Rewards (`_handle_delivery_rewards`)**:
  - HP distributed evenly among registered members (active HP) + organizer upon order delivery.
  - Unregistered squad members receive `pending_squad_hp` claimed automatically upon subsequent account sign-up.

---

## 3. Stage 3 — Tier Perks & Resource Access

### Configuration (`app/config.py`)
- `TIER_PERKS`:
  ```json
  {
    "ember": {"earn_multiplier": 1.00, "monthly_free_delivery": false, "birthday_hp": 0, "free_side_credits_monthly": 0, "exclusive_spins_monthly": 0},
    "flame": {"earn_multiplier": 1.08, "monthly_free_delivery": false, "birthday_hp": 0, "free_side_credits_monthly": 0, "exclusive_spins_monthly": 0},
    "blaze": {"earn_multiplier": 1.15, "monthly_free_delivery": true, "birthday_hp": 0, "free_side_credits_monthly": 0, "exclusive_spins_monthly": 0},
    "holy":  {"earn_multiplier": 1.25, "monthly_free_delivery": true, "birthday_hp": 0, "free_side_credits_monthly": 0, "exclusive_spins_monthly": 0}
  }
  ```

### Endpoints & Service Utilities (`app/services/tier_service.py`)
- `resolve_perk(user_id, perk_key)`: Checks campus-specific / global `system_settings` (`tier_perk_{slug}_{key}`), falling back to `TIER_PERKS`.
- `can_access_tier_resource(user_id, min_tier_id)`: Checks if user's tier `sort_order` satisfies required `min_tier_id`. Integrated into reward redemption and marketplace purchases.
- `POST /api/delivery/calculate-fee`
  - **Response Addition**:
    ```json
    {
      "delivery_fee": 500.0,
      "tier_free_delivery_available": true // boolean
    }
    ```
- **Order Checkout**: If user qualifies for `monthly_free_delivery` and has not claimed it this month, claims perk via `hg_claim_tier_monthly_perk` RPC and waives `delivery_fee` (`0.0`).

---

## 4. Stage 4 & 11 — Ordering Windows, Live Slot Counter & Capacity Weighting

### Capacity Weighting (`_order_capacity_weight`)
- Standard order weight = `1`.
- Squad order weight = `squad_item_count` (total item quantity).

### Live Ordering Window Status (`GET /api/orders/delivery-windows/status`)
- **Query Params**: `?calendar=true` (optional)
- **Response (200)**:
  ```json
  {
    "is_open": true,
    "any_capacity_remaining": true,
    "windows": [
      {
        "id": "uuid",
        "is_closed": false,
        "is_full": false,
        "remaining": 4,
        "delivery_starts_at": "18:00",
        "delivery_ends_at": "19:00"
      }
    ],
    "next_available_date": "2026-09-15", // string | null (populated if current day at capacity)
    "next_opens_at": "08:00",
    "calendar": [ // Array | null
      {"date": "2026-09-14", "is_open": true, "any_capacity_remaining": true}
    ]
  }
  ```

### Deferred Capacity Checkout Flow (`POST /api/orders`)
- **Error Response on Capacity Reached (400)**:
  ```json
  {
    "error": "This ordering window has reached capacity.",
    "next_available_date": "2026-09-15"
  }
  ```
- **Accept Next Available Resubmission**:
  - Frontend passes `"accept_next_available_date": true` in payload.
  - Backend automatically schedules order for next available date/window (`p_capacity_deferred=True`, `p_originally_requested_date=today`).

---

## 5. Stage 5 — Secret Menu Items

- `GET /api/menu/items`
  - Secret items (`is_secret = true`) are excluded from general listing unless a search query (`?q=...`) is provided.
- `POST /api/admin/menu/items` / `PATCH /api/admin/menu/items/<id>`
  - Whitelisted parameter `"is_secret": boolean`.

---

## 6. Stage 6 & Cap Fix — Instant Active Event HP & Monthly Pending Cap

- `earn_pending_hp(user_id, amount, source_type)`
  - If `source_type == "event"`: HP credited as **ACTIVE**.
  - Other non-order earn sources: HP credited as **PENDING** subject to monthly cap check (`check_monthly_cap`).
  - Returns `{"added_to_pending": int, "added_to_overflow": 0, "source_type": string}`.

---

## 7. Stage 7 & 8 — HP Multipliers & Auto-Rotation Tasks

- `calculate_delivery_hp`: `line_base_hp * item_multiplier * event_multiplier * menu_multiplier`.
- **Scheduled Auto-Rotation Tasks**:
  - `rotate_hp_multiplier_event`: Rotates global multiplier and notifies admins.
  - `rotate_flash_rewards`: Rotates flash reward offers per campus and broadcasts `flash_reward_live` notifications.

---

## 8. Stage 9 — Redeemed Item Delivery & Checkout

- `POST /api/rewards/redemptions/<redemption_id>/checkout`
  - **Request**:
    ```json
    {
      "delivery_mode": "instant", // "instant" | "next_order"
      "delivery_location_id": "uuid",
      "delivery_type": "on_campus"
    }
    ```
  - **Response (201)**: Creates order attaching redemption (`attached_order_id`).

---

## 9. Stage 10 — Capacity Reassignment Engine

- `PATCH /api/admin/ordering-windows/<window_id>`
  - When window capacity is increased, automatically searches for orders with `capacity_deferred = True` and `originally_requested_date <= window_date`.
  - Reassigns eligible received orders to the earlier window and dispatches `order_moved_up` notification.

---

## 10. Stage 12 & 13 — Segment Notifications & Email Provider Toggle

- **Segment User Resolution**: `resolve_segment_user_ids(segment, campus_id)`.
- **Email Provider**: Toggles between `resend` and `onesignal` via `system_settings` key `email_provider_default`. Supports custom database templates from `email_templates`.

---

## 11. Stage 14 — Order History Reminder Suggestions

- `GET /api/orders/suggestions`
  - **Response (200)**:
    ```json
    {
      "suggestion": {
        "order_id": "uuid",
        "ordered_at": "ISO-8601",
        "items": [
          {"name": "Jollof Rice & Chicken", "quantity": 2}
        ]
      }
    }
    ```

---

## 12. Stage 16 — HP Economics Module

- `app/services/economics_service.py`:
  - `calculate_food_reward_value()`
  - `calculate_merch_reward_value()`
  - `calculate_hp_price()`
  - `calculate_hp_liability()`
  - `validate_event_margin()`
- Applied in `POST /api/rewards` / `PATCH /api/rewards/<id>` to calculate `reward_value`, `hp_cost`, and `hp_liability`. Logs actual costs to `redemption_cost_log` upon fulfillment.

---

## 13. Guest Order Account Linking & Notifications

- **Confirmation Email**: Dispatches `guest_order_confirmed` email with order tracking link upon guest checkout.
- **Account Linking**: When a user registers (`auth_service.register`), retroactive guest orders previously placed with their email are linked, and delivered order HP rewards are credited synchronously.
