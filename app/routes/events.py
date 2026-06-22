"""Events routes — discovery, catering requests, QR check-in."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import earn_pending_hp
from app.db import get_db
from datetime import datetime, timezone
import uuid

events_bp = Blueprint("events", __name__)


@events_bp.route("", methods=["GET"])
def list_events():
    """
    List active upcoming events.
    ---
    tags: [Events]
    security: []
    responses:
      200:
        description: Event list
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    events = (
        db.table("events")
        .select("id,title,slug,description,venue,event_date,event_end_date,hp_earn,hp_promo_enabled,is_featured,ticket_listing_id")
        .eq("is_active", "true")
        .gte("event_date", now)
        .order("is_featured", ascending=False)
        .order("event_date")
        .execute()
    )
    return jsonify(events), 200


@events_bp.route("/<event_id>", methods=["GET"])
def get_event(event_id):
    """
    Get event detail.
    ---
    tags: [Events]
    security: []
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      200:
        description: Event detail
      404:
        description: Not found
    """
    db = get_db()
    event = db.table("events").select("*").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": "Event not found"}), 404
    checkin_count = db.table("event_checkins").select("id").eq("event_id", event_id).execute()
    event["checkin_count"] = len(checkin_count)
    return jsonify(event), 200


@events_bp.route("/<event_id>/checkin", methods=["POST"])
@require_auth
def checkin(event_id):
    """
    Check in to a Holy Grills event using QR token. Awards HP to pending pool.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [qr_token]
          properties:
            qr_token: {type: string}
    responses:
      200:
        description: Check-in successful, HP awarded
      400:
        description: Already checked in or invalid QR
    """
    db = get_db()
    data = request.get_json(force=True)
    qr_token = data.get("qr_token", "").strip()

    try:
        result = db.rpc("checkin_event_atomic", {
            "p_event_id": event_id,
            "p_user_id": g.user_id,
            "p_qr_token": qr_token,
        })
        if isinstance(result, dict) and result.get("error"):
            return jsonify({"error": result["error"]}), 400

        event = db.table("events").select("hp_earn,title").eq("id", event_id).single().execute()
        hp_amount = event.get("hp_earn", 40) if event else 40

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        checkins_this_month = (
            db.table("event_checkins")
            .select("id")
            .eq("user_id", g.user_id)
            .gte("checked_in_at", month_start)
            .execute()
        )
        if len(checkins_this_month) >= 3:
            return jsonify({"message": "Monthly event check-in limit reached (3x/month). No HP awarded.", "hp_awarded": 0}), 200

        hp_result = earn_pending_hp(
            user_id=g.user_id,
            amount=hp_amount,
            source_type="event",
            reference_id=event_id,
            notes=f"Event check-in HP: {event.get('title', '')}",
        )

        from app.services.notification_service import send_notification
        send_notification(
            user_id=g.user_id,
            notif_type="hp_earned",
            title=f"+{hp_result['added_to_pending']} HP Pending!",
            body=f"You earned HP for attending {event.get('title', 'the event')}. Order food to unlock it!",
            channels=["in_app"],
        )

        return jsonify({
            "message": "Check-in successful",
            "hp_added_to_pending": hp_result["added_to_pending"],
            "hp_added_to_overflow": hp_result.get("added_to_overflow", 0),
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@events_bp.route("/catering-requests", methods=["POST"])
def submit_catering_request():
    """
    Submit a catering / event partnership request.
    ---
    tags: [Events]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [organizer_name, organizer_email, event_name, event_date, venue, expected_attendance]
          properties:
            organizer_name: {type: string}
            organizer_email: {type: string}
            event_name: {type: string}
            event_date: {type: string, format: date}
            event_time: {type: string}
            venue: {type: string}
            expected_attendance: {type: integer}
            budget_range: {type: string}
            catering_notes: {type: string}
            hp_promo_optin: {type: boolean}
    responses:
      201:
        description: Request submitted
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["organizer_name", "organizer_email", "event_name", "event_date", "venue", "expected_attendance"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400
    data["status"] = "pending"
    result = db.table("catering_requests").insert(data)
    saved = result[0] if isinstance(result, list) else result

    admins = db.table("profiles").select("id").eq("role", "admin").execute()
    from app.services.notification_service import send_notification
    for admin in admins:
        send_notification(
            user_id=admin["id"],
            notif_type="catering_request",
            title="New Catering Request",
            body=f"{data['organizer_name']} submitted a catering request for '{data['event_name']}'",
            reference_id=saved["id"],
            reference_type="catering_request",
            channels=["in_app"],
        )

    return jsonify(saved), 201


@events_bp.route("", methods=["POST"])
@require_role("admin")
def create_event():
    """
    Create a new event listing (admin only). Generates unique QR token.
    ---
    tags: [Events]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, venue, event_date, hp_earn]
          properties:
            title: {type: string}
            description: {type: string}
            venue: {type: string}
            event_date: {type: string, format: date-time}
            event_end_date: {type: string, format: date-time}
            hp_earn: {type: integer}
            hp_promo_enabled: {type: boolean}
            is_featured: {type: boolean}
            ticket_listing_id: {type: string}
    responses:
      201:
        description: Event created with QR token
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["title", "venue", "event_date", "hp_earn"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400

    import hashlib
    data["qr_code_token"] = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:32]
    data["slug"] = data["title"].lower().replace(" ", "-")[:60]
    data["is_active"] = True
    data["created_by"] = g.user_id
    result = db.table("events").insert(data)
    return jsonify(result[0] if isinstance(result, list) else result), 201
