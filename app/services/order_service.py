"""
Order Service — handles order creation, status transitions, and HP award flow.

Order Status Machine:
  received → preparing → ready → assigned → out_for_delivery → delivered
                                                              → delivery_attempted → unclaimed
  Any pre-delivery state → cancelled (by admin/kitchen)

HP Flow on Delivery:
  1. Award base food HP (1 HP/₦10) → ACTIVE
  2. Apply tier bonus multiplier → ACTIVE
  3. Unlock pending HP (100 HP/₦1,000 food spend)
  4. Award welcome bonus (50 HP) on first-ever order
  5. Trigger referral completion if applicable
  6. Recalculate tier
"""

import uuid
from datetime import datetime, timezone
from flask import current_app
from app.db import get_db, SupabaseError
from app.services import hp_service
from app.services.wallet_service import debit_wallet
from app.services.notification_service import send_notification


VALID_TRANSITIONS = {
    "received":           ["preparing", "cancelled", "refunded"],
    "paid":               ["preparing", "cancelled", "refunded"],
    "preparing":          ["ready", "cancelled", "refunded"],
    "ready":              ["assigned", "cancelled", "refunded"],
    "assigned":           ["out_for_delivery", "cancelled", "refunded"],
    "out_for_delivery":   ["delivered", "delivery_attempted", "refunded"],
    "delivery_attempted": ["delivered", "unclaimed", "refunded"],
    "unclaimed":          ["cancelled", "refunded"],
    "delivered":          ["refunded"],
    "cancelled":          [],
    "refunded":           [],
}

STATUS_TIMESTAMPS = {
    "received":           "received_at",
    "paid":               "paid_at",
    "preparing":          "preparing_at",
    "ready":              "ready_at",
    "assigned":           "assigned_at",
    "out_for_delivery":   "out_for_delivery_at",
    "delivered":          "delivered_at",
    "delivery_attempted": "delivery_attempted_at",
    "unclaimed":          "unclaimed_at",
    "cancelled":          "cancelled_at",
    "refunded":           "refunded_at",
}


def _today_start_iso():
    """UTC midnight today as ISO string."""
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()


def _check_kitchen_capacity(db):
    """Raise ValueError if the kitchen's daily order cap has been reached."""
    row = (
        db.table("kitchen_settings")
        .select("value")
        .eq("key", "daily_order_capacity")
        .single()
        .execute()
    )
    raw = row.get("value") if row else ""
    if not raw or not str(raw).isdigit():
        return  # no cap configured
    capacity = int(raw)
    orders_today = (
        db.table("orders")
        .select("id")
        .gte("created_at", _today_start_iso())
        .execute()
    ) or []
    if len(orders_today) >= capacity:
        raise ValueError(
            "The kitchen has reached its daily order capacity. "
            "Please try again tomorrow or check back later."
        )


def _count_item_today(db, menu_item_id: str, today_order_ids: set) -> int:
    """Return how many units of menu_item_id have been ordered today."""
    if not today_order_ids:
        return 0
    rows = (
        db.table("order_items")
        .select("quantity,order_id")
        .eq("menu_item_id", menu_item_id)
        .execute()
    ) or []
    return sum(
        int(r.get("quantity", 1))
        for r in rows
        if r.get("order_id") in today_order_ids
    )


