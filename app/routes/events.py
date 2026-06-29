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
        .select("id,title,slug,description,location,starts_at,ends_at,hp_reward,hp_promo_enabled,is_featured")
        .eq("is_published", "true")
        .gte("starts_at", now)
        .order("starts_at")
        .execute()
    )
    return jsonify(events or []), 200


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
    try:
        tickets = db.table("event_tickets").select("id").eq("event_id", event_id).execute()
        ticket_ids = [t["id"] for t in (tickets or [])]
        if ticket_ids:
            checkins = db.table("event_checkins").select("id").in_("ticket_id", ticket_ids).execute()
            event["checkin_count"] = len(checkins or [])
        else:
            event["checkin_count"] = 0
    except Exception:
        event["checkin_count"] = 0
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

        from flask import current_app
        event = db.table("events").select("hp_reward,title").eq("id", event_id).single().execute()
        hp_amount = event.get("hp_reward") or current_app.config["EVENT_CHECKIN_HP"] if event else current_app.config["EVENT_CHECKIN_HP"]

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        try:
            user_tickets = db.table("event_tickets").select("id").eq("user_id", g.user_id).execute()
            ticket_ids = [t["id"] for t in (user_tickets or [])]
            if ticket_ids:
                checkins_this_month = db.table("event_checkins").select("id").in_("ticket_id", ticket_ids).gte("created_at", month_start).execute()
            else:
                checkins_this_month = []
        except Exception:
            checkins_this_month = []

        cap = current_app.config["EVENT_CHECKIN_CAP_PER_MONTH"]
        if len(checkins_this_month) >= cap:
            return jsonify({"message": f"Monthly event check-in limit reached ({cap}x/month). No HP awarded.", "hp_awarded": 0}), 200

        hp_result = earn_pending_hp(
            user_id=g.user_id,
            amount=hp_amount,
            source_type="event",
            reference_id=event_id,
            notes=f"Event check-in HP: {event.get('title', '') if event else ''}",
        )

        from app.services.notification_service import send_notification
        send_notification(
            user_id=g.user_id,
            notif_type="hp_earned",
            title=f"+{hp_result['added_to_pending']} HP Pending!",
            body=f"You earned HP for attending {event.get('title', 'the event') if event else 'the event'}. Order food to unlock it!",
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
          required: [organizer_name, email, event_name, event_date, expected_guests]
          properties:
            organizer_name: {type: string}
            email: {type: string}
            phone: {type: string}
            event_name: {type: string}
            event_date: {type: string, format: date}
            expected_guests: {type: integer}
            budget: {type: number}
            notes: {type: string}
            hp_promo_optin: {type: boolean}
    responses:
      201:
        description: Request submitted
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["organizer_name", "email", "phone", "event_name", "event_date", "expected_guests"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400
    data["status"] = "new"
    result = db.table("catering_requests").insert(data)
    saved = result[0] if isinstance(result, list) else result

    admins = db.table("profiles").select("id").eq("role", "admin").execute()
    from app.services.notification_service import send_notification
    for admin in (admins or []):
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
    Create a new event listing (admin only).
    ---
    tags: [Events]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, location, starts_at, hp_reward]
          properties:
            title: {type: string}
            description: {type: string}
            location: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
            hp_reward: {type: integer}
            hp_promo_enabled: {type: boolean}
            is_featured: {type: boolean}
            capacity: {type: integer}
    responses:
      201:
        description: Event created
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["title", "location", "starts_at", "hp_reward"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400

    import re, uuid as _uuid
    base_slug = re.sub(r"[^a-z0-9]+", "-", data["title"].lower()).strip("-")[:54]
    data["slug"] = f"{base_slug}-{_uuid.uuid4().hex[:5]}"
    data["is_published"] = True
    data["organizer_id"] = g.user_id
    if not data.get("ends_at"):
        from datetime import datetime, timezone, timedelta
        starts = datetime.fromisoformat(data["starts_at"].replace("Z", "+00:00"))
        data["ends_at"] = (starts + timedelta(hours=3)).isoformat()
    EVENT_COLUMNS = {
        "title", "slug", "description", "location", "starts_at", "ends_at",
        "hp_reward", "hp_promo_enabled", "is_featured", "capacity",
        "is_published", "organizer_id",
    }
    safe = {k: v for k, v in data.items() if k in EVENT_COLUMNS}
    result = db.table("events").insert(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 201
