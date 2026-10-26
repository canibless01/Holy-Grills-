from flask import Blueprint, request, jsonify, g, Response, redirect
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
import base64

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
    from app.services.notification_preferences import effective_preferences
    try:
        return jsonify(effective_preferences(get_db(),g.user_id)), 200
    except Exception:
        logger.exception("Notification preferences unavailable for %s",g.user_id)
        return jsonify({'error':MSG.SERVICE_UNAVAILABLE}), 503


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

    try:
        result = get_db().rpc('hg_update_notification_preferences_atomic',{'p_user_id':g.user_id,'p_preferences':update})
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


@notifications_bp.route("/blasts/<blast_id>/retry", methods=["POST"])
@require_role("admin")
def retry_blast(blast_id):
    if not validate_uuid(blast_id):
        return jsonify({"error": MSG.NOTIF_BLAST_NOT_FOUND}), 404
    db = get_user_client()
    blast = db.table("notification_blasts").select("*").eq("id", blast_id).single().execute()
    if not blast:
        return jsonify({"error": MSG.NOTIF_BLAST_NOT_FOUND}), 404
    assert_can_modify(blast.get("campus_id"))
    if blast.get("status") == "sent":
        return jsonify({"already_processed": True}), 200
    if blast.get("status") not in ("failed", "sending"):
        return jsonify({"error": MSG.BLAST_RETRY_BUSY}), 409
    try:
        result = send_blast(blast_id)
        if result.get("skipped"):
            return jsonify({"error": MSG.BLAST_RETRY_BUSY}), 409
        return jsonify(result), 200
    except Exception:
        logger.exception("Campaign retry failed for %s", blast_id)
        return jsonify({"error": MSG.SERVICE_UNAVAILABLE}), 503


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
    action_url = data.get("action_url")
    if action_url is not None:
        from urllib.parse import unquote
        if not isinstance(action_url, str) or len(action_url) > 1000:
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        action_url = action_url.strip() or None
        if action_url:
            decoded = unquote(unquote(action_url))
            if not decoded.startswith("/") or decoded.startswith("//") or "\\" in decoded or any(ord(c) < 32 for c in decoded):
                return jsonify({"error": MSG.INVALID_INPUT}), 400
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
            "email_provider": email_provider, "action_url": action_url}
    
    # Handle rich content fields
    if "body_html" in data and data["body_html"]:
        if not isinstance(data["body_html"], str) or len(data["body_html"]) > 50000:
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        data["body_html"] = data["body_html"].strip()
    
    if "images" in data and data["images"]:
        if not isinstance(data["images"], list) or len(data["images"]) > 6:
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        for img in data["images"]:
            if not isinstance(img, dict) or "url" not in img or "alt" not in img:
                return jsonify({"error": MSG.INVALID_INPUT}), 400
        data["images"] = data["images"]
    
    if "cta_blocks" in data and data["cta_blocks"]:
        if not isinstance(data["cta_blocks"], list) or len(data["cta_blocks"]) > 10:
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        for cta in data["cta_blocks"]:
            if not isinstance(cta, dict) or "label" not in cta or "url" not in cta:
                return jsonify({"error": MSG.INVALID_INPUT}), 400
        data["cta_blocks"] = data["cta_blocks"]
    
    if "push_image" in data and data["push_image"]:
        if not isinstance(data["push_image"], str) or len(data["push_image"]) > 1000:
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        data["push_image"] = data["push_image"].strip()
    
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