def create_order(user_id: str | None, payload: dict) -> dict:
    """
    Create a new order. Supports authenticated and guest checkout.
    Validates kitchen capacity, daily item limits, window, resolves items,
    resolves add-ons, applies promo/HP discounts, returns order record.

    Payload additions vs v1:
      items[].selected_variations  — list of {variation_group_id, option_id}
      addons                       — list of {addon_id, quantity}
    """
    db = get_db()

    # Reject if kitchen is already at daily capacity
    _check_kitchen_capacity(db)

    window_id = payload.get("delivery_window_id")
    if window_id:
        window = db.table("delivery_windows").select("id,status").eq("id", window_id).single().execute()
        if not window or window.get("status") != "open":
            raise ValueError("Selected delivery window is not open")

    raw_items = payload.get("items", [])
    if not raw_items:
        raise ValueError("Order must contain at least one item")

    # Pre-fetch today's order IDs once for daily-limit checks
    today_orders = (
        db.table("orders")
        .select("id")
        .gte("created_at", _today_start_iso())
        .execute()
    ) or []
    today_order_ids = {o["id"] for o in today_orders}

    subtotal = 0.0
    order_items = []
    for item in raw_items:
        menu_item = (
            db.table("menu_items")
            .select("id,name,price,hp_earn,is_available,deleted_at,daily_limit")
            .eq("id", item["menu_item_id"])
            .single()
            .execute()
        )
        if not menu_item:
            raise ValueError(f"Menu item {item['menu_item_id']} not found")
        if not menu_item.get("is_available") or menu_item.get("deleted_at"):
            raise ValueError(f"'{menu_item['name']}' is not currently available")

        qty = max(1, int(item.get("quantity", 1)))

        # Enforce per-item daily limit
        daily_limit = menu_item.get("daily_limit")
        if daily_limit is not None:
            count_today = _count_item_today(db, menu_item["id"], today_order_ids)
            remaining = max(0, int(daily_limit) - count_today)
            if qty > remaining:
                raise ValueError(
                    f"'{menu_item['name']}' only has {remaining} serving(s) left today"
                )

        unit_price = float(menu_item["price"])

        # Resolve variation selections and add any price deltas
        selected_variations = item.get("selected_variations", [])
        variation_price_delta = 0.0
        resolved_variations = []
        for sel in selected_variations:
            option = (
                db.table("menu_item_variation_options")
                .select("id,name,price_delta,variation_group_id,is_available")
                .eq("id", sel.get("option_id"))
                .single()
                .execute()
            )
            if option and not option.get("is_available", True):
                raise ValueError(f"Variation option '{option.get('name')}' is not currently available")
            if option:
                variation_price_delta += float(option.get("price_delta", 0))
                resolved_variations.append({
                    "variation_group_id": option["variation_group_id"],
                    "option_id": option["id"],
                    "option_name": option["name"],
                    "price_delta": float(option.get("price_delta", 0)),
                })

        effective_unit_price = round(unit_price + variation_price_delta, 2)
        order_items.append({
            "menu_item_id": menu_item["id"],
            "name_snapshot": menu_item["name"],
            "quantity": qty,
            "price_snapshot": effective_unit_price,
            "hp_earn_snapshot": menu_item.get("hp_earn", 0),
            "line_total": round(effective_unit_price * qty, 2),
            "selected_variations": resolved_variations,
            "is_addon": False,
        })
        subtotal += effective_unit_price * qty

    # Resolve order-level add-ons
    for addon_entry in payload.get("addons", []):
        addon = (
            db.table("menu_addons")
            .select("id,name,price,is_available,is_archived")
            .eq("id", addon_entry.get("addon_id"))
            .single()
            .execute()
        )
        if not addon:
            raise ValueError(f"Add-on {addon_entry.get('addon_id')} not found")
        if not addon.get("is_available"):
            raise ValueError(f"Add-on '{addon['name']}' is not currently available")
        addon_qty = max(1, int(addon_entry.get("quantity", 1)))
        addon_price = float(addon["price"])
        order_items.append({
            "menu_item_id": None,
            "addon_id": addon["id"],
            "name_snapshot": addon["name"],
            "quantity": addon_qty,
            "price_snapshot": addon_price,
            "hp_earn_snapshot": 0,
            "line_total": round(addon_price * addon_qty, 2),
            "selected_variations": [],
            "is_addon": True,
        })
        subtotal += addon_price * addon_qty

    subtotal = round(subtotal, 2)

    # ── Squad Order discount ──────────────────────────────────────────────────
    config = current_app.config
    squad_discount = 0.0
    squad_delivery_discount = 0.0
    squad_item_count = sum(oi["quantity"] for oi in order_items if not oi.get("is_addon"))
    is_squad_order = False

    if config.get("SQUAD_ORDER_ENABLED", True):
        min_items = int(config.get("SQUAD_ORDER_MIN_ITEMS", 3))
        max_items = int(config.get("SQUAD_ORDER_MAX_ITEMS", 20))
        if min_items <= squad_item_count <= max_items:
            is_squad_order = True

    promo_discount = 0.0
    promo_code_id = None
    if payload.get("promo_code") and user_id:
        promo = _apply_promo(user_id, payload["promo_code"], subtotal)
        promo_discount = promo["discount"]
        promo_code_id = promo["promo_code_id"]

    hp_discount = 0.0
    hp_points_used = 0
    if payload.get("hp_points_to_redeem", 0) > 0 and user_id:
        hp_to_use = int(payload["hp_points_to_redeem"])
        hp_discount = round(hp_to_use * config["HP_LIABILITY_VALUE"], 2)
        hp_points_used = hp_to_use

    delivery_fee = 0.0

    # Apply squad delivery-fee discount
    if is_squad_order and config.get("SQUAD_DELIVERY_DISCOUNT_ENABLED", True):
        pct = float(config.get("SQUAD_DELIVERY_DISCOUNT_PCT", 100))
        squad_delivery_discount = round(delivery_fee * pct / 100.0, 2)
        delivery_fee = max(0.0, delivery_fee - squad_delivery_discount)

    # Apply squad subtotal discount
    if is_squad_order and config.get("SQUAD_ORDER_DISCOUNT_ENABLED", False):
        pct = float(config.get("SQUAD_ORDER_DISCOUNT_PCT", 10))
        squad_discount = round(subtotal * pct / 100.0, 2)

    total = max(0.0, round(subtotal - promo_discount - hp_discount - squad_discount + delivery_fee, 2))

    payment_method = payload.get("payment_method", "card")
    wallet_amount_used = 0.0
    card_amount_used = 0.0

    if payment_method == "wallet":
        wallet_amount_used = total
    elif payment_method == "card":
        card_amount_used = total
    elif payment_method == "split":
        wallet_amount_used = min(float(payload.get("wallet_amount", 0)), total)
        card_amount_used = round(total - wallet_amount_used, 2)

    # Pre-check wallet balance before inserting order
    if payment_method == "wallet" and user_id:
        wallet = db.table("wallets").select("balance").eq("user_id", user_id).single().execute()
        if not wallet or float(wallet.get("balance", 0)) < wallet_amount_used:
            raise ValueError(f"Insufficient wallet balance: need ₦{wallet_amount_used:.2f}")

    is_guest = user_id is None
    claim_token = str(uuid.uuid4()) if is_guest else None
    order_record = {
        "user_id": user_id,
        "guest_name": payload.get("guest_name"),
        "guest_phone": payload.get("guest_phone"),
        "guest_email": payload.get("guest_email"),
        "delivery_window_id": window_id,
        "delivery_address_snapshot": payload.get("delivery_address"),
        "status": "received",
        "payment_status": "pending",
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "discount_amount": round(promo_discount + squad_discount, 2),
        "total_amount": total,
        "wallet_amount_used": wallet_amount_used,
        "card_amount_used": card_amount_used,
        "hp_redeemed": hp_points_used,
        "promo_code_id": promo_code_id,
        "notes": payload.get("notes", ""),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "is_squad_order": is_squad_order,
        "squad_discount_amount": squad_discount,
        "squad_item_count": squad_item_count,
    }

    if claim_token:
        order_record["claim_token"] = claim_token

    try:
        created = db.table("orders").insert(order_record)
    except Exception:
        # claim_token column may not exist yet — retry without it first
        no_claim = {k: v for k, v in order_record.items() if k != "claim_token"}
        try:
            created = db.table("orders").insert(no_claim)
        except Exception:
            # Squad-order columns may also not exist — strip those too and retry
            safe_record = {k: v for k, v in no_claim.items()
                           if k not in ("is_squad_order", "squad_discount_amount", "squad_item_count")}
            safe_record["discount_amount"] = round(promo_discount, 2)
            safe_record["total_amount"] = max(0.0, round(
                subtotal - promo_discount - hp_discount - squad_discount + delivery_fee, 2))
            created = db.table("orders").insert(safe_record)

    order = created[0] if isinstance(created, list) else created
    order_id = order["id"]
    # Surface squad info even when DB columns don't exist
    order.setdefault("is_squad_order", is_squad_order)
    order.setdefault("squad_discount_amount", squad_discount)
    order.setdefault("squad_item_count", squad_item_count)

    # Deduct wallet now that we have the real order_id
    if payment_method == "wallet" and user_id:
        try:
            debit_wallet(
                user_id=user_id,
                amount=wallet_amount_used,
                reference_id=order_id,
                reference_type="order",
                notes=f"Wallet payment for order {order_id[:8].upper()}",
            )
            db.table("orders").eq("id", order_id).update({"payment_status": "paid"})
            order["payment_status"] = "paid"
        except ValueError as e:
            db.table("orders").eq("id", order_id).update({"status": "cancelled"})
            raise ValueError(f"Wallet payment failed: {e}")

    for oi in order_items:
        oi["order_id"] = order_id
    db.table("order_items").insert(order_items)

    # Record promo code use
    if promo_code_id and user_id:
        try:
            db.table("promo_code_uses").insert({
                "promo_code_id": promo_code_id,
                "user_id": user_id,
                "order_id": order_id,
                "discount_amount": promo_discount,
            })
            db.table("promo_codes").eq("id", promo_code_id).update({
                "used_count": None  # incremented via DB trigger ideally
            })
        except Exception:
            pass

    return order


