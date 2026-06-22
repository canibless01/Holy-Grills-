"""Challenge routes — list, complete, admin management."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import earn_pending_hp
from app.db import get_db
from datetime import datetime, timezone

challenges_bp = Blueprint("challenges", __name__)


@challenges_bp.route("", methods=["GET"])
def list_challenges():
    """
    List active challenges.
    ---
    tags: [Challenges]
    security: []
    responses:
      200:
        description: Active challenges
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    challenges = (
        db.table("challenges")
        .select("*")
        .eq("is_active", "true")
        .lte("starts_at", now)
        .gte("ends_at", now)
        .execute()
    )
    return jsonify(challenges), 200


@challenges_bp.route("/<challenge_id>/complete", methods=["POST"])
@require_auth
def complete_challenge(challenge_id):
    """
    Mark a challenge as completed. Calls atomic RPC, awards HP to pending pool.
    ---
    tags: [Challenges]
    parameters:
      - in: path
        name: challenge_id
        type: string
        required: true
    responses:
      200:
        description: Challenge completed, HP earned
      400:
        description: Already completed or not eligible
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    challenge = (
        db.table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .eq("is_active", "true")
        .single()
        .execute()
    )
    if not challenge:
        return jsonify({"error": "Challenge not found or inactive"}), 404

    if challenge.get("ends_at") < now:
        return jsonify({"error": "Challenge has ended"}), 400

    existing = (
        db.table("challenge_completions")
        .select("id")
        .eq("user_id", g.user_id)
        .eq("challenge_id", challenge_id)
        .execute()
    )
    max_completions = challenge.get("max_completions_per_user", 1) or 1
    if len(existing) >= max_completions:
        return jsonify({"error": "Challenge already completed (max completions reached)"}), 400

    hp_reward = min(challenge.get("hp_reward", 0), 100)

    hp_result = earn_pending_hp(
        user_id=g.user_id,
        amount=hp_reward,
        source_type="challenge",
        reference_id=challenge_id,
        notes=f"Challenge: {challenge.get('title', '')}",
    )

    completion = db.table("challenge_completions").insert({
        "user_id": g.user_id,
        "challenge_id": challenge_id,
        "hp_awarded": hp_result["added_to_pending"],
    })
    completion_row = completion[0] if isinstance(completion, list) else completion

    from app.services.notification_service import send_notification
    send_notification(
        user_id=g.user_id,
        notif_type="challenge_complete",
        title=f"Challenge Complete: {challenge.get('title', '')}",
        body=f"You earned {hp_result['added_to_pending']} HP (pending). Order food to unlock!",
        channels=["in_app"],
    )

    return jsonify({
        "completion": completion_row,
        "hp_added_to_pending": hp_result["added_to_pending"],
    }), 200


@challenges_bp.route("", methods=["POST"])
@require_role("admin")
def create_challenge():
    """
    Create a new challenge (admin only).
    ---
    tags: [Challenges]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, hp_reward, starts_at, ends_at, type]
          properties:
            title: {type: string}
            description: {type: string}
            type: {type: string, enum: [weekly_streak, social_share, review, order_milestone, referral, monthly_challenge]}
            hp_reward: {type: integer, maximum: 100}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
            max_completions_per_user: {type: integer, default: 1}
            criteria: {type: object}
    responses:
      201:
        description: Challenge created
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["title", "hp_reward", "starts_at", "ends_at", "type"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400
    if int(data["hp_reward"]) > 100:
        return jsonify({"error": "HP reward cannot exceed 100 HP per challenge"}), 400
    data["created_by"] = g.user_id
    data["is_active"] = data.get("is_active", False)
    result = db.table("challenges").insert(data)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@challenges_bp.route("/<challenge_id>", methods=["PATCH"])
@require_role("admin")
def update_challenge(challenge_id):
    """
    Update/activate/deactivate a challenge (admin only).
    ---
    tags: [Challenges]
    parameters:
      - in: path
        name: challenge_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            is_active: {type: boolean}
            hp_reward: {type: integer}
            ends_at: {type: string, format: date-time}
    responses:
      200:
        description: Challenge updated
    """
    db = get_db()
    data = request.get_json(force=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("challenges").eq("id", challenge_id).update(data)
    return jsonify(result[0] if isinstance(result, list) else result), 200
