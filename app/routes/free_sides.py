"""
Free side credit routes.

GET  /api/free-sides          — check my free side credits
POST /api/free-sides/redeem   — redeem a free side credit at checkout
"""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db, get_user_client
from app.messages import MSG, resolve_msg
from app.utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

free_sides_bp = Blueprint("free_sides", __name__)


def _get_free_side_options() -> list:
    """Fetch allowed side options — from system_settings first, then config fallback."""
    try:
        db = get_db()
        row = db.table("system_settings").select("value").eq("key", "free_side_options").is_("campus_id", "null").single().execute()
        if row and row.get("value"):
            import json
            return json.loads(row["value"])
    except Exception:
        pass
    return current_app.config.get("FREE_SIDE_OPTIONS", ["Fries", "Coleslaw", "Plantain", "Gizzard"])


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
    db = get_user_client()

    credits = _active_credits(db, user_id)
    total = sum(r.get("credits_remaining", 0) for r in credits)
    options = _get_free_side_options()

    return jsonify({
        "total_credits": total,
        "credits": credits,
        "available_sides": options,
    }), 200


@free_sides_bp.route("/redeem", methods=["POST"])
@require_auth
def redeem_free_side():
    # Credit consumed here; order attachment happens at checkout
    """
    Redeem one free side credit.
    Body: { "side_choice": "Fries", "order_id": "<uuid>" }
    ---
    tags: [FreeSides]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [side_choice]
          properties:
            side_choice: {type: string}
            order_id: {type: string, format: uuid}
    responses:
      200:
        description: Credit redeemed
      400:
        description: Invalid choice or no credits
    """
    user_id = g.user_id
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}

    order_id = data.get("order_id")
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400

    import uuid as _uuid
    try:
        _uuid.UUID(order_id)
    except (ValueError, TypeError, AttributeError):
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    order = db.table("orders").select("id,user_id").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != user_id:
        return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403

    side_choice = (data.get("side_choice") or "").strip()
    if not side_choice:
        return jsonify({"error": MSG.FREE_SIDE_INVALID_CHOICE}), 400

    options = _get_free_side_options()
    if side_choice not in options:
        return jsonify({"error": MSG.FREE_SIDE_INVALID_CHOICE, "available": options}), 400

    credits = _active_credits(db, user_id)
    if not credits:
        return jsonify({"error": MSG.FREE_SIDE_NO_CREDITS}), 400

    # Use oldest-expiring credit first, try to update atomically using Optimistic Concurrency Control (OCC)
    write_db = get_db()
    success = False
    new_remaining = 0
    credit_row_used = None
    for credit_row in credits:
        try:
            res = write_db.table("free_side_credits") \
                .eq("id", credit_row["id"]) \
                .eq("user_id", user_id) \
                .eq("credits_remaining", credit_row["credits_remaining"]) \
                .update({
                    "credits_remaining": credit_row["credits_remaining"] - 1,
                    "used_at": datetime.now(timezone.utc).isoformat(),
                })
            if res:
                success = True
                new_remaining = credit_row["credits_remaining"] - 1
                credit_row_used = credit_row
                break
        except Exception as e:
            logger.error("redeem_free_side OCC update failed for credit row %s: %s", credit_row["id"], e)
            pass

    if not success:
        return jsonify({"error": "No credits available or concurrent update occurred. Please try again."}), 409

    # Attach free line item to the order in order_items table using service role write_db
    try:
        write_db.table("order_items").insert({
            "order_id": order_id,
            "menu_item_id": None,
            "name_snapshot": f"Free Side ({side_choice})",
            "quantity": 1,
            "price_snapshot": 0.0,
            "hp_earn_snapshot": 0,
            "line_total": 0.0,
            "is_addon": True,
        })
    except Exception as e:
        logger.error("Failed to insert free side line item into order_items: %s", e)
        # Compensate: restore the used credit if order item insertion fails
        try:
            write_db.table("free_side_credits").eq("id", credit_row_used["id"]).update({
                "credits_remaining": credit_row_used["credits_remaining"],
                "used_at": None,
            })
        except Exception as refund_err:
            logger.error("redeem_free_side: refund-on-failure also failed for credit %s: %s", credit_row_used["id"], refund_err)
        return jsonify({"error": "Failed to apply free side to order — your credit has not been used, please try again"}), 500

    return jsonify({
        "message": MSG.FREE_SIDE_REDEEMED,
        "side_choice": side_choice,
        "credits_remaining": new_remaining,
        "order_id": order_id,
    }), 200