def _find_status_path(from_status: str, to_status: str) -> list | None:
    """BFS — returns the ordered list of statuses to pass through to reach to_status,
    or None if no valid path exists in the state machine."""
    if from_status == to_status:
        return []
    queue = [(from_status, [])]
    visited = {from_status}
    while queue:
        current, path = queue.pop(0)
        for nxt in VALID_TRANSITIONS.get(current, []):
            new_path = path + [nxt]
            if nxt == to_status:
                return new_path
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, new_path))
    return None


def walk_order_to_status(
    order_id: str,
    target_status: str,
    changed_by: str = None,
    notes: str = "",
) -> dict:
    """
    Walk an order through every intermediate state until it reaches target_status.
    Uses BFS on VALID_TRANSITIONS to find the shortest legal path.

    Returns:
        {"steps": ["preparing", "ready", ...], "final": <order dict>}
    """
    db = get_db()
    order = db.table("orders").select("status").eq("id", order_id).single().execute()
    if not order:
        raise ValueError("Order not found")

    path = _find_status_path(order["status"], target_status)
    if path is None:
        raise ValueError(
            f"No valid path from '{order['status']}' to '{target_status}' "
            "in the order state machine"
        )
    if not path:
        raise ValueError(f"Order is already in '{target_status}' status")

    final = None
    for status in path:
        final = update_order_status(
            order_id=order_id,
            new_status=status,
            changed_by=changed_by,
            notes=notes or f"bulk walk → {status}",
        )

    return {"steps": path, "final": final}


