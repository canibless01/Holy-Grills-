"""Admin panel routes — users, orders, delivery windows, promo codes, audit log."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.services.notification_service import send_notification
from app.db import get_db
from datetime import datetime, timezone

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

    q = db.table("profiles").select("id,full_name,phone,role,is_active,created_at,referral_code,monthly_hp_earned,hp_earned_120day")
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
        return jsonify({"error": "User not found"}), 404

    from app.services.hp_service import get_hp_balance, get_user_tier
    balance = get_hp_balance(user_id)
    tier = get_user_tier(user_id)
    wallet = db.table("wallets").select("balance").eq("user_id", user_id).single().execute()
    recent_orders = (
        db.table("orders")
        .select("id,status,total,created_at")
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
    return jsonify({"message": "User deactivated"}), 200


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
    windows = db.table("delivery_windows").select("*").order("opens_at", ascending=False).limit(50).execute()
    for w in windows:
        orders = db.table("orders").select("id").eq("delivery_window_id", w["id"]).execute()
        w["order_count"] = len(orders)
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
          required: [label, opens_at, closes_at]
          properties:
            label: {type: string}
            opens_at: {type: string, format: date-time}
            closes_at: {type: string, format: date-time}
    responses:
      201:
        description: Window created
    """
    db = get_db()
    data = request.get_json(force=True)
    data["status"] = "open"
    data["created_by"] = g.user_id
    result = db.table("delivery_windows").insert(data)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@admin_bp.route("/delivery-windows/<window_id>/close", methods=["POST"])
@require_role("admin")
def close_window(window_id):
    """
    Close a delivery window and trigger batch creation (admin only).
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
    db.table("delivery_windows").eq("id", window_id).update({
        "status": "closed",
        "modified_by": g.user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    _audit(g.user_id, "delivery_windows", window_id, "close_window")
    return jsonify({"message": "Window closed"}), 200


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
    data = request.get_json(force=True)
    batch = db.table("delivery_batches").insert({
        "window_id": data["window_id"],
        "rider_id": data["rider_id"],
        "zone": data.get("zone", ""),
        "status": "assigned",
        "assigned_at": datetime.now(timezone.utc).isoformat(),
    })
    batch_row = batch[0] if isinstance(batch, list) else batch
    batch_id = batch_row["id"]

    for order_id in data.get("order_ids", []):
        db.table("orders").eq("id", order_id).update({"batch_id": batch_id})

    return jsonify(batch_row), 201


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
            return jsonify({"error": f"'{f}' is required"}), 400
    data["code"] = data["code"].upper()
    data["used_count"] = 0
    data["is_active"] = True
    data["created_by"] = g.user_id
    result = db.table("promo_codes").insert(data)
    return jsonify(result[0] if isinstance(result, list) else result), 201


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
        return jsonify({"error": "Cart not found or guest cart"}), 404

    send_notification(
        user_id=cart["user_id"],
        notif_type="abandoned_cart",
        title="You left something behind!",
        body="Your cart is still waiting — and so is your HP. Complete your order today.",
        action_url="/cart",
        channels=["in_app", "email"],
    )
    db.table("abandoned_carts").eq("id", cart_id).update({
        "recovery_sent_count": (cart.get("recovery_sent_count") or 0) + 1,
        "last_recovery_sent_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": "Recovery nudge sent"}), 200


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
    logs = db.table("admin_audit_log").select("*").order("created_at", ascending=False).limit(limit).execute()
    return jsonify(logs), 200


def _audit(actor_id, table, target_id, action, after_data=None):
    db = get_db()
    try:
        db.table("admin_audit_log").insert({
            "actor_id": actor_id,
            "actor_role": "admin",
            "target_table": table,
            "target_id": target_id,
            "action": action,
            "after_data": after_data,
        })
    except Exception:
        pass
