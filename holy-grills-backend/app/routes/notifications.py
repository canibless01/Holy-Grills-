from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role, resolve_scoped_campus_id
from app.services.notification_service import send_blast, resolve_segment_user_ids
from app.db import get_user_client, SupabaseError
from app.utils.validators import validate_uuid
from app.utils.campus_scope import assert_can_modify
from app.db import get_db
from app.messages import MSG
from app.utils.logger import get_logger
from datetime import datetime, timezone
from app.utils.campus_scope import resolve_write_campus
from app.utils.admin_helpers import as_instant

logger = get_logger(__name__)

notifications_bp = Blueprint("notifications", __name__)

# Separate blueprint (still defined in this file, per project convention of not
# creating new route files) so it can be mounted at its own "/api/push" prefix.
push_bp = Blueprint("push", __name__)


@push_bp.route("/subscribe", methods=["POST"])
@require_auth
def push_subscribe():
    """
    Register a browser Web Push subscription for the authenticated user.
    ---
    tags: [Notifications]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [subscription]
          properties:
            subscription:
              type: object
              description: Web Push subscription object (endpoint, keys.p256dh, keys.auth)
            device_label:
              type: string
              description: Human-readable label, e.g. "Chrome on Windows"
    responses:
      201:
        description: Subscription registered
      200:
        description: Subscription updated
      400:
        description: subscription field missing
    """
    db = get_user_client()
    data = request.get_json(force=True) or {}
    subscription = data.get("subscription")
    if not subscription:
        return jsonify({"error": MSG.PUSH_SUBSCRIPTION_REQUIRED}), 400

    now = datetime.now(timezone.utc).isoformat()
    endpoint = subscription.get("endpoint") if isinstance(subscription, dict) else None

    existing = None
    if endpoint:
        rows = (
            db.table("push_subscriptions")
            .select("id,subscription")
            .eq("user_id", g.user_id)
            .execute()
        ) or []
        for row in rows:
            sub = row.get("subscription") or {}
            if isinstance(sub, dict) and sub.get("endpoint") == endpoint:
                existing = row
                break

    record = {
        "user_id": g.user_id,
        "subscription": subscription,
        "device_label": data.get("device_label"),
        "is_active": True,
        "updated_at": now,
    }
    campus_id = getattr(g, "campus_id", None)
    if campus_id:
        record["campus_id"] = campus_id

    try:
        if existing:
            result = db.table("push_subscriptions").eq("id", existing["id"]).update(record)
        else:
            record["created_at"] = now
            result = db.table("push_subscriptions").insert(record)
        row = result[0] if isinstance(result, list) and result else (result if isinstance(result, dict) else None)
        return jsonify(row if row else {"message": MSG.NOTIF_TOKEN_REGISTERED}), 200
    except Exception:
        logger.exception("push_subscribe failed for user %s", g.user_id)
        return jsonify({"error": MSG.PUSH_SUBSCRIPTION_FAILED}), 500


