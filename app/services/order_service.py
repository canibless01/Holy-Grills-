"""
Order Service — handles order creation, status transitions, and HP award flow.

DEPRECATION NOTICE:
  Legacy order creation database function `hg_place_order` is DEPRECATED and
  MUST NOT be used. All order creation logic routes through `create_order()`,
  which uses the authoritative, atomic `hg_create_order_atomic` RPC to ensure
  safe lock claiming, wallet debits, and item creation without race conditions.

LEGACY FIELD DOCUMENTATION:
  - `order_items.options_snapshot` is a legacy column and is NOT the real customization
    snapshotting field. Real item variations and add-ons are snapshot in `selected_variations`
    and `_addon_selections` within the order item payload.

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
from decimal import Decimal
from flask import current_app
from app.db import get_db, SupabaseError
from app.services import hp_service
from app.services.wallet_service import debit_wallet
from app.services.notification_service import send_notification
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)


VALID_TRANSITIONS = {
    "scheduled":          ["received", "cancelled"],
    "received":           ["preparing", "cancelled", "refunded"],
    "paid":               ["preparing", "cancelled", "refunded"],
    "preparing":          ["ready", "cancelled", "refunded"],
    "ready":              ["assigned", "out_for_delivery", "cancelled", "refunded"],
    "assigned":           ["out_for_delivery", "cancelled", "refunded"],
    "out_for_delivery":   ["delivered", "delivery_attempted", "refunded"],
    "delivery_attempted": ["delivered", "unclaimed", "refunded"],
    "unclaimed":          ["cancelled", "refunded"],
    "delivered":          ["refunded"],
    "cancelled":          [],
    "refunded":           [],
}

STATUS_TIMESTAMPS = {
    "scheduled":          None,          # no separate column; scheduled_for is the relevant field
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
        from app.messages import MSG
        raise ValueError(MSG.ORDER_KITCHEN_AT_CAPACITY)


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


def _resolve_item_variations(db, menu_item: dict, selected_variations: list) -> tuple[Decimal, list]:
    """
    Validate and resolve `selected_variations` (list of {variation_group_id, option_id})
    for a single order item against that item's variation groups.
    Enforces required groups, min/max selection bounds, option ownership, and availability.
    Returns (price_delta_total_dec, resolved_variation_dicts).
    """
    menu_item_id = menu_item["id"]
    try:
        groups = (
            db.table("menu_item_variation_groups")
            .select("id,name,is_required,min_select,max_select,min_selections,max_selections")
            .eq("menu_item_id", menu_item_id)
            .execute()
        ) or []
    except Exception:
        groups = []

    group_ids = {g["id"] for g in groups}
    selected_variations = selected_variations or []
    selected_ids = [sel.get("option_id") for sel in selected_variations if sel.get("option_id")]

    resolved_options_by_id = {}
    if selected_ids:
        try:
            fetched = (
                db.table("menu_item_variation_options")
                .select("id,name,price_delta,variation_group_id,is_available,is_archived")
                .in_("id", selected_ids)
                .execute()
            ) or []
            resolved_options_by_id = {o["id"]: o for o in fetched}
        except Exception:
            resolved_options_by_id = {}

    counts_by_group = {}
    resolved_variations = []
    price_delta_total = Decimal("0.0")

    for sel in selected_variations:
        opt_id = sel.get("option_id")
        option = resolved_options_by_id.get(opt_id)
        if not option:
            raise ValueError(f"Variation option {opt_id} not found")
        if not option.get("is_available", True) or option.get("is_archived", False):
            raise ValueError(MSG.ORDER_VARIATION_UNAVAILABLE.format(name=option.get("name", "")))
        if group_ids and option.get("variation_group_id") not in group_ids:
            raise ValueError(f"Option '{option.get('name')}' does not belong to '{menu_item['name']}'")

        vgroup_id = option.get("variation_group_id")
        counts_by_group[vgroup_id] = counts_by_group.get(vgroup_id, 0) + 1
        p_delta = Decimal(str(option.get("price_delta", 0)))
        price_delta_total += p_delta
        resolved_variations.append({
            "variation_group_id": vgroup_id,
            "option_id": option["id"],
            "option_name": option["name"],
            "price_delta": float(p_delta),
        })

    for group in groups:
        count = counts_by_group.get(group["id"], 0)
        min_select = group.get("min_select") if group.get("min_select") is not None else group.get("min_selections")
        if min_select is None:
            min_select = 1 if group.get("is_required") else 0
        min_select = int(min_select)

        max_select = group.get("max_select") if group.get("max_select") is not None else group.get("max_selections")
        if max_select is None:
            max_select = 1
        max_select = int(max_select)

        if (group.get("is_required") or min_select > 0) and count < min_select:
            raise ValueError(f"Selection required for variation group '{group['name']}' in '{menu_item['name']}'")
        if count > max_select:
            raise ValueError(f"Too many selections for variation group '{group['name']}' in '{menu_item['name']}' (max {max_select})")

    return price_delta_total, resolved_variations


def _resolve_item_addons(db, menu_item: dict, selected_addons: list) -> tuple[float, list]:
    """
    Validate and resolve `selected_addons` (list of {addon_id, quantity}) for a
    single order item against that item's menu_addon_groups (required/min/max
    selection counts). Returns (price_delta_total, resolved_selection_dicts).

    This is additive: it only runs when items[].selected_addons is present, and
    never touches the pre-existing order-level `addons` flow used by the flat
    "menu_addons with group_id = NULL" add-ons.
    """
    menu_item_id = menu_item["id"]
    groups = (
        db.table("menu_addon_groups")
        .select("id,name,is_required,min_select,max_select")
        .eq("menu_item_id", menu_item_id)
        .execute()
    ) or []

    selected_addons = selected_addons or []
    selected_ids = [sel.get("addon_id") for sel in selected_addons if sel.get("addon_id")]

    resolved_addons_by_id = {}
    if selected_ids:
        fetched = (
            db.table("menu_addons")
            .select("id,name,price,is_available,is_archived,group_id")
            .in_("id", selected_ids)
            .execute()
        ) or []
        resolved_addons_by_id = {a["id"]: a for a in fetched}

    # Count selections per group for min/max validation
    counts_by_group = {}
    resolved_selections = []
    price_delta_total = 0.0

    for sel in selected_addons:
        addon = resolved_addons_by_id.get(sel.get("addon_id"))
        if not addon:
            raise ValueError(MSG.ORDER_ADDON_NOT_FOUND.format(addon_id=sel.get("addon_id")))
        if not addon.get("is_available") or addon.get("is_archived"):
            raise ValueError(MSG.ORDER_ADDON_UNAVAILABLE.format(name=addon["name"]))
        if addon.get("group_id") not in {g["id"] for g in groups}:
            raise ValueError(MSG.ORDER_ADDON_WRONG_ITEM.format(name=addon["name"], item_name=menu_item["name"]))

        qty = max(1, int(sel.get("quantity", 1)))
        counts_by_group[addon["group_id"]] = counts_by_group.get(addon["group_id"], 0) + qty
        price_delta = float(addon.get("price", 0))
        price_delta_total += price_delta * qty
        resolved_selections.append({
            "addon_id": addon["id"],
            "group_id": addon["group_id"],
            "name_snapshot": addon["name"],
            "price_delta_snapshot": price_delta,
            "quantity": qty,
        })

    # Enforce required-group and min/max constraints
    for group in groups:
        count = counts_by_group.get(group["id"], 0)
        min_select = int(group.get("min_select") if group.get("min_select") is not None else group.get("min_selections", 0))
        max_select = int(group.get("max_select") if group.get("max_select") is not None else group.get("max_selections", 1))
        if (group.get("is_required") or min_select > 0) and count < min_select:
            raise ValueError(MSG.ORDER_ADDON_GROUP_REQUIRED.format(
                group_name=group["name"], min_select=min_select, item_name=menu_item["name"]
            ))
        if count > max_select:
            raise ValueError(MSG.ORDER_ADDON_GROUP_TOO_MANY.format(
                group_name=group["name"], max_select=max_select, item_name=menu_item["name"]
            ))

    return round(price_delta_total, 2), resolved_selections


def create_order(user_id: str | None, payload: dict) -> dict:
    """
    Create a new order. Supports authenticated and guest checkout.
    Validates kitchen capacity, daily item limits, window, resolves items,
    resolves add-ons, applies promo/HP discounts, returns order record.

    Payload additions vs v1:
      items[].selected_variations  — list of {variation_group_id, option_id}
      addons                       — list of {addon_id, quantity}
    """
    idempotency_key = str(uuid.uuid4())

    db = get_db()

    # Reject if kitchen is already at daily capacity
    _check_kitchen_capacity(db)

    # ── Ordering window gate (non-scheduled orders only) ──────────────────────
    # Checks (in priority order):
    #   1. operating_hour_overrides for today — if a DB override exists, use it.
    #   2. operating_hours table for today's weekday.
    #   3. Fall back to ORDERING_WINDOW_OPEN_TIME/CLOSE_TIME config.
    # Scheduled orders may be placed at any time.
    is_scheduled = bool(payload.get("is_scheduled", False))
    if not is_scheduled:
        try:
            from datetime import date as _date, time as _time, timedelta as _td, timezone as _tz

            def _parse_hm(s, default_h=8, default_m=0):
                try:
                    parts = str(s).split(":")
                    return _time(int(parts[0]), int(parts[1]))
                except Exception:
                    return _time(default_h, default_m)

            _now_utc = datetime.now(_tz.utc)
            _now_wat = (_now_utc + _td(hours=1)).time()
            _today_iso = _date.today().isoformat()

            # 1. Check DB override for today
            _override_rows = (
                db.table("operating_hour_overrides")
                .select("is_closed,opens_at,closes_at,open_time,close_time")
                .eq("date", _today_iso)
                .execute()
            ) or []
            _override = _override_rows[0] if _override_rows else None

            if _override is not None:
                if _override.get("is_closed"):
                    raise ValueError(MSG.ORDER_OUTSIDE_ORDERING_HOURS)
                _ov_open = _override.get("opens_at") or _override.get("open_time")
                _ov_close = _override.get("closes_at") or _override.get("close_time")
                if _ov_open and _ov_close:
                    if not (_parse_hm(_ov_open, 0, 0) <= _now_wat <= _parse_hm(_ov_close, 23, 59)):
                        raise ValueError(MSG.ORDER_OUTSIDE_ORDERING_HOURS)
                # Override says open with no specific times → open all day, allow
            else:
                # 2. Check operating_hours table for today's weekday
                _weekday = _now_utc.weekday()
                _oh_rows = (
                    db.table("operating_hours")
                    .select("is_closed,opens_at,closes_at,open_time,close_time")
                    .eq("weekday", _weekday)
                    .execute()
                ) or []
                _oh = _oh_rows[0] if _oh_rows else None

                if _oh is not None:
                    if _oh.get("is_closed"):
                        raise ValueError(MSG.ORDER_OUTSIDE_ORDERING_HOURS)
                    _oh_open = _oh.get("opens_at") or _oh.get("open_time")
                    _oh_close = _oh.get("closes_at") or _oh.get("close_time")
                    if _oh_open and _oh_close:
                        if not (_parse_hm(_oh_open, 0, 0) <= _now_wat <= _parse_hm(_oh_close, 23, 59)):
                            raise ValueError(MSG.ORDER_OUTSIDE_ORDERING_HOURS)
                else:
                    # 3. Fall back to config-based window
                    _open_str = current_app.config.get("ORDERING_WINDOW_OPEN_TIME", "08:00")
                    _close_str = current_app.config.get("ORDERING_WINDOW_CLOSE_TIME", "16:00")
                    if not (_parse_hm(_open_str, 8, 0) <= _now_wat <= _parse_hm(_close_str, 16, 0)):
                        raise ValueError(MSG.ORDER_OUTSIDE_ORDERING_HOURS)
        except ValueError:
            raise
        except Exception:
            pass  # If hours config is malformed, allow the order

    # §22: delivery_window_id is NOT accepted from the client payload.
    # The system always auto-assigns the current open delivery window.
    # Users cannot choose their own window; this prevents gaming the queue.
    window_id = None
    try:
        open_windows = (
            db.table("delivery_windows")
            .select("id,status,starts_at")
            .eq("status", "open")
            .order("starts_at", ascending=True)
            .limit(1)
            .execute()
        ) or []
        if open_windows:
            window_id = open_windows[0]["id"]
    except Exception:
        pass  # window_id stays None; order proceeds without one
    scheduled_for = None
    if is_scheduled:
        scheduled_window_id = payload.get("scheduled_for_window_id")
        scheduled_window = None
        if scheduled_window_id:
            # Explicit window ID provided — validate it (backward compatible)
            scheduled_window = (
                db.table("delivery_windows")
                .select("id,status,starts_at")
                .eq("id", scheduled_window_id)
                .single()
                .execute()
            )
            if not scheduled_window or scheduled_window.get("status") != "open":
                raise ValueError(MSG.ORDER_SCHEDULE_WINDOW_INVALID)
        else:
            # §Spec §18: date-only scheduling — auto-assign to next available
            # delivery window starting after the current moment. The client
            # supplies is_scheduled=True (and optionally a date hint via
            # scheduled_date YYYY-MM-DD); no window ID required.
            now_iso = datetime.now(timezone.utc).isoformat()
            _future = (
                db.table("delivery_windows")
                .select("id,status,starts_at")
                .gt("starts_at", now_iso)
                .order("starts_at", ascending=True)
                .limit(1)
                .execute()
            ) or []
            if _future:
                scheduled_window = _future[0]
                scheduled_window_id = scheduled_window["id"]
            # If no future window exists, order proceeds without one (graceful degradation)
        scheduled_for = payload.get("scheduled_for") or (scheduled_window.get("starts_at") if scheduled_window else None)
        if not window_id and scheduled_window_id:
            window_id = scheduled_window_id

        # Capacity check: count non-cancelled orders already booked into this window
        window_orders = (
            db.table("orders")
            .select("id")
            .eq("delivery_window_id", scheduled_window_id)
            .not_.in_("status", ["cancelled", "refunded"])
            .execute()
        ) or []
        # Per-window cap stored in kitchen_settings as "window_capacity" (optional)
        cap_row = (
            db.table("kitchen_settings")
            .select("value")
            .eq("key", "window_capacity")
            .single()
            .execute()
        )
        raw_cap = cap_row.get("value") if cap_row else None
        if raw_cap and str(raw_cap).isdigit() and len(window_orders) >= int(raw_cap):
            raise ValueError(MSG.ORDER_WINDOW_AT_CAPACITY)

    raw_items = payload.get("items", [])
    if not raw_items:
        raise ValueError(MSG.ORDER_ITEMS_EMPTY)

    # Pre-fetch today's active order IDs once for daily-limit checks (excludes cancelled/refunded)
    today_orders = (
        db.table("orders")
        .select("id")
        .gte("created_at", _today_start_iso())
        .not_.in_("status", ["cancelled", "refunded"])
        .execute()
    ) or []
    today_order_ids = {o["id"] for o in today_orders}

    subtotal = 0.0
    order_items = []
    for item in raw_items:
        try:
            menu_item = (
                db.table("menu_items")
                .select("id,name,price,hp_earn_value,hp_earn,hp_multiplier,is_available,deleted_at,daily_limit")
                .eq("id", item["menu_item_id"])
                .single()
                .execute()
            )
        except SupabaseError as exc:
            if "hp_multiplier" not in str(exc):
                raise
            menu_item = (
                db.table("menu_items")
                .select("id,name,price,hp_earn_value,hp_earn,is_available,deleted_at,daily_limit")
                .eq("id", item["menu_item_id"])
                .single()
                .execute()
            )
        if not menu_item:
            raise ValueError(MSG.ORDER_MENU_ITEM_NOT_FOUND.format(id=item["menu_item_id"]))
        if not menu_item.get("is_available") or menu_item.get("deleted_at"):
            raise ValueError(MSG.ORDER_MENU_ITEM_UNAVAILABLE.format(name=menu_item["name"]))

        qty = max(1, int(item.get("quantity", 1)))

        # Enforce per-item daily limit
        daily_limit = menu_item.get("daily_limit")
        if daily_limit is not None:
            count_today = _count_item_today(db, menu_item["id"], today_order_ids)
            remaining = max(0, int(daily_limit) - count_today)
            if qty > remaining:
                raise ValueError(MSG.ORDER_MENU_ITEM_SOLD_OUT_TODAY.format(name=menu_item["name"], remaining=remaining))

        from decimal import Decimal
        unit_price = Decimal(str(menu_item["price"]))

        # Resolve variation selections and add any price deltas
        selected_variations = item.get("selected_variations", [])
        variation_price_delta, resolved_variations = _resolve_item_variations(db, menu_item, selected_variations)

        # Resolve required/optional per-item add-on group selections
        selected_addons = item.get("selected_addons", [])
        addon_price_delta, resolved_addon_selections = _resolve_item_addons(db, menu_item, selected_addons)
        addon_price_delta_dec = Decimal(str(addon_price_delta))

        effective_unit_price = unit_price + variation_price_delta + addon_price_delta_dec
        effective_unit_price = effective_unit_price.quantize(Decimal("0.01"))
        try:
            hp_multiplier = float(menu_item.get("hp_multiplier") or 1.0)
        except (TypeError, ValueError):
            hp_multiplier = 1.0
        if hp_multiplier not in (0.5, 1.0, 2.0):
            hp_multiplier = 1.0

        line_total = (effective_unit_price * Decimal(str(qty))).quantize(Decimal("0.01"))

        order_items.append({
            "menu_item_id": menu_item["id"],
            "name_snapshot": menu_item["name"],
            "quantity": qty,
            "price_snapshot": float(effective_unit_price),
            "hp_earn_snapshot": menu_item.get("hp_earn_value") or menu_item.get("hp_earn") or 0,
            "hp_multiplier_snapshot": hp_multiplier,
            "line_total": float(line_total),
            "selected_variations": resolved_variations,
            "is_addon": False,
            "_addon_selections": resolved_addon_selections,
        })
        subtotal += float(line_total)

    # Resolve order-level add-ons (group_id IS NULL flat add-ons)
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
        if not addon.get("is_available") or addon.get("is_archived"):
            raise ValueError(f"Add-on '{addon['name']}' is not currently available")
        addon_qty = max(1, int(addon_entry.get("quantity", 1)))
        addon_price = Decimal(str(addon["price"]))
        line_total = (addon_price * Decimal(str(addon_qty))).quantize(Decimal("0.01"))
        order_items.append({
            "menu_item_id": None,
            "addon_id": addon["id"],
            "name_snapshot": addon["name"],
            "quantity": addon_qty,
            "price_snapshot": float(addon_price),
            "hp_earn_snapshot": 0,
            "line_total": float(line_total),
            "selected_variations": [],
            "is_addon": True,
        })
        subtotal += float(line_total)

    subtotal = float(Decimal(str(subtotal)).quantize(Decimal("0.01")))

    # ── Order Lock check (detect active lock for today before computing total) ──
    # Must run before total is calculated so the discount is baked into the order.
    order_lock = None
    order_lock_discount = 0.0
    if user_id:
        try:
            today_date = datetime.now(timezone.utc).date().isoformat()
            _lock_rows = (
                db.table("order_locks")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "active")
                .eq("locked_date", today_date)
                .execute()
            ) or []
            if _lock_rows:
                order_lock = _lock_rows[0]
                if order_lock.get("reward_type", "discount") == "discount":
                    _lock_pct = float(order_lock.get("discount_pct", 10))
                    order_lock_discount = round(subtotal * _lock_pct / 100.0, 2)
        except Exception as _le:
            logger.warning("create_order: order lock check failed for user %s: %s", user_id, _le)
            order_lock = None

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

    delivery_fee = 0.0

    # ── Delivery location fee resolution ──────────────────────────────────────
    delivery_type = payload.get("delivery_type")  # "on_campus" | "off_campus" | None
    if delivery_type is not None and delivery_type not in ("on_campus", "off_campus"):
        raise ValueError("Invalid delivery type")

    delivery_location_id = payload.get("delivery_location_id")
    delivery_location_lat = payload.get("delivery_location_lat")
    delivery_location_lon = payload.get("delivery_location_lon")

    # If delivery_address_id is provided, verify ownership and retrieve coordinates
    delivery_address_id = payload.get("delivery_address_id")
    if delivery_address_id and user_id:
        try:
            addr = db.table("user_addresses").eq("id", delivery_address_id).single().execute()
            if addr:
                if addr.get("user_id") != user_id:
                    raise ValueError("Unauthorized address access")
                if addr.get("latitude") is not None and addr.get("longitude") is not None:
                    delivery_location_lat = float(addr["latitude"])
                    delivery_location_lon = float(addr["longitude"])
                if addr.get("delivery_location_id"):
                    delivery_location_id = addr["delivery_location_id"]
                if addr.get("delivery_type"):
                    delivery_type = addr["delivery_type"]
        except ValueError as ve:
            if "Unauthorized" in str(ve):
                raise
        except Exception:
            pass

    from app.routes.delivery import validate_coordinates
    if delivery_location_lat is not None or delivery_location_lon is not None:
        delivery_location_lat, delivery_location_lon = validate_coordinates(delivery_location_lat, delivery_location_lon)

    if delivery_type == "on_campus" and delivery_location_id:
        try:
            hostel = (
                db.table("hostels")
                .select("delivery_fee")
                .eq("id", delivery_location_id)
                .eq("is_active", "true")
                .single()
                .execute()
            )
            if hostel:
                delivery_fee = float(hostel.get("delivery_fee") or 0)
        except Exception:
            pass  # Table may not exist yet — fee stays 0
    elif delivery_type == "off_campus" and delivery_location_id:
        try:
            gate = (
                db.table("gates")
                .select("*")
                .eq("id", delivery_location_id)
                .eq("is_active", "true")
                .single()
                .execute()
            )
            if gate:
                from app.routes.delivery import calculate_off_campus_fee
                delivery_fee, _ = calculate_off_campus_fee(
                    gate,
                    delivery_location_lat,
                    delivery_location_lon,
                )
        except Exception as e:
            if "Coordinate" in str(e):
                raise ValueError(str(e))
            pass  # Table may not exist yet — fee stays 0

    from decimal import Decimal
    # Apply squad delivery-fee discount
    delivery_fee_dec = Decimal(str(delivery_fee))
    if is_squad_order and config.get("SQUAD_DELIVERY_DISCOUNT_ENABLED", True):
        pct = Decimal(str(config.get("SQUAD_DELIVERY_DISCOUNT_PCT", 100)))
        squad_delivery_discount_dec = (delivery_fee_dec * pct / Decimal("100.0")).quantize(Decimal("0.01"))
        squad_delivery_discount = float(squad_delivery_discount_dec)
        delivery_fee_dec = max(Decimal("0.0"), delivery_fee_dec - squad_delivery_discount_dec)
        delivery_fee = float(delivery_fee_dec)

    # Apply squad subtotal discount
    subtotal_dec = Decimal(str(subtotal))
    if is_squad_order and config.get("SQUAD_ORDER_DISCOUNT_ENABLED", False):
        pct = Decimal(str(config.get("SQUAD_ORDER_DISCOUNT_PCT", 10)))
        squad_discount_dec = (subtotal_dec * pct / Decimal("100.0")).quantize(Decimal("0.01"))
        squad_discount = float(squad_discount_dec)

    subtotal_dec = Decimal(str(subtotal))
    promo_discount_dec = Decimal(str(promo_discount))
    hp_discount_dec = Decimal(str(hp_discount))
    squad_discount_dec = Decimal(str(squad_discount))
    order_lock_discount_dec = Decimal(str(order_lock_discount))

    total_dec = subtotal_dec - promo_discount_dec - hp_discount_dec - squad_discount_dec - order_lock_discount_dec + delivery_fee_dec
    total_dec = max(Decimal("0.0"), total_dec.quantize(Decimal("0.01")))
    total = float(total_dec)

    payment_method = payload.get("payment_method", "card")
    wallet_amount_used_dec = Decimal("0.0")
    card_amount_used_dec = Decimal("0.0")

    if payment_method == "wallet":
        wallet_amount_used_dec = total_dec
    elif payment_method == "card":
        card_amount_used_dec = total_dec
    elif payment_method == "split":
        wallet_amount_used_dec = min(Decimal(str(payload.get("wallet_amount", 0))), total_dec)
        card_amount_used_dec = (total_dec - wallet_amount_used_dec).quantize(Decimal("0.01"))

    wallet_amount_used = float(wallet_amount_used_dec)
    card_amount_used = float(card_amount_used_dec)

    # Pre-check wallet balance before inserting order (for both wallet and split payment methods)
    if payment_method in ("wallet", "split") and user_id and wallet_amount_used > 0:
        wallet = db.table("wallets").select("balance").eq("user_id", user_id).single().execute()
        if not wallet or float(wallet.get("balance", 0)) < wallet_amount_used:
            raise ValueError(MSG.ORDER_WALLET_INSUFFICIENT.format(need=wallet_amount_used))

    is_guest = user_id is None
    claim_token = str(uuid.uuid4()) if is_guest else None

    # Calculate variables for RPC payload
    total_discount = round(promo_discount + squad_discount + order_lock_discount, 2)
    delivery_address_snapshot = payload.get("delivery_address") or {}

    # Pre-calculate hp_preview
    hp_preview_items = []
    hp_preview_total = 0
    hp_preview_base = 0
    for line in order_items:
        if line.get("is_addon") or not line.get("price_snapshot"):
            continue
        base_line = int(
            float(line["price_snapshot"]) * int(line.get("quantity") or 1)
            * current_app.config["HP_PER_NAIRA_FOOD"]
        )
        multiplier = float(line.get("hp_multiplier_snapshot") or 1.0)
        line_hp = round(base_line * multiplier)
        hp_preview_base += base_line
        hp_preview_total += line_hp
        hp_preview_items.append({
            "menu_item_id": line.get("menu_item_id"),
            "quantity": int(line.get("quantity") or 1),
            "hp_multiplier": multiplier,
            "base_hp": base_line,
            "hp": line_hp,
        })
    hp_preview = {
        "base_hp": hp_preview_base,
        "total_hp": hp_preview_total,
        "items": hp_preview_items,
    }

    campus_id = getattr(g, 'campus_id', None)

    rpc_payload = {
        "p_user_id": user_id,
        "p_campus_id": campus_id,
        "p_guest_name": payload.get("guest_name"),
        "p_guest_email": payload.get("guest_email"),
        "p_guest_phone": payload.get("guest_phone"),
        "p_claim_token": claim_token,
        "p_status": "received",
        "p_payment_status": "pending",
        "p_subtotal": subtotal,
        "p_delivery_fee": delivery_fee,
        "p_discount_amount": total_discount,
        "p_total_amount": total,
        "p_wallet_amount_used": wallet_amount_used,
        "p_card_amount_used": card_amount_used,
        "p_hp_redeemed": 0,
        "p_delivery_type": delivery_type,
        "p_delivery_location_id": delivery_location_id,
        "p_delivery_location_lat": delivery_location_lat,
        "p_delivery_location_lon": delivery_location_lon,
        "p_delivery_address_snapshot": delivery_address_snapshot,
        "p_delivery_window_id": window_id,
        "p_is_scheduled": is_scheduled,
        "p_scheduled_for": scheduled_for,
        "p_is_squad_order": is_squad_order,
        "p_squad_name": payload.get("squad_name"),
        "p_squad_discount_amount": squad_discount,
        "p_squad_item_count": squad_item_count,
        "p_notes": payload.get("notes", ""),
        "p_gift_included": False,
        "p_idempotency_key": idempotency_key,
        "p_promo_code_id": promo_code_id,
        "p_items": order_items,
        "p_order_lock_id": order_lock.get("id") if order_lock else None
    }

    try:
        result = db.rpc("hg_create_order_atomic", rpc_payload)
    except Exception as exc:
        result = {"error": str(exc)}

    if result is None:
        result = {}

    if result.get("error"):
        raise ValueError(result["error"])

    order = db.table("orders").select("*").eq("id", result["order_id"]).single().execute()
    if not result.get("idempotent"):
        order["hp_preview"] = hp_preview
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
    Validates rider and kitchen caller permissions prior to walking states.

    Returns:
        {"steps": ["preparing", "ready", ...], "final": <order dict>}
    """
    from flask import has_app_context, g
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).single().execute()
    if not order:
        raise ValueError("Order not found")

    if changed_by:
        caller_role = None
        caller_campus = None
        if has_app_context() and getattr(g, 'user_id', None) == changed_by:
            caller_role = getattr(g, 'user_role', None)
            caller_campus = getattr(g, 'campus_id', None)
        else:
            try:
                c_prof = db.table("profiles").select("role,campus_id").eq("id", changed_by).single().execute()
                if c_prof:
                    caller_role = c_prof.get("role")
                    caller_campus = c_prof.get("campus_id")
            except Exception:
                pass

        if caller_role == "rider":
            batch_id = order.get("batch_id")
            assigned_rider_id = None
            if batch_id:
                try:
                    batch = db.table("delivery_batches").select("rider_id").eq("id", batch_id).single().execute()
                    if batch:
                        assigned_rider_id = batch.get("rider_id")
                except Exception:
                    pass
            if not assigned_rider_id or assigned_rider_id != changed_by:
                raise ValueError("Unauthorized: Rider is not assigned to this order")

        elif caller_role == "kitchen":
            order_campus = order.get("campus_id")
            if caller_campus and order_campus and caller_campus != order_campus:
                raise ValueError("Unauthorized: Kitchen staff is scoped to a different campus")

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

    current_pay_status = order.get("payment_status")
    if current_pay_status == "paid":
        return order  # idempotent

    # Enforce strict transition policies
    if current_pay_status in ("refunded", "cancelled"):
        raise ValueError(f"Cannot transition payment status from '{current_pay_status}' to 'paid'")

    if order.get("status") in ("cancelled", "refunded"):
        raise ValueError(f"Cannot transition payment status because order is already '{order.get('status')}'")

    # Call the existing RPC rather than a direct table update
    provider = "paystack"

    try:
        payment_result = db.rpc("hg_mark_order_paid", {
            "p_order_id": order_id,
            "p_provider": provider,
            "p_provider_reference": payment_reference,
            "p_amount": order["total_amount"],
            "p_metadata": provider_response or {},
        })
    except Exception as exc:
        payment_result = {"error": str(exc)}

    if not payment_result:
        raise ValueError("Failed to mark order as paid")

    if isinstance(payment_result, dict) and payment_result.get("error"):
        raise ValueError(payment_result["error"])

    # Complete the referral atomically on the same successful payment transition.
    if order.get("user_id"):
        try:
            paid_orders = (
                db.table("orders")
                .select("id")
                .eq("user_id", order["user_id"])
                .eq("payment_status", "paid")
                .execute()
            ) or []

            if len(paid_orders) == 1:
                from app.routes.referrals import _complete_referral_award

                referral = (
                    db.table("referrals")
                    .select("*")
                    .eq("referred_user_id", order["user_id"])
                    .single()
                    .execute()
                )

                if referral and not referral.get("hp_awarded", 0):
                    _complete_referral_award(referral, order_id)
        except Exception as exc:
            logger.error(
                "Referral completion failed for order %s: %s",
                order_id,
                exc,
            )

    updated_order = (
        db.table("orders")
        .select("*")
        .eq("id", order_id)
        .single()
        .execute()
    )

    if order.get("user_id"):
        send_notification(
            user_id=order["user_id"],
            notif_type="order_confirmed",
            template_data={"order_id": order_id[:8].upper()},
            reference_id=order_id,
            reference_type="order",
        )

    return updated_order


