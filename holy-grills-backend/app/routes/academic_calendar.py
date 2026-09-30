"""
Academic Calendar routes — public listing and admin CRUD.

Public / Student-facing:
  GET /api/academic-calendar          — list active entries for campus
  GET /api/academic-calendar/current  — get currently active term/period

Admin:
  GET   /api/admin/academic-calendar       — list entries
  POST  /api/admin/academic-calendar       — create entry
  PATCH /api/admin/academic-calendar/<id>  — update entry or set is_active: false
"""

import requests
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role, optional_auth, resolve_scoped_campus_id
from app.db import get_user_client, SupabaseError
from app.messages import MSG
from app.utils.admin_helpers import get_json_object, as_bool, as_text, db_error_response
from app.utils.campus_scope import as_campus_id, assert_can_modify, campus_or_global, public_campus, resolve_write_campus
from app.utils.logger import get_logger
from app.utils.tz import today_wat
from app.utils.validators import validate_choice, validate_uuid
from datetime import datetime, timezone

logger = get_logger(__name__)

academic_calendar_bp = Blueprint("academic_calendar", __name__)
admin_academic_calendar_bp = Blueprint("admin_academic_calendar", __name__)

# Mirrors the DB CHECK academic_calendar_period_type_check. Keep in sync.
PERIOD_TYPES = ("semester", "exam", "break", "holiday", "orientation")


def _requested_campus():
    """Return (campus_id_or_None, error_response_or_None). Resolves via the same
    query-param -> X-Campus-ID header -> g.campus_id priority every other guest-facing
    route uses (app.routes.events._get_campus_id is the reference implementation this
    codebase settled on), then validates the result as a UUID."""
    from app.routes.events import _get_campus_id
    try:
        return as_campus_id(_get_campus_id()), None
    except ValueError:
        return None, (jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400)


