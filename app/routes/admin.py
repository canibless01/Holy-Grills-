"""Admin panel routes — users, orders, delivery windows, promo codes, audit log."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_role
from app.services.notification_service import send_notification
from app.db import get_db
from datetime import datetime, timezone
from app.messages import MSG
from app.utils.logger import get_logger
from app.utils.validators import (
    validate_choice, validate_positive_number, validate_non_negative_number,
    validate_datetime_order,
)

logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/users", methods=["GET"])
@require_role("admin")
def list_users():
    """
    List all users with HP balance and tier info.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: q
        type: string
      - in: query
        name: role
        type: string
      - in: query
        name: limit
        type: integer
        default: 50
    responses:
      200:
        description: User list
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = db.table("profiles").select("id,full_name,phone,role,is_active,created_at,referral_code,hp_balance,wallet_balance,current_tier_id")
    role_filter = request.args.get("role")
    if role_filter:
        q = q.eq("role", role_filter)
    search = request.args.get("q")
    if search:
        q = q.ilike("full_name", f"%{search}%")

    users = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(users), 200


@admin_bp.route("/users/<user_id>", methods=["GET"])
@require_role("admin")
def get_user(user_id):
    """
    Get full user profile with order history and HP ledger.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
    responses:
      200:
        description: User detail
    """
    db = get_db()
    profile = db.table("profiles").select("*").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404

    from app.services.hp_service import get_hp_balance, get_user_tier
    balance = get_hp_balance(user_id)
    tier = get_user_tier(user_id)
    wallet = db.table("wallets").select("balance").eq("user_id", user_id).single().execute()
    recent_orders = (
        db.table("orders")
        .select("id,status,total_amount,created_at")
        .eq("user_id", user_id)
        .order("created_at", ascending=False)
        .limit(10)
        .execute()
    )

    return jsonify({
        "profile": profile,
        "hp_balance": balance,
        "tier": tier,
        "wallet_balance": float(wallet.get("balance", 0)) if wallet else 0,
        "recent_orders": recent_orders,
    }), 200


