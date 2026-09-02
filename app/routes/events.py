"""Events routes — discovery, catering requests, QR check-in, ticket tiers, admin export."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role, optional_auth, assert_owns_campus, ADMIN_ROLES
from app.utils.email import send_qr_ticket_email
from app.services.hp_service import earn_pending_hp
from app.db import get_db, get_user_client, SupabaseError
from app.messages import MSG, resolve_msg
from app.utils.validators import (
    validate_choice, validate_non_negative_number, validate_uuid,
    validate_datetime_order, sanitize_string,
)
from datetime import datetime, timezone
import uuid

events_bp = Blueprint("events", __name__)

def _get_campus_id():
    """
    Resolve campus_id from multiple sources (for guests and authenticated users).

    Priority:
    1. Query param (?campus_id=123)
    2. Header (X-Campus-ID: 123)
    3. Authenticated user's session (g.campus_id)
    4. None (show all events)
    """
    campus_id = request.args.get("campus_id")
    if campus_id:
        return campus_id.strip()

    campus_id = request.headers.get("X-Campus-ID")
    if campus_id:
        return campus_id.strip()

    campus_id = getattr(g, "campus_id", None)
    if campus_id:
        return str(campus_id).strip()

    return None


def _require_campus_selection():
    """
    Guard for guest/user browse endpoints where campus selection is mandatory.
    Returns (campus_id, None) or (None, (json_response, status_code)).
    """
    campus_id = _get_campus_id()
    if not campus_id:
        return None, (jsonify({
            "error": "Please select a campus to continue",
            "code": "CAMPUS_SELECTION_REQUIRED",
        }), 400)
    return campus_id, None

CATERING_STATUSES = ("new", "reviewed", "quoted", "accepted", "completed", "rejected", "cancelled")


@events_bp.route("", methods=["GET"])
def list_events():
    """
    List published upcoming events for the selected campus (or all if unspecified).
    ---
    tags: [Events]
    security: []
    responses:
      200:
        description: Event list
    """
    campus_id = _get_campus_id()
    db = get_user_client()
    now = datetime.now(timezone.utc).isoformat()
    q = (
        db.table("events")
        .select("id,title,slug,description,location,starts_at,ends_at,hp_reward,hp_promo_enabled,is_featured,campus_id,is_global")
        .eq("is_published", "true")
        .gte("starts_at", now)
    )
    events = q.order("starts_at").execute() or []
    if campus_id:
        events = [
            e for e in events
            if e.get("campus_id") == campus_id or e.get("campus_id") is None or e.get("is_global") in (True, "true")
        ]
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
    db = get_user_client()
    event = db.table("events").select("*").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    campus_id = _get_campus_id()
    is_event_global = event.get("campus_id") is None or event.get("is_global") in (True, "true")
    if campus_id and event.get("campus_id") != campus_id and not is_event_global:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
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
@optional_auth
def checkin(event_id):
    """
    Check in to a Holy Grills event using QR token or ticket ID / guest email.
    Awards HP if user is registered/authenticated or links guest account.
    """
    db = get_user_client()

    # Campus check
    event = None
    try:
        event = db.table("events").select("id,campus_id,is_global,metadata").eq("id", event_id).single().execute()
        if not event:
            return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
        campus_id = getattr(g, "campus_id", None)
        is_event_global = event.get("campus_id") is None or event.get("is_global") in (True, "true")
        if campus_id and event.get("campus_id") != campus_id and not is_event_global:
            return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    except Exception:
        if not event:
            return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    raw_token = (data.get("qr_token") or data.get("ticket_id") or "").strip()
    guest_email = (data.get("guest_email") or data.get("email") or "").strip()

    event_metadata = event.get("metadata") or {}
    expected_door_qr = event_metadata.get("qr_token")

    door_qr_matched = False
    clean_token = raw_token

    if raw_token.startswith("hg-event:"):
        parts = raw_token.split(":")
        if len(parts) == 3:
            p_event_id, p_token = parts[1], parts[2]
            if p_event_id != event_id:
                return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
            if expected_door_qr and p_token == expected_door_qr:
                door_qr_matched = True
            else:
                return jsonify({"error": "Invalid door QR token"}), 400
            clean_token = p_token
    elif expected_door_qr and raw_token == expected_door_qr:
        door_qr_matched = True

    try:
        ticket = None
        # Try finding ticket by QR code / ID if it wasn't a door QR match
        if clean_token and not door_qr_matched:
            ticket_rows = db.table("event_tickets").select("*").eq("id", clean_token).execute() or []
            if not ticket_rows:
                ticket_rows = db.table("event_tickets").select("*").eq("qr_code", clean_token).execute() or []
            if ticket_rows:
                ticket = ticket_rows[0]

        # Try finding ticket by user_id if authenticated
        if not ticket and getattr(g, "user_id", None):
            t_rows = db.table("event_tickets").select("*").eq("event_id", event_id).eq("user_id", g.user_id).execute() or []
            if t_rows:
                ticket = t_rows[0]

        # Try finding ticket by guest_email
        if not ticket and guest_email:
            t_rows = db.table("event_tickets").select("*").eq("event_id", event_id).eq("guest_email", guest_email).execute() or []
            if t_rows:
                ticket = t_rows[0]

        if not ticket:
            return jsonify({"error": MSG.TICKET_NOT_FOUND}), 400

        ticket_id_str = ticket["id"]

        # Check existing check-in
        existing_checkin = db.table("event_checkins").select("id").eq("ticket_id", ticket_id_str).execute() or []
        if existing_checkin:
            return jsonify({"error": MSG.TICKET_ALREADY_CHECKED_IN}), 400

        # Insert check-in record
        checked_by = getattr(g, "user_id", None)
        try:
            db.table("event_checkins").insert({
                "ticket_id": ticket_id_str,
                "checked_in_by": checked_by,
                "qr_code": clean_token or ticket_id_str,
            })
        except SupabaseError as insert_err:
            err_str = str(insert_err)
            if "23505" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
                return jsonify({"error": MSG.TICKET_ALREADY_CHECKED_IN}), 400
            raise

        # Check if guest email now has an account profile in system
        target_user_id = getattr(g, "user_id", None) or ticket.get("user_id")
        was_guest_linked = False

        if not target_user_id and ticket.get("guest_email"):
            prof_row = db.table("profiles").select("id").eq("email", ticket["guest_email"]).execute() or []
            if prof_row:
                target_user_id = prof_row[0]["id"]
                was_guest_linked = True

        if target_user_id:
            # Auto-link ticket if previously guest
            if ticket.get("is_guest") or not ticket.get("user_id"):
                db.table("event_tickets").eq("id", ticket_id_str).update({
                    "user_id": target_user_id,
                    "is_guest": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                was_guest_linked = True

            event = db.table("events").select("hp_reward,hp_per_attendee,title").eq("id", event_id).single().execute()
            hp_amount = (
                (event.get("hp_per_attendee") or event.get("hp_reward"))
                if event else current_app.config.get("EVENT_CHECKIN_HP", 50)
            ) or current_app.config.get("EVENT_CHECKIN_HP", 50)

            hp_result = earn_pending_hp(
                user_id=target_user_id,
                amount=hp_amount,
                source_type="event",
                reference_id=event_id,
                notes=f"Event check-in HP: {event.get('title', '') if event else ''}",
            )

            try:
                from app.services.milestone_service import check_milestone_trigger
                check_milestone_trigger(target_user_id, "first_event", 1)
                check_milestone_trigger(target_user_id, "event_checkins", 1)
            except Exception:
                pass

            msg_text = MSG.TICKET_LINKED_TO_ACCOUNT if was_guest_linked else MSG.EVENT_CHECKIN_SUCCESS
            return jsonify({
                "message": msg_text,
                "hp_added_to_pending": hp_result.get("added_to_pending", hp_amount),
            }), 200

        # Still guest without account
        return jsonify({
            "message": MSG.EVENT_CHECKIN_SUCCESS,
            "hp_added_to_pending": 0,
            "is_guest": True,
            "prompt_create_account": MSG.GUEST_ACCOUNT_PROMPT,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@events_bp.route("/admin", methods=["GET"])
@require_role("admin")
def admin_list_events():
    """
    List all events including unpublished (admin only).
    ---
    tags: [Events]
    parameters:
      - in: query
        name: published_only
        type: boolean
        default: false
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
        description: All events for admin
    """
    db = get_user_client()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("events").select("*")
    if request.args.get("published_only", "false").lower() == "true":
        q = q.eq("is_published", "true")
    events = q.order("starts_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"events": events, "count": len(events)}), 200


@events_bp.route("/<event_id>", methods=["PATCH"])
@require_role("admin")
def update_event(event_id):
    """
    Update an event (admin only).
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            title: {type: string}
            description: {type: string}
            location: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
            hp_reward: {type: integer}
            hp_promo_enabled: {type: boolean}
            is_featured: {type: boolean}
            is_published: {type: boolean}
            capacity: {type: integer}
    responses:
      200:
        description: Event updated
      404:
        description: Not found
    """
    db = get_user_client()
    event = db.table("events").select("id,starts_at,ends_at,capacity,title,campus_id").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    assert_owns_campus(event.get("campus_id"))
    data = request.get_json(force=True, silent=True) or {}
    EVENT_UPDATE_COLS = {
        "title", "description", "location", "starts_at", "ends_at",
        "hp_reward", "hp_promo_enabled", "is_featured", "is_published", "capacity",
        # Phase 2 columns:
        "hp_per_attendee", "funding_source", "max_attendees",
        "hp_required", "total_value", "is_paid",
    }
    # Prefer hp_per_attendee; sync to hp_reward for backward compat
    if "hp_per_attendee" in data and "hp_reward" not in data:
        data["hp_reward"] = data["hp_per_attendee"]
    safe = {k: v for k, v in data.items() if k in EVENT_UPDATE_COLS}
    if not safe:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400

    if "capacity" in safe and safe["capacity"] is not None:
        try:
            cap = int(safe["capacity"])
            if cap <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": MSG.EVENT_CAPACITY_INVALID}), 400
        issued = db.table("event_tickets").select("id").eq("event_id", event_id).execute() or []
        if cap < len(issued):
            return jsonify({"error": MSG.EVENT_CAPACITY_BELOW_ISSUED.format(issued=len(issued))}), 400
        safe["capacity"] = cap

    if "hp_reward" in safe and safe["hp_reward"] is not None:
        try:
            hp = int(safe["hp_reward"])
            if hp < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": MSG.EVENT_HP_REWARD_INVALID}), 400
        safe["hp_reward"] = hp

    starts_at = safe.get("starts_at", event.get("starts_at"))
    ends_at = safe.get("ends_at", event.get("ends_at"))
    if ("starts_at" in safe or "ends_at" in safe) and starts_at and ends_at:
        ok, err = validate_datetime_order(starts_at, ends_at)
        if not ok:
            return jsonify({"error": err}), 400

    for bool_field in ("hp_promo_enabled", "is_featured", "is_published"):
        if bool_field in safe and not isinstance(safe[bool_field], bool):
            return jsonify({"error": f"{bool_field} must be a boolean"}), 400

    result = db.table("events").eq("id", event_id).update(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@events_bp.route("/<event_id>", methods=["DELETE"])
@require_role("admin")
def delete_event(event_id):
    """
    Delete an event (admin only). Cascades to event_tickets and checkins.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      200:
        description: Event deleted
      404:
        description: Not found
    """
    db = get_user_client()
    event = db.table("events").select("id,title,campus_id").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    assert_owns_campus(event.get("campus_id"))
    # Cascade: remove check-ins and tickets before deleting event
    try:
        tickets = db.table("event_tickets").select("id").eq("event_id", event_id).execute() or []
        ticket_ids = [t["id"] for t in tickets]
        if ticket_ids:
            for tid in ticket_ids:
                db.table("event_checkins").eq("ticket_id", tid).delete()
        db.table("event_tickets").eq("event_id", event_id).delete()
    except Exception:
        pass
    db.table("events").eq("id", event_id).delete()
    return jsonify({"message": MSG.EVENT_DELETED.format(title=event.get("title", event_id))}), 200


@events_bp.route("/<event_id>/qr", methods=["POST"])
@require_role("admin")
def generate_event_qr(event_id):
    """
    Generate a QR token for event check-in (admin only).

    Returns a signed token that attendees scan at the door. The token is stored
    on the event and verified by POST /<event_id>/checkin. Regenerating
    overwrites the previous token, invalidating old QR codes.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      200:
        description: QR token generated
      404:
        description: Event not found
    """
    db = get_user_client()
    event = db.table("events").select("id,title,metadata").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    import uuid as _uuid
    qr_token = _uuid.uuid4().hex
    metadata = dict(event.get("metadata") or {})
    metadata["qr_token"] = qr_token
    db.table("events").eq("id", event_id).update({"metadata": metadata})
    qr_payload = f"hg-event:{event_id}:{qr_token}"
    return jsonify({
        "event_id": event_id,
        "qr_token": qr_token,
        "qr_payload": qr_payload,
        "instructions": "Encode qr_payload as a QR code. Attendees scan it at checkin.",
    }), 200


@events_bp.route("/<event_id>/register", methods=["POST"])
@optional_auth
def register_for_event(event_id):
    """
    Register for an event. Supports ticket tiers, an optional HP discount
    (HP + discounted cash, never HP alone), wallet/card/split cash payment,
    and promo codes. Guests (no account) can register and pay by card,
    exactly like guest checkout on orders -- always full price, no HP/wallet.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      201:
        description: Registered (or payment initiated)
      400:
        description: Validation error
      404:
        description: Event not found
    """
    import uuid
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}

    try:
        event = db.table("events").select("*").eq("id", event_id).single().execute()
    except Exception:
        event = None
    if not event or not event.get("is_published"):
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    campus_id = _get_campus_id()
    is_event_global = event.get("campus_id") is None
    if campus_id and event.get("campus_id") != campus_id and not is_event_global:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    # ── Custom registration field validation (unchanged from original) ──
    answers_data = data.get("registration_answers", {}) or {}
    reg_fields = event.get("registration_fields") or []
    for field_def in reg_fields:
        if not isinstance(field_def, dict):
            continue
        fname = field_def.get("name")
        flabel = field_def.get("label") or fname
        ftype = field_def.get("type", "text")
        is_req = field_def.get("required", False)
        ans_val = answers_data.get(fname)
        if ans_val is None and fname in data:
            ans_val = data.get(fname)
        if is_req and (ans_val is None or str(ans_val).strip() == ""):
            return jsonify({"error": MSG.REGISTRATION_FIELD_REQUIRED.format(field=flabel)}), 400
        if ans_val is not None and str(ans_val).strip() != "":
            if ftype == "select":
                opts = field_def.get("options") or []
                if opts and ans_val not in opts:
                    return jsonify({"error": f"Invalid selection for {flabel}"}), 400
            answers_data[fname] = ans_val
    metadata_payload = {"registration_answers": answers_data}

    # ── Tier lookup ──
    tier_id = data.get("tier_id")
    tier = None
    if tier_id:
        tier = db.table("event_ticket_tiers").select("*").eq("id", tier_id).eq("event_id", event_id).single().execute()
        if not tier:
            return jsonify({"error": "Ticket tier not found"}), 404

    price_hp = int((tier or {}).get("price_hp") or 0)
    user_id = getattr(g, "user_id", None)

    # ── Guest path (no bearer token) -- always full price, card only ──
    if not user_id:
        guest_email = (data.get("guest_email") or data.get("email") or "").strip()
        guest_name = (data.get("guest_name") or data.get("name") or "").strip()
        guest_phone = (data.get("guest_phone") or data.get("phone") or "").strip()
        if not guest_email:
            return jsonify({"error": MSG.GUEST_EMAIL_REQUIRED}), 400
        if not guest_name:
            return jsonify({"error": MSG.GUEST_NAME_REQUIRED}), 400
        if not guest_phone:
            return jsonify({"error": MSG.GUEST_PHONE_REQUIRED}), 400

        promo_code_id = None
        full_price = float((tier or {}).get("price_naira_full") or (tier or {}).get("price_naira") or 0)
        if data.get("promo_code") and full_price > 0:
            code = str(data["promo_code"]).strip().upper()
            promo = db.table("promo_codes").select("id,min_order_amount").eq("code", code).eq("is_active", "true").execute() or []
            if not promo:
                return jsonify({"error": f"Promo code '{code}' is invalid"}), 400
            promo_code_id = promo[0]["id"]

        try:
            rpc_res = db.rpc("register_for_event_guest_paid", {
                "p_event_id": event_id,
                "p_guest_email": guest_email,
                "p_guest_name": guest_name,
                "p_guest_phone": guest_phone,
                "p_tier_id": tier_id,
                "p_promo_code_id": promo_code_id,
                "p_metadata": metadata_payload,
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

        if isinstance(rpc_res, dict) and rpc_res.get("error"):
            return jsonify({"error": rpc_res["error"]}), 400

        if isinstance(rpc_res, dict):
            ticket_id = rpc_res.get("ticket_id")
            status = rpc_res.get("status")
            payment_status = rpc_res.get("payment_status")
            card_amount_used = rpc_res.get("card_amount_used")
        else:
            ticket_id = str(rpc_res) if rpc_res else None
            status = "confirmed"
            payment_status = "not_required"
            card_amount_used = 0

        response = {
            "message": MSG.GUEST_REGISTRATION_SUCCESS,
            "ticket_id": ticket_id,
            "qr_token": ticket_id,
            "status": status,
            "payment_status": payment_status,
            "is_guest": True,
            "prompt_create_account": getattr(MSG, "GUEST_ACCOUNT_PROMPT", "Create an account to track your orders and earn points!"),
        }

        card_amount = float(card_amount_used or 0)
        if card_amount > 0:
            resp = _initiate_event_card_payment(db, ticket_id, event_id, card_amount, guest_email, data.get("callback_url"))
            if "error" in resp:
                return jsonify({**resp, "ticket_id": ticket_id}), 502
            response.update(resp)
        else:
            try:
                send_qr_ticket_email(
                    email=guest_email, name=guest_name, event_title=event.get("title", ""),
                    ticket_id=ticket_id, event_id=event_id,
                    event_date=event.get("starts_at", ""), event_location=event.get("location", ""),
                )
            except Exception:
                pass

        return jsonify(response), 201

    # ── Authenticated user path ──
    use_hp = bool(data.get("use_hp"))  # explicit opt-in only -- never automatic
    if use_hp:
        if price_hp <= 0:
            return jsonify({"error": "This ticket has no HP discount available"}), 400
        from app.services.hp_service import get_hp_balance
        balance = get_hp_balance(user_id)
        if balance.get("active", 0) < price_hp:
            return jsonify({"error": f"Insufficient HP balance. Need {price_hp} HP to use the HP discount -- you can still register at full price instead."}), 400

    cash_reference_price = float((tier or {}).get("price_naira") or 0) if use_hp else float((tier or {}).get("price_naira_full") or (tier or {}).get("price_naira") or 0)

    promo_code_id = None
    if data.get("promo_code") and cash_reference_price > 0:
        code = str(data["promo_code"]).strip().upper()
        promo = db.table("promo_codes").select("id,min_order_amount").eq("code", code).eq("is_active", "true").execute() or []
        if not promo:
            return jsonify({"error": f"Promo code '{code}' is invalid"}), 400
        promo_code_id = promo[0]["id"]
        if cash_reference_price < float(promo[0].get("min_order_amount") or 0):
            return jsonify({"error": f"This ticket does not meet the minimum amount for promo code '{code}'"}), 400

    wallet_amount = 0
    if cash_reference_price > 0:
        payment_method = data.get("payment_method", "wallet")
        if payment_method == "wallet":
            wallet_amount = cash_reference_price  # RPC caps this to the post-discount total
        elif payment_method == "split":
            wallet_amount = max(0, float(data.get("wallet_amount", 0)))
        # "card" -> wallet_amount stays 0

    try:
        rpc_res = db.rpc("register_for_event_paid", {
            "p_event_id": event_id,
            "p_user_id": user_id,
            "p_tier_id": tier_id,
            "p_use_hp": use_hp,
            "p_wallet_amount": wallet_amount,
            "p_promo_code_id": promo_code_id,
            "p_metadata": metadata_payload,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    if isinstance(rpc_res, dict) and rpc_res.get("error"):
        return jsonify({"error": rpc_res["error"]}), 400

    ticket_id = rpc_res.get("ticket_id")
    already = rpc_res.get("already_registered", False)
    msg = MSG.ALREADY_REGISTERED_FOR_EVENT if already else (getattr(MSG, "EVENT_REGISTRATION_SUCCESS", MSG.GUEST_REGISTRATION_SUCCESS))
    response = {
        "message": msg,
        "ticket_id": ticket_id,
        "status": rpc_res.get("status") if isinstance(rpc_res, dict) else "confirmed",
        "payment_status": rpc_res.get("payment_status") if isinstance(rpc_res, dict) else "not_required",
        "payment_method": rpc_res.get("payment_method") if isinstance(rpc_res, dict) else "none",
        "hp_charged": rpc_res.get("hp_charged", 0) if isinstance(rpc_res, dict) else 0,
    }

    card_amount = float(rpc_res.get("card_amount_used") or 0)
    if not already and card_amount > 0:
        profile = db.table("profiles").select("email,full_name").eq("id", user_id).single().execute() or {}
        email = (g.jwt_payload or {}).get("email") or profile.get("email") or ""
        resp = _initiate_event_card_payment(db, ticket_id, event_id, card_amount, email, data.get("callback_url"), user_id=user_id)
        if "error" in resp:
            return jsonify({**resp, "ticket_id": ticket_id}), 502
        response.update(resp)
    elif not already and response["payment_status"] in ("paid", "not_required"):
        try:
            profile = db.table("profiles").select("email,full_name").eq("id", user_id).single().execute() or {}
            send_qr_ticket_email(
                email=(g.jwt_payload or {}).get("email") or profile.get("email") or "",
                name=profile.get("full_name") or "", event_title=event.get("title", ""),
                ticket_id=ticket_id, event_id=event_id,
                event_date=event.get("starts_at", ""), event_location=event.get("location", ""),
            )
        except Exception:
            pass

    return jsonify(response), 201


def _initiate_event_card_payment(db, ticket_id, event_id, amount_naira, email, callback_url=None, user_id=None):
    """Shared helper: initialize Paystack for the card portion of an event ticket."""
    import uuid
    from app.services.payment_service import initialize_payment
    if not current_app.config.get("PAYSTACK_SECRET_KEY"):
        return {"error": "Card payments are not configured on this server."}
    try:
        ref_prefix = current_app.config.get("EVENT_TICKET_REF_PREFIX", "HG-EVTKT-")
        reference = f"{ref_prefix}{str(uuid.uuid4())[:8].upper()}"
        meta = {"type": "event_ticket_payment", "ticket_id": ticket_id, "event_id": event_id}
        if user_id:
            meta["user_id"] = user_id
        pay_result = initialize_payment(
            email=email, amount_naira=amount_naira, reference=reference,
            metadata=meta, callback_url=callback_url,
        )
        db.table("event_tickets").eq("id", ticket_id).update({"payment_reference": reference})
        return {"authorization_url": pay_result["authorization_url"], "card_amount_due": amount_naira}
    except Exception as exc:
        return {"error": f"Registration recorded but card payment setup failed: {exc}"}


@events_bp.route("/<event_id>/tickets/<ticket_id>/pdf", methods=["GET"])
@optional_auth
def download_ticket_pdf(event_id, ticket_id):
    """
    Download a PDF version of an event ticket, with the same QR the
    check-in scanner expects (ticket_id-based -- NOT the shared door-poster code).
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: path
        name: ticket_id
        type: string
        required: true
    responses:
      200:
        description: PDF file
      403:
        description: Not your ticket
      404:
        description: Not found
    """
    import io
    import qrcode
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    db = get_user_client()
    ticket = db.table("event_tickets").select("*").eq("id", ticket_id).eq("event_id", event_id).single().execute()
    if not ticket:
        return jsonify({"error": MSG.TICKET_NOT_FOUND}), 404

    user_id = getattr(g, "user_id", None)
    if ticket.get("user_id"):
        if not user_id or str(ticket["user_id"]) != str(user_id):
            return jsonify({"error": "You do not have access to this ticket"}), 403
    else:
        provided_email = (request.args.get("guest_email") or "").strip().lower()
        if not provided_email or provided_email != (ticket.get("guest_email") or "").lower():
            return jsonify({"error": "You do not have access to this ticket"}), 403

    event = db.table("events").select("title,starts_at,ends_at,location").eq("id", event_id).single().execute() or {}
    tier = None
    if ticket.get("tier_id"):
        tier = db.table("event_ticket_tiers").select("name").eq("id", ticket["tier_id"]).single().execute()

    qr_payload = f"hg-event:{event_id}:{ticket_id}"
    qr_img = qrcode.make(qr_payload)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    width, height = A5

    c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, height - 20 * mm, "Holy Grills — Event Ticket")

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, height - 32 * mm, event.get("title", "Event"))

    c.setFont("Helvetica", 10)
    y = height - 40 * mm
    if event.get("starts_at"):
        c.drawString(15 * mm, y, f"When: {event['starts_at']}")
        y -= 6 * mm
    if event.get("location"):
        c.drawString(15 * mm, y, f"Where: {event['location']}")
        y -= 6 * mm
    if tier and tier.get("name"):
        c.drawString(15 * mm, y, f"Tier: {tier['name']}")
        y -= 6 * mm
    attendee = ticket.get("guest_name") or "Registered attendee"
    c.drawString(15 * mm, y, f"Attendee: {attendee}")
    y -= 10 * mm

    c.drawImage(ImageReader(qr_buf), 15 * mm, y - 45 * mm, width=45 * mm, height=45 * mm)
    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, y - 50 * mm, f"Ticket ID: {ticket_id}")
    c.drawString(15 * mm, y - 55 * mm, "Present this QR code at the door.")

    c.showPage()
    c.save()
    buf.seek(0)

    from flask import send_file
    return send_file(
        buf, mimetype="application/pdf", as_attachment=True,
        download_name=f"holy-grills-ticket-{ticket_id[:8]}.pdf",
    )


def confirm_event_ticket_payment(ticket_id: str, payment_reference: str, provider_response: dict = None) -> dict:
    """
    Called after card payment for an event ticket is confirmed (webhook).
    Mirrors confirm_order_payment() exactly.
    """
    db = get_user_client()
    ticket = db.table("event_tickets").select("*").eq("id", ticket_id).single().execute()
    if not ticket:
        raise ValueError("Ticket not found")

    if ticket.get("payment_status") == "paid":
        return ticket  # idempotent

    try:
        db.rpc("hg_mark_event_ticket_paid", {
            "p_ticket_id": ticket_id,
            "p_provider": "paystack",
            "p_provider_reference": payment_reference,
            "p_amount": ticket.get("card_amount_used"),
            "p_metadata": provider_response or {},
        })
    except Exception as exc:
        raise ValueError(f"Failed to confirm ticket payment: {exc}")

    updated = db.table("event_tickets").select("*").eq("id", ticket_id).single().execute()

    # Send the QR ticket email now that payment is actually confirmed
    try:
        event = db.table("events").select("title,starts_at,location").eq("id", updated["event_id"]).single().execute() or {}
        if updated.get("user_id"):
            profile = db.table("profiles").select("email,full_name").eq("id", updated["user_id"]).single().execute() or {}
            email, name = profile.get("email", ""), profile.get("full_name", "")
        else:
            email, name = updated.get("guest_email", ""), updated.get("guest_name", "")
        send_qr_ticket_email(
            email=email, name=name, event_title=event.get("title", ""),
            ticket_id=ticket_id, event_id=updated["event_id"],
            event_date=event.get("starts_at", ""), event_location=event.get("location", ""),
        )
    except Exception:
        pass

    return updated


@events_bp.route("/catering-requests", methods=["GET"])
@require_role("admin")
def list_catering_requests():
    """
    List catering/event partnership requests (admin only).
    ---
    tags: [Events]
    parameters:
      - in: query
        name: status
        type: string
        enum: [new, reviewed, accepted, rejected]
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
        description: Catering request list
    """
    db = get_user_client()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("catering_requests").select("*")
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"requests": rows, "count": len(rows)}), 200


@events_bp.route("/catering-requests/<request_id>", methods=["PATCH"])
@require_role("admin")
def update_catering_request(request_id):
    """
    Respond to a catering request — accept, reject, or add notes (admin only).
    ---
    tags: [Events]
    parameters:
      - in: path
        name: request_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            status: {type: string, enum: [quoted, completed, cancelled]}
            notes: {type: string}
            quoted_amount: {type: number}
            assigned_to: {type: string}
    responses:
      200:
        description: Request updated
      404:
        description: Not found
    """
    db = get_user_client()
    row = db.table("catering_requests").select("id,organizer_name,email").eq("id", request_id).single().execute()
    if not row:
        return jsonify({"error": MSG.EVENT_CATERING_NOT_FOUND}), 404
    data = request.get_json(force=True, silent=True) or {}
    ALLOWED = {"status", "notes", "quoted_amount", "assigned_to"}
    safe = {k: v for k, v in data.items() if k in ALLOWED}
    if not safe:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400

    if "status" in safe:
        ok, err = validate_choice(safe["status"], CATERING_STATUSES, "status")
        if not ok:
            return jsonify({"error": err}), 400

    if "quoted_amount" in safe and safe["quoted_amount"] is not None:
        ok, err = validate_non_negative_number(safe["quoted_amount"], "quoted_amount")
        if not ok:
            return jsonify({"error": err}), 400

    if "notes" in safe and safe["notes"] is not None:
        if not isinstance(safe["notes"], str) or len(safe["notes"]) > 2000:
            return jsonify({"error": MSG.EVENT_NOTES_INVALID}), 400
        safe["notes"] = sanitize_string(safe["notes"], max_len=2000)

    if "assigned_to" in safe and safe["assigned_to"] is not None:
        if not validate_uuid(safe["assigned_to"]):
            return jsonify({"error": MSG.EVENT_ASSIGNED_TO_INVALID}), 400
        assignee = db.table("profiles").select("id,role").eq("id", safe["assigned_to"]).single().execute()
        if not assignee or assignee.get("role") not in ADMIN_ROLES:
            return jsonify({"error": MSG.EVENT_ASSIGNED_TO_NOT_STAFF}), 400

    result = db.table("catering_requests").eq("id", request_id).update(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 200


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
    db = get_user_client()
    data = request.get_json(force=True)
    required = ["organizer_name", "email", "phone", "event_name", "event_date", "expected_guests"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400

    campus_id = getattr(g, "campus_id", None) or _get_campus_id()
    if not campus_id:
        return jsonify({"error": "campus_id is required"}), 400
    data["campus_id"] = campus_id
    data["status"] = "new"
    result = db.table("catering_requests").insert(data)
    saved = result[0] if isinstance(result, list) else result

    admins = (
        db.table("profiles")
        .select("id")
        .eq("role", "admin")
        .eq("campus_id", campus_id)
        .execute()
    ) or []
    super_admins = get_db().table("profiles").select("id").eq("role", "super_admin").execute() or []

    from app.services.notification_service import send_notification
    for admin in list(admins) + list(super_admins):
        send_notification(
            user_id=admin["id"],
            notif_type="catering_request",
            template_data={"organizer": data["organizer_name"], "event_name": data["event_name"]},
            reference_id=saved["id"],
            reference_type="catering_request",
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
    db = get_user_client()
    data = request.get_json(force=True)
    required = ["title", "location", "starts_at", "hp_reward"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400

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
        "is_published", "organizer_id", "campus_id",
        # Phase 2 columns (from migration):
        "hp_per_attendee", "funding_source", "max_attendees",
        "hp_required", "total_value", "is_paid",
    }
    # Prefer hp_per_attendee over legacy hp_reward if provided
    if data.get("hp_per_attendee") and not data.get("hp_reward"):
        data["hp_reward"] = data["hp_per_attendee"]
    campus_id = getattr(g, "campus_id", None)
    if not campus_id:
        return jsonify({"error": "Unable to resolve campus for this request"}), 400
    safe = {k: v for k, v in data.items() if k in EVENT_COLUMNS or k == "campus_id"}
    safe["campus_id"] = campus_id
    try:
        result = db.table("events").insert(safe).execute()
    except Exception as _exc:
        # New columns may not exist yet — strip them and retry
        PHASE2_COLS = {"hp_per_attendee", "funding_source", "max_attendees", "hp_required", "total_value", "is_paid"}
        safe2 = {k: v for k, v in safe.items() if k not in PHASE2_COLS}
        result = db.table("events").insert(safe2).execute()
    return jsonify(result[0] if isinstance(result, list) else result), 201


# ── Ticket Tiers ─────────────────────────────────────────────────────────────

@events_bp.route("/<event_id>/tiers", methods=["GET"])
def list_event_tiers(event_id):
    """
    List ticket tiers for an event (public).
    """
    db = get_user_client()
    event = db.table("events").select("id,title,campus_id").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    campus_id = _get_campus_id()
    if campus_id and event.get("campus_id") != campus_id:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    tiers = (
        db.table("event_ticket_tiers")
        .select("id,name,price_naira,price_hp,capacity,sold_count,description")
        .eq("event_id", event_id)
        .order("price_naira")
        .execute()
    ) or []
    return jsonify(tiers), 200


@events_bp.route("/<event_id>/tiers", methods=["POST"])
@require_role("admin")
def create_event_tier(event_id):
    """
    Create a ticket tier for an event (admin only).
    """
    db = get_user_client()
    event = db.table("events").select("id").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": MSG.TIER_NAME_REQUIRED}), 400

    price_naira = data.get("price_naira", 0)
    price_hp    = data.get("price_hp", 0)
    if price_naira < 0 or price_hp < 0:
        return jsonify({"error": MSG.TIER_PRICE_INVALID}), 400

    capacity = data.get("capacity")
    if capacity is not None and (not isinstance(capacity, int) or capacity < 1):
        return jsonify({"error": MSG.TIER_CAPACITY_INVALID_TIER}), 400

    features = data.get("features", [])
    if features is not None and not isinstance(features, list):
        return jsonify({"error": MSG.TIER_FEATURES_INVALID}), 400
    if features and not all(isinstance(f, str) for f in features):
        return jsonify({"error": MSG.TIER_FEATURES_INVALID}), 400

    terms = data.get("terms", [])
    if terms is not None and not isinstance(terms, list):
        return jsonify({"error": MSG.TIER_TERMS_INVALID}), 400
    if terms and not all(isinstance(t, str) for t in terms):
        return jsonify({"error": MSG.TIER_TERMS_INVALID}), 400

    is_early_bird = bool(data.get("is_early_bird"))
    early_bird_deadline = data.get("early_bird_deadline")
    if is_early_bird and not early_bird_deadline:
        return jsonify({"error": MSG.TIER_EARLY_BIRD_DEADLINE_REQUIRED}), 400

    payload = {
        "event_id": event_id,
        "name": sanitize_string(name, max_len=120),
        "price_naira": price_naira,
        "price_hp": price_hp,
        "capacity": capacity,
        "description": sanitize_string(data.get("description", ""), max_len=500),
        "sold_count": 0,
        "features": features or [],
        "terms": terms or [],
        "color": data.get("color"),
        "icon": data.get("icon"),
        "is_early_bird": is_early_bird,
        "early_bird_deadline": early_bird_deadline,
    }

    try:
        result = db.table("event_ticket_tiers").insert(payload)
    except Exception:
        fallback = {k: v for k, v in payload.items() if k not in ("features", "terms", "color", "icon", "is_early_bird", "early_bird_deadline")}
        result = db.table("event_ticket_tiers").insert(fallback)

    saved = result[0] if isinstance(result, list) else result
    return jsonify(saved), 201


@events_bp.route("/tiers/<tier_id>", methods=["PATCH"])
@require_role("admin")
def update_event_tier(tier_id):
    """
    Update a ticket tier (admin only).
    """
    db = get_user_client()
    tier = db.table("event_ticket_tiers").select("*").eq("id", tier_id).single().execute()
    if not tier:
        return jsonify({"error": MSG.TIER_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    ALLOWED = {"name", "price_naira", "price_hp", "capacity", "description", "features", "terms", "color", "icon", "is_early_bird", "early_bird_deadline"}
    safe = {k: v for k, v in data.items() if k in ALLOWED}

    if "features" in safe:
        if not isinstance(safe["features"], list) or not all(isinstance(f, str) for f in safe["features"]):
            return jsonify({"error": MSG.TIER_FEATURES_INVALID}), 400

    if "terms" in safe:
        if not isinstance(safe["terms"], list) or not all(isinstance(t, str) for t in safe["terms"]):
            return jsonify({"error": MSG.TIER_TERMS_INVALID}), 400

    is_eb = safe.get("is_early_bird", tier.get("is_early_bird"))
    eb_dl = safe.get("early_bird_deadline", tier.get("early_bird_deadline"))
    if is_eb and not eb_dl:
        return jsonify({"error": MSG.TIER_EARLY_BIRD_DEADLINE_REQUIRED}), 400

    if "name" in safe:
        safe["name"] = sanitize_string(safe["name"], max_len=120)
    if "description" in safe:
        safe["description"] = sanitize_string(safe["description"], max_len=500)
    if "capacity" in safe and safe["capacity"] is not None:
        sold = int(tier.get("sold_count") or 0)
        if int(safe["capacity"]) < sold:
            return jsonify({"error": MSG.EVENT_CAPACITY_BELOW_ISSUED.format(issued=sold)}), 400

    try:
        result = db.table("event_ticket_tiers").eq("id", tier_id).update(safe)
    except Exception:
        fallback = {k: v for k, v in safe.items() if k not in ("features", "terms", "color", "icon", "is_early_bird", "early_bird_deadline")}
        result = db.table("event_ticket_tiers").eq("id", tier_id).update(fallback)

    updated = result[0] if isinstance(result, list) else result
    return jsonify(updated), 200


@events_bp.route("/tiers/<tier_id>", methods=["DELETE"])
@require_role("admin")
def delete_event_tier(tier_id):
    """
    Delete a ticket tier (admin only). Forbidden if any tickets sold.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: tier_id
        type: string
        required: true
    responses:
      200:
        description: Tier deleted
      400:
        description: Cannot delete — tickets already sold
      404:
        description: Tier not found
    """
    db = get_user_client()
    tier = db.table("event_ticket_tiers").select("*").eq("id", tier_id).single().execute()
    if not tier:
        return jsonify({"error": MSG.TIER_NOT_FOUND}), 404

    sold = int(tier.get("sold_count") or 0)
    if sold > 0:
        return jsonify({"error": MSG.TIER_DELETE_HAS_SALES, "sold_count": sold}), 400

    db.table("event_ticket_tiers").eq("id", tier_id).delete()
    return jsonify({"message": "Tier deleted"}), 200


# ── Admin event ticket export & send-to-host ──────────────────────────────────

@events_bp.route("/<event_id>/registrants", methods=["GET"])
@require_role("admin")
def list_event_registrants(event_id):
    """
    List all registrants for an event (admin only).
    Optional ?format=csv for CSV download.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: query
        name: format
        type: string
        enum: [json, csv]
        default: json
    responses:
      200:
        description: Registrant list
      404:
        description: Event not found
    """
    db = get_user_client()
    event = db.table("events").select("id,title,starts_at,location,campus_id").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    assert_owns_campus(event.get("campus_id"))

    try:
        tickets = (
            db.table("event_tickets")
            .select("id,user_id,tier_id,status,created_at,qr_code")
            .eq("event_id", event_id)
            .order("created_at")
            .execute()
        ) or []
    except Exception:
        tickets = (
            db.table("event_tickets")
            .select("id,user_id,tier_id,status,created_at,qr_code")
            .eq("event_id", event_id)
            .order("created_at")
            .execute()
        ) or []

    # Enrich with profile and tier info
    user_ids = list({t["user_id"] for t in tickets if t.get("user_id")})
    tier_ids = list({t["tier_id"] for t in tickets if t.get("tier_id")})

    profiles = {}
    if user_ids:
        profile_rows = db.table("profiles").select("id,full_name,phone,email").in_("id", user_ids).execute() or []
        profiles = {p["id"]: p for p in profile_rows}

    tiers = {}
    if tier_ids:
        tier_rows = db.table("event_ticket_tiers").select("id,name").in_("id", tier_ids).execute() or []
        tiers = {t["id"]: t for t in tier_rows}

    # Fetch check-in status
    ticket_ids = [t["id"] for t in tickets]
    checkins = {}
    if ticket_ids:
        ci_rows = db.table("event_checkins").select("ticket_id,checked_in_at").in_("ticket_id", ticket_ids).execute() or []
        checkins = {r["ticket_id"]: r["checked_in_at"] for r in ci_rows}

    enriched = []
    for t in tickets:
        prof = profiles.get(t.get("user_id"), {})
        tier = tiers.get(t.get("tier_id"), {})
        enriched.append({
            "ticket_id":    t["id"],
            "full_name":    prof.get("full_name"),
            "phone":        prof.get("phone"),
            "email":        prof.get("email"),
            "tier_name":    tier.get("name"),
            "status":       t.get("status"),
            "registered_at": t.get("created_at"),
            "checked_in":   bool(checkins.get(t["id"])),
            "checked_in_at": checkins.get(t["id"]),
        })

    fmt = request.args.get("format", "json").lower()
    if fmt == "csv":
        import csv, io
        si = io.StringIO()
        writer = csv.DictWriter(si, fieldnames=[
            "ticket_id", "full_name", "phone", "email", "tier_name",
            "status", "registered_at", "checked_in", "checked_in_at",
        ])
        writer.writeheader()
        writer.writerows(enriched)
        from flask import make_response
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=event_{event_id}_registrants.csv"
        output.headers["Content-Type"] = "text/csv"
        return output

    return jsonify({
        "event": event,
        "registrants": enriched,
        "total": len(enriched),
    }), 200


@events_bp.route("/<event_id>/image", methods=["POST"])
@require_role("admin")
def update_event_image(event_id):
    """Update event image with Cloudinary URL."""
    data = request.get_json(force=True, silent=True) or {}
    image_url = data.get("image_url")

    if not image_url:
        return jsonify({"error": "image_url is required"}), 400

    db = get_user_client()
    db.table("events").eq("id", event_id).update({
        "image_url": image_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    return jsonify({"image_url": image_url}), 200


@events_bp.route("/<event_id>/send-registrants-to-host", methods=["POST"])
@require_role("admin")
def send_registrants_to_host(event_id):
    """
    Email the full registrant list to the event organiser / host.
    Body: { "host_email": "organizer@example.com", "host_name": "Jane" }
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
          required: [host_email]
          properties:
            host_email: {type: string, format: email}
            host_name:  {type: string}
    responses:
      200:
        description: Email sent
      404:
        description: Event not found
    """
    db = get_user_client()
    event = db.table("events").select("*").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    host_email = (data.get("host_email") or "").strip()
    host_name  = (data.get("host_name")  or "Event Organiser").strip()
    custom_message = (data.get("custom_message") or "").strip()
    if not host_email:
        return jsonify({"error": "host_email is required"}), 400

    # Build registrant table (reuse list_event_registrants logic inline)
    tickets = (
        db.table("event_tickets")
        .select("id,user_id,tier_id,status,created_at")
        .eq("event_id", event_id)
        .order("created_at")
        .execute()
    ) or []

    user_ids = list({t["user_id"] for t in tickets if t.get("user_id")})
    tier_ids = list({t["tier_id"] for t in tickets if t.get("tier_id")})

    profiles = {}
    if user_ids:
        prows = db.table("profiles").select("id,full_name,phone,email").in_("id", user_ids).execute() or []
        profiles = {p["id"]: p for p in prows}

    tiers = {}
    if tier_ids:
        trows = db.table("event_ticket_tiers").select("id,name").in_("id", tier_ids).execute() or []
        tiers = {t["id"]: t for t in trows}

    rows_html = ""
    for t in tickets:
        prof = profiles.get(t.get("user_id"), {})
        tier = tiers.get(t.get("tier_id"), {})
        rows_html += (
            f"<tr><td>{prof.get('full_name','')}</td>"
            f"<td>{prof.get('phone','')}</td>"
            f"<td>{prof.get('email','')}</td>"
            f"<td>{tier.get('name','')}</td>"
            f"<td>{t.get('status','')}</td></tr>"
        )

    custom_msg_html = f"<p>{custom_message}</p>" if custom_message else ""
    html = (
        f"<html><body style='font-family:sans-serif'>"
        f"<h2>Registrants for: {event.get('title', event_id)}</h2>"
        f"<p>Date: {event.get('starts_at','')}</p>"
        f"<p>Location: {event.get('location','')}</p>"
        f"<p>Total: {len(tickets)}</p>"
        f"{custom_msg_html}"
        f"<table border='1' cellpadding='6' cellspacing='0'>"
        f"<tr><th>Name</th><th>Phone</th><th>Email</th><th>Tier</th><th>Status</th></tr>"
        f"{rows_html}"
        f"</table></body></html>"
    )

    from app.utils.email import send_email_raw
    ok = send_email_raw(
        to_email=host_email,
        to_name=host_name,
        subject=f"Registrant List — {event.get('title', event_id)}",
        html_body=html,
    )
    if not ok:
        return jsonify({"error": "Failed to send email — check RESEND_API_KEY"}), 502

    return jsonify({
        "message": "Registrant list sent",
        "host_email": host_email,
        "count": len(tickets),
    }), 200


@events_bp.route("/<event_id>/tiers/comparison", methods=["GET"])
def get_tier_comparison(event_id):
    """Fetch tier comparison view for an event (public)."""
    db = get_user_client()
    event = db.table("events").select("id,title,starts_at,location,campus_id").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    campus_id = _get_campus_id()
    if campus_id and event.get("campus_id") != campus_id:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    try:
        rpc_tiers = db.rpc("get_event_tier_comparison", {"p_event_id": event_id})
        if isinstance(rpc_tiers, list):
            return jsonify({"tiers": rpc_tiers}), 200
    except Exception:
        pass

    try:
        tiers = (
            db.table("event_ticket_tiers")
            .select("id,name,price_naira,price_hp,capacity,sold_count,description,features,terms,color,icon,is_early_bird,early_bird_deadline")
            .eq("event_id", event_id)
            .order("price_naira")
            .execute()
        ) or []
    except Exception:
        tiers = (
            db.table("event_ticket_tiers")
            .select("id,name,price_naira,price_hp,capacity,sold_count,description")
            .eq("event_id", event_id)
            .order("price_naira")
            .execute()
        ) or []

    formatted = []
    for t in tiers:
        cap = t.get("capacity")
        sold = int(t.get("sold_count") or 0)
        item = {
            "id": t["id"],
            "name": t.get("name"),
            "price_naira": t.get("price_naira"),
            "price_hp": t.get("price_hp"),
            "capacity": cap,
            "sold_count": sold,
            "available": (cap - sold) if cap is not None else None,
            "is_sold_out": (cap is not None and sold >= cap),
            "description": t.get("description"),
            "features": t.get("features") if isinstance(t.get("features"), list) else [],
            "terms": t.get("terms") if isinstance(t.get("terms"), list) else [],
            "color": t.get("color"),
            "icon": t.get("icon"),
            "is_early_bird": bool(t.get("is_early_bird")),
            "early_bird_deadline": t.get("early_bird_deadline"),
        }
        formatted.append(item)

    return jsonify({"tiers": formatted}), 200


@events_bp.route("/tiers/<tier_id>/detail", methods=["GET"])
def get_tier_detail(tier_id):
    """Return full tier detail with event info."""
    db = get_user_client()
    tier = db.table("event_ticket_tiers").select("*, events(id,campus_id,title)").eq("id", tier_id).single().execute()
    if not tier:
        return jsonify({"error": MSG.TIER_NOT_FOUND}), 404

    event = tier.get("events")
    if not event or not isinstance(event, dict):
        event = db.table("events").select("*").eq("id", tier["event_id"]).single().execute() or {}

    campus_id = _get_campus_id()
    if campus_id and event.get("campus_id") != campus_id:
        return jsonify({"error": MSG.TIER_NOT_FOUND}), 404

    cap = tier.get("capacity")
    sold = int(tier.get("sold_count") or 0)
    tier["available"] = (cap - sold) if cap is not None else None
    tier["is_sold_out"] = (cap is not None and sold >= cap)
    tier["features"] = tier.get("features") if isinstance(tier.get("features"), list) else []
    tier["terms"] = tier.get("terms") if isinstance(tier.get("terms"), list) else []
    tier["event"] = event

    return jsonify(tier), 200


@events_bp.route("/my-tickets", methods=["GET"])
@require_auth
def my_tickets():
    """Show all tickets for the authenticated user."""
    db = get_user_client()
    tickets = (
        db.table("event_tickets")
        .select("*")
        .eq("user_id", g.user_id)
        .order("created_at", ascending=False)
        .execute()
    ) or []

    event_ids = list({t["event_id"] for t in tickets if t.get("event_id")})
    ticket_ids = [t["id"] for t in tickets]

    events_map = {}
    if event_ids:
        e_rows = db.table("events").select("*").in_("id", event_ids).execute() or []
        events_map = {e["id"]: e for e in e_rows}

    checkins_map = {}
    if ticket_ids:
        c_rows = db.table("event_checkins").select("*").in_("ticket_id", ticket_ids).execute() or []
        checkins_map = {c["ticket_id"]: c for c in c_rows}

    now = datetime.now(timezone.utc).isoformat()
    formatted_tickets = []
    upcoming = []
    past = []
    checked_in = []

    for t in tickets:
        e = events_map.get(t.get("event_id"), {})
        ci = checkins_map.get(t["id"])
        item = {
            "ticket_id": t["id"],
            "qr_token": t.get("qr_code") or t["id"],
            "event_id": t.get("event_id"),
            "event_title": e.get("title"),
            "starts_at": e.get("starts_at"),
            "location": e.get("location"),
            "status": t.get("status"),
            "is_guest": t.get("is_guest", False),
            "checked_in": bool(ci),
            "checked_in_at": ci.get("checked_in_at") if isinstance(ci, dict) else None,
            "event": e,
        }
        formatted_tickets.append(item)
        if ci:
            checked_in.append(item)
        elif e.get("starts_at") and e["starts_at"] < now:
            past.append(item)
        else:
            upcoming.append(item)

    return jsonify({
        "tickets": formatted_tickets,
        "upcoming": upcoming,
        "past": past,
        "checked_in": checked_in,
    }), 200
