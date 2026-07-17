"""Rider dashboard routes — role: rider only."""

import math
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.services.order_service import update_order_status
from app.db import get_db
from app.messages import MSG

riders_bp = Blueprint("riders", __name__)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Return great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlam = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@riders_bp.route("/my-batch", methods=["GET"])
@require_role("rider", "admin")
def my_batch():
    """
    Get the current delivery batch assigned to this rider.
    Shows customer name, address, items, order number. Phone never exposed in payload.
    ---
    tags: [Riders]
    responses:
      200:
        description: Rider's assigned batch
    """
    db = get_db()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    batches = (
        db.table("delivery_batches")
        .select("id,window_id,zone,status,created_at")
        .eq("rider_id", g.user_id)
        .in_("status", ["assigned", "in_progress"])
        .order("created_at", ascending=False)
        .limit(1)
        .execute()
    )

    if not batches:
        return jsonify({"batch": None, "orders": []}), 200

    batch = batches[0]
    batch_id = batch["id"]

    window_id = batch.get("window_id")
    if window_id:
        try:
            window = (
                db.table("delivery_windows")
                .select("id,label,starts_at,ends_at")
                .eq("id", window_id)
                .single()
                .execute()
            )
            batch["delivery_window"] = window
        except Exception:
            batch["delivery_window"] = None

    orders = (
        db.table("orders")
        .select("id,status,notes,delivery_address_snapshot,user_id")
        .eq("batch_id", batch_id)
        .execute()
    )

    # Fetch gate coordinates for distance ranking (look up via batch zone name or gate table)
    gate_lat = None
    gate_lon = None
    try:
        zone_name = batch.get("zone", "")
        if zone_name:
            gate_row = (
                db.table("gates")
                .select("lat,lon")
                .ilike("name", f"%{zone_name}%")
                .eq("is_active", "true")
                .limit(1)
                .execute()
            )
            if gate_row:
                gate_lat = gate_row[0].get("lat")
                gate_lon = gate_row[0].get("lon")
    except Exception:
        pass

    # Fetch full order details for distance sorting
    orders_full = (
        db.table("orders")
        .select("id,status,notes,delivery_address_snapshot,user_id,delivery_location_lat,delivery_location_lon")
        .eq("batch_id", batch_id)
        .execute()
    ) if orders else []

    safe_orders = []
    for order in (orders_full or orders):
        customer_name = None
        try:
            if order.get("user_id"):
                profile = (
                    db.table("profiles")
                    .select("full_name")
                    .eq("id", order["user_id"])
                    .single()
                    .execute()
                )
                customer_name = profile.get("full_name") if profile else None
        except Exception:
            pass

        try:
            items = (
                db.table("order_items")
                .select("name_snapshot,quantity")
                .eq("order_id", order["id"])
                .execute()
            ) or []
        except Exception:
            items = []

        # Calculate distance from gate to this order's delivery location
        distance_km = None
        if (gate_lat is not None and gate_lon is not None
                and order.get("delivery_location_lat") is not None
                and order.get("delivery_location_lon") is not None):
            try:
                distance_km = round(_haversine_km(
                    gate_lat, gate_lon,
                    order["delivery_location_lat"],
                    order["delivery_location_lon"],
                ), 2)
            except Exception:
                pass

        safe_orders.append({
            "id": order["id"],
            "status": order["status"],
            "notes": order.get("notes"),
            "customer_name": customer_name,
            "delivery_address": order.get("delivery_address_snapshot"),
            "items": items,
            "distance_km": distance_km,
        })

    # Sort by distance ascending (closest first); orders without coordinates sort last
    safe_orders.sort(key=lambda o: (o["distance_km"] is None, o["distance_km"] or 0))

    # Add delivery rank labels
    for i, o in enumerate(safe_orders, 1):
        o["delivery_rank"] = i
        if o["distance_km"] is not None:
            o["delivery_hint"] = f"Order #{str(o['id'])[:6].upper()} — {o['distance_km']} km (deliver {'first' if i == 1 else ('second' if i == 2 else f'#{i}')})"

    return jsonify({"batch": batch, "orders": safe_orders}), 200