@admin_bp.route("/orders", methods=["GET"])
@require_role("admin")
def list_all_orders():
    """
    List all orders across all users (admin only).
    Supports filtering by status, user, date range, and payment method.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: status
        type: string
        description: Filter by order status
      - in: query
        name: user_id
        type: string
        description: Filter by user UUID
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
      - in: query
        name: payment_method
        type: string
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: List of all orders with user and item details
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = db.table("orders").select("*,order_items(name_snapshot,quantity,price_snapshot,line_total)")

    status = request.args.get("status")
    if status:
        q = q.eq("status", status)

    user_id = request.args.get("user_id")
    if user_id:
        q = q.eq("user_id", user_id)

    payment_method = request.args.get("payment_method")
    if payment_method:
        if payment_method == "wallet":
            q = q.gt("wallet_amount_used", 0)
        elif payment_method == "card":
            q = q.gt("card_amount_used", 0)

    from_date = request.args.get("from_date")
    if from_date:
        q = q.gte("created_at", from_date)

    to_date = request.args.get("to_date")
    if to_date:
        q = q.lte("created_at", to_date + "T23:59:59Z")

    orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"orders": orders, "count": len(orders), "limit": limit, "offset": offset}), 200


@admin_bp.route("/users/<user_id>/orders", methods=["GET"])
@require_role("admin")
def user_order_history(user_id):
    """
    Get complete order history for a specific user (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
      - in: query
        name: status
        type: string
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: User's full order history
      404:
        description: User not found
    """
    db = get_db()
    profile = db.table("profiles").select("id,full_name").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404

    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = db.table("orders").select("*,order_items(name_snapshot,quantity,price_snapshot,line_total)").eq("user_id", user_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)

    orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []

    total_spent = sum(float(o.get("total_amount", 0)) for o in orders if o.get("status") == "delivered")

    return jsonify({
        "user": {"id": profile["id"], "full_name": profile["full_name"]},
        "orders": orders,
        "count": len(orders),
        "total_spent": round(total_spent, 2),
        "limit": limit,
        "offset": offset,
    }), 200


@admin_bp.route("/users/<user_id>/role", methods=["PATCH"])
@require_role("admin")
def change_user_role(user_id):
    """
    Change a user's role (admin only). Use with caution.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [role]
          properties:
            role: {type: string, enum: [user, admin, kitchen, rider, super_admin]}
    responses:
      200:
        description: Role updated
      400:
        description: Invalid role
      404:
        description: User not found
    """
    db = get_db()
    profile = db.table("profiles").select("id,full_name,role").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    data = request.get_json(force=True) or {}
    new_role = data.get("role", "").strip()
    VALID_ROLES = {"student", "admin", "kitchen", "rider", "super_admin"}
    if new_role not in VALID_ROLES:
        return jsonify({"error": MSG.ADMIN_INVALID_ROLE.format(roles=", ".join(sorted(VALID_ROLES)))}), 400
    result = db.table("profiles").eq("id", user_id).update({"role": new_role})
    _audit(g.user_id, "profiles", user_id, "change_role",
           {"from": profile.get("role"), "to": new_role})
    return jsonify({"user_id": user_id, "role": new_role, "full_name": profile.get("full_name")}), 200


@admin_bp.route("/users/<user_id>/hp", methods=["GET"])
@require_role("admin")
def user_hp_history(user_id):
    """
    Get HP transaction history for a specific user (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: HP transactions and current balance
      404:
        description: User not found
    """
    db = get_db()
    profile = db.table("profiles").select("id,full_name").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    txns = (
        db.table("hp_transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", ascending=False)
        .limit(limit)
        .offset(offset)
        .execute()
    ) or []
    from app.services.hp_service import get_hp_balance
    balance = get_hp_balance(user_id)
    return jsonify({
        "user": {"id": user_id, "full_name": profile.get("full_name")},
        "hp_balance": balance,
        "transactions": txns,
        "count": len(txns),
    }), 200


@admin_bp.route("/users/<user_id>/wallet", methods=["GET"])
@require_role("admin")
def user_wallet_history(user_id):
    """
    Get wallet transaction history for a specific user (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: Wallet transactions and current balance
      404:
        description: User not found
    """
    db = get_db()
    profile = db.table("profiles").select("id,full_name").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    wallet = db.table("wallets").select("balance,currency").eq("user_id", user_id).single().execute()
    from app.services.wallet_service import get_wallet_transactions
    txns = get_wallet_transactions(user_id, limit=limit, offset=offset)
    return jsonify({
        "user": {"id": user_id, "full_name": profile.get("full_name")},
        "wallet_balance": float(wallet.get("balance", 0)) if wallet else 0,
        "currency": wallet.get("currency", "NGN") if wallet else "NGN",
        "transactions": txns,
        "count": len(txns),
    }), 200


@admin_bp.route("/users/<user_id>/deactivate", methods=["POST"])
@require_role("admin")
def deactivate_user(user_id):
    """
    Deactivate a user account (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
    responses:
      200:
        description: User deactivated
    """
    db = get_db()
    db.table("profiles").eq("id", user_id).update({
        "is_active": False,
        "deactivated_at": datetime.now(timezone.utc).isoformat(),
        "deactivated_by": g.user_id,
    })
    _audit(g.user_id, "profiles", user_id, "deactivate_account")
    return jsonify({"message": MSG.ADMIN_USER_DEACTIVATED}), 200


@admin_bp.route("/users/<user_id>/activate", methods=["POST"])
@require_role("admin")
def activate_user(user_id):
    """
    Reactivate a previously deactivated user account (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
    responses:
      200:
        description: User reactivated
      404:
        description: User not found
    """
    db = get_db()
    profile = db.table("profiles").select("id,is_active,full_name").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    if profile.get("is_active"):
        return jsonify({"message": MSG.ADMIN_USER_ALREADY_ACTIVE, "user_id": user_id}), 200

    db.table("profiles").eq("id", user_id).update({
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    })
    _audit(g.user_id, "profiles", user_id, "activate_account")
    return jsonify({"message": MSG.ADMIN_USER_REACTIVATED, "user_id": user_id}), 200


@admin_bp.route("/delivery-windows", methods=["GET"])
@require_role("admin", "kitchen")
def list_windows():
    """
    List delivery windows (admin/kitchen).
    ---
    tags: [Admin]
    responses:
      200:
        description: Delivery windows
    """
    db = get_db()
    windows = db.table("delivery_windows").select("*").order("starts_at", ascending=False).limit(50).execute()
    for w in (windows or []):
        orders = db.table("orders").select("id").eq("delivery_window_id", w["id"]).execute()
        w["order_count"] = len(orders or [])
    return jsonify(windows), 200


@admin_bp.route("/delivery-windows", methods=["POST"])
@require_role("admin")
def create_window():
    """
    Create a delivery window (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [label, starts_at, ends_at]
          properties:
            label: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
    responses:
      201:
        description: Window created
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    if "opens_at" in data:
        data["starts_at"] = data.pop("opens_at")
    if "closes_at" in data:
        data["ends_at"] = data.pop("closes_at")

    for f in ("label", "starts_at", "ends_at"):
        if not data.get(f):
            return jsonify({"error": MSG.ADMIN_FIELD_REQUIRED.format(field=f)}), 400
    if not isinstance(data["label"], str) or not data["label"].strip():
        return jsonify({"error": "label must be a non-empty string"}), 400

    ok, err = validate_datetime_order(data["starts_at"], data["ends_at"])
    if not ok:
        return jsonify({"error": err}), 400

    if "capacity" in data and data["capacity"] is not None:
        try:
            cap = int(data["capacity"])
            if cap <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "capacity must be a positive integer"}), 400
        data["capacity"] = cap

    if "is_active" in data and not isinstance(data["is_active"], bool):
        return jsonify({"error": "is_active must be a boolean"}), 400

    # Only insert columns that exist in delivery_windows
    WINDOW_COLS = {"label", "starts_at", "ends_at", "capacity", "is_active"}
    safe = {k: v for k, v in data.items() if k in WINDOW_COLS}
    safe["status"] = "open"
    safe["created_by"] = g.user_id
    result = db.table("delivery_windows").insert(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@admin_bp.route("/delivery-windows/<window_id>/close", methods=["POST"])
@require_role("admin")
def close_window(window_id):
    """
    Close a delivery window (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: window_id
        type: string
        required: true
    responses:
      200:
        description: Window closed
    """
    db = get_db()
    db.table("delivery_windows").eq("id", window_id).update({"status": "closed"})
    _audit(g.user_id, "delivery_windows", window_id, "close_window")
    return jsonify({"message": MSG.ADMIN_WINDOW_CLOSED}), 200


@admin_bp.route("/delivery-windows/<window_id>/reopen", methods=["POST"])
@require_role("admin")
def reopen_window(window_id):
    """
    Reopen a previously closed delivery window (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: window_id
        type: string
        required: true
    responses:
      200:
        description: Window reopened
      404:
        description: Window not found
    """
    db = get_db()
    window = db.table("delivery_windows").select("id,status").eq("id", window_id).single().execute()
    if not window:
        return jsonify({"error": MSG.ADMIN_WINDOW_NOT_FOUND}), 404
    if window.get("status") == "open":
        return jsonify({"message": MSG.ADMIN_WINDOW_ALREADY_OPEN, "status": "open"}), 200
    db.table("delivery_windows").eq("id", window_id).update({"status": "open"})
    _audit(g.user_id, "delivery_windows", window_id, "reopen_window")
    return jsonify({"message": MSG.ADMIN_WINDOW_REOPENED, "window_id": window_id, "status": "open"}), 200


@admin_bp.route("/delivery-batches", methods=["GET"])
@require_role("admin")
def list_batches():
    """
    List delivery batches with their assigned rider and order count (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: window_id
        type: string
        description: Filter by delivery window
      - in: query
        name: status
        type: string
        enum: [assigned, completed, cancelled]
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: Delivery batch list
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("delivery_batches").select(
        "*,delivery_windows!window_id(label,starts_at,ends_at),profiles!rider_id(full_name,phone)"
    )
    window_id = request.args.get("window_id")
    if window_id:
        q = q.eq("window_id", window_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    batches = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    # Annotate each batch with its order count
    for b in batches:
        try:
            orders = db.table("orders").select("id").eq("batch_id", b["id"]).execute() or []
            b["order_count"] = len(orders)
        except Exception:
            b["order_count"] = 0
    return jsonify({"batches": batches, "count": len(batches)}), 200


@admin_bp.route("/delivery-batches/<batch_id>", methods=["GET"])
@require_role("admin")
def get_batch(batch_id):
    """
    Get a delivery batch with all assigned orders (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
    responses:
      200:
        description: Batch detail with orders
      404:
        description: Batch not found
    """
    db = get_db()
    batch = db.table("delivery_batches").select(
        "*,delivery_windows!window_id(label,starts_at,ends_at),profiles!rider_id(full_name,phone)"
    ).eq("id", batch_id).limit(1).execute()
    batch = batch[0] if batch else None
    if not batch:
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    orders = db.table("orders").select(
        "id,status,delivery_address_snapshot,total_amount,created_at,"
        "order_items(name_snapshot,quantity)"
    ).eq("batch_id", batch_id).execute() or []
    batch["orders"] = orders
    return jsonify(batch), 200


@admin_bp.route("/delivery-batches", methods=["POST"])
@require_role("admin")
def create_batch():
    """
    Create a delivery batch and assign a rider (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [window_id, rider_id, zone]
          properties:
            window_id: {type: string}
            rider_id: {type: string}
            zone: {type: string}
            order_ids: {type: array, items: {type: string}}
    responses:
      201:
        description: Batch created and orders assigned
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    if not data.get("window_id") or not data.get("rider_id"):
        return jsonify({"error": MSG.REQUIRED_FIELD_MISSING}), 400
    batch = db.table("delivery_batches").insert({
        "window_id": data["window_id"],
        "rider_id": data["rider_id"],
        "zone": data.get("zone", ""),
        "status": "assigned",
    })
    batch_row = batch[0] if isinstance(batch, list) else batch
    batch_id = batch_row["id"]

    for order_id in data.get("order_ids", []):
        db.table("orders").eq("id", order_id).update({"batch_id": batch_id})

    return jsonify(batch_row), 201


@admin_bp.route("/delivery-batches/<batch_id>", methods=["PATCH"])
@require_role("admin")
def update_batch(batch_id):
    """
    Update a delivery batch's status (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          properties:
            status: {type: string, enum: [assigned, completed, cancelled]}
            rider_id: {type: string}
            zone: {type: string}
            notes: {type: string}
    responses:
      200:
        description: Batch updated
      404:
        description: Batch not found
    """
    db = get_db()
    existing = db.table("delivery_batches").select("id").eq("id", batch_id).limit(1).execute()
    if not existing:
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    data = request.get_json(force=True) or {}
    BATCH_UPDATE_COLS = {"status", "rider_id", "zone", "notes"}
    safe = {k: v for k, v in data.items() if k in BATCH_UPDATE_COLS}
    if not safe:
        return jsonify({"error": MSG.ADMIN_BATCH_NO_FIELDS}), 400
    if "status" in safe and safe["status"] not in ("assigned", "completed", "cancelled"):
        return jsonify({"error": MSG.ADMIN_BATCH_INVALID_STATUS}), 400
    if safe.get("status") == "completed":
        safe["completed_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("delivery_batches").eq("id", batch_id).update(safe)
    _audit(g.user_id, "delivery_batches", batch_id, "update_batch", safe)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@admin_bp.route("/delivery-batches/<batch_id>", methods=["DELETE"])
@require_role("admin")
def cancel_batch(batch_id):
    """
    Cancel a delivery batch and unassign its orders (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
    responses:
      200:
        description: Batch cancelled
      404:
        description: Batch not found
    """
    db = get_db()
    existing = db.table("delivery_batches").select("id,status").eq("id", batch_id).limit(1).execute()
    if not existing:
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    db.table("delivery_batches").eq("id", batch_id).update({"status": "cancelled"})
    orders = db.table("orders").select("id").eq("batch_id", batch_id).execute() or []
    for o in orders:
        db.table("orders").eq("id", o["id"]).update({"batch_id": None, "status": "ready"})
    _audit(g.user_id, "delivery_batches", batch_id, "cancel_batch")
    return jsonify({
        "message": MSG.ADMIN_BATCH_CANCELLED,
        "batch_id": batch_id,
        "orders_unassigned": len(orders),
    }), 200


@admin_bp.route("/delivery-batches/<batch_id>/orders", methods=["GET"])
@require_role("admin")
def list_batch_orders(batch_id):
    """
    List all orders assigned to a delivery batch (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
    responses:
      200:
        description: Orders in this batch
      404:
        description: Batch not found
    """
    db = get_db()
    batch = db.table("delivery_batches").select("id").eq("id", batch_id).limit(1).execute()
    if not batch:
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    orders = db.table("orders").select(
        "id,status,delivery_address_snapshot,total_amount,created_at,"
        "order_items(name_snapshot,quantity)"
    ).eq("batch_id", batch_id).execute() or []
    return jsonify({"batch_id": batch_id, "orders": orders, "count": len(orders)}), 200


@admin_bp.route("/promo-codes", methods=["GET"])
@require_role("admin")
def list_promos():
    """
    List all promo codes (admin only).
    ---
    tags: [Admin]
    responses:
      200:
        description: Promo code list
    """
    db = get_db()
    codes = db.table("promo_codes").select("*").order("created_at", ascending=False).execute()
    return jsonify(codes), 200


@admin_bp.route("/promo-codes", methods=["POST"])
@require_role("admin")
def create_promo():
    """
    Create a promo code (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [code, discount_type, discount_value]
          properties:
            code: {type: string}
            discount_type: {type: string, enum: [percentage, flat]}
            discount_value: {type: number}
            min_order_value: {type: number}
            max_discount_cap: {type: number}
            max_uses: {type: integer}
            max_uses_per_user: {type: integer}
            valid_from: {type: string, format: date-time}
            valid_until: {type: string, format: date-time}
            scope: {type: string, enum: [cart, item]}
    responses:
      201:
        description: Promo code created
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["code", "discount_type", "discount_value"]
    for f in required:
        if data.get(f) is None:
            return jsonify({"error": MSG.ADMIN_FIELD_REQUIRED.format(field=f)}), 400
    data["code"] = data["code"].upper()
    data["used_count"] = 0
    data["is_active"] = True
    data["created_by"] = g.user_id
    KNOWN_COLUMNS = {
        "code", "discount_type", "discount_value", "min_order_amount",
        "max_uses", "max_uses_per_user",
        "scope", "used_count", "is_active", "created_by",
        "starts_at", "ends_at",
        "description", "applicable_item_ids", "applicable_category_ids",
    }
    safe = {k: v for k, v in data.items() if k in KNOWN_COLUMNS}
    result = db.table("promo_codes").insert(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@admin_bp.route("/promo-codes/<promo_id>", methods=["PATCH"])
@require_role("admin")
def update_promo(promo_id):
    """
    Update or deactivate a promo code (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: promo_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            is_active: {type: boolean}
            description: {type: string}
            discount_type: {type: string, enum: [percentage, flat]}
            discount_value: {type: number}
            min_order_amount: {type: number}
            max_uses: {type: integer}
            max_uses_per_user: {type: integer}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
    responses:
      200:
        description: Promo code updated
      404:
        description: Promo code not found
    """
    db = get_db()
    existing = db.table("promo_codes").select("id").eq("id", promo_id).limit(1).execute()
    if not existing:
        return jsonify({"error": MSG.ADMIN_PROMO_NOT_FOUND}), 404

    data = request.get_json(force=True) or {}
    KNOWN_COLUMNS = {
        "description", "discount_type", "discount_value", "min_order_amount",
        "max_uses", "max_uses_per_user", "scope", "is_active",
        "starts_at", "ends_at", "applicable_item_ids", "applicable_category_ids",
    }
    safe = {k: v for k, v in data.items() if k in KNOWN_COLUMNS}
    if not safe:
        return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400

    if "discount_type" in safe:
        ok, err = validate_choice(safe["discount_type"], ("percentage", "flat"), "discount_type")
        if not ok:
            return jsonify({"error": err}), 400

    if "scope" in safe:
        ok, err = validate_choice(safe["scope"], ("cart", "item"), "scope")
        if not ok:
            return jsonify({"error": err}), 400

    if "discount_value" in safe:
        ok, err = validate_positive_number(safe["discount_value"], "discount_value")
        if not ok:
            return jsonify({"error": err}), 400
        effective_type = safe.get("discount_type")
        if effective_type == "percentage" and float(safe["discount_value"]) > 100:
            return jsonify({"error": "discount_value must not exceed 100 for a percentage discount"}), 400

    if "min_order_amount" in safe and safe["min_order_amount"] is not None:
        ok, err = validate_non_negative_number(safe["min_order_amount"], "min_order_amount")
        if not ok:
            return jsonify({"error": err}), 400

    for int_field in ("max_uses", "max_uses_per_user"):
        if int_field in safe and safe[int_field] is not None:
            try:
                n = int(safe[int_field])
                if n <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return jsonify({"error": MSG.ADMIN_FIELD_MUST_BE_POSITIVE.format(field=int_field)}), 400
            safe[int_field] = n

    if "starts_at" in safe or "ends_at" in safe:
        current = db.table("promo_codes").select("starts_at,ends_at").eq("id", promo_id).single().execute() or {}
        starts_at = safe.get("starts_at", current.get("starts_at"))
        ends_at = safe.get("ends_at", current.get("ends_at"))
        if starts_at and ends_at:
            ok, err = validate_datetime_order(starts_at, ends_at)
            if not ok:
                return jsonify({"error": err}), 400

    if "is_active" in safe and not isinstance(safe["is_active"], bool):
        return jsonify({"error": "is_active must be a boolean"}), 400

    result = db.table("promo_codes").eq("id", promo_id).update(safe)
    updated = result[0] if isinstance(result, list) else result
    return jsonify({"message": MSG.ADMIN_PROMO_UPDATED, "promo_code": updated}), 200


@admin_bp.route("/promo-codes/<promo_id>/uses", methods=["GET"])
@require_role("admin")
def promo_uses(promo_id):
    """
    Get redemption stats and usage history for a promo code (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: promo_id
        type: string
        required: true
    responses:
      200:
        description: Promo code redemption stats and use log
      404:
        description: Promo code not found
    """
    db = get_db()
    promo = db.table("promo_codes").select("*").eq("id", promo_id).limit(1).execute()
    promo = promo[0] if promo else None
    if not promo:
        return jsonify({"error": MSG.ADMIN_PROMO_NOT_FOUND}), 404

    uses = (
        db.table("promo_code_uses")
        .select("id,user_id,order_id,discount_amount,created_at")
        .eq("promo_code_id", promo_id)
        .order("created_at", ascending=False)
        .execute()
    ) or []

    total_discount_given = round(sum(float(u.get("discount_amount") or 0) for u in uses), 2)

    return jsonify({
        "promo_code": promo,
        "total_uses": len(uses),
        "total_discount_given": total_discount_given,
        "uses": uses,
    }), 200


@admin_bp.route("/abandoned-carts", methods=["GET"])
@require_role("admin")
def abandoned_carts():
    """
    List abandoned carts for recovery (admin only).
    ---
    tags: [Admin]
    responses:
      200:
        description: Abandoned cart list
    """
    db = get_db()
    carts = (
        db.table("abandoned_carts")
        .select("*,profiles(full_name)")
        .eq("is_recovered", "false")
        .order("last_active_at", ascending=False)
        .execute()
    )
    return jsonify(carts), 200


@admin_bp.route("/abandoned-carts/<cart_id>/nudge", methods=["POST"])
@require_role("admin")
def nudge_cart(cart_id):
    """
    Manually trigger recovery nudge for an abandoned cart (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: cart_id
        type: string
        required: true
    responses:
      200:
        description: Recovery nudge sent
    """
    db = get_db()
    cart = db.table("abandoned_carts").select("*").eq("id", cart_id).single().execute()
    if not cart or not cart.get("user_id"):
        return jsonify({"error": MSG.ADMIN_CART_NOT_FOUND}), 404

    send_notification(
        user_id=cart["user_id"],
        notif_type="abandoned_cart",
        template_data={},
        action_url="/cart",
    )
    db.table("abandoned_carts").eq("id", cart_id).update({
        "recovery_attempts": (cart.get("recovery_attempts") or 0) + 1,
        "last_recovery_sent_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": MSG.ADMIN_RECOVERY_NUDGE_SENT}), 200


@admin_bp.route("/audit-log", methods=["GET"])
@require_role("admin")
def audit_log():
    """
    View admin audit log (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 50
    responses:
      200:
        description: Audit log entries
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    logs = db.table("admin_audit_logs").select("*").order("created_at", ascending=False).limit(limit).execute()
    return jsonify(logs), 200


@admin_bp.route("/cron/<job_name>", methods=["POST"])
@require_role("admin")
def run_cron_job(job_name):
    """
    Manually trigger a scheduled cron job (admin only).
    Useful for testing or forcing an immediate run without waiting for Celery beat.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: job_name
        type: string
        required: true
        enum:
          - birthday-hp
          - reset-monthly-leaderboard
          - recalculate-120day-hp
          - tier-grace-period-check
          - hp-decay-check
          - scan-abandoned-carts
          - monthly-birthday-report
          - win-back-notifications
          - check-order-locks
          - reset-monthly-hp-tracker
          - membership-anniversary-awards
          - send-scheduled-notifications
          - process-scheduled-orders
    responses:
      200:
        description: Cron job result
      404:
        description: Unknown job name
      500:
        description: Job execution failed
    """
    from app.tasks.scheduled import (
        birthday_hp_awards,
        reset_monthly_leaderboard,
        recalculate_120day_hp,
        tier_grace_period_check,
        scan_abandoned_carts,
        monthly_birthday_report,
        hp_decay_check,
        win_back_notifications,
        check_order_locks,
        reset_monthly_hp_tracker,
        membership_anniversary_awards,
        send_scheduled_notifications,
        process_scheduled_orders,
    )

    task_map = {
        "birthday-hp":                  birthday_hp_awards,
        "reset-monthly-leaderboard":    reset_monthly_leaderboard,
        "recalculate-120day-hp":        recalculate_120day_hp,
        "tier-grace-period-check":      tier_grace_period_check,
        "scan-abandoned-carts":         scan_abandoned_carts,
        "monthly-birthday-report":      monthly_birthday_report,
        "hp-decay-check":               hp_decay_check,
        "win-back-notifications":       win_back_notifications,
        "check-order-locks":            check_order_locks,
        "reset-monthly-hp-tracker":     reset_monthly_hp_tracker,
        "membership-anniversary-awards": membership_anniversary_awards,
        "send-scheduled-notifications": send_scheduled_notifications,
        "process-scheduled-orders":     process_scheduled_orders,
    }

    task_fn = task_map.get(job_name)
    if not task_fn:
        return jsonify({
            "error": MSG.ADMIN_UNKNOWN_CRON_JOB.format(job=job_name),
            "available_jobs": sorted(task_map.keys()),
        }), 404

    import threading
    triggered_by = g.user_id
    flask_app = current_app._get_current_object()

    def _run():
        # Manual trigger runs task_fn.apply() synchronously in a plain thread,
        # not through the Celery worker pool, so it does not automatically get
        # a Flask application context. Several tasks read current_app.config
        # (e.g. scan_abandoned_carts, hp_decay_check), so push one explicitly
        # or they fail with "Working outside of application context".
        with flask_app.app_context():
            try:
                task_fn.apply().get(timeout=300)
                _audit(triggered_by, "cron_jobs", job_name, "manual_trigger", {})
            except Exception as exc:
                logger.error("cron/%s background run failed: %s", job_name, exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({
        "job": job_name,
        "status": "started",
        "triggered_by": triggered_by,
        "note": MSG.ADMIN_JOB_RUNNING,
    }), 202


@admin_bp.route("/cron/status", methods=["GET"])
@require_role("admin")
def cron_status():
    """
    Show last run time, result, and status of every cron job (admin only).
    Reads from admin_audit_logs — any job that has never been manually triggered
    will show as 'never_run'. Silent failures in background threads are surfaced
    by cross-referencing the last trigger time against expected schedule cadence.
    ---
    tags: [Admin]
    responses:
      200:
        description: Cron job status map
    """
    db = get_db()

    KNOWN_JOBS = [
        "birthday-hp",
        "monthly-birthday-report",
        "tier-grace-period-check",
        "recalculate-120day-hp",
        "hp-decay-check",
        "reset-monthly-leaderboard",
        "scan-abandoned-carts",
        "win-back-notifications",
        "check-order-locks",
        "reset-monthly-hp-tracker",
        "membership-anniversary-awards",
        "send-scheduled-notifications",
        "process-scheduled-orders",
    ]

    EXPECTED_CADENCE = {
        "birthday-hp":                  "daily @ 08:00 WAT",
        "monthly-birthday-report":      "1st of month @ 07:00 WAT",
        "tier-grace-period-check":      "daily @ 03:00 WAT",
        "recalculate-120day-hp":        "daily @ 02:00 WAT",
        "hp-decay-check":               "daily @ 05:00 WAT",
        "reset-monthly-leaderboard":    "1st of month @ 00:01 WAT",
        "scan-abandoned-carts":         "every 30 minutes",
        "win-back-notifications":       "daily @ 10:00 WAT",
        "check-order-locks":            "daily @ 09:00 WAT",
        "reset-monthly-hp-tracker":     "1st of month @ 00:05 WAT",
        "membership-anniversary-awards": "daily @ 06:00 WAT",
        "send-scheduled-notifications": "every 15 minutes",
        "process-scheduled-orders":     "every 5 minutes",
    }

    try:
        logs = (
            db.table("admin_audit_logs")
            .select("entity_id,action,created_at,after_value,actor_id")
            .eq("entity_type", "cron_jobs")
            .order("created_at", ascending=False)
            .limit(200)
            .execute()
        ) or []
    except Exception as exc:
        return jsonify({"error": MSG.ADMIN_AUDIT_LOGS_FAILED.format(error=str(exc))}), 500

    last_by_job = {}
    for row in logs:
        job = row.get("entity_id")
        if job and job not in last_by_job:
            last_by_job[job] = row

    now_iso = datetime.now(timezone.utc).isoformat()
    status_map = {}
    for job in KNOWN_JOBS:
        entry = last_by_job.get(job)
        if entry:
            status_map[job] = {
                "status":        "ok",
                "last_triggered": entry["created_at"],
                "triggered_by":  entry.get("actor_id"),
                "last_result":   entry.get("after_value"),
                "cadence":       EXPECTED_CADENCE.get(job),
            }
        else:
            status_map[job] = {
                "status":        "never_run",
                "last_triggered": None,
                "triggered_by":  None,
                "last_result":   None,
                "cadence":       EXPECTED_CADENCE.get(job),
            }

    return jsonify({
        "checked_at": now_iso,
        "jobs":       status_map,
        "summary": {
            "total":      len(KNOWN_JOBS),
            "ok":         sum(1 for v in status_map.values() if v["status"] == "ok"),
            "never_run":  sum(1 for v in status_map.values() if v["status"] == "never_run"),
        },
    }), 200


@admin_bp.route("/hp/bulk-grant", methods=["POST"])
@require_role("admin")
def bulk_grant_hp():
    """
    Bulk-grant HP to a segment of users (by tier, last-order date, etc.) — for promotions.
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [amount, reason]
          properties:
            amount:
              type: integer
              description: HP amount to award each matched user
            reason:
              type: string
              description: Human-readable reason (saved as notes on every transaction)
            tier_slug:
              type: string
              description: "Filter: only award users currently on this tier (e.g. flame, blaze, holy)"
            last_order_before:
              type: string
              format: date-time
              description: "Filter: only users whose last order was BEFORE this ISO datetime (win-back)"
            last_order_after:
              type: string
              format: date-time
              description: "Filter: only users whose last order was AFTER this ISO datetime (reward active)"
            user_ids:
              type: array
              items:
                type: string
              description: "Explicit list of user IDs — overrides all other filters"
            dry_run:
              type: boolean
              description: "If true, return matched user count/IDs without actually awarding HP"
    responses:
      200:
        description: Bulk grant result
      400:
        description: Validation error
    """
    from app.services.hp_service import award_active_hp

    db = get_db()
    data = request.get_json(force=True) or {}

    amount = data.get("amount")
    reason = data.get("reason", "").strip()
    dry_run = bool(data.get("dry_run", False))

    if not amount or int(amount) <= 0:
        return jsonify({"error": MSG.ADMIN_AMOUNT_POSITIVE}), 400
    if not reason:
        return jsonify({"error": MSG.ADMIN_REASON_REQUIRED}), 400

    amount = int(amount)

    # ── Build the user list ──────────────────────────────────────────────────
    explicit_ids = data.get("user_ids")
    if explicit_ids:
        # Explicit list — validate they're real users
        profiles = (
            db.table("profiles")
            .select("id,full_name,current_tier_id")
            .in_("id", explicit_ids)
            .eq("is_active", True)
            .execute()
        ) or []
    else:
        # Start from all active users
        query = db.table("profiles").select("id,full_name,current_tier_id").eq("is_active", True)

        tier_slug = data.get("tier_slug")
        if tier_slug:
            tier_row = (
                db.table("hp_tiers")
                .select("id")
                .eq("slug", tier_slug.lower())
                .single()
                .execute()
            )
            if not tier_row:
                return jsonify({"error": MSG.ADMIN_TIER_NOT_FOUND.format(slug=tier_slug)}), 400
            query = query.eq("current_tier_id", tier_row["id"])

        profiles = query.execute() or []

        # Last-order date filters: applied in Python against orders table
        last_order_before = data.get("last_order_before")
        last_order_after = data.get("last_order_after")

        if last_order_before or last_order_after:
            user_ids_after_filter = []
            for p in profiles:
                uid = p["id"]
                q2 = (
                    db.table("orders")
                    .select("created_at")
                    .eq("user_id", uid)
                    .order("created_at", ascending=False)
                    .limit(1)
                    .execute()
                )
                last_order_date = q2[0]["created_at"] if q2 else None

                if last_order_before:
                    if not last_order_date or last_order_date >= last_order_before:
                        continue
                if last_order_after:
                    if not last_order_date or last_order_date <= last_order_after:
                        continue
                user_ids_after_filter.append(p)
            profiles = user_ids_after_filter

    if dry_run:
        return jsonify({
            "dry_run": True,
            "matched_count": len(profiles),
            "matched_user_ids": [p["id"] for p in profiles],
            "amount_per_user": amount,
            "total_hp_to_award": amount * len(profiles),
            "reason": reason,
        }), 200

    # ── Award HP to each matched user ────────────────────────────────────────
    awarded_ids = []
    failed_ids = []
    for p in profiles:
        uid = p["id"]
        try:
            award_active_hp(
                user_id=uid,
                amount=amount,
                txn_type="earn",
                reference_id=g.user_id,
                reference_type="admin_grant",
                source_type="admin_grant",
                notes=f"Bulk grant: {reason}",
                issued_by_admin_id=g.user_id,
            )
            awarded_ids.append(uid)
        except Exception as exc:
            failed_ids.append({"user_id": uid, "error": str(exc)})

    _audit(g.user_id, "profiles", "bulk", "bulk_hp_grant", {
        "amount": amount,
        "reason": reason,
        "awarded_count": len(awarded_ids),
        "failed_count": len(failed_ids),
    })

    return jsonify({
        "awarded_count": len(awarded_ids),
        "failed_count": len(failed_ids),
        "amount_per_user": amount,
        "total_hp_awarded": amount * len(awarded_ids),
        "reason": reason,
        "failed": failed_ids,
    }), 200


@admin_bp.route("/hp/report", methods=["GET"])
@require_role("admin")
def hp_report():
    """
    HP loyalty program health report — totals, tier distribution, top earners.
    ---
    tags: [Admin]
    responses:
      200:
        description: HP program metrics
    """
    db = get_db()

    issued_rows = db.table("hp_transactions").select("amount").gt("amount", 0).execute() or []
    spent_rows  = db.table("hp_transactions").select("amount").lt("amount", 0).execute() or []
    total_issued = sum(int(r.get("amount", 0)) for r in issued_rows)
    total_spent  = abs(sum(int(r.get("amount", 0)) for r in spent_rows))

    today = datetime.now(timezone.utc).date().isoformat()
    issued_today_rows = (
        db.table("hp_transactions")
        .select("amount")
        .gt("amount", 0)
        .gte("created_at", f"{today}T00:00:00Z")
        .execute()
    ) or []
    issued_today = sum(int(r.get("amount", 0)) for r in issued_today_rows)

    tier_rows = db.table("profiles").select("current_tier_id").execute() or []
    tier_counts = {}
    for r in tier_rows:
        tid = r.get("current_tier_id") or "none"
        tier_counts[tid] = tier_counts.get(tid, 0) + 1

    top_rows = (
        db.table("profiles")
        .select("id,full_name,hp_balance,current_tier_id")
        .order("hp_balance", ascending=False)
        .limit(10)
        .execute()
    ) or []

    return jsonify({
        "total_hp_issued":   total_issued,
        "total_hp_spent":    total_spent,
        "net_hp_in_system":  total_issued - total_spent,
        "hp_issued_today":   issued_today,
        "users_by_tier":     tier_counts,
        "top_earners":       top_rows,
    }), 200


def _audit(actor_id, table, target_id, action, after_data=None):
    db = get_db()
    try:
        db.table("admin_audit_logs").insert({
            "actor_id": actor_id,
            "actor_role": "admin",
            "entity_type": table,
            "entity_id": target_id,
            "action": action,
            "after_value": after_data,
        })
    except Exception:
        pass
