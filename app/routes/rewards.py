"""Rewards store routes — list, redeem, flash sales."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import spend_hp, get_hp_balance, get_user_tier
from app.services.notification_service import send_notification
from app.db import get_db
import uuid
from datetime import datetime, timezone

rewards_bp = Blueprint("rewards", __name__)


@rewards_bp.route("", methods=["GET"])
def list_rewards():
    """
    List active rewards. Optionally filter by category.
    ---
    tags: [Rewards]
    security: []
    parameters:
      - in: query
        name: category
        type: string
      - in: query
        name: available_only
        type: boolean
        default: true
    responses:
      200:
        description: List of rewards
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    q = db.table("rewards").select("*,tiers(name,slug)").eq("is_active", "true")

    category = request.args.get("category")
    if category:
        q = q.eq("category", category)

    q = q.order("hp_cost")
    rewards = q.execute()
    result = []
    for r in rewards:
        qty = r.get("quantity_available")
        redeemed = r.get("quantity_redeemed", 0) or 0
        ends_at = r.get("ends_at")
        if qty is not None and qty - redeemed <= 0:
            continue
        if ends_at and ends_at < now:
            continue
        result.append(r)
    return jsonify(result), 200


@rewards_bp.route("/<reward_id>", methods=["GET"])
def get_reward(reward_id):
    """
    Get reward detail.
    ---
    tags: [Rewards]
    security: []
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      200:
        description: Reward detail
      404:
        description: Not found
    """
    db = get_db()
    reward = db.table("rewards").select("*,tiers(name,slug)").eq("id", reward_id).single().execute()
    if not reward:
        return jsonify({"error": "Reward not found"}), 404
    return jsonify(reward), 200


@rewards_bp.route("/<reward_id>/redeem", methods=["POST"])
@require_auth
def redeem_reward(reward_id):
    """
    Redeem a reward using HP. Checks balance, quantity, tier eligibility.
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      201:
        description: Redemption successful
      400:
        description: Insufficient HP or reward not available
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    reward = db.table("rewards").select("*").eq("id", reward_id).single().execute()
    if not reward or not reward.get("is_active", True):
        return jsonify({"error": "Reward not available"}), 404

    qty = reward.get("quantity_available")
    redeemed = reward.get("quantity_redeemed", 0) or 0
    if qty is not None and qty - redeemed <= 0:
        return jsonify({"error": "Reward is out of stock"}), 400

    ends_at = reward.get("ends_at")
    if ends_at and ends_at < now:
        return jsonify({"error": "Reward has expired"}), 400

    starts_at = reward.get("starts_at")
    if starts_at and starts_at > now:
        return jsonify({"error": "Reward is not yet available"}), 400

    if reward.get("min_tier_id"):
        user_tier = get_user_tier(g.user_id)
        user_tier_order = user_tier["tier"].get("sort_order", 0) if user_tier.get("tier") else 0
        all_tiers = db.table("tiers").select("id,sort_order").execute()
        req_tier = next((t for t in all_tiers if t["id"] == reward["min_tier_id"]), None)
        if req_tier and user_tier_order < req_tier.get("sort_order", 0):
            return jsonify({"error": "Your tier is not high enough to redeem this reward"}), 400

    hp_cost = reward["hp_cost"]
    balance = get_hp_balance(g.user_id)
    if balance["active"] < hp_cost:
        return jsonify({"error": f"Insufficient HP. Need {hp_cost}, have {balance['active']}"}), 400

    redemption = db.table("reward_redemptions").insert({
        "user_id": g.user_id,
        "reward_id": reward_id,
        "hp_cost_snapshot": hp_cost,
        "is_fulfilled": False,
    })
    redemption_row = redemption[0] if isinstance(redemption, list) else redemption
    redemption_id = redemption_row["id"]

    try:
        spend_hp(
            user_id=g.user_id,
            amount=hp_cost,
            reference_id=redemption_id,
            reference_type="reward_redemption",
            notes=f"Redeemed: {reward['name']}",
        )
    except ValueError as e:
        db.table("reward_redemptions").eq("id", redemption_id).delete()
        return jsonify({"error": str(e)}), 400

    if qty is not None:
        db.table("rewards").eq("id", reward_id).update({"quantity_redeemed": redeemed + 1})

    db.table("reward_redemptions").eq("id", redemption_id).update({"hp_transaction_id": None})

    send_notification(
        user_id=g.user_id,
        notif_type="reward_redeemed",
        title=f"Reward Redeemed: {reward['name']}",
        body=f"You spent {hp_cost} HP. Our team will fulfil your reward shortly.",
        reference_id=redemption_id,
        reference_type="reward_redemption",
        channels=["in_app", "email"],
    )

    return jsonify({"redemption": redemption_row, "hp_spent": hp_cost}), 201


@rewards_bp.route("", methods=["POST"])
@require_role("admin")
def create_reward():
    """
    Create a new reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, hp_cost, category]
          properties:
            name: {type: string}
            hp_cost: {type: integer}
            category: {type: string, enum: [food, merch, experience, marketplace]}
            quantity_available: {type: integer}
            min_tier_id: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
    responses:
      201:
        description: Reward created
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["name", "hp_cost", "category"]
    for f in required:
        if data.get(f) is None:
            return jsonify({"error": f"'{f}' is required"}), 400
    data["created_by"] = g.user_id
    data["is_active"] = data.get("is_active", True)
    data["quantity_redeemed"] = 0
    result = db.table("rewards").insert(data)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@rewards_bp.route("/<reward_id>", methods=["PATCH"])
@require_role("admin")
def update_reward(reward_id):
    """
    Update a reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            hp_cost: {type: integer}
            is_active: {type: boolean}
            quantity_available: {type: integer}
            ends_at: {type: string, format: date-time}
    responses:
      200:
        description: Reward updated
    """
    db = get_db()
    data = request.get_json(force=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("rewards").eq("id", reward_id).update(data)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@rewards_bp.route("/redemptions", methods=["GET"])
@require_auth
def my_redemptions():
    """
    Get authenticated user's reward redemption history.
    ---
    tags: [Rewards]
    responses:
      200:
        description: Redemption history
    """
    db = get_db()
    redemptions = (
        db.table("reward_redemptions")
        .select("*,rewards(name,category,hp_cost,image_url)")
        .eq("user_id", g.user_id)
        .order("created_at", ascending=False)
        .execute()
    )
    return jsonify(redemptions), 200
    
