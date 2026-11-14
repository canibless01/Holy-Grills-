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
from app.db import get_db, SupabaseError
from app.messages import MSG
from app.middleware.auth import require_auth, require_role, optional_auth, resolve_scoped_campus_id
from app.middleware.rate_limit import rate_limit
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


def _staff_scope():
    scope=resolve_scoped_campus_id()
    if not _is_super() and not scope:raise svc.AmbassadorError(MSG.AMBASSADOR_CAMPUS_FORBIDDEN,status=403)
    return scope


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


def _milestone_values(data, partial=False):
    fields = {"metric", "threshold", "reward_type", "reward_amount", "reward_uses", "validity_days", "auto_issue", "is_active"}
    values = {key: value for key, value in data.items() if key in fields}
    if not partial:
        values = {"reward_uses": 1, "validity_days": 14, "auto_issue": False, "is_active": True, **values}
        if not {"metric", "threshold", "reward_type", "reward_amount"} <= values.keys():
            raise ValueError()
    if not values: raise ValueError()
    for key, value in values.items():
        if key in ("auto_issue", "is_active"):
            if not isinstance(value, bool): raise ValueError()
        elif key == "metric":
            if value not in svc.MILESTONE_METRICS: raise ValueError()
        elif key == "reward_type":
            if value not in svc.GRANT_CATEGORIES: raise ValueError()
        else:
            from decimal import Decimal, InvalidOperation
            try: number = Decimal(str(value))
            except InvalidOperation: raise ValueError()
            if isinstance(value,bool) or not number.is_finite() or number <= 0: raise ValueError()
            if key != "reward_amount" and number != int(number): raise ValueError()
            if key == "validity_days" and number > 365: raise ValueError()
            if key == "threshold" and number > 2147483647:raise ValueError()
            if key == "reward_amount" and number > 1000000:raise ValueError()
            if key == "reward_uses" and number > 100: raise ValueError()
            values[key] = float(number) if key == "reward_amount" else int(number)
    if values.get('reward_type')=='meal_discount' and 'reward_amount' in values:
        amount=Decimal(str(values['reward_amount']))
        if amount.quantize(Decimal('0.01'))!=amount:raise ValueError()
    if values.get('reward_type') in ('hp','free_side') and 'reward_amount' in values:
        amount = values['reward_amount']
        if amount != int(amount) or (values['reward_type'] == 'free_side' and amount > 20): raise ValueError()
    return values


# ---------------------------------------------------------------------------
# Public tracking (the ?ref= link) — works for guests and logged-in users
# ---------------------------------------------------------------------------
@ambassadors_bp.route("/track-click", methods=["POST"])
@optional_auth
@rate_limit(60, 60)
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
    rows = svc.staff_ambassador_list(db, _staff_scope(), _is_super())
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
    scope=_staff_scope()
    if profile.get("is_active") is False:return jsonify({"error":MSG.AMBASSADOR_USER_NOT_FOUND}),404
    if scope and profile.get("campus_id") != scope:
        return jsonify({"error": MSG.AMBASSADOR_CAMPUS_FORBIDDEN}), 403
    row = svc.tag_ambassador(g.user_id, profile)
    return jsonify({"ambassador": row}), 201


@ambassadors_bp.route("/staff/ambassadors/<ambassador_id>", methods=["DELETE"])
@require_role("admin")
def staff_untag_ambassador(ambassador_id):
    if not validate_uuid(ambassador_id):return jsonify({'error':MSG.AMBASSADOR_NOT_FOUND}),404
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
        get_db(), month, _staff_scope(), _is_super())
    return jsonify({"messages": rows, "month": month}), 200


