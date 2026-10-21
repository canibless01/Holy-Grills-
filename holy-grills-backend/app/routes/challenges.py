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
from app.middleware.auth import require_auth, require_role, optional_auth
from app.db import get_user_client
from app.messages import MSG, resolve_msg
from app.utils.logger import get_logger
from app.utils.campus_scope import as_campus_id, public_campus, resolve_write_campus, assert_can_modify
from datetime import datetime, timezone

logger = get_logger(__name__)

challenges_bp = Blueprint("challenges", __name__)


def _requested_campus_id():
    """Guests have no g.campus_id, so they choose a campus; signed-in users default to their own.
    Reads ?campus_id= then the X-Campus-ID header -- the same two sources and priority order
    app/routes/events.py's _get_campus_id() uses, and menu.py / storefront.py already follow, so a
    guest's campus choice (however the frontend sends it) works the same way across every browse route.
    Raises ValueError for anything that is not a UUID: unlike _get_campus_id(), this value goes into a
    raw PostgREST or= filter string (see campus_or_global), so it needs that validation regardless of
    which upstream helper resolved the candidate value."""
    raw = request.args.get("campus_id") or request.headers.get("X-Campus-ID")
    return public_campus(as_campus_id(raw))


MILESTONE_ALLOWED_FIELDS = {
    "title", "description", "trigger_type", "trigger_value", "hp_awarded",
    "time_window", "icon_won", "icon_locked", "is_active", "social_link", "campus_id"
}


def _milestone_fields(data, *, creating=False):
    """Keep admin configuration valid before persistence, including partial edits."""
    if not isinstance(data, dict):
        raise ValueError(MSG.CHALLENGE_CONFIG_INVALID)
    if creating:
        for key in ("title", "trigger_type", "trigger_value", "hp_awarded"):
            if key not in data:
                raise ValueError(MSG.AUTH_FIELD_REQUIRED.format(field=key))
    safe = {key: value for key, value in data.items() if key in MILESTONE_ALLOWED_FIELDS}
    for key in ("title", "description", "icon_won", "icon_locked", "social_link"):
        if key not in safe:
            continue
        value = safe[key]
        if value is None and key != "title":
            continue  # Optional copy/artwork fields may be cleared.
        if not isinstance(value, str) or len(value) > (240 if key == "title" else 4000):
            raise ValueError(MSG.CHALLENGE_CONFIG_INVALID)
        safe[key] = value.strip()
    if "title" in safe and not safe["title"]:
        raise ValueError(MSG.AUTH_FIELD_REQUIRED.format(field="title"))
    for key, minimum in (("trigger_value", 1), ("hp_awarded", 0)):
        if key in safe and (isinstance(safe[key], bool) or not isinstance(safe[key], int)
                            or not minimum <= safe[key] <= 2147483647):
            raise ValueError(MSG.CHALLENGE_CONFIG_INVALID)
    if "is_active" in safe and not isinstance(safe["is_active"], bool):
        raise ValueError(MSG.CHALLENGE_CONFIG_INVALID)
    if "time_window" in safe and safe["time_window"] not in (None, "weekly", "monthly"):
        raise ValueError(MSG.CHALLENGE_TIME_WINDOW_INVALID)
    if "trigger_type" in safe:
        from app.services.milestone_service import VALID_TRIGGER_TYPES
        if not isinstance(safe["trigger_type"], str) or safe["trigger_type"] not in VALID_TRIGGER_TYPES:
            raise ValueError(resolve_msg(MSG.MILESTONE_TRIGGER_TYPE_INVALID, valid=", ".join(sorted(VALID_TRIGGER_TYPES))))
    if safe.get("social_link"):
        from urllib.parse import urlparse
        try:
            link = urlparse(safe["social_link"])
            valid = (link.scheme == "https" and bool(link.hostname) and not link.username
                     and not link.password and link.port in (None, 443)
                     and not any(char.isspace() for char in safe["social_link"]))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(MSG.CHALLENGE_CONFIG_INVALID)
    return safe


