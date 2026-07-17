"""Leaderboard routes — individual rankings, squad leaderboard, hall of fame."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db
from datetime import date, timedelta, datetime, timezone

leaderboard_bp = Blueprint("leaderboard", __name__)


def _period_key_for(period_type: str):
    today = date.today()
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
    db = get_db()
    period_type = request.args.get("period_type", "monthly")
    if period_type not in ("monthly", "weekly", "all_time"):
        period_type = "monthly"
    default_limit = current_app.config.get("LEADERBOARD_DEFAULT_LIMIT", 10)
    max_limit = current_app.config.get("LEADERBOARD_MAX_LIMIT", 50)
    limit = min(int(request.args.get("limit", default_limit)), max_limit)
    period_key = _period_key_for(period_type)

    snapshot_rows = (
        db.table("leaderboard_snapshots")
        .select("*")
        .eq("ranking_type", period_type)
        .eq("period_key", period_key)
        .order("created_at", ascending=False)
        .limit(1)
        .execute()
    )

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
    Permanent Hall of Fame — monthly leaderboard #1 winners by period,
    plus all users inducted via 4 top-4 finishes (hall_of_fame_inductees).
    ---
    tags: [Leaderboard]
    security: []
    responses:
      200:
        description: Hall of Fame entries
    """
    db = get_db()
    try:
        # Monthly #1 winners from leaderboard snapshots
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

        # Top-4 finish inductees
        inductees_raw = (
            db.table("hall_of_fame_inductees")
            .select("user_id,full_name,inducted_at,tier_at_induction,top4_finish_count")
            .order("inducted_at", ascending=False)
            .execute()
        ) or []

        return jsonify({
            "monthly_winners": hall,
            "inductees": inductees_raw,
        }), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@leaderboard_bp.route("/hall-of-fame/inductees", methods=["GET"])
