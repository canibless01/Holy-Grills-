"""
Departments routes — public listing and admin CRUD.

User-facing:
  GET  /api/departments                     — list active departments (grouped by faculty)
  GET  /api/departments/faculties           — list distinct faculty names
  GET  /api/departments/<dept_id>           — get single department detail

Admin:
  POST   /api/admin/departments             — create department
  PATCH  /api/admin/departments/<dept_id>   — update department
  DELETE /api/admin/departments/<dept_id>   — deactivate (soft-delete) department
  POST   /api/admin/departments/<dept_id>/restore  — reactivate department
"""

import re
import requests
from flask import Blueprint, request, jsonify
from app.middleware.auth import require_role, optional_auth
from app.db import get_user_client, SupabaseError
from app.messages import MSG
from app.utils.admin_helpers import get_json_object, as_bool, as_int, as_text, db_error_response
from app.utils.campus_scope import (
    as_campus_id, campus_or_global, prefer_campus_rows, public_campus,
    resolve_write_campus, assert_can_modify,
)
from app.utils.logger import get_logger
from app.utils.validators import validate_uuid
from datetime import datetime, timezone

logger = get_logger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _make_slug(name):
    slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-").replace("&", "and"))
    return re.sub(r"-{2,}", "-", slug).strip("-")


# Departments are either global (campus_id NULL) or belong to one campus
departments_bp = Blueprint("departments", __name__)

# Admin department CRUD: a campus admin manages their own campus; super_admin manages global and any campus
admin_departments_bp = Blueprint("admin_departments", __name__)

# ---------------------------------------------------------------------------
# User-facing endpoints
# ---------------------------------------------------------------------------

