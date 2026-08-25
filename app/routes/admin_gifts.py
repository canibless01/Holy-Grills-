"""
Admin Gift routes — manage first-order hot dog gifts and system settings.

GET    /admin/gifts/first-order          — list pending/all first-order gifts
PATCH  /admin/gifts/first-order/<id>     — update gift status (fulfil/cancel)
GET    /admin/settings                   — list all system settings
PATCH  /admin/settings/<key>             — update a system setting
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.db import get_db, get_user_client
from app.messages import MSG
from datetime import datetime, timezone

admin_gifts_bp = Blueprint("admin_gifts", __name__)


@admin_gifts_bp.route("/first-order-gifts", methods=["GET"])
@require_role("admin")
def list_first_order_gifts():
    """
    Admin: list first-order gifts with user details.
    ---
    tags: [Admin - Gifts]
    parameters:
      - in: query
        name: status
        type: string
        description: Filter by status (pending, fulfilled, cancelled, claimed, redeemed, returned). Default all.
    responses:
      200:
        description: List of first-order gifts
    """
    db = get_user_client()
    q = (
        db.table("first_order_gifts")
        .select("*,profiles(full_name,email,phone),orders(id,total_amount,created_at)")
    )
    campus_id = request.args.get("campus_id") or getattr(g, 'campus_id', None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    gifts = q.order("created_at", ascending=False).execute() or []
    return jsonify({"gifts": gifts, "count": len(gifts)}), 200


@admin_gifts_bp.route("/first-order-gifts/<gift_id>", methods=["PATCH"])
@require_role("admin")
def update_first_order_gift(gift_id):
    """
    Admin: update a first-order gift status.
    ---
    tags: [Admin - Gifts]
    parameters:
      - in: path
        name: gift_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string, enum: [fulfilled, cancelled, claimed, redeemed, returned]}
    responses:
      200:
        description: Gift updated
      400:
        description: Invalid status
      404:
        description: Gift not found
    """
    db = get_user_client()
    gift = (
        db.table("first_order_gifts")
        .select("id,status")
        .eq("id", gift_id)
        .single()
        .execute()
    )
    if not gift:
        return jsonify({"error": MSG.GIFT_NOT_FOUND}), 404

    data = request.get_json(force=True) or {}
    new_status = (data.get("status") or "").strip()
    if new_status not in ("fulfilled", "cancelled", "claimed", "redeemed", "returned"):
        return jsonify({"error": MSG.GIFT_INVALID_STATUS}), 400

    update_payload = {"status": new_status}

    db.table("first_order_gifts").eq("id", gift_id).update(update_payload)
    return jsonify({"message": MSG.GIFT_UPDATED, "status": new_status}), 200


# ── System Settings ───────────────────────────────────────────────────────────

def require_super_admin_for_settings_write(g, jsonify):
    """Insert at the top of any system_settings admin-write route."""
    if g.user_role != "super_admin":
        return jsonify({"error": "Only super_admin may modify system settings"}), 403
    return None  # proceed


def read_global_setting(db, key):
    """Global keys now have campus_id IS NULL — query explicitly for that,
    don't assume a row always has a campus_id."""
    return db.table("system_settings").select("*").eq("key", key).is_("campus_id", "null").single().execute()


def read_percampus_setting(db, key, campus_id):
    return db.table("system_settings").select("*").eq("key", key).eq("campus_id", campus_id).single().execute()


@admin_gifts_bp.route("/settings", methods=["GET"])
@require_role("admin")
def list_settings():
    """
    Admin: list all system settings.
    ---
    tags: [Admin - Settings]
    responses:
      200:
        description: All system settings
    """
    db = get_user_client()
    settings = db.table("system_settings").select("*").order("key").execute() or []
    return jsonify({"settings": settings, "count": len(settings)}), 200


@admin_gifts_bp.route("/settings/<key>", methods=["PATCH"])
@require_role("admin")
def update_setting(key):
    auth_err = require_super_admin_for_settings_write(g, jsonify)
    if auth_err:
        return auth_err
    db = get_user_client()
    data = request.get_json(force=True) or {}
    campus_id = data.get("campus_id")

    if campus_id:
        existing = read_percampus_setting(db, key, campus_id)
    else:
        existing = read_global_setting(db, key)

    if not existing:
        return jsonify({"error": MSG.SETTING_NOT_FOUND}), 404

    value = data.get("value")
    if value is None:
        return jsonify({"error": MSG.SETTING_VALUE_REQUIRED}), 400
    if key == "hp_multiplier":
        try:
            if float(str(value)) not in (0.5, 1.0, 2.0):
                return jsonify({"error": "hp_multiplier must be 0.5, 1.0, or 2.0"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "hp_multiplier must be 0.5, 1.0, or 2.0"}), 400

    update_payload = {
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": g.user_id,
    }
    if "description" in data:
        update_payload["description"] = data["description"]

    q = db.table("system_settings").eq("key", key)
    q = q.is_("campus_id", "null") if not campus_id else q.eq("campus_id", campus_id)
    q.update(update_payload)

    # When hp_multiplier is set above 1, broadcast to all active users immediately
    if key == "hp_multiplier":
        try:
            mult_val = float(str(value))
            if mult_val > 1.0:
                _broadcast_multiplier_event(db, mult_val)
        except Exception:
            pass  # non-critical — setting is saved regardless

    return jsonify({"message": MSG.SETTING_UPDATED, "key": key, "value": str(value)}), 200


def _broadcast_multiplier_event(db, multiplier: float):
    """Send a push + in-app notification to all active users when a multiplier event goes live."""
    try:
        from app.services.notification_service import send_notification
        from app.messages import MSG
        users = db.table("profiles").select("id").eq("is_active", True).execute() or []
        for user in users:
            try:
                send_notification(
                    user_id=user["id"],
                    notif_type="multiplier_live",
                    title=MSG.MULTIPLIER_LIVE_TITLE,
                    body=MSG.MULTIPLIER_LIVE_BODY.format(multiplier=multiplier),
                    channels=["push", "in_app"],
                )
            except Exception:
                pass
    except Exception:
        pass


@admin_gifts_bp.route("/settings", methods=["POST"])
@require_role("admin")
def create_setting():
    auth_err = require_super_admin_for_settings_write(g, jsonify)
    if auth_err:
        return auth_err
    db = get_user_client()
    data = request.get_json(force=True) or {}
    key = (data.get("key") or "").strip()
    value = data.get("value")
    campus_id = data.get("campus_id")
    if not key or value is None:
        return jsonify({"error": MSG.SETTING_KEY_VALUE_REQUIRED}), 400

    existing = read_percampus_setting(db, key, campus_id) if campus_id else read_global_setting(db, key)
    if existing:
        return jsonify({"error": MSG.SETTING_KEY_EXISTS}), 409

    now = datetime.now(timezone.utc).isoformat()
    result = db.table("system_settings").insert({
        "key": key,
        "value": value,
        "description": data.get("description", ""),
        "campus_id": campus_id,
        "updated_at": now,
        "updated_by": g.user_id,
    })
    row = result[0] if isinstance(result, list) else result
    return jsonify({"message": MSG.SETTING_CREATED, "setting": row}), 201
