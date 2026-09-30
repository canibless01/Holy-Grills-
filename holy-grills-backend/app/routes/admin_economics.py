from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify
from app.db import get_user_client
from app.messages import MSG
from app.middleware.auth import require_role, resolve_scoped_campus_id
from app.services import economics_dashboard_service
from app.utils.settings import SettingError
from app.utils.tz import WAT_OFFSET
from app.utils.validators import validate_date, validate_uuid

admin_economics_bp = Blueprint("admin_economics", __name__)

_WAT = timezone(WAT_OFFSET)


def _econ_campus():
    """Effective campus: a super_admin may pick one with ?campus_id=; everyone else is pinned to their own.
    Raises ValueError if the effective value is not a UUID."""
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id") or None)
    if campus_id and not validate_uuid(campus_id):
        raise ValueError("campus")
    return campus_id


def _econ_window():
    """start_date / end_date (YYYY-MM-DD, WAT days) -> (start_utc | None, end_utc_EXCLUSIVE | None).
    Raises ValueError on malformed input."""
    s, e = request.args.get("start_date"), request.args.get("end_date")
    start = end = None
    if s:
        if not validate_date(s):
            raise ValueError("start_date")
        start = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=_WAT).astimezone(timezone.utc).isoformat()
    if e:
        if not validate_date(e):
            raise ValueError("end_date")
        end = (datetime.strptime(e, "%Y-%m-%d").replace(tzinfo=_WAT) + timedelta(days=1)).astimezone(timezone.utc).isoformat()
    return start, end


def _econ_args():
    """(campus_id, start_utc, end_utc_exclusive) or raises ValueError."""
    campus_id = _econ_campus()
    start, end = _econ_window()
    return campus_id, start, end


@admin_economics_bp.route("/overview", methods=["GET"])
@require_role("admin")
def economics_overview():
    # B-13 · ANL-01. Requires db.py's B-22 paginate patch (get_user_client(paginate=True)) —
    # see the separate db_py_paginate_patch.py note; db.py itself hasn't had its full pass yet.
    db = get_user_client(paginate=True)
    try:
        campus_id, start_date, end_date = _econ_args()
    except ValueError as exc:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS if str(exc) == "campus" else MSG.ANALYTICS_INVALID_DATE}), 400
    try:
        return jsonify(economics_dashboard_service.get_economics_overview(db, start_date, end_date, campus_id)), 200
    except SettingError:
        return jsonify({"error": MSG.HP_VALUE_NOT_CONFIGURED}), 503


@admin_economics_bp.route("/tier-breakdown", methods=["GET"])
@require_role("admin")
def economics_tier_breakdown():
    # B-13 · ANL-02
    db = get_user_client(paginate=True)
    try:
        campus_id, start_date, end_date = _econ_args()
    except ValueError as exc:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS if str(exc) == "campus" else MSG.ANALYTICS_INVALID_DATE}), 400
    return jsonify(economics_dashboard_service.get_tier_breakdown(db, start_date, end_date, campus_id)), 200


@admin_economics_bp.route("/redemption-analytics", methods=["GET"])
@require_role("admin")
def economics_redemption_analytics():
    # B-13 · ANL-03
    db = get_user_client(paginate=True)
    try:
        campus_id, start_date, end_date = _econ_args()
    except ValueError as exc:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS if str(exc) == "campus" else MSG.ANALYTICS_INVALID_DATE}), 400
    return jsonify(economics_dashboard_service.get_redemption_analytics(db, start_date, end_date, campus_id)), 200
