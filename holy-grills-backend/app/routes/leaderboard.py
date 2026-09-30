from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, resolve_scoped_campus_id
from app.db import get_db, get_user_client
from datetime import date, timedelta, datetime, timezone
from app.utils.tz import today_wat
from app.utils.logger import get_logger

logger = get_logger(__name__)

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


def _period_start_utc_iso(period_type: str):
    """WAT-midnight start of the CURRENT (in-progress) monthly/weekly period, as the
    equivalent UTC instant -- used to bound the live hp_transactions aggregation below.
    Same WAT-midnight conversion as kitchen.py's _today_start_iso."""
    from app.utils.tz import WAT_OFFSET
    today = today_wat()
    start_date = today.replace(day=1) if period_type == "monthly" else today - timedelta(days=today.weekday())
    wat_midnight_naive = datetime.combine(start_date, datetime.min.time())
    return (wat_midnight_naive - WAT_OFFSET).replace(tzinfo=timezone.utc).isoformat()


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
    try:
        limit = int(request.args.get("limit", default_limit))
    except (TypeError, ValueError):
        limit = default_limit
    limit = max(1, min(limit, max_limit))
    period_key = _period_key_for(period_type)

    campus_id = request.args.get("campus_id") or getattr(g, 'campus_id', None)

    if period_type != "all_time":
        # Snapshots (leaderboard_snapshots) only ever hold ALREADY-COMPLETED periods --
        # the monthly/weekly reset jobs archive the period that just ended, under that
        # period's own key. _period_key_for() above always returns the CURRENT,
        # in-progress period's key, which cannot match a snapshot until the period is
        # over -- and by then _period_key_for() has already moved on to the next one.
        # These two can never coincide, so rather than a snapshot lookup that can only
        # ever return "pending", the current period is computed live from hp_transactions,
        # the same way the all_time branch already computes live from profiles.hp_balance.
        period_start = _period_start_utc_iso(period_type)
        txn_q = (
            db.table("hp_transactions")
            .select("user_id,amount")
            .eq("type", "earn")
            .neq("reference_type", "hp_transfer")  # exclude transfers so two colluding accounts
            .gte("created_at", period_start)        # can't inflate rank by shuffling HP between themselves
        )
        if campus_id:
            txn_q = txn_q.eq("campus_id", campus_id)
        txns = txn_q.execute() or []

        totals = {}
        for t in txns:
            uid = t.get("user_id")
            if uid:
                totals[uid] = totals.get(uid, 0) + (t.get("amount") or 0)

        # Overfetch candidates before the is_active/role=student filter below, so removing
        # an inactive top-earner doesn't leave fewer than `limit` entries in the result.
        candidate_ids = sorted(totals, key=totals.get, reverse=True)[: limit * 3]
        profile_data = []
        if candidate_ids:
            prof_q = (
                db.table("profiles")
                .select("id,nickname,full_name,email,department,campus_id,leaderboard_show_full_name")
                .eq("is_active", "true").eq("role", "student")
                .in_("id", candidate_ids)
            )
            profile_data = prof_q.execute() or []
        valid_ids = {p["id"] for p in profile_data}
        ranked_ids = [uid for uid in candidate_ids if uid in valid_ids][:limit]

        from app.services.squad_service import resolve_leaderboard_names_batch
        names = resolve_leaderboard_names_batch(profile_data)
        rankings = [
            {"rank": i + 1, "user_id": uid, "full_name": names.get(uid), "hp_total": totals[uid]}
            for i, uid in enumerate(ranked_ids)
        ]
        return jsonify({
            "period_key": period_key, "period_type": period_type,
            "rankings": rankings, "computed_live": True,
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
    plus all users inducted via 3 top-4 finishes (hall_of_fame_inductees).
    ---
    tags: [Leaderboard]
    security: []
    responses:
      200:
        description: Hall of Fame entries
    """
    db = get_user_client()
    from app.services.feature_flags import is_feature_enabled
    if not is_feature_enabled("hall_of_fame"):
        from app.messages import MSG, resolve_msg
        return jsonify({"error": resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature="Hall of Fame")}), 403
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
    except Exception:
        logger.exception("hall_of_fame: lookup failed")
        return jsonify({"error": "An unexpected error occurred"}), 500


@leaderboard_bp.route("/hall-of-fame/inductees", methods=["GET"])
def hall_of_fame_inductees():
    """
    All Hall of Fame inductees — users who reached 3 top-4 leaderboard finishes (global).
    Includes full profile data for card rendering.
    ---
    tags: [Leaderboard]
    security: []
    responses:
      200:
        description: Inductee list with profile enrichment
    """
    db = get_user_client()
    from app.services.feature_flags import is_feature_enabled
    if not is_feature_enabled("hall_of_fame"):
        from app.messages import MSG, resolve_msg
        return jsonify({"error": resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature="Hall of Fame")}), 403
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
    except Exception:
        logger.exception("hall_of_fame_inductees: lookup failed")
        return jsonify({"error": "An unexpected error occurred"}), 500


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
    except Exception:
        logger.exception("inductee_share_card: lookup failed")
        return jsonify({"error": "An unexpected error occurred"}), 500


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

    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
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

    # Member count: active squad_roster rows per squad_id — same table/filter squad_my_rank()
    # already uses, just grouped by squad_id and counted instead of filtered to one user.
    roster_rows = db.table("squad_roster").select("squad_id").eq("is_active", True).in_("squad_id", list(hp_by_squad.keys())).execute() or []
    member_counts = {}
    for r in roster_rows:
        sid = r.get("squad_id")
        if sid:
            member_counts[sid] = member_counts.get(sid, 0) + 1

    ranked = sorted(squads_rows, key=lambda s: hp_by_squad.get(s["id"], 0), reverse=True)
    return jsonify([
        {
            "rank": i + 1, "squad_id": s["id"], "squad_name": s["name"],
            "organizer_name": creator_names.get(s["creator_id"]),
            "hp_total": hp_by_squad.get(s["id"], 0),
            "member_count": member_counts.get(s["id"], 0),
        }
        for i, s in enumerate(ranked)
    ]), 200


@leaderboard_bp.route("/squad/my-rank", methods=["GET"])
@require_auth
def squad_my_rank():
    db = get_user_client()
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))

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
