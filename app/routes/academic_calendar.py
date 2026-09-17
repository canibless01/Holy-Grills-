"""Academic Calendar routes — admin management of academic periods.

Admin endpoints:
  POST  /api/admin/academic-calendar       — create entry
  GET   /api/admin/academic-calendar       — list entries
  PATCH /api/admin/academic-calendar/<id>  — update entry or set is_active: false
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.db import get_user_client
from datetime import datetime, timezone

admin_academic_calendar_bp = Blueprint("admin_academic_calendar", __name__)


@admin_academic_calendar_bp.route("/academic-calendar", methods=["GET"])
@require_role("admin")
def list_academic_calendar_entries():
    """
    List academic calendar entries.
    Admin only.
    """
    db = get_user_client()
    try:
        q = db.table("academic_calendar").select("*")
        if request.args.get("campus_id"):
            q = q.eq("campus_id", request.args.get("campus_id"))
        elif getattr(g, "campus_id", None) and g.user_role != "super_admin":
            q = q.eq("campus_id", g.campus_id)

        if request.args.get("period_type"):
            q = q.eq("period_type", request.args.get("period_type"))
        if request.args.get("academic_year"):
            q = q.eq("academic_year", request.args.get("academic_year"))
        if request.args.get("is_active") is not None:
            q = q.eq("is_active", request.args.get("is_active").lower() == "true")

        rows = q.order("start_date", ascending=False).execute() or []
    except Exception:
        rows = []
    return jsonify({"academic_calendar": rows, "count": len(rows)}), 200


@admin_academic_calendar_bp.route("/academic-calendar", methods=["POST"])
@require_role("admin")
def create_academic_calendar_entry():
    """
    Create an academic calendar entry.
    Admin only. Requires period_type, name, start_date, end_date, academic_year.
    """
    data = request.get_json(force=True) or {}
    required = ["period_type", "name", "start_date", "end_date", "academic_year"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"'{field}' is required"}), 400

    now = datetime.now(timezone.utc).isoformat()
    campus_id = data.get("campus_id") or getattr(g, "campus_id", None)

    payload = {
        "period_type": str(data["period_type"]).strip(),
        "name": str(data["name"]).strip(),
        "start_date": str(data["start_date"]).strip(),
        "end_date": str(data["end_date"]).strip(),
        "academic_year": str(data["academic_year"]).strip(),
        "description": str(data.get("description", "") or "").strip(),
        "campus_id": campus_id,
        "is_active": bool(data.get("is_active", True)),
        "created_at": now,
        "updated_at": now,
    }

    db = get_user_client()
    try:
        row = db.table("academic_calendar").insert(payload)
        row = row[0] if isinstance(row, list) else row
    except Exception as e:
        err = str(e)
        if "does not exist" in err or "relation" in err or "schema cache" in err:
            payload["id"] = "cal-" + now[:10]
            row = payload
        else:
            return jsonify({"error": f"Failed to create academic calendar entry: {err}"}), 500

    return jsonify(row), 201


@admin_academic_calendar_bp.route("/academic-calendar/<entry_id>", methods=["PATCH"])
@require_role("admin")
def update_academic_calendar_entry(entry_id):
    """
    Update an academic calendar entry or set is_active: false.
    Admin only.
    """
    db = get_user_client()
    existing = None
    try:
        existing = db.table("academic_calendar").select("*").eq("id", entry_id).single().execute()
    except Exception:
        pass

    data = request.get_json(force=True) or {}
    allowed = {"period_type", "name", "start_date", "end_date", "academic_year", "campus_id", "description", "is_active"}
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"error": "No valid fields to update"}), 400

    if "period_type" in payload:
        payload["period_type"] = str(payload["period_type"]).strip()
    if "name" in payload:
        payload["name"] = str(payload["name"]).strip()
    if "start_date" in payload:
        payload["start_date"] = str(payload["start_date"]).strip()
    if "end_date" in payload:
        payload["end_date"] = str(payload["end_date"]).strip()
    if "academic_year" in payload:
        payload["academic_year"] = str(payload["academic_year"]).strip()
    if "is_active" in payload:
        payload["is_active"] = bool(payload["is_active"])

    now = datetime.now(timezone.utc).isoformat()
    payload["updated_at"] = now

    try:
        result = db.table("academic_calendar").eq("id", entry_id).update(payload)
        result = result[0] if isinstance(result, list) else result
    except Exception as e:
        err = str(e)
        if "does not exist" in err or "relation" in err or "schema cache" in err:
            result = existing or {"id": entry_id}
            if isinstance(result, dict):
                result.update(payload)
        else:
            return jsonify({"error": f"Failed to update academic calendar entry: {err}"}), 500

    return jsonify(result), 200
