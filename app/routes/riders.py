"""Rider dashboard routes — role: rider only."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.services.order_service import update_order_status
from app.db import get_db

riders_bp = Blueprint("riders", __name__)


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
        .select("id,window_id,zone,status,delivery_windows(label,opens_at,closes_at)")
        .eq("rider_id", g.user_id)
        .in_("status", ["assigned", "in_progress"])
        .order("assigned_at", ascending=False)
        .limit(1)
        .execute()
    )

    if not batches:
        return jsonify({"batch": None, "orders": []}), 200

    batch = batches[0]
    batch_id = batch["id"]

    orders = (
        db.table("orders")
        .select("id,status,order_notes,delivery_address_snapshot,order_items(item_name,quantity),profiles(full_name)")
        .eq("batch_id", batch_id)
        .execute()
    )

    safe_orders = []
    for order in orders:
        safe_orders.append({
            "id": order["id"],
            "status": order["status"],
            "order_notes": order.get("order_notes"),
            "customer_name": order.get("profiles", {}).get("full_name") if order.get("profiles") else None,
            "delivery_address": order.get("delivery_address_snapshot"),
            "items": order.get("order_items", []),
        })

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
        result = update_order_status(order_id, "attempted", g.user_id, data.get("notes", "Delivery attempted — customer unreachable"))
        return jsonify(result), 200
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
        return jsonify({"error": "Order not found"}), 404

    phone = order.get("guest_phone")
    if order.get("user_id"):
        profile = db.table("profiles").select("phone").eq("id", order["user_id"]).single().execute()
        phone = profile.get("phone") if profile else phone

    if not phone:
        return jsonify({"error": "No phone number available"}), 404

    return jsonify({"call_link": f"tel:{phone}"}), 200
