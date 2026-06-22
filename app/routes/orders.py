"""Order routes — create, track, manage delivery."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role, optional_auth
from app.middleware.rate_limit import rate_limit
from app.services import order_service
from app.services.hp_service import earn_pending_hp
from app.db import get_db

orders_bp = Blueprint("orders", __name__)


@orders_bp.route("", methods=["POST"])
@optional_auth
@rate_limit(max_requests=10, window_seconds=300)
def create_order():
    """
    Create a new order. Supports authenticated and guest checkout.
    ---
    tags: [Orders]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [items, delivery_window_id, payment_method, delivery_address]
          properties:
            items:
              type: array
              items:
                properties:
                  menu_item_id: {type: string}
                  quantity: {type: integer}
            delivery_window_id: {type: string}
            payment_method: {type: string, enum: [wallet, card, split]}
            delivery_address:
              type: object
              properties:
                address_line: {type: string}
                landmark: {type: string}
                zone: {type: string}
            promo_code: {type: string}
            hp_points_to_redeem: {type: integer}
            notes: {type: string}
            guest_name: {type: string}
            guest_phone: {type: string}
            guest_email: {type: string}
            is_scheduled: {type: boolean}
            scheduled_for_window_id: {type: string}
    responses:
      201:
        description: Order created
      400:
        description: Validation error
    """
    data = request.get_json(force=True)
    user_id = g.user_id

    is_guest = user_id is None
    if is_guest:
        for field in ["guest_name", "guest_phone"]:
            if not data.get(field):
                return jsonify({"error": f"'{field}' required for guest checkout"}), 400
        if data.get("payment_method") == "wallet":
            return jsonify({"error": "Wallet payment requires a logged-in account"}), 400
        if data.get("hp_points_to_redeem", 0) > 0:
            return jsonify({"error": "HP redemption requires a logged-in account"}), 400

    try:
        order = order_service.create_order(user_id, data)
        return jsonify(order), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Order creation failed", "detail": str(e)}), 500


@orders_bp.route("", methods=["GET"])
@require_auth
def list_orders():
    """
    List authenticated user's orders.
    ---
    tags: [Orders]
    parameters:
      - in: query
        name: status
        type: string
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
        description: Order list
    """
    db = get_db()
    q = db.table("orders").select("*,order_items(*)").eq("user_id", g.user_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(orders), 200


@orders_bp.route("/<order_id>", methods=["GET"])
@optional_auth
def get_order(order_id):
    """
    Get order detail. Authenticated users can only see their own orders.
    Guest orders accessible via claim_token query param.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: query
        name: claim_token
        type: string
    responses:
      200:
        description: Order detail
      403:
        description: Access denied
      404:
        description: Not found
    """
    db = get_db()
    order = db.table("orders").select("*,order_items(*),delivery_windows(*),delivery_batches(rider_id,zone,status)").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    claim_token = request.args.get("claim_token")
    if g.user_id:
        if order.get("user_id") and order["user_id"] != g.user_id:
            return jsonify({"error": "Access denied"}), 403
    elif claim_token:
        if order.get("claim_token") != claim_token:
            return jsonify({"error": "Invalid claim token"}), 403
    else:
        return jsonify({"error": "Authentication or claim_token required"}), 403

    return jsonify(order), 200


@orders_bp.route("/<order_id>/status", methods=["PATCH"])
@require_role("admin", "kitchen", "rider")
def update_status(order_id):
    """
    Update order status (kitchen/rider/admin).
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string}
            notes: {type: string}
    responses:
      200:
        description: Status updated
      400:
        description: Invalid transition
    """
    data = request.get_json(force=True)
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": "status is required"}), 400

    try:
        result = order_service.update_order_status(
            order_id=order_id,
            new_status=new_status,
            changed_by=g.user_id,
            notes=data.get("notes", ""),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@orders_bp.route("/<order_id>/review", methods=["POST"])
@require_auth
def submit_review(order_id):
    """
    Submit an order review (earns 20 HP, once per month).
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [rating]
          properties:
            rating: {type: string, enum: [1,2,3,4,5]}
            comment: {type: string}
    responses:
      201:
        description: Review submitted, HP earned
    """
    db = get_db()
    data = request.get_json(force=True)

    order = db.table("orders").select("user_id,status,review_submitted").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order.get("user_id") != g.user_id:
        return jsonify({"error": "Access denied"}), 403
    if order.get("status") != "delivered":
        return jsonify({"error": "Can only review delivered orders"}), 400
    if order.get("review_submitted"):
        return jsonify({"error": "Order already reviewed"}), 400

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    existing_review_this_month = (
        db.table("order_reviews")
        .select("id")
        .eq("user_id", g.user_id)
        .gte("created_at", month_start)
        .execute()
    )

    review = db.table("order_reviews").insert({
        "order_id": order_id,
        "user_id": g.user_id,
        "rating": str(data.get("rating", "5")),
        "comment": data.get("comment", ""),
        "hp_awarded": False,
    })
    review_row = review[0] if isinstance(review, list) else review
    review_id = review_row["id"]

    hp_awarded = 0
    if not existing_review_this_month:
        hp_amount = current_app.config["REVIEW_HP"]
        earn_pending_hp(
            user_id=g.user_id,
            amount=hp_amount,
            source_type="review",
            reference_id=review_id,
            notes="HP for leaving a review (monthly cap 1x)",
        )
        db.table("order_reviews").eq("id", review_id).update({"hp_awarded": True, "hp_transaction_id": None})
        hp_awarded = hp_amount

    db.table("orders").eq("id", order_id).update({"review_submitted": True})

    return jsonify({"review": review_row, "hp_awarded": hp_awarded}), 201


@orders_bp.route("/<order_id>/claim", methods=["POST"])
@require_auth
def claim_guest_order(order_id):
    """
    Link a guest order to a newly created account.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [claim_token]
          properties:
            claim_token: {type: string}
    responses:
      200:
        description: Order linked to account
    """
    data = request.get_json(force=True)
    claim_token = data.get("claim_token")
    if not claim_token:
        return jsonify({"error": "claim_token is required"}), 400

    try:
        result = get_db().rpc("claim_guest_order", {
            "p_order_id": order_id,
            "p_user_id": g.user_id,
            "p_claim_token": claim_token,
        })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@orders_bp.route("/<order_id>/history", methods=["GET"])
@require_auth
def order_status_history(order_id):
    """
    Get the full status change history for an order.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: List of status transitions with timestamps and actor info
      404:
        description: Order not found or not accessible
    """
    from app.middleware.auth import require_role as _rr
    db = get_db()
    order = (
        db.table("orders")
        .select("id,user_id,guest_phone")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": "Order not found"}), 404

    is_owner = (
        order.get("user_id") == g.user_id or
        getattr(g, "role", None) in ("admin", "kitchen", "rider")
    )
    if not is_owner:
        return jsonify({"error": "Access denied"}), 403

    history = (
        db.table("order_status_log")
        .select("*")
        .eq("order_id", order_id)
        .order("changed_at", ascending=True)
        .execute()
    )
    return jsonify(history), 200
