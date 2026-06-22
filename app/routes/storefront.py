"""Storefront routes — CMS sections, operating hours, promo codes."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.db import get_db
from datetime import datetime, timezone

storefront_bp = Blueprint("storefront", __name__)


@storefront_bp.route("/sections", methods=["GET"])
def list_sections():
    """
    Get active storefront CMS sections (homepage, banners, etc).
    ---
    tags: [Storefront]
    security: []
    responses:
      200:
        description: Storefront sections
    """
    db = get_db()
    sections = db.table("storefront_sections").select("*").eq("is_active", "true").order("sort_order").execute()
    return jsonify(sections), 200


@storefront_bp.route("/sections/<section_id>", methods=["PATCH"])
@require_role("admin")
def update_section(section_id):
    """
    Update a storefront section (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: path
        name: section_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            title: {type: string}
            subtitle: {type: string}
            body: {type: string}
            image_url: {type: string}
            cta_text: {type: string}
            cta_url: {type: string}
            is_active: {type: boolean}
            sort_order: {type: integer}
            config: {type: object}
    responses:
      200:
        description: Section updated
    """
    db = get_db()
    data = request.get_json(force=True)
    data["last_edited_by"] = g.user_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("storefront_sections").eq("id", section_id).update(data)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@storefront_bp.route("/operating-hours", methods=["GET"])
def get_hours():
    """
    Get current operating hours schedule and any today-specific override.
    ---
    tags: [Storefront]
    security: []
    responses:
      200:
        description: Operating hours including today's status
    """
    db = get_db()
    hours = db.table("operating_hours").select("*").order("day").execute()

    from datetime import date
    today = date.today().isoformat()
    override = (
        db.table("operating_hour_overrides")
        .select("*")
        .eq("override_date", today)
        .single()
        .execute()
    )

    return jsonify({
        "schedule": hours,
        "today_override": override,
        "is_open": _is_currently_open(hours, override),
    }), 200


@storefront_bp.route("/operating-hours", methods=["PATCH"])
@require_role("admin")
def update_hours():
    """
    Update operating hours for a day (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            day: {type: string, enum: [monday, tuesday, wednesday, thursday, friday, saturday, sunday]}
            open_time: {type: string, example: "10:00"}
            close_time: {type: string, example: "21:00"}
            is_closed: {type: boolean}
    responses:
      200:
        description: Hours updated
    """
    db = get_db()
    data = request.get_json(force=True)
    day = data.get("day")
    if not day:
        return jsonify({"error": "day is required"}), 400
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("operating_hours").eq("day", day).update(data)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@storefront_bp.route("/operating-hours/override", methods=["POST"])
@require_role("admin")
def set_override():
    """
    Set a date-specific operating hours override (e.g., public holiday closure).
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [override_date, is_closed]
          properties:
            override_date: {type: string, format: date}
            is_closed: {type: boolean}
            open_time: {type: string}
            close_time: {type: string}
            reason: {type: string}
    responses:
      201:
        description: Override set
    """
    db = get_db()
    data = request.get_json(force=True)
    data["created_by"] = g.user_id
    result = db.table("operating_hour_overrides").upsert(data, on_conflict="override_date")
    return jsonify(result[0] if isinstance(result, list) else result), 201


@storefront_bp.route("/promo-codes/validate", methods=["POST"])
def validate_promo():
    """
    Validate a promo code without applying it. Returns discount info.
    ---
    tags: [Storefront]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [code, order_subtotal]
          properties:
            code: {type: string}
            order_subtotal: {type: number}
    responses:
      200:
        description: Promo code valid with discount info
      400:
        description: Invalid or expired code
    """
    db = get_db()
    data = request.get_json(force=True)
    code = data.get("code", "").upper()
    subtotal = float(data.get("order_subtotal", 0))

    promo = db.table("promo_codes").select("*").eq("code", code).eq("is_active", "true").single().execute()
    if not promo:
        return jsonify({"error": "Invalid or expired promo code"}), 400

    now = datetime.now(timezone.utc).isoformat()
    if promo.get("valid_until") and promo["valid_until"] < now:
        return jsonify({"error": "Promo code has expired"}), 400
    if promo.get("max_uses") and promo.get("used_count", 0) >= promo["max_uses"]:
        return jsonify({"error": "Promo code has reached its usage limit"}), 400
    if subtotal < float(promo.get("min_order_value", 0)):
        return jsonify({"error": f"Minimum order ₦{promo['min_order_value']:.0f} required"}), 400

    if promo["discount_type"] == "percentage":
        discount = subtotal * float(promo["discount_value"]) / 100
    else:
        discount = float(promo["discount_value"])

    if promo.get("max_discount_cap"):
        discount = min(discount, float(promo["max_discount_cap"]))

    return jsonify({
        "valid": True,
        "discount_type": promo["discount_type"],
        "discount_value": promo["discount_value"],
        "calculated_discount": round(discount, 2),
        "code": code,
    }), 200


def _is_currently_open(schedule: list, override) -> bool:
    from datetime import datetime, timezone, time
    now = datetime.now(timezone.utc)
    day_name = now.strftime("%A").lower()

    if override:
        if override.get("is_closed"):
            return False
        if override.get("open_time") and override.get("close_time"):
            open_t = _parse_time(override["open_time"])
            close_t = _parse_time(override["close_time"])
            return open_t <= now.time() <= close_t

    for row in schedule:
        if row.get("day", "").lower() == day_name:
            if row.get("is_closed"):
                return False
            open_t = _parse_time(row.get("open_time", "00:00"))
            close_t = _parse_time(row.get("close_time", "23:59"))
            return open_t <= now.time() <= close_t
    return False


def _parse_time(t_str: str):
    from datetime import time
    try:
        parts = str(t_str).split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return time(0, 0)


@storefront_bp.route("/newsletter", methods=["POST"])
def newsletter_subscribe():
    """
    Subscribe an email address to the Holy Grills newsletter.
    ---
    tags: [Storefront]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email]
          properties:
            email: {type: string, format: email}
            full_name: {type: string}
            source: {type: string, example: "footer"}
    responses:
      201:
        description: Subscribed successfully
      200:
        description: Already subscribed
    """
    db = get_db()
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    existing = db.table("newsletter_subscriptions").select("id,is_active").eq("email", email).single().execute()
    if existing:
        if existing.get("is_active"):
            return jsonify({"message": "Already subscribed"}), 200
        db.table("newsletter_subscriptions").eq("email", email).update({"is_active": True, "unsubscribed_at": None})
        return jsonify({"message": "Resubscribed successfully"}), 200

    row = db.table("newsletter_subscriptions").insert({
        "email": email,
        "full_name": data.get("full_name"),
        "source": data.get("source", "direct"),
        "is_active": True,
    })
    return jsonify(row[0] if isinstance(row, list) else row), 201


@storefront_bp.route("/newsletter/unsubscribe", methods=["POST"])
def newsletter_unsubscribe():
    """
    Unsubscribe an email address from the newsletter.
    ---
    tags: [Storefront]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email]
          properties:
            email: {type: string, format: email}
    responses:
      200:
        description: Unsubscribed successfully
    """
    db = get_db()
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    db.table("newsletter_subscriptions").eq("email", email).update({
        "is_active": False,
        "unsubscribed_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": "Unsubscribed successfully"}), 200


@storefront_bp.route("/newsletter", methods=["GET"])
@require_role("admin")
def newsletter_list():
    """
    List newsletter subscribers (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: query
        name: active_only
        type: boolean
        default: true
      - in: query
        name: limit
        type: integer
        default: 100
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: Subscriber list
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))
    q = db.table("newsletter_subscriptions").select("*")
    if request.args.get("active_only", "true").lower() != "false":
        q = q.eq("is_active", "true")
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(rows), 200
