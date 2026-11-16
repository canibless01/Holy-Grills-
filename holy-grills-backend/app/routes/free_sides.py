from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role, resolve_scoped_campus_id
from app.db import get_user_client, get_db, SupabaseError
from app.messages import MSG, resolve_msg
from app.utils.admin_helpers import as_uuid, as_int, as_bool, as_text, as_instant, get_json_object
from app.utils.upload_urls import is_cms_image_url
import uuid
from app.utils.logger import get_logger
from datetime import datetime, timezone, timedelta

logger = get_logger(__name__)

free_sides_bp = Blueprint("free_sides", __name__)


def _get_free_side_options(db, campus_id) -> list:
    """Fetch admin-curated free side items. Replaces the old system_settings JSON blob —
    items now live in their own table, uploadable from the admin panel."""
    q = db.table("free_side_items").select("id,name,image_url").eq("is_active", "true")
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    return q.execute() or []


def _active_credits(db, user_id: str) -> list:
    """Return non-expired rows from free_side_credits with remaining credits > 0."""
    now = datetime.now(timezone.utc).isoformat()
    q = (
        db.table("free_side_credits")
        .select("id,credits_remaining,source,month,expires_at")
        .eq("user_id", user_id)
        .gt("credits_remaining", 0)
        .gte("expires_at", now)
    )
    campus_id = getattr(g, 'campus_id', None)
    if not campus_id:
        profile = db.table('profiles').select('campus_id').eq('id', user_id).single().execute() or {}
        campus_id = profile.get('campus_id')
    if not campus_id:
        return []
    return q.or_(f"campus_id.eq.{campus_id},campus_id.is.null").order("expires_at").execute() or []


def _validity_days():
    row = get_db().table('system_settings').select('value').eq('key','free_side_credits_validity_days').is_('campus_id','null').single().execute()
    value = row.get('value') if row else current_app.config.get('FREE_SIDE_CREDITS_VALIDITY_DAYS',60)
    return as_int(value,minimum=1,maximum=365)


def _rpc_failure(exc):
    text = str(exc).lower()
    if 'free_side_forbidden' in text:
        return jsonify({'error': MSG.RESOURCE_NOT_FOUND}), 404
    if 'free_side_no_credits' in text:
        return jsonify({'error': MSG.FREE_SIDE_NO_CREDITS}), 400
    if 'free_side_grant_invalid' in text:
        return jsonify({'error': MSG.FREE_SIDE_GRANT_INVALID}), 400
    if any(key in text for key in ('free_side_selection_changed', 'free_side_grant_conflict', '23505', 'duplicate')):
        return jsonify({'error': MSG.FREE_SIDE_SELECTION_CHANGED}), 409
    logger.exception('Free-side operation unavailable')
    return jsonify({'error': MSG.SERVICE_UNAVAILABLE}), 503


def _item_payload(data, required=False):
    safe = {}
    if required or 'name' in data:
        safe['name'] = as_text(data.get('name'), max_len=120)
    if required or 'is_active' in data:
        safe['is_active'] = as_bool(data.get('is_active', True))
    if required or 'image_url' in data:
        image = data.get('image_url')
        if image and not is_cms_image_url(image):
            raise ValueError(MSG.STOREFRONT_IMAGE_PROVIDER_INVALID)
        safe['image_url'] = image or None
    return safe


@free_sides_bp.route("", methods=["GET"])
@require_auth
def my_free_sides():
    """
    Return the authenticated user's free side credit balance and active rows.
    ---
    tags: [FreeSides]
    responses:
      200:
        description: Free side credit summary
    """
    user_id = g.user_id
    from app.services.feature_flags import is_feature_enabled
    if not is_feature_enabled("free_side_credits"):
        return jsonify({"error": resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature="Free side credits")}), 403
    db = get_user_client()
    campus_id = getattr(g, "campus_id", None)

    credits = _active_credits(db, user_id)
    total = sum(r.get("credits_remaining", 0) for r in credits)
    options = _get_free_side_options(db, campus_id)

    return jsonify({
        "total_credits": total,
        "credits": credits,
        "available_sides": options,
        "active_selections": db.table("cart_free_side_selections").select("id,free_side_item_id,free_side_items(id,name,image_url,is_active)").eq("user_id", user_id).order("created_at").order("id").execute() or [],
    }), 200


