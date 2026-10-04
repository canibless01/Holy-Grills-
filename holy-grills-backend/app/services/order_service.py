"""
Order service — order creation, status transitions, delivery rewards, payment confirmation.
"""

import uuid
from datetime import datetime, timezone, timedelta

class OrderingWindowUnavailable(ValueError):
    """Raised when an ordering window is closed or at capacity.

    Carries an optional `next_available_date` so callers (routes) can surface
    a "schedule for {date}" prompt instead of a plain rejection.
    """
    def __init__(self, message: str, next_available_date: str = None):
        super().__init__(message)
        self.next_available_date = next_available_date
from decimal import Decimal
from app.utils.tz import today_wat
from app.utils.schedule import effective_ordering_windows
from app.utils.settings import setting_or_config, setting_bool
from flask import current_app
from app.db import get_db, get_user_client, SupabaseError
from app.services import hp_service
from app.services.notification_service import send_notification
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── SHARED: order status transitions ────────────────────────────────────────────────────────────
class OrderStatusError(ValueError):
    """Failed status change. Still a ValueError, so existing `except ValueError` callers keep working."""
    http_status = 400


class OrderNotFoundError(OrderStatusError):
    http_status = 404


class OrderForbiddenError(OrderStatusError):
    http_status = 403


class OrderConflictError(OrderStatusError):
    http_status = 409


def _effective_rider_id(order: dict):
    """Rider who may act on `order` — the same rule as the database function hg_effective_rider:
    an explicit delivery_assignments row wins, otherwise the batch's rider."""
    db = get_db()
    rows = db.table("delivery_assignments").select("rider_id").eq("order_id", order["id"]).limit(1).execute() or []
    if rows:
        return rows[0].get("rider_id")
    if order.get("batch_id"):
        batch = db.table("delivery_batches").select("rider_id").eq("id", order["batch_id"]).limit(1).execute() or []
        return batch[0].get("rider_id") if batch else None
    return None


def _map_db_error(exc):
    """Errors raised by the orders triggers (state machine / rider scoping) -> typed errors."""
    text = str(exc)
    if "Riders can only" in text:
        return OrderForbiddenError(MSG.RIDER_NOT_ASSIGNED_TO_ORDER)
    if "Invalid order status transition" in text:
        return OrderConflictError(MSG.ORDER_STATUS_CONFLICT)
    return None


VALID_TRANSITIONS = {
    "received":           ["preparing", "cancelled", "refunded"],
    "paid":               ["preparing", "cancelled", "refunded"],
    "preparing":          ["ready", "cancelled", "refunded"],
    "ready":              ["assigned", "out_for_delivery", "cancelled", "refunded"],
    "assigned":           ["ready", "out_for_delivery", "cancelled", "refunded"],
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


def create_order_apply_rpc_total(rpc_result, locally_computed_total):
    """
    Call this immediately after the hg_create_order_atomic RPC call
    returns, instead of using locally_computed_total for anything shown
    to the customer or charged.
    """
    total_amount = rpc_result.get("total_amount", locally_computed_total)
    discount_applied = rpc_result.get("order_lock_discount_applied", False)
    return total_amount, discount_applied


def _today_start_iso():
    """Start of today in WAT (the business day), expressed as a UTC ISO timestamp."""
    from app.utils.tz import today_wat, WAT_OFFSET
    wat_date = today_wat()
    wat_midnight_naive = datetime(wat_date.year, wat_date.month, wat_date.day)
    utc_midnight = wat_midnight_naive - WAT_OFFSET
    return utc_midnight.replace(tzinfo=timezone.utc).isoformat()


def _check_kitchen_capacity(db):
    """Raise ValueError if the kitchen's daily order cap has been reached."""
    from flask import has_request_context, g
    campus_id = getattr(g, 'campus_id', None) if has_request_context() else None
    rows = (
        db.table("kitchen_settings")
        .select("value")
        .eq("key", "daily_order_capacity")
        .eq("campus_id", campus_id)
        .execute()
    ) or []
    raw = rows[0].get("value") if rows else ""
    if not raw or not str(raw).isdigit():
        return  # no cap configured for this campus
    capacity = int(raw)
    orders_today = (
        db.table("orders")
        .select("id,is_squad_order,squad_item_count")
        .eq("campus_id", campus_id)
        .gte("created_at", _today_start_iso())
        .not_.in_("status", ["cancelled", "refunded"])
        .limit(1000)
        .execute()
    ) or []
    used = sum(_order_capacity_weight(o) for o in orders_today)
    if used >= capacity:
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
            .select("id,name,is_required,min_selections,max_selections")
            .eq("menu_item_id", menu_item_id)
            .execute()
        ) or []
    except Exception:
        groups = []
        logger.error("menu_item_variation_groups query failed for item %s", menu_item_id)

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
        min_select = group.get("min_selections")
        if min_select is None:
            min_select = 1 if group.get("is_required") else 0
        min_select = int(min_select)

        max_select = group.get("max_selections")
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
        min_select = int(group.get("min_select", 0))
        max_select = int(group.get("max_select", 1))
        if (group.get("is_required") or min_select > 0) and count < min_select:
            raise ValueError(MSG.ORDER_ADDON_GROUP_REQUIRED.format(
                group_name=group["name"], min_select=min_select, item_name=menu_item["name"]
            ))
        if count > max_select:
            raise ValueError(MSG.ORDER_ADDON_GROUP_TOO_MANY.format(
                group_name=group["name"], max_select=max_select, item_name=menu_item["name"]
            ))

    return round(price_delta_total, 2), resolved_selections


def _assert_redemption_claimable(db, redemption_id: str, user_id: str) -> None:
    """Reject an already-spent reward *before* anything is charged.

    The database is the authority (hg_claim_reward_redemption_for_order), but
    failing here gives the customer a clear 400 instead of an error after the
    money moved. A reward is spendable exactly once: status 'fulfilled' and not
    yet attached to an order.
    """
    try:
        rows = (
            db.table("reward_redemptions")
            .select("id,user_id,status,attached_order_id")
            .eq("id", redemption_id)
            .execute()
        ) or []
    except SupabaseError as exc:
        # e.g. attached_order_id does not exist yet (migration not applied) —
        # let the RPC be the judge rather than blocking a legitimate order.
        logger.warning("create_order: reward pre-check unavailable (%s) — deferring to the RPC", exc)
        return

    if not rows:
        raise ValueError("Reward redemption not found for this account.")
    row = rows[0]
    if str(row.get("user_id")) != str(user_id):
        raise ValueError("Reward redemption not found for this account.")
    if row.get("attached_order_id"):
        raise ValueError("This reward has already been used on an order.")
    if str(row.get("status") or "").lower() != "fulfilled":
        raise ValueError("This reward must be marked fulfilled before it can be used.")


def _claim_reward_redemption(db, redemption_id: str, user_id: str, order_id: str) -> dict:
    """Attach one redemption to one order — first writer wins, later calls no-op.

    Uses the conditional UPDATE in hg_claim_reward_redemption_for_order, so two
    concurrent checkouts holding the same redemption cannot both spend it.
    """
    res = db.rpc("hg_claim_reward_redemption_for_order", {
        "p_redemption_id": redemption_id,
        "p_user_id": user_id,
        "p_order_id": order_id,
    })
    return res if isinstance(res, dict) else {"claimed": False, "reason": "unexpected_rpc_result"}


