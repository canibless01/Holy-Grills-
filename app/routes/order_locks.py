"""
Order Locks routes — lock-in a future order date with a discount.

POST   /order-locks                    — create a new lock
GET    /order-locks                    — list user's locks
GET    /order-locks/<id>               — get a specific lock
PATCH  /order-locks/<id>/reschedule    — reschedule locked date (once only)
DELETE /order-locks/<id>               — cancel a lock
GET    /admin/order-locks              — admin: list all active locks
GET    /admin/order-locks/pending-gifts — admin: list pending first-order gifts
"""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role
from app.db import get_db
from app.messages import MSG
from datetime import datetime, timezone, date, timedelta

order_locks_bp = Blueprint("order_locks", __name__)


@order_locks_bp.route("", methods=["POST"])
@require_auth
def create_lock():
    """
    Lock-in a future order date with a discount.
    ---
    tags: [Order Locks]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [locked_date]
          properties:
            locked_date: {type: string, format: date, description: "ISO date YYYY-MM-DD"}
            discount_pct: {type: number, description: "Discount 1-50%. Default 10."}
    responses:
      201:
        description: Lock created
      400:
        description: Validation error
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    locked_date_str = (data.get("locked_date") or "").strip()
    if not locked_date_str:
        return jsonify({"error": MSG.ORDER_LOCK_DATE_REQUIRED}), 400

    try:
        locked_date = date.fromisoformat(locked_date_str)
    except ValueError:
        return jsonify({"error": MSG.ORDER_LOCK_DATE_INVALID}), 400

    if locked_date <= date.today():
        return jsonify({"error": MSG.ORDER_LOCK_DATE_FUTURE}), 400

    # reward_type: 'discount' (default) or 'hp'; resolve BEFORE discount_pct so
    # validation can be skipped for the HP path.
    reward_type = (data.get("reward_type") or "discount").lower()
    if reward_type not in ("discount", "hp"):
        return jsonify({"error": "reward_type must be 'discount' or 'hp'"}), 400
    reward_hp_amount = None
    if reward_type == "hp":
        try:
            reward_hp_amount = int(data.get("reward_hp_amount") or 0)
        except (TypeError, ValueError):
            return jsonify({"error": "reward_hp_amount must be an integer when reward_type='hp'"}), 400
        if reward_hp_amount <= 0:
            return jsonify({"error": "reward_hp_amount must be positive when reward_type='hp'"}), 400

    # Only parse and validate discount_pct for the 'discount' reward type
    discount_pct = None
    if reward_type == "discount":
        max_discount = float(_get_setting(db, "order_lock_max_discount",
                                          str(current_app.config.get("ORDER_LOCK_MAX_DISCOUNT_PCT", 50))))
        default_discount = current_app.config.get("ORDER_LOCK_DEFAULT_DISCOUNT_PCT", 10.0)
        raw_discount = data.get("discount_pct", default_discount)
        try:
            discount_pct = float(raw_discount)
        except (TypeError, ValueError):
            return jsonify({"error": "discount_pct must be a number"}), 400
        if not (1 <= discount_pct <= max_discount):
            return jsonify({"error": MSG.ORDER_LOCK_DISCOUNT_RANGE.format(max=int(max_discount))}), 400

    now = datetime.now(timezone.utc).isoformat()
    insert_data = {
        "user_id": g.user_id,
        "locked_date": locked_date_str,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    if discount_pct is not None:
        insert_data["discount_pct"] = discount_pct
    if reward_hp_amount is not None:
        insert_data["reward_hp_amount"] = reward_hp_amount

    try:
        insert_data["reward_type"] = reward_type
        insert_data["reschedule_count"] = 0
        result = db.table("order_locks").insert(insert_data)
    except Exception:
        # Fallback: strip columns that may not exist yet in older schemas
        fallback = {k: v for k, v in insert_data.items()
                    if k not in ("reward_type", "reward_hp_amount", "reschedule_count")}
        result = db.table("order_locks").insert(fallback)
    row = result[0] if isinstance(result, list) else result
    return jsonify({"message": MSG.ORDER_LOCK_CREATED, "lock": row}), 201


@order_locks_bp.route("", methods=["GET"])
@require_auth
def list_locks():
    """
    List the authenticated user's order locks.
    ---
    tags: [Order Locks]
    parameters:
      - in: query
        name: status
        type: string
        description: Filter by status (active, used, expired, cancelled)
    responses:
      200:
        description: List of locks
    """
    db = get_db()
    q = (
        db.table("order_locks")
        .select("*")
        .eq("user_id", g.user_id)
        .order("created_at", ascending=False)
    )
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    locks = q.execute() or []
    return jsonify({"locks": locks, "count": len(locks)}), 200


@order_locks_bp.route("/<lock_id>", methods=["GET"])
@require_auth
def get_lock(lock_id):
    """
    Get a specific order lock.
    ---
    tags: [Order Locks]
    parameters:
      - in: path
        name: lock_id
        type: string
        required: true
    responses:
      200:
        description: Lock details
      404:
        description: Lock not found
    """
    db = get_db()
    lock = (
        db.table("order_locks")
        .select("*")
        .eq("id", lock_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not lock:
        return jsonify({"error": MSG.ORDER_LOCK_NOT_FOUND}), 404
    return jsonify({"lock": lock}), 200


@order_locks_bp.route("/<lock_id>/reschedule", methods=["PATCH"])
@require_auth
def reschedule_lock(lock_id):
    """
    Reschedule a locked order date. Allowed once only.
    ---
    tags: [Order Locks]
    parameters:
      - in: path
        name: lock_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [locked_date]
          properties:
            locked_date: {type: string, format: date}
    responses:
      200:
        description: Lock rescheduled
      400:
        description: Already rescheduled or date invalid
      404:
        description: Lock not found
    """
    db = get_db()
    lock = (
        db.table("order_locks")
        .select("*")
        .eq("id", lock_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not lock:
        return jsonify({"error": MSG.ORDER_LOCK_NOT_FOUND}), 404
    if lock.get("status") != "active":
        return jsonify({"error": MSG.ORDER_LOCK_NOT_ACTIVE}), 400
    max_reschedules = current_app.config.get("ORDER_LOCK_MAX_RESCHEDULES", 1)
    if int(lock.get("reschedule_count", 0)) >= max_reschedules:
        return jsonify({"error": MSG.ORDER_LOCK_RESCHEDULE_LIMIT}), 400

    data = request.get_json(force=True) or {}
    new_date_str = (data.get("locked_date") or "").strip()
    if not new_date_str:
        return jsonify({"error": MSG.ORDER_LOCK_DATE_REQUIRED}), 400
    try:
        new_date = date.fromisoformat(new_date_str)
    except ValueError:
        return jsonify({"error": MSG.ORDER_LOCK_DATE_INVALID}), 400
    if new_date <= date.today():
        return jsonify({"error": MSG.ORDER_LOCK_DATE_FUTURE}), 400

    now = datetime.now(timezone.utc).isoformat()
    new_reschedule_count = int(lock.get("reschedule_count", 0)) + 1
    updated = db.table("order_locks").eq("id", lock_id).update({
        "locked_date": new_date_str,
        "reschedule_count": new_reschedule_count,
        "updated_at": now,
    })
    row = updated[0] if isinstance(updated, list) else updated
    return jsonify({"message": MSG.ORDER_LOCK_RESCHEDULED, "lock": row}), 200


@order_locks_bp.route("/<lock_id>", methods=["DELETE"])
@require_auth
def cancel_lock(lock_id):
    """
    Cancel an active order lock.
    ---
    tags: [Order Locks]
    parameters:
      - in: path
        name: lock_id
        type: string
        required: true
    responses:
      200:
        description: Lock cancelled
      400:
        description: Lock is not active
      404:
        description: Lock not found
    """
    db = get_db()
    lock = (
        db.table("order_locks")
        .select("id,status")
        .eq("id", lock_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not lock:
        return jsonify({"error": MSG.ORDER_LOCK_NOT_FOUND}), 404
    if lock.get("status") != "active":
        return jsonify({"error": MSG.ORDER_LOCK_NOT_ACTIVE}), 400

    now = datetime.now(timezone.utc).isoformat()
    db.table("order_locks").eq("id", lock_id).update({"status": "cancelled", "updated_at": now})
    return jsonify({"message": MSG.ORDER_LOCK_CANCELLED}), 200


# ── Admin endpoints ───────────────────────────────────────────────────────────

@order_locks_bp.route("/admin/all", methods=["GET"])
@require_auth
@require_role("admin")
def admin_list_locks():
    """
    Admin: list all order locks with filters.
    ---
    tags: [Order Locks]
    parameters:
      - in: query
        name: status
        type: string
      - in: query
        name: date
        type: string
        description: Filter by locked_date (ISO date)
    responses:
      200:
        description: All locks
    """
    db = get_db()
    q = (
        db.table("order_locks")
        .select("*,profiles(full_name,email,phone)")
        .order("locked_date", ascending=True)
    )
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    date_filter = request.args.get("date")
    if date_filter:
        q = q.eq("locked_date", date_filter)
    locks = q.execute() or []
    return jsonify({"locks": locks, "count": len(locks)}), 200


def _get_setting(db, key: str, default: str = "") -> str:
    try:
        row = db.table("system_settings").select("value").eq("key", key).single().execute()
        return row.get("value", default) if row else default
    except Exception:
        return default