@ambassadors_bp.route("/staff/promo-messages", methods=["POST"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_create_promo():
    data = _body() or {}
    for field in ('caption', 'image_url', 'month'):
        if data.get(field) is not None and not isinstance(data[field], str):
            return jsonify({'error': MSG.AUTH_FIELD_INVALID.format(field=field)}), 400
    try:
        result = svc.create_promo_message(
            get_db(),
            {"id": g.user_id, "role": g.user_role, "campus_id": _staff_scope()},
            image_url=str(data.get("image_url") or "").strip() or None,
            caption=str(data.get("caption") or ""),
            target_all=data.get("target_all", False),
            ambassador_ids=data.get("ambassador_ids", []),
            month=str(data.get("month") or "").strip() or svc.current_month(),
            request_id=data.get("request_id"),
        )
    except svc.AmbassadorError as exc:
        return jsonify({"error": str(exc)}), exc.status
    return jsonify(result), 201


@ambassadors_bp.route("/staff/promo-messages/<message_id>/assignments", methods=["GET"])
@require_role(COMMUNITY_MANAGER_ROLE, "admin")
def staff_promo_assignments(message_id):
    if not validate_uuid(message_id):
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    scope=_staff_scope()
    rows = svc.promo_assignments(get_db(), message_id, campus_id=scope)
    # Campus scope: hide another campus's recipients from a campus manager.
    if scope or not _is_super():
        rows = [r for r in rows if (r.get("profile") or {}).get("campus_id") == scope]
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
        get_db(), month, _staff_scope(), _is_super())
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
    scope=_staff_scope()
    if _is_super() and scope is None:
        rows=get_db().table('ambassador_milestones').select('*').order('metric').order('threshold').order('id').execute() or []
    else:rows=svc.list_milestones(get_db(),scope,include_inactive=True)
    return jsonify({"milestones": rows}), 200


@ambassadors_bp.route("/staff/milestones", methods=["POST"])
@require_role("admin")
def staff_create_milestone():
    denied = _require_financial_admin()
    if denied:
        return denied
    data=_body() or {}
    try:
        values=_milestone_values(data)
        scope=None if _is_super() and data.get('global') is True else _staff_scope()
        if _is_super() and data.get('global') is not True and not scope:raise ValueError()
        request_id=data.get('request_id') or str(uuid.uuid4())
        if not validate_uuid(request_id):raise ValueError()
    except (TypeError,ValueError):return jsonify({'error':MSG.AMBASSADOR_MILESTONE_INVALID}),400
    try:
        result=get_db().rpc('hg_write_ambassador_milestone',{'p_actor':g.user_id,'p_request':request_id,'p_id':request_id,'p_scope':scope,'p_values':values,'p_expected':None,'p_create':True})
    except SupabaseError as exc:return _milestone_write_error(exc)
    return jsonify(result),200 if result.get('replayed') else 201


@ambassadors_bp.route("/staff/milestones/<milestone_id>", methods=["PATCH"])
@require_role("admin")
def staff_update_milestone(milestone_id):
    denied = _require_financial_admin()
    if denied:
        return denied
    if not validate_uuid(milestone_id):
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    data = _body() or {}
    db = get_db()
    existing = db.table("ambassador_milestones").select("*").eq("id",milestone_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    if not _is_super() and (not getattr(g,"campus_id",None) or existing.get("campus_id") != g.campus_id):
        return jsonify({"error": MSG.RESOURCE_ACCESS_DENIED}), 403
    scope = _staff_scope()
    if scope and existing.get("campus_id") not in (None, scope):
        return jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404
    try:
        patch = _milestone_values(data, partial=True)
        _milestone_values({**existing, **patch})
    except (TypeError, ValueError): return jsonify({"error": MSG.AMBASSADOR_MILESTONE_INVALID}), 400
    request_id=data.get('request_id') or str(uuid.uuid4())
    if not validate_uuid(request_id):return jsonify({'error':MSG.AMBASSADOR_MILESTONE_INVALID}),400
    expected=data.get('expected_updated_at') or existing.get('updated_at')
    from app.utils.admin_helpers import as_instant
    try:expected=as_instant(expected)
    except (TypeError,ValueError):return jsonify({'error':MSG.AMBASSADOR_MILESTONE_INVALID}),400
    try:
        result=db.rpc('hg_write_ambassador_milestone',{'p_actor':g.user_id,'p_request':request_id,'p_id':milestone_id,'p_scope':existing.get('campus_id'),'p_values':patch,'p_expected':expected,'p_create':False})
    except SupabaseError as exc:return _milestone_write_error(exc)
    return jsonify(result),200


def _milestone_write_error(exc):
    value=str(exc)
    if 'HG_AMB_MILESTONE_ACCESS' in value:return jsonify({'error':MSG.RESOURCE_ACCESS_DENIED}),403
    if 'HG_AMB_MILESTONE_STALE' in value:return jsonify({'error':MSG.AMBASSADOR_MILESTONE_STALE}),409
    if 'HG_AMB_MILESTONE_CONFLICT' in value:return jsonify({'error':MSG.AMBASSADOR_MILESTONE_CONFLICT}),409
    if 'HG_AMB_MILESTONE_INVALID' in value:return jsonify({'error':MSG.AMBASSADOR_MILESTONE_INVALID}),400
    raise exc


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
    db = get_db()
    scope=_staff_scope()
    if not ambassador_id and (scope or not _is_super()):
        allowed = [a['profile_id'] for a in db.table('ambassadors').select('profile_id').eq(
            'status', 'active').eq('campus_id', scope).execute() or []]
        rows = svc.list_grants(db, ambassador_ids=allowed)
    else:
        rows = svc.list_grants(db, ambassador_id or None)
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
            {"id": g.user_id, "role": g.user_role, "campus_id": _staff_scope()},
            ambassador_id=ambassador_id,
            category=str(data.get("reward_type") or data.get("category") or "").strip(),
            amount=data.get("amount", 0),
            reason=str(data.get("reason") or ""),
            month=str(data.get("month") or "").strip() or svc.current_month(),
            validity_days=data.get("validity_days"),
            uses_count=data.get("uses_count", 1),
            source=str(data.get("source") or "manual"),
            milestone_claim_id=data.get("milestone_claim_id"),
            override=data.get("override_duplicate", False),
        )
    except svc.DuplicateGrant as exc:
        return jsonify({"error": str(exc), "code": "DUPLICATE_MONTHLY_GRANT"}), 409
    except svc.AmbassadorError as exc:
        return jsonify({"error": str(exc)}), exc.status
    except (TypeError, ValueError):
        return jsonify({"error": MSG.AMBASSADOR_GRANT_AMOUNT_INVALID}), 400
    return jsonify({"grant": grant}), 201

@ambassadors_bp.errorhandler(svc.AmbassadorError)
def programme_error(error):
    return jsonify({"error": str(error)}), error.status
