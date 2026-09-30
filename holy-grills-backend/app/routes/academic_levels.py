"""
Academic Levels routes — public listing and admin CRUD.

User-facing:
  GET  /api/academic-levels            — list active levels (ordered)
  GET  /api/academic-levels/<level_id> — get single level detail

Admin:
  GET    /api/admin/academic-levels             — list all (including inactive)
  POST   /api/admin/academic-levels             — create level
  PATCH  /api/admin/academic-levels/<level_id>  — update level
  DELETE /api/admin/academic-levels/<level_id>  — deactivate (soft-delete)
  POST   /api/admin/academic-levels/<level_id>/restore — reactivate

Design note: academic_level is a dropdown so users cannot type "200" vs "200 Level" —
admin controls the canonical list (e.g. "100 Level", "200 Level", "Postgraduate").
"""

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

# Academic levels are global (platform-wide) by default, but a campus can define its
# own overrides (campus_id set) — see prefer_campus_rows below.
academic_levels_bp = Blueprint("academic_levels", __name__)
admin_academic_levels_bp = Blueprint("admin_academic_levels", __name__)

# ---------------------------------------------------------------------------
# User-facing endpoints (no auth required — used at registration)
# ---------------------------------------------------------------------------

@academic_levels_bp.route("", methods=["GET"])
@optional_auth
def list_academic_levels():
    """
    List active academic levels in sort order.
    No authentication required — used to populate the registration dropdown.
    ---
    tags: [Academic Levels]
    security: []
    parameters:
      - in: query
        name: campus_id
        type: string
        required: false
    responses:
      200:
        description: List of active academic levels
        schema:
          properties:
            levels:
              type: array
              items:
                properties:
                  id: {type: string}
                  name: {type: string, example: "200 Level"}
                  value: {type: string, example: "200L"}
                  sort_order: {type: integer}
            count: {type: integer}
    """
    db = get_user_client()
    from app.routes.events import _get_campus_id
    try:
        requested = as_campus_id(_get_campus_id())
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    campus_id = public_campus(requested)
    try:
        q = db.table("academic_levels").select("id,name,value,sort_order,campus_id").eq("is_active", True)
        rows = campus_or_global(q, campus_id).order("sort_order", ascending=True).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        logger.error("list_academic_levels failed: %s", e)
        return jsonify({"error": MSG.REFERENCE_DATA_UNAVAILABLE}), 503
    rows = prefer_campus_rows(rows, lambda r: r["value"])
    return jsonify({"levels": rows, "count": len(rows)}), 200


@academic_levels_bp.route("/<level_id>", methods=["GET"])
def get_academic_level(level_id):
    """
    Get a single academic level by ID (active only).
    ---
    tags: [Academic Levels]
    security: []
    parameters:
      - in: path
        name: level_id
        type: string
        required: true
    responses:
      200:
        description: Academic level detail
      404:
        description: Not found or inactive
    """
    if not validate_uuid(level_id):
        return jsonify({"error": MSG.ACADEMIC_LEVEL_NOT_FOUND}), 404
    db = get_user_client()
    try:
        row = (
            db.table("academic_levels").select("id,name,value,sort_order,campus_id")
            .eq("id", level_id).eq("is_active", True).single().execute()
        )
    except (SupabaseError, requests.RequestException) as e:
        logger.error("get_academic_level failed: %s", e)
        return jsonify({"error": MSG.REFERENCE_DATA_UNAVAILABLE}), 503
    if not row:
        return jsonify({"error": MSG.ACADEMIC_LEVEL_NOT_FOUND}), 404
    return jsonify(row), 200


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@admin_academic_levels_bp.route("/academic-levels", methods=["GET"])
@require_role("admin")
def admin_list_academic_levels():
    """
    List all academic levels including inactive ones (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: is_active
        type: boolean
    responses:
      200:
        description: All academic levels
    """
    # (unchanged — ADM-08)
    db = get_user_client()
    q = db.table("academic_levels").select("*")
    if request.args.get("is_active") is not None:
        q = q.eq("is_active", request.args.get("is_active").lower() == "true")
    rows = q.order("sort_order", ascending=True).execute() or []
    return jsonify({"levels": rows, "count": len(rows)}), 200