def confirm_order_payment(order_id: str, payment_reference: str, provider_response: dict = None) -> dict:
    """
    Called after card payment confirmed (webhook).
    Updates payment_status to paid. Order is already in 'received' state.
    """
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).single().execute()
    if not order:
        raise ValueError("Order not found")
    if order.get("payment_status") == "paid":
        return order  # idempotent

    # Deduct HP redemption if used
    if order.get("hp_redeemed", 0) > 0 and order.get("user_id"):
        try:
            hp_service.spend_hp(
                user_id=order["user_id"],
                amount=int(order["hp_redeemed"]),
                reference_id=order_id,
                reference_type="order_hp_redemption",
                notes=f"HP discount on order {order_id[:8].upper()}",
            )
        except ValueError as e:
            raise ValueError(f"HP deduction failed: {e}")

    update_data = {
        "payment_status": "paid",
        "payment_reference": payment_reference,
        "payment_confirmed_at": datetime.now(timezone.utc).isoformat(),
    }

    updated = db.table("orders").eq("id", order_id).update(update_data)

    if order.get("user_id"):
        send_notification(
            user_id=order["user_id"],
            notif_type="order_confirmed",
            title="Order Confirmed!",
            body=f"Your order #{order_id[:8].upper()} is received and heading to the kitchen.",
            reference_id=order_id,
            reference_type="order",
            channels=["in_app", "email"],
        )

    return updated[0] if isinstance(updated, list) else updated