@push_bp.route("/subscribe", methods=["DELETE"])
@require_auth
def push_unsubscribe():
    """
    Deactivate all Web Push subscriptions for the authenticated user (or one endpoint).
    ---
    tags: [Notifications]
    parameters:
      - in: body
        name: body
        schema:
          properties:
            endpoint:
              type: string
              description: Optional — only unsubscribe this specific push endpoint
    responses:
      200:
        description: Subscription(s) deactivated
    """
    db = get_user_client()
    data = request.get_json(force=True) or {}
    endpoint = data.get("endpoint")

    rows = (
        db.table("push_subscriptions")
        .select("id,subscription")
        .eq("user_id", g.user_id)
        .execute()
    ) or []

    removed = 0
    for row in rows:
        sub = row.get("subscription") or {}
        if endpoint and isinstance(sub, dict) and sub.get("endpoint") != endpoint:
            continue
        db.table("push_subscriptions").eq("id", row["id"]).update({
            "is_active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        removed += 1

    return jsonify({"message": MSG.PUSH_UNSUBSCRIBED, "removed": removed}), 200


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
    db = get_user_client()
    try:
        limit = max(1, min(int(request.args.get("limit", 30)), 100))
    except (TypeError, ValueError):
        return jsonify({"error": MSG.PAGINATION_INVALID}), 400
    q = db.table("notifications").select("*").eq("user_id", g.user_id).eq("channel", "in_app")

    unread_only = request.args.get("unread_only", "false").lower() == "true"
    if unread_only:
        q = q.is_("read_at", "null")

    notifications = q.order("created_at", ascending=False).limit(limit).execute()

    count_q = (
        db.table("notifications")
        .select("id")
        .eq("user_id", g.user_id)
        .eq("channel", "in_app")
        .is_("read_at", "null")
    )
    unread_count_rows = count_q.execute()

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
    if result is None:
        return jsonify({"error": MSG.NOTIFICATION_NOT_FOUND}), 404
    result["message"] = MSG.NOTIFICATION_MARKED_READ
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
    db = get_user_client()
    db.table("notifications").eq("user_id", g.user_id).eq("channel", "in_app").is_("read_at", "null").update({
        "read_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return jsonify({"message": MSG.NOTIF_ALL_READ}), 200


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
    db = get_user_client()
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
    db = get_user_client()
    data = request.get_json(force=True, silent=True)
    allowed = {"push_enabled", "email_enabled", "order_updates", "promotions", "hp_updates", "delivery_updates"}
    if not isinstance(data, dict) or any(not isinstance(v, bool) for k, v in data.items() if k in allowed):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"error": MSG.NOTIF_NO_VALID_PREFS}), 400

    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        # Database defaults initialize a new row; PATCH must not reset any
        # existing opt-out that this request did not mention.
        db.table("notification_preferences").upsert({"user_id": g.user_id, **update}, on_conflict="user_id").execute()

        result = (
            db.table("notification_preferences")
            .select("*")
            .eq("user_id", g.user_id)
            .single()
            .execute()
        )
        if isinstance(result, dict):
            result["message"] = MSG.NOTIFICATION_PREFERENCES_UPDATED
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("Notification preference save failed for %s", g.user_id)
        return jsonify({"error": MSG.SERVICE_UNAVAILABLE}), 503


@notifications_bp.route("/blasts", methods=["GET"])
@require_role("admin")
def list_blasts():
    """
    List notification blast history (admin only).
    ---
    tags: [Notifications]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, sent, failed]
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
        description: Blast history
    """
    db = get_user_client()
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 200))
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": MSG.PAGINATION_INVALID}), 400
    q = db.table("notification_blasts").select("*")
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
    if campus_id:
        q = q.eq("campus_id", campus_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"blasts": rows, "count": len(rows)}), 200


