"""
app/routes/riders.py — Rider dashboard routes (D08). FULL REPLACEMENT of the audited file.
Earnings and stats now come from the database functions hg_rider_earnings / hg_rider_batch_pay / hg_rider_stats.
Every change is tagged with its fix id (D08-Bxx) as listed in D08_fixes.md. Needs the order_service patch (OrderStatusError) deployed with it.

Roles: rider, admin, super_admin (as before). New: GET /roster and the /admin/... batch-pay routes (admin only).

Merged version: the D08 rewrite above is the base; additions from the earlier D08 audit log (RB-*) are tagged RB-n.
Not carried over from that log: a Python `_sync_batch_status` (the database trigger trg_orders_progress_batch already
moves batches to in_progress / completed, so doing it here too would race with it) and its /admin/board (the /roster
below covers the same ground).
"""
import math
import re
from datetime import datetime, time as dtime, timedelta, timezone
from decimal import Decimal

from flask import Blueprint, request, jsonify, g

from app.middleware.auth import require_role, resolve_scoped_campus_id
from app.middleware.rate_limit import rate_limit
from app.services.order_service import update_order_status, OrderStatusError
from app.db import get_db, get_user_client, SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger
from app.utils.tz import today_wat
from app.utils.validators import validate_uuid

logger = get_logger(__name__)

riders_bp = Blueprint("riders", __name__)

_ACTIVE_BATCH_STATUSES = ("assigned", "in_progress")
_LIVE_ORDER_STATUSES = ("ready", "assigned", "out_for_delivery", "delivery_attempted")      # a rider may still work / call these
_PENDING_ORDER_STATUSES = ("received", "paid", "preparing", "ready", "assigned", "out_for_delivery", "delivery_attempted")
_CHUNK = 100                                                                                # ids per `in.(...)` filter (URL length)
_WAT = timezone(timedelta(hours=1))

# D08-B01: these four names were used by my_batch but defined nowhere -> NameError as soon as a rider had a batch
DEFAULT_SEQUENCING_MODE = "distance_from_gate"
VALID_SEQUENCING_MODES = ("distance_from_gate", "nearest_neighbour")


# ───────────────────────────── helpers ─────────────────────────────
def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Return great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlam = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _chunks(values, size=_CHUNK):
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _select_in(db, table, select, column, values, apply=None):
    """Rows where `column` is in `values`, fetched in chunks (a long in.(...) list breaks the URL)."""
    rows = []
    for chunk in _chunks(dict.fromkeys(v for v in values if v)):
        q = db.table(table).select(select).in_(column, chunk)
        if apply:
            q = apply(q)
        rows.extend(q.execute() or [])
    return rows


def _fetch_all(build, page=1000):
    """Page through a query (PostgREST caps a response at 1000 rows). `build()` returns a fresh query."""
    rows, offset = [], 0
    while True:
        chunk = build().order("id").limit(page).offset(offset).execute() or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        offset += page


def _json_object():
    data = request.get_json(force=True, silent=True)
    return data if isinstance(data, dict) else None


