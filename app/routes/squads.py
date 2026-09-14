"""Squad routes: persistent squad entity, roster, and squad order history."""
from flask import Blueprint, request, jsonify, g, current_app
from app.db import get_user_client
from app.middleware.auth import require_auth
from app.messages import MSG
from app.services.squad_service import resolve_display_name, resolve_display_names_batch

squads_bp = Blueprint("squads", __name__)


def _get_squad_or_404(db, squad_id):
    squad = db.table("squads").select("*").eq("id", squad_id).single().execute()
    return squad


@squads_bp.route("", methods=["POST"])
@require_auth
def create_squad():
    """Create a squad (organizer types name + member emails)."""
    db = get_user_client()
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": MSG.SQUAD_NAME_REQUIRED}), 400
    emails = [e.strip().lower() for e in (data.get("emails") or []) if e and e.strip()]

    max_members = int(current_app.config.get("SQUAD_MAX_MEMBERS", 20))
    if len(emails) > max_members:
        return jsonify({"error": MSG.SQUAD_MAX_MEMBERS_REACHED}), 400

    campus_id = getattr(g, "campus_id", None)

    # Cross-campus block: every invited email must belong to the same campus.
    by_email = {}
    if emails:
        member_profiles = db.table("profiles").select("id,email,campus_id").in_("email", emails).execute() or []
        by_email = {p["email"]: p for p in member_profiles}
        for email in emails:
            prof = by_email.get(email)
            if prof and campus_id and prof.get("campus_id") and prof["campus_id"] != campus_id:
                return jsonify({"error": MSG.SQUAD_CROSS_CAMPUS_BLOCKED}), 400

    squad = db.table("squads").insert({
        "name": name, "creator_id": g.user_id, "campus_id": campus_id,
    }).execute()
    squad_row = squad[0] if isinstance(squad, list) else squad

    for email in emails:
        try:
            db.table("squad_roster").insert({
                "squad_id": squad_row["id"], "email": email,
                "user_id": by_email.get(email, {}).get("id"),
            })
        except Exception:
            pass  # duplicate (squad_id, email) — ignore

    return jsonify(squad_row), 201


@squads_bp.route("", methods=["GET"])
@require_auth
def list_my_squads():
    """List squads I belong to (creator or roster member) — for the checkout dropdown."""
    db = get_user_client()
    created = db.table("squads").select("*").eq("creator_id", g.user_id).execute() or []
    roster_rows = db.table("squad_roster").select("squad_id").eq("user_id", g.user_id).eq("is_active", True).execute() or []
    roster_squad_ids = [r["squad_id"] for r in roster_rows]
    member_of = []
    if roster_squad_ids:
        member_of = db.table("squads").select("*").in_("id", roster_squad_ids).execute() or []
    seen = {s["id"] for s in created}
    combined = list(created) + [s for s in member_of if s["id"] not in seen]
    return jsonify(combined), 200


@squads_bp.route("/<squad_id>", methods=["GET"])
@require_auth
def get_squad(squad_id):
    """Roster + per-member cumulative HP (drill-down from leaderboard)."""
    db = get_user_client()
    squad = _get_squad_or_404(db, squad_id)
    if not squad:
        return jsonify({"error": "Squad not found"}), 404

    roster = db.table("squad_roster").select("id,user_id,email,is_active,joined_at").eq("squad_id", squad_id).execute() or []
    user_ids = [r["user_id"] for r in roster if r.get("user_id")]
    profiles_by_id = {}
    if user_ids:
        profs = db.table("profiles").select("id,nickname,full_name,email,department,campus_id").in_("id", user_ids).execute() or []
        names = resolve_display_names_batch(profs)
        profiles_by_id = {p["id"]: names.get(p["id"], p.get("email")) for p in profs}

    # Cumulative HP per member: sum squad_members.hp_share across this squad's orders.
    order_rows = db.table("orders").select("id").eq("squad_id", squad_id).execute() or []
    order_ids = [o["id"] for o in order_rows]
    hp_by_email = {}
    if order_ids:
        member_rows = db.table("squad_members").select("email,hp_share").in_("order_id", order_ids).execute() or []
        for m in member_rows:
            hp_by_email[m["email"]] = hp_by_email.get(m["email"], 0) + (m.get("hp_share") or 0)

    roster_out = []
    for r in roster:
        display_name = profiles_by_id.get(r.get("user_id")) or r["email"]
        roster_out.append({
            "id": r["id"], "email": r["email"], "user_id": r.get("user_id"),
            "display_name": display_name, "is_active": r["is_active"],
            "cumulative_hp": hp_by_email.get(r["email"], 0),
        })

    return jsonify({**squad, "roster": roster_out}), 200


@squads_bp.route("/<squad_id>/orders", methods=["GET"])
@require_auth
def get_squad_orders(squad_id):
    """Squad order history."""
    db = get_user_client()
    orders = db.table("orders").select(
        "id,order_number,total_amount,status,squad_item_count,created_at,delivered_at"
    ).eq("squad_id", squad_id).order("created_at", ascending=False).execute() or []
    return jsonify(orders), 200


@squads_bp.route("/<squad_id>/members", methods=["POST"])
@require_auth
def add_roster_member(squad_id):
    """Add roster member (organizer only, enforced by RLS creator-only policy)."""
    db = get_user_client()
    squad = _get_squad_or_404(db, squad_id)
    if not squad:
        return jsonify({"error": "Squad not found"}), 404
    if squad["creator_id"] != g.user_id:
        return jsonify({"error": MSG.SQUAD_ORGANIZER_ONLY}), 403

    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": MSG.SQUAD_EMAIL_REQUIRED}), 400

    current_count = db.table("squad_roster").select("id", count="exact").eq("squad_id", squad_id).eq("is_active", True).execute()
    roster_count = current_count.get("count", 0) if isinstance(current_count, dict) else len(current_count or [])
    max_members = int(current_app.config.get("SQUAD_MAX_MEMBERS", 20))
    if roster_count >= max_members:
        return jsonify({"error": MSG.SQUAD_MAX_MEMBERS_REACHED}), 400

    profile = db.table("profiles").select("id,campus_id").eq("email", email).single().execute()
    if profile and squad.get("campus_id") and profile.get("campus_id") and profile["campus_id"] != squad["campus_id"]:
        return jsonify({"error": MSG.SQUAD_CROSS_CAMPUS_BLOCKED}), 400

    try:
        row = db.table("squad_roster").insert({
            "squad_id": squad_id, "email": email,
            "user_id": profile["id"] if profile else None,
        }).execute()
    except Exception:
        return jsonify({"error": "Already a member"}), 400
    return jsonify(row[0] if isinstance(row, list) else row), 201


@squads_bp.route("/<squad_id>/members/<member_id>", methods=["DELETE"])
@require_auth
def remove_roster_member(squad_id, member_id):
    """Soft-remove roster member (organizer only). No leave/deactivate for squad itself."""
    db = get_user_client()
    squad = _get_squad_or_404(db, squad_id)
    if not squad:
        return jsonify({"error": "Squad not found"}), 404
    if squad["creator_id"] != g.user_id:
        return jsonify({"error": MSG.SQUAD_ORGANIZER_ONLY}), 403
    db.table("squad_roster").eq("id", member_id).eq("squad_id", squad_id).update({"is_active": False})
    return jsonify({"message": "Member removed"}), 200