@notifications_bp.route("/blasts/<blast_id>", methods=["GET"])
@require_role("admin")
def get_blast(blast_id):
    """
    Get a single notification blast's detail (admin only).
    ---
    tags: [Notifications]
    parameters:
      - in: path
        name: blast_id
        type: string
        required: true
    responses:
      200:
        description: Blast detail
      404:
        description: Blast not found
    """
    db = get_user_client()
    blast = db.table("notification_blasts").select("*").eq("id", blast_id).limit(1).execute()
    blast = blast[0] if blast else None
    if not blast:
        return jsonify({"error": MSG.NOTIF_BLAST_NOT_FOUND}), 404
    # A campus admin only sees their own campus's blasts, same scoping list_blasts applies;
    # a super_admin (resolve_scoped_campus_id returns None with no arg) sees any.
    campus_id = resolve_scoped_campus_id(None)
    if campus_id and blast.get("campus_id") and blast["campus_id"] != campus_id:
        return jsonify({"error": MSG.NOTIF_BLAST_NOT_FOUND}), 404
    return jsonify(blast), 200


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
    db = get_user_client()
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    required = ["title", "body", "channels"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400

    if (not isinstance(data["title"], str) or not data["title"].strip() or len(data["title"]) > 200
            or not isinstance(data["body"], str) or not data["body"].strip() or len(data["body"]) > 10000
            or not isinstance(data["channels"], list) or not data["channels"]
            or any(c not in ("in_app", "email", "push") for c in data["channels"])):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    campus_id = resolve_write_campus(data.get("campus_id"))
    segment = data.get("target_segment", data.get("segment", {}))
    if not isinstance(segment, dict):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if campus_id:
        if any(segment.get(k) not in (None, "", campus_id) for k in ("campus", "campus_id")):
            return jsonify({"error": MSG.NOTIFICATION_BLAST_CAMPUS_DENIED}), 403
        segment = {**segment, "campus_id": campus_id}
    scheduled_at = data.get("send_at", data.get("scheduled_at"))
    request_id = data.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not validate_uuid(request_id)):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    email_provider = data.get("email_provider")
    if email_provider not in (None, "resend", "onesignal"):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if scheduled_at:
        try:
            scheduled_at = as_instant(scheduled_at)
            if datetime.fromisoformat(scheduled_at) <= datetime.now(timezone.utc):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": MSG.INVALID_INPUT}), 400
    # Never let clients supply receipts, recipient counts or worker status.
    data = {"title": data["title"].strip(), "body": data["body"].strip(),
            "channels": list(dict.fromkeys(data["channels"])), "segment": segment,
            "campus_id": campus_id, "created_by": g.user_id, "scheduled_at": scheduled_at,
            "email_provider": email_provider}
    if request_id:
        data["id"] = request_id

    if data.get("scheduled_at"):
        data["status"] = "scheduled"
    else:
        data["status"] = "pending"

    try:
        blast = db.table("notification_blasts").insert(data).execute()
    except SupabaseError as exc:
        if request_id and str((exc.details or {}).get("code")) == "23505":
            existing = db.table("notification_blasts").select("*").eq("id", request_id).single().execute()
            if existing and all(existing.get(k) == v for k, v in data.items() if k != "status"):
                return jsonify({"blast": existing, "already_created": True}), 200
            return jsonify({"error": MSG.INVALID_INPUT}), 409
        logger.exception("create_blast failed")
        return jsonify({"error": MSG.NOTIFICATION_BLAST_CREATE_FAILED}), 503
    except Exception as e:
        err_msg = str(getattr(e, "details", {}).get("message", "")) if hasattr(e, "details") and e.details else str(e)
        if "policy" in err_msg.lower() or "permission" in err_msg.lower() or "rls" in err_msg.lower():
            return jsonify({"error": MSG.NOTIFICATION_BLAST_CAMPUS_DENIED}), 403
        logger.exception("create_blast failed")
        return jsonify({"error": MSG.NOTIFICATION_BLAST_CREATE_FAILED}), 500
    blast_row = blast[0] if isinstance(blast, list) else blast

    if not data.get("scheduled_at"):
        result = send_blast(blast_row["id"])
        return jsonify({"blast": blast_row, "sent_to": result["sent_to"]}), 201

    return jsonify({"blast": blast_row, "message": "Blast scheduled"}), 201


@notifications_bp.route("/blasts/<blast_id>/cancel", methods=["POST"])
@require_role("admin")
def cancel_blast(blast_id):
    db = get_user_client()
    row = db.table("notification_blasts").select("*").eq("id", blast_id).single().execute()
    if not row:
        return jsonify({"error": MSG.NOTIF_BLAST_NOT_FOUND}), 404
    assert_can_modify(row.get("campus_id"))
    if row.get("status") == "cancelled":
        return jsonify(row), 200
    if row.get("status") not in ("scheduled", "pending"):
        return jsonify({"error": MSG.BLAST_CANCELLATION_TOO_LATE}), 409
    updated = db.table("notification_blasts").eq("id", blast_id).eq("status", row["status"]).update({"status": "cancelled"})
    if not updated:
        return jsonify({"error": MSG.BLAST_CANCELLATION_TOO_LATE}), 409
    return jsonify(updated[0] if isinstance(updated, list) else updated), 200


@notifications_bp.route("/blasts/preview", methods=["POST"])
@require_role("admin")
def preview_blast():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    campus = resolve_write_campus(data.get("campus_id"))
    segment = data.get("target_segment", data.get("segment", {}))
    if not isinstance(segment, dict):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if campus and any(segment.get(k) not in (None, "", campus) for k in ("campus", "campus_id")):
        return jsonify({"error": MSG.NOTIFICATION_BLAST_CAMPUS_DENIED}), 403
    try:
        target_campus = campus or segment.get("campus_id") or segment.get("campus")
        ids = resolve_segment_user_ids(segment, campus_id=target_campus, db=get_db())
    except Exception:
        logger.exception("Blast audience preview failed")
        return jsonify({"error": MSG.SERVICE_UNAVAILABLE}), 503
    return jsonify({"recipient_count": len(ids)}), 200