@admin_academic_levels_bp.route("/academic-levels", methods=["POST"])
@require_role("admin")
def admin_create_academic_level():
    """
    Create a new academic level (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, value]
          properties:
            name:
              type: string
              description: Display name shown in dropdown (e.g. "200 Level")
            value:
              type: string
              description: Stored value on the profile (e.g. "200L")
            sort_order:
              type: integer
              default: 0
            is_active:
              type: boolean
              default: true
            rank:
              type: integer
              description: Optional ordering rank (0-100000), separate from sort_order
            campus_id:
              type: string
              description: Optional — omit for a global level. super_admin only; campus admins always get their own campus.
    responses:
      201:
        description: Level created
      400:
        description: Validation error
      409:
        description: Duplicate value
    """
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    if not data.get("name") or not data.get("value"):
        return jsonify({"error": MSG.ACADEMIC_LEVEL_NAME_VALUE_REQUIRED}), 400
    try:
        name = as_text(data["name"], 100)
        value = as_text(data["value"], 50)
        is_active = as_bool(data.get("is_active", True))
        sort_order = as_int(data.get("sort_order", 0), 0, 100000)
        rank = as_int(data["rank"], 0, 100000) if data.get("rank") is not None else None
        requested_campus = as_campus_id(data.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    # Campus admin: always their own campus (403 if they name another). super_admin: the named campus, or global.
    campus_id = resolve_write_campus(requested_campus)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "name": name, "value": value, "is_active": is_active, "sort_order": sort_order,
        "campus_id": campus_id, "created_at": now, "updated_at": now,
    }
    if rank is not None:
        payload["rank"] = rank
    db = get_user_client()
    try:
        row = db.table("academic_levels").insert(payload)
        row = row[0] if isinstance(row, list) and row else row
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "admin_create_academic_level", MSG.ACADEMIC_LEVEL_EXISTS.format(value=value))
    return jsonify(row), 201


@admin_academic_levels_bp.route("/academic-levels/<level_id>", methods=["PATCH"])
@require_role("admin")
def admin_update_academic_level(level_id):
    """
    Update an academic level (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: level_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            name: {type: string}
            value: {type: string}
            is_active: {type: boolean}
            sort_order: {type: integer}
            rank: {type: integer}
    responses:
      200:
        description: Level updated
      404:
        description: Not found
    """
    if not validate_uuid(level_id):
        return jsonify({"error": MSG.ACADEMIC_LEVEL_NOT_FOUND}), 404
    db = get_user_client()
    try:
        existing = db.table("academic_levels").select("id,value,campus_id").eq("id", level_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "admin_update_academic_level.lookup")
    if not existing:
        return jsonify({"error": MSG.ACADEMIC_LEVEL_NOT_FOUND}), 404
    assert_can_modify(existing.get("campus_id"))
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    allowed = {"name", "value", "is_active", "sort_order", "rank"}  # campus_id cannot be changed
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    try:
        if "name" in payload:
            payload["name"] = as_text(payload["name"], 100)
        if "value" in payload:
            payload["value"] = as_text(payload["value"], 50)
        if "is_active" in payload:
            payload["is_active"] = as_bool(payload["is_active"])
        if "sort_order" in payload:
            payload["sort_order"] = as_int(payload["sort_order"], 0, 100000)
        if "rank" in payload:
            payload["rank"] = None if payload["rank"] is None else as_int(payload["rank"], 0, 100000)
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    # A changed `value` is carried over to profiles by the database trigger academic_levels_cascade_value (A-07).
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table("academic_levels").eq("id", level_id).update(payload)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(
            e, "admin_update_academic_level",
            MSG.ACADEMIC_LEVEL_EXISTS.format(value=payload.get("value", "")),
        )
    if not result:
        return jsonify({"error": MSG.ACADEMIC_LEVEL_NOT_FOUND}), 404
    return jsonify(result[0] if isinstance(result, list) else result), 200


def _set_level_active(level_id, active, success_message):
    if not validate_uuid(level_id):
        return jsonify({"error": MSG.ACADEMIC_LEVEL_NOT_FOUND}), 404
    db = get_user_client()
    try:
        existing = db.table("academic_levels").select("id,name,campus_id").eq("id", level_id).single().execute()
        if not existing:
            return jsonify({"error": MSG.ACADEMIC_LEVEL_NOT_FOUND}), 404
        assert_can_modify(existing.get("campus_id"))
        result = db.table("academic_levels").eq("id", level_id).update({
            "is_active": active,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "set_academic_level_active")
    if not result:
        return jsonify({"error": MSG.ACADEMIC_LEVEL_NOT_FOUND}), 404
    return jsonify({"message": success_message.format(name=existing.get("name"))}), 200


@admin_academic_levels_bp.route("/academic-levels/<level_id>", methods=["DELETE"])
@require_role("admin")
def admin_deactivate_academic_level(level_id):
    """
    Soft-delete (deactivate) an academic level (admin only).
    Hidden from the user dropdown but existing profile data is preserved.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: level_id
        type: string
        required: true
    responses:
      200:
        description: Level deactivated
      404:
        description: Not found
    """
    return _set_level_active(level_id, False, MSG.ACADEMIC_LEVEL_DEACTIVATED)


@admin_academic_levels_bp.route("/academic-levels/<level_id>/restore", methods=["POST"])
@require_role("admin")
def admin_restore_academic_level(level_id):
    """
    Reactivate a previously deactivated academic level (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: level_id
        type: string
        required: true
    responses:
      200:
        description: Level restored
      404:
        description: Not found
    """
    return _set_level_active(level_id, True, MSG.ACADEMIC_LEVEL_RESTORED)
