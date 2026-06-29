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

    from datetime import date, timedelta
    today = date.today()
    if period_type == "monthly":
        period_key = today.strftime("%Y-%m")
    elif period_type == "weekly":
        week_start = today - timedelta(days=today.weekday())
        period_key = week_start.isoformat()
    else:
        period_key = "all_time"
        period_type = "all_time"

    snapshot_rows = (
        db.table("leaderboard_snapshots")
        .select("*")
        .eq("ranking_type", period_type)
        .eq("period_key", period_key)
        .order("created_at", ascending=False)
        .limit(1)
        .execute()
    )

    if snapshot_rows:
        snapshot = snapshot_rows[0]
        entries = snapshot.get("entries") or []
        if isinstance(entries, list):
            entries = entries[:limit]
        return jsonify({
            "period_key": period_key,
            "period_type": period_type,
            "rankings": entries,
        }), 200

    profile_data = (
        db.table("profiles")
        .select("id,full_name,hp_balance")
        .eq("is_active", "true")
        .eq("role", "student")
        .order("hp_balance", ascending=False)
        .limit(limit)
        .execute()
    )
    rankings = []
    for i, p in enumerate(profile_data or []):
        rankings.append({
            "rank": i + 1,
            "user_id": p["id"],
            "full_name": p.get("full_name"),
            "hp_total": p.get("hp_balance", 0) or 0,
        })
    return jsonify({"period_key": period_key, "period_type": period_type, "rankings": rankings}), 200


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
        entries = (
            db.table("leaderboard_snapshots")
            .select("*")
            .eq("ranking_type", "monthly")
            .order("period_key", ascending=False)
            .execute()
        )
        hall = []
        for snap in (entries or []):
            snap_entries = snap.get("entries") or []
            if snap_entries:
                winner = snap_entries[0] if isinstance(snap_entries, list) else snap_entries
                hall.append({
                    "period_key": snap.get("period_key"),
                    "winner": winner,
                })
        return jsonify(hall), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


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

    from datetime import date, timedelta
    today = date.today()
    if period_type == "monthly":
        period_key = today.strftime("%Y-%m")
    elif period_type == "weekly":
        week_start = today - timedelta(days=today.weekday())
        period_key = week_start.isoformat()
    else:
        period_key = "all_time"
        period_type = "all_time"

    snapshot_rows = (
        db.table("leaderboard_snapshots")
        .select("*")
        .eq("ranking_type", period_type)
        .eq("period_key", period_key)
        .order("created_at", ascending=False)
        .limit(1)
        .execute()
    )

    user_rank = None
    if snapshot_rows:
        entries = snapshot_rows[0].get("entries") or []
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("user_id") == g.user_id:
                    user_rank = entry
                    break

    profile_rows = db.table("profiles").select("hp_balance").eq("id", g.user_id).execute()
    profile = profile_rows[0] if profile_rows else {}
    hp_balance = profile.get("hp_balance", 0) if profile else 0

    if user_rank is None:
        all_profiles = (
            db.table("profiles")
            .select("id,hp_balance")
            .eq("is_active", "true")
            .order("hp_balance", ascending=False)
            .execute()
        )
        for i, p in enumerate(all_profiles or []):
            if p.get("id") == g.user_id:
                user_rank = {
                    "rank": i + 1,
                    "user_id": g.user_id,
                    "hp_total": p.get("hp_balance", 0) or 0,
                    "source": "live",
                }
                break

    return jsonify({
        "rank_entry": user_rank,
        "hp_balance": hp_balance,
        "period_key": period_key,
        "period_type": period_type,
    }), 200