@notifications_bp.route("/blasts/test", methods=["POST"])
@require_role("admin")
def send_test_blast():
    """
    Send a test notification to the current admin user only.
    ---
    tags: [Notifications]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            title: {type: string}
            body: {type: string}
            channels: {type: array, items: {type: string}}
            test_email: {type: string}
            body_html: {type: string}
            images: {type: array}
            cta_blocks: {type: array}
            push_image: {type: string}
    responses:
      200:
        description: Test notification sent
    """
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    
    title = data.get("title", "Test Notification").strip()
    body = data.get("body", "This is a test notification.").strip()
    channels = data.get("channels", ["in_app"])
    test_email = data.get("test_email")
    
    if not test_email:
        return jsonify({"error": "test_email is required"}), 400
    
    db = get_user_client()
    
    # Get current user
    try:
        user = db.auth.admin.get_user_by_email(test_email)
        if not user:
            return jsonify({"error": "Test user not found"}), 404
        user_id = user.id
    except Exception:
        return jsonify({"error": "Failed to find test user"}), 503
    
    # Create a test blast record
    blast_data = {
        "title": f"[TEST] {title}",
        "body": body,
        "channels": channels,
        "status": "pending",
        "created_by": g.user_id,
        "segment": {},
        "body_html": data.get("body_html"),
        "images": data.get("images", []),
        "cta_blocks": data.get("cta_blocks", []),
        "push_image": data.get("push_image"),
    }
    
    try:
        blast = db.table("notification_blasts").insert(blast_data).execute()
        blast_row = blast[0] if isinstance(blast, list) else blast
        blast_id = blast_row["id"]
        
        # Send to only the test user
        notifications_sent = []
        
        if "in_app" in channels:
            notif_data = {
                "user_id": user_id,
                "title": f"[TEST] {title}",
                "body": body,
                "type": "blast",
                "channel": "in_app",
                "action_url": data.get("action_url"),
                "metadata": {
                    "blast_id": blast_id,
                    "is_test": True,
                }
            }
            try:
                db.table("notifications").insert(notif_data).execute()
                notifications_sent.append(f"in_app:{user_id}")
            except Exception as e:
                logger.warning(f"Failed to create in_app notification: {e}")
        
        if "push" in channels:
            try:
                tokens = db.table("push_subscriptions").select("*").eq("user_id", user_id).execute()
                for sub in tokens:
                    endpoint = sub.get("endpoint") or sub.get("token")
                    if not endpoint:
                        continue
                    title_to_send = f"[TEST] {title}"
                    body_to_send = body
                    send_push_notification(endpoint, sub, title_to_send, body_to_send)
                    notifications_sent.append(f"push:{endpoint[:20]}...")
            except Exception as e:
                logger.warning(f"Failed to send push notification: {e}")
        
        # Update blast record
        db.table("notification_blasts").update({
            "status": "sent",
            "recipient_count": len(notifications_sent),
        }).eq("id", blast_id).execute()
        
        return jsonify({
            "blast_id": blast_id,
            "sent_to": len(notifications_sent),
            "channels": channels,
            "test_user": test_email,
        }), 200
        
    except Exception as e:
        logger.exception("Failed to send test blast")
        return jsonify({"error": f"Failed to send test: {str(e)}"}), 503


# ── Email Analytics Tracking Endpoints ────────────────────────────────────────

@notifications_bp.route("/tracking/open/<blast_id>.png", methods=["GET"])
def track_email_open(blast_id):
    """
    Track email open via 1x1 transparent pixel.
    Called when email client loads the tracking pixel.
    ---
    tags: [Notifications]
    parameters:
      - in: path
        name: blast_id
        type: string
        required: true
    responses:
      200:
        description: 1x1 transparent PNG pixel
    """
    try:
        db = get_db()
        
        # Get blast to check if tracking is enabled
        blast = db.table("notification_blasts").select("tracking_enabled").eq("id", blast_id).single().execute()
        if not blast or not blast.get("tracking_enabled"):
            # Return pixel anyway to avoid broken images, but don't track
            pass
        else:
            # Record the open event
            # Using metadata JSONB field to store analytics
            current_metadata = blast.get("metadata") or {}
            open_events = current_metadata.get("open_events", [])
            
            # Add open event with timestamp
            open_events.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ip": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", "")[:200]
            })
            
            # Keep only last 1000 opens to avoid bloat
            open_events = open_events[-1000:]
            
            current_metadata["open_events"] = open_events
            current_metadata["open_count"] = len(open_events)
            current_metadata["last_opened_at"] = datetime.now(timezone.utc).isoformat()
            
            db.table("notification_blasts").update({
                "metadata": current_metadata
            }).eq("id", blast_id).execute()
            
    except Exception as e:
        # Never fail the pixel request - just log the error
        logger.warning(f"Failed to track email open for blast {blast_id}: {e}")
    
    # Return 1x1 transparent PNG pixel (smallest valid PNG)
    pixel_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    return Response(
        pixel_data,
        mimetype="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@notifications_bp.route("/tracking/click", methods=["GET"])
def track_email_click():
    """
    Track email link click and redirect to destination.
    Called when user clicks a tracked link in email.
    ---
    tags: [Notifications]
    parameters:
      - in: query
        name: blast_id
        type: string
        required: true
      - in: query
        name: url
        type: string
        required: true
      - in: query
        name: label
        type: string
    responses:
      302:
        description: Redirect to destination URL
      400:
        description: Missing required parameters
    """
    blast_id = request.args.get("blast_id")
    destination_url = request.args.get("url")
    link_label = request.args.get("label", "Unknown")
    
    if not blast_id or not destination_url:
        return jsonify({"error": "Missing blast_id or url parameter"}), 400
    
    try:
        db = get_db()
        
        # Get blast to check if tracking is enabled
        blast = db.table("notification_blasts").select("tracking_enabled").eq("id", blast_id).single().execute()
        if not blast or not blast.get("tracking_enabled"):
            # Just redirect without tracking
            pass
        else:
            # Record the click event
            current_metadata = blast.get("metadata") or {}
            click_events = current_metadata.get("click_events", [])
            
            # Add click event
            click_events.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": destination_url,
                "label": link_label,
                "ip": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", "")[:200]
            })
            
            # Keep only last 1000 clicks to avoid bloat
            click_events = click_events[-1000:]
            
            # Track clicks per link
            link_clicks = current_metadata.get("link_clicks", {})
            if destination_url not in link_clicks:
                link_clicks[destination_url] = {
                    "url": destination_url,
                    "label": link_label,
                    "count": 0
                }
            link_clicks[destination_url]["count"] += 1
            
            current_metadata["click_events"] = click_events
            current_metadata["link_clicks"] = link_clicks
            current_metadata["click_count"] = len(click_events)
            
            db.table("notification_blasts").update({
                "metadata": current_metadata
            }).eq("id", blast_id).execute()
            
    except Exception as e:
        # Log error but still redirect
        logger.warning(f"Failed to track email click for blast {blast_id}: {e}")
    
    # Redirect to destination
    return redirect(destination_url, code=302)


