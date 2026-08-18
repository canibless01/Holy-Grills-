"""Departments routes — public listing and admin CRUD.

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

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.db import get_db
from datetime import datetime, timezone

departments_bp = Blueprint("departments", __name__)
admin_departments_bp = Blueprint("admin_departments", __name__)

# ---------------------------------------------------------------------------
# User-facing endpoints
# ---------------------------------------------------------------------------

@departments_bp.route("", methods=["GET"])
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
    responses:
      200:
        description: List of active departments
    """
    db = get_db()
    try:
        q = db.table("departments").select("id,name,slug,faculty,sort_order").eq("is_active", True)
        faculty_filter = request.args.get("faculty")
        if faculty_filter:
            q = q.eq("faculty", faculty_filter)
        rows = q.order("sort_order", ascending=True).execute() or []
    except Exception:
        rows = []

    grouped = request.args.get("grouped", "false").lower() == "true"
    if not grouped:
        return jsonify({"departments": rows, "count": len(rows)}), 200

    # Group by faculty
    by_faculty: dict = {}
    for dept in rows:
        fac = dept.get("faculty", "Other")
        by_faculty.setdefault(fac, []).append(dept)

    result = [
        {"faculty": fac, "departments": depts}
        for fac, depts in sorted(by_faculty.items())
    ]
    return jsonify({"faculties": result, "count": len(rows)}), 200


@departments_bp.route("/faculties", methods=["GET"])
def list_faculties():
    """
    List distinct faculty names from active departments.
    ---
    tags: [Departments]
    security: []
    responses:
      200:
        description: List of faculty names
    """
    db = get_db()
    try:
        rows = db.table("departments").select("faculty").eq("is_active", True).execute() or []
        faculties = sorted({r["faculty"] for r in rows if r.get("faculty")})
    except Exception:
        faculties = []
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
    db = get_db()
    try:
        # Enforce is_active for the public endpoint — inactive depts are admin-only
        dept = (
            db.table("departments")
            .select("id,name,slug,faculty,sort_order")
            .eq("id", dept_id)
            .eq("is_active", True)
            .single()
            .execute()
        )
    except Exception:
        dept = None
    if not dept:
        return jsonify({"error": "Department not found"}), 404
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
    db = get_db()
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
    responses:
      201:
        description: Department created
      400:
        description: Validation error
    """
    data = request.get_json(force=True) or {}
    if not data.get("name") or not data.get("faculty"):
        return jsonify({"error": "'name' and 'faculty' are required"}), 400

    slug = (data.get("slug") or "").strip()
    if not slug:
        slug = data["name"].lower().replace(" ", "-").replace("&", "and")
        import re
        slug = re.sub(r"[^a-z0-9-]", "", slug)

    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    try:
        row = db.table("departments").insert({
            "name": data["name"].strip(),
            "slug": slug,
            "faculty": data["faculty"].strip(),
            "is_active": bool(data.get("is_active", True)),
            "sort_order": int(data.get("sort_order", 0)),
            "created_at": now,
            "updated_at": now,
        })
        row = row[0] if isinstance(row, list) else row
    except Exception as e:
        err = str(e)
        if "unique" in err.lower() or "duplicate" in err.lower():
            return jsonify({"error": f"A department with slug '{slug}' already exists"}), 409
        return jsonify({"error": f"Failed to create department: {err}"}), 500

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
    db = get_db()
    existing = db.table("departments").select("id").eq("id", dept_id).single().execute()
    if not existing:
        return jsonify({"error": "Department not found"}), 404

    data = request.get_json(force=True) or {}
    allowed = {"name", "slug", "faculty", "is_active", "sort_order"}
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"error": "No valid fields to update"}), 400

    if "name" in payload:
        payload["name"] = payload["name"].strip()
    if "faculty" in payload:
        payload["faculty"] = payload["faculty"].strip()
    if "is_active" in payload:
        payload["is_active"] = bool(payload["is_active"])
    if "sort_order" in payload:
        payload["sort_order"] = int(payload["sort_order"])

    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = db.table("departments").eq("id", dept_id).update(payload)
        result = result[0] if isinstance(result, list) else result
    except Exception as e:
        return jsonify({"error": f"Update failed: {e}"}), 500

    return jsonify(result), 200


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
    db = get_db()
    existing = db.table("departments").select("id,name").eq("id", dept_id).single().execute()
    if not existing:
        return jsonify({"error": "Department not found"}), 404

    db.table("departments").eq("id", dept_id).update({
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": f"Department '{existing.get('name')}' deactivated"}), 200


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
    db = get_db()
    existing = db.table("departments").select("id,name").eq("id", dept_id).single().execute()
    if not existing:
        return jsonify({"error": "Department not found"}), 404

    db.table("departments").eq("id", dept_id).update({
        "is_active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": f"Department '{existing.get('name')}' restored"}), 200
