"""
Challenge & Milestone routes.

GET    /challenges                  — active challenges (time_window IS NOT NULL)
POST   /challenges/<id>/complete    — verify against real data + award HP
GET    /challenges/badges           — list all badges (time_window IS NULL)
GET    /challenges/my               — user's full milestones progress
POST   /challenges/social-follow    — self-declared social follow (one-time, pending)

Admin:
GET    /challenges/admin            — all milestones (admin)
POST   /challenges/admin            — create milestone
PATCH  /challenges/admin/<id>       — update milestone
DELETE /challenges/admin/<id>       — deactivate milestone
POST   /challenges/admin/<id>/grant — grant milestone to specific user
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.db import get_db
from app.messages import MSG
from datetime import datetime, timezone

challenges_bp = Blueprint("challenges", __name__)


@challenges_bp.route("", methods=["GET"])
def list_challenges():
    """
    List active challenges (milestones with time_window set).
    ---
    tags: [Challenges]
    security: []
    parameters:
      - in: query
        name: time_window
        type: string
        enum: [weekly, monthly]
        description: Filter by period type; omit to return all active challenges
    responses:
      200:
        description: Active challenges
    """
    db = get_db()
    q = (
        db.table("milestones")
        .select("id,title,description,trigger_type,trigger_value,hp_awarded,time_window,icon_won,icon_locked")
        .eq("is_active", "true")
        .not_.is_("time_window", "null")
    )
    tw = request.args.get("time_window")
    if tw in ("weekly", "monthly"):
        q = q.eq("time_window", tw)
    rows = q.order("hp_awarded", ascending=False).execute() or []
    return jsonify(rows), 200


@challenges_bp.route("/badges", methods=["GET"])
def list_badges():
    """
    List all badges (lifetime milestones, time_window IS NULL).
    ---
    tags: [Challenges]
    security: []
    responses:
      200:
        description: All badge definitions
    """
    db = get_db()
    rows = (
        db.table("milestones")
        .select("id,title,description,trigger_type,trigger_value,hp_awarded,icon_won,icon_locked")
        .eq("is_active", "true")
        .is_("time_window", "null")
        .order("hp_awarded", ascending=False)
        .execute()
    ) or []
    return jsonify(rows), 200


@challenges_bp.route("/my", methods=["GET"])
@require_auth
def my_milestones():
    """
    Get the authenticated user's full milestone progress (badges + challenges).
    ---
    tags: [Challenges]
    responses:
      200:
        description: User's milestone progress
    """
    from app.services.milestone_service import get_user_milestones
    try:
        result = get_user_milestones(g.user_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@challenges_bp.route("/<milestone_id>/complete", methods=["POST"])
@require_auth
def complete_challenge(milestone_id):
    """
    Attempt to complete a challenge or claim a badge.
    Verifies progress against real data tables — no button-click free awards.
    ---
    tags: [Challenges]
    parameters:
      - in: path
        name: milestone_id
        type: string
        required: true
    responses:
      200:
        description: Milestone completed, HP earned
      400:
        description: Not eligible or already completed
      404:
        description: Milestone not found
    """
    from app.services.milestone_service import check_and_award_milestone
    try:
        result = check_and_award_milestone(g.user_id, milestone_id)
        if result.get("already_completed"):
            return jsonify({"message": "Already completed this milestone"}), 200
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@challenges_bp.route("/social-follow", methods=["POST"])
@require_auth
def social_follow():
    """
    Self-declare a social follow (one-time, HP → Pending, subject to monthly cap).
    The post/share challenge type has been removed; use this for social_follow badges only.
    ---
    tags: [Challenges]
    responses:
      200:
        description: Social follow recorded
      400:
        description: Already recorded
    """
    db = get_db()

    # Find the social_follow milestone
    milestone = (
        db.table("milestones")
        .select("id,hp_awarded,title,social_link")
        .eq("trigger_type", "social_follow")
        .eq("is_active", "true")
        .single()
        .execute()
    )
    if not milestone:
        return jsonify({"error": MSG.SOCIAL_FOLLOW_NOT_CONFIGURED}), 404

    from app.services.milestone_service import check_and_award_milestone
    try:
        result = check_and_award_milestone(g.user_id, milestone["id"])
        if result.get("already_completed"):
            return jsonify({"message": MSG.SOCIAL_FOLLOW_ALREADY_DONE, "already_done": True}), 200
        return jsonify({
            "message": "Social follow recorded",
            "hp_added_to_pending": result.get("hp_awarded", 0),
            "social_link": milestone.get("social_link"),
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Admin endpoints ───────────────────────────────────────────────────────────

@challenges_bp.route("/admin", methods=["GET"])
@require_role("admin")
def admin_list_milestones():
    """
    List all milestones (admin).
    ---
    tags: [Challenges]
    parameters:
      - in: query
        name: time_window
        type: string
        description: Filter by 'weekly', 'monthly', or 'none' (badges)
      - in: query
        name: is_active
        type: boolean
      - in: query
        name: limit
        type: integer
        default: 50
    responses:
      200:
        description: All milestones
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("milestones").select("*")
    tw = request.args.get("time_window")
    if tw == "none":
        q = q.is_("time_window", "null")
    elif tw in ("weekly", "monthly"):
        q = q.eq("time_window", tw)
    is_active = request.args.get("is_active")
    if is_active is not None:
        q = q.eq("is_active", is_active.lower() == "true")
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"milestones": rows, "count": len(rows)}), 200


