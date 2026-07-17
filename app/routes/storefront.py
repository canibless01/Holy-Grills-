"""Storefront routes — CMS sections, operating hours, promo codes."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.db import get_db
from app.messages import MSG
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
    allowed = {"title", "subtitle", "body", "image_url", "cta_text", "cta_url", "is_active", "sort_order", "config"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("storefront_sections").eq("id", section_id).update(update)
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
    hours = db.table("operating_hours").select("*").order("weekday").execute()

    from datetime import date
    today = date.today().isoformat()
    override_rows = (
        db.table("operating_hour_overrides")
        .select("*")
        .eq("date", today)
        .execute()
    )
    override = override_rows[0] if override_rows else None

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
    day_name = (data.get("day") or "").lower()
    if not day_name:
        return jsonify({"error": MSG.STOREFRONT_DAY_REQUIRED}), 400
    day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
               "friday": 4, "saturday": 5, "sunday": 6}
    if day_name not in day_map:
        return jsonify({"error": MSG.STOREFRONT_INVALID_DAY.format(day=day_name)}), 400
    weekday_int = day_map[day_name]
    allowed = {"open_time", "close_time", "is_closed"}
    update_raw = {k: v for k, v in data.items() if k in allowed}
    if not update_raw:
        return jsonify({"error": "At least one of open_time, close_time, is_closed is required"}), 400
    # DB columns are opens_at / closes_at; route accepts either name
    update = {}
    if "open_time" in update_raw:
        update["opens_at"] = update_raw.pop("open_time")
    if "close_time" in update_raw:
        update["closes_at"] = update_raw.pop("close_time")
    update.update(update_raw)  # carries is_closed unchanged
    result = db.table("operating_hours").eq("weekday", weekday_int).update(update)
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
    data = request.get_json(force=True) or {}
    if "override_date" in data:
        data["date"] = data.pop("override_date")
    if not data.get("date"):
        return jsonify({"error": "date (or override_date) is required"}), 400
    allowed = {"date", "is_closed", "open_time", "close_time", "reason"}
    raw = {k: v for k, v in data.items() if k in allowed}
    # DB columns are opens_at / closes_at; route accepts either name
    payload = {}
    if "open_time" in raw:
        payload["opens_at"] = raw.pop("open_time")
    if "close_time" in raw:
        payload["closes_at"] = raw.pop("close_time")
    payload.update(raw)
    result = db.table("operating_hour_overrides").upsert(payload, on_conflict="date")
    return jsonify(result[0] if isinstance(result, list) else result), 201


@storefront_bp.route("/promo-codes/validate", methods=["POST"])
def validate_promo():
    """
    [DEPRECATED] Validate a promo code — use POST /orders/validate-promo instead.

    This endpoint lacks per-user usage enforcement and will be removed in a
    future release. Switch to POST /orders/validate-promo which applies the
    same validation *plus* checks that the requesting user has not already
    exceeded their personal usage quota for the code.
    ---
    tags: [Storefront]
    deprecated: true
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
        description: Promo code valid with discount info (deprecated — use /orders/validate-promo)
      400:
        description: Invalid or expired code
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    code = data.get("code", "").upper()
    subtotal = float(data.get("order_subtotal", 0))

    def _dep(body, status=200):
        """Return a response with deprecation headers on every path."""
        r = jsonify({**body, "_deprecated": True, "_use_instead": "POST /api/orders/validate-promo"})
        r.headers["Deprecation"] = "true"
        r.headers["Sunset"] = "2026-10-01"
        r.headers["Link"] = '</api/orders/validate-promo>; rel="successor-version"'
        return r, status

    rows = db.table("promo_codes").select("*").eq("code", code).eq("is_active", "true").limit(1).execute()
    promo = rows[0] if rows else None
    if not promo:
        return _dep({"error": MSG.STOREFRONT_PROMO_INVALID}, 400)

    now = datetime.now(timezone.utc).isoformat()
    if promo.get("ends_at") and promo["ends_at"] < now:
        return _dep({"error": MSG.STOREFRONT_PROMO_EXPIRED}, 400)
    if promo.get("starts_at") and promo["starts_at"] > now:
        return _dep({"error": MSG.STOREFRONT_PROMO_NOT_ACTIVE}, 400)
    if promo.get("max_uses") and int(promo.get("used_count") or 0) >= promo["max_uses"]:
        return _dep({"error": MSG.STOREFRONT_PROMO_LIMIT}, 400)
    if subtotal < float(promo.get("min_order_amount") or 0):
        return _dep({"error": MSG.STOREFRONT_PROMO_MIN_ORDER.format(min_amount=float(promo.get("min_order_amount", 0)))}, 400)

    if promo["discount_type"] == "percentage":
        discount = subtotal * float(promo["discount_value"]) / 100
    else:
        discount = float(promo["discount_value"])

    return _dep({
        "valid": True,
        "discount_type": promo["discount_type"],
        "discount_value": promo["discount_value"],
        "calculated_discount": round(discount, 2),
        "code": code,
    })


