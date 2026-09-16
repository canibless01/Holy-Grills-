"""Leaderboard routes — individual rankings, squad leaderboard, hall of fame."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db, get_user_client
from datetime import date, timedelta, datetime, timezone
from app.utils.tz import today_wat

leaderboard_bp = Blueprint("leaderboard", __name__)


def _period_key_for(period_type: str):
    today = today_wat()
    if period_type == "monthly":
        return today.strftime("%Y-%m")
    elif period_type == "weekly":
        week_start = today - timedelta(days=today.weekday())
        return week_start.isoformat()
    else:
        return "all_time"


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
    db = get_user_client()
    period_type = request.args.get("period_type", "monthly")
    if period_type not in ("monthly", "weekly", "all_time"):
        period_type = "monthly"
    default_limit = current_app.config.get("LEADERBOARD_DEFAULT_LIMIT", 10)
    max_limit = current_app.config.get("LEADERBOARD_MAX_LIMIT", 50)
    limit = min(int(request.args.get("limit", default_limit)), max_limit)
    period_key = _period_key_for(period_type)

    campus_id = request.args.get("campus_id") or getattr(g, 'campus_id', None)
    snap_q = (
        db.table("leaderboard_snapshots")
        .select("*")
        .eq("ranking_type", period_type)
        .eq("period_key", period_key)
    )
    if campus_id:
        snap_q = snap_q.eq("campus_id", campus_id)
    snapshot_rows = snap_q.order("created_at", ascending=False).limit(1).execute()

    # Only serve snapshot if it was created within the last 24 hours
    _snapshot_fresh = False
    if snapshot_rows:
        snap_created = snapshot_rows[0].get("created_at", "")
        try:
            snap_dt = datetime.fromisoformat(snap_created.replace("Z", "+00:00"))
            _snapshot_fresh = (datetime.now(timezone.utc) - snap_dt).total_seconds() < 86400
        except Exception:
            _snapshot_fresh = False

    if _snapshot_fresh:
        snapshot = snapshot_rows[0]
        entries = snapshot.get("entries") or []
        if isinstance(entries, list):
            entries = entries[:limit]
        return jsonify({
            "period_key": period_key,
            "period_type": period_type,
            "rankings": entries,
            "snapshot_at": snapshot.get("created_at"),
        }), 200

    if period_type != "all_time":
        return jsonify({
            "period_key": period_key,
            "period_type": period_type,
            "rankings": [],
            "snapshot_pending": True,
            "message": "Rankings for this period are being calculated — check back shortly.",
        }), 200

    q = db.table("profiles").select("id,nickname,full_name,email,department,campus_id,leaderboard_show_full_name,hp_balance").eq("is_active", "true").eq("role", "student")
    campus_id = request.args.get("campus_id") or getattr(g, 'campus_id', None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    profile_data = q.order("hp_balance", ascending=False).limit(limit).execute()
    from app.services.squad_service import resolve_leaderboard_names_batch
    names = resolve_leaderboard_names_batch(profile_data or [])
    rankings = []
    for i, p in enumerate(profile_data or []):
        rankings.append({
            "rank": i + 1,
            "user_id": p["id"],
            "full_name": names.get(p["id"]),
            "hp_total": p.get("hp_balance", 0) or 0,
        })
    return jsonify({"period_key": period_key, "period_type": period_type, "rankings": rankings}), 200


@leaderboard_bp.route("/hall-of-fame", methods=["GET"])
def hall_of_fame():
    """
    Permanent Hall of Fame — global monthly leaderboard #1 winners by period,
    plus all users inducted via 4 top-4 finishes (hall_of_fame_inductees).
    ---
    tags: [Leaderboard]
    security: []
    responses:
      200:
        description: Hall of Fame entries
    """
    db = get_user_client()
    try:
        # Monthly #1 winners from leaderboard snapshots (global)
        q_snap = (
            db.table("leaderboard_snapshots")
            .select("*")
            .eq("ranking_type", "monthly")
        )
        entries = q_snap.order("period_key", ascending=False).execute()

        hall = []
        for snap in (entries or []):
            snap_entries = snap.get("entries") or []
            if snap_entries:
                winner = snap_entries[0] if isinstance(snap_entries, list) else snap_entries
                hall.append({
                    "period_key": snap.get("period_key"),
                    "winner": winner,
                })

        # Top-4 finish inductees (global)
        q_ind = db.table("hall_of_fame_inductees").select("user_id,full_name,inducted_at,tier_at_induction,top4_finish_count")
        inductees_raw = q_ind.order("inducted_at", ascending=False).execute() or []

        return jsonify({
            "monthly_winners": hall,
            "inductees": inductees_raw,
        }), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@leaderboard_bp.route("/hall-of-fame/inductees", methods=["GET"])
def hall_of_fame_inductees():
    """
    All Hall of Fame inductees — users who reached 4 top-4 leaderboard finishes (global).
    Includes full profile data for card rendering.
    ---
    tags: [Leaderboard]
    security: []
    responses:
      200:
        description: Inductee list with profile enrichment
    """
    db = get_user_client()
    try:
        q = db.table("hall_of_fame_inductees").select("*")
        rows = q.order("inducted_at", ascending=False).execute() or []

        inductees = []
        for row in rows:
            uid = row.get("user_id")
            profile = {}
            if uid:
                try:
                    profile = db.table("profiles").select(
                        "photo_url,faculty,department"
                    ).eq("id", uid).single().execute() or {}
                except Exception:
                    pass
            inductees.append({
                "user_id": uid,
                "name": row.get("full_name"),
                "inducted_at": row.get("inducted_at"),
                "tier_at_induction": row.get("tier_at_induction"),
                "top4_finish_count": row.get("top4_finish_count"),
                "photo_url": profile.get("photo_url"),
                "faculty": profile.get("faculty"),
                "department": profile.get("department"),
                "share_path": f"/hall-of-fame/{uid}",
            })
        return jsonify({"inductees": inductees, "count": len(inductees)}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@leaderboard_bp.route("/hall-of-fame/inductees/<inductee_user_id>/card", methods=["GET"])
def inductee_share_card(inductee_user_id):
    """
    Shareable induction card data for a specific Hall of Fame inductee (global).
    Returns everything needed for the frontend to render and share the card.
    ---
    tags: [Leaderboard]
    security: []
    responses:
      200:
        description: Induction card data
      404:
        description: Inductee not found
    """
    db = get_user_client()
    try:
        q = db.table("hall_of_fame_inductees").select("*").eq("user_id", inductee_user_id)
        row = q.order("inducted_at", ascending=False).limit(1).execute()
        row = (row[0] if isinstance(row, list) and row else row) or None
        if not row:
            return jsonify({"error": "Inductee not found"}), 404

        profile = {}
        try:
            profile = db.table("profiles").select(
                "photo_url,faculty,department,hp_earned_120day,current_tier_id"
            ).eq("id", inductee_user_id).single().execute() or {}
        except Exception:
            pass

        card = {
            "user_id": inductee_user_id,
            "name": row.get("full_name"),
            "inducted_at": row.get("inducted_at"),
            "tier_at_induction": row.get("tier_at_induction"),
            "top4_finish_count": row.get("top4_finish_count"),
            "photo_url": profile.get("photo_url"),
            "faculty": profile.get("faculty"),
            "department": profile.get("department"),
            # Relative share path — frontend prepends the app base URL
            "share_path": f"/hall-of-fame/{inductee_user_id}",
        }
        return jsonify(card), 200
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
    db = get_user_client()
    period_type = request.args.get("period_type", "monthly")
    if period_type not in ("monthly", "weekly", "all_time"):
        period_type = "monthly"
    period_key = _period_key_for(period_type)

    campus_id = request.args.get("campus_id") or getattr(g, 'campus_id', None)
    snap_q = (
        db.table("leaderboard_snapshots")
        .select("*")
        .eq("ranking_type", period_type)
        .eq("period_key", period_key)
    )
    if campus_id:
        snap_q = snap_q.eq("campus_id", campus_id)
    snapshot_rows = snap_q.order("created_at", ascending=False).limit(1).execute()

    # Only trust snapshot when it is ≤24 hours old
    user_rank = None
    if snapshot_rows:
        snap_created = snapshot_rows[0].get("created_at", "")
        try:
            snap_dt = datetime.fromisoformat(snap_created.replace("Z", "+00:00"))
            _fresh = (datetime.now(timezone.utc) - snap_dt).total_seconds() < 86400
        except Exception:
            _fresh = False
        if _fresh:
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
        if period_type != "all_time":
            return jsonify({
                "rank_entry": None,
                "hp_balance": hp_balance,
                "period_key": period_key,
                "period_type": period_type,
                "snapshot_pending": True,
                "message": "Rankings for this period are being calculated — check back shortly.",
            }), 200

        all_q = (
            db.table("profiles")
            .select("id,hp_balance")
            .eq("is_active", "true")
            .eq("role", "student")
        )
        if campus_id:
            all_q = all_q.eq("campus_id", campus_id)
        all_profiles = all_q.order("hp_balance", ascending=False).execute()
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


@leaderboard_bp.route("/squad", methods=["GET"])
def squad_leaderboard():
    db = get_db()
    campus_id = request.args.get("campus_id") or getattr(g, 'campus_id', None)
    orders_q = db.table("orders").select("squad_id,hp_earned").eq("is_squad_order", "true").eq("status", "delivered")
    if campus_id:
        orders_q = orders_q.eq("campus_id", campus_id)
    squad_orders = orders_q.execute() or []

    hp_by_squad = {}
    for o in squad_orders:
        if o.get("squad_id"):
            hp_by_squad[o["squad_id"]] = hp_by_squad.get(o["squad_id"], 0) + (o.get("hp_earned") or 0)

    if not hp_by_squad:
        return jsonify([]), 200

    squads_rows = db.table("squads").select("id,name,creator_id").in_("id", list(hp_by_squad.keys())).execute() or []
    creator_ids = [s["creator_id"] for s in squads_rows if s.get("creator_id")]
    creator_profiles = []
    if creator_ids:
        creator_profiles = db.table("profiles").select("id,nickname,full_name,email,department,campus_id,leaderboard_show_full_name").in_("id", creator_ids).execute() or []
    from app.services.squad_service import resolve_leaderboard_names_batch
    creator_names = resolve_leaderboard_names_batch(creator_profiles)

    ranked = sorted(squads_rows, key=lambda s: hp_by_squad.get(s["id"], 0), reverse=True)
    return jsonify([
        {
            "rank": i + 1, "squad_id": s["id"], "squad_name": s["name"],
            "organizer_name": creator_names.get(s["creator_id"]),
            "hp_total": hp_by_squad.get(s["id"], 0),
        }
        for i, s in enumerate(ranked)
    ]), 200


@leaderboard_bp.route("/squad/my-rank", methods=["GET"])
@require_auth
def squad_my_rank():
    db = get_user_client()
    campus_id = request.args.get("campus_id") or getattr(g, 'campus_id', None)

    my_squads = db.table("squads").select("id").eq("creator_id", g.user_id).execute() or []
    roster_rows = db.table("squad_roster").select("squad_id").eq("user_id", g.user_id).eq("is_active", True).execute() or []
    squad_ids = list({s["id"] for s in my_squads} | {r["squad_id"] for r in roster_rows})

    if not squad_ids:
        return jsonify([]), 200

    orders_q = db.table("orders").select("squad_id,hp_earned").eq("is_squad_order", "true").not_.is_("squad_id", "null")
    if campus_id:
        orders_q = orders_q.eq("campus_id", campus_id)
    squad_orders = orders_q.execute() or []

    hp_by_squad = {}
    for o in squad_orders:
        if o.get("squad_id"):
            hp_by_squad[o["squad_id"]] = hp_by_squad.get(o["squad_id"], 0) + (o.get("hp_earned") or 0)

    ranked = sorted(hp_by_squad.items(), key=lambda item: item[1], reverse=True)
    ranks = {squad_id: i + 1 for i, (squad_id, _) in enumerate(ranked)}

    my_rankings = [
        {"squad_id": sid, "rank": ranks.get(sid), "hp_total": hp_by_squad.get(sid, 0)}
        for sid in squad_ids
    ]
    return jsonify(my_rankings), 200