def _consume_free_sides(db, user_id: str, campus_id, order_id: str) -> dict:
    """Spend this user's free-side selections on `order_id`.

    Primary path: hg_consume_free_sides_atomic does the credit decrement, the ₦0
    order line and the selection deletion in one transaction. If that migration
    is not applied yet, fall back to the Python consumer, which uses the same
    compare-and-set decrement, so a retry cannot double-spend either way.
    """
    from app.services.feature_flags import is_feature_enabled
    if not is_feature_enabled("free_side_credits"):
        return {"consumed": 0, "skipped": "feature_disabled"}

    try:
        res = db.rpc("hg_consume_free_sides_atomic", {
            "p_user_id": user_id,
            "p_order_id": order_id,
            "p_campus_id": campus_id,
        })
        if isinstance(res, dict):
            return res
    except SupabaseError as exc:
        code = str((getattr(exc, "details", None) or {}).get("code") or "")
        if code not in ("PGRST202", "42883") and exc.status_code != 404:
            raise
        logger.warning("create_order: hg_consume_free_sides_atomic missing (%s) — "
                       "using the Python consumer", exc)

    from app.routes.free_sides import consume_free_side_selections
    inserted = consume_free_side_selections(db, user_id, campus_id, order_id) or []
    return {"consumed": len(inserted), "source": "python_fallback"}


# The order RPC now claims p_redemption_id inside its own transaction and refuses
# the whole order when the reward cannot be spent. Its message wording is the
# database's; translate the known cases so the customer gets a stable 400.
_RPC_ERROR_MAP = (
    ("reward redemption is not available", MSG.REWARD_REDEMPTION_UNAVAILABLE),
    ("redemption is not available", MSG.REWARD_REDEMPTION_UNAVAILABLE),
    ("reward redemption is not yours", MSG.REWARD_REDEMPTION_UNAVAILABLE),
)


def _normalize_rpc_error(message: str) -> str:
    """Map a raw RPC refusal to the customer-facing wording, else pass it through."""
    text = str(message or "")
    low = text.lower()
    for marker, friendly in _RPC_ERROR_MAP:
        if marker in low:
            return friendly
    return text