@departments_bp.route("", methods=["GET"])
@optional_auth
def list_departments():
    """
    List active departments, optionally grouped by faculty.
    No authentication required — used at registration and profile setup.
    ---
    tags: [Departments]
    security: []
    parameters:
      - in: query
        name: faculty
        type: string
        description: Filter by faculty name
      - in: query
        name: grouped
        type: boolean
        default: false
        description: If true, returns departments nested under faculty keys
      - in: query
        name: campus_id
        type: string
        description: Campus to list for (guests choose one; signed-in users default to their own). Global rows are always included.
    responses:
      200:
        description: List of active departments
    """
    db = get_user_client()
    try:
        requested = as_campus_id(request.args.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    campus_id = public_campus(requested)
    try:
        q = db.table("departments").select("id,name,slug,faculty,sort_order,campus_id").eq("is_active", True)
        faculty_filter = request.args.get("faculty")
        if faculty_filter:
            q = q.eq("faculty", faculty_filter)
        rows = campus_or_global(q, campus_id).order("sort_order", ascending=True).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        logger.error("list_departments failed: %s", e)
        return jsonify({"error": MSG.REFERENCE_DATA_UNAVAILABLE}), 503
    rows = prefer_campus_rows(rows, lambda r: r["name"].strip().lower())
    rows.sort(key=lambda d: (d.get("sort_order") or 0, d.get("name") or ""))   # B-33: stable order when sort_order ties
    grouped = request.args.get("grouped", "false").lower() == "true"
    if not grouped:
        return jsonify({"departments": rows, "count": len(rows)}), 200
    by_faculty: dict = {}
    for dept in rows:
        by_faculty.setdefault(dept.get("faculty", "Other"), []).append(dept)
    result = [{"faculty": fac, "departments": depts} for fac, depts in sorted(by_faculty.items())]
    return jsonify({"faculties": result, "count": len(rows)}), 200


@departments_bp.route("/faculties", methods=["GET"])
@optional_auth
def list_faculties():
    """
    List distinct faculty names from active departments.
    ---
    tags: [Departments]
    security: []
    parameters:
      - in: query
        name: campus_id
        type: string
        description: Campus to list for (guests choose one; signed-in users default to their own). Global rows are always included.
    responses:
      200:
        description: List of faculty names
    """
    db = get_user_client()
    try:
        requested = as_campus_id(request.args.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    campus_id = public_campus(requested)
    try:
        q = db.table("departments").select("faculty,campus_id").eq("is_active", True)
        rows = campus_or_global(q, campus_id).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        logger.error("list_faculties failed: %s", e)
        return jsonify({"error": MSG.REFERENCE_DATA_UNAVAILABLE}), 503
    faculties = sorted({r["faculty"] for r in rows if r.get("faculty")})
    return jsonify({"faculties": faculties}), 200


@departments_bp.route("/<dept_id>", methods=["GET"])
def get_department(dept_id):
    """
    Get a single department by ID.
    ---
    tags: [Departments]
    security: []
    parameters:
      - in: path
        name: dept_id
        type: string
        required: true
    responses:
      200:
        description: Department detail
      404:
        description: Not found
    """
    if not validate_uuid(dept_id):
        return jsonify({"error": MSG.DEPARTMENT_NOT_FOUND}), 404
    db = get_user_client()
    try:
        dept = (
            db.table("departments").select("id,name,slug,faculty,sort_order,campus_id")
            .eq("id", dept_id).eq("is_active", True).single().execute()
        )
    except (SupabaseError, requests.RequestException) as e:
        logger.error("get_department failed: %s", e)
        return jsonify({"error": MSG.REFERENCE_DATA_UNAVAILABLE}), 503
    if not dept:
        return jsonify({"error": MSG.DEPARTMENT_NOT_FOUND}), 404
    return jsonify(dept), 200


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@admin_departments_bp.route("/departments", methods=["GET"])
@require_role("admin")
def admin_list_departments():
    """
    List all departments including inactive ones (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: faculty
        type: string
      - in: query
        name: is_active
        type: boolean
    responses:
      200:
        description: All departments
    """
    db = get_user_client()
    q = db.table("departments").select("*")
    if request.args.get("faculty"):
        q = q.eq("faculty", request.args["faculty"])
    if request.args.get("is_active") is not None:
        q = q.eq("is_active", request.args.get("is_active").lower() == "true")
    rows = q.order("sort_order", ascending=True).execute() or []
    return jsonify({"departments": rows, "count": len(rows)}), 200


@admin_departments_bp.route("/departments", methods=["POST"])
@require_role("admin")
def admin_create_department():
    """
    Create a new department (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, faculty]
          properties:
            name: {type: string, description: "Full department name"}
            slug: {type: string, description: "URL-friendly slug (auto-generated if omitted)"}
            faculty: {type: string, description: "Faculty this department belongs to"}
            is_active: {type: boolean, default: true}
            sort_order: {type: integer, default: 0}
            campus_id: {type: string, description: "super_admin only: the campus, or omit for a global department. Campus admins always create in their own campus."}
    responses:
      201:
        description: Department created
      400:
        description: Validation error
    """
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    if not data.get("name") or not data.get("faculty"):
        return jsonify({"error": MSG.DEPARTMENT_NAME_FACULTY_REQUIRED}), 400
    try:
        name = as_text(data["name"], 150)
        faculty = as_text(data["faculty"], 150)
        is_active = as_bool(data.get("is_active", True))
        sort_order = as_int(data.get("sort_order", 0), 0, 100000)
        slug = as_text(data["slug"], 100).lower() if data.get("slug") else _make_slug(name)
        requested_campus = as_campus_id(data.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if not _SLUG_RE.match(slug):
        return jsonify({"error": MSG.INVALID_SLUG}), 400
    # Campus admin: always their own campus (403 if they name another). super_admin: the named campus, or global.
    campus_id = resolve_write_campus(requested_campus)
    now = datetime.now(timezone.utc).isoformat()
    db = get_user_client()
    try:
        row = db.table("departments").insert({
            "name": name, "slug": slug, "faculty": faculty, "campus_id": campus_id,
            "is_active": is_active, "sort_order": sort_order,
            "created_at": now, "updated_at": now,
        })
        row = row[0] if isinstance(row, list) and row else row
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "admin_create_department", MSG.DEPARTMENT_EXISTS)
    return jsonify(row), 201


@admin_departments_bp.route("/departments/<dept_id>", methods=["PATCH"])
@require_role("admin")
def admin_update_department(dept_id):
    """
    Update a department (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: dept_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            name: {type: string}
            slug: {type: string}
            faculty: {type: string}
            is_active: {type: boolean}
            sort_order: {type: integer}
    responses:
      200:
        description: Department updated
      404:
        description: Department not found
    """
    if not validate_uuid(dept_id):
        return jsonify({"error": MSG.DEPARTMENT_NOT_FOUND}), 404
    db = get_user_client()
    try:
        existing = db.table("departments").select("id,campus_id").eq("id", dept_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "admin_update_department.lookup")
    if not existing:
        return jsonify({"error": MSG.DEPARTMENT_NOT_FOUND}), 404
    assert_can_modify(existing.get("campus_id"))
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    allowed = {"name", "slug", "faculty", "is_active", "sort_order"}  # campus_id cannot be changed
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    try:
        if "name" in payload:
            payload["name"] = as_text(payload["name"], 150)
        if "faculty" in payload:
            payload["faculty"] = as_text(payload["faculty"], 150)
        if "slug" in payload:
            payload["slug"] = as_text(payload["slug"], 100).lower()
        if "is_active" in payload:
            payload["is_active"] = as_bool(payload["is_active"])
        if "sort_order" in payload:
            payload["sort_order"] = as_int(payload["sort_order"], 0, 100000)
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if "slug" in payload and not _SLUG_RE.match(payload["slug"]):
        return jsonify({"error": MSG.INVALID_SLUG}), 400
    # A changed name or faculty is carried over to profiles by the database trigger departments_cascade_copy (A-07).
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table("departments").eq("id", dept_id).update(payload)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "admin_update_department", MSG.DEPARTMENT_EXISTS)
    if not result:
        return jsonify({"error": MSG.DEPARTMENT_NOT_FOUND}), 404
    return jsonify(result[0] if isinstance(result, list) else result), 200


def _set_department_active(dept_id, active, success_message):
    if not validate_uuid(dept_id):
        return jsonify({"error": MSG.DEPARTMENT_NOT_FOUND}), 404
    db = get_user_client()
    try:
        existing = db.table("departments").select("id,name,campus_id").eq("id", dept_id).single().execute()
        if not existing:
            return jsonify({"error": MSG.DEPARTMENT_NOT_FOUND}), 404
        assert_can_modify(existing.get("campus_id"))
        result = db.table("departments").eq("id", dept_id).update({
            "is_active": active,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "set_department_active")
    if not result:
        return jsonify({"error": MSG.DEPARTMENT_NOT_FOUND}), 404
    return jsonify({"message": success_message.format(name=existing.get("name"))}), 200


@admin_departments_bp.route("/departments/<dept_id>", methods=["DELETE"])
@require_role("admin")
def admin_deactivate_department(dept_id):
    """
    Soft-delete (deactivate) a department (admin only).
    The department is hidden from the user dropdown but existing profile data is preserved.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: dept_id
        type: string
        required: true
    responses:
      200:
        description: Department deactivated
      404:
        description: Department not found
    """
    return _set_department_active(dept_id, False, MSG.DEPARTMENT_DEACTIVATED)


@admin_departments_bp.route("/departments/<dept_id>/restore", methods=["POST"])
@require_role("admin")
def admin_restore_department(dept_id):
    """
    Reactivate a previously deactivated department (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: dept_id
        type: string
        required: true
    responses:
      200:
        description: Department restored
      404:
        description: Department not found
    """
    return _set_department_active(dept_id, True, MSG.DEPARTMENT_RESTORED)