def _coord(value, low, high):
    """float within [low, high] from a number / numeric string, else None (bool, NaN, inf, out of range -> None)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(str(value).strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not (low <= number <= high):
        return None
    return number


def _bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0", "no"):
        return False
    return None


def _page_args(default_limit=20, max_limit=100):
    """(limit, offset) or None when they are not whole numbers in range."""
    try:
        limit = int(request.args.get("limit", default_limit))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return None
    if limit < 1 or limit > max_limit or offset < 0:
        return None
    return limit, offset


def _rider_order_view(order):
    """
    RB-2: what a rider gets back after a status action. update_order_status returns the whole order row
    (customer id, guest phone, totals, payment and claim fields); a rider only needs the status fields.
    """
    order = order or {}
    view = {k: order.get(k) for k in ("id", "status", "out_for_delivery_at", "delivered_at", "delivery_attempted_at")}
    if order.get("unchanged"):
        view["unchanged"] = True          # a repeated tap: nothing was done twice
    return view


def _order_error(exc: OrderStatusError):                                                     # D08-B09: 403 / 404 / 409 instead of a blanket 400
    return jsonify({"error": str(exc)}), getattr(exc, "http_status", 400)


def _upsert_rider_profile(payload):
    """One atomic write: creates the row on the first ping/toggle, updates it afterwards (user_id is unique)."""
    row = {"user_id": g.user_id, **payload}
    campus_id = getattr(g, "campus_id", None)
    if campus_id:
        row["campus_id"] = campus_id
    return get_user_client().table("rider_profiles").upsert(row, on_conflict="user_id")


# ───────────────────────────── sequencing (D08-B01) ─────────────────────────────
def _coords(order):
    lat, lon = order.get("delivery_location_lat"), order.get("delivery_location_lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _sequence_distance_from_gate(orders, gate_lat, gate_lon):
    """Nearest to the gate first; orders without coordinates go last (stable)."""
    def key(o):
        c = _coords(o)
        return (0, _haversine_km(gate_lat, gate_lon, c[0], c[1])) if c else (1, 0.0)
    return sorted(orders, key=key)


def _sequence_nearest_neighbour(orders, gate_lat, gate_lon):
    """Greedy route: start at the gate, always go to the closest remaining drop; orders without coordinates go last."""
    remaining = [o for o in orders if _coords(o)]
    unknown = [o for o in orders if not _coords(o)]
    route, here = [], (float(gate_lat), float(gate_lon))
    while remaining:
        nxt = min(remaining, key=lambda o: _haversine_km(here[0], here[1], *_coords(o)))
        remaining.remove(nxt)
        route.append(nxt)
        here = _coords(nxt)
    return route + unknown


# ───────────────────────────── RID-01 ─────────────────────────────
@riders_bp.route("/my-batch", methods=["GET"])
@require_role("rider", "admin")
def my_batch():
    """
    Get the current delivery batch assigned to this rider.
    Shows customer name, address, items, order number. Phone never exposed in payload.
    The batch in progress comes first, otherwise the oldest assigned batch; `other_batches` counts the rest.
    ---
    tags: [Riders]
    parameters:
      - in: query
        name: sequencing
        type: string
        enum: [distance_from_gate, nearest_neighbour]
    responses:
      200:
        description: Rider's assigned batch
    """
    db = get_user_client()
    q = (db.table("delivery_batches")
         .select("id,window_id,delivery_window_id,zone,gate_id,status,created_at,campus_id,rider_pay_total,rider_paid_at")
         .eq("rider_id", g.user_id).in_("status", list(_ACTIVE_BATCH_STATUSES)))
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
    if campus_id:
        q = q.eq("campus_id", campus_id)
    batches = q.order("created_at", ascending=True).limit(20).execute() or []       # D08-B02: oldest first (was newest: the older batch was never shown)

    sequencing_mode = request.args.get("sequencing", DEFAULT_SEQUENCING_MODE)
    if sequencing_mode not in VALID_SEQUENCING_MODES:
        sequencing_mode = DEFAULT_SEQUENCING_MODE
    if not batches:
        return jsonify({"batch": None, "orders": [], "batches": [], "other_batches": 0, "sequencing_mode": sequencing_mode}), 200

    # The batch in progress first, otherwise the oldest; the rest follow in creation order.
    featured = next((b for b in batches if b.get("status") == "in_progress"), batches[0])
    batches = [featured] + [b for b in batches if b is not featured]
    batch_ids = [b["id"] for b in batches]

    # D08-B03 / RB-1: a fixed number of queries for ALL of the rider's active batches (not per batch, not per order)
    windows = {}
    window_ids = [b.get("window_id") or b.get("delivery_window_id") for b in batches]
    try:
        for w in _select_in(db, "delivery_windows", "id,label,starts_at,ends_at", "id", window_ids):
            windows[w["id"]] = w
    except SupabaseError:
        logger.warning("my_batch: delivery windows unreadable for rider %s", g.user_id, exc_info=True)

    gates = {}
    try:
        for gate in _select_in(db, "gates", "id,lat,lon", "id", [b.get("gate_id") for b in batches]):
            gates[gate["id"]] = gate
    except SupabaseError:
        logger.warning("my_batch: gates unreadable for rider %s", g.user_id, exc_info=True)

    # A cancelled or refunded order leaves the rider's screen (the rider's session can still read the row;
    # the database trigger has already closed the batch if nothing else in it is open).
    all_orders = _select_in(
        db, "orders",
        "id,order_number,status,notes,delivery_address_snapshot,user_id,guest_name,delivery_location_lat,delivery_location_lon,batch_id",
        "batch_id", batch_ids)
    all_orders = [o for o in all_orders if o.get("status") not in ("cancelled", "refunded")]

    names = {}
    user_ids = [o["user_id"] for o in all_orders if o.get("user_id")]
    if user_ids:
        try:
            for p in _select_in(get_db(), "profiles", "id,full_name", "id", user_ids):
                names[p["id"]] = p.get("full_name")
        except SupabaseError:
            logger.warning("my_batch: customer names unavailable for rider %s", g.user_id, exc_info=True)
    items_by_order = {}
    try:
        for it in _select_in(db, "order_items", "order_id,name_snapshot,quantity", "order_id", [o["id"] for o in all_orders]):
            items_by_order.setdefault(it["order_id"], []).append({"name_snapshot": it.get("name_snapshot"), "quantity": it.get("quantity")})
    except SupabaseError:
        logger.warning("my_batch: order items unavailable for rider %s", g.user_id, exc_info=True)

    views = []
    for batch in batches:
        orders = [o for o in all_orders if o.get("batch_id") == batch["id"]]
        pending = [o for o in orders if o.get("status") in _PENDING_ORDER_STATUSES]
        finished = [o for o in orders if o.get("status") not in _PENDING_ORDER_STATUSES]
        gate = gates.get(batch.get("gate_id"))
        if pending and gate and gate.get("lat") is not None and gate.get("lon") is not None:
            sequence = _sequence_nearest_neighbour if sequencing_mode == "nearest_neighbour" else _sequence_distance_from_gate
            pending = sequence(pending, gate["lat"], gate["lon"])
        view = {k: v for k, v in batch.items() if k != "delivery_window_id"}
        view["delivery_window"] = windows.get(batch.get("window_id") or batch.get("delivery_window_id"))
        view["orders"] = [{
            "id": order["id"],
            "order_number": order.get("order_number"),
            "status": order["status"],
            "notes": order.get("notes"),
            "customer_name": names.get(order.get("user_id")) or order.get("guest_name"),      # D08-B03: guest orders now show the guest's name
            "delivery_address": order.get("delivery_address_snapshot"),
            "items": items_by_order.get(order["id"], []),
            "delivery_rank": rank,
        } for rank, order in enumerate(pending + finished, 1)]
        views.append(view)

    first = views[0]
    # `batch` / `orders` / `other_batches` are the D08 shape (one batch on screen); `batches` carries every active batch
    return jsonify({
        "batch": {k: v for k, v in first.items() if k != "orders"},
        "orders": first["orders"],
        "batches": views,
        "other_batches": len(views) - 1,
        "sequencing_mode": sequencing_mode,
    }), 200


# ───────────────────────────── RID-02 / RID-03 / RID-09 ─────────────────────────────
@riders_bp.route("/orders/<order_id>/deliver", methods=["POST"])
@require_role("rider", "admin")
def mark_delivered(order_id):
    """
    Mark an order as delivered. Repeating the call is safe (200, nothing happens twice).
    ---
    tags: [Riders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: Order marked delivered
      403:
        description: Not your order
      404:
        description: Order not found
      409:
        description: The order changed status meanwhile
    """
    if not validate_uuid(order_id):
        return jsonify({"error": MSG.RIDER_ORDER_NOT_FOUND}), 404
    try:
        return jsonify(_rider_order_view(update_order_status(order_id, "delivered", g.user_id, MSG.RIDER_DELIVERED_NOTE))), 200
    except OrderStatusError as e:
        return _order_error(e)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@riders_bp.route("/orders/<order_id>/attempt", methods=["POST"])
@require_role("rider", "admin")
def mark_attempted(order_id):
    """
    Mark a delivery as attempted (customer unreachable).
    ---
    tags: [Riders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            notes: {type: string, maxLength: 500}
    responses:
      200:
        description: Delivery attempt logged
    """
    if not validate_uuid(order_id):
        return jsonify({"error": MSG.RIDER_ORDER_NOT_FOUND}), 404
    data = request.get_json(force=True, silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400
    notes = data.get("notes", MSG.RIDER_ATTEMPT_DEFAULT_NOTE)
    if notes is None or notes == "":
        notes = MSG.RIDER_ATTEMPT_DEFAULT_NOTE
    if not isinstance(notes, str) or len(notes) > 500:                                          # D08-B05
        return jsonify({"error": MSG.RIDER_NOTES_INVALID}), 400
    try:
        return jsonify(_rider_order_view(update_order_status(order_id, "delivery_attempted", g.user_id, notes))), 200
    except OrderStatusError as e:
        return _order_error(e)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@riders_bp.route("/orders/<order_id>/pickup", methods=["POST"])
@require_role("rider", "admin")
def mark_picked_up(order_id):
    """
    Confirm order pickup from kitchen. Transitions the order from 'assigned' (or 'ready') → 'out_for_delivery'.
    ---
    tags: [Riders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: Pickup confirmed, order now out for delivery
      400:
        description: Order not ready for pickup
      404:
        description: Order not found
    """
    if not validate_uuid(order_id):
        return jsonify({"error": MSG.RIDER_ORDER_NOT_FOUND}), 404
    db = get_user_client()
    order = db.table("orders").select("id,status").eq("id", order_id).single().execute()        # RLS: a rider only sees orders assigned to them
    if not order:
        return jsonify({"error": MSG.RIDER_ORDER_NOT_FOUND}), 404
    if order.get("status") == "out_for_delivery":                                              # double tap / retry: already picked up
        return jsonify({"message": MSG.RIDER_PICKUP_OK, "order": order}), 200
    if order.get("status") not in ("assigned", "ready"):
        return jsonify({"error": MSG.RIDER_PICKUP_NOT_READY}), 400
    try:
        result = update_order_status(order_id, "out_for_delivery", g.user_id, MSG.RIDER_PICKUP_NOTE)
        return jsonify({"message": MSG.RIDER_PICKUP_OK, "order": _rider_order_view(result)}), 200
    except OrderStatusError as e:
        return _order_error(e)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ───────────────────────────── RID-04 / RID-05 ─────────────────────────────
@riders_bp.route("/location-update", methods=["POST"])
@require_role("rider", "admin")
@rate_limit(max_requests=120, window_seconds=60)                                               # RB-3: continuous pings, per rider
def location_update():
    """
    Continuous rider location ping. Accepts { location_lat, location_lng },
    writes to rider_profiles.location_lat / location_lng.
    ---
    tags: [Riders]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            location_lat: {type: number}
            location_lng: {type: number}
    responses:
      200:
        description: Location updated
      400:
        description: Missing or invalid coordinates
    """
    data = _json_object()
    if data is None:
        return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400
    raw_lat = data.get("location_lat")
    raw_lng = data.get("location_lng") if data.get("location_lng") is not None else data.get("location_lon")
    if raw_lat is None or raw_lng is None:
        return jsonify({"error": MSG.RIDER_LOCATION_REQUIRED}), 400
    lat, lng = _coord(raw_lat, -90, 90), _coord(raw_lng, -180, 180)
    if lat is None or lng is None:
        return jsonify({"error": MSG.RIDER_LOCATION_INVALID}), 400

    now = _now_iso()
    # D08-B04: a failed write is an error, not a 200 (it was swallowed); availability_updated_at is no longer touched by pings
    _upsert_rider_profile({"location_lat": lat, "location_lng": lng, "updated_at": now})
    return jsonify({"message": MSG.RIDER_LOCATION_UPDATED, "location_lat": lat, "location_lng": lng, "updated_at": now}), 200


@riders_bp.route("/availability", methods=["PATCH"])
@require_role("rider", "admin")
def toggle_availability():
    """
    Toggle rider online/offline availability status.
    ---
    tags: [Riders]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [is_available]
          properties:
            is_available: {type: boolean, description: "true = online/ready, false = offline"}
            location_lat: {type: number}
            location_lng: {type: number}
    responses:
      200:
        description: Availability updated
    """
    data = _json_object()
    if data is None:
        return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400
    if "is_available" not in data:
        return jsonify({"error": MSG.RIDER_AVAILABILITY_REQUIRED}), 400
    available = _bool(data["is_available"])                                                    # D08-B05: bool("false") was True
    if available is None:
        return jsonify({"error": MSG.RIDER_AVAILABILITY_INVALID}), 400

    now = _now_iso()
    update = {"is_available": available, "availability_updated_at": now, "updated_at": now}
    if data.get("location_lat") is not None or data.get("location_lng") is not None:
        lat, lng = _coord(data.get("location_lat"), -90, 90), _coord(data.get("location_lng"), -180, 180)
        if lat is None or lng is None:
            return jsonify({"error": MSG.RIDER_LOCATION_INVALID}), 400
        update["location_lat"], update["location_lng"] = lat, lng

    _upsert_rider_profile(update)                                                              # D08-B04
    return jsonify({"is_available": available, "status": "online" if available else "offline", "updated_at": now}), 200


# ───────────────────────────── RID-06 / RID-07 / RID-08 ─────────────────────────────
@riders_bp.route("/history", methods=["GET"])
@require_role("rider", "admin")
def delivery_history():
    """
    Get the authenticated rider's completed delivery history.
    ---
    tags: [Riders]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 20
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: Past deliveries with batch and order summaries
      400:
        description: Invalid limit / offset
    """
    page = _page_args()
    if page is None:
        return jsonify({"error": MSG.RIDER_QUERY_INVALID}), 400
    limit, offset = page
    db = get_user_client()

    q = db.table("delivery_batches").select("id,window_id,zone,status,created_at,completed_at,rider_pay_total,rider_paid_at").eq("rider_id", g.user_id).eq("status", "completed")   # D08-B06: 'delivered' is not a batch status
    campus_id = getattr(g, "campus_id", None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    batches = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []

    # D08-B03: one chunked query for all the batches instead of one per batch
    by_batch = {}
    for o in _select_in(db, "orders", "id,status,batch_id", "batch_id", [b["id"] for b in batches]):
        by_batch.setdefault(o["batch_id"], []).append({"id": o["id"], "status": o["status"]})
    result = [{**b, "order_count": len(by_batch.get(b["id"], [])), "orders": by_batch.get(b["id"], [])} for b in batches]
    return jsonify({"history": result, "count": len(result)}), 200


@riders_bp.route("/stats", methods=["GET"])
@require_role("rider", "admin")
def rider_stats():
    """
    Get performance statistics for the authenticated rider (computed by the database function hg_rider_stats).
    ---
    tags: [Riders]
    responses:
      200:
        description: Rider delivery stats — total deliveries, completion rate, zones served
    """
    db = get_user_client()
    rows = db.rpc("hg_rider_stats") or []                                                       # D08-B07: one source of truth (auth.uid() scoped)
    stats = rows[0] if isinstance(rows, list) and rows else {}
    total = int(stats.get("total_batches") or 0)
    completed = int(stats.get("completed_batches") or 0)

    rider_profile = {}
    try:
        rider_profile = db.table("rider_profiles").select("is_available,availability_updated_at").eq("user_id", g.user_id).single().execute() or {}
    except SupabaseError:
        logger.warning("rider_stats: rider profile unreadable for %s", g.user_id, exc_info=True)

    return jsonify({
        "rider_id": g.user_id,
        "total_batches": total,
        "completed_batches": completed,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        "total_orders_delivered": int(stats.get("total_orders_delivered") or 0),
        "zones_served": sorted(stats.get("zones") or []),
        "is_available": rider_profile.get("is_available", False),
        "availability_updated_at": rider_profile.get("availability_updated_at"),
    }), 200


@riders_bp.route("/earnings", methods=["GET"])
@require_role("rider", "admin")
def rider_earnings():
    """
    Get the authenticated rider's earnings for a period.
    Riders are paid per completed batch (delivery_batches.rider_pay_total, set by an admin). Batches an admin has not
    priced yet are counted in `unpriced_batches`. Periods use Nigerian time (WAT).
    ---
    tags: [Riders]
    parameters:
      - in: query
        name: period
        type: string
        enum: [today, week, month, all]
        default: week
    responses:
      200:
        description: "{period, since, completed_batches, total_earnings, total_paid, outstanding, unpriced_batches, batches[]}"
      400:
        description: Invalid period
    """
    period = request.args.get("period", "week")
    page = _page_args(100, 100)                                                                # RB-6: page through long histories
    if page is None:
        return jsonify({"error": MSG.RIDER_QUERY_INVALID}), 400
    limit, offset = page
    valid, since = _period_since(period)                                                       # D08-B07: "today" = midnight in Lagos, not midnight UTC
    if not valid:
        return jsonify({"error": MSG.RIDER_EARNINGS_INVALID_PERIOD}), 400

    db = get_user_client()
    params = {"p_since": since.isoformat() if since else None}
    rows = db.rpc("hg_rider_earnings", params) or []                                           # D08-B07: database functions, scoped to auth.uid()
    summary = rows[0] if isinstance(rows, list) and rows else {}
    batches = db.rpc("hg_rider_batch_pay", {**params, "p_limit": limit, "p_offset": offset}) or []
    total = Decimal(str(summary.get("total_earnings") or 0))
    paid = Decimal(str(summary.get("total_paid") or 0))
    return jsonify({
        "period": period,
        "since": since.isoformat() if since else None,
        "completed_batches": int(summary.get("completed_batches") or 0),
        "total_earnings": float(total),
        "total_paid": float(paid),
        "outstanding": float(total - paid),
        "unpriced_batches": int(summary.get("unpriced_batches") or 0),
        "batches": [{
            "batch_id": b.get("batch_id"), "zone": b.get("zone"), "completed_at": b.get("completed_at"),
            "amount": float(b["rider_pay_total"]) if b.get("rider_pay_total") is not None else None,
            "paid_at": b.get("rider_paid_at"), "order_count": b.get("order_count"),
        } for b in batches],
        "batches_shown": len(batches),
    }), 200


# ───────────────────────────── RID-10 ─────────────────────────────
@riders_bp.route("/call/<order_id>", methods=["GET"])
@require_role("rider", "admin")
def get_customer_call_link(order_id):
    """
    Get a click-to-call link for the customer.
    Returns a tel: URI formatted with the customer's phone number for mobile dialing.
    A rider can only call the customer of an order that is still live (not delivered / cancelled / refunded).
    ---
    tags: [Riders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: "Click-to-call tel: URI link"
      404:
        description: Order not found / no phone number
    """
    if not validate_uuid(order_id):
        return jsonify({"error": MSG.RIDER_ORDER_NOT_FOUND}), 404
    db = get_user_client()
    order = db.table("orders").select("user_id,guest_phone,status").eq("id", order_id).single().execute()      # RLS: rider -> assigned orders only
    if not order:
        return jsonify({"error": MSG.RIDER_ORDER_NOT_FOUND}), 404
    if getattr(g, "user_role", None) == "rider" and order.get("status") not in _LIVE_ORDER_STATUSES:            # D08-B08
        return jsonify({"error": MSG.RIDER_ORDER_NOT_ACTIVE}), 403

    phone = order.get("guest_phone")
    if order.get("user_id"):
        profile = get_db().table("profiles").select("phone").eq("id", order["user_id"]).single().execute()
        phone = (profile.get("phone") if profile else None) or phone                            # D08-B08: fall back to the order's phone
    phone = re.sub(r"[^\d+]", "", phone or "")                                                 # D08-B08: only digits and '+' go into the tel: link
    if len(re.sub(r"\D", "", phone)) < 7:
        return jsonify({"error": MSG.RIDER_NO_PHONE}), 404
    return jsonify({"call_link": f"tel:{phone}"}), 200


# ───────────────────────────── NEW (D08-B10): roster for admins ─────────────────────────────
@riders_bp.route("/roster", methods=["GET"])
@require_role("admin")
def rider_roster():
    """
    Riders of the campus with their availability, last known location and number of active batches (admin only).
    Lets an admin see who is online before assigning a batch. super_admin: all campuses, or ?campus_id=.
    ---
    tags: [Riders]
    parameters:
      - in: query
        name: campus_id
        type: string
        description: super_admin only
    responses:
      200:
        description: "[{rider_id, full_name, phone, is_available, availability_updated_at, location_lat, location_lng, location_updated_at, active_batches}]"
    """
    db = get_user_client()
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
    q = db.table("profiles").select("id,full_name,phone,campus_id").eq("role", "rider").eq("is_active", "true")
    if campus_id:
        q = q.eq("campus_id", campus_id)
    riders = _fetch_all(lambda: q)
    ids = [r["id"] for r in riders]
    profiles = {p["user_id"]: p for p in _select_in(db, "rider_profiles", "user_id,is_available,availability_updated_at,location_lat,location_lng,updated_at", "user_id", ids)}
    active = {}
    for b in _select_in(db, "delivery_batches", "id,rider_id", "rider_id", ids, lambda x: x.in_("status", list(_ACTIVE_BATCH_STATUSES))):
        active[b["rider_id"]] = active.get(b["rider_id"], 0) + 1
    roster = []
    for r in riders:
        p = profiles.get(r["id"], {})
        roster.append({
            "rider_id": r["id"], "full_name": r.get("full_name"), "phone": r.get("phone"), "campus_id": r.get("campus_id"),
            "is_available": bool(p.get("is_available")), "availability_updated_at": p.get("availability_updated_at"),
            "location_lat": p.get("location_lat"), "location_lng": p.get("location_lng"), "location_updated_at": p.get("updated_at"),
            "active_batches": active.get(r["id"], 0),
        })
    roster.sort(key=lambda r: (not r["is_available"], r["active_batches"], r["full_name"] or ""))
    return jsonify({"riders": roster, "count": len(roster)}), 200


# ───────────────────────────── RB-11: batch pay and the payments screen (admin only) ─────────────────────────────
# Riders are paid per completed batch. Earnings (rider_earnings above) read delivery_batches.rider_pay_total, and
# nothing else in the code base ever sets it, so without these routes every batch would show as unpriced.
def _non_negative_number(value):
    """True for a real number that is 0 or more (rejects bool, NaN, infinity and text)."""
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0


def _log_rider_admin_action(entity_type, entity_id, action, before=None, after=None, campus_id=None):
    """Write an admin_audit_logs row. Never raises: a logging failure must not undo the change."""
    try:
        get_user_client().table("admin_audit_logs").insert({
            "actor_id": g.user_id,
            "actor_role": getattr(g, "user_role", "admin"),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "before_value": before,
            "after_value": after,
            "campus_id": campus_id or getattr(g, "campus_id", None),
        })
    except Exception:
        logger.warning("rider admin audit log write failed (%s %s)", action, entity_id, exc_info=True)


def _period_since(period):
    """(valid, since_utc) for period = today | week | month | all. 'today' starts at midnight Nigerian time."""
    now = datetime.now(timezone.utc)
    if period == "today":
        return True, datetime.combine(today_wat(), dtime.min, tzinfo=_WAT)
    if period == "week":
        return True, now - timedelta(days=7)
    if period == "month":
        return True, now - timedelta(days=30)
    if period == "all":
        return True, None
    return False, None


@riders_bp.route("/admin/batches/<batch_id>/pay", methods=["PATCH"])
@require_role("admin")
def admin_set_batch_pay(batch_id):
    """
    Set the total the rider is paid for a batch (admin only). Riders see this total, never a per-order amount.
    ---
    tags: [Riders]
    security:
      - Bearer: []
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            rider_pay_total: {type: number}
    responses:
      200: {description: Pay saved}
      400: {description: Invalid amount, or the batch is cancelled}
      404: {description: Batch not found}
      409: {description: Already marked paid}
    """
    if not validate_uuid(batch_id):
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    data = _json_object()
    if data is None or not _non_negative_number(data.get("rider_pay_total")):
        return jsonify({"error": MSG.RIDER_PAY_INVALID}), 400
    db = get_user_client()
    batch = db.table("delivery_batches").select("id,status,rider_pay_total,rider_paid_at,campus_id").eq("id", batch_id).single().execute()
    if not batch:
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    if batch.get("rider_paid_at"):
        return jsonify({"error": MSG.RIDER_PAY_ALREADY_PAID}), 409
    if batch.get("status") == "cancelled":
        return jsonify({"error": MSG.RIDER_PAY_BATCH_CANCELLED}), 400
    amount = round(float(data["rider_pay_total"]), 2)
    # only while it is still unpaid: an admin marking it paid at the same moment must win
    updated = db.table("delivery_batches").eq("id", batch_id).eq("rider_paid_at", None).update({"rider_pay_total": amount})
    if not updated:
        return jsonify({"error": MSG.RIDER_PAY_ALREADY_PAID}), 409
    _log_rider_admin_action(
        "delivery_batch", batch_id, "set_rider_pay",
        before={"rider_pay_total": batch.get("rider_pay_total")}, after={"rider_pay_total": amount},
        campus_id=batch.get("campus_id"),
    )
    return jsonify({"batch_id": batch_id, "rider_pay_total": amount}), 200


@riders_bp.route("/admin/payments", methods=["GET"])
@require_role("admin")
def admin_rider_payments():
    """
    Every rider of the campus with completed batches, earned, paid and outstanding (admin only).
    ---
    tags: [Riders]
    security:
      - Bearer: []
    parameters:
      - in: query
        name: period
        type: string
        enum: [today, week, month, all]
        default: all
    responses:
      200: {description: Riders and their payments}
    """
    valid, since = _period_since(request.args.get("period", "all"))
    if not valid:
        return jsonify({"error": MSG.RIDER_EARNINGS_INVALID_PERIOD}), 400
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
    rows = get_user_client().rpc("hg_admin_rider_payments", {
        "p_campus": campus_id,
        "p_since": since.isoformat() if since else None,
    }) or []
    return jsonify({"riders": rows, "count": len(rows)}), 200


@riders_bp.route("/admin/payments/<rider_id>", methods=["GET"])
@require_role("admin")
def admin_rider_payment_batches(rider_id):
    """
    One rider's batches with pay, paid state, fees collected and what each batch cost (admin only).
    ---
    tags: [Riders]
    security:
      - Bearer: []
    responses:
      200: {description: Batches for the rider}
    """
    if not validate_uuid(rider_id):
        return jsonify({"error": MSG.RIDER_QUERY_INVALID}), 400
    valid, since = _period_since(request.args.get("period", "all"))
    if not valid:
        return jsonify({"error": MSG.RIDER_EARNINGS_INVALID_PERIOD}), 400
    page = _page_args(50, 100)
    if page is None:
        return jsonify({"error": MSG.RIDER_QUERY_INVALID}), 400
    limit, offset = page
    rows = get_user_client().rpc("hg_admin_rider_batches", {
        "p_rider": rider_id,
        "p_since": since.isoformat() if since else None,
        "p_limit": limit,
        "p_offset": offset,
    }) or []
    return jsonify({"rider_id": rider_id, "batches": rows, "count": len(rows)}), 200


@riders_bp.route("/admin/batches/<batch_id>/pay-breakdown", methods=["GET"])
@require_role("admin")
def admin_batch_pay_breakdown(batch_id):
    """
    Per-order split of a batch total, for records only (admin only). Never shown to riders.
    ---
    tags: [Riders]
    security:
      - Bearer: []
    responses:
      200: {description: Split}
    """
    if not validate_uuid(batch_id):
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    rows = get_user_client().rpc("hg_admin_batch_pay_breakdown", {"p_batch": batch_id}) or []
    return jsonify({"batch_id": batch_id, "orders": rows, "count": len(rows)}), 200


def _set_batches_paid_state(paid):
    data = _json_object()
    batch_ids = (data or {}).get("batch_ids")
    if (
        not isinstance(batch_ids, list) or not batch_ids or len(batch_ids) > 100
        or not all(isinstance(b, str) and validate_uuid(b) for b in batch_ids)
    ):
        return jsonify({"error": MSG.RIDER_PAY_BATCH_IDS_INVALID}), 400
    batch_ids = list(dict.fromkeys(batch_ids))
    db = get_user_client()
    rows = _select_in(db, "delivery_batches", "id,status,rider_pay_total,rider_paid_at,campus_id", "id", batch_ids)
    by_id = {r["id"]: r for r in rows}
    now_iso = _now_iso()
    updated = []
    for batch_id in batch_ids:
        row = by_id.get(batch_id)
        if not row:
            continue
        if paid:
            # only a completed batch with a total that is not already paid; the write repeats those conditions
            if row["status"] != "completed" or row.get("rider_pay_total") is None or row.get("rider_paid_at"):
                continue
            done = (db.table("delivery_batches").eq("id", batch_id).eq("status", "completed").eq("rider_paid_at", None)
                    .update({"rider_paid_at": now_iso, "rider_paid_by": g.user_id}))
        else:
            if not row.get("rider_paid_at"):
                continue
            done = db.table("delivery_batches").eq("id", batch_id).update({"rider_paid_at": None, "rider_paid_by": None})
        if not done:
            continue
        updated.append(batch_id)
        _log_rider_admin_action(
            "delivery_batch", batch_id, "mark_rider_paid" if paid else "mark_rider_unpaid",
            after={"rider_paid_at": now_iso if paid else None}, campus_id=row.get("campus_id"),
        )
    return jsonify({
        "updated": updated,
        "skipped": [b for b in batch_ids if b in by_id and b not in updated],
        "not_found": [b for b in batch_ids if b not in by_id],
    }), 200


@riders_bp.route("/admin/payments/mark-paid", methods=["POST"])
@require_role("admin")
def admin_mark_batches_paid():
    """
    Mark completed batches as paid to the rider (admin only). Payment itself happens outside the site.
    ---
    tags: [Riders]
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          properties:
            batch_ids: {type: array, items: {type: string}}
    responses:
      200: {description: Batches marked paid}
    """
    return _set_batches_paid_state(True)


@riders_bp.route("/admin/payments/mark-unpaid", methods=["POST"])
@require_role("admin")
def admin_mark_batches_unpaid():
    """
    Undo a paid marker (admin only). Logged.
    ---
    tags: [Riders]
    security:
      - Bearer: []
    responses:
      200: {description: Batches marked unpaid}
    """
    return _set_batches_paid_state(False)