def create_order(user_id: str | None, payload: dict) -> dict:
    """
    Create a new order. Supports authenticated and guest checkout.
    Validates kitchen capacity, daily item limits, window, resolves items,
    resolves add-ons, applies promo/HP discounts, returns order record.

    Payload additions vs v1:
      items[].selected_variations  — list of {variation_group_id, option_id}
      addons                       — list of {addon_id, quantity}
    """
    idempotency_key = payload.get("idempotency_key") or str(uuid.uuid4())   # frontend resends the same
    # key on a retry so the DB's unique constraint on it catches a genuine double-submit

    db = get_user_client()
    from flask import has_request_context, g
    campus_id = getattr(g, "campus_id", None) if has_request_context() else None
    if not campus_id:
        try:
            from app.routes.events import _get_campus_id
            campus_id = _get_campus_id()
        except Exception as exc:
            logger.debug("create_order: campus resolution from the request context failed: %s", exc)
    if not campus_id:
        raise ValueError("campus_id could not be resolved for this order")

    # Reject if kitchen is already at daily capacity
    _check_kitchen_capacity(db)

    is_scheduled = bool(payload.get("is_scheduled", False))
    ordering_window_id = None
    linked_delivery_window_id = None
    scheduled_for = payload.get("scheduled_for") if is_scheduled else None

    # scheduled_orders is a global switch (feature_flags rows carry no campus_id in this project),
    # so one check covers both ways an order can end up scheduled: an explicit request, and the
    # automatic next-available-slot fallback below.
    if is_scheduled or payload.get("accept_next_available_date"):
        from app.services.feature_flags import is_feature_enabled
        if not is_feature_enabled("scheduled_orders"):
            raise ValueError("Scheduled ordering is not available right now")

    if not is_scheduled:
        try:
            _win = resolve_ordering_window(db, campus_id)
            ordering_window_id = _win.get("id")
            linked_delivery_window_id = _win.get("linked_delivery_window_id")
        except OrderingWindowUnavailable:
            if not payload.get("accept_next_available_date"):
                raise
            tomorrow = (datetime.now(timezone.utc) + timedelta(hours=1) + timedelta(days=1)).date()
            next_slot = find_next_available_ordering_slot(db, campus_id, start_date=tomorrow)
            if not next_slot or not next_slot.get("date"):
                raise
            is_scheduled = True
            ordering_window_id = next_slot.get("window_id")
            scheduled_for = f"{next_slot['date']}T{next_slot.get('opens_at') or '08:00:00'}"
            if ordering_window_id:
                ow_row = db.table("ordering_windows").select("linked_delivery_window_id").eq("id", ordering_window_id).single().execute()
                if ow_row:
                    linked_delivery_window_id = ow_row.get("linked_delivery_window_id")

    window_id = linked_delivery_window_id

    raw_items = payload.get("items", [])
    if not raw_items:
        raise ValueError(MSG.ORDER_ITEMS_EMPTY)

    # Pre-fetch today's active order IDs once for daily-limit checks (excludes cancelled/refunded)
    today_orders = (
        db.table("orders")
        .select("id")
        .gte("created_at", _today_start_iso())
        .eq("campus_id", campus_id)
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

        availability = None
        try:
            availability = (
                db.table("menu_item_availability")
                .select("is_available,daily_limit,price_override,opens_at,closes_at")
                .eq("menu_item_id", menu_item["id"])
                .eq("campus_id", campus_id)
                .single()
                .execute()
            )
        except Exception as av_exc:
            logger.warning("create_order: availability lookup failed for %s: %s", menu_item["id"], av_exc)
            availability = None

        is_item_available = bool(menu_item.get("is_available"))
        if availability:
            from app.utils.tz import is_within_availability_window
            is_item_available = (
                is_item_available and bool(availability.get("is_available"))
                and is_within_availability_window(availability.get("opens_at"), availability.get("closes_at"))
            )

        if not is_item_available or menu_item.get("deleted_at"):
            raise ValueError(MSG.ORDER_MENU_ITEM_UNAVAILABLE.format(name=menu_item["name"]))

        qty = max(1, int(item.get("quantity", 1)))

        daily_limit = availability.get("daily_limit") if availability else menu_item.get("daily_limit")
        if daily_limit is not None:
            count_today = _count_item_today(db, menu_item["id"], today_order_ids)
            remaining = max(0, int(daily_limit) - count_today)
            if qty > remaining:
                raise ValueError(MSG.ORDER_MENU_ITEM_SOLD_OUT_TODAY.format(name=menu_item["name"], remaining=remaining))

        base_price = availability.get("price_override") if (availability and availability.get("price_override") is not None) else menu_item["price"]
        unit_price = Decimal(str(base_price))

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
            today_date = today_wat().isoformat()
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
    squad_item_count = sum(oi["quantity"] for oi in order_items if not oi.get("is_addon"))
    is_squad_order = False
    squad_id = None
    squad_roster_rows = []

    requested_squad_id = payload.get("squad_id")
    if requested_squad_id:
        squad_row = db.table("squads").select("id,name,creator_id,campus_id").eq("id", requested_squad_id).single().execute()
        if not squad_row:
            raise ValueError(MSG.SQUAD_NOT_FOUND)
        if squad_row.get("campus_id") != campus_id:
            raise ValueError(MSG.SQUAD_NOT_FOUND)
        is_member = (squad_row["creator_id"] == user_id) or bool(
            db.table("squad_roster").select("id").eq("squad_id", requested_squad_id).eq("user_id", user_id).eq("is_active", True).execute()
        )
        if not is_member:
            raise ValueError("You are not a member of this squad")
        squad_id = requested_squad_id
        is_squad_order = True
        squad_roster_rows = db.table("squad_roster").select("id,user_id,email").eq("squad_id", squad_id).eq("is_active", True).execute() or []

    if not is_squad_order and config.get("SQUAD_ORDER_ENABLED", True):
        min_items = int(setting_or_config(
            db, "squad_order_min_items", config.get("SQUAD_ORDER_MIN_ITEMS", 3),
            minimum=1, maximum=50,
        ))
        max_items = int(setting_or_config(
            db, "squad_order_max_items", config.get("SQUAD_ORDER_MAX_ITEMS", 20),
            minimum=1, maximum=200,
        ))
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
        raise ValueError(MSG.DELIVERY_TYPE_VALUE_INVALID)

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
                    raise ValueError(MSG.ADDRESS_ACCESS_UNAUTHORIZED)
                if addr.get("latitude") is not None and addr.get("longitude") is not None:
                    delivery_location_lat = float(addr["latitude"])
                    delivery_location_lon = float(addr["longitude"])
                if addr.get("delivery_location_id"):
                    delivery_location_id = addr["delivery_location_id"]
                if addr.get("delivery_type"):
                    delivery_type = addr["delivery_type"]
        except ValueError:
            raise
        except Exception as exc:
            logger.debug("create_order: saved-address lookup failed — using the payload's delivery fields: %s",
                          exc)

    from app.routes.delivery import validate_coordinates, is_within_delivery_area, find_nearest_gate
    if delivery_location_lat is not None or delivery_location_lon is not None:
        delivery_location_lat, delivery_location_lon = validate_coordinates(delivery_location_lat, delivery_location_lon)

    campus_id_for_check = campus_id   # use the order's own already-resolved campus, not g alone —
    # g.campus_id is unset for guests and for background/no-request-context callers
    if delivery_type == "off_campus" and delivery_location_lat is None and delivery_location_lon is None:
        if not delivery_location_id:
            raise ValueError(MSG.DELIVERY_GATE_OR_LOCATION_REQUIRED)
        gate = db.table("gates").select("campus_id").eq("id", delivery_location_id).eq("is_active", "true").single().execute()
        if not gate or (campus_id_for_check and gate.get("campus_id") not in (campus_id_for_check, None)):
            raise ValueError(MSG.DELIVERY_OUTSIDE_AREA)
    elif delivery_type == "off_campus" and delivery_location_lat is not None and delivery_location_lon is not None:
        if not is_within_delivery_area(db, delivery_location_lat, delivery_location_lon, campus_id_for_check):
            raise ValueError(MSG.DELIVERY_OUTSIDE_AREA)
        if not delivery_location_id:
            nearest_gate = find_nearest_gate(db, delivery_location_lat, delivery_location_lon, campus_id_for_check)
            if nearest_gate:
                delivery_location_id = nearest_gate["id"]

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
        except Exception as exc:
            logger.warning("create_order: hostel delivery_fee unreadable — the order charges ₦0 delivery: %s",
                            exc)
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

    # Apply squad delivery-fee discount
    delivery_fee_dec = Decimal(str(delivery_fee))
    if is_squad_order and setting_bool(
        db, "squad_delivery_discount_enabled", config.get("SQUAD_DELIVERY_DISCOUNT_ENABLED", True)
    ):
        pct = Decimal(str(setting_or_config(
            db, "squad_delivery_discount_pct", config.get("SQUAD_DELIVERY_DISCOUNT_PCT", 100),
            minimum=0, maximum=100,
        )))
        squad_delivery_discount_dec = (delivery_fee_dec * pct / Decimal("100.0")).quantize(Decimal("0.01"))
        delivery_fee_dec = max(Decimal("0.0"), delivery_fee_dec - squad_delivery_discount_dec)
        delivery_fee = float(delivery_fee_dec)

    # Apply squad subtotal discount
    subtotal_dec = Decimal(str(subtotal))
    if is_squad_order and setting_bool(
        db, "squad_order_discount_enabled", config.get("SQUAD_ORDER_DISCOUNT_ENABLED", False)
    ):
        pct = Decimal(str(setting_or_config(
            db, "squad_order_discount_pct", config.get("SQUAD_ORDER_DISCOUNT_PCT", 10),
            minimum=0, maximum=100,
        )))
        squad_discount_dec = (subtotal_dec * pct / Decimal("100.0")).quantize(Decimal("0.01"))
        squad_discount = float(squad_discount_dec)

    subtotal_dec = Decimal(str(subtotal))
    promo_discount_dec = Decimal(str(promo_discount))
    squad_discount_dec = Decimal(str(squad_discount))
    order_lock_discount_dec = Decimal(str(order_lock_discount))

    total_dec = subtotal_dec - promo_discount_dec - squad_discount_dec - order_lock_discount_dec + delivery_fee_dec
    total_dec = max(Decimal("0.0"), total_dec.quantize(Decimal("0.01")))
    total = total_amount = float(total_dec)

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

    if user_id is None:
        if payment_method in ("wallet", "split") and wallet_amount_used > 0:
            raise ValueError(MSG.GUEST_NO_WALLET_PAYMENTS)
        if not payload.get("guest_name") or not payload.get("guest_phone") or not payload.get("guest_email"):
            raise ValueError(MSG.GUEST_DETAILS_REQUIRED)

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

    # Pre-calculate hp_preview. The food-earn rate is read live from system_settings (same source
    # hp_service._get_food_earn_rate() uses for the actual payout at delivery, key "hp_per_naira_food",
    # global row) rather than the static config default, so the preview a customer sees at checkout
    # matches what they're actually paid -- the two diverged whenever an admin edited the live rate.
    try:
        # hp_per_naira_food is is_public=false (campus-admin/super_admin only under RLS) -- a plain
        # customer's own client (db, below) can never read it, so this must use the service role,
        # exactly like hp_service._get_food_earn_rate() already does for the payout side.
        _rate_row = get_db().table("system_settings").select("value").eq(
            "key", "hp_per_naira_food").is_("campus_id", "null").single().execute()
        food_earn_rate = float(_rate_row["value"]) if _rate_row and _rate_row.get("value") is not None else current_app.config["HP_PER_NAIRA_FOOD"]
    except Exception:
        food_earn_rate = current_app.config["HP_PER_NAIRA_FOOD"]

    hp_preview_items = []
    hp_preview_base = 0
    for line in order_items:
        if line.get("is_addon") or not line.get("price_snapshot"):
            continue
        base_line = int(
            float(line["price_snapshot"]) * int(line.get("quantity") or 1)
            * food_earn_rate
        )
        multiplier = float(line.get("hp_multiplier_snapshot") or 1.0)
        line_hp = round(base_line * multiplier)
        hp_preview_base += base_line
        hp_preview_items.append({
            "menu_item_id": line.get("menu_item_id"),
            "quantity": int(line.get("quantity") or 1),
            "hp_multiplier": multiplier,
            "base_hp": base_line,
            "hp": line_hp,
        })

    tier_slug = "ember"
    next_order_hp_mult = 1.0
    if user_id:
        try:
            tier_info = hp_service.get_user_tier(user_id)
            tier_slug = (tier_info.get("tier") or {}).get("slug", "ember")
        except Exception as exc:
            logger.warning("create_order: tier lookup failed for %s — the HP preview uses the default tier: %s",
                            user_id, exc)
        try:
            prof = db.table("profiles").select("next_order_hp_multiplier").eq("id", user_id).single().execute()
            next_order_hp_mult = float((prof or {}).get("next_order_hp_multiplier") or 1)
        except Exception as exc:
            logger.warning("create_order: next_order_hp_multiplier unreadable for %s — the bonus may be lost: %s",
                            user_id, exc)

    hp_preview_total = hp_service.calculate_delivery_hp(
        subtotal, tier_slug, order_items, user_id=user_id, campus_id=campus_id
    )
    if next_order_hp_mult > 1:
        # Preview only -- READ next_order_hp_multiplier to show the customer their doubled total, but
        # do NOT reset it here. This used to write next_order_hp_multiplier back to 1 at order-creation
        # time; _handle_delivery_rewards (the actual payout, at delivery) reads the same column and
        # found it already reset, so the "Double HP next order" prize was silently never paid, and a
        # later-cancelled order burned the prize for nothing. The reset now happens exactly once, in
        # _handle_delivery_rewards, at the point the bonus is actually applied.
        hp_preview_total = round(hp_preview_total * next_order_hp_mult)

    hp_preview = {
        "base_hp": hp_preview_base,
        "total_hp": hp_preview_total,
        "next_order_hp_multiplier": next_order_hp_mult,
        "items": hp_preview_items,
    }

    # A reward may ride exactly one order. Check before anything is charged; the
    # authoritative claim happens after the order exists (see below).
    redemption_id = payload.get("redemption_id")
    if redemption_id:
        _assert_redemption_claimable(get_db(), redemption_id, user_id)

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
        "p_hp_redeemed": int(payload.get("hp_redeemed") or 0),
        "p_redemption_id": redemption_id,
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
        "p_squad_id": squad_id,
        "p_squad_discount_amount": squad_discount,
        "p_squad_item_count": squad_item_count,
        "p_notes": payload.get("notes", ""),
        "p_gift_included": False,
        "p_idempotency_key": idempotency_key,
        "p_promo_code_id": promo_code_id,
        "p_items": order_items,
        "p_order_lock_id": order_lock.get("id") if order_lock else None,
        "p_ordering_window_id": ordering_window_id,
        "p_capacity_deferred": bool(payload.get("accept_next_available_date") and is_scheduled),
        "p_originally_requested_date": today_wat().isoformat() if (payload.get("accept_next_available_date") and is_scheduled) else None,
    }

    try:
        result = get_db().rpc("hg_create_order_atomic", rpc_payload)   # service role: anon/authenticated have no grant
    except Exception as exc:
        logger.error("create_order: RPC call failed: %s", exc)
        result = {"error": str(exc)}

    if result is None:
        result = {}

    if result.get("error"):
        raise ValueError(_normalize_rpc_error(result["error"]))

    rpc_total, discount_applied = create_order_apply_rpc_total(result, total)

    order_id = result.get("order_id")

    # ── Free sides: spend the credits and add the ₦0 lines ──────────────────
    # The one place a free-side credit is actually consumed. Runs after the order
    # exists (it needs order_id) and must never fail the order: the customer has
    # paid for the real items, and an unconsumed selection simply stays for the
    # next checkout.
    if order_id and not result.get("idempotent"):
        try:
            _consume_free_sides(get_db(), user_id, campus_id, str(order_id))
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("create_order: free-side consumption failed for order %s: %s",
                           order_id, exc)

    # ── Reward redemption: attach it to this order exactly once ─────────────
    # The authoritative claim happens inside hg_create_order_atomic, so this call
    # is a safety net: it returns claimed=true with already_attached=true when the
    # order already carries the reward — that is success. Only a genuine refusal
    # (the reward was spent elsewhere in the meantime) is logged, because by then
    # the customer has already received the discount on this order.
    claim = None
    if order_id and redemption_id and not result.get("idempotent"):
        try:
            claim = _claim_reward_redemption(get_db(), redemption_id, user_id, str(order_id)) or {}
            attached = bool(claim.get("claimed")) or bool(claim.get("already_attached"))
            if not attached:
                logger.error("create_order: reward redemption %s could not be attached to order %s "
                             "(%s) — the reward may have been used twice", redemption_id, order_id,
                             claim.get("reason"))
        except Exception as exc:                                    # noqa: BLE001
            logger.error("create_order: reward claim call failed for redemption %s / order %s: %s",
                         redemption_id, order_id, exc)

    if squad_id and order_id and not result.get("idempotent"):
        excluded_ids = set(payload.get("excluded_member_ids") or [])
        extra_members = [e.strip().lower() for e in (payload.get("extra_members") or []) if e and e.strip()]
        campus_id_for_squad = campus_id
        snapshot = []
        for r in squad_roster_rows:
            if r["id"] in excluded_ids:
                continue
            try:
                db.table("squad_members").insert({
                    "order_id": order_id, "email": r["email"], "user_id": r.get("user_id"),
                    "is_registered": bool(r.get("user_id")), "campus_id": campus_id_for_squad,
                })
            except Exception as exc:
                logger.warning("create_order: squad member row not written for %s on order %s: %s",
                                r.get("email"), order_id, exc)
            snapshot.append({"email": r["email"], "user_id": r.get("user_id")})
        for email in extra_members:
            prof = db.table("profiles").select("id").eq("email", email).single().execute()
            try:
                db.table("squad_members").insert({
                    "order_id": order_id, "email": email,
                    "user_id": prof["id"] if prof else None,
                    "is_registered": bool(prof), "campus_id": campus_id_for_squad,
                })
            except Exception as exc:
                logger.warning("create_order: squad member row not written for %s on order %s: %s",
                                email, order_id, exc)
            snapshot.append({"email": email, "user_id": prof["id"] if prof else None})
        if snapshot:
            get_db().table("orders").eq("id", order_id).update({"squad_member_snapshot": snapshot}).execute()

    order = db.table("orders").select("*").eq("id", result["order_id"]).single().execute()
    order_source = payload.get("order_source") or payload.get("source") or "website"
    if order_source not in ("website", "whatsapp", "instagram", "referral", "sms", "other"):
        order_source = "other"          # the orders.order_source CHECK only allows these six values
    if order_source and result.get("order_id"):
        try:
            get_db().table("orders").eq("id", result["order_id"]).update({"order_source": order_source}).execute()
        except Exception as _ose:
            logger.warning("create_order: failed to set order_source: %s", _ose)

    # The customer came back and ordered: close their open abandoned-cart rows so recovery stats are
    # real and the recovery cron stops nudging them. Service role (RLS); never blocks the order.
    if user_id and result.get("order_id"):
        try:
            get_db().table("abandoned_carts").eq("user_id", user_id).eq("is_recovered", False).update({
                "is_recovered": True,
                "recovered_order_id": result["order_id"],
            }).execute()
        except Exception as _rce:
            logger.warning("create_order: failed to mark abandoned cart recovered: %s", _rce)

    if order and isinstance(order, dict):
        order["total_amount"] = rpc_total
        order["order_lock_discount_applied"] = discount_applied
        if order_source:
            order["order_source"] = order_source

        delivery_start = delivery_end = None
        if linked_delivery_window_id:
            try:
                dw = db.table("delivery_windows").select("opens_at,closes_at").eq("id", linked_delivery_window_id).single().execute()
                if dw:
                    delivery_start = dw.get("opens_at")
                    delivery_end = dw.get("closes_at")
            except Exception as exc:
                logger.warning("create_order: delivery window %s unreadable — the customer sees the 18:00-19:00 default: %s",
                                linked_delivery_window_id, exc)
        order["delivery_window_start"] = delivery_start or "18:00"
        order["delivery_window_end"] = delivery_end or "19:00"

        if user_id and not is_squad_order:
            try:
                from app.services.tier_service import try_claim_monthly_free_delivery
                if try_claim_monthly_free_delivery(user_id, order_id=result["order_id"]):
                    get_db().table("orders").eq("id", result["order_id"]).update({"delivery_fee": 0.0}).execute()
                    order["delivery_fee"] = 0.0
            except Exception as _fe:
                logger.warning("create_order: monthly free delivery perk claim failed: %s", _fe)

        if is_scheduled and payload.get("accept_next_available_date") and user_id:
            try:
                scheduled_date_display = (scheduled_for or "")[:10]
                send_notification(
                    user_id=user_id,
                    notif_type="order_scheduled_deferred",
                    template_data={
                        "scheduled_date": scheduled_date_display,
                        "delivery_window_start": delivery_start or "18:00",
                        "delivery_window_end": delivery_end or "19:00",
                    },
                    reference_id=result["order_id"],
                    reference_type="order",
                )
            except Exception as _dn:
                logger.warning("create_order: order_scheduled_deferred notify failed: %s", _dn)

        if user_id is None and payload.get("guest_email"):
            try:
                from app.utils.email import send_email
                send_email(
                    to_email=payload["guest_email"],
                    to_name=payload.get("guest_name", ""),
                    template_key="guest_order_confirmed",
                    data={"order_id": result["order_id"][:8].upper(), "claim_token": claim_token},
                )
            except Exception as _ge:
                logger.warning("create_order: guest email failed: %s", _ge)

    if not result.get("idempotent") and isinstance(order, dict):
        order["hp_preview"] = hp_preview

    if user_id and not is_scheduled and not result.get("idempotent") and result.get("order_id"):
        try:
            send_notification(
                user_id=user_id,
                notif_type="order_placed",
                template_data={"order_id": result["order_id"][:8].upper(), "total_amount": total_amount},
            )
        except Exception as _pe:
            logger.warning("create_order: order_placed notify failed: %s", _pe)

    if isinstance(order, dict) and order.get("payment_status") == "paid":
        try:
            _on_order_paid(order)
        except Exception as _pe:
            logger.warning("create_order: _on_order_paid failed for order %s: %s", order.get("id"), _pe)

    # Clear the cart now that the order has been placed successfully.
    # Guests (user_id is None) don't have a server-side cart to clear.
    # Skip on an idempotent replay (same idempotency_key called twice) — the
    # cart was already cleared the first time this order was actually created.
    if user_id and not result.get("idempotent"):
        try:
            db.table("cart_items").eq("user_id", user_id).delete()
        except Exception as cart_exc:
            # NOTE: do not shadow the module-level `current_app` import with a local one here — Python
            # would then treat current_app as local for the whole function, and `config = current_app.config`
            # near the top would raise UnboundLocalError on every single call. (This was a live bug: the
            # combined file already imports current_app at module scope; this local import must not be re-added.)
            current_app.logger.error(
                "create_order: order %s succeeded but cart clear failed for user %s: %s",
                result.get("order_id"), user_id, cart_exc,
            )

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
    db = get_user_client()
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
            except Exception as exc:
                logger.error("walk_order_to_status: could not resolve the role of %s — the rider/kitchen/admin checks are SKIPPED for this call: %s",
                              changed_by, exc)

        if caller_role == "rider":
            effective_rider = db.rpc("hg_effective_rider", {"p_order_id": order_id}).execute()
            if not effective_rider or str(effective_rider) != str(changed_by):
                raise ValueError("Unauthorized: Rider is not assigned to this order")

        elif caller_role == "kitchen":
            if order.get("campus_id") != caller_campus:
                raise ValueError("Unauthorized: Kitchen staff is scoped to a different campus")
        elif caller_role == "admin":
            if order.get("campus_id") != caller_campus:
                raise ValueError("Unauthorized: Admin is scoped to a different campus")

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