def _parse_date(value):
    """'YYYY-MM-DD' -> date, or None if invalid."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public / Student-facing endpoints
# ---------------------------------------------------------------------------

@academic_calendar_bp.route("", methods=["GET"])
@optional_auth
def list_active_academic_calendar():
    """
    List active academic calendar entries for the campus.
    """
    db = get_user_client()
    requested, error = _requested_campus()
    if error:
        return error
    campus_id = public_campus(requested)
    try:
        q = campus_or_global(db.table("academic_calendar").select("*").eq("is_active", True), campus_id)
        if request.args.get("period_type"):
            q = q.eq("period_type", request.args.get("period_type"))
        if request.args.get("academic_year"):
            q = q.eq("academic_year", request.args.get("academic_year"))
        rows = q.order("start_date", ascending=False).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        logger.error("list_active_academic_calendar failed: %s", e)
        return jsonify({"error": MSG.ACADEMIC_CALENDAR_UNAVAILABLE}), 503
    return jsonify({"academic_calendar": rows, "count": len(rows)}), 200


@academic_calendar_bp.route("/current", methods=["GET"])
@optional_auth
def get_current_academic_period():
    """
    Get the currently active academic term/period based on today's WAT date.
    """
    db = get_user_client()
    today_str = today_wat().isoformat()
    requested, error = _requested_campus()
    if error:
        return error
    campus_id = public_campus(requested)
    try:
        q = (
            db.table("academic_calendar").select("*").eq("is_active", True)
            .lte("start_date", today_str).gte("end_date", today_str)
        )
        q = campus_or_global(q, campus_id)
        rows = q.order("start_date", ascending=False).limit(1).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        logger.error("get_current_academic_period failed: %s", e)
        return jsonify({"error": MSG.ACADEMIC_CALENDAR_UNAVAILABLE}), 503
    if not rows:
        return jsonify({"current_period": None, "message": MSG.NO_ACTIVE_ACADEMIC_TERM}), 200
    return jsonify({"current_period": rows[0]}), 200


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@admin_academic_calendar_bp.route("/academic-calendar", methods=["GET"])
@require_role("admin")
def list_academic_calendar_entries():
    """
    List academic calendar entries (admin only).
    """
    db = get_user_client()
    requested, error = _requested_campus()
    if error:
        return error
    campus_id = resolve_scoped_campus_id(requested)  # admin: own campus (param ignored); super_admin: param or all
    try:
        # none_means_all=True: an admin always has a campus_id by this point (B-27), so this only changes
        # behavior for super_admin with no ?campus_id= — they see every campus's entries, not just globals.
        q = campus_or_global(db.table("academic_calendar").select("*"), campus_id, none_means_all=True)
        if request.args.get("period_type"):
            q = q.eq("period_type", request.args.get("period_type"))
        if request.args.get("academic_year"):
            q = q.eq("academic_year", request.args.get("academic_year"))
        if request.args.get("is_active") is not None:
            q = q.eq("is_active", request.args.get("is_active").lower() == "true")
        rows = q.order("start_date", ascending=False).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        logger.error("list_academic_calendar_entries failed: %s", e)
        return jsonify({"error": MSG.ACADEMIC_CALENDAR_UNAVAILABLE}), 503
    return jsonify({"academic_calendar": rows, "count": len(rows)}), 200


@admin_academic_calendar_bp.route("/academic-calendar", methods=["POST"])
@require_role("admin")
def create_academic_calendar_entry():
    """
    Create an academic calendar entry (admin only).
    """
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    for field in ("period_type", "name", "start_date", "end_date", "academic_year"):
        if not data.get(field):
            return jsonify({"error": MSG.FIELD_REQUIRED.format(field=field)}), 400
    try:
        period_type = as_text(data["period_type"], 50)
        name = as_text(data["name"], 200)
        academic_year = as_text(data["academic_year"], 50)
        start_date = _parse_date(as_text(data["start_date"], 10))
        end_date = _parse_date(as_text(data["end_date"], 10))
        is_active = as_bool(data.get("is_active", True))
        description = str(data.get("description") or "").strip()
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    ok, message = validate_choice(period_type, PERIOD_TYPES, "period_type")
    if not ok:
        return jsonify({"error": message}), 400
    if start_date is None or end_date is None:
        return jsonify({"error": MSG.INVALID_DATE_FORMAT}), 400
    if end_date < start_date:
        return jsonify({"error": MSG.END_DATE_BEFORE_START}), 400

    try:
        requested_campus = as_campus_id(data.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    campus_id = resolve_write_campus(requested_campus)  # 403 if a campus admin names another campus; None = global for super_admin

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "period_type": period_type,
        "name": name,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "academic_year": academic_year,
        "description": description,
        "campus_id": campus_id,
        "is_active": is_active,
        "created_at": now,
        "updated_at": now,
    }
    db = get_user_client()
    try:
        row = db.table("academic_calendar").insert(payload)
        row = row[0] if isinstance(row, list) and row else row
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "create_academic_calendar_entry", MSG.ACADEMIC_CALENDAR_ENTRY_EXISTS)
    return jsonify(row), 201


@admin_academic_calendar_bp.route("/academic-calendar/<entry_id>", methods=["PATCH"])
@require_role("admin")
def update_academic_calendar_entry(entry_id):
    """
    Update an academic calendar entry or set is_active: false (admin only).
    """
    if not validate_uuid(entry_id):
        return jsonify({"error": MSG.ACADEMIC_CALENDAR_ENTRY_NOT_FOUND}), 404
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    db = get_user_client()
    try:
        existing = (
            db.table("academic_calendar").select("id,campus_id,start_date,end_date")
            .eq("id", entry_id).single().execute()
        )
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_academic_calendar_entry.lookup")
    if not existing:
        return jsonify({"error": MSG.ACADEMIC_CALENDAR_ENTRY_NOT_FOUND}), 404
    assert_can_modify(existing.get("campus_id"))  # global (NULL-campus) entries are super_admin-only

    allowed = {"period_type", "name", "start_date", "end_date", "academic_year", "campus_id", "description", "is_active"}
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    dates = {}
    try:
        for key, limit in (("period_type", 50), ("name", 200), ("academic_year", 50)):
            if key in payload:
                payload[key] = as_text(payload[key], limit)
        if "description" in payload:
            payload["description"] = str(payload["description"] or "").strip()
        if "is_active" in payload:
            payload["is_active"] = as_bool(payload["is_active"])
        for key in ("start_date", "end_date"):
            if key in payload:
                dates[key] = _parse_date(as_text(payload[key], 10))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if "period_type" in payload:
        ok, message = validate_choice(payload["period_type"], PERIOD_TYPES, "period_type")
        if not ok:
            return jsonify({"error": message}), 400
    if any(value is None for value in dates.values()):
        return jsonify({"error": MSG.INVALID_DATE_FORMAT}), 400
    new_start = dates.get("start_date") or _parse_date(existing.get("start_date"))
    new_end = dates.get("end_date") or _parse_date(existing.get("end_date"))
    if new_start and new_end and new_end < new_start:
        return jsonify({"error": MSG.END_DATE_BEFORE_START}), 400
    for key, value in dates.items():
        payload[key] = value.isoformat()

    if "campus_id" in payload:
        new_campus = payload["campus_id"] or None
        if new_campus is not None:
            if not isinstance(new_campus, str) or not validate_uuid(new_campus):
                return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
            new_campus = new_campus.lower()
        if getattr(g, "user_role", None) != "super_admin" and new_campus != getattr(g, "campus_id", None):
            return jsonify({"error": MSG.RESOURCE_ACCESS_DENIED}), 403
        payload["campus_id"] = new_campus

    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table("academic_calendar").eq("id", entry_id).update(payload)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_academic_calendar_entry", MSG.ACADEMIC_CALENDAR_ENTRY_EXISTS)
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    return jsonify(result[0] if isinstance(result, list) else result), 200
