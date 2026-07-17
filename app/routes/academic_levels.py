"""Academic Levels routes — public listing and admin CRUD.

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

from flask import Blueprint, request, jsonify
from app.middleware.auth import require_role
from app.db import get_db
from datetime import datetime, timezone

academic_levels_bp = Blueprint("academic_levels", __name__)
admin_academic_levels_bp = Blueprint("admin_academic_levels", __name__)

# ---------------------------------------------------------------------------
# User-facing endpoints (no auth required — used at registration)
# ---------------------------------------------------------------------------

@academic_levels_bp.route("", methods=["GET"])
def list_academic_levels():
    """
    List active academic levels in sort order.
    No authentication required — used to populate the registration dropdown.
    ---
    tags: [Academic Levels]
    security: []
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
    db = get_db()
    try:
        rows = (
            db.table("academic_levels")
            .select("id,name,value,sort_order")
            .eq("is_active", True)
            .order("sort_order", ascending=True)
            .execute()
        ) or []
    except Exception:
        rows = []
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
    db = get_db()
    try:
        row = (
            db.table("academic_levels")
            .select("id,name,value,sort_order")
            .eq("id", level_id)
            .eq("is_active", True)
            .single()
            .execute()
        )
    except Exception:
        row = None
    if not row:
        return jsonify({"error": "Academic level not found"}), 404
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
    db = get_db()
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
    responses:
      201:
        description: Level created
      400:
        description: Validation error
      409:
        description: Duplicate value
    """
    data = request.get_json(force=True) or {}
    if not data.get("name") or not data.get("value"):
        return jsonify({"error": "'name' and 'value' are required"}), 400

    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    try:
        row = db.table("academic_levels").insert({
            "name": data["name"].strip(),
            "value": data["value"].strip(),
            "is_active": bool(data.get("is_active", True)),
            "sort_order": int(data.get("sort_order", 0)),
            "created_at": now,
            "updated_at": now,
        })
        row = row[0] if isinstance(row, list) else row
    except Exception as e:
        err = str(e)
        if "unique" in err.lower() or "duplicate" in err.lower():
            return jsonify({"error": f"An academic level with value '{data['value']}' already exists"}), 409
        return jsonify({"error": f"Failed to create academic level: {err}"}), 500

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
    responses:
      200:
        description: Level updated
      404:
        description: Not found
    """
    db = get_db()
    existing = db.table("academic_levels").select("id").eq("id", level_id).single().execute()
    if not existing:
        return jsonify({"error": "Academic level not found"}), 404

    data = request.get_json(force=True) or {}
    allowed = {"name", "value", "is_active", "sort_order"}
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"error": "No valid fields to update"}), 400

    if "name" in payload:
        payload["name"] = payload["name"].strip()
    if "value" in payload:
        payload["value"] = payload["value"].strip()
    if "is_active" in payload:
        payload["is_active"] = bool(payload["is_active"])
    if "sort_order" in payload:
        payload["sort_order"] = int(payload["sort_order"])

    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = db.table("academic_levels").eq("id", level_id).update(payload)
        result = result[0] if isinstance(result, list) else result
    except Exception as e:
        return jsonify({"error": f"Update failed: {e}"}), 500

    return jsonify(result), 200


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
    db = get_db()
    existing = db.table("academic_levels").select("id,name").eq("id", level_id).single().execute()
    if not existing:
        return jsonify({"error": "Academic level not found"}), 404

    db.table("academic_levels").eq("id", level_id).update({
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": f"Academic level '{existing.get('name')}' deactivated"}), 200


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
    db = get_db()
    existing = db.table("academic_levels").select("id,name").eq("id", level_id).single().execute()
    if not existing:
        return jsonify({"error": "Academic level not found"}), 404

    db.table("academic_levels").eq("id", level_id).update({
        "is_active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": f"Academic level '{existing.get('name')}' restored"}), 200
