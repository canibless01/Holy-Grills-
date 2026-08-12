"""
Exclusive Spin routes — premium spin wheel with limited prizes.

GET  /api/exclusive-spin          — check my leaderboard reward spin credits
POST /api/exclusive-spin/spin     — consume one reward spin credit and return prize
"""

import random
from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db
from app.messages import MSG, resolve_msg
from app.utils.logger import get_logger
from datetime import datetime, timezone, timedelta

logger = get_logger(__name__)

exclusive_spin_bp = Blueprint("exclusive_spin", __name__)


def _available_spins(db, user_id: str) -> list:
    """Return only non-expired leaderboard reward credits.

    Exclusive spins are intentionally not purchasable. Filtering the source here
    also prevents legacy/admin-created non-leaderboard credits from becoming a
    way around that rule.
    """
    now = datetime.now(timezone.utc).isoformat()
    return (
        db.table("exclusive_spins")
        .select("id,spin_count,source,month,expires_at")
        .eq("user_id", user_id)
        .eq("source", "leaderboard_prize")
        .gt("spin_count", 0)
        .gte("expires_at", now)
        .order("expires_at")
        .execute()
    ) or []


def _spin_prizes() -> list:
    """Load prize table from config. Each entry: {"name": str, "weight": int}."""
    return current_app.config.get("EXCLUSIVE_SPIN_TEMPLATE_ITEMS", [
        {"name": "Free Sausage ×2", "weight": 15},
        {"name": "Free Gizzard ×3", "weight": 15},
        {"name": "Free Side",       "weight": 10},
        {"name": "Free Coleslaw",   "weight": 10},
        {"name": "HP Jackpot +750", "weight": 5},
        {"name": "HP Bolt +300",    "weight": 20},
        {"name": "HP Boost +150",   "weight": 15},
        {"name": "Double HP next order", "weight": 10},
    ])


def _draw_prize(prizes: list) -> str:
    """Weighted random draw. Returns prize name."""
    if not prizes:
        return "HP Boost +50"
    names   = [p["name"]   for p in prizes]
    weights = [p.get("weight", 1) for p in prizes]
    return random.choices(names, weights=weights, k=1)[0]


def _apply_prize(user_id: str, prize_name: str, db) -> None:
    """Award HP prizes automatically; physical prizes are logged for admin fulfilment."""
    hp_map = {
        "HP Jackpot +750": 750,
        "HP Bolt +300":    300,
        "HP Boost +150":   150,
        "HP Boost +50":     50,
    }
    for key, amount in hp_map.items():
        if prize_name == key:
            try:
                from app.services.hp_service import award_active_hp
                award_active_hp(
                    user_id=user_id,
                    amount=amount,
                    source_type="exclusive_spin",
                    reference_type="exclusive_spin",
                    reference_id=prize_name,
                    notes=f"Exclusive Spin prize: {prize_name}",
                )
            except Exception as e:
                logger.warning("_apply_prize: HP award failed for %s: %s", user_id, e)
            return

    if prize_name == "Double HP next order":
        try:
            db.table("profiles").eq("id", user_id).update({"next_order_hp_multiplier": 2})
        except Exception as e:
            logger.warning("_apply_prize: multiplier update failed for %s: %s", user_id, e)


@exclusive_spin_bp.route("", methods=["GET"])
@require_auth
def my_spins():
    """
    Return the authenticated user's available exclusive spin credits.
    ---
    tags: [ExclusiveSpin]
    responses:
      200:
        description: Spin summary
    """
    user_id = g.user_id
    db = get_db()
    spins = _available_spins(db, user_id)
    total = sum(s.get("spin_count", 0) for s in spins)

    return jsonify({
        "total_spins": total,
        "spins": spins,
        "prizes": _spin_prizes(),
    }), 200
@exclusive_spin_bp.route("/spin", methods=["POST"])
@require_auth
def do_spin():
    """
    Consume one exclusive spin credit and return the prize.
    ---
    tags: [ExclusiveSpin]
    responses:
      200:
        description: Spin result with prize name
      400:
        description: No spin credits available
    """
    user_id = g.user_id
    db = get_db()
    spins = _available_spins(db, user_id)

    if not spins:
        return jsonify({"error": MSG.SPIN_NO_CREDITS}), 400

    # Use oldest-expiring spin first
    spin_row = spins[0]
    new_count = spin_row["spin_count"] - 1

    try:
        db.table("exclusive_spins").eq("id", spin_row["id"]).update({"spin_count": new_count})
    except Exception as e:
        logger.error("do_spin: update failed for user %s: %s", user_id, e)
        return jsonify({"error": "Could not record spin — please try again"}), 500

    prizes = _spin_prizes()
    prize  = _draw_prize(prizes)

    # Apply HP prizes instantly; log physical prizes for admin fulfilment
    _apply_prize(user_id, prize, db)

    # Send notification
    try:
        from app.services.notification_service import send_notification
        send_notification(
            user_id=user_id,
            notif_type="exclusive_spin_won",
            template_data={"prize": prize},
        )
    except Exception:
        pass

    return jsonify({
        "message": resolve_msg(MSG.SPIN_SUCCESS, prize=prize),
        "prize": prize,
        "spins_remaining": new_count,
    }), 200


@exclusive_spin_bp.route("/buy", methods=["POST"])
@require_auth
def buy_spin():
    """
    Buy an extra exclusive spin using HP.
    ---
    tags: [ExclusiveSpin]
    responses:
      201:
        description: Spin purchased successfully
      400:
        description: Insufficient HP
    """
    user_id = g.user_id
    db = get_db()

    # Read cost from system_settings or config
    try:
        cost_row = db.table("system_settings").select("value").eq("key", "exclusive_spin_extra_cost").single().execute()
        cost = int(float((cost_row or {}).get("value", "500") or "500"))
    except Exception:
        cost = current_app.config.get("EXCLUSIVE_SPIN_EXTRA_COST", 500)

    from app.services.hp_service import spend_hp
    try:
        spend_hp(user_id, cost, user_id, "exclusive_spin_purchase", f"Purchased extra exclusive spin for {cost} HP")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    now = datetime.now(timezone.utc)
    try:
        val_days = int(current_app.config.get("EXCLUSIVE_SPIN_VALIDITY_DAYS", 30))
    except Exception:
        val_days = 30
    expires_at = (now + timedelta(days=val_days)).isoformat()

    # Insert a new spin record or increment existing
    try:
        # Check if an active leaderboard_prize spin already exists to merge
        existing = db.table("exclusive_spins").select("id,spin_count").eq("user_id", user_id).eq("source", "leaderboard_prize").gte("expires_at", now.isoformat()).execute()
        if existing:
            row = existing[0]
            db.table("exclusive_spins").eq("id", row["id"]).update({"spin_count": row["spin_count"] + 1})
        else:
            db.table("exclusive_spins").insert({
                "user_id": user_id,
                "spin_count": 1,
                "source": "leaderboard_prize",
                "expires_at": expires_at,
            })
    except Exception as e:
        logger.error("buy_spin: insert/update failed: %s", e)
        return jsonify({"error": "Failed to record purchase"}), 500

    try:
        from app.services.notification_service import send_notification
        send_notification(
            user_id=user_id,
            notif_type="hp_spin_extra",
        )
    except Exception:
        pass

    return jsonify({
        "message": resolve_msg(MSG.SPIN_BOUGHT),
        "cost": cost,
        "expires_at": expires_at,
    }), 201
