"""
Campus Ambassador Programme — HTTP routes.

Role model (enforced here AND in RLS policies / RPC grants):
  * community_manager / admin / super_admin — read programme data, distribute
    promos, record activity, write recommendations (campus-scoped except super).
  * admin / super_admin only — tag/untag ambassadors, configure milestones,
    record reward decisions and issue grants.
  * any authenticated student tagged as an ambassador — read their own
    programme data via GET /ambassadors/me and their meal discounts.
  * everyone (incl. guests) — POST /track-click so ?ref links work pre-login.
"""
import uuid

from flask import Blueprint, request, jsonify, g, current_app

from app.constants import ADMIN_ROLES, COMMUNITY_MANAGER_ROLE
from app.db import get_db
from app.messages import MSG
from app.middleware.auth import require_auth, require_role, optional_auth
from app.services import ambassador_service as svc
from app.utils.logger import get_logger
from app.utils.validators import validate_uuid

logger = get_logger(__name__)

ambassadors_bp = Blueprint("ambassadors", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _is_super():
    return getattr(g, "user_role", None) == "super_admin"


def _is_financial_admin():
    return getattr(g, "user_role", None) in ADMIN_ROLES


def _require_financial_admin():
    if not _is_financial_admin():
        return jsonify({"error": MSG.AMBASSADOR_FINANCIAL_ADMIN_ONLY}), 403
    return None


def _guard_ambassador(ambassador_id: str):
    """Load + campus check; raises AmbassadorError (mapped below)."""
    if not validate_uuid(ambassador_id):
        raise svc.AmbassadorError(MSG.AMBASSADOR_NOT_FOUND, status=404)
    return svc._active_ambassador(get_db(), ambassador_id)


# ---------------------------------------------------------------------------
# Public tracking (the ?ref= link) — works for guests and logged-in users
# ---------------------------------------------------------------------------
@ambassadors_bp.route("/track-click", methods=["POST"])
@optional_auth
def track_click():
    data = _body() or {}
    ref_code = str(data.get("ref_code") or "").strip()
    if not ref_code:
        return jsonify({"error": MSG.AMBASSADOR_REF_REQUIRED}), 400
    anonymous_id = str(data.get("anonymous_id") or "").strip() or str(uuid.uuid4())
    result = svc.record_click(
        ref_code=ref_code,
        anonymous_id=anonymous_id,
        visitor_user_id=getattr(g, "user_id", None),
        campus_id=getattr(g, "campus_id", None),
    )
    # Hand the browser a stable anonymous id so the trail survives until login.
    result["anonymous_id"] = anonymous_id
    return jsonify(result), 200


@ambassadors_bp.route("/merge-visitor", methods=["POST"])
@require_auth
def merge_visitor():
    data = _body() or {}
    anonymous_id = str(data.get("anonymous_id") or "").strip()
    if not anonymous_id:
        return jsonify({"error": MSG.AMBASSADOR_ANON_REQUIRED}), 400
    return jsonify(svc.merge_visitor(anonymous_id, g.user_id)), 200


# ---------------------------------------------------------------------------
# Ambassador self-service (own data only)
# ---------------------------------------------------------------------------
@ambassadors_bp.route("/me", methods=["GET"])
@require_auth
def my_ambassador_programme():
    # Service client, not the RLS user client: the payload joins staff-read
    # tables (milestones, promo assignments) and may create milestone claims /
    # auto-issue grants, none of which authenticated users have policies for.
    # Every query is hard-scoped to g.user_id from the verified JWT, so this
    # cannot read another student's programme; the self-read RLS policies stay
    # as defense in depth for any direct table access.
    data = svc.ambassador_dashboard(
        get_db(), g.user_id, current_app.config.get("FRONTEND_URL", ""))
    if data is None:
        # Not an ambassador — a normal 200 flag, not an error, so the student
        # dashboard can hide the card without a failed request.
        return jsonify({"is_ambassador": False}), 200
    return jsonify(data), 200


@ambassadors_bp.route("/meal-discounts", methods=["GET"])
@require_auth
def my_meal_discounts():
    # Service client: list_my_discounts also runs the service-only expiry sweep
    # RPC, and rows are filtered to the JWT user inside the service.
    return jsonify({
        "discounts": svc.list_my_discounts(get_db(), g.user_id),
    }), 200


# ---------------------------------------------------------------------------
# Staff: ambassador roster + tagging
# ---------------------------------------------------------------------------
@ambassadors_bp.route("/staff/ambassadors", methods=["GET"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_list_ambassadors():
    db = get_db()
    month = svc.parse_month(request.args.get("month"))
    rows = svc.staff_ambassador_list(db, getattr(g, "campus_id", None), _is_super())
    return jsonify({"ambassadors": rows, "month": month}), 200


@ambassadors_bp.route("/staff/ambassadors/<ambassador_id>", methods=["GET"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_ambassador_detail(ambassador_id):
    db = get_db()
    _guard_ambassador(ambassador_id)
    month = svc.parse_month(request.args.get("month"))
    review = svc.build_review(db, ambassador_id, month)
    grants = svc.list_grants(db, ambassador_id)
    return jsonify({"review": review, "grants": grants}), 200


@ambassadors_bp.route("/staff/ambassadors", methods=["POST"])
@require_role("admin")
def staff_tag_ambassador():
    data = _body() or {}
    user_id = str(data.get("user_id") or "").strip()
    if not validate_uuid(user_id):
        return jsonify({"error": MSG.AMBASSADOR_USER_REQUIRED}), 400
    db = get_db()
    profile = db.table("profiles").select(
        "id,full_name,nickname,role,campus_id,is_active"
    ).eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AMBASSADOR_USER_NOT_FOUND}), 404
    if not _is_super() and profile.get("campus_id") != getattr(g, "campus_id", None):
        return jsonify({"error": MSG.AMBASSADOR_CAMPUS_FORBIDDEN}), 403
    row = svc.tag_ambassador(g.user_id, profile)
    return jsonify({"ambassador": row}), 201


@ambassadors_bp.route("/staff/ambassadors/<ambassador_id>", methods=["DELETE"])
@require_role("admin")
def staff_untag_ambassador(ambassador_id):
    _guard_ambassador(ambassador_id)
    row = svc.untag_ambassador(g.user_id, ambassador_id)
    return jsonify({"ambassador": row}), 200


# ---------------------------------------------------------------------------
# Staff: promo distribution + manual activity tracking
# ---------------------------------------------------------------------------
@ambassadors_bp.route("/staff/promo-messages", methods=["GET"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_list_promos():
    month = svc.parse_month(request.args.get("month"))
    rows = svc.list_promo_messages(
        get_db(), month, getattr(g, "campus_id", None), _is_super())
    return jsonify({"messages": rows, "month": month}), 200


@ambassadors_bp.route("/staff/promo-messages", methods=["POST"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_create_promo():
    data = _body() or {}
    try:
        result = svc.create_promo_message(
            get_db(),
            {"id": g.user_id, "role": g.user_role, "campus_id": getattr(g, "campus_id", None)},
            image_url=str(data.get("image_url") or "").strip() or None,
            caption=str(data.get("caption") or ""),
            target_all=bool(data.get("target_all")),
            ambassador_ids=[str(x) for x in (data.get("ambassador_ids") or []) if validate_uuid(x)],
            month=str(data.get("month") or "").strip() or svc.current_month(),
        )
    except svc.AmbassadorError as exc:
        return jsonify({"error": str(exc)}), exc.status
    return jsonify(result), 201


@ambassadors_bp.route("/staff/promo-messages/<message_id>/assignments", methods=["GET"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_promo_assignments(message_id):
    if not validate_uuid(message_id):
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    rows = svc.promo_assignments(get_db(), message_id)
    # Campus scope: hide another campus's recipients from a campus manager.
    if not _is_super():
        rows = [r for r in rows
                if (r.get("profile") or {}).get("campus_id") == getattr(g, "campus_id", None)]
    return jsonify({"assignments": rows}), 200


@ambassadors_bp.route("/staff/assignments/<assignment_id>", methods=["PATCH"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_update_assignment(assignment_id):
    data = _body() or {}
    if not validate_uuid(assignment_id):
        return jsonify({"error": MSG.AMBASSADOR_ASSIGNMENT_NOT_FOUND}), 404
    try:
        row = svc.set_assignment_status(
            get_db(), g.user_id, assignment_id,
            str(data.get("status") or "").strip(),
            data.get("evidence_note"),
        )
    except svc.AmbassadorError as exc:
        return jsonify({"error": str(exc)}), exc.status
    return jsonify({"assignment": row}), 200


# ---------------------------------------------------------------------------
# Staff: monthly reviews
# ---------------------------------------------------------------------------
@ambassadors_bp.route("/staff/reviews", methods=["GET"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_list_reviews():
    month = svc.parse_month(request.args.get("month"))
    rows = svc.list_monthly_reviews(
        get_db(), month, getattr(g, "campus_id", None), _is_super())
    return jsonify({"reviews": rows, "month": month}), 200


@ambassadors_bp.route("/staff/reviews/<ambassador_id>/recommendation", methods=["POST"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_recommendation(ambassador_id):
    data = _body() or {}
    try:
        _guard_ambassador(ambassador_id)
        review = svc.submit_recommendation(
            get_db(), g.user_id, ambassador_id,
            str(data.get("month") or "").strip() or svc.current_month(),
            str(data.get("recommendation") or "").strip(),
            data.get("note"),
        )
    except svc.AmbassadorError as exc:
        return jsonify({"error": str(exc)}), exc.status
    return jsonify({"review": review}), 200


@ambassadors_bp.route("/staff/reviews/<ambassador_id>/decision", methods=["POST"])
@require_role("admin")
def staff_decision(ambassador_id):
    denied = _require_financial_admin()
    if denied:
        return denied
    data = _body() or {}
    try:
        _guard_ambassador(ambassador_id)
        review = svc.record_decision(
            get_db(), g.user_id, ambassador_id,
            str(data.get("month") or "").strip() or svc.current_month(),
            str(data.get("decision") or "").strip(),
            data.get("note"),
        )
    except svc.AmbassadorError as exc:
        return jsonify({"error": str(exc)}), exc.status
    return jsonify({"review": review}), 200


# ---------------------------------------------------------------------------
# Admin: milestones configuration
# ---------------------------------------------------------------------------
@ambassadors_bp.route("/staff/milestones", methods=["GET"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_list_milestones():
    rows = svc.list_milestones(
        get_db(), getattr(g, "campus_id", None), include_inactive=True)
    return jsonify({"milestones": rows}), 200


@ambassadors_bp.route("/staff/milestones", methods=["POST"])
@require_role("admin")
def staff_create_milestone():
    denied = _require_financial_admin()
    if denied:
        return denied
    data = _body() or {}
    db = get_db()
    try:
        metric = str(data.get("metric") or "").strip()
        if metric not in svc.MILESTONE_METRICS:
            raise svc.AmbassadorError(MSG.AMBASSADOR_INVALID_METRIC)
        reward_type = str(data.get("reward_type") or "").strip()
        if reward_type not in svc.GRANT_CATEGORIES:
            raise svc.AmbassadorError(MSG.AMBASSADOR_INVALID_GRANT_CATEGORY)
        row = db.table("ambassador_milestones").insert({
            # Super admin creates global milestones; campus admins' rows are
            # pinned to their campus.
            "campus_id": None if _is_super() and data.get("global") else getattr(g, "campus_id", None),
            "metric": metric,
            "threshold": int(data.get("threshold")),
            "reward_type": reward_type,
            "reward_amount": float(data.get("reward_amount")),
            "reward_uses": max(1, int(data.get("reward_uses") or 1)),
            "validity_days": max(1, int(data.get("validity_days") or 14)),
            "auto_issue": bool(data.get("auto_issue")),
            "is_active": bool(data.get("is_active", True)),
            "created_by": g.user_id,
        }).execute()
    except (TypeError, ValueError):
        return jsonify({"error": MSG.AMBASSADOR_MILESTONE_INVALID}), 400
    row = row[0] if isinstance(row, list) else row
    svc.audit(g.user_id, "ambassador_milestone_created", row["id"], after=row)
    return jsonify({"milestone": row}), 201


@ambassadors_bp.route("/staff/milestones/<milestone_id>", methods=["PATCH"])
@require_role("admin")
def staff_update_milestone(milestone_id):
    denied = _require_financial_admin()
    if denied:
        return denied
    if not validate_uuid(milestone_id):
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    data = _body() or {}
    allowed = {"metric", "threshold", "reward_type", "reward_amount", "reward_uses",
               "validity_days", "auto_issue", "is_active"}
    patch = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not patch:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    db = get_db()
    row = db.table("ambassador_milestones").update(patch).eq("id", milestone_id).execute()
    row = row[0] if isinstance(row, list) and row else row
    if not row:
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    svc.audit(g.user_id, "ambassador_milestone_updated", milestone_id, after=patch)
    return jsonify({"milestone": row}), 200


# ---------------------------------------------------------------------------
# Admin: reward grants (the only financial endpoint)
# ---------------------------------------------------------------------------
@ambassadors_bp.route("/staff/grants", methods=["GET"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_list_grants():
    ambassador_id = request.args.get("ambassador_id")
    if ambassador_id and not validate_uuid(ambassador_id):
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    if ambassador_id:
        _guard_ambassador(ambassador_id)
    rows = svc.list_grants(get_db(), ambassador_id or None)
    if not _is_super() and not ambassador_id:
        # Campus managers only ever see their own campus's ambassadors.
        allowed = {a["profile_id"] for a in get_db().table("ambassadors").select(
            "profile_id").eq("status", "active").eq(
            "campus_id", getattr(g, "campus_id", None)).execute() or []}
        rows = [r for r in rows if r.get("ambassador_id") in allowed]
    return jsonify({"grants": rows}), 200


@ambassadors_bp.route("/staff/grants", methods=["POST"])
@require_role("admin")
def staff_create_grant():
    denied = _require_financial_admin()
    if denied:
        return denied
    data = _body() or {}
    ambassador_id = str(data.get("ambassador_id") or "").strip()
    if not validate_uuid(ambassador_id):
        return jsonify({"error": MSG.AMBASSADOR_USER_REQUIRED}), 400
    try:
        _guard_ambassador(ambassador_id)
        grant = svc.issue_grant(
            get_db(),
            {"id": g.user_id, "role": g.user_role, "campus_id": getattr(g, "campus_id", None)},
            ambassador_id=ambassador_id,
            category=str(data.get("reward_type") or data.get("category") or "").strip(),
            amount=float(data.get("amount") or 0),
            reason=str(data.get("reason") or ""),
            month=str(data.get("month") or "").strip() or svc.current_month(),
            validity_days=int(data["validity_days"]) if data.get("validity_days") else None,
            uses_count=int(data.get("uses_count") or 1),
            source=str(data.get("source") or "manual"),
            milestone_claim_id=data.get("milestone_claim_id"),
            override=bool(data.get("override_duplicate")),
        )
    except svc.DuplicateGrant as exc:
        return jsonify({"error": str(exc), "code": "DUPLICATE_MONTHLY_GRANT"}), 409
    except svc.AmbassadorError as exc:
        return jsonify({"error": str(exc)}), exc.status
    except (TypeError, ValueError):
        return jsonify({"error": MSG.AMBASSADOR_GRANT_AMOUNT_INVALID}), 400
    return jsonify({"grant": grant}), 201
