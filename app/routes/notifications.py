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
        q = q.eq("is_read", "false")

    notifications = q.order("created_at", ascending=False).limit(limit).execute()

    unread_count_rows = (
        db.table("notifications")
        .select("id")
        .eq("user_id", g.user_id)
        .eq("channel", "in_app")
        .eq("is_read", "false")
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
    db.table("notifications").eq("user_id", g.user_id).eq("channel", "in_app").eq("is_read", "false").update({
        "is_read": True,
        "read_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": "All notifications marked as read"}), 200


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
    data["is_sent"] = False
    blast = db.table("notification_blasts").insert(data)
    blast_row = blast[0] if isinstance(blast, list) else blast

    if not data.get("send_at"):
        result = send_blast(blast_row["id"])
        return jsonify({"blast": blast_row, "sent_to": result["sent_to"]}), 201

    return jsonify({"blast": blast_row, "message": "Blast scheduled"}), 201