def _on_order_paid(order: dict):
    """Run once, the moment an order's payment_status first becomes 'paid' — whether via card webhook
    (confirm_order_payment) or instant wallet payment (create_order). Completes a pending referral and
    sends the order_confirmed notification. order_placed (immediate, at creation) is a separate message."""
    if not order.get("user_id"):
        return
    db = get_db()
    try:
        paid_orders = db.table("orders").select("id").eq("user_id", order["user_id"]).eq("payment_status", "paid").execute() or []
        if len(paid_orders) == 1:
            from app.routes.referrals import _complete_referral_award
            referral = db.table("referrals").select("*").eq("referred_user_id", order["user_id"]).single().execute()
            if referral and not referral.get("hp_awarded", 0):
                _complete_referral_award(referral, order["id"])
    except Exception as exc:
        logger.error("Referral completion failed for order %s: %s", order["id"], exc)

    send_notification(
        user_id=order["user_id"], notif_type="order_confirmed",
        template_data={"order_id": order["id"][:8].upper()},
        reference_id=order["id"], reference_type="order",
    )


def confirm_order_payment(order_id: str, payment_reference: str, provider_response: dict = None) -> dict:
    """
    Called after card payment confirmed (webhook).
    Updates payment_status to paid. Order is already in 'received' state.
    Runs as the service role: anon/authenticated have no grant on hg_mark_order_paid, and a real,
    already-paid order was invisible to an anon-role query in this project — every card/bank-transfer
    payment was failing confirmation permanently.
    """
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).single().execute()
    if not order:
        raise ValueError(MSG.RIDER_ORDER_NOT_FOUND)

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
        logger.error("confirm_order_payment: RPC call failed for order %s: %s", order_id, exc)
        payment_result = {"error": str(exc)}

    if not payment_result:
        raise ValueError("Failed to mark order as paid")

    if isinstance(payment_result, dict) and payment_result.get("error"):
        raise ValueError(payment_result["error"])

    updated_order = (
        db.table("orders")
        .select("*")
        .eq("id", order_id)
        .single()
        .execute()
    )

    if isinstance(updated_order, dict):
        _on_order_paid(updated_order)

    return updated_order