def update_order_status(order_id: str, new_status: str, changed_by: str = None, notes: str = "") -> dict:
    """
    Transition order status. Validates state machine. Awards HP on delivery.
    Notifications and delivery rewards run in a daemon thread so the response
    is not held up by sequential Supabase notification inserts.
    """
    import threading as _threading
    from flask import current_app as _app
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).single().execute()
    if not order:
        raise ValueError("Order not found")

    current_status = order["status"]
    allowed = VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise ValueError(f"Cannot transition '{current_status}' → '{new_status}'")

    now = datetime.now(timezone.utc).isoformat()
    update_data = {"status": new_status}
    ts_field = STATUS_TIMESTAMPS.get(new_status)
    if ts_field:
        update_data[ts_field] = now

    updated = db.table("orders").eq("id", order_id).update(update_data)
    _log_status_change(order_id, current_status, new_status, changed_by, notes)

    # HP award must complete before we return so callers see the updated balance.
    if new_status == "delivered" and order.get("user_id"):
        _handle_delivery_rewards(order)

    # Status notifications are fire-and-forget; run in a thread so the
    # response is not held up by sequential Supabase notification inserts.
    app_ctx = _app._get_current_object()

    def _notify():
        with app_ctx.app_context():
            _send_status_notification(order, new_status)

    _threading.Thread(target=_notify, daemon=True).start()

    return updated[0] if isinstance(updated, list) else updated


def _handle_delivery_rewards(order: dict):
    """
    Full HP award sequence on order delivery:
    1. Food HP + tier bonus → active
    2. Unlock pending HP
    3. Welcome bonus (first order)
    4. Referral completion trigger
    5. Tier recalculation
    """
    user_id = order["user_id"]
    order_id = order["id"]
    subtotal = float(order.get("subtotal", 0))

    tier_info = hp_service.get_user_tier(user_id)
    tier = tier_info.get("tier") or {}
    tier_slug = tier.get("slug", "ember")

    hp_result = hp_service.award_food_order_hp(
        user_id=user_id,
        order_id=order_id,
        order_total=subtotal,
        tier_slug=tier_slug,
    )

    welcome_result = hp_service.award_welcome_bonus(user_id, order_id)

    tier_change = hp_service.recalculate_tier(user_id)

    db = get_db()
    order_updates = {
        "hp_earned": hp_result["total_hp"],
        "hp_credited_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        db.table("orders").eq("id", order_id).update(order_updates)
    except Exception:
        pass

    # All HP/tier/referral logic above is synchronous so callers see updated
    # balances immediately. Notifications are fire-and-forget — queue them as
    # daemon threads so they don't add latency to the status-update response.
    import threading as _t

    total_hp_awarded = hp_result["total_hp"] + welcome_result.get("awarded", 0)

    def _send_delivery_notifications():
        if total_hp_awarded > 0:
            send_notification(
                user_id=user_id,
                notif_type="hp_earned",
                title=f"+{total_hp_awarded} HP Earned!",
                body=f"You earned {hp_result['base_hp']} food HP" +
                     (f" + {hp_result['tier_bonus_hp']} tier bonus" if hp_result["tier_bonus_hp"] else "") +
                     (f" + {welcome_result['awarded']} welcome bonus" if welcome_result.get("awarded") else "") +
                     ".",
                reference_id=order_id,
                reference_type="order",
                channels=["in_app"],
            )
        if hp_result["unlocked_pending_hp"] > 0:
            send_notification(
                user_id=user_id,
                notif_type="hp_unlocked",
                title=f"+{hp_result['unlocked_pending_hp']} HP Unlocked!",
                body=f"Your food order unlocked {hp_result['unlocked_pending_hp']} HP from your pending pool.",
                channels=["in_app"],
            )
        if tier_change.get("changed") and tier_change.get("tier"):
            tier_name = tier_change["tier"].get("name", "new tier")
            send_notification(
                user_id=user_id,
                notif_type="tier_upgrade",
                title=f"You reached {tier_name}!",
                body=f"Congratulations! You've earned {tier_name} status. Enjoy your enhanced rewards.",
                reference_id=user_id,
                reference_type="user_tier",
                channels=["in_app", "email"],
            )

    _t.Thread(target=_send_delivery_notifications, daemon=True).start()

    _trigger_referral_completion(user_id, order_id)


def _trigger_referral_completion(user_id: str, order_id: str):
    """Check if this is the user's first order and complete any pending referral."""
    db = get_db()
    try:
        all_delivered = (
            db.table("orders")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "delivered")
            .execute()
        )
        if len(all_delivered) == 1:  # This is their first completed order
            referral = (
                db.table("referrals")
                .select("*")
                .eq("referred_user_id", user_id)
                .single()
                .execute()
            )
            if referral and not referral.get("hp_awarded", 0):
                from app.routes.referrals import _complete_referral_award
                _complete_referral_award(referral, order_id)
    except Exception:
        pass


