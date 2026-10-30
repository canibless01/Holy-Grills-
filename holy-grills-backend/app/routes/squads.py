"""Squad routes: persistent squad entity, roster, and squad order history."""
import re
import uuid
from flask import Blueprint, request, jsonify, g, current_app
from app.db import get_user_client, get_db
from app.middleware.auth import require_auth
from app.messages import MSG
from app.services.squad_service import resolve_display_names_batch
from app.services.feature_flags import is_feature_enabled
from app.utils.logger import get_logger

logger = get_logger(__name__)

squads_bp = Blueprint("squads", __name__)


def _get_squad_or_404(db, squad_id):
    squad = db.table("squads").select("*").eq("id", squad_id).single().execute()
    return squad


@squads_bp.route("", methods=["POST"])
@require_auth
def create_squad():
    """Create a squad (organizer types name + member emails)."""
    db = get_user_client()
    campus_id = getattr(g, "campus_id", None)
    if not is_feature_enabled("squad_orders", campus_id):
        return jsonify({"error": MSG.SQUAD_ORDERS_DISABLED}), 403

    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": MSG.SQUAD_NAME_REQUIRED}), 400
    raw_emails = data.get("emails") or []
    raw_ids = data.get("member_user_ids") or []
    if not isinstance(raw_emails, list) or not all(isinstance(email, str) for email in raw_emails) or not isinstance(raw_ids, list):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    emails = list(dict.fromkeys(email.strip().lower() for email in raw_emails if email.strip()))
    if any(not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) for email in emails):
        return jsonify({"error": MSG.SQUAD_EMAIL_REQUIRED}), 400
    selected_profiles = []
    if raw_ids:
        try:
            selected_ids = list(dict.fromkeys(str(uuid.UUID(value)) for value in raw_ids))
        except (ValueError, TypeError, AttributeError):
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        if len(selected_ids) > int(current_app.config.get("SQUAD_MAX_MEMBERS", 20)) or not campus_id or g.user_id in selected_ids:
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        selected_profiles = (get_db().table("profiles").select("id,email,campus_id")
                             .in_("id", selected_ids).eq("role", "student")
                             .eq("is_active", True).eq("campus_id", campus_id).execute()) or []
        if len(selected_profiles) != len(selected_ids):
            return jsonify({"error": MSG.SQUAD_CROSS_CAMPUS_BLOCKED}), 400
        emails = list(dict.fromkeys(emails + [profile["email"].strip().lower() for profile in selected_profiles]))

    max_members = int(current_app.config.get("SQUAD_MAX_MEMBERS", 20))
    if len(emails) > max_members:
        return jsonify({"error": MSG.SQUAD_MAX_MEMBERS_REACHED}), 400

    # Cross-campus block: every invited email must belong to the same campus.
    by_email = {profile["email"].strip().lower(): profile for profile in selected_profiles}
    if emails:
        member_profiles = db.table("profiles").select("id,email,campus_id").in_("email", emails).execute() or []
        by_email.update({p["email"]: p for p in member_profiles})
        for email in emails:
            prof = by_email.get(email)
            if prof and campus_id and prof.get("campus_id") and prof["campus_id"] != campus_id:
                return jsonify({"error": MSG.SQUAD_CROSS_CAMPUS_BLOCKED}), 400

    # squads_creator_id_name_key (UNIQUE(creator_id, name), added live for this fix) stops a rapid
    # double-click on "Create Squad" from creating two identical squads: the first insert wins, the
    # second gets a clean 409 instead of a duplicate row.
    try:
        squad = db.table("squads").insert({
            "name": name, "creator_id": g.user_id, "campus_id": campus_id,
        }).execute()
    except Exception as e:
        if "squads_creator_id_name_key" in str(e) or "duplicate" in str(e).lower():
            return jsonify({"error": MSG.SQUAD_DUPLICATE_NAME}), 409
        raise
    squad_row = squad[0] if isinstance(squad, list) else squad

    for email in emails:
        try:
            db.table("squad_roster").insert({
                "squad_id": squad_row["id"], "email": email,
                "user_id": by_email.get(email, {}).get("id"),
            })
        except Exception as e:
            # squad_roster_squad_id_email_key (duplicate email on this squad) is the expected case and is
            # silently fine; anything else is worth knowing about.
            logger.warning("create_squad: roster insert failed for %s on squad %s: %s", email, squad_row["id"], e)

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

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    selected_profile = None
    if data.get("user_id"):
        try:
            selected_id = str(uuid.UUID(data["user_id"]))
        except (ValueError, TypeError, AttributeError):
            return jsonify({"error": MSG.INVALID_INPUT}), 400
        # Search returns identities, never other students' email addresses.
        # Resolve contact server-side under the same campus/student boundary.
        if not squad.get("campus_id"):
            return jsonify({"error": MSG.SQUAD_CROSS_CAMPUS_BLOCKED}), 400
        selected_profile = (get_db().table("profiles").select("id,email,campus_id")
                            .eq("id", selected_id).eq("role", "student").eq("is_active", True)
                            .eq("campus_id", squad.get("campus_id")).single().execute())
        if not selected_profile or selected_id == g.user_id:
            return jsonify({"error": MSG.SQUAD_CROSS_CAMPUS_BLOCKED}), 400
        email = (selected_profile.get("email") or "").strip().lower()
    else:
        email = data.get("email")
        if not isinstance(email, str):
            return jsonify({"error": MSG.SQUAD_EMAIL_REQUIRED}), 400
        email = email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify({"error": MSG.SQUAD_EMAIL_REQUIRED}), 400

    current_count = db.table("squad_roster").select("id", count="exact").eq("squad_id", squad_id).eq("is_active", True).execute()
    roster_count = current_count.get("count", 0) if isinstance(current_count, dict) else len(current_count or [])
    max_members = int(current_app.config.get("SQUAD_MAX_MEMBERS", 20))
    if roster_count >= max_members:
        return jsonify({"error": MSG.SQUAD_MAX_MEMBERS_REACHED}), 400

    profile = selected_profile or db.table("profiles").select("id,campus_id").eq("email", email).single().execute()
    if profile and squad.get("campus_id") and profile.get("campus_id") and profile["campus_id"] != squad["campus_id"]:
        return jsonify({"error": MSG.SQUAD_CROSS_CAMPUS_BLOCKED}), 400

    # squad_roster has a UNIQUE(squad_id, email); a member removed earlier (is_active=False) already holds
    # that row, so a plain insert on re-add always hits the duplicate-key error. Reactivate that row instead.
    existing = db.table("squad_roster").select("id,is_active").eq("squad_id", squad_id).eq("email", email).execute() or []
    if existing:
        if existing[0].get("is_active"):
            return jsonify({"error": MSG.SQUAD_ALREADY_MEMBER}), 400
        row = db.table("squad_roster").eq("id", existing[0]["id"]).update({
            "is_active": True, "user_id": profile["id"] if profile else None,
        })
        return jsonify(row[0] if isinstance(row, list) else row), 201

    try:
        row = db.table("squad_roster").insert({
            "squad_id": squad_id, "email": email,
            "user_id": profile["id"] if profile else None,
        }).execute()
    except Exception:
        return jsonify({"error": MSG.SQUAD_ALREADY_MEMBER}), 400
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
    result = db.table("squad_roster").eq("id", member_id).eq("squad_id", squad_id).update({"is_active": False})
    if not result:
        return jsonify({"error": MSG.SQUAD_MEMBER_NOT_FOUND}), 404
    return jsonify({"message": MSG.SQUAD_MEMBER_REMOVED}), 200
