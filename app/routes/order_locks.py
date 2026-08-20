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
from app.db import get_db, get_user_client, SupabaseError
from app.messages import MSG
from app.utils.settings import get_validated_setting, SettingError
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
    db = get_user_client()
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

    # Prevent users from having multiple active locks
    existing = db.table("order_locks").select("id").eq("user_id", g.user_id).eq("status", "active").execute()
    has_active = False
    if isinstance(existing, list) and len(existing) > 0:
        has_active = True
    elif isinstance(existing, dict) and existing.get("data"):
        has_active = True
    elif hasattr(existing, "data") and isinstance(existing.data, list) and len(existing.data) > 0:
        has_active = True

    if has_active:
        return jsonify({"error": "User already has an active lock"}), 400

    # reward_type: 'discount' (default) or 'hp'
    reward_type = (data.get("reward_type") or "discount").lower()
    if reward_type not in ("discount", "hp"):
        return jsonify({"error": "reward_type must be 'discount' or 'hp'"}), 400

    # Retrieve values strictly from system settings (client-provided values are strictly ignored)
    discount_pct = None
    reward_hp_amount = None

    try:
        if reward_type == "discount":
            # order_lock_default_discount: default 10.0
            discount_pct = get_validated_setting(
                db,
                "order_lock_default_discount",
                default=10.0,
                minimum=1.0,
                maximum=100.0,
                required=False
            )
        elif reward_type == "hp":
            # order_lock_max_hp setting
            max_hp_setting = get_validated_setting(
                db,
                "order_lock_max_hp",
                default=1000.0,
                minimum=1.0,
                maximum=10000.0,
                required=False
            )
            # order_lock_default_hp: default 100
            reward_hp_amount = int(get_validated_setting(
                db,
                "order_lock_default_hp",
                default=100,
                minimum=1,
                maximum=int(max_hp_setting),
                required=False
            ))
    except SettingError as e:
        return jsonify({"error": f"Configuration error: {str(e)}"}), 500

    now = datetime.now(timezone.utc).isoformat()
    campus_id = getattr(g, 'campus_id', None)
    insert_data = {
        "user_id": g.user_id,
        "locked_date": locked_date_str,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    if campus_id:
        insert_data["campus_id"] = campus_id
    if discount_pct is not None:
        insert_data["discount_pct"] = discount_pct
    if reward_hp_amount is not None:
        insert_data["reward_hp_amount"] = reward_hp_amount

    try:
        insert_data["reward_type"] = reward_type
        insert_data["reschedule_count"] = 0
        res = db.table("order_locks").insert(insert_data)
        result = res.execute() if hasattr(res, "execute") else res
    except SupabaseError as exc:
        err_msg = str(exc.details.get("message", "")) if exc.details else str(exc)
        if "uq_order_locks_one_active_per_user" in err_msg or "unique constraint" in err_msg.lower():
            return jsonify({"error": "User already has an active lock"}), 400
        is_missing_col = "column" in err_msg and "does not exist" in err_msg
        if is_missing_col:
            # Fallback: strip columns that may not exist yet in older schemas
            fallback = {k: v for k, v in insert_data.items()
                        if k not in ("reward_type", "reward_hp_amount", "reschedule_count")}
            res = db.table("order_locks").insert(fallback)
            result = res.execute() if hasattr(res, "execute") else res
        else:
            raise
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
    db = get_user_client()
    q = db.table("order_locks").select("*").eq("user_id", g.user_id)
    campus_id = getattr(g, 'campus_id', None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    locks = q.order("created_at", ascending=False).execute() or []
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
    db = get_user_client()
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
    db = get_user_client()
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
    }).execute()
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
    db = get_user_client()
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
    db.table("order_locks").eq("id", lock_id).update({"status": "cancelled", "updated_at": now}).execute()
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
    campus_id = request.args.get("campus_id") or getattr(g, "campus_id", None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
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
        row = db.table("system_settings").select("value").eq("key", key).is_("campus_id", "null").single().execute()
        return row.get("value", default) if row else default
    except Exception:
        return default