def _is_currently_open(schedule: list, override) -> bool:
    from datetime import datetime, timezone, time
    now = datetime.now(timezone.utc)
    today_weekday = now.weekday()  # 0=Monday … 6=Sunday

    if override:
        if override.get("is_closed"):
            return False
        open_val = override.get("open_time") or override.get("opens_at")
        close_val = override.get("close_time") or override.get("closes_at")
        if open_val and close_val:
            open_t = _parse_time(open_val)
            close_t = _parse_time(close_val)
            return open_t <= now.time() <= close_t

    for row in schedule:
        if row.get("weekday") == today_weekday:
            if row.get("is_closed"):
                return False
            open_val = row.get("open_time") or row.get("opens_at", "00:00")
            close_val = row.get("close_time") or row.get("closes_at", "23:59")
            open_t = _parse_time(open_val)
            close_t = _parse_time(close_val)
            return open_t <= now.time() <= close_t
    return False


def _parse_time(t_str: str):
    from datetime import time
    try:
        parts = str(t_str).split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return time(0, 0)


@storefront_bp.route("/early-supporters", methods=["GET"])
def list_early_supporters():
    """
    Get the public-facing Early Supporters list.
    Early Supporters are storefront_sections rows with section_type='early_supporter'.
    Each entry's content object carries: name, photo_url, social_links, note.
    ---
    tags: [Storefront]
    security: []
    responses:
      200:
        description: List of early supporters (ordered by sort_order)
    """
    db = get_db()
    rows = (
        db.table("storefront_sections")
        .select("id,title,content,sort_order,created_at")
        .eq("section_type", "early_supporter")
        .eq("is_active", "true")
        .order("sort_order", ascending=True)
        .execute()
    ) or []
    supporters = []
    for row in rows:
        content = row.get("content") or {}
        supporters.append({
            "id": row.get("id"),
            "name": content.get("name") or row.get("title"),
            "photo_url": content.get("photo_url"),
            "social_links": content.get("social_links") or {},
            "note": content.get("note"),
            "sort_order": row.get("sort_order", 0),
        })
    return jsonify(supporters), 200


