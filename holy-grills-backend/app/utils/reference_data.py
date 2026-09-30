"""Campus-aware lookups of academic levels and departments (used by register, profile update, graduation)."""
from app.utils.campus_scope import as_campus_id, campus_or_global, prefer_campus_rows


def _safe_campus(campus_id):
    try:
        return as_campus_id(campus_id)
    except ValueError:
        return None


def resolve_level(db, value, campus_id, active_only=True):
    """The level row for `value` as seen from `campus_id`: the campus's own row beats the global one."""
    q = db.table("academic_levels").select("id,name,value,rank,campus_id").eq("value", str(value).strip())
    if active_only:
        q = q.eq("is_active", True)
    rows = campus_or_global(q, _safe_campus(campus_id)).execute() or []
    picked = prefer_campus_rows(rows, lambda r: r["value"])
    return picked[0] if picked else None


def resolve_department(db, name, campus_id, active_only=True):
    """The department row for `name` as seen from `campus_id`: the campus's own row beats the global one."""
    q = db.table("departments").select("id,name,faculty,campus_id").eq("name", str(name).strip())
    if active_only:
        q = q.eq("is_active", True)
    rows = campus_or_global(q, _safe_campus(campus_id)).execute() or []
    picked = prefer_campus_rows(rows, lambda r: r["name"].strip().lower())
    return picked[0] if picked else None