@notifications_bp.route("/blasts/<blast_id>/analytics", methods=["GET"])
@require_role("admin")
def get_blast_analytics(blast_id):
    """
    Get analytics data for a specific email blast.
    ---
    tags: [Notifications]
    parameters:
      - in: path
        name: blast_id
        type: string
        required: true
    responses:
      200:
        description: Analytics data
      404:
        description: Blast not found
    """
    try:
        db = get_db()
        blast = db.table("notification_blasts").select("*").eq("id", blast_id).single().execute()
        
        if not blast:
            return jsonify({"error": "Blast not found"}), 404
        
        metadata = blast.get("metadata") or {}
        
        # Calculate analytics
        recipient_count = blast.get("recipient_count", 0)
        open_count = metadata.get("open_count", 0)
        click_count = metadata.get("click_count", 0)
        
        open_rate = (open_count / recipient_count * 100) if recipient_count > 0 else 0
        click_rate = (click_count / recipient_count * 100) if recipient_count > 0 else 0
        click_to_open_rate = (click_count / open_count * 100) if open_count > 0 else 0
        
        analytics = {
            "blast_id": blast_id,
            "recipient_count": recipient_count,
            "open_count": open_count,
            "click_count": click_count,
            "open_rate": round(open_rate, 2),
            "click_rate": round(click_rate, 2),
            "click_to_open_rate": round(click_to_open_rate, 2),
            "last_opened_at": metadata.get("last_opened_at"),
            "link_clicks": metadata.get("link_clicks", {}),
            "recent_opens": metadata.get("open_events", [])[-10:],  # Last 10 opens
            "recent_clicks": metadata.get("click_events", [])[-10:]  # Last 10 clicks
        }
        
        return jsonify(analytics), 200
        
    except Exception as e:
        logger.exception(f"Failed to get analytics for blast {blast_id}")
        return jsonify({"error": f"Failed to get analytics: {str(e)}"}), 500


@notifications_bp.route("/blasts/test-deliverability", methods=["POST"])
@require_role("admin")
def test_email_deliverability():
    """
    Test email deliverability by sending a test email to a spam testing service.
    Returns recommendations for improving deliverability.
    ---
    tags: [Notifications]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            test_email: {type: string, description: "Email address to send test to (e.g., mail-tester address)"}
            title: {type: string}
            body: {type: string}
    responses:
      200:
        description: Test email sent
      400:
        description: Invalid input
    """
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    
    test_email = data.get("test_email")
    title = data.get("title", "Test Email")
    body = data.get("body", "This is a test email for deliverability checking.")
    
    if not test_email:
        return jsonify({"error": "test_email is required"}), 400
    
    try:
        from app.utils.email import send_email_raw, _build_html
        
        # Build a test email with typical content
        html_body = _build_html(
            "Test User",
            body,
            os.environ.get("APP_TAGLINE", "The Holy Grills Team"),
        )
        
        # Send the test email
        send_email_raw(
            to_email=test_email,
            to_name="Test User",
            subject=f"[DELIVERABILITY TEST] {title}",
            html_body=html_body,
        )
        
        return jsonify({
            "success": True,
            "message": f"Test email sent to {test_email}. Check the spam testing service for results.",
            "recommendations": [
                "Ensure SPF, DKIM, and DMARC records are properly configured",
                "Avoid using spam trigger words in subject lines",
                "Include a clear unsubscribe link for marketing emails",
                "Use a consistent sender name and email address",
                "Monitor your sender reputation regularly",
                "Keep your email list clean and engaged",
                "Test emails before sending to large lists",
                "Use double opt-in for new subscribers",
            ]
        }), 200
        
    except Exception as e:
        logger.exception("Failed to send deliverability test email")
        return jsonify({"error": f"Failed to send test: {str(e)}"}), 503