def _apply_promo(user_id: str, code: str, order_subtotal: float) -> dict:
    db = get_db()
    promo = (
        db.table("promo_codes")
        .select("*")
        .eq("code", code.upper().strip())
        .eq("is_active", "true")
        .single()
        .execute()
    )
    if not promo:
        raise ValueError(f"Promo code '{code}' is not valid")

    now = datetime.now(timezone.utc).isoformat()
    if promo.get("ends_at") and promo["ends_at"] < now:
        raise ValueError("Promo code has expired")
    if promo.get("starts_at") and promo["starts_at"] > now:
        raise ValueError("Promo code is not yet active")
    if promo.get("max_uses") and int(promo.get("used_count") or 0) >= promo["max_uses"]:
        raise ValueError("Promo code has reached its usage limit")
    if order_subtotal < float(promo.get("min_order_amount") or 0):
        raise ValueError(f"Minimum order value ₦{promo.get('min_order_amount', 0):.0f} required for this code")

    if promo["discount_type"] == "percentage":
        discount = order_subtotal * float(promo["discount_value"]) / 100
    else:
        discount = float(promo["discount_value"])

    return {"discount": round(discount, 2), "promo_code_id": promo["id"]}


def _log_status_change(order_id: str, from_status: str, to_status: str, changed_by: str = None, notes: str = ""):
    db = get_db()
    try:
        db.table("order_status_logs").insert({
            "order_id": order_id,
            "status": to_status,
            "changed_by": changed_by,
            "note": notes or f"{from_status} → {to_status}",
            "metadata": {"from_status": from_status},
        })
    except Exception:
        pass


def _send_status_notification(order: dict, new_status: str):
    user_id = order.get("user_id")
    if not user_id:
        return
    messages = {
        "preparing":          ("Your order is being prepared", "The kitchen is on it! Won't be long."),
        "ready":              ("Order Ready!", "Your order is ready and waiting for a rider."),
        "assigned":           ("Rider Assigned!", "A rider has been assigned to your order."),
        "out_for_delivery":   ("On The Way!", "Your rider has picked up your order."),
        "delivered":          ("Order Delivered!", "Your order has been delivered. Enjoy your meal!"),
        "delivery_attempted": ("Delivery Attempted", "We tried to reach you. Please respond within 30 minutes."),
        "unclaimed":          ("Order Unclaimed", "Your order was not collected. Please contact us."),
        "cancelled":          ("Order Cancelled", "Your order has been cancelled. Contact us for help."),
    }
    if new_status in messages:
        title, body = messages[new_status]
        send_notification(
            user_id=user_id,
            notif_type=f"order_{new_status}",
            title=title,
            body=body,
            reference_id=order["id"],
            reference_type="order",
            channels=["in_app", "email"],
        )