def update_order_status(order_id: str, new_status: str, changed_by: str = None, notes: str = "") -> dict:
    """
    Transition order status. Validates state machine. Awards HP on delivery.
    Notifications and delivery rewards run in a daemon thread so the response
    is not held up by sequential Supabase notification inserts.
    """
    import threading as _threading
    from flask import current_app as _app, has_app_context, g
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).single().execute()
    if not order:
        raise ValueError("Order not found")

    if changed_by:
        caller_role = None
        caller_campus = None
        if has_app_context() and getattr(g, 'user_id', None) == changed_by:
            caller_role = getattr(g, 'user_role', None)
            caller_campus = getattr(g, 'campus_id', None)
        else:
            try:
                c_prof = db.table("profiles").select("role,campus_id").eq("id", changed_by).single().execute()
                if c_prof:
                    caller_role = c_prof.get("role")
                    caller_campus = c_prof.get("campus_id")
            except Exception:
                pass

        if caller_role == "rider":
            batch_id = order.get("batch_id")
            assigned_rider_id = None
            if batch_id:
                try:
                    batch = db.table("delivery_batches").select("rider_id").eq("id", batch_id).single().execute()
                    if batch:
                        assigned_rider_id = batch.get("rider_id")
                except Exception:
                    pass
            if not assigned_rider_id or assigned_rider_id != changed_by:
                raise ValueError("Unauthorized: Rider is not assigned to this order")

        elif caller_role == "kitchen":
            order_campus = order.get("campus_id")
            if caller_campus and order_campus and caller_campus != order_campus:
                raise ValueError("Unauthorized: Kitchen staff is scoped to a different campus")

    current_status = order["status"]
    allowed = VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise ValueError(f"Cannot transition '{current_status}' → '{new_status}'")

    now = datetime.now(timezone.utc).isoformat()
    update_data = {"status": new_status}
    ts_field = STATUS_TIMESTAMPS.get(new_status)
    if ts_field:
        update_data[ts_field] = now

    updated = db.table("orders").eq("id", order_id).update(update_data).execute()
    _log_status_change(order_id, current_status, new_status, changed_by, notes)

    # Gift wiring: notify rider assigned; auto-return on failed/unclaimed delivery
    if order.get("user_id"):
        if new_status == "assigned":
            try:
                from app.services.gift_service import notify_gift_rider_assigned
                notify_gift_rider_assigned(order["user_id"], order_id)
            except Exception:
                pass
        elif new_status in ("delivery_attempted", "unclaimed"):
            try:
                from app.services.gift_service import mark_gift_returned
                mark_gift_returned(order["user_id"], order_id)
            except Exception:
                pass

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
    1. Food HP + tier bonus (using calculate_delivery_hp)
    2. Atomic unconditional credit via hg_credit_delivery_hp_atomic RPC
    3. Welcome bonus
    4. Tier recalculation
    """
    user_id = order["user_id"]
    order_id = order["id"]
    subtotal = float(order.get("subtotal", 0))

    tier_info = hp_service.get_user_tier(user_id)
    tier = tier_info.get("tier") or {}
    tier_slug = tier.get("slug", "ember")

    db = get_db()
    order_items = order.get("order_items")
    if not isinstance(order_items, list):
        try:
            order_items = (
                db.table("order_items")
                .select("price_snapshot,quantity,hp_earn_snapshot,hp_multiplier_snapshot,is_addon")
                .eq("order_id", order_id)
                .execute()
            ) or []
        except SupabaseError as exc:
            if "hp_multiplier_snapshot" not in str(exc):
                raise
            order_items = (
                db.table("order_items")
                .select("price_snapshot,quantity,hp_earn_snapshot,is_addon")
                .eq("order_id", order_id)
                .execute()
            ) or []

    # Step 1: Calculate HP in Python (business logic) — may be zero
    hp_amount = hp_service.calculate_delivery_hp(
        order_total=subtotal,
        tier_slug=tier_slug,
        order_items=order_items,
    )

    # Apply next_order_hp_multiplier bonus if present, then reset to 1
    try:
        prof = db.table("profiles").select("next_order_hp_multiplier").eq("id", user_id).single().execute()
        mult = float((prof or {}).get("next_order_hp_multiplier") or 1)
        if mult > 1:
            hp_amount = round(hp_amount * mult)
            db.table("profiles").eq("id", user_id).update({"next_order_hp_multiplier": 1})
    except Exception as me:
        logger.warning("_handle_delivery_rewards: next_order_hp_multiplier check failed: %s", me)

    # Step 2: Atomically credit via Supabase RPC — call for EVERY eligible
    # delivery, zero-HP included, so the idempotency marker always gets set
    try:
        result = db.rpc("hg_credit_delivery_hp_atomic", {
            "p_order_id": order_id,
            "p_user_id": user_id,
            "p_hp_amount": hp_amount,
            "p_tier_name": tier_slug,
            "p_source_type": "food_order"
        })
    except Exception as exc:
        result = {"error": str(exc)}

    if result is None:
        result = {}

    if result.get("already_credited"):
        return
    if result.get("error"):
        logger.error(f"Failed to credit HP for order {order_id}: {result['error']}")
        return

    welcome_result = hp_service.award_welcome_bonus(user_id, order_id)

    tier_change = hp_service.recalculate_tier(user_id)

    order_updates = {
        "hp_earned": hp_amount,
        "hp_credited_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        db.table("orders").eq("id", order_id).update(order_updates).execute()
    except Exception:
        pass

    # All HP/tier/referral logic above is synchronous so callers see updated
    # balances immediately. Notifications are fire-and-forget — queue them as
    # daemon threads so they don't add latency to the status-update response.
    import threading as _t

    total_hp_awarded = hp_amount + welcome_result.get("awarded", 0)

    def _send_delivery_notifications():
        if total_hp_awarded > 0:
            send_notification(
                user_id=user_id,
                notif_type="hp_earned",
                template_data={"hp": total_hp_awarded, "total_hp": total_hp_awarded},
                reference_id=order_id,
                reference_type="order",
            )
        unlocked = int(result.get("unlocked_hp") or 0)
        if unlocked > 0:
            send_notification(
                user_id=user_id,
                notif_type="hp_unlocked",
                template_data={"unlocked_hp": unlocked},
            )
        if tier_change.get("changed") and tier_change.get("tier"):
            tier_name = tier_change["tier"].get("name", "new tier")
            send_notification(
                user_id=user_id,
                notif_type="tier_upgrade",
                template_data={"tier_name": tier_name},
                reference_id=user_id,
                reference_type="user_tier",
            )

    _t.Thread(target=_send_delivery_notifications, daemon=True).start()

    # Try to reclaim a missed login-streak day via this order
    try:
        from app.services.streak_service import try_reclaim_checkin, process_order_streak
        try_reclaim_checkin(user_id)
        process_order_streak(user_id, order_id)
    except Exception as _se:
        logger.warning("_handle_delivery_rewards: streak hooks failed for %s: %s", user_id, _se)

    # Fire first_order badge trigger
    try:
        from app.services.milestone_service import check_milestone_trigger
        delivered_count_rows = (
            get_db().table("orders")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "delivered")
            .execute()
        ) or []
        delivered_count = len(delivered_count_rows)
        check_milestone_trigger(user_id, "first_order", delivered_count)
        check_milestone_trigger(user_id, "order_count", delivered_count)
    except Exception as _me:
        logger.warning("_handle_delivery_rewards: milestone trigger failed for %s: %s", user_id, _me)

    # First-order gift check — runs synchronously to prevent critical order mutation loss
    try:
        from app.services.gift_service import maybe_grant_first_order_gift
        maybe_grant_first_order_gift(user_id, order_id)
    except Exception as _ge:
        logger.warning("first_order_gift check failed for order %s: %s", order_id, _ge)

    # Update last_activity_at for decay-onset tracking
    try:
        get_db().table("profiles").eq("id", user_id).update({
            "last_activity_at": datetime.now(timezone.utc).isoformat()
        }).execute()
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
        raise ValueError(MSG.ORDER_PROMO_INVALID.format(code=code))

    now = datetime.now(timezone.utc).isoformat()
    if promo.get("ends_at") and promo["ends_at"] < now:
        raise ValueError(MSG.STOREFRONT_PROMO_EXPIRED)
    if promo.get("starts_at") and promo["starts_at"] > now:
        raise ValueError(MSG.STOREFRONT_PROMO_NOT_ACTIVE)
    if promo.get("max_uses") and int(promo.get("used_count") or 0) >= promo["max_uses"]:
        raise ValueError(MSG.STOREFRONT_PROMO_LIMIT)
    if order_subtotal < float(promo.get("min_order_amount") or 0):
        raise ValueError(MSG.ORDER_PROMO_MIN_ORDER.format(min_amount=float(promo.get("min_order_amount", 0))))

    if promo.get("max_uses_per_user") and user_id:
        user_uses = (
            db.table("orders")
            .select("id")
            .eq("user_id", user_id)
            .eq("promo_code_id", promo["id"])
            .neq("status", "cancelled")
            .execute()
        )
        if len(user_uses or []) >= int(promo["max_uses_per_user"]):
            raise ValueError("You have already used this promo code the maximum number of times")

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
        }).execute()
    except Exception:
        pass


def _send_status_notification(order: dict, new_status: str):
    user_id = order.get("user_id")
    if not user_id:
        return
    # push+in_app for all order status transitions.
    # email is added for confirmed, delivered, and cancelled (summary-worthy events).
    _STATUS_NOTIF_TYPES = {
        "preparing", "ready", "assigned", "out_for_delivery",
        "delivered", "delivery_attempted", "unclaimed", "cancelled",
    }
    if new_status in _STATUS_NOTIF_TYPES:
        # Channels come from EMAIL_TYPES in notification_service (delivered, cancelled → email).
        # delivery_attempted email intentionally removed per updated EMAIL_TYPES spec.
        send_notification(
            user_id=user_id,
            notif_type=f"order_{new_status}",
            template_data={},  # all order status bodies have no dynamic placeholders
            reference_id=order["id"],
            reference_type="order",
            urgency="high" if new_status == "delivery_attempted" else None,
        )
        # 8.1 — Immediate thank-you on delivery (in-app + push only)
        if new_status == "delivered":
            try:
                send_notification(
                    user_id=user_id,
                    notif_type="order_thank_you",
                    template_data={},
                    reference_id=order["id"],
                    reference_type="order",
                )
            except Exception:
                pass