def _restore_order_consumables(order: dict) -> None:
    """Give back what an order cancelled before preparation took from the customer.

    Cancelling from 'received' means the kitchen never started, so the HP the order
    redeemed and any reward it had claimed both go back:

    * HP returns at the exact amount redeemed, with no multiplier — it is the return of
      something spent, not a fresh earn (the same call the scheduled-cancel path used).
    * The reward claim is released, which is what makes the reward claimable again. The
      update is pinned to this order, so a retry or a race cannot free a reward that
      belongs to another order.

    Both are best-effort: the cancellation has already been committed and the customer
    has been told, so a failure here is logged rather than allowed to undo the cancel.
    """
    order_id = order.get("id")
    user_id = order.get("user_id")
    if not order_id or not user_id:
        return

    hp_redeemed = int(order.get("hp_redeemed") or 0)
    if hp_redeemed > 0:
        try:
            from app.services import hp_service
            hp_service.award_active_hp(
                user_id, hp_redeemed,
                txn_type="refund", reference_id=order_id, reference_type="order",
                apply_multiplier=False,  # returning HP that was spent, not a fresh earn
            )
        except Exception as exc:
            logger.error("cancel: HP restore failed for order %s (%s HP, user %s): %s",
                         order_id, hp_redeemed, user_id, exc)

    # reward_redemptions has no UPDATE policy for the owner (only admins) — see the same
    # note in routes/rewards.py — so this write has to go through the service role, pinned
    # to the order that actually holds the claim. Both the claim link and its timestamp go
    # back to empty: the database only ever sets them (hg_create_order_atomic claims the
    # reward; nothing reverses it), so clearing them here is what makes the reward
    # claimable again. Re-running is a no-op — the row no longer matches the filter.
    try:
        released = (
            get_db().table("reward_redemptions")
            .eq("attached_order_id", order_id)
            .update({"attached_order_id": None, "used_at": None})
        )
        count = len(released) if isinstance(released, list) else (1 if released else 0)
        if count:
            logger.info("cancel: released %s reward claim(s) for order %s", count, order_id)
    except Exception as exc:
        logger.error("cancel: reward release failed for order %s — the reward stays used: %s",
                     order_id, exc)