# ---------------------------------------------------------------------------
# Admin: manage the curated list of free side items
# ---------------------------------------------------------------------------

@free_sides_bp.route("/admin/items", methods=["GET"])
@require_role("admin")
def list_free_side_items():
    """
    List free side items (admin only) — the items shown to users on the cart-selection screen.
    ---
    tags: [Admin, FreeSides]
    parameters:
      - in: query
        name: campus_id
        type: string
        description: super_admin only — filter by campus. Ignored for campus admins (always their own campus).
    responses:
      200:
        description: All free side items visible to this admin's campus scope
    """
    db = get_user_client()
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
    q = db.table("free_side_items").select("*").order("created_at")
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    try:
        return jsonify({"items": q.execute() or [], "validity_days": _validity_days()}), 200
    except Exception as exc:
        return _rpc_failure(exc)


@free_sides_bp.route("/admin/items", methods=["POST"])
@require_role("admin")
def create_free_side_item():
    """
    Create a free side item (admin only).
    ---
    tags: [Admin, FreeSides]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string}
            image_url: {type: string}
            is_active: {type: boolean, default: true}
    responses:
      201:
        description: Free side item created
      400:
        description: name is required
    """
    data = get_json_object()
    if data is None:
        return jsonify({'error': MSG.JSON_OBJECT_REQUIRED}), 400
    try:
        safe = _item_payload(data, required=True)
        campus_id = resolve_scoped_campus_id(data.get('campus_id'))
        intent = as_uuid(data.get('intent_key')) or str(uuid.uuid4())
    except ValueError as exc:
        return jsonify({'error': str(exc) if str(exc)==MSG.STOREFRONT_IMAGE_PROVIDER_INVALID else MSG.FREE_SIDE_ITEM_NAME_REQUIRED}), 400
    db = get_user_client()
    existing = db.table('free_side_items').select('*').eq('id', intent).single().execute()
    if existing:
        if all(existing.get(k)==v for k,v in {**safe,'campus_id':campus_id}.items()):
            return jsonify(existing), 200
        return jsonify({'error': MSG.FREE_SIDE_SELECTION_CHANGED}), 409
    try:
        result = db.table('free_side_items').insert({'id':intent, **safe, 'campus_id':campus_id})
        return jsonify(result[0] if isinstance(result,list) else result), 201
    except SupabaseError as exc:
        if any(marker in str(exc).lower() for marker in ('23505','duplicate')):
            existing = db.table('free_side_items').select('*').eq('id',intent).single().execute()
            if existing and all(existing.get(k)==v for k,v in {**safe,'campus_id':campus_id}.items()):
                return jsonify(existing), 200
        return _rpc_failure(exc)

