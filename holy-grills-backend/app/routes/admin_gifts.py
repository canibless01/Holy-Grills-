"""
Admin Gift routes — manage first-order hot dog gifts and system settings.

GET    /admin/gifts/first-order          — list pending/all first-order gifts
PATCH  /admin/gifts/first-order/<id>     — update gift status (fulfil/cancel)
GET    /admin/settings                   — list all system settings
PATCH  /admin/settings/<key>             — update a system setting
"""
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role, resolve_scoped_campus_id
from app.db import get_user_client, SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)
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
        description: Filter by status (pending, fulfilled, cancelled). Default all.
    responses:
      200:
        description: List of first-order gifts
    """
    db = get_user_client()
    q = (
        db.table("first_order_gifts")
        .select("*,profiles(full_name,email,phone),orders(id,total_amount,created_at)")
    )
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
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
            status: {type: string, enum: [fulfilled, cancelled]}
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
    if new_status not in ("fulfilled", "cancelled"):
        return jsonify({"error": MSG.GIFT_INVALID_STATUS}), 400

    update_payload = {"status": new_status}

    db.table("first_order_gifts").eq("id", gift_id).update(update_payload)
    return jsonify({"message": MSG.GIFT_UPDATED, "status": new_status}), 200


# ── System Settings ───────────────────────────────────────────────────────────

def _validator_refusal(exc):
    """The sentence from the database validator, or None if this wasn't it.

    `hg_validate_system_setting` (BEFORE INSERT OR UPDATE on system_settings) is
    the range check for every numeric setting. When it refuses a value it RAISEs
    with a message written for the person editing it ("... must be between 0 and
    1"), which Postgres reports as code P0001 — and the app-wide error handler can
    only turn that into a generic 400/500, so the admin sees "Something went
    wrong" instead of the reason. The settings routes catch it here and hand the
    sentence through verbatim.

    Everything else — RLS denial, a missing column, the network — returns None and
    falls through to the global handler unchanged, so this cannot become a way to
    surface arbitrary database text.
    """
    details = exc.details if isinstance(getattr(exc, "details", None), dict) else {}
    code = str(details.get("code") or "")
    message = str(exc) or ""
    hint = str(details.get("hint") or "")
    if code == "P0001" or "hg_validate_system_setting" in message or "hg_validate_system_setting" in hint:
        return message or MSG.SETTING_VALUE_REJECTED
    return None


def require_settings_write_permission(g, jsonify, campus_id):
    """Insert after reading campus_id from the request body, at the top of any
    system_settings admin-write route. Global settings (campus_id is None) stay
    super_admin-only; campus-scoped settings can also be edited by that campus's
    own admin, matching the live RLS policy."""
    if g.user_role == "super_admin":
        return None
    if campus_id and g.user_role == "admin" and getattr(g, "campus_id", None) == campus_id:
        return None
    return jsonify({"error": MSG.SETTINGS_WRITE_FORBIDDEN}), 403


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
    db = get_user_client()
    data = request.get_json(force=True) or {}
    campus_id = data.get("campus_id")
    auth_err = require_settings_write_permission(g, jsonify, campus_id)
    if auth_err:
        return auth_err

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
                return jsonify({"error": MSG.HP_MULTIPLIER_INVALID}), 400
        except (TypeError, ValueError):
            return jsonify({"error": MSG.HP_MULTIPLIER_INVALID}), 400
    if key == "squad_hp_bonus_pct":
        try:
            iv = int(str(value))
            if iv < 0 or iv > 100:
                return jsonify({"error": "squad_hp_bonus_pct must be an integer between 0 and 100"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "squad_hp_bonus_pct must be an integer between 0 and 100"}), 400

    update_payload = {
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": g.user_id,
    }
    if "description" in data:
        update_payload["description"] = data["description"]
    # is_public decides whether students can read this key at all: the public
    # config route (GET /storefront/config/public) is the ONLY settings source
    # available to a signed-out visitor, and it filters on this flag. The admin
    # screen shows a Public/Private badge per row and toggles it here.
    if "is_public" in data:
        update_payload["is_public"] = bool(data["is_public"])

    q = db.table("system_settings").eq("key", key)
    q = q.is_("campus_id", "null") if not campus_id else q.eq("campus_id", campus_id)
    try:
        q.update(update_payload)
    except SupabaseError as exc:
        refusal = _validator_refusal(exc)
        if refusal is None:
            raise
        logger.warning("settings: %s refused by hg_validate_system_setting: %s", key, refusal)
        return jsonify({"error": refusal}), 400

    # When hp_multiplier is set above 1, broadcast to the affected users immediately
    # (that campus's users for a per-campus change, everyone for a global one)
    if key == "hp_multiplier":
        try:
            mult_val = float(str(value))
            if mult_val > 1.0:
                _broadcast_multiplier_event(db, mult_val, campus_id=campus_id)
        except Exception as exc:
            # Not critical — the setting is saved regardless — but if this keeps failing
            # nobody is ever told the multiplier went live, so leave a trail.
            logger.warning("multiplier_live: broadcast failed (multiplier=%s, campus=%s): %s",
                           value, campus_id, exc)

    return jsonify({"message": MSG.SETTING_UPDATED, "key": key, "value": str(value)}), 200


def _broadcast_multiplier_event(db, multiplier: float, campus_id: str = None):
    """Send a push + in-app notification to active users when a multiplier event goes live.
    Scoped to campus_id when the multiplier change was per-campus; global when it wasn't."""
    try:
        from app.services.notification_service import send_notification
        from app.messages import MSG
        q = db.table("profiles").select("id").eq("is_active", True)
        if campus_id:
            q = q.eq("campus_id", campus_id)
        users = q.execute() or []
        for user in users:
            try:
                send_notification(
                    user_id=user["id"],
                    notif_type="multiplier_live",
                    title=MSG.MULTIPLIER_LIVE_TITLE,
                    # leave {currency} for send_notification, which resolves it from HP_CURRENCY_NAME
                    body=MSG.MULTIPLIER_LIVE_BODY.format(multiplier=multiplier, currency="{currency}"),
                    channels=["push", "in_app"],
                )
            except Exception as exc:
                # The multiplier is already live; only this user's announcement was lost.
                logger.warning("multiplier_live: notify failed for %s: %s", user["id"], exc)
    except Exception as exc:
        # The whole broadcast failed — e.g. the user lookup itself — so no one was told.
        logger.error("multiplier_live: broadcast aborted (%s): %s", multiplier, exc)


@admin_gifts_bp.route("/settings", methods=["POST"])
@require_role("admin")
def create_setting():
    db = get_user_client()
    data = request.get_json(force=True) or {}
    key = (data.get("key") or "").strip()
    value = data.get("value")
    campus_id = data.get("campus_id")
    auth_err = require_settings_write_permission(g, jsonify, campus_id)
    if auth_err:
        return auth_err
    if not key or value is None:
        return jsonify({"error": MSG.SETTING_KEY_VALUE_REQUIRED}), 400

    existing = read_percampus_setting(db, key, campus_id) if campus_id else read_global_setting(db, key)
    if existing:
        return jsonify({"error": MSG.SETTING_KEY_EXISTS}), 409

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "key": key,
        "value": value,
        "description": data.get("description", ""),
        "campus_id": campus_id,
        "updated_at": now,
        "updated_by": g.user_id,
    }
    # New keys are public unless the caller says otherwise. A private row is
    # invisible to the app it is meant to configure (students read settings
    # only through the public config), which is exactly the trap the WhatsApp
    # number fell into: saved, listed for admins, never used by the button.
    payload["is_public"] = data.get("is_public") is not False
    try:
        try:
            result = db.table("system_settings").insert(payload)
        except SupabaseError as exc:
            # Schema without the column — retry without it rather than failing
            # the create.
            if "is_public" in str(exc) and "is_public" in payload:
                logger.warning("settings: system_settings has no is_public column — creating %s without it", key)
                payload.pop("is_public")
                result = db.table("system_settings").insert(payload)
            else:
                raise
    except SupabaseError as exc:
        refusal = _validator_refusal(exc)
        if refusal is None:
            raise
        logger.warning("settings: new key %s refused by hg_validate_system_setting: %s", key, refusal)
        return jsonify({"error": refusal}), 400
    row = result[0] if isinstance(result, list) else result
    return jsonify({"message": MSG.SETTING_CREATED, "setting": row}), 201