def _saved_milestone(result):
    return result[0] if isinstance(result, list) and result else result if isinstance(result, dict) else None


@challenges_bp.route("", methods=["GET"])
@optional_auth
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
    db = get_user_client()
    q = (
        db.table("milestones")
        .select("id,title,description,trigger_type,trigger_value,hp_awarded,time_window,icon_won,icon_locked")
        .eq("is_active", True)
        .not_.is_("time_window", "null")
    )
    try:
        campus_id = _requested_campus_id()
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    elif getattr(g, "user_role", None) != "super_admin":
        q = q.is_("campus_id", "null")
    tw = request.args.get("time_window")
    if tw in ("weekly", "monthly"):
        q = q.eq("time_window", tw)
    rows = q.order("hp_awarded", ascending=False).execute() or []
    return jsonify(rows), 200


@challenges_bp.route("/badges", methods=["GET"])
@optional_auth
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
    db = get_user_client()
    q = (
        db.table("milestones")
        .select("id,title,description,trigger_type,trigger_value,hp_awarded,icon_won,icon_locked")
        .eq("is_active", True)
        .is_("time_window", "null")
    )
    try:
        campus_id = _requested_campus_id()
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    elif getattr(g, "user_role", None) != "super_admin":
        q = q.is_("campus_id", "null")
    rows = q.order("hp_awarded", ascending=False).execute() or []
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
        return jsonify(result), 200
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
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
    db = get_user_client()

    # Find the social_follow milestone
    m_rows = (
        db.table("milestones")
        .select("id,hp_awarded,title,social_link")
        .eq("trigger_type", "social_follow")
        .eq("is_active", "true")
        .order("created_at", ascending=True)
        .limit(1)
        .execute()
    ) or []
    milestone = m_rows[0] if m_rows else None
    if not milestone:
        return jsonify({"error": MSG.SOCIAL_FOLLOW_NOT_CONFIGURED}), 404

    from app.services.milestone_service import check_and_award_milestone
    try:
        result = check_and_award_milestone(g.user_id, milestone["id"])
        if result.get("already_completed"):
            return jsonify({"error": MSG.SOCIAL_FOLLOW_ALREADY_DONE, "already_done": True}), 400
        return jsonify({
            "message": "Social follow recorded",
            "hp_added_to_pending": result.get("hp_awarded", 0),
            "social_link": milestone.get("social_link"),
        }), 200
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@challenges_bp.route("/pwa-installed", methods=["POST"])
@require_auth
def pwa_installed():
    """
    Claim PWA installation system milestone reward.
    ---
    tags: [Challenges]
    responses:
      200:
        description: PWA install milestone status or claim result
    """
    db = get_user_client()
    m_rows = (
        db.table("milestones")
        .select("id,title")
        .eq("trigger_type", "pwa_install")
        .eq("is_active", "true")
        .limit(1)
        .execute()
    ) or []
    milestone = m_rows[0] if m_rows else None
    if not milestone:
        return jsonify({"error": "PWA install milestone not configured or inactive"}), 404

    from app.services.milestone_service import check_and_award_milestone, check_and_award_pwa_push_bonus
    try:
        result = check_and_award_milestone(g.user_id, milestone["id"])
        # Check if PWA + Push bonus is now eligible
        check_and_award_pwa_push_bonus(g.user_id)
        already_completed = bool(result.get("already_completed"))
        hp_awarded = int(result.get("hp_awarded") or 0) if not already_completed else 0
        return jsonify({
            "success": True,
            "milestone": "pwa_install",
            "hp_awarded": hp_awarded,
            "already_completed": already_completed,
            "message": MSG.PWA_INSTALL_RECORDED,
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("pwa_installed: failed for %s: %s", g.user_id, e)
        return jsonify({"error": MSG.ERR_UNEXPECTED}), 500


@challenges_bp.route("/push-subscribed", methods=["POST"])
@require_auth
def push_subscribed_challenge():
    """
    Register Web Push subscription and claim push subscription system milestone reward.
    ---
    tags: [Challenges]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [subscription]
          properties:
            subscription:
              type: object
              description: Web Push subscription object
            device_label:
              type: string
    responses:
      200:
        description: Push subscription registered and milestone evaluated
      400:
        description: Missing subscription data or validation error
    """
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    subscription = data.get("subscription")
    if not subscription or not isinstance(subscription, dict):
        return jsonify({"error": MSG.PUSH_SUBSCRIPTION_REQUIRED}), 400

    now = datetime.now(timezone.utc).isoformat()
    endpoint = subscription.get("endpoint")

    existing = None
    if endpoint:
        rows = (
            db.table("push_subscriptions")
            .select("id,subscription")
            .eq("user_id", g.user_id)
            .execute()
        ) or []
        for row in rows:
            sub = row.get("subscription") or {}
            if isinstance(sub, dict) and sub.get("endpoint") == endpoint:
                existing = row
                break

    record = {
        "user_id": g.user_id,
        "subscription": subscription,
        "device_label": data.get("device_label"),
        "is_active": True,
        "updated_at": now,
    }
    campus_id = getattr(g, "campus_id", None)
    if campus_id:
        record["campus_id"] = campus_id

    if existing:
        try:
            db.table("push_subscriptions").eq("id", existing["id"]).update(record)
        except Exception as e:
            from app.utils.logger import get_logger
            get_logger(__name__).warning("push subscription update failed for %s: %s", g.user_id, e)
            return jsonify({"error": "Failed to update subscription"}), 500
    else:
        record["created_at"] = now
        try:
            db.table("push_subscriptions").insert(record)
        except Exception as exc:
            err_str = str(exc)
            if "uq_push_subscriptions_user_endpoint" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
                rows = (
                    db.table("push_subscriptions")
                    .select("id,subscription")
                    .eq("user_id", g.user_id)
                    .execute()
                ) or []
                match = next((r for r in rows if (r.get("subscription") or {}).get("endpoint") == endpoint), None)
                if match:
                    db.table("push_subscriptions").eq("id", match["id"]).update(record)

    # Look up push_subscribe milestone
    m_rows = (
        db.table("milestones")
        .select("id,title")
        .eq("trigger_type", "push_subscribe")
        .eq("is_active", "true")
        .limit(1)
        .execute()
    ) or []
    milestone = m_rows[0] if m_rows else None
    if not milestone:
        return jsonify({"error": "Push subscribe milestone not configured or inactive"}), 404

    from app.services.milestone_service import check_and_award_milestone, check_and_award_pwa_push_bonus
    try:
        result = check_and_award_milestone(g.user_id, milestone["id"])
        check_and_award_pwa_push_bonus(g.user_id)
        already_completed = bool(result.get("already_completed"))
        hp_awarded = int(result.get("hp_awarded") or 0) if not already_completed else 0
        return jsonify({
            "success": True,
            "milestone": "push_subscribe",
            "hp_awarded": hp_awarded,
            "already_completed": already_completed,
            "message": MSG.PUSH_SUBSCRIBED,
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("push_subscribed_challenge: failed for %s: %s", g.user_id, e)
        return jsonify({"error": MSG.ERR_UNEXPECTED}), 500


@challenges_bp.route("/pwa-push-bonus-status", methods=["GET"])
@require_auth
def pwa_push_bonus_status():
    """
    Get PWA + Push Subscription bonus eligibility without awarding HP.
    ---
    tags: [Challenges]
    responses:
      200:
        description: PWA and Push bonus status summary
    """
    from app.services.milestone_service import check_and_award_pwa_push_bonus
    status = check_and_award_pwa_push_bonus(g.user_id)
    return jsonify({
        "pwa_install": status["pwa_install"],
        "push_subscribe": status["push_subscribe"],
        "bonus_completed": status["bonus_completed"],
        "eligible": status["eligible"],
        "bonus_configured": status["bonus_configured"],
    }), 200


@challenges_bp.route("/pwa-push-bonus", methods=["POST"])
@require_auth
def claim_pwa_push_bonus():
    """Explicit, idempotent claim; eligibility comes from recorded milestones."""
    from app.services.milestone_service import check_and_award_pwa_push_bonus
    status = check_and_award_pwa_push_bonus(g.user_id, award=True)
    if not status["eligible"]:
        return jsonify({"error": MSG.PWA_BONUS_REQUIREMENTS}), 400
    if not status["bonus_completed"]:
        return jsonify({"error": MSG.PWA_BONUS_UNAVAILABLE}), 503
    return jsonify({key: value for key, value in status.items() if key != "bonus_result"}), 200


@challenges_bp.route("/push-registered", methods=["POST"])
@require_auth
def claim_registered_push():
    """The OneSignal flow must have registered a web token for this user first."""
    db = get_user_client()
    tokens = db.table("device_tokens").select("id").eq("user_id", g.user_id).eq("platform", "web").limit(1).execute() or []
    if not tokens:
        return jsonify({"error": MSG.PWA_PUSH_REGISTRATION_REQUIRED}), 400
    milestones = db.table("milestones").select("id").eq("trigger_type", "push_subscribe").eq("is_active", True).limit(1).execute() or []
    if not milestones:
        return jsonify({"error": MSG.PWA_BONUS_UNAVAILABLE}), 503
    from app.services.milestone_service import check_and_award_milestone
    try:
        result = check_and_award_milestone(g.user_id, milestones[0]["id"])
        return jsonify({"success": True, "already_completed": bool(result.get("already_completed"))}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


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
    db = get_user_client()
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
        if limit < 1 or offset < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
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
    time_window: null = lifetime milestone; 'weekly'/'monthly' = recurring challenge.
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
    try:
        safe = _milestone_fields(request.get_json(silent=True), creating=True)
        campus_id = resolve_write_campus(as_campus_id(safe.get("campus_id")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    safe.update(created_by=g.user_id, campus_id=campus_id)
    safe.setdefault("is_active", False)
    try:
        result = _saved_milestone(get_user_client().table("milestones").insert(safe))
    except Exception:
        logger.exception("admin_create_milestone: write failed")
        return jsonify({"error": MSG.CHALLENGE_SAVE_UNAVAILABLE}), 503
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    return jsonify(result), 201


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
    try:
        safe = _milestone_fields(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not safe:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    db = get_user_client()
    existing = db.table("milestones").select("id,campus_id").eq("id", milestone_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.CHALLENGE_NOT_FOUND}), 404
    assert_can_modify(existing.get("campus_id"))
    # Moving an existing challenge would strand its progress/history in the old campus.
    if "campus_id" in safe:
        try:
            requested = as_campus_id(safe.pop("campus_id"))
        except ValueError:
            return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
        if requested != existing.get("campus_id"):
            return jsonify({"error": MSG.CHALLENGE_SCOPE_IMMUTABLE}), 400
    safe["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = _saved_milestone(db.table("milestones").eq("id", milestone_id).update(safe))
    except Exception:
        logger.exception("admin_update_milestone: write failed")
        return jsonify({"error": MSG.CHALLENGE_SAVE_UNAVAILABLE}), 503
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    return jsonify(result), 200


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
    db = get_user_client()
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

    db = get_user_client()
    target = db.table("profiles").select("campus_id").eq("id", target_user_id).single().execute()
    if not target:
        return jsonify({"error": MSG.HP_ADMIN_TARGET_NOT_FOUND}), 404
    if getattr(g, "user_role", None) == "admin":
        if target.get("campus_id") != getattr(g, "campus_id", None):
            return jsonify({"error": MSG.MILESTONE_ADMIN_GRANT_CROSS_CAMPUS}), 403

    from app.services.milestone_service import admin_grant_milestone as _grant
    try:
        result = _grant(admin_id=g.user_id, user_id=target_user_id, milestone_id=milestone_id, target_campus_id=target.get("campus_id"))
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