@storefront_bp.route("/early-supporters", methods=["POST"])
@require_role("admin")
def create_early_supporter():
    """
    Add a new Early Supporter entry (admin only).
    Uses storefront_sections with section_type='early_supporter'.
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name:        {type: string, description: "Supporter's name"}
            photo_url:   {type: string, description: "Profile photo URL"}
            social_links:
              type: object
              description: "e.g. {twitter, instagram, linkedin}"
            note:        {type: string, description: "Short personal note"}
            sort_order:  {type: integer}
    responses:
      201:
        description: Early supporter created
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "'name' is required"}), 400

    import re
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug_key = f"early_supporter_{slug}"

    content = {
        "name": name,
        "photo_url": data.get("photo_url"),
        "social_links": data.get("social_links") or {},
        "note": data.get("note"),
    }
    try:
        result = db.table("storefront_sections").insert({
            "key": slug_key,
            "title": name,
            "section_type": "early_supporter",
            "content": content,
            "is_active": True,
            "sort_order": int(data.get("sort_order", 0)),
        })
    except Exception as e:
        err_str = str(e)
        if "duplicate" in err_str.lower() or "unique" in err_str.lower() or "23505" in err_str:
            # Deduplicate key: append timestamp suffix and retry
            import time as _time
            slug_key = f"{slug_key}_{int(_time.time())}"
            result = db.table("storefront_sections").insert({
                "key": slug_key,
                "title": name,
                "section_type": "early_supporter",
                "content": content,
                "is_active": True,
                "sort_order": int(data.get("sort_order", 0)),
            })
        else:
            raise
    row = result[0] if isinstance(result, list) else result
    return jsonify({"message": "Early supporter added", "supporter": row}), 201


@storefront_bp.route("/early-supporters/<section_id>", methods=["PATCH"])
@require_role("admin")
def update_early_supporter(section_id):
    """
    Update an Early Supporter entry (admin only).
    ---
    tags: [Storefront]
    """
    db = get_db()
    existing = (
        db.table("storefront_sections")
        .select("id,content,section_type")
        .eq("id", section_id)
        .eq("section_type", "early_supporter")
        .limit(1)
        .execute()
    )
    if not existing:
        return jsonify({"error": "Early supporter not found"}), 404

    data = request.get_json(force=True) or {}
    current_content = (existing[0] if isinstance(existing, list) else existing).get("content") or {}
    for field in ("name", "photo_url", "social_links", "note"):
        if field in data:
            current_content[field] = data[field]

    update_payload = {
        "content": current_content,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if "name" in data:
        update_payload["title"] = data["name"]
    if "sort_order" in data:
        update_payload["sort_order"] = int(data["sort_order"])
    if "is_active" in data:
        update_payload["is_active"] = bool(data["is_active"])

    result = db.table("storefront_sections").eq("id", section_id).update(update_payload)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@storefront_bp.route("/early-supporters/<section_id>", methods=["DELETE"])
@require_role("admin")
def delete_early_supporter(section_id):
    """
    Deactivate an Early Supporter entry (admin only — soft delete).
    ---
    tags: [Storefront]
    """
    db = get_db()
    existing = (
        db.table("storefront_sections")
        .select("id")
        .eq("id", section_id)
        .eq("section_type", "early_supporter")
        .limit(1)
        .execute()
    )
    if not existing:
        return jsonify({"error": "Early supporter not found"}), 404
    db.table("storefront_sections").eq("id", section_id).update({
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": "Early supporter removed", "id": section_id}), 200


@storefront_bp.route("/sections", methods=["POST"])
@require_role("admin")
def create_section():
    """
    Create a new CMS homepage section (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [key, title, section_type]
          properties:
            key: {type: string, description: "Unique identifier slug"}
            title: {type: string}
            section_type: {type: string, description: "e.g. hero, banner, promo, faq"}
            content: {type: object, description: "Arbitrary JSON content for the section"}
            is_active: {type: boolean}
            sort_order: {type: integer}
    responses:
      201:
        description: Section created
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    for f in ["key", "title", "section_type"]:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400
    SECTION_COLS = {"key", "title", "section_type", "content", "is_active", "sort_order"}
    safe = {k: v for k, v in data.items() if k in SECTION_COLS}
    safe.setdefault("is_active", True)
    safe.setdefault("sort_order", 0)
    safe.setdefault("content", {})
    result = db.table("storefront_sections").insert(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@storefront_bp.route("/sections/<section_id>", methods=["DELETE"])
@require_role("admin")
def delete_section(section_id):
    """
    Deactivate (soft-delete) a CMS homepage section (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: path
        name: section_id
        type: string
        required: true
    responses:
      200:
        description: Section deactivated
      404:
        description: Not found
    """
    db = get_db()
    existing = db.table("storefront_sections").select("id").eq("id", section_id).limit(1).execute()
    if not existing:
        return jsonify({"error": MSG.SECTION_NOT_FOUND}), 404
    db.table("storefront_sections").eq("id", section_id).update({
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": MSG.SECTION_DEACTIVATED, "section_id": section_id}), 200


@storefront_bp.route("/banners", methods=["GET"])
def list_banners():
    """
    Get active promotional banners for the storefront homepage.
    ---
    tags: [Storefront]
    security: []
    parameters:
      - in: query
        name: placement
        type: string
        description: Filter by banner placement (e.g. homepage, checkout)
    responses:
      200:
        description: Active banners ordered by sort_order
    """
    db = get_db()
    q = db.table("banners").select("*").eq("is_active", "true")
    placement = request.args.get("placement")
    if placement:
        q = q.eq("placement", placement)
    banners = q.order("sort_order").execute() or []
    return jsonify(banners), 200


@storefront_bp.route("/banners", methods=["POST"])
@require_role("admin")
def create_banner():
    """
    Create a new promotional banner (admin only).

    Supports carousel mode: pass an `images` array of URLs alongside the
    required `image_url` (used as the primary/fallback image). The mobile
    client iterates `images` to render a swipeable carousel; single-image
    banners omit `images` and fall back to `image_url`.
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, image_url]
          properties:
            title: {type: string}
            subtitle: {type: string}
            image_url: {type: string, description: "Primary / fallback image URL"}
            images: {type: array, items: {type: string}, description: "Ordered list of image URLs for carousel slides"}
            cta_text: {type: string}
            cta_url: {type: string}
            placement: {type: string, description: "homepage, checkout, etc."}
            is_active: {type: boolean}
            sort_order: {type: integer}
    responses:
      201:
        description: Banner created
      400:
        description: Missing required field or invalid images format
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    for f in ["title", "image_url"]:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400

    # Validate carousel images if provided
    images = data.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(isinstance(u, str) and u for u in images):
            return jsonify({"error": "'images' must be a non-empty list of URL strings"}), 400

    BANNER_COLS = {"title", "subtitle", "image_url", "images", "cta_text", "cta_url",
                   "placement", "is_active", "sort_order"}
    safe = {k: v for k, v in data.items() if k in BANNER_COLS}
    safe.setdefault("is_active", True)
    safe.setdefault("sort_order", 0)
    result = db.table("banners").insert(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@storefront_bp.route("/banners/<banner_id>", methods=["DELETE"])
@require_role("admin")
def delete_banner(banner_id):
    """
    Delete a banner (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: path
        name: banner_id
        type: string
        required: true
    responses:
      200:
        description: Banner deleted
      404:
        description: Not found
    """
    db = get_db()
    banner = db.table("banners").select("id,title").eq("id", banner_id).single().execute()
    if not banner:
        return jsonify({"error": "Banner not found"}), 404
    db.table("banners").eq("id", banner_id).delete()
    return jsonify({"message": f"Banner '{banner.get('title', banner_id)}' deleted"}), 200


@storefront_bp.route("/banners/<banner_id>", methods=["PATCH"])
@require_role("admin")
def update_banner(banner_id):
    """
    Update a banner (admin only). Pass `images` array to enable/update carousel slides.
    ---
    tags: [Storefront]
    parameters:
      - in: path
        name: banner_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            title: {type: string}
            subtitle: {type: string}
            image_url: {type: string, description: "Primary / fallback image URL"}
            images: {type: array, items: {type: string}, description: "Carousel slide URLs (replaces existing array)"}
            cta_text: {type: string}
            cta_url: {type: string}
            placement: {type: string}
            is_active: {type: boolean}
            sort_order: {type: integer}
    responses:
      200:
        description: Banner updated
      400:
        description: Invalid images format
      404:
        description: Banner not found
    """
    db = get_db()
    data = request.get_json(force=True) or {}

    # Validate carousel images if provided
    images = data.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(isinstance(u, str) and u for u in images):
            return jsonify({"error": "'images' must be a non-empty list of URL strings"}), 400

    # Verify banner exists
    existing = db.table("banners").select("id").eq("id", banner_id).single().execute()
    if not existing:
        return jsonify({"error": "Banner not found"}), 404

    allowed = {"title", "subtitle", "image_url", "images", "cta_text", "cta_url",
               "placement", "is_active", "sort_order"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("banners").eq("id", banner_id).update(update)
    return jsonify(result[0] if isinstance(result, list) else result), 200


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
        return jsonify({"error": MSG.STOREFRONT_EMAIL_REQUIRED}), 400

    existing_rows = db.table("newsletter_subscriptions").select("id,unsubscribed_at").eq("email", email).limit(1).execute()
    existing = existing_rows[0] if existing_rows else None
    if existing:
        if not existing.get("unsubscribed_at"):
            return jsonify({"message": MSG.STOREFRONT_ALREADY_SUBSCRIBED}), 200
        db.table("newsletter_subscriptions").eq("email", email).update({"unsubscribed_at": None})
        return jsonify({"message": MSG.STOREFRONT_RESUBSCRIBED}), 200

    row = db.table("newsletter_subscriptions").insert({
        "email": email,
        "full_name": data.get("full_name"),
        "source": data.get("source", "direct"),
        "is_confirmed": True,
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
        return jsonify({"error": MSG.STOREFRONT_EMAIL_REQUIRED}), 400

    db.table("newsletter_subscriptions").eq("email", email).update({
        "unsubscribed_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": MSG.STOREFRONT_UNSUBSCRIBED}), 200


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
        q = q.is_("unsubscribed_at", "null")
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(rows), 200