@challenges_bp.route("/admin", methods=["POST"])
@require_role("admin")
def admin_create_milestone():
    """
    Create a new milestone (admin).
    trigger_type: see module docstring for valid values.
    time_window: null = lifetime badge; 'weekly'/'monthly' = recurring challenge.
    ---
    tags: [Challenges]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, trigger_type, trigger_value, hp_awarded]
          properties:
            title: {type: string}
            description: {type: string}
            trigger_type: {type: string}
            trigger_value: {type: integer}
            hp_awarded: {type: integer}
            time_window: {type: string, enum: [weekly, monthly]}
            icon_won: {type: string}
            icon_locked: {type: string}
    responses:
      201:
        description: Milestone created
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    required = ["title", "trigger_type", "trigger_value", "hp_awarded"]
    for f in required:
        if data.get(f) is None:
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400
    if data.get("time_window") and data["time_window"] not in ("weekly", "monthly"):
        return jsonify({"error": MSG.CHALLENGE_TIME_WINDOW_INVALID}), 400

    ALLOWED = {"title", "description", "trigger_type", "trigger_value", "hp_awarded",
               "time_window", "icon_won", "icon_locked", "is_active", "social_link"}
    safe = {k: v for k, v in data.items() if k in ALLOWED}
    safe["created_by"] = g.user_id
    safe.setdefault("is_active", False)
    try:
        result = db.table("milestones").insert(safe)
    except Exception as exc:
        return jsonify({"error": str(exc)[:200]}), 400
    return jsonify(result[0] if isinstance(result, list) else result), 201


@challenges_bp.route("/admin/<milestone_id>", methods=["PATCH"])
@require_role("admin")
def admin_update_milestone(milestone_id):
    """
    Update a milestone (admin).
    ---
    tags: [Challenges]
    parameters:
      - in: path
        name: milestone_id
        type: string
        required: true
    responses:
      200:
        description: Milestone updated
      404:
        description: Not found
    """
    db = get_db()
    if not db.table("milestones").select("id").eq("id", milestone_id).limit(1).execute():
        return jsonify({"error": MSG.CHALLENGE_NOT_FOUND}), 404
    data = request.get_json(force=True) or {}
    ALLOWED = {
        "title", "description", "trigger_type", "trigger_value", "hp_awarded",
        "time_window", "icon_won", "icon_locked", "is_active", "social_link",
    }
    safe = {k: v for k, v in data.items() if k in ALLOWED}
    if not safe:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    safe["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("milestones").eq("id", milestone_id).update(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@challenges_bp.route("/admin/<milestone_id>", methods=["DELETE"])
@require_role("admin")
def admin_delete_milestone(milestone_id):
    """
    Deactivate (soft-delete) a milestone (admin).
    ---
    tags: [Challenges]
    parameters:
      - in: path
        name: milestone_id
        type: string
        required: true
    responses:
      200:
        description: Milestone deactivated
      404:
        description: Not found
    """
    db = get_db()
    if not db.table("milestones").select("id").eq("id", milestone_id).limit(1).execute():
        return jsonify({"error": MSG.CHALLENGE_NOT_FOUND}), 404
    db.table("milestones").eq("id", milestone_id).update({"is_active": False})
    return jsonify({"message": MSG.CHALLENGE_DEACTIVATED, "milestone_id": milestone_id}), 200


@challenges_bp.route("/admin/<milestone_id>/grant", methods=["POST"])
@require_role("admin")
def admin_grant_milestone(milestone_id):
    """
    Manually grant a milestone to a user (admin).
    Used for department_leader, faculty_leader, and other admin-only milestones.
    ---
    tags: [Challenges]
    parameters:
      - in: path
        name: milestone_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [user_id]
          properties:
            user_id: {type: string}
    responses:
      200:
        description: Milestone granted
    """
    data = request.get_json(force=True) or {}
    target_user_id = data.get("user_id", "").strip()
    if not target_user_id:
        return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field="user_id")}), 400

    from app.services.milestone_service import admin_grant_milestone as _grant
    try:
        result = _grant(admin_id=g.user_id, user_id=target_user_id, milestone_id=milestone_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
