from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role, resolve_scoped_campus_id
from app.db import get_db, get_user_client
from app.messages import MSG, resolve_msg
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
    if campus_id:
        q = q.eq("campus_id", campus_id)
    return q.order("expires_at").execute() or []


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
    return jsonify({"items": q.execute() or []}), 200


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
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    result = db.table("free_side_items").insert({
        "name": data["name"], "image_url": data.get("image_url"),
        "is_active": bool(data.get("is_active", True)), "campus_id": getattr(g, "campus_id", None),
    })
    return jsonify(result[0] if isinstance(result, list) else result), 201


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
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    safe = {k: v for k, v in data.items() if k in ("name", "image_url", "is_active")}
    result = db.table("free_side_items").eq("id", item_id).update(safe)
    if not result:
        return jsonify({"error": "Free side item not found"}), 404
    return jsonify(result[0] if isinstance(result, list) else result), 200


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
    db = get_user_client()
    result = db.table("free_side_items").eq("id", item_id).update({"is_active": False})
    if not result:
        return jsonify({"error": "Free side item not found"}), 404
    return jsonify({"message": "Deactivated"}), 200


# ---------------------------------------------------------------------------
# Cart-stage selection — replaces the old post-order /redeem flow. A user picks
# free sides while building their cart; credits are actually consumed once at
# checkout by consume_free_side_selections() (called from order_service.create_order()).
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
    if not is_feature_enabled("free_side_credits"):
        return jsonify({"error": resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature="Free side credits")}), 403
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    item_id = data.get("free_side_item_id")
    if not item_id:
        return jsonify({"error": "free_side_item_id is required"}), 400
    campus_id = getattr(g, "campus_id", None)
    item = db.table("free_side_items").select("id,campus_id").eq("id", item_id).eq("is_active", "true").single().execute()
    if not item or (campus_id and item.get("campus_id") not in (campus_id, None)):
        return jsonify({"error": "Free side item not found"}), 404
    credits = _active_credits(db, g.user_id)
    available = sum(c["credits_remaining"] for c in credits)
    current_selections = db.table("cart_free_side_selections").select("id", count="exact").eq("user_id", g.user_id).execute()
    current_count = current_selections.get("count", 0) if isinstance(current_selections, dict) else len(current_selections or [])
    if current_count >= available:
        return jsonify({"error": MSG.FREE_SIDE_NO_CREDITS}), 400
    result = db.table("cart_free_side_selections").insert({
        "user_id": g.user_id, "free_side_item_id": item_id, "campus_id": campus_id,
    })
    return jsonify(result[0] if isinstance(result, list) else result), 201


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
    db = get_user_client()
    result = db.table("cart_free_side_selections").eq("id", selection_id).eq("user_id", g.user_id).delete()
    if not result:
        return jsonify({"error": "Selection not found"}), 404
    return jsonify({"message": "Removed"}), 200


# ---------------------------------------------------------------------------
# Shared consumption path — the ONE place a free-side credit is actually spent.
# Called by order_service.create_order() at checkout (wiring lives in that file,
# not here — order_service.py is outside this pass).
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


def consume_free_side_selections(write_db, user_id: str, campus_id, order_id: str) -> list:
    """Mirrors the existing OCC credit-decrement pattern already proven in this
    domain (spin credits, the old redeem_free_side). Returns inserted order_items rows.
    Checks the free_side_credits feature flag itself (rather than relying on the caller
    to check it) since this is the one place a credit is actually spent — not yet wired
    into order_service.create_order() as of this pass; see CROSS_FILE_DEPENDENCIES.md."""
    from app.services.feature_flags import is_feature_enabled
    if not is_feature_enabled("free_side_credits"):
        return []
    selections = write_db.table("cart_free_side_selections").select("id,free_side_item_id").eq("user_id", user_id).execute() or []
    inserted = []
    for sel in selections:
        credits = _active_credits(write_db, user_id)
        consumed = False
        for credit_row in credits:
            res = (
                write_db.table("free_side_credits")
                .eq("id", credit_row["id"]).eq("credits_remaining", credit_row["credits_remaining"])
                .update({"credits_remaining": credit_row["credits_remaining"] - 1, "used_at": datetime.now(timezone.utc).isoformat()})
            )
            if res:
                consumed = True
                break
        if not consumed:
            continue  # ran out of credits mid-checkout; leave this selection unconsumed
        item = write_db.table("free_side_items").select("name").eq("id", sel["free_side_item_id"]).single().execute()
        row = write_db.table("order_items").insert({
            "order_id": order_id, "name_snapshot": item.get("name", "Free side") if item else "Free side",
            "quantity": 1, "price_snapshot": 0, "line_total": 0, "is_addon": False,
        })
        inserted.append(row[0] if isinstance(row, list) else row)
        write_db.table("cart_free_side_selections").eq("id", sel["id"]).delete()
    return inserted
