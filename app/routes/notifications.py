"""Notification routes — in-app inbox, mark read, admin blasts."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.notification_service import send_blast
from app.db import get_db
from datetime import datetime, timezone

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("", methods=["GET"])
@require_auth
def my_notifications():
    """
    Get authenticated user's notification inbox.
    ---
    tags: [Notifications]
    parameters:
      - in: query
        name: unread_only
        type: boolean
        default: false
      - in: query
        name: limit
        type: integer
        default: 30
    responses:
      200:
        description: Notification list with unread count
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 30)), 100)
    q = db.table("notifications").select("*").eq("user_id", g.user_id).eq("channel", "in_app")

    unread_only = request.args.get("unread_only", "false").lower() == "true"
    if unread_only:
        q = q.is_("read_at", "null")

    notifications = q.order("created_at", ascending=False).limit(limit).execute()

    unread_count_rows = (
        db.table("notifications")
        .select("id")
        .eq("user_id", g.user_id)
        .eq("channel", "in_app")
        .is_("read_at", "null")
        .execute()
    )

    return jsonify({
        "notifications": notifications,
        "unread_count": len(unread_count_rows),
    }), 200


@notifications_bp.route("/<notification_id>/read", methods=["POST"])
@require_auth
def mark_read(notification_id):
    """
    Mark a notification as read.
    ---
    tags: [Notifications]
    parameters:
      - in: path
        name: notification_id
        type: string
        required: true
    responses:
      200:
        description: Marked as read
    """
    from app.services.notification_service import mark_read as _mark_read
    result = _mark_read(notification_id, g.user_id)
    return jsonify(result), 200


@notifications_bp.route("/read-all", methods=["POST"])
@require_auth
def mark_all_read():
    """
    Mark all in-app notifications as read.
    ---
    tags: [Notifications]
    responses:
      200:
        description: All marked as read
    """
    db = get_db()
    db.table("notifications").eq("user_id", g.user_id).eq("channel", "in_app").is_("read_at", "null").update({
        "read_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": "All notifications marked as read"}), 200


@notifications_bp.route("/device", methods=["POST"])
@require_auth
def register_device():
    """
    Register a device push token (OneSignal player/subscription ID).
    Call this after the user grants push permission in the app.
    ---
    tags: [Notifications]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [token]
          properties:
            token: {type: string, description: "OneSignal player_id or subscription_id"}
            platform: {type: string, enum: [ios, android, web], description: "Device platform"}
            device_model: {type: string}
    responses:
      200:
        description: Token registered or updated
      201:
        description: Token registered (new)
    """
    db = get_db()
    data = request.get_json(force=True)
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"error": "'token' is required"}), 400

    record = {
        "user_id": g.user_id,
        "token": token,
        "platform": data.get("platform", "unknown"),
        "device_model": data.get("device_model"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        existing = (
            db.table("device_tokens")
            .select("id")
            .eq("user_id", g.user_id)
            .eq("token", token)
            .single()
            .execute()
        )

        if existing:
            db.table("device_tokens").eq("id", existing["id"]).update(record)
            return jsonify({"message": "Device token updated", "token": token}), 200
        else:
            record["created_at"] = datetime.now(timezone.utc).isoformat()
            db.table("device_tokens").insert(record)
            return jsonify({"message": "Device token registered", "token": token}), 201
    except Exception as exc:
        err = str(exc)
        if "does not exist" in err or "schema cache" in err or "relation" in err:
            return jsonify({"message": "Device token registered", "token": token, "note": "push notifications not yet provisioned"}), 201
        raise


@notifications_bp.route("/preferences", methods=["GET"])
@require_auth
def get_preferences():
    """
    Get the authenticated user's notification preferences.
    ---
    tags: [Notifications]
    responses:
      200:
        description: Notification preference settings
    """
    db = get_db()
    prefs = (
        db.table("notification_preferences")
        .select("*")
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )

    if not prefs:
        prefs = {
            "user_id": g.user_id,
            "push_enabled": True,
            "email_enabled": True,
            "order_updates": True,
            "promotions": True,
            "hp_updates": True,
            "delivery_updates": True,
        }

    return jsonify(prefs), 200


@notifications_bp.route("/preferences", methods=["PATCH"])
@require_auth
def update_preferences():
    """
    Update the authenticated user's notification preferences.
    ---
    tags: [Notifications]
    parameters:
      - in: body
        name: body
        schema:
          properties:
            push_enabled: {type: boolean}
            email_enabled: {type: boolean}
            order_updates: {type: boolean}
            promotions: {type: boolean}
            hp_updates: {type: boolean}
            delivery_updates: {type: boolean}
    responses:
      200:
        description: Preferences updated
    """
    db = get_db()
    data = request.get_json(force=True)
    allowed = {"push_enabled", "email_enabled", "order_updates", "promotions", "hp_updates", "delivery_updates"}
    update = {k: bool(v) for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"error": "No valid preference fields provided"}), 400

    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        existing = (
            db.table("notification_preferences")
            .select("id")
            .eq("user_id", g.user_id)
            .single()
            .execute()
        )

        if existing:
            db.table("notification_preferences").eq("user_id", g.user_id).update(update)
        else:
            defaults = {
                "user_id": g.user_id,
                "push_enabled": True,
                "email_enabled": True,
                "order_updates": True,
                "promotions": True,
                "hp_updates": True,
                "delivery_updates": True,
            }
            defaults.update(update)
            db.table("notification_preferences").insert(defaults)

        result = (
            db.table("notification_preferences")
            .select("*")
            .eq("user_id", g.user_id)
            .single()
            .execute()
        )
        return jsonify(result), 200
    except Exception as exc:
        err = str(exc)
        if "does not exist" in err or "schema cache" in err or "relation" in err:
            merged = {
                "user_id": g.user_id,
                "push_enabled": True,
                "email_enabled": True,
                "order_updates": True,
                "promotions": True,
                "hp_updates": True,
                "delivery_updates": True,
            }
            merged.update({k: v for k, v in update.items() if k != "updated_at"})
            return jsonify(merged), 200
        raise


@notifications_bp.route("/blasts", methods=["POST"])
@require_role("admin")
def create_blast():
    """
    Create and optionally send a notification blast (admin only).
    ---
    tags: [Notifications]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, body, channels]
          properties:
            title: {type: string}
            body: {type: string}
            channels: {type: array, items: {type: string, enum: [in_app, email, push]}}
            target_segment: {type: object, description: "Optional: tier_id, etc."}
            send_at: {type: string, format: date-time, description: "If omitted, sends immediately"}
    responses:
      201:
        description: Blast created and sent
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["title", "body", "channels"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400

    data["created_by"] = g.user_id
    data["status"] = "pending"
    if "target_segment" in data:
        data["segment"] = data.pop("target_segment")
    if "send_at" in data:
        data["scheduled_at"] = data.pop("send_at")
    blast = db.table("notification_blasts").insert(data)
    blast_row = blast[0] if isinstance(blast, list) else blast

    if not data.get("scheduled_at"):
        result = send_blast(blast_row["id"])
        return jsonify({"blast": blast_row, "sent_to": result["sent_to"]}), 201

    return jsonify({"blast": blast_row, "message": "Blast scheduled"}), 201