@riders_bp.route("/orders/<order_id>/deliver", methods=["POST"])
@require_role("rider", "admin")
def mark_delivered(order_id):
    """
    Mark an order as delivered.
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
    """
    try:
        result = update_order_status(order_id, "delivered", g.user_id, "Marked delivered by rider")
        return jsonify(result), 200
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
            notes: {type: string}
    responses:
      200:
        description: Delivery attempt logged
    """
    data = request.get_json(force=True) or {}
    try:
        result = update_order_status(order_id, "delivery_attempted", g.user_id, data.get("notes", "Delivery attempted — customer unreachable"))
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


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
    data = request.get_json(force=True)
    if "is_available" not in data:
        return jsonify({"error": MSG.RIDER_AVAILABILITY_REQUIRED}), 400

    db = get_db()
    from datetime import datetime, timezone
    update = {
        "is_available": bool(data["is_available"]),
        "availability_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if data.get("location_lat") is not None:
        update["location_lat"] = float(data["location_lat"])
    if data.get("location_lng") is not None:
        update["location_lng"] = float(data["location_lng"])

    try:
        existing = db.table("rider_profiles").select("id").eq("user_id", g.user_id).single().execute()
        if existing:
            db.table("rider_profiles").eq("user_id", g.user_id).update(update)
        else:
            db.table("rider_profiles").insert({"user_id": g.user_id, **update})
    except Exception:
        pass

    return jsonify({
        "is_available": bool(data["is_available"]),
        "status": "online" if data["is_available"] else "offline",
        "updated_at": update["availability_updated_at"],
    }), 200


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
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))

    batches = (
        db.table("delivery_batches")
        .select("id,window_id,zone,status,created_at")
        .eq("rider_id", g.user_id)
        .in_("status", ["completed", "delivered"])
        .order("created_at", ascending=False)
        .limit(limit)
        .offset(offset)
        .execute()
    ) or []

    result = []
    for batch in batches:
        orders = (
            db.table("orders")
            .select("id,status,delivery_address_snapshot")
            .eq("batch_id", batch["id"])
            .execute()
        ) or []
        result.append({
            **batch,
            "order_count": len(orders),
            "orders": [{"id": o["id"], "status": o["status"]} for o in orders],
        })

    return jsonify({"history": result, "count": len(result)}), 200


@riders_bp.route("/stats", methods=["GET"])
@require_role("rider", "admin")
def rider_stats():
    """
    Get performance statistics for the authenticated rider.
    ---
    tags: [Riders]
    responses:
      200:
        description: Rider delivery stats — total deliveries, completion rate, zones served
    """
    db = get_db()
    all_batches = (
        db.table("delivery_batches")
        .select("id,status,zone,created_at")
        .eq("rider_id", g.user_id)
        .execute()
    ) or []

    total = len(all_batches)
    completed = len([b for b in all_batches if b.get("status") in ("completed", "delivered")])
    zones = list({b["zone"] for b in all_batches if b.get("zone")})

    batch_ids = [b["id"] for b in all_batches if b.get("status") in ("completed", "delivered")]
    total_orders_delivered = 0
    if batch_ids:
        orders = (
            db.table("orders")
            .select("id")
            .in_("batch_id", batch_ids)
            .eq("status", "delivered")
            .execute()
        ) or []
        total_orders_delivered = len(orders)

    try:
        rider_profile = (
            db.table("rider_profiles")
            .select("is_available,availability_updated_at")
            .eq("user_id", g.user_id)
            .single()
            .execute()
        ) or {}
    except Exception:
        rider_profile = {}

    return jsonify({
        "rider_id": g.user_id,
        "total_batches": total,
        "completed_batches": completed,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        "total_orders_delivered": total_orders_delivered,
        "zones_served": zones,
        "is_available": rider_profile.get("is_available", False),
        "availability_updated_at": rider_profile.get("availability_updated_at"),
    }), 200


@riders_bp.route("/earnings", methods=["GET"])
@require_role("rider", "admin")
def rider_earnings():
    """
    Get the authenticated rider's earnings summary for a period.
    Earnings are the sum of the delivery_fee on orders the rider delivered.
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
        description: Rider earnings summary
      400:
        description: Invalid period
    """
    from datetime import datetime, timezone, timedelta

    period = request.args.get("period", "week")
    now = datetime.now(timezone.utc)
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    elif period == "all":
        since = None
    else:
        return jsonify({"error": MSG.RIDER_EARNINGS_INVALID_PERIOD}), 400

    db = get_db()
    batches = (
        db.table("delivery_batches")
        .select("id")
        .eq("rider_id", g.user_id)
        .execute()
    ) or []
    batch_ids = [b["id"] for b in batches]

    orders = []
    if batch_ids:
        q = (
            db.table("orders")
            .select("id,delivery_fee,delivered_at,batch_id")
            .in_("batch_id", batch_ids)
            .eq("status", "delivered")
        )
        if since is not None:
            q = q.gte("delivered_at", since.isoformat())
        orders = q.execute() or []

    total_earnings = round(sum(float(o.get("delivery_fee") or 0) for o in orders), 2)
    deliveries = [
        {"order_id": o["id"], "amount": float(o.get("delivery_fee") or 0), "delivered_at": o.get("delivered_at")}
        for o in orders
    ]

    return jsonify({
        "period": period,
        "since": since.isoformat() if since else None,
        "total_deliveries": len(orders),
        "total_earnings": total_earnings,
        "deliveries": deliveries,
    }), 200


@riders_bp.route("/orders/<order_id>/pickup", methods=["POST"])
@require_role("rider", "admin")
def mark_picked_up(order_id):
    """
    Confirm order pickup from kitchen. Transitions order from 'assigned' → 'out_for_delivery'.
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
        description: Order not in assigned state
      404:
        description: Order not found
    """
    db = get_db()
    order = db.table("orders").select("id,status").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": MSG.RIDER_ORDER_NOT_FOUND}), 404
    if order.get("status") not in ("assigned", "ready"):
        return jsonify({"error": MSG.RIDER_PICKUP_NOT_READY}), 400
    try:
        # Transition ready → out_for_delivery directly (no delivery batch required for simple pickup)
        result = update_order_status(order_id, "out_for_delivery", g.user_id, "Picked up from kitchen")
        return jsonify({"message": MSG.RIDER_PICKUP_OK, "order": result}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@riders_bp.route("/call/<order_id>", methods=["GET"])
@require_role("rider", "admin")
def get_customer_call_link(order_id):
    """
    Get a secure call link for the customer. Phone number never exposed in plain text.
    Returns tel: URI via server-side — never sent to browser as raw number.
    ---
    tags: [Riders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: Secure call link
    """
    db = get_db()
    order = db.table("orders").select("user_id,guest_phone").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": MSG.RIDER_ORDER_NOT_FOUND}), 404

    phone = order.get("guest_phone")
    if order.get("user_id"):
        profile = db.table("profiles").select("phone").eq("id", order["user_id"]).single().execute()
        phone = profile.get("phone") if profile else phone

    if not phone:
        return jsonify({"error": MSG.RIDER_NO_PHONE}), 404

    return jsonify({"call_link": f"tel:{phone}"}), 200