def update_order_status(order_id: str, new_status: str, changed_by: str = None, notes: str = "") -> dict:
    """
    Transition order status. Validates the state machine. Awards HP on delivery.
    Notifications and delivery rewards run in a daemon thread so the response
    is not held up by sequential Supabase notification inserts.
    Fixes: rider authorisation follows the database rule (explicit assignment, else batch rider); the
    update is a compare-and-set on the current status (no lost updates / double rewards); repeating the
    same status is a no-op; a rewards failure no longer turns an already-committed delivery into a 500;
    'refunded' can only be reached through the dedicated refund action, never a plain status change.
    """
    import threading as _threading
    from flask import current_app as _app, has_app_context, g
    if new_status == "refunded":
        raise OrderStatusError(MSG.REFUND_USE_DEDICATED_ENDPOINT)
    db = get_user_client()
    order = db.table("orders").select("*").eq("id", order_id).single().execute()
    if not order:
        raise OrderNotFoundError(MSG.RIDER_ORDER_NOT_FOUND)

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
            except Exception as exc:
                logger.error("update_order_status: could not resolve the role of %s — the rider/kitchen/admin checks are SKIPPED for this call: %s",
                              changed_by, exc)

        if caller_role == "rider":
            if _effective_rider_id(order) != changed_by:
                raise OrderForbiddenError(MSG.RIDER_NOT_ASSIGNED_TO_ORDER)
        elif caller_role == "kitchen":
            if order.get("campus_id") != caller_campus:
                raise OrderForbiddenError(MSG.ORDER_KITCHEN_CAMPUS_MISMATCH)
        elif caller_role == "admin":
            if order.get("campus_id") != caller_campus:
                raise OrderForbiddenError(MSG.ORDER_ADMIN_CAMPUS_MISMATCH)

    current_status = order["status"]
    if new_status == current_status:
        return {**order, "unchanged": True}                       # repeat of the same action (double tap / retry): nothing to do
    allowed = VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise OrderConflictError(MSG.ORDER_INVALID_TRANSITION.format(current=current_status, new=new_status))

    now = datetime.now(timezone.utc).isoformat()
    update_data = {"status": new_status}
    ts_field = STATUS_TIMESTAMPS.get(new_status)
    if ts_field:
        update_data[ts_field] = now
    if new_status in ("cancelled", "refunded") and order.get("batch_id"):
        update_data["batch_id"] = None

    try:
        updated = db.table("orders").eq("id", order_id).eq("status", current_status).update(update_data).execute()
    except SupabaseError as exc:
        mapped = _map_db_error(exc)
        if mapped:
            raise mapped from exc
        raise
    if not updated:
        latest = db.table("orders").select("status").eq("id", order_id).limit(1).execute() or []
        if latest and latest[0].get("status") != current_status:
            raise OrderConflictError(MSG.ORDER_STATUS_CONFLICT)   # somebody else moved the order first
        raise OrderForbiddenError(MSG.ORDER_UPDATE_FAILED)
    _log_status_change(order_id, current_status, new_status, changed_by, notes, order.get("campus_id"))

    # Cancelled before preparation: the customer gets back the HP and the reward this
    # order consumed. Placed on the one compare-and-set transition every cancel path
    # goes through (customer, admin, kitchen), so it fires exactly once — a retry hits
    # the `new_status == current_status` no-op above and cannot credit twice. Cancels
    # from later states keep their HP/reward: the kitchen has already spent real money.
    if new_status == "cancelled" and current_status == "received":
        _restore_order_consumables(order)

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
    rewards_pending = False
    if new_status == "delivered" and order.get("user_id"):
        try:
            _handle_delivery_rewards(order)
        except Exception:
            rewards_pending = True
            logger.exception("update_order_status: delivery rewards failed for order %s (status is already 'delivered')", order_id)

    # Status notifications are fire-and-forget; run in a thread so the
    # response is not held up by sequential Supabase notification inserts.
    app_ctx = _app._get_current_object()

    def _notify():
        with app_ctx.app_context():
            _send_status_notification(order, new_status)
            if new_status == "ready":
                _notify_rider_order_ready(order)

    _threading.Thread(target=_notify, daemon=True).start()

    row = updated[0] if isinstance(updated, list) else updated
    return {**row, "rewards_pending": True} if rewards_pending else row