def hall_of_fame_inductees():
    """
    All Hall of Fame inductees — users who reached 4 top-4 leaderboard finishes.
    Includes full profile data for card rendering.
    ---
    tags: [Leaderboard]
    security: []
    responses:
      200:
        description: Inductee list with profile enrichment
    """
    db = get_db()
    try:
        rows = (
            db.table("hall_of_fame_inductees")
            .select("*")
            .order("inducted_at", ascending=False)
            .execute()
        ) or []

        inductees = []
        for row in rows:
            uid = row.get("user_id")
            profile = {}
            if uid:
                try:
                    profile = db.table("profiles").select(
                        "avatar_url,faculty,department"
                    ).eq("id", uid).single().execute() or {}
                except Exception:
                    pass
            inductees.append({
                "user_id": uid,
                "name": row.get("full_name"),
                "inducted_at": row.get("inducted_at"),
                "tier_at_induction": row.get("tier_at_induction"),
                "top4_finish_count": row.get("top4_finish_count"),
                "qualifying_record": row.get("qualifying_record"),
                "avatar_url": profile.get("avatar_url"),
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
    Shareable induction card data for a specific Hall of Fame inductee.
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
    db = get_db()
    try:
        row = (
            db.table("hall_of_fame_inductees")
            .select("*")
            .eq("user_id", inductee_user_id)
            .order("inducted_at", ascending=False)
            .limit(1)
            .execute()
        )
        row = (row[0] if isinstance(row, list) and row else row) or None
        if not row:
            return jsonify({"error": "Inductee not found"}), 404

        profile = {}
        try:
            profile = db.table("profiles").select(
                "avatar_url,faculty,department,hp_earned_120day,current_tier_id"
            ).eq("id", inductee_user_id).single().execute() or {}
        except Exception:
            pass

        card = {
            "user_id": inductee_user_id,
            "name": row.get("full_name"),
            "inducted_at": row.get("inducted_at"),
            "tier_at_induction": row.get("tier_at_induction"),
            "top4_finish_count": row.get("top4_finish_count"),
            "qualifying_record": row.get("qualifying_record"),
            "avatar_url": profile.get("avatar_url"),
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
    db = get_db()
    period_type = request.args.get("period_type", "monthly")
    if period_type not in ("monthly", "weekly", "all_time"):
        period_type = "monthly"
    period_key = _period_key_for(period_type)

    snapshot_rows = (
        db.table("leaderboard_snapshots")
        .select("*")
        .eq("ranking_type", period_type)
        .eq("period_key", period_key)
        .order("created_at", ascending=False)
        .limit(1)
        .execute()
    )

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


@leaderboard_bp.route("/squad", methods=["GET"])
def squad_leaderboard():
    """
    Squad leaderboard — ranks squads by combined HP earned from squad orders.
    A squad is identified by its organiser (the user who placed the squad order).
    ---
    tags: [Leaderboard]
    security: []
    parameters:
      - in: query
        name: period_type
        type: string
        default: monthly
        enum: [monthly, weekly, all_time]
      - in: query
        name: limit
        type: integer
        default: 10
    responses:
      200:
        description: Squad leaderboard rankings
    """
    db = get_db()
    period_type = request.args.get("period_type", "monthly")
    if period_type not in ("monthly", "weekly", "all_time"):
        period_type = "monthly"
    default_limit = current_app.config.get("LEADERBOARD_DEFAULT_LIMIT", 10)
    max_limit = current_app.config.get("LEADERBOARD_MAX_LIMIT", 50)
    limit = min(int(request.args.get("limit", default_limit)), max_limit)
    period_key = _period_key_for(period_type)
    today = date.today()

    try:
        # Fetch delivered squad orders
        squad_orders = (
            db.table("orders")
            .select("id,user_id,hp_earned,created_at")
            .eq("is_squad_order", "true")
            .eq("status", "delivered")
            .execute()
        ) or []

        # Filter by period
        if period_type == "monthly":
            prefix = today.strftime("%Y-%m")
            squad_orders = [o for o in squad_orders if (o.get("created_at") or "").startswith(prefix)]
        elif period_type == "weekly":
            week_start = (today - timedelta(days=today.weekday())).isoformat()
            squad_orders = [o for o in squad_orders if (o.get("created_at") or "")[:10] >= week_start]

        if not squad_orders:
            return jsonify({"period_key": period_key, "period_type": period_type, "rankings": []}), 200

        order_ids = [o["id"] for o in squad_orders]

        # Accumulate HP and squad-order count per organiser
        org_hp: dict = {}
        org_count: dict = {}
        for o in squad_orders:
            uid = o.get("user_id")
            if not uid:
                continue
            org_hp[uid] = org_hp.get(uid, 0) + (o.get("hp_earned") or 0)
            org_count[uid] = org_count.get(uid, 0) + 1

        # Fetch squad members for all orders in batches of 50 (avoids URL-length cap)
        all_members = []
        for _i in range(0, len(order_ids), 50):
            _batch = order_ids[_i:_i + 50]
            _batch_members = (
                db.table("squad_members")
                .select("order_id,user_id,is_registered")
                .in_("order_id", _batch)
                .execute()
            ) or []
            all_members.extend(_batch_members)

        # Build order_id → organiser_id map
        oid_to_org = {o["id"]: o.get("user_id") for o in squad_orders}
        org_members: dict = {}
        for m in all_members:
            org_id = oid_to_org.get(m.get("order_id"))
            if org_id and m.get("user_id"):
                org_members.setdefault(org_id, set()).add(m["user_id"])

        # Rank by combined HP
        ranked = sorted(org_hp.items(), key=lambda x: x[1], reverse=True)[:limit]

        # Batch-fetch profiles for organiser names
        org_ids = [uid for uid, _ in ranked]
        profiles_raw = (
            db.table("profiles")
            .select("id,full_name")
            .in_("id", org_ids)
            .execute()
        ) or []
        profile_map = {p["id"]: p.get("full_name") for p in profiles_raw}

        rankings = []
        for rank, (uid, total_hp) in enumerate(ranked, 1):
            members = org_members.get(uid, set())
            rankings.append({
                "rank": rank,
                "organiser_id": uid,
                "organiser_name": profile_map.get(uid) or "Unknown",
                "total_hp": total_hp,
                "squad_order_count": org_count.get(uid, 0),
                "squad_size": len(members) + 1,  # +1 for organiser
            })

        return jsonify({
            "period_key": period_key,
            "period_type": period_type,
            "rankings": rankings,
        }), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@leaderboard_bp.route("/squad/my-rank", methods=["GET"])
@require_auth
def squad_my_rank():
    """
    Get the authenticated user's position in the squad leaderboard.
    ---
    tags: [Leaderboard]
    parameters:
      - in: query
        name: period_type
        type: string
        default: monthly
    responses:
      200:
        description: User's squad rank and HP stats
    """
    db = get_db()
    period_type = request.args.get("period_type", "monthly")
    if period_type not in ("monthly", "weekly", "all_time"):
        period_type = "monthly"
    period_key = _period_key_for(period_type)
    today = date.today()

    try:
        squad_orders = (
            db.table("orders")
            .select("id,user_id,hp_earned,created_at")
            .eq("is_squad_order", "true")
            .eq("status", "delivered")
            .execute()
        ) or []

        if period_type == "monthly":
            prefix = today.strftime("%Y-%m")
            squad_orders = [o for o in squad_orders if (o.get("created_at") or "").startswith(prefix)]
        elif period_type == "weekly":
            week_start = (today - timedelta(days=today.weekday())).isoformat()
            squad_orders = [o for o in squad_orders if (o.get("created_at") or "")[:10] >= week_start]

        org_hp: dict = {}
        org_count: dict = {}
        for o in squad_orders:
            uid = o.get("user_id")
            if not uid:
                continue
            org_hp[uid] = org_hp.get(uid, 0) + (o.get("hp_earned") or 0)
            org_count[uid] = org_count.get(uid, 0) + 1

        ranked = sorted(org_hp.items(), key=lambda x: x[1], reverse=True)
        user_hp = org_hp.get(g.user_id, 0)
        user_rank = next((i + 1 for i, (uid, _) in enumerate(ranked) if uid == g.user_id), None)

        return jsonify({
            "period_key": period_key,
            "period_type": period_type,
            "rank": user_rank,
            "total_hp": user_hp,
            "squad_order_count": org_count.get(g.user_id, 0),
        }), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