@free_sides_bp.route("/admin/credits", methods=["POST"])
@require_role("admin")
def admin_grant_free_side_credits():
    # NOTE: the name matters. `grant_free_side_credits(write_db, user_id, count, ...)`
    # further down this file is the service-role helper the jobs use; a route function
    # with that name would shadow it for any `from app.routes.free_sides import ...`
    # and break with a TypeError. Keep this one prefixed with `admin_`.
    """
    Grant free-side credits to one user (admin only).
    Body: { "user_id": "<uuid>", "credits": 1, "validity_days": 60, "reason": "..." }
    ---
    tags: [Admin, FreeSides]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [user_id]
          properties:
            user_id: {type: string, format: uuid}
            credits: {type: integer, default: 1, description: 1-20}
            validity_days: {type: integer, description: "default: the free_side_credits_validity_days setting"}
            reason: {type: string}
    responses:
      201:
        description: Credits granted
      400:
        description: Invalid user or credit count
      404:
        description: User not found in your campus
    """
    from app.middleware.auth import fetch_or_403
    from app.services.notification_service import send_notification
    data = get_json_object()
    if data is None:
        return jsonify({'error': MSG.JSON_OBJECT_REQUIRED}), 400
    try:
        user_id = as_uuid(data.get('user_id'))
        intent = as_uuid(data.get('intent_key'))
        credits = as_int(data.get('credits',1), minimum=1, maximum=20)
        if not user_id or not intent:
            raise ValueError()
        reason = data.get('reason') or MSG.FREE_SIDE_GRANT_REASON
        reason = as_text(reason,max_len=200)
        days = data.get('validity_days')
        if days is None:
            days = _validity_days()
        days = as_int(days,minimum=1,maximum=365)
    except ValueError:
        return jsonify({'error': MSG.FREE_SIDE_GRANT_INVALID}), 400
    except Exception as exc:
        return _rpc_failure(exc)
    target, err = fetch_or_403(get_user_client(), 'profiles', user_id, select='id,campus_id', not_found_msg=MSG.RESOURCE_NOT_FOUND)
    if err:
        return err
    try:
        result = get_db().rpc('hg_grant_free_sides_atomic', {'p_actor_id':g.user_id,'p_user_id':user_id,'p_intent_key':intent,'p_credits':credits,'p_days':days,'p_reason':reason})
    except Exception as exc:
        return _rpc_failure(exc)
    if not result.get('idempotent'):
        try:
            send_notification(user_id=user_id,notif_type='free_side_credits_granted',template_data={'credits':credits,'expires_at':result['expires_at'][:10]},campus_id=target.get('campus_id'),reference_id=result.get('credit_id'),reference_type='free_side_grant')
        except Exception:
            logger.exception('Free-side grant saved but notification unavailable')
    return jsonify({**result,'message':MSG.FREE_SIDE_GRANTED}), 200 if result.get('idempotent') else 201

@free_sides_bp.route("/admin/items/<item_id>", methods=["PATCH"])
@require_role("admin")
def update_free_side_item(item_id):
    """
    Update a free side item (admin only).
    ---
    tags: [Admin, FreeSides]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            name: {type: string}
            image_url: {type: string}
            is_active: {type: boolean}
    responses:
      200:
        description: Free side item updated
      404:
        description: Free side item not found
    """
    data = get_json_object()
    if data is None:
        return jsonify({'error': MSG.JSON_OBJECT_REQUIRED}), 400
    try:
        as_uuid(item_id)
        safe = _item_payload(data)
        if not safe:
            raise ValueError()
        expected_updated_at = as_instant(data['expected_updated_at']) if data.get('expected_updated_at') else None
    except ValueError as exc:
        return jsonify({'error': str(exc) if str(exc)==MSG.STOREFRONT_IMAGE_PROVIDER_INVALID else MSG.FREE_SIDE_ITEM_NAME_REQUIRED}), 400
    db = get_user_client()
    query = db.table('free_side_items').eq('id',item_id)
    if expected_updated_at:
        query = query.eq('updated_at',expected_updated_at)
    result = query.update(safe)
    if not result:
        return jsonify({'error': MSG.FREE_SIDE_SELECTION_CHANGED}), 409
    return jsonify(result[0] if isinstance(result,list) else result), 200

@free_sides_bp.route("/admin/items/<item_id>", methods=["DELETE"])
@require_role("admin")
def delete_free_side_item(item_id):
    """
    Deactivate a free side item (admin only). Soft-delete — the item stops showing to users
    but past cart selections / order_items referencing it are preserved.
    ---
    tags: [Admin, FreeSides]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: Free side item deactivated
      404:
        description: Free side item not found
    """
    try:
        as_uuid(item_id)
    except ValueError:
        return jsonify({'error': MSG.FREE_SIDE_ITEM_NOT_FOUND}), 404
    db = get_user_client()
    result = db.table("free_side_items").eq("id", item_id).update({"is_active": False})
    if not result:
        return jsonify({"error": MSG.FREE_SIDE_ITEM_NOT_FOUND}), 404
    return jsonify({"message": MSG.FREE_SIDE_DEACTIVATED}), 200