def _notify_rider_order_ready(order: dict):
    """Tell the rider whose batch holds this order that it can be collected (template rider_order_ready)."""
    try:
        rider_id = _effective_rider_id(order)
        if rider_id:
            send_notification(
                user_id=rider_id,
                notif_type="rider_order_ready",
                template_data={"order_id": order.get("order_number") or str(order["id"])[:8]},
                reference_id=order["id"],
                reference_type="order",
            )
    except Exception:
        logger.warning("_notify_rider_order_ready failed for order %s", order.get("id"), exc_info=True)


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
        user_id=user_id,
        campus_id=order.get("campus_id"),
    )

    # Apply next_order_hp_multiplier bonus if present, then reset to 1
    try:
        prof = db.table("profiles").select("next_order_hp_multiplier").eq("id", user_id).single().execute()
        mult = float((prof or {}).get("next_order_hp_multiplier") or 1)
        if mult > 1:
            hp_amount = round(hp_amount * mult)
            db.table("profiles").eq("id", user_id).update({"next_order_hp_multiplier": 1}).execute()
    except Exception as me:
        logger.warning("_handle_delivery_rewards: next_order_hp_multiplier check failed: %s", me)

    # B-8: Compute squad share plan BEFORE credit — true split
    # If squad members exist, owner gets only owner_share, not full hp_amount
    has_squad_members = False
    owner_share_for_credit = hp_amount
    squad_plan = None
    try:
        # Quick check if squad members exist
        sm_check = db.table("squad_members").select("id").eq("order_id", order_id).limit(1).execute()
        has_squad_members = bool(sm_check)
        if has_squad_members and hp_amount > 0:
            from app.services.squad_service import squad_share_plan
            squad_plan = squad_share_plan(order_id, hp_amount, user_id, campus_id=order.get("campus_id"))
            owner_share_for_credit = squad_plan.get("owner_share", hp_amount)
    except Exception as e:
        logger.warning("_handle_delivery_rewards: squad_share_plan failed for order %s, falling back to full HP: %s", order_id, e)
        owner_share_for_credit = hp_amount

    # Step 2: Atomically credit via Supabase RPC — call for EVERY eligible
    # delivery, zero-HP included, so the idempotency marker always gets set
    # B-8: use owner_share when squad exists, but hp_earned column stays full amount
    try:
        result = db.rpc("hg_credit_delivery_hp_atomic", {
            "p_order_id": order_id,
            "p_user_id": user_id,
            "p_hp_amount": owner_share_for_credit,
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

    try:
        hp_service.unlock_pending_hp(user_id=user_id, order_id=order_id, food_spend=subtotal)
    except Exception as e:
        logger.warning("_handle_delivery_rewards: unlock_pending_hp failed for order %s: %s", order_id, e)

    welcome_result = hp_service.award_welcome_bonus(user_id, order_id)

    tier_change = hp_service.recalculate_tier(user_id)

    order_updates = {
        "hp_earned": hp_amount,
        "hp_credited_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        db.table("orders").eq("id", order_id).update(order_updates).execute()
    except Exception as e:
        logger.warning("_handle_delivery_rewards: order hp_earned update failed for %s: %s", order_id, e)

    # All HP/tier/referral logic above is synchronous so callers see updated
    # balances immediately. Notifications are fire-and-forget — queue them as
    # daemon threads so they don't add latency to the status-update response.
    import threading as _t

    # B-8: owner notification uses owner_share when squad exists, but hp_earned stays total
    notify_hp = owner_share_for_credit if has_squad_members else hp_amount
    total_hp_awarded = notify_hp + welcome_result.get("awarded", 0)

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

    # has_squad_members already computed above
    if has_squad_members and not order.get("squad_hp_distributed"):
        try:
            from app.services.squad_service import distribute_squad_hp
            distribute_squad_hp(order_id, hp_amount, user_id, campus_id=order.get("campus_id"))
            db.table("orders").eq("id", order_id).update({
                "squad_hp_distributed": True,
                "squad_hp_distributed_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.warning("_handle_delivery_rewards: squad HP distribution failed for order %s: %s", order_id, e)

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
            get_user_client().table("orders")
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
    except Exception as e:
        logger.warning("_handle_delivery_rewards: last_activity_at update failed for %s: %s", user_id, e)


def _apply_promo(user_id: str, code: str, order_subtotal: float) -> dict:
    db = get_user_client()
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

    from flask import has_request_context, g
    if has_request_context():
        campus_id = getattr(g, 'campus_id', None)
        if campus_id and promo.get("campus_id") and promo["campus_id"] != campus_id:
            raise ValueError(MSG.ORDER_PROMO_INVALID.format(code=code))

    now = datetime.now(timezone.utc).isoformat()
    if promo.get("ends_at") and promo["ends_at"] < now:
        raise ValueError(MSG.STOREFRONT_PROMO_EXPIRED)
    if promo.get("starts_at") and promo["starts_at"] > now:
        raise ValueError(MSG.STOREFRONT_PROMO_NOT_ACTIVE)
    if promo.get("max_uses"):
        total_uses = (
            db.table("orders")
            .select("id")
            .eq("promo_code_id", promo["id"])
            .neq("status", "cancelled")
            .execute()
        ) or []
        if len(total_uses) >= promo["max_uses"]:
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
            raise ValueError(MSG.PROMO_CODE_MAX_USES)

    if promo["discount_type"] == "percentage":
        discount = order_subtotal * float(promo["discount_value"]) / 100
    else:
        discount = float(promo["discount_value"])

    return {"discount": round(discount, 2), "promo_code_id": promo["id"]}


def _log_status_change(order_id: str, from_status: str, to_status: str, changed_by: str = None, notes: str = "", campus_id: str = None):
    """The database trigger already writes one log row per status change; enrich that row (who / why /
    campus) instead of adding a duplicate, and insert one only if the trigger row is missing."""
    db = get_db()
    note = notes or f"{from_status} → {to_status}"
    meta = {"from_status": from_status}
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        rows = (db.table("order_status_logs").eq("order_id", order_id).eq("status", to_status).gte("created_at", cutoff)
                .update({"changed_by": changed_by, "note": note, "metadata": meta, "campus_id": campus_id}))
        if not rows:
            db.table("order_status_logs").insert({"order_id": order_id, "status": to_status, "changed_by": changed_by,
                                                  "note": note, "metadata": meta, "campus_id": campus_id})
    except Exception:
        logger.warning("_log_status_change failed for order %s", order_id, exc_info=True)


_GUEST_STATUS_EMAILS = {
    "out_for_delivery": (MSG.GUEST_ORDER_OUT_SUBJECT, MSG.GUEST_ORDER_OUT_BODY),
    "delivered": (MSG.GUEST_ORDER_DELIVERED_SUBJECT, MSG.GUEST_ORDER_DELIVERED_BODY),
    "delivery_attempted": (MSG.GUEST_ORDER_ATTEMPTED_SUBJECT, MSG.GUEST_ORDER_ATTEMPTED_BODY),
}


def _send_guest_status_email(order: dict, new_status: str):
    """Guest orders have no app account, so no push/in-app: email them the three delivery milestones."""
    template = _GUEST_STATUS_EMAILS.get(new_status)
    email = order.get("guest_email")
    if not template or not email:
        return
    try:
        import html as _html
        from app.utils.email import send_email_raw
        number = order.get("order_number") or str(order["id"])[:8]
        subject, body = template
        text = _html.escape(body.format(order_number=number))
        html_body = f"<html><body style='font-family:sans-serif;max-width:600px;margin:auto;padding:20px'><p>Hi {_html.escape(order.get('guest_name') or 'there')},</p><p>{text}</p></body></html>"
        send_email_raw(email, order.get("guest_name") or "", subject.format(order_number=number), html_body)
    except Exception:
        logger.warning("_send_guest_status_email failed for order %s", order.get("id"), exc_info=True)


def _send_status_notification(order: dict, new_status: str):
    user_id = order.get("user_id")
    if not user_id:
        _send_guest_status_email(order, new_status)
        return
    _STATUS_NOTIF_TYPES = {
        "preparing", "ready", "assigned", "out_for_delivery",
        "delivered", "delivery_attempted", "unclaimed", "cancelled", "refunded",
    }
    if new_status in _STATUS_NOTIF_TYPES:
        send_notification(
            user_id=user_id,
            notif_type=f"order_{new_status}",
            template_data={},  # all order status bodies have no dynamic placeholders
            reference_id=order["id"],
            reference_type="order",
            urgency="high" if new_status == "delivery_attempted" else None,
        )
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


def _order_capacity_weight(order_row: dict) -> int:
    """Needs 'is_squad_order','squad_item_count' selected."""
    if order_row.get("is_squad_order"):
        return max(int(order_row.get("squad_item_count") or 1), 1)
    return 1


def resolve_ordering_window(db, campus_id):
    """
    Raises ValueError(MSG.ORDER_OUTSIDE_ORDERING_HOURS) or
    ValueError(MSG.ORDERING_WINDOW_AT_CAPACITY). Returns
    {'id':..., 'capacity':..., 'linked_delivery_window_id':...} on success.
    """
    from datetime import time as _time, timedelta as _td, timezone as _tz

    def _parse_hm(s, default_h=8, default_m=0):
        try:
            parts = str(s).split(":")
            return _time(int(parts[0]), int(parts[1]))
        except Exception:
            return _time(default_h, default_m)

    _now_utc = datetime.now(_tz.utc)
    _now_wat_dt = _now_utc + _td(hours=1)
    _now_wat = _now_wat_dt.time()
    _today_iso = _now_wat_dt.date().isoformat()
    _weekday = _now_wat_dt.weekday()

    # Precedence lives in app/utils/schedule.py: a dated ordering_windows row, then
    # a per-date operating_hours override (closed, or one window at its times), then
    # the recurring weekday rows, then the config fallback. An override applies to
    # its own date only — the next day is back on the recurring schedule.
    candidates, _source = effective_ordering_windows(db, campus_id, _today_iso, _weekday)

    if not candidates:
        from flask import current_app
        _open_str = current_app.config.get("ORDERING_WINDOW_OPEN_TIME", "08:00")
        _close_str = current_app.config.get("ORDERING_WINDOW_CLOSE_TIME", "16:00")
        if _parse_hm(_open_str, 8, 0) <= _now_wat <= _parse_hm(_close_str, 16, 0):
            return {"id": None, "capacity": None, "linked_delivery_window_id": None}
        raise OrderingWindowUnavailable(MSG.ORDER_OUTSIDE_ORDERING_HOURS)

    open_rows = [r for r in candidates if not r.get("is_closed") and r.get("opens_at") and r.get("closes_at")]
    if not open_rows:
        raise OrderingWindowUnavailable(MSG.ORDER_OUTSIDE_ORDERING_HOURS)

    open_rows.sort(key=lambda r: _parse_hm(r["opens_at"], 0, 0))
    earliest_open = _parse_hm(open_rows[0]["opens_at"], 0, 0)
    latest_close = max(_parse_hm(r["closes_at"], 23, 59) for r in open_rows)
    if _now_wat < earliest_open or _now_wat > latest_close:
        raise OrderingWindowUnavailable(MSG.ORDER_OUTSIDE_ORDERING_HOURS)

    any_time_eligible = False
    for row in open_rows:
        if _now_wat > _parse_hm(row["closes_at"], 23, 59):
            continue
        any_time_eligible = True
        if row.get("capacity") is not None:
            _rows = (
                db.table("orders")
                .select("id,is_squad_order,squad_item_count")
                .eq("ordering_window_id", row["id"])
                .gte("created_at", _today_start_iso())
                .not_.in_("status", ["cancelled", "refunded"])
                .limit(1000)
                .execute()
            ) or []
            if sum(_order_capacity_weight(o) for o in _rows) >= int(row["capacity"]):
                continue
        return row

    if any_time_eligible:
        next_slot = None
        try:
            tomorrow = (_now_wat_dt + _td(days=1)).date()
            next_slot = find_next_available_ordering_slot(db, campus_id, start_date=tomorrow)
        except Exception as _nse:
            logger.warning("resolve_ordering_window: next-slot lookup failed: %s", _nse)
        next_date = (next_slot or {}).get("date")
        raise OrderingWindowUnavailable(MSG.ORDERING_WINDOW_AT_CAPACITY, next_available_date=next_date)

    raise OrderingWindowUnavailable(MSG.ORDER_OUTSIDE_ORDERING_HOURS)


def get_ordering_window_status(db, campus_id, for_date=None):
    from datetime import timedelta as _td, timezone as _tz
    _now_utc = datetime.now(_tz.utc)
    _now_wat_dt = _now_utc + _td(hours=1)
    target_dt = for_date if for_date else _now_wat_dt.date()
    _today_iso = target_dt.isoformat() if hasattr(target_dt, "isoformat") else str(target_dt)

    try:
        dt_obj = datetime.fromisoformat(_today_iso) if isinstance(_today_iso, str) else target_dt
        _weekday = dt_obj.weekday()
    except Exception:
        _weekday = _now_wat_dt.weekday()

    # Same precedence as resolve_ordering_window, through the same helper — this is
    # what makes find_next_available_ordering_slot and the 7-day calendar
    # override-aware without their own copy of the rules.
    candidates, _source = effective_ordering_windows(db, campus_id, _today_iso, _weekday)

    windows_out = []
    any_capacity = False
    for row in candidates:
        deliv = None
        if row.get("linked_delivery_window_id"):
            try:
                deliv = db.table("delivery_windows").select("opens_at,closes_at").eq("id", row["linked_delivery_window_id"]).single().execute()
            except Exception:
                deliv = None

        is_full = False
        remaining = None
        if row.get("capacity") is not None:
            _rows = (
                db.table("orders")
                .select("id,is_squad_order,squad_item_count")
                .eq("ordering_window_id", row["id"])
                .gte("created_at", f"{_today_iso}T00:00:00")
                .not_.in_("status", ["cancelled", "refunded"])
                .limit(1000)
                .execute()
            ) or []
            used = sum(_order_capacity_weight(o) for o in _rows)
            remaining = max(0, int(row["capacity"]) - used)
            is_full = used >= int(row["capacity"])

        if not row.get("is_closed") and not is_full:
            any_capacity = True

        windows_out.append({
            "id": row["id"],
            "is_closed": bool(row.get("is_closed")),
            "is_full": is_full,
            "remaining": remaining,
            "opens_at": row.get("opens_at"),
            "closes_at": row.get("closes_at"),
            "delivery_starts_at": (deliv or {}).get("opens_at"),
            "delivery_ends_at": (deliv or {}).get("closes_at"),
        })

    return {
        "date": _today_iso,
        "is_open": any_capacity,
        "windows": windows_out,
        "any_capacity_remaining": any_capacity,
    }


def find_next_available_ordering_slot(db, campus_id, start_date, max_days_ahead=14):
    from datetime import timedelta as _td
    curr = start_date
    for _ in range(max_days_ahead):
        status = get_ordering_window_status(db, campus_id, for_date=curr)
        if status.get("any_capacity_remaining"):
            open_wins = [w for w in status.get("windows", []) if not w["is_closed"] and not w["is_full"]]
            return {
                "date": status["date"],
                "window_id": open_wins[0]["id"] if open_wins else None,
                "opens_at": open_wins[0].get("delivery_starts_at") if open_wins else None,
            }
        curr = curr + _td(days=1)
    return None
