"""Leaderboard routes — monthly rankings, hall of fame."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.db import get_db

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("", methods=["GET"])
def get_leaderboard():
    """
    Get leaderboard. period_type: monthly | weekly | all_time.
    ---
    tags: [Leaderboard]
    security: []
    parameters:
      - in: query
        name: period_type
        type: string
        default: monthly
      - in: query
        name: limit
        type: integer
        default: 10
    responses:
      200:
        description: Leaderboard rankings
    """
    db = get_db()
    period_type = request.args.get("period_type", "monthly")
    limit = min(int(request.args.get("limit", 10)), 50)

    from datetime import datetime, timezone, date
    today = date.today()
    if period_type == "monthly":
        period = today.strftime("%Y-%m")
    elif period_type == "weekly":
        from datetime import timedelta
        week_start = today - timedelta(days=today.weekday())
        period = week_start.isoformat()
    else:
        period = "all_time"

    snapshots = (
        db.table("leaderboard_snapshots")
        .select("*,profiles(full_name),tiers(name,slug,badge_color_hex)")
        .eq("period", period_type)
        .order("rank")
        .limit(limit)
        .execute()
    )

    if not snapshots:
        profiles = (
            db.table("profiles")
            .select("id,full_name")
            .eq("is_active", "true")
            .eq("role", "student")
            .execute()
        )

        if period_type == "monthly":
            field = "monthly_hp_earned"
        elif period_type == "all_time":
            field = "hp_earned_120day"
        else:
            field = "monthly_hp_earned"

        profile_data = db.table("profiles").select(f"id,full_name,{field}").order(field, ascending=False).limit(limit).execute()
        rankings = []
        for i, p in enumerate(profile_data):
            rankings.append({
                "rank": i + 1,
                "user_id": p["id"],
                "full_name": p.get("full_name"),
                "hp_total": p.get(field, 0) or 0,
            })
        return jsonify({"period": period, "period_type": period_type, "rankings": rankings}), 200

    return jsonify({"period": period, "period_type": period_type, "rankings": snapshots}), 200


@leaderboard_bp.route("/hall-of-fame", methods=["GET"])
def hall_of_fame():
    """
    Permanent Hall of Fame — all-time monthly #1 winners.
    ---
    tags: [Leaderboard]
    security: []
    responses:
      200:
        description: Hall of Fame entries
    """
    db = get_db()
    try:
        entries = db.table("hall_of_fame").select("*,profiles(full_name)").order("month", ascending=False).execute()
        return jsonify(entries), 200
    except Exception:
        entries = (
            db.table("leaderboard_snapshots")
            .select("*,profiles(full_name)")
            .eq("rank", "1")
            .order("week_start", ascending=False)
            .execute()
        )
        return jsonify(entries), 200


@leaderboard_bp.route("/my-rank", methods=["GET"])
@require_auth
def my_rank():
    """
    Get authenticated user's current rank and HP stats.
    ---
    tags: [Leaderboard]
    responses:
      200:
        description: User's rank and stats
    """
    db = get_db()
    period_type = request.args.get("period_type", "monthly")

    snapshot = (
        db.table("leaderboard_snapshots")
        .select("*")
        .eq("user_id", g.user_id)
        .eq("period", period_type)
        .order("computed_at", ascending=False)
        .limit(1)
        .execute()
    )

    profile = db.table("profiles").select("monthly_hp_earned,hp_earned_120day").eq("id", g.user_id).single().execute()

    return jsonify({
        "snapshot": snapshot[0] if snapshot else None,
        "monthly_hp_earned": profile.get("monthly_hp_earned", 0) if profile else 0,
        "hp_earned_120day": profile.get("hp_earned_120day", 0) if profile else 0,
    }), 200