# ---------------------------------------------------------------------------
# Cart-stage selection — replaces the old post-order /redeem flow. A user picks
# free sides while building their cart; credits are consumed once at checkout,
# inside the order admission transaction.
# ---------------------------------------------------------------------------

@free_sides_bp.route("/select", methods=["POST"])
@require_auth
def select_free_side():
    """
    Add a free side item to the user's cart selection.
    Body: { "free_side_item_id": "<uuid>" }
    ---
    tags: [FreeSides]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [free_side_item_id]
          properties:
            free_side_item_id: {type: string, format: uuid}
    responses:
      201:
        description: Selection added
      400:
        description: Missing item id, or no credit available for another selection
      404:
        description: Free side item not found
    """
    from app.services.feature_flags import is_feature_enabled
    if not is_feature_enabled('free_side_credits'):
        return jsonify({'error': resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature='Free side credits')}), 403
    data = get_json_object()
    if data is None:
        return jsonify({'error': MSG.JSON_OBJECT_REQUIRED}), 400
    try:
        item_id = as_uuid(data.get('free_side_item_id'))
        intent = as_uuid(data.get('intent_key')) or str(uuid.uuid4())
        replace_id = as_uuid(data.get('replace_selection_id'))
        if not item_id:
            raise ValueError()
    except ValueError:
        return jsonify({'error': MSG.FREE_SIDE_SELECTION_REQUIRED}), 400
    try:
        result = get_db().rpc('hg_select_free_side_atomic',{'p_user_id':g.user_id,'p_campus_id':getattr(g,'campus_id',None),'p_item_id':item_id,'p_intent_key':intent,'p_replace_id':replace_id})
        return jsonify(result), 200 if result.get('idempotent') else 201
    except Exception as exc:
        return _rpc_failure(exc)

@free_sides_bp.route("/select/<selection_id>", methods=["DELETE"])
@require_auth
def deselect_free_side(selection_id):
    """
    Remove a free side item from the user's cart selection.
    ---
    tags: [FreeSides]
    parameters:
      - in: path
        name: selection_id
        type: string
        required: true
    responses:
      200:
        description: Selection removed
      404:
        description: Selection not found
    """
    try:
        as_uuid(selection_id)
    except ValueError:
        return jsonify({'error': MSG.RESOURCE_NOT_FOUND}), 404
    db = get_db()
    result = db.table("cart_free_side_selections").eq("id", selection_id).eq("user_id", g.user_id).delete()
    if not result:
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    return jsonify({"message": MSG.FREE_SIDE_REMOVED}), 200


# ---------------------------------------------------------------------------
# Shared service-role grants used by scheduled reward jobs. Checkout consumption
# lives only in the order-admission transaction.
# ---------------------------------------------------------------------------

def grant_free_side_credits(write_db, user_id: str, count: int, campus_id, source: str, validity_days: int = 30) -> list:
    """Grant `count` free side credits to a user. For the monthly leaderboard #1-3 prize and the
    tier exclusive_spins-style monthly perk (grant_monthly_tier_perks in scheduled.py) to call —
    that function's own attempt to grant free_side_credits inserts a 'status' column that does
    not exist on this table (confirmed against the live schema) and would fail; this uses the
    real columns instead. One row per credit, matching the existing pattern elsewhere in this
    domain (grant_monthly_tier_perks already loops one insert per unit rather than a single row
    with a quantity column). Service role required — write_db, not get_user_client()."""
    if count <= 0:
        return []
    expires_at = (datetime.now(timezone.utc) + timedelta(days=validity_days)).isoformat()
    granted = []
    for _ in range(int(count)):
        row = write_db.table("free_side_credits").insert({
            "user_id": user_id,
            "credits_remaining": 1,
            "source": source,
            "campus_id": campus_id,
            "expires_at": expires_at,
        })
        granted.append(row[0] if isinstance(row, list) and row else row)
    return granted
